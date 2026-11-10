#!/usr/bin/env python3
"""CLK-03: ROM-backed CPC TIME acquisition and fail-closed replay; no native TIME."""
from __future__ import annotations
import argparse
import configparser
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/cpc6128/clk_03_time/corpus.json"
SOURCE_SHA = "0b35697d97e7b6c69c2645308805b65e83dfd328a590e3b6d9a8b21607482084"
CAP_SHA = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
ROM_SHA = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
IMAGE = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
         "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")
SESSIONS = ("original", "repeat")
REQUIRED_CFG = {"system": {"model": "2", "ram_size": "128", "speed": "4",
                            "limit_speed": "1", "printer": "1", "auto_pause": "0"},
                "sound": {"enabled": "0"}}
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")
NUM = re.compile(rb"[ \t]*[+-]?[0-9]+[ \t\r]*\Z")

class OracleError(ValueError):
    pass

def need(condition, code):
    if not condition:
        raise OracleError(code)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    need(path.is_file() and not path.is_symlink(), "ABSENT_OR_SYMLINK_" + str(path))
    return path.read_bytes()

def canonical(obj):
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")

def source_cases():
    data = read(SOURCE)
    need(sha(data) == SOURCE_SHA, "CORPUS_SHA_DRIFT")
    obj = json.loads(data)
    cases = obj.get("cases")
    need(obj.get("schema") == 1 and obj.get("mission") == "CLK-03" and
         isinstance(cases, list) and len(cases) == 10, "CORPUS_SHAPE")
    ids = [case["id"] for case in cases]
    need(len(set(ids)) == len(ids) and all(re.fullmatch(r"[DPN][0-9]{2}_[A-Z_]+", i)
                                           for i in ids), "CORPUS_IDS")
    for case in cases:
        kind = case["kind"]
        need(kind in ("program", "direct", "direct_diagnostic"), "CASE_KIND")
        need(isinstance(case["printer_numeric_count"], int) and
             0 <= case["printer_numeric_count"] <= 5, "CASE_OUTPUT_COUNT")
        cmds = case["lines"] if kind == "program" else case["commands"]
        need(0 < len(cmds) <= 12 and all(isinstance(c, str) and
             c.isascii() and "\n" not in c and "\r" not in c for c in cmds), "SOURCE_COMMANDS")
        if kind == "program":
            nums = [int(c.split(" ", 1)[0]) for c in cmds]
            need(nums == sorted(set(nums)) and all(1 <= n <= 65535 for n in nums)
                 and cmds[-1].endswith(" END") and any("TIME" in c for c in cmds),
                 "PROGRAM_LINES")
    return cases

def parse_numbers(data, count):
    lines = [x for x in data.split(b"\n") if x.strip()]
    need(len(lines) == count and all(NUM.fullmatch(x) for x in lines), "TIME_AMBIGUOUS_PRINTER")
    return [int(x.strip()) for x in lines]

def valid_png(data):
    return (len(data) > 1024 and data[:8] == b"\x89PNG\r\n\x1a\n" and
            int.from_bytes(data[16:20], "big") >= 320 and
            int.from_bytes(data[20:24], "big") >= 200)

def cfg_validate(path):
    cfg = configparser.ConfigParser(interpolation=None)
    need(bool(cfg.read(path)), "CFG_MISSING")
    for section, keys in REQUIRED_CFG.items():
        need(cfg.has_section(section), "CFG_SECTION_" + section)
        for key, value in keys.items():
            need(cfg.get(section, key, fallback=None) == value, "CFG_BAD_" + key)
    need(cfg.get("file", "printer_file", fallback="").endswith("/printer.dat"),
         "CFG_PRINTER")
    return cfg

def setup(cap, folder, snaps):
    cfg = configparser.ConfigParser(interpolation=None)
    need(bool(cfg.read(cap / "cap32.cfg")), "CAPRICE_CFG_NOT_FOUND")
    for section, opts in REQUIRED_CFG.items():
        need(cfg.has_section(section), "CAPRICE_CFG_SECTION_" + section)
        cfg[section].update(opts)
    cfg["system"].update(keyboard="0", boot_time="42", mf2="0",
                         resources_path=str(cap / "resources"))
    cfg["control"]["kbd_layout"] = "0"
    cfg["video"].update(scr_style="1", scr_window="1")
    cfg["file"].update(printer_file=str(folder / "printer.dat"),
                       sdump_dir=str(folder), snap_path=str(snaps))
    cfg["rom"].update(rom_path=str(cap / "rom"), slot07="amsdos.rom", rom_mf2="")
    with (folder / "cap32.cfg").open("w", encoding="ascii") as out:
        cfg.write(out, space_around_delimiters=False)
    cfg_validate(folder / "cap32.cfg")

