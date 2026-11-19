#!/usr/bin/env python3
"""CLK-04-A5: independent ROM CPC REAL5 product RAM, not native TIME.

Acquisition never imports or executes the C99 candidate. It copies only the
real transient CPC STOP scalar bytes; SNA and ROM never enter the archive.
Only a separate sealed replay may execute the unchanged A4 C99 proposal.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clk_04_a4_oracle as a4

prior, a1 = a4.prior, a4.a1
need, sha, read, canonical = prior.need, prior.sha, prior.read, prior.canonical
ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/cpc6128/clk_04_a4_numeric/a5_product_ram/corpus.json"
CORPUS_SHA = "09a132467b71aed8c55e9c8691948c350b921dce5b1195f3af26ace0adfd600c"
VALUES = (0, 1, 32767, 32768, 65536, 8388608, 2147483648, 4294967295)
PINS = a4.PINS
SESSIONS = a4.SESSIONS
RAW_STATUS = "ACQUIRED_PENDING_PNG_REVIEW"


def source_lines(value, alternative):
    lines = ["10 T!=" + str(value), "20 U!=T!*2"]
    if alternative is not None:
        lines.append("30 R!=" + alternative)
    lines += ["90 STOP", "100 PRINT #8,@T!", "110 PRINT #8,@U!",
              "120 PRINT #8,T!", "130 PRINT #8,U!", "140 PRINT #8,T!*2"]
    if alternative is not None:
        lines += ["150 PRINT #8,@R!", "160 PRINT #8,R!",
                  "170 PRINT #8,T!=R!", "180 PRINT #8,(R!+1)-R!",
                  "190 PRINT #8,R!-(R!-1)"]
    lines.append("200 END" if alternative is not None else "150 END")
    return lines


def source_cases():
    data = read(CORPUS)
    need(sha(data) == CORPUS_SHA, "A5_CORPUS_SHA_DRIFT")
    obj = json.loads(data)
    cases = obj.get("cases")
    need(obj.get("schema") == 1 and obj.get("mission") == "CLK-04-A5"
         and obj.get("status") == "SEALED_INPUTS_NOT_OBSERVATIONS"
         and obj.get("scope") == "REAL5_PRODUCT_TWO_ROM_BACKED_SESSIONS_ONLY"
         and isinstance(cases, list) and len(cases) == len(VALUES),
         "A5_CORPUS_SHAPE_DRIFT")
    for idx, (case, n) in enumerate(zip(cases, VALUES), start=1):
        alternative = a4.alternative(n)
        need(case.get("id") == "P%02d" % idx and case.get("value") == str(n)
             and case.get("arithmetic") == alternative
             and case.get("lines") == source_lines(n, alternative)
             and case.get("printer_numeric_count") == (10 if alternative else 5),
             "A5_SOURCE_CONSTRUCTION_OR_PRINT_DRIFT")
        # A4/A2 already observed these independent CPC constructions.
        need(alternative is None or alternative in
             ("2^15", "2^16", "2^23", "2^31", "(2^32)-1"),
             "A5_UNREVIEWED_ARITHMETIC_CONSTRUCTION")
    return cases


def requested_names(case):
    return [ord("T"), ord("U")] + ([ord("R")] if case["arithmetic"] else [])


def snapshot_window(snapshot, case):
    items = [{"variable": chr(n) + "!", "arithmetic": None}
             for n in requested_names(case)]
    return a4.snapshot_window(snapshot, case["lines"], items)


def read_values(case, stop, printer):
    entries = {int(k): v for k, v in stop["entries"].items()}
    need(set(entries) == set(requested_names(case)), "A5_SCALAR_NAMES_MISMATCH")
    lines = a4.raw_number_lines(read(printer), case["printer_numeric_count"])
    t, u = entries[ord("T")], entries[ord("U")]
    need(t["type_byte"] == u["type_byte"] == 4 and
         t["address"] != u["address"] and
         lines[0]["number"] == t["address"] and
         lines[1]["number"] == u["address"],
         "A5_AT_ADDRESS_OR_TYPE_MISMATCH")
    # Only numeric PRINT is compared here: the authoritative bytes above
    # come exclusively from the STOP scalar window, never from PRINT.
    n = int(case["value"])
    if n <= 65536:
        need(lines[2]["number"] == Decimal(n) and
             lines[3]["number"] == Decimal(n * 2) and
             lines[4]["number"] == Decimal(n * 2),
             "A5_EXACT_PRINT_OR_PRODUCT_MISMATCH")
    else:
        need(lines[3]["number"] == lines[4]["number"],
             "A5_PRODUCT_PRINT_VS_EXPRESSION_MISMATCH")
    alternative = None
    if case["arithmetic"] is not None:
        r = entries[ord("R")]
        alt = lines[5:]
        need(r["type_byte"] == 4 and alt[0]["number"] == r["address"]
             and r["value_hex"] == t["value_hex"]
             and alt[2]["number"] == -1,
             "A5_INDEPENDENT_CONSTRUCTION_MISMATCH")
        alternative = {"expression": case["arithmetic"],
                       "address": r["address"], "real5_hex": r["value_hex"],
                       "cpc_print": str(alt[1]["number"]),
                       "equal": str(alt[2]["number"]),
                       "plus_step": str(alt[3]["number"]),
                       "minus_step": str(alt[4]["number"])}
    return {"value_requested": case["value"],
            "RAW_INPUT_REAL5_CPC": {"name": "T!", "type": 4,
                "address": t["address"], "hex": t["value_hex"]},
            "RAW_PRODUCT_REAL5_CPC": {"name": "U!", "type": 4,
                "address": u["address"], "hex": u["value_hex"]},
            "RAW_PRINT_CPC": {
                "address_t": str(lines[0]["number"]),
                "address_u": str(lines[1]["number"]),
                "t": str(lines[2]["number"]),
                "u": str(lines[3]["number"]),
                "expression_twice": str(lines[4]["number"]),
                "full_printer_lines_hex": [x["raw_hex"] for x in lines]},
            "alternative_CPC": alternative}


def capture_case(cap, out, session, case, snap_root):
    folder = out / session / case["id"]
    lines = case["lines"]
    nums = [int(x.split(" ", 1)[0]) for x in lines]
    snaps = snap_root / (session + "-" + case["id"] + "-list")
    snaps.mkdir()
    listing = prior.run(cap, folder / "list", a4.list_commands(lines), snaps)
    files = list(snaps.glob("*.sna"))
    need(len(files) == 1, "A5_LIST_SNA_MISSING")
    program, region = prior.ram_parser().extract_snapshot(read(files[0]), nums)
    files[0].unlink()
    need(read(folder / "list/printer.dat").strip(), "A5_LIST_PRINTER_MISSING")
    (folder / "program.bin").write_bytes(program)

    snaps = snap_root / (session + "-" + case["id"] + "-stop")
    snaps.mkdir()
    execution = a4.run_double_screen(cap, folder / "run",
                                     a4.run_commands(lines), snaps)
    files = list(snaps.glob("*.sna"))
    need(len(files) == 1, "A5_STOP_SNA_MISSING")
    stop_program, window, stop = snapshot_window(read(files[0]), case)
    files[0].unlink()
    (folder / "window.bin").write_bytes(window)
    (folder / "stop_program.bin").write_bytes(stop_program)
    (folder / "stop.json").write_bytes(canonical(stop))
    row = read_values(case, stop, folder / "run/printer.dat")
    return {"list": listing, "run": execution, "list_region": region,
            "program_sha256": sha(program),
            "stop_program_sha256": sha(stop_program),
            "window_sha256": sha(window),
            "stop_sha256": sha(read(folder / "stop.json")),
            "list_printer_sha256": sha(read(folder / "list/printer.dat")),
            "reading": row}


def acquire(cap, out, head):
    cases = source_cases()
    need(prior.SHA40.fullmatch(head or ""), "A5_HEAD_INVALID")
    actual = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                     text=True).strip()
    need(actual == head, "A5_CHECKOUT_HEAD_MISMATCH")
    need(not out.exists(), "A5_NO_OVERWRITE")
    need(subprocess.check_output(["git", "-C", str(cap), "rev-parse", "HEAD"],
                                 text=True).strip() == prior.CAP_SHA,
         "A5_CAPRICE_PIN_MISMATCH")
    need(sha(read(cap / "rom/cpc6128.rom")) == prior.ROM_SHA,
         "A5_ROM_PIN_MISMATCH")
    need((cap / "cap32").is_file() and (cap / "rom/amsdos.rom").is_file(),
         "A5_CAPRICE_EXEC_OR_AMSDOS_MISSING")
    version = subprocess.check_output([str(cap / "cap32"), "--version"],
                                      text=True).strip()
    manifest = {"schema": 1, "mission": "CLK-04-A5", "status": "ACQUISITION_PARTIAL",
                "head": head, "corpus_sha256": CORPUS_SHA, **PINS,
                "caprice_version": version,
                "run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"),
                "observation_class": "CPC6128_CAPRICE32_ROM_BACKED",
                "rom_archived": False, "snapshot_archived": False,
                "sessions": {}, "files": {}}
    out.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix="clk04-a5-sna-") as temp:
            snaps = Path(temp)
            for session in SESSIONS:
                boot = prior.run(cap, out / session / "boot",
                                 ["CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"],
                                 snaps)
                gate = prior.speed_gate(cap, out, session, snaps)
                observed = {}
                for case in cases:
                    observed[case["id"]] = capture_case(cap, out, session,
                                                        case, snaps)
                manifest["sessions"][session] = {
                    "boot": boot, "gate": gate, "cases": observed}
        manifest["status"] = RAW_STATUS
    finally:
        manifest["files"] = prior.inventory(out)
        (out / "manifest.json").write_bytes(canonical(manifest))
    need(manifest["status"] == RAW_STATUS, "A5_ACQUISITION_INCOMPLETE")
    print("CLK-04-A5 CPC_RAW_ACQUIRED_PENDING_PNG_REVIEW",
          sha(read(out / "manifest.json")))


def authenticated_manifest(out, head, seal):
    source_cases()
    need(prior.SHA64.fullmatch(seal or "") and
         sha(read(out / "manifest.json")) == seal,
         "A5_EXTERNAL_MANIFEST_SEAL_MISMATCH")
    m = json.loads(read(out / "manifest.json"))
    need(prior.SHA40.fullmatch(head or "") and m.get("head") == head,
         "A5_HEAD_MISMATCH")
    need(m.get("schema") == 1 and m.get("mission") == "CLK-04-A5"
         and m.get("status") == RAW_STATUS
         and m.get("corpus_sha256") == CORPUS_SHA
         and all(m.get(k) == v for k, v in PINS.items())
         and m.get("observation_class") == "CPC6128_CAPRICE32_ROM_BACKED"
         and m.get("rom_archived") is False
         and m.get("snapshot_archived") is False,
         "A5_ROM_IMAGE_OR_SOURCE_PROVENANCE")
    need(set(m.get("sessions", {})) == set(SESSIONS),
         "A5_INDEPENDENT_SESSIONS_MISSING")
    actual = prior.inventory(out)
    actual.pop("manifest.json", None)
    need(bool(actual) and actual == m.get("files") and
         not any(x.endswith((".sna", ".rom")) for x in actual),
         "A5_RAW_INVENTORY_SIZE_OR_SHA_MISMATCH")
    allowed = {c["id"] for c in source_cases()} | {
        "boot", "gate_short", "gate_long"}
    need(all(p.split("/")[0] in SESSIONS and
             p.split("/")[1] in allowed for p in actual),
         "A5_UNEXPECTED_RAW_MEMBER")
    return m


def replay_raw(out, head, seal):
    m = authenticated_manifest(out, head, seal)
    cases = source_cases()
    starts = set()
    report = []
    for session in SESSIONS:
        group = m["sessions"][session]
        gate = group["gate"]
        need(set(group["cases"]) == {c["id"] for c in cases},
             "A5_8_CASES_PER_SESSION_REQUIRED")
        for part, meta in (("boot", group["boot"]), ("gate_short", gate["short"]),
                           ("gate_long", gate["long"])):
            a4.cfg_process(out / session / part, meta)
            need(meta["started_utc"] not in starts,
                 "A5_SESSION_OR_PROCESS_REUSED")
            starts.add(meta["started_utc"])
            if part.startswith("gate"):
                observed = prior.parse_numbers(
                    read(out / session / part / "printer.dat"), 2)
                need(observed == meta["ticks"] and
                     observed[1] - observed[0] == meta["delta_ticks"],
                     "A5_SPEED_GATE_RAW_DRIFT")
        delta_wall = gate["long"]["wall_seconds"] - gate["short"]["wall_seconds"]
        delta_ticks = gate["long"]["delta_ticks"] - gate["short"]["delta_ticks"]
        need(delta_wall > .5 and delta_ticks > 100 and
             abs(gate["delta_wall_seconds"] - delta_wall) < 1e-6 and
             delta_ticks == gate["delta_ticks"] and
             abs(gate["ticks_per_wall_second"] - delta_ticks / delta_wall) < 1e-5
             and 255 <= delta_ticks / delta_wall <= 345,
             "A5_SPEED_GATE_FAILED")
        for case in cases:
            data = group["cases"][case["id"]]
            folder = out / session / case["id"]
            listing = a4.cfg_process(folder / "list", data["list"])
            running = a4.cfg_process(folder / "run", data["run"], double=True)
            need(listing == a4.list_commands(case["lines"]) and
                 running == a4.run_commands(case["lines"]),
                 "A5_COMMANDS_DRIFT")
            for meta in (data["list"], data["run"]):
                need(meta["started_utc"] not in starts,
                     "A5_SESSION_PROCESS_TIMESTAMP_REUSE")
                starts.add(meta["started_utc"])
            program = read(folder / "program.bin")
            line_nums, _ = prior.ram_parser().records(program)
            need(line_nums == [int(x.split(" ", 1)[0]) for x in case["lines"]]
                 and b"\xff\x46" not in program
                 and sha(program) == data["program_sha256"]
                 and sha(read(folder / "stop_program.bin")) ==
                     data["stop_program_sha256"]
                 and sha(read(folder / "list/printer.dat")) ==
                     data["list_printer_sha256"]
                 and read(folder / "list/printer.dat").strip(),
                 "A5_LIST_OR_STOP_PROGRAM_DRIFT")
            stop = json.loads(read(folder / "stop.json"))
            window = read(folder / "window.bin")
            ptr = stop["pointers"]
            need(stop["ram_window_sha256"] == sha(window) ==
                     data["window_sha256"]
                 and stop["ram_window_start"] == ptr["scalar_start"]
                 and stop["ram_window_end"] == ptr["array_start"]
                 and ptr["array_start"] - ptr["scalar_start"] == len(window)
                 and 0x016f < ptr["program_end"] <= ptr["scalar_start"] <
                     ptr["array_start"] <= ptr["array_end"] < 0xac00,
                 "A5_RAM_POINTER_SHA_OR_BOUNDS_MISMATCH")
            entries = a1.check_window(window, ptr["scalar_start"],
                                      requested_names(case))
            need({str(k): v for k, v in entries.items()} == stop["entries"] and
                 sha(read(folder / "stop.json")) == data["stop_sha256"],
                 "A5_RAM_T_U_RAW_BYTES_OR_TYPE_MISMATCH")
            row = read_values(case, stop, folder / "run/printer.dat")
            need(row == data["reading"], "A5_PRINTER_OR_READING_DRIFT")
            row["session"] = session
            row["case"] = case["id"]
            report.append(row)
    need(len(report) == 16 and
         {r["value_requested"] for r in report} == {str(v) for v in VALUES},
         "A5_PRODUCT_CARDINALITY")
    return report


def compare_candidate(rows, candidate):
    """Only called AFTER the entire independent archive has passed replay."""
    need(candidate is not None and Path(candidate).is_file(),
         "A5_C99_CANDIDATE_MISSING")
    args = [str(Path(candidate).resolve())] + [x["value_requested"] for x in rows]
    proc = subprocess.run(args, capture_output=True, timeout=20, check=False)
    need(proc.returncode == 0 and not proc.stderr,
         "A5_C99_CANDIDATE_FAILED")
    lines = proc.stdout.decode("ascii").splitlines()
    need(len(lines) == len(rows) == 16, "A5_CANDIDATE_COUNT")
    totals = {"CANDIDATE_MATCH": 0, "CANDIDATE_MISMATCH": 0,
              "CANDIDATE_PRINT_UNSUPPORTED": 0}
    for row, line in zip(rows, lines):
        fields = line.split("\t")
        need(len(fields) == 10 and fields[0] == row["value_requested"] and
             all(re.fullmatch(r"[0-9A-F]{10}", fields[k]) for k in (1, 3)),
             "A5_CANDIDATE_ID_OR_HEX")
        input_hex = bytes.fromhex(fields[1]).hex(" ").upper()
        product_hex = bytes.fromhex(fields[3]).hex(" ").upper()
        real_input = row["RAW_INPUT_REAL5_CPC"]["hex"]
        real_product = row["RAW_PRODUCT_REAL5_CPC"]["hex"]
        match_input = input_hex == real_input
        match_product = product_hex == real_product
        observations = row["RAW_PRINT_CPC"]["full_printer_lines_hex"]
        print_t = ("UNSUPPORTED" if fields[6] == "UNSUPPORTED" else
                   "CANDIDATE_MATCH" if fields[6] == observations[2]
                   else "CANDIDATE_MISMATCH")
        print_product = ("UNSUPPORTED" if fields[7] == "UNSUPPORTED" else
                         "CANDIDATE_MATCH" if fields[7] == observations[3]
                         else "CANDIDATE_MISMATCH")
        row["C99_CANDIDATE"] = {
            "raw_input_hex": input_hex, "raw_product_hex": product_hex,
            "twice_integer": fields[2],
            "input_status": "CANDIDATE_MATCH" if match_input else "CANDIDATE_MISMATCH",
            "product_status": "CANDIDATE_MATCH" if match_product else "CANDIDATE_MISMATCH",
            "print_t": print_t, "print_u": print_product}
        row["status"] = ("CANDIDATE_MATCH" if match_input and match_product
                         else "CANDIDATE_MISMATCH")
        totals[row["status"]] += 1
        if print_t == "UNSUPPORTED" or print_product == "UNSUPPORTED":
            totals["CANDIDATE_PRINT_UNSUPPORTED"] += 1
    return totals


def verify(out, head, seal, candidate):
    rows = replay_raw(out, head, seal)
    totals = compare_candidate(rows, candidate)
    return {"mission": "CLK-04-A5", "head": head, "external_seal": seal,
            "status": "VERIFIED_CPC_SAMPLES_ONLY",
            "scope": "8_DISTINCT_X_2_INDEPENDENT_SESSIONS_PRODUCT_REAL5_ONLY",
            "RAW_INPUT_REAL5_CPC": "AUTHENTICATED",
            "RAW_PRODUCT_REAL5_CPC": "AUTHENTICATED",
            "RAW_PRINT_CPC": "AUTHENTICATED",
            "C99_CANDIDATE": "POST_AUTHENTICATION_COMPARISON_ONLY",
            "totals": totals, "samples": rows,
            "human_png_review": "REQUIRED_NOT_AUTOMATED",
            "time_origin": "UNVERIFIED", "time_wrap": "UNVERIFIED",
            "time_native": "NOT_AUTHORIZED",
            "uint32_global_range": "UNVERIFIED"}


def self_test():
    cases = source_cases()
    need(len(cases) == 8 and sum(c["printer_numeric_count"] for c in cases) == 65,
         "A5_SELF_CORPUS_COUNT")
    need(all(any(x == "20 U!=T!*2" for x in c["lines"]) and
             c["lines"].index("90 STOP") < c["lines"].index("100 PRINT #8,@T!")
             for c in cases), "A5_SELF_STOP_BEFORE_PRINT")
    print("CLK-04-A5 SELF_TEST_PASS SYNTHETIC_ONLY")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--acquire", action="store_true")
    p.add_argument("--verify", type=Path)
    p.add_argument("--caprice", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--head")
    p.add_argument("--seal")
    p.add_argument("--candidate", type=Path)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    if args.self_test:
        self_test()
    elif args.acquire:
        need(args.caprice is not None and args.output is not None and args.head,
             "A5_ACQUISITION_ARGS_MISSING")
        acquire(args.caprice.resolve(), args.output.resolve(), args.head)
    elif args.verify:
        need(args.head and args.seal, "A5_REPLAY_SEAL_OR_HEAD_MISSING")
        report = verify(args.verify.resolve(), args.head, args.seal, args.candidate)
        if args.report:
            need(not args.report.exists(), "A5_REPORT_NO_OVERWRITE")
            args.report.write_bytes(canonical(report))
        print("CLK-04-A5 SEALED_REPLAY_PASS",
              json.dumps(report["totals"], sort_keys=True))
    else:
        p.error("choose --self-test, --acquire or --verify")


if __name__ == "__main__":
    try:
        main()
    except (prior.OracleError, ValueError, TypeError, KeyError, IndexError,
            subprocess.CalledProcessError, OSError) as exc:
        print("CLK-04-A5 REJECT", str(exc), file=sys.stderr)
        raise SystemExit(2)
