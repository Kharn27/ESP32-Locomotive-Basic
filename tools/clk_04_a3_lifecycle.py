#!/usr/bin/env python3
"""CLK-04-A3: sealed, ROM-backed CPC6128 TIME lifecycle acquisition and replay.

Only observations from a single genuine Caprice32 process are compared within
each session. ROM and full SNA are NEVER shipped. No production TIME code.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clk_03_cpc_time as prior
import clk_04_real5_oracle as a1
import clk_04_a2_numeric as candidate

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/cpc6128/clk_04_a3_lifecycle/corpus.json"
CORPUS_SHA = "7ad864070855715c3b004aed86546420b2f7149026b3a6ac6ab52f3dabde5631"
SESSIONS = ("original", "repeat")
PINS = {"image": prior.IMAGE, "caprice_commit": prior.CAP_SHA,
        "rom_sha256": prior.ROM_SHA}
need, sha, read, canonical = prior.need, prior.sha, prior.read, prior.canonical
NUM = re.compile(rb"[ \t]*([+]?(?:[0-9]+(?:\.[0-9]*)?|[0-9]*\.[0-9]+)(?:[Ee][+-]?[0-9]+)?)[ \t\r]*\Z")
LIST = re.compile(rb"[ \t]*([0-9]{1,5})[ \t]+(.+?)[ \t\r]*\Z")


def protocol():
    data = read(CORPUS)
    need(sha(data) == CORPUS_SHA, "CORPUS_SHA_DRIFT")
    obj = json.loads(data)
    need(obj["schema"] == 1 and obj["mission"] == "CLK-04-A3"
         and obj["status"] == "SEALED_INPUTS_NOT_OBSERVATIONS"
         and obj["sessions"] == list(SESSIONS), "CORPUS_METADATA")
    stages = obj["stages"]
    need([x["id"] for x in stages] ==
         ["boot", "idle", "run_first", "run_second", "new_direct",
          "clear_direct", "stop_wait_cont"], "STAGE_ORDER")
    for x in stages:
        need(len(x["commands"]) > 0 and all(isinstance(c, str) and
             c.isascii() and "\n" not in c and "\r" not in c for c in x["commands"]),
             "COMMANDS_NOT_LITERAL")
    commands = [c for s in stages for c in s["commands"]]
    need(sum(c.count("CAP32_DELAY") for c in commands) <=
         obj["bounds"]["maximum_delay_tokens_per_session"], "DELAY_BUDGET")
    need(commands[-1].endswith("CAP32_EXIT"), "MISSING_BOUNDED_EXIT")
    need(sum(len(s["screens"]) for s in stages) ==
         len(obj["screens_expected"]) == 10 and
         [x for s in stages for x in s["screens"]] == obj["screens_expected"],
         "SCREEN_PROTOCOL_ORDER")
    need(sum(len(s["snaps"]) for s in stages) ==
         len(obj["snapshots_expected"]) == 5 and
         [x for s in stages for x in s["snaps"]] == obj["snapshots_expected"],
         "SNAP_PROTOCOL_ORDER")
    need(sum(c.count("CAP32_SCRNSHOT") for c in commands) == 10 and
         sum(c.count("CAP32_SNAPSHOT") for c in commands) == 5,
         "CAPTURE_COMMAND_COUNT")
    need(obj["programs"]["run"] == [
        "10 T!=TIME", "20 STOP", '30 PRINT #8,"A3:RUN:CONT"',
        "40 PRINT #8,@T!", "50 PRINT #8,T!", "60 PRINT #8,TIME",
        "70 PRINT #8,TIME", "80 END"], "RUN_PROGRAM_DRIFT")
    need(obj["programs"]["stop"] == [
        '10 PRINT #8,"A3:STOP:BEFORE"', "20 PRINT #8,TIME",
        "30 T!=TIME", "40 STOP", '50 PRINT #8,"A3:STOP:AFTER"',
        "60 PRINT #8,@T!", "70 PRINT #8,T!", "80 PRINT #8,TIME",
        "90 PRINT #8,TIME", "100 END"], "STOP_PROGRAM_DRIFT")
    need(obj["caprice_commit"] == prior.CAP_SHA and
         obj["rom_sha256"] == prior.ROM_SHA and obj["image"] == prior.IMAGE,
         "CORPUS_PIN_DRIFT")
    return obj


def integer(line):
    m = NUM.fullmatch(line)
    need(m is not None, "PRINTER_NUMBER_AMBIGUOUS")
    try:
        number = Decimal(m.group(1).decode("ascii"))
    except InvalidOperation as exc:
        raise prior.OracleError("PRINTER_DECIMAL_INVALID") from exc
    need(number.is_finite() and number >= 0 and
         number == number.to_integral_value() and number <= 4294967295,
         "PRINTER_NOT_UNSIGNED_EXACT_INTEGER")
    return int(number)


def observe_printer(raw, proto):
    """Require exact ordering and identity; LIST streams are never numeric probes."""
    rows = [x.strip() for x in raw.splitlines() if x.strip()]
    pos, values, lists = 0, {}, {}
    def marker(label):
        nonlocal pos
        need(pos < len(rows) and rows[pos] == ("A3:" + label).encode(),
             "PRINTER_MARKER_OR_ORDER_" + label)
        pos += 1
    def num(name):
        nonlocal pos
        need(pos < len(rows), "PRINTER_MISSING_" + name)
        values[name] = integer(rows[pos])
        pos += 1
    def listing(name, program):
        nonlocal pos
        nums, lines = [], []
        for line in program:
            need(pos < len(rows), "PRINTER_LIST_MISSING_" + name)
            m = LIST.fullmatch(rows[pos])
            need(m is not None and int(m.group(1)) == int(line.split(" ", 1)[0]),
                 "PRINTER_LIST_ORDER_" + name)
            # ROM LIST produces the source form; allow spacing, not missing tokens.
            body = m.group(2).decode("ascii", "strict").replace(" ", "")
            expected = line.split(" ", 1)[1].replace(" ", "")
            need(body.upper() == expected.upper(),
                 "PRINTER_LIST_TEXT_" + name)
            nums.append(int(m.group(1)))
            lines.append(rows[pos].decode("ascii"))
            pos += 1
        lists[name] = lines
    marker("BOOT")
    num("boot_1"); num("boot_2")
    marker("IDLE")
    for i in range(1, 5):
        num("idle_" + str(i))
    marker("RUN:PRE")
    num("run_pre")
    listing("run", proto["programs"]["run"])
    for run in (1, 2):
        marker("RUN:CONT")
        for kind in ("address", "stored", "after_1", "after_2"):
            num("run%d_%s" % (run, kind))
    marker("RUN:POST")
    num("run_post")
    marker("NEW:BEFORE")
    num("new_before")
    # LIST #8 immediately after NEW must contribute ZERO numbered lines here.
    marker("NEW:AFTER")
    num("new_after")
    marker("CLEAR:BEFORE")
    num("clear_before_var"); num("clear_before_time")
    marker("CLEAR:AFTER")
    num("clear_after_var"); num("clear_after_time")
    listing("stop", proto["programs"]["stop"])
    marker("STOP:BEFORE")
    num("stop_before")
    marker("STOP:AFTER")
    for kind in ("address", "stored", "after_1", "after_2"):
        num("stop_" + kind)
    marker("FINAL")
    num("final")
    need(pos == len(rows), "PRINTER_TRAILING_OR_DUPLICATE")
    need(values["clear_before_var"] == 777 and
         values["clear_after_var"] == 0, "CLEAR_VARIABLE_CONTROL")
    return {"values": values, "lists": lists, "printer_lines": len(rows)}


def snapshot_program(snapshot, lines):
    parser = prior.ram_parser()
    program, region = parser.extract_snapshot(snapshot, [int(
        line.split(" ", 1)[0]) for line in lines])
    need(b"\xff\x46" in program, "TIME_RAM_TOKEN_ABSENT")
    return program, region


def stop_witness(snapshot, lines):
    program, region = snapshot_program(snapshot, lines)
    parser = prior.ram_parser()
    ram = memoryview(snapshot)[parser.HEADER:]
    word = lambda at: int.from_bytes(ram[at:at+2], "little")
    ptrs = {"program_end": word(0xae66), "scalar_start": word(0xae68),
            "array_start": word(0xae6a), "array_end": word(0xae6c)}
    start, end = ptrs["scalar_start"], ptrs["array_start"]
    need(0x016f < ptrs["program_end"] <= start < end <=
         ptrs["array_end"] < 0xac00, "RAM_POINTER_ORDER")
    window = bytes(ram[start:end])
    item = a1.check_window(window, start, [ord("T")])[ord("T")]
    return program, window, {"pointers": ptrs, "region": region,
        "sna_sha256": sha(snapshot), "window_start": start, "window_end": end,
        "window_sha256": sha(window), "scalar": item,
        "real5_from_original_sna": item["value_hex"]}


def link_witness(witness, values, prefix):
    item = witness["scalar"]
    need(values[prefix + "_address"] == item["address"],
         "RAM_AT_ADDRESS_MISMATCH_" + prefix)
    raw = bytes.fromhex(item["value_hex"])
    try:
        decoded = candidate.decode_nonnegative_integer(raw)
    except (ValueError, TypeError) as exc:
        raise prior.OracleError("RAM_REAL5_UNSUPPORTED_" + prefix) from exc
    need(decoded == values[prefix + "_stored"],
         "RAM_REAL5_PRINT_MISMATCH_" + prefix)
    # A subsequent TIME is a separate ROM sample, not identical to stored T!.
    return {"stored_decimal_printed": values[prefix + "_stored"],
            "stored_real5_hex": item["value_hex"],
            "scalar_address": item["address"], "experimental_decoder": decoded,
            "next_time_is_not_simultaneous": True}


def camera_files(folder, proto, started_ns):
    files = sorted(folder.glob("screenshot_*.png"))
    need(len(files) == len(proto["screens_expected"]), "PNG_CARDINALITY")
    result = []
    pngdir = folder / "png"
    pngdir.mkdir()
    for i, (p, ident) in enumerate(zip(files, proto["screens_expected"])):
        need(prior.valid_png(read(p)) and p.stat().st_mtime_ns >= started_ns,
             "PNG_INVALID_OR_STALE_" + ident)
        dest = pngdir / ("%02d_" % i + ident + ".png")
        stamp = p.stat().st_mtime_ns
        name = p.name
        p.rename(dest)
        result.append({"id": ident, "original_filename": name,
                       "relative_filename": dest.relative_to(folder).as_posix(),
                       "utc_mtime": datetime.fromtimestamp(
                           stamp / 1e9, tz=timezone.utc).isoformat()})
    return result


def collect_snapshots(snaps, target, proto, session):
    files = sorted(snaps.glob("*.sna"), key=lambda p:(p.stat().st_mtime_ns,p.name))
    need(len(files) == len(proto["snapshots_expected"]), "SNA_CARDINALITY")
    need(all(p.stat().st_size > 256 + 65536 for p in files),
         "SNA_TRUNCATED")
    witnesses, identities = {}, []
    source = proto["programs"]["run"]
    stop_source = proto["programs"]["stop"]
    expected = proto["snapshots_expected"]
    for p, ident in zip(files, expected):
        blob = read(p)
        if ident in ("run_program", "stop_program"):
            lines = source if ident == "run_program" else stop_source
            program, region = snapshot_program(blob, lines)
            (target / (ident + ".bin")).write_bytes(program)
            witnesses[ident] = {"program_sha256": sha(program), "region": region,
                                "sna_sha256": sha(blob)}
        else:
            lines = stop_source if ident == "stop_wait" else source
            program, window, evidence = stop_witness(blob, lines)
            (target / (ident + "_program.bin")).write_bytes(program)
            (target / (ident + "_window.bin")).write_bytes(window)
            (target / (ident + "_ram.json")).write_bytes(canonical(evidence))
            witnesses[ident] = evidence
            # Execution can legitimately rewrite tokenised RAM pointers.
            # Do not equate pre-RUN and STOP bytes. Keep BOTH original
            # snapshots' program extracts; parser has checked line identities
            # and TIME token independently for each phase.
            need(len(program) > 0, "STOP_PROGRAM_EMPTY")
        identities.append({"id": ident, "sna_sha256": sha(blob),
                           "original_filename": p.name,
                           "utc_mtime": datetime.fromtimestamp(
                               p.stat().st_mtime_ns / 1e9, tz=timezone.utc).isoformat()})
        p.unlink()
    need(not list(snaps.glob("*.sna")), "SNA_LEAK")
    (target / "snapshots_index.json").write_bytes(canonical(identities))
    return witnesses


def execute_session(cap, out, session, proto, snaps):
    folder = out / session / "process"
    need(not folder.exists(), "SESSION_OUTPUT_EXISTS")
    folder.mkdir(parents=True)
    prior.setup(cap, folder, snaps)
    commands = [c for s in proto["stages"] for c in s["commands"]]
    argv = ["xvfb-run", "-a", str(cap / "cap32"), "-c",
            str(folder / "cap32.cfg")]
    for c in commands:
        argv += ["-a", c.replace("CAP32_SNAPSHOT", "\x0c\x0d")]
    (folder / "autocmd.json").write_bytes(canonical({
        "stages": proto["stages"], "commands": commands, "argv": argv}))
    env = dict(os.environ, SDL_VIDEODRIVER="x11", SDL_AUDIODRIVER="dummy")
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic_ns()
    wall_start = time.time_ns()
    proc = subprocess.Popen(argv, cwd=cap, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    try:
        stdout, stderr = proc.communicate(timeout=proto["bounds"]["session_timeout_seconds"])
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        (folder / "stdout.bin").write_bytes(stdout)
        (folder / "stderr.bin").write_bytes(stderr)
        raise prior.OracleError("SESSION_TIMEOUT_" + session)
    elapsed = (time.monotonic_ns() - t0) / 1e9
    ended = datetime.now(timezone.utc).isoformat()
    (folder / "stdout.bin").write_bytes(stdout)
    (folder / "stderr.bin").write_bytes(stderr)
    (folder / "caprice.log").write_bytes((
        "returncode=%d\npid=%d\nstart_utc=%s\nend_utc=%s\nwall_seconds=%.9f\n" %
        (proc.returncode, proc.pid, started, ended, elapsed)).encode("ascii"))
    need(proc.returncode == 0, "SESSION_PROCESS_NONZERO_" + session)
    need(elapsed > 0, "SESSION_BAD_WALL_INTERVAL")
    images = camera_files(folder, proto, wall_start)
    witnesses = collect_snapshots(snaps, folder, proto, session)
    observed = observe_printer(read(folder / "printer.dat"), proto)
    values = observed["values"]
    for label, ident in (("run1", "run1_stop"),
                         ("run2", "run2_stop"), ("stop", "stop_wait")):
        observed[label + "_real5"] = link_witness(witnesses[ident], values, label)
    (folder / "observations.json").write_bytes(canonical(observed))
    (folder / "screens_index.json").write_bytes(canonical(images))
    return {"session_id": session, "process_nonce": uuid.uuid4().hex,
            "pid": proc.pid, "started_utc": started, "ended_utc": ended,
            "wall_seconds": elapsed, "returncode": proc.returncode,
            "screens": [p["id"] for p in images],
            "snaps": [p["id"] for p in json.loads(read(folder / "snapshots_index.json"))],
            "values": values}


def inventory(out):
    files = {}
    for p in sorted(out.rglob("*")):
        if p.is_symlink():
            raise prior.OracleError("EVIDENCE_SYMLINK")
        if p.is_file():
            need(p.suffix.lower() not in (".sna", ".rom"),
                 "SENSITIVE_IMAGE_ARCHIVED")
            if p == out / "manifest.json":
                continue
            files[p.relative_to(out).as_posix()] = {
                "bytes": p.stat().st_size, "sha256": sha(read(p))}
    return files


def acquire(cap, out, head):
    proto = protocol()
    need(prior.SHA40.fullmatch(head or ""), "HEAD_INVALID")
    live = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                   text=True).strip()
    need(head == live, "HEAD_NOT_CHECKED_OUT")
    need(not out.exists(), "OUTPUT_EXISTS")
    need(subprocess.check_output(["git", "-C", str(cap), "rev-parse", "HEAD"],
        text=True).strip() == prior.CAP_SHA, "CAPRICE_COMMIT_MISMATCH")
    need(sha(read(cap / "rom/cpc6128.rom")) == prior.ROM_SHA,
         "ROM_SHA_MISMATCH")
    need((cap / "rom/amsdos.rom").is_file() and (cap / "cap32").is_file(),
         "CPC_BINARY_MISSING")
    version = subprocess.check_output([str(cap / "cap32"), "--version"],
                                      text=True).strip()
    m = {"schema": 1, "mission": "CLK-04-A3",
         "status": "ACQUISITION_PARTIAL", "head": head,
         "corpus_sha256": CORPUS_SHA, **PINS,
         "caprice_version": version,
         "run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"),
         "observation_class": "CPC6128_CAPRICE32_ROM_BACKED",
         "rom_archived": False, "snapshot_archived": False,
         "sessions": {}, "files": {}}
    out.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix="clk04-a3-sna-") as tmp:
            for session in SESSIONS:
                snap = Path(tmp) / session
                snap.mkdir()
                gate = prior.speed_gate(cap, out, session, snap)
                # Explicitly destroy any gate-generated SNA before main process.
                need(not list(snap.glob("*.sna")), "GATE_SNA_LEAK")
                observation = execute_session(cap, out, session, proto, snap)
                m["sessions"][session] = {"speed_gate": gate, "observation": observation}
        m["status"] = "ACQUIRED_PENDING_PNG_REVIEW"
    finally:
        m["files"] = inventory(out)
        (out / "manifest.json").write_bytes(canonical(m))
    need(m["status"] == "ACQUIRED_PENDING_PNG_REVIEW", "CPC_ORACLE_UNVERIFIED")
    print("CLK04_A3_MANIFEST_SHA256_LOCAL=" + sha(read(out / "manifest.json")))
    print("CLK04_A3_PNG_INSPECTION=PENDING_NOT_VERIFIED")


def verify(out, head, seal):
    proto = protocol()
    need(prior.SHA40.fullmatch(head or ""), "HEAD_INVALID")
    need(prior.SHA64.fullmatch(seal or "") and
         sha(read(out / "manifest.json")) == seal, "EXTERNAL_SEAL_REQUIRED")
    m = json.loads(read(out / "manifest.json"))
    need(m.get("schema") == 1 and m.get("mission") == "CLK-04-A3"
         and m.get("status") == "ACQUIRED_PENDING_PNG_REVIEW"
         and m.get("head") == head, "HEAD_OR_MANIFEST_MISMATCH")
    need(all(m.get(k) == v for k, v in PINS.items()) and
         m.get("corpus_sha256") == CORPUS_SHA and
         m.get("rom_archived") is False and
         m.get("snapshot_archived") is False and
         m.get("observation_class") == "CPC6128_CAPRICE32_ROM_BACKED",
         "PROVENANCE_MISMATCH")
    need(set(m.get("sessions", {})) == set(SESSIONS),
         "SESSIONS_MISSING_OR_EXTRA")
    actual = inventory(out)
    need(set(actual) == set(m["files"]), "RAW_FILE_SET_DRIFT")
    for k, record in m["files"].items():
        # A successful CPC process may write zero stderr bytes. The exact
        # empty file and SHA256 still belong to the mandatory RAW inventory.
        need(actual[k] == record and
             (record["bytes"] > 0 or
              (record["bytes"] == 0 and k.endswith("/process/stderr.bin"))),
             "RAW_HASH_OR_SIZE_DRIFT_" + k)
    seen_nonces, start_stamps = [], []
    for session in SESSIONS:
        state = m["sessions"][session]
        gate = state["speed_gate"]
        need(255 <= gate["ticks_per_wall_second"] <= 345 and
             gate["delta_wall_seconds"] > .5,
             "SESSION_SPEED_GUARD_" + session)
        meta = state["observation"]
        folder = out / session / "process"
        need(meta["session_id"] == session and
             meta["returncode"] == 0 and meta["pid"] > 0 and
             meta["wall_seconds"] > 0,
             "SESSION_PROCESS_IDENTITY")
        started = datetime.fromisoformat(meta["started_utc"])
        ended = datetime.fromisoformat(meta["ended_utc"])
        need(started.tzinfo is not None and ended > started,
             "SESSION_TIMESTAMP_INVALID")
        start_stamps.append(started)
        seen_nonces.append(meta["process_nonce"])
        prior.cfg_validate(folder / "cap32.cfg")
        cfg = read(folder / "cap32.cfg")
        # The replay occurs in a different checkout and RUNNER_TEMP. Reconstruct
        # paths from the original, sealed autocmd argv instead of the replay
        # extraction path. They must agree *within* the original CPC process.
        need(b"printer_file=" in cfg, "CFG_PRINTER_MISSING")
        log = read(folder / "caprice.log")
        need(("returncode=0\npid=%d\n" % meta["pid"]).encode() in log,
             "PROCESS_LOG_PID_MISMATCH")
        auto = json.loads(read(folder / "autocmd.json"))
        commands = [c for stage in proto["stages"] for c in stage["commands"]]
        need(auto["commands"] == commands and auto["stages"] == proto["stages"],
             "AUTOMATION_PROTOCOL_DRIFT")
        observed_argv = auto["argv"]
        need(isinstance(observed_argv, list) and len(observed_argv) >= 5
             and observed_argv[:2] == ["xvfb-run", "-a"]
             and observed_argv[3] == "-c"
             and observed_argv[2].endswith("/tests/oracles/caprice32/cap32"),
             "PROCESS_ARGV_PREFIX_DRIFT")
        original_cfg = Path(observed_argv[4])
        need(original_cfg.is_absolute() and original_cfg.name == "cap32.cfg"
             and original_cfg.parent.name == "process"
             and original_cfg.parent.parent.name == session
             and ("/printer.dat").encode() in cfg
             and ("printer_file=" + str(original_cfg.parent / "printer.dat")).encode() in cfg,
             "PROCESS_CFG_PATH_OR_IDENTITY_DRIFT")
        expected_argv = observed_argv[:5]
        for c in commands:
            expected_argv += ["-a", c.replace("CAP32_SNAPSHOT", "\x0c\x0d")]
        need(observed_argv == expected_argv, "PROCESS_ARGV_DRIFT")
        images = json.loads(read(folder / "screens_index.json"))
        need([x["id"] for x in images] == proto["screens_expected"],
             "SCREEN_INDEX_DRIFT")
        for i, shot in enumerate(images):
            need(shot["relative_filename"] ==
                 "png/%02d_%s.png" % (i, shot["id"]) and
                 prior.valid_png(read(folder / shot["relative_filename"])),
                 "PNG_MISSING_OR_INVALID")
        snaps = json.loads(read(folder / "snapshots_index.json"))
        need([x["id"] for x in snaps] == proto["snapshots_expected"] and
             meta["snaps"] == proto["snapshots_expected"],
             "SNAP_IDENTITY_DRIFT")
        for idx, name in enumerate(proto["snapshots_expected"]):
            if name in ("run_program", "stop_program"):
                program = read(folder / (name + ".bin"))
                need(len(program) > 0 and b"\xff\x46" in program,
                     "SNAP_PROGRAM_MISSING_OR_TIME_TOKEN")
            else:
                w = read(folder / (name + "_window.bin"))
                data = json.loads(read(folder / (name + "_ram.json")))
                need(sha(w) == data["window_sha256"] ==
                     sha(w) and data["sna_sha256"] == snaps[idx]["sna_sha256"],
                     "SNA_WINDOW_INTEGRITY")
                derived = a1.check_window(w, data["window_start"], [ord("T")])[ord("T")]
                need(derived == data["scalar"] and
                     data["window_end"] == data["window_start"] + len(w),
                     "RAM_SCALAR_FORGERY")
        observed = observe_printer(read(folder / "printer.dat"), proto)
        stored = json.loads(read(folder / "observations.json"))
        need(observed["values"] == stored["values"] and
             observed["lists"] == stored["lists"] and
             observed["values"] == meta["values"],
             "PRINTED_OBSERVATION_DRIFT")
        for label, ident in (("run1", "run1_stop"), ("run2", "run2_stop"),
                             ("stop", "stop_wait")):
            witness = json.loads(read(folder / (ident + "_ram.json")))
            link = link_witness(witness, observed["values"], label)
            need(link == stored[label + "_real5"], "REAL5_LINK_CHANGED")
        # Verify the stored program has TIME token in the original RAM.
        for pname in ("run_program", "stop_program"):
            need(b"\xff\x46" in read(folder / (pname + ".bin")),
                 "TIME_PROGRAM_TOKEN_MISSING")
        need(not list(folder.glob("*.sna")) and
             not list(folder.glob("*.rom")),
             "SENSITIVE_IMAGE_ARCHIVED")
    need(len(set(seen_nonces)) == 2 and start_stamps[1] > start_stamps[0],
         "INDEPENDENT_PROCESSES_NOT_PROVEN")
    return {"mission": "CLK-04-A3", "status": "REPLAY_OK_PNG_MANUAL_REVIEW_PENDING",
            "head": head, "external_manifest_sha256": seal,
            "sessions": {s: m["sessions"][s]["observation"]["values"]
                         for s in SESSIONS},
            "reset_in_process": "UNSUPPORTED",
            "time_origin": "UNVERIFIED",
            "wrap": "UNSUPPORTED",
            "clock_model": "NOT_IMPLEMENTED"}


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--acquire", action="store_true")
    g.add_argument("--verify", type=Path)
    g.add_argument("--self-test", action="store_true")
    p.add_argument("--caprice", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--head")
    p.add_argument("--seal")
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    if args.self_test:
        obj = protocol()
        need(len(obj["stages"]) == 7, "SELFTEST_PROTOCOL")
        print("CLK04_A3_CORPUS_SELF_TEST_PASS (NOT CPC)")
    elif args.acquire:
        need(args.caprice is not None and args.output is not None,
             "ARGS_MISSING")
        acquire(args.caprice.resolve(), args.output.resolve(), args.head)
    else:
        result = verify(args.verify.resolve(), args.head, args.seal)
        if args.report is not None:
            args.report.write_bytes(canonical(result))
        print("CLK04_A3_REPLAY_PASS (PNG MANUAL INSPECTION NOT IMPLIED)")


if __name__ == "__main__":
    main()