def run(cap, folder, commands, snaps, timeout=200):
    need(not folder.exists(), "NO_OVERWRITE")
    folder.mkdir(parents=True)
    setup(cap, folder, snaps)
    argv = ["xvfb-run", "-a", str(cap / "cap32"), "-c", str(folder / "cap32.cfg")]
    for cmd in commands:
        need("\r" not in cmd and "\n" not in cmd, "NEWLINE_IN_AUTOCMD")
        # Caprice32 automation accepts F12 + Return as the snapshot hotkey,
        # not the literal word CAP32_SNAPSHOT. The original text remains
        # visible in autocmd.json; argv stores the real control sequence.
        argv.extend(("-a", cmd.replace("CAP32_SNAPSHOT", "\x0c\x0d")))
    (folder / "autocmd.json").write_bytes(canonical({"commands": commands, "argv": argv}))
    env = dict(os.environ, SDL_VIDEODRIVER="x11", SDL_AUDIODRIVER="dummy")
    start_utc = datetime.now(timezone.utc).isoformat()
    start = time.monotonic_ns()
    try:
        p = subprocess.run(argv, cwd=cap, env=env, capture_output=True,
                           timeout=timeout, check=False)
    except subprocess.TimeoutExpired as e:
        (folder / "caprice.log").write_bytes((e.stdout or b"") + b"\nTIMEOUT\n" +
                                                   (e.stderr or b""))
        raise OracleError("CAPRICE_TIMEOUT") from e
    elapsed = (time.monotonic_ns() - start) / 1e9
    end_utc = datetime.now(timezone.utc).isoformat()
    (folder / "caprice.log").write_bytes((f"returncode={p.returncode}\n"
       f"start_utc={start_utc}\nend_utc={end_utc}\n"
       f"wall_seconds={elapsed:.9f}\n[stdout]\n").encode() +
       p.stdout + b"\n[stderr]\n" + p.stderr)
    need(p.returncode == 0, "CAPRICE_NONZERO")
    shots = sorted(folder.glob("screenshot_*.png"))
    need(len(shots) == 1 and valid_png(read(shots[0])), "CPC_SCREEN_MISSING")
    shots[0].rename(folder / "screen.png")
    return {"started_utc": start_utc, "ended_utc": end_utc,
            "wall_seconds": elapsed, "returncode": p.returncode}

def speed_gate(cap, out, session, snaps):
    # Two independent fresh processes per session; differential wall-clock estimates
    # remove nominal boot overhead, but do NOT prove absolute timing accuracy.
    measurements = {}
    for label, repetitions in (("short", 2), ("long", 18)):
        folder = out / session / ("gate_" + label)
        commands = ["PRINT #8,TIME", " ".join(["CAP32_DELAY"] * repetitions),
                    "PRINT #8,TIME", "CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"]
        meta = run(cap, folder, commands, snaps)
        ticks = parse_numbers(read(folder / "printer.dat"), 2)
        need(ticks[1] > ticks[0], "GATE_TICKS_NONPOSITIVE")
        measurements[label] = {"ticks": ticks, "delta_ticks": ticks[1] - ticks[0],
                               **meta}
    dw = measurements["long"]["wall_seconds"] - measurements["short"]["wall_seconds"]
    dt = measurements["long"]["delta_ticks"] - measurements["short"]["delta_ticks"]
    need(dw > 0.5 and dt > 100, "SPEED_GATE_TOO_SHORT")
    rate = dt / dw
    need(255 <= rate <= 345, "EMULATOR_SPEED_UNVERIFIED")
    return {"short": measurements["short"], "long": measurements["long"],
            "delta_wall_seconds": dw, "delta_ticks": dt, "ticks_per_wall_second": rate}

def ram_parser():
    sys.path.insert(0, str(ROOT / "tests/oracles"))
    import token_ram_oracle as oracle
    return oracle

def capture_case(cap, out, session, case, snaps, oracle):
    ident = case["id"]
    folder = out / session / ident
    kind = case["kind"]
    if kind == "program":
        lines = case["lines"]
        list_cmds = ["MODE 1", "NEW", *lines, "LIST",
                     "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT",
                     "LIST #8", "CAP32_DELAY CAP32_EXIT"]
        # Snapshot never goes into committed output; only extracted program bytes.
        before = set(snaps.glob("*.sna"))
        listing = run(cap, folder / "list", list_cmds, snaps)
        created = set(snaps.glob("*.sna")) - before
        need(len(created) == 1, "SNA_MISSING")
        numbers = [int(s.split(" ", 1)[0]) for s in lines]
        program, region = oracle.extract_snapshot(read(next(iter(created))), numbers)
        for path in created:
            path.unlink()
        (folder / "program.bin").write_bytes(program)
        seen_nums, seen_records = oracle.records(program)
        for source, rec in zip(lines, seen_records):
            if "TIME" in source and '"' not in source:
                body = program[rec["offset"]+4:rec["offset"]+rec["length"]-1]
                need(b"\xff\x46" in body, "TIME_RAM_TOKEN_MISSING_" + ident)
        # 9000 interpreted iterations run longer than two automation delays;
        # the first genuine CPC screenshot showed RUN still in progress.
        # Only enlarge the collection window, without changing BASIC source.
        delays = 16 if ident == "P04_LONG" else 2
        run_cmds = ["MODE 1", "NEW", *lines, "RUN",
                    " ".join(["CAP32_DELAY"] * delays) + " CAP32_SCRNSHOT CAP32_EXIT"]
        execution = run(cap, folder / "run", run_cmds, snaps)
        nums = parse_numbers(read(folder / "run/printer.dat"), case["printer_numeric_count"])
        need(len(read(folder / "list/printer.dat")) > 0, "LIST_PRINTER_EMPTY")
        return {"kind": kind, "list": listing, "run": execution,
                "program_sha256": sha(program), "region": region,
                "line_numbers": seen_nums, "numbers": nums,
                "list_hex": read(folder / "list/printer.dat").hex()}
    commands = case["commands"] + ["CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"]
    execution = run(cap, folder / "direct", commands, snaps)
    printer = folder / "direct/printer.dat"
    if kind == "direct":
        nums = parse_numbers(read(printer), case["printer_numeric_count"])
    else:
        # Diagnostic screens are authoritative. Printer/ERR/ERL are deliberately
        # NOT inferred from a bare absence of #8 output.
        nums = []
    return {"kind": kind, "direct": execution, "numbers": nums,
            "diagnostic_text": "UNVERIFIED_SCREEN_INSPECTION" if kind.endswith("diagnostic") else None}

def inventory(out):
    return {p.relative_to(out).as_posix(): {"bytes": p.stat().st_size,
            "sha256": sha(read(p))} for p in sorted(out.rglob("*")) if p.is_file()}

def acquire(cap, out, head):
    cases = source_cases()
    need(SHA40.fullmatch(head or ""), "HEAD_INVALID")
    actual_head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                           text=True).strip()
    need(head == actual_head, "HEAD_NOT_CHECKED_OUT")
    need(not out.exists(), "OUTPUT_EXISTS")
    need(subprocess.check_output(["git", "-C", str(cap), "rev-parse", "HEAD"],
                                 text=True).strip() == CAP_SHA, "CAPRICE_GIT_MISMATCH")
    need(sha(read(cap / "rom/cpc6128.rom")) == ROM_SHA, "ROM_SHA_MISMATCH")
    need((cap / "cap32").is_file(), "CAPRICE_BINARY_MISSING")
    need((cap / "rom/amsdos.rom").is_file(), "AMSDOS_MISSING")
    version = subprocess.check_output([str(cap / "cap32"), "--version"], text=True).strip()
    oracle = ram_parser()
    out.mkdir(parents=True)
    m = {"schema": 1, "mission": "CLK-03", "status": "ACQUISITION_PARTIAL",
         "head": head, "corpus_sha256": SOURCE_SHA, "caprice_commit": CAP_SHA,
         "rom_sha256": ROM_SHA, "image": IMAGE, "caprice_version": version,
         "run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"), "sessions": {},
         "rom_archived": False, "snapshot_archived": False,
         "observation_class": "CPC6128_CAPRICE32_ROM_BACKED", "files": {}}
    try:
        with tempfile.TemporaryDirectory(prefix="clk03-sna-") as tmp:
            snap = Path(tmp)
            for session in SESSIONS:
                folder = out / session
                boot = run(cap, folder / "boot", ["CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"], snap)
                gate = speed_gate(cap, out, session, snap)
                rows = {}
                for case in cases:
                    rows[case["id"]] = capture_case(cap, out, session, case, snap, oracle)
                m["sessions"][session] = {"boot": boot, "gate": gate, "cases": rows}
        m["status"] = "ACQUIRED_PENDING_SCREEN_REVIEW"
    finally:
        # Do not discard raw evidence on failure. A partial capture is NOT qualified.
        m["files"] = inventory(out)
        (out / "manifest.json").write_bytes(canonical(m))
    need(m["status"] == "ACQUIRED_PENDING_SCREEN_REVIEW", "CPC_ORACLE_UNVERIFIED")
    print("CLK-03 ACQUIRED (not screen-qualified); manifest SHA256", sha(read(out / "manifest.json")))

def check_capture(out, manifest, expected_head, seal):
    cases = source_cases()
    need(SHA64.fullmatch(seal or "") and sha(read(out / "manifest.json")) == seal,
         "EXTERNAL_SEAL_REQUIRED")
    need(SHA40.fullmatch(expected_head or "") and manifest.get("head") == expected_head,
         "HEAD_SEAL_MISMATCH")
    need(manifest.get("schema") == 1 and manifest.get("mission") == "CLK-03" and
         manifest.get("status") == "ACQUIRED_PENDING_SCREEN_REVIEW" and
         manifest.get("corpus_sha256") == SOURCE_SHA and
         manifest.get("caprice_commit") == CAP_SHA and
         manifest.get("rom_sha256") == ROM_SHA and manifest.get("image") == IMAGE and
         manifest.get("rom_archived") is False and
         manifest.get("snapshot_archived") is False and
         manifest.get("observation_class") == "CPC6128_CAPRICE32_ROM_BACKED",
         "PROVENANCE_UNVERIFIED")
    need(set(manifest.get("sessions", {})) == set(SESSIONS), "SESSIONS_MISSING")
    hashes = manifest.get("files", {})
    need(hashes and all(re.fullmatch(r"(original|repeat)/[a-zA-Z0-9_]+/.*", p)
                            for p in hashes), "INVENTORY_BAD_PATH")
    actual = inventory(out)
    actual.pop("manifest.json", None)
    need(actual == hashes, "FILE_MISSING_OR_MODIFIED")
    timestamps = set()
    for session in SESSIONS:
        info = manifest["sessions"][session]
        gate = info["gate"]
        need(255 <= gate["ticks_per_wall_second"] <= 345 and
             gate["delta_wall_seconds"] > 0.5 and gate["delta_ticks"] > 100,
             "EMULATOR_SPEED_UNVERIFIED")
        need(set(info["cases"]) == {c["id"] for c in cases}, "CASES_MISSING")
        for task, meta in [("boot", info["boot"]),
                           ("gate_short", gate["short"]), ("gate_long", gate["long"])]:
            folder = out / session / task
            if task.startswith("gate"):
                need(len(parse_numbers(read(folder / "printer.dat"), 2)) == 2,
                     "GATE_PRINTER")
                ticks = parse_numbers(read(folder / "printer.dat"), 2)
                need(ticks == meta["ticks"] and ticks[1] - ticks[0] == meta["delta_ticks"],
                     "GATE_DATA_MISMATCH")
            need(valid_png(read(folder / "screen.png")) and
                 meta["returncode"] == 0 and meta["wall_seconds"] > 0,
                 "PROCESS_BAD_" + task)
            need(meta["started_utc"] not in timestamps, "FAKE_SESSION_SAME_START")
            timestamps.add(meta["started_utc"])
            need(b"returncode=0\n" in read(folder / "caprice.log"), "PROCESS_LOG_MISSING")
            cfg_validate(folder / "cap32.cfg")
        for case in cases:
            name = case["id"]
            entry = info["cases"][name]
            need(entry["kind"] == case["kind"], "CASE_KIND_MISMATCH")
            kinds = ["list", "run"] if case["kind"] == "program" else ["direct"]
            for part in kinds:
                folder = out / session / name / part
                meta = entry[part]
                need(meta["returncode"] == 0 and meta["wall_seconds"] > 0,
                     "CAPTURE_FAILED")
                need(meta["started_utc"] not in timestamps, "FAKE_SESSION_SAME_START")
                timestamps.add(meta["started_utc"])
                need(valid_png(read(folder / "screen.png")), "SCREEN_UNVERIFIED")
                need(b"returncode=0\n" in read(folder / "caprice.log"), "PROCESS_LOG_MISSING")
                cfg_validate(folder / "cap32.cfg")
                cmd = json.loads(read(folder / "autocmd.json"))["commands"]
                if part == "list":
                    need("LIST #8" in cmd and "CAP32_SNAPSHOT" in " ".join(cmd),
                         "LIST_OR_SNAPSHOT_NOT_CAPTURED")
                elif part == "run":
                    need("RUN" in cmd, "RUN_NOT_CAPTURED")
                elif part == "direct":
                    need(cmd[:-1] == case["commands"], "DIRECT_COMMAND_DRIFT")
            if case["kind"] == "program":
                need(entry["line_numbers"] == [int(s.split(" ", 1)[0]) for s in case["lines"]],
                     "PROGRAM_LINE_MISMATCH")
                need(sha(read(out / session / name / "program.bin")) == entry["program_sha256"],
                     "RAM_SHA_MISMATCH")
                ram = ram_parser()
                _, records = ram.records(read(out / session / name / "program.bin"))
                for line, rec in zip(case["lines"], records):
                    if "TIME" in line and '"' not in line:
                        raw = read(out / session / name / "program.bin")
                        need(b"\xff\x46" in raw[rec["offset"]+4:rec["offset"]+rec["length"]-1],
                             "TIME_TOKEN_UNVERIFIED")
                need(read(out / session / name / "list/printer.dat").hex() == entry["list_hex"],
                     "LIST_PRINTER_DRIFT")
                printer = read(out / session / name / "run/printer.dat")
            else:
                printer = read(out / session / name / "direct/printer.dat") if (
                    out / session / name / "direct/printer.dat").exists() else b""
            if case["kind"] != "direct_diagnostic":
                need(parse_numbers(printer, case["printer_numeric_count"]) == entry["numbers"],
                     "TIME_AMBIGUOUS")
            else:
                need(entry["diagnostic_text"] == "UNVERIFIED_SCREEN_INSPECTION",
                     "DIAGNOSTIC_WAS_INFERRED")
    return True

def self_test():
    source_cases()
    need(parse_numbers(b" 1\r\n 2\r\n", 2) == [1, 2], "PARSE_TEST")
    for raw, count in [(b"1\n2\n", 1), (b"1 2\n", 1), (b"+X\n", 1)]:
        try:
            parse_numbers(raw, count)
        except OracleError:
            continue
        raise OracleError("PARSER_FALSE_ACCEPT")
    print("CLK-03 SOURCE_SELF_TEST PASS; NO EMULATOR EXECUTED")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--caprice", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--head")
    parser.add_argument("--seal")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.acquire:
        need(args.caprice is not None and args.output is not None and args.head,
             "ACQUIRE_ARGS_REQUIRED")
        acquire(args.caprice.resolve(), args.output.resolve(), args.head)
    elif args.verify:
        check_capture(args.verify.resolve(),
                      json.loads(read(args.verify / "manifest.json")), args.head, args.seal)
        print("CLK-03 RAW_REPLAY_PASS; SCREEN_DIAGNOSTICS_UNVERIFIED UNTIL HUMAN INSPECTION")
    else:
        parser.error("select --self-test, --acquire or --verify")

if __name__ == "__main__":
    try:
        main()
    except (OracleError, OSError, ValueError, subprocess.SubprocessError,
            configparser.Error) as exc:
        print("CLK-03 CPC_ORACLE_UNVERIFIED:", exc, file=sys.stderr)
        sys.exit(2)
