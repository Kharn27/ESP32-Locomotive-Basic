#!/usr/bin/env python3
"""CLK-04-A1: genuine CPC6128 REAL5 TIME acquisition. No native BASIC code.

ROM/Caprice32 provenance and speed gates reuse the immutable CLK-03 helper.
SNAs are ephemeral; RAM windows and printer bytes originate only from Caprice32.
A structural self-test or synthetic archive is NOT a CPC oracle.
"""
import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clk_03_cpc_time as prior

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/cpc6128/clk_04_real5/corpus.json"
SOURCE_SHA = "3ba8d1ce7f1d1996dd1593cc5b4ae15a84be9fefd9bd637b4c44b2a02e39f423"
SESSIONS = prior.SESSIONS
SHA40 = prior.SHA40
SHA64 = prior.SHA64
PINS = {"caprice_commit":prior.CAP_SHA,"rom_sha256":prior.ROM_SHA,
        "image":prior.IMAGE}
PRINT_NUMBER = re.compile(rb"[ \t]*([+-]?[0-9]+(?:\.[0-9]+)?)[ \t\r]*\Z")
KNOWN = {"F_ZERO":(b"\0\0\0\0\0","0"),
         "F_ONE":(bytes.fromhex("00 00 00 00 81"),"1"),
         "F_NEG_ONE":(bytes.fromhex("00 00 00 80 81"),"-1"),
         "F_HALF":(bytes.fromhex("00 00 00 00 80"),"0.5"),
         "F_QUARTER":(bytes.fromhex("00 00 00 20 81"),"1.25")}
need, sha, read, canonical = prior.need, prior.sha, prior.read, prior.canonical

def source_cases():
    data = read(SOURCE)
    need(sha(data) == SOURCE_SHA, "CORPUS_SHA_DRIFT")
    obj = json.loads(data)
    cases = obj.get("cases", [])
    ids = [c.get("id") for c in cases]
    need(obj.get("schema") == 1 and obj.get("mission") == "CLK-04-A1"
         and obj.get("status") == "SEALED_INPUTS_NOT_OBSERVATIONS"
         and ids == list(KNOWN) + ["T_DYNAMIC_PAIR", "T_LATE_BOUNDED"],
         "CORPUS_SHAPE_OR_ORDER")
    for c in cases:
        lines = c.get("lines")
        need(c.get("kind") == ("known" if c["id"] in KNOWN else "time")
             and isinstance(lines,list) and 7 <= len(lines) <= 14
             and all(isinstance(x,str) and x.isascii() and "\r" not in x
                     and "\n" not in x for x in lines)
             and lines[-1].endswith(" END")
             and c.get("printer_numeric_count") ==
                 (5 if c["kind"] == "known" else 9)
             and c.get("pre_run_delays",0) ==
                 (160 if c["id"] == "T_LATE_BOUNDED" else 0)
             and sum(" STOP" in x for x in lines) == 1,
             "SOURCE_CASE_CONTRACT")
        nums = [int(s.split(" ",1)[0]) for s in lines]
        need(nums == sorted(set(nums)), "SOURCE_LINE_ORDER")
        if c["kind"] == "time":
            need(lines[0] == "10 T!=TIME" and lines[1] == "20 U!=TIME",
                 "DYNAMIC_ASSIGNMENT_DRIFT")
        else:
            need(lines[0] == "10 T!=" + KNOWN[c["id"]][1],
                 "FIXED_ASSIGNMENT_DRIFT")
    return cases

def numbers(raw, expected):
    lines = [line for line in raw.split(b"\n") if line.strip()]
    need(len(lines) == expected, "PRINTER_CARDINALITY")
    need(all(PRINT_NUMBER.fullmatch(x) for x in lines), "PRINTER_AMBIGUOUS")
    try:
        return [Decimal(PRINT_NUMBER.fullmatch(line).group(1).decode("ascii"))
                for line in lines]
    except InvalidOperation as exc:
        raise prior.OracleError("PRINTER_INVALID_DECIMAL") from exc

def check_window(window, starts, ids):
    need(len(window) == 9 * len(ids) and len(window) <= 72,
         "RAM_WINDOW_INVALID_LENGTH")
    found = {}
    for offset in range(0,len(window),9):
        item = window[offset:offset+9]
        # Scalar layout observed in J1.16-E-A: 2 opaque link bytes,
        # ASCII name with high bit, CPC type code 04, 5 raw REAL5 bytes.
        name = item[2] & 0x7f
        need(item[2] & 0x80 and item[3] == 4 and name in ids and
             name not in found, "RAM_SCALAR_IDENTITY_OR_TYPE")
        found[name] = {"address":starts+offset+4,
                       "value_hex":item[4:9].hex(" ").upper(),
                       "entry_offset":offset,
                       "link_hex":item[:2].hex(" ").upper(),
                       "name_byte":item[2],"type_byte":item[3]}
    need(set(found) == set(ids), "RAM_SCALAR_MISSING")
    return found

def snapshot_window(snapshot, lines, kind):
    parser = prior.ram_parser()
    expected = [int(x.split(" ",1)[0]) for x in lines]
    program, region = parser.extract_snapshot(snapshot,expected)
    need(b"\xff\x46" in program if kind == "time" else
         b"\xff\x46" not in program,"TIME_TOKEN_RAM")
    ram = memoryview(snapshot)[parser.HEADER:]
    word = lambda at:int.from_bytes(ram[at:at+2],"little")
    starts = {"program_end":word(0xae66),"scalar_start":word(0xae68),
              "array_start":word(0xae6a),"array_end":word(0xae6c)}
    st, en = starts["scalar_start"],starts["array_start"]
    need(0x016f < starts["program_end"] <= st < en <= starts["array_end"] < 0xac00,
         "RAM_POINTER_ORDER")
    window = bytes(ram[st:en])
    ids = [ord("T")] if kind == "known" else [ord("T"),ord("U")]
    found = check_window(window,st,ids)
    return program,window,{"sna_sha256":sha(snapshot),
        "sna_header_first_16_hex":snapshot[:16].hex(" ").upper(),
        "pointers":starts,"ram_window_start":st,"ram_window_end":en,
        "ram_window_sha256":sha(window),"entries":found,
        "region":region}

def validate_link(case, stop, printer):
    raw = read(printer)
    nums = numbers(raw,case["printer_numeric_count"])
    entries = stop["entries"]
    t = entries[ord("T")]
    need(nums[0] == t["address"], "AT_T_ADDRESS_MISMATCH")
    if case["kind"] == "known":
        need(bytes.fromhex(t["value_hex"]) == KNOWN[case["id"]][0],
             "FIXED_REAL5_NOT_MEASURED")
        expected = Decimal(KNOWN[case["id"]][1])
        need(nums[1] == expected and nums[2] == 2*expected and
             nums[3] == (-1 if expected >= 0 else 0) and
             nums[4] == ( -1 if expected > 32767 else 0),
             "FIXED_PRINT_OR_COMPUTATION_MISMATCH")
    else:
        u = entries[ord("U")]
        need(nums[5] == u["address"], "AT_U_ADDRESS_MISMATCH")
        need(nums[1] >= 0 and nums[2] == 2*nums[1] and
             nums[3] == -1 and nums[4] == (-1 if nums[1] > 32767 else 0)
             and nums[7] == (-1 if nums[6] >= nums[1] else 0)
             and nums[8] >= nums[6],
             "TIME_PRINT_OR_COMPUTATION_MISMATCH")
        # No claim that the final TIME read equals either stored sample.
        # No numeric value is decoded from REAL5 bytes here.
    return [str(x) for x in nums]

def cfg_and_process(folder,meta):
    need(meta["returncode"] == 0 and meta["wall_seconds"] > 0 and
         prior.valid_png(read(folder/"screen.png")) and
         b"returncode=0\n" in read(folder/"caprice.log"),
         "PROCESS_PROVENANCE")
    prior.cfg_validate(folder/"cap32.cfg")
    need(datetime.fromisoformat(meta["started_utc"]).tzinfo is not None,
         "START_TIMESTAMP_INVALID")
    return json.loads(read(folder/"autocmd.json"))["commands"]

def capture_case(cap,out,session,case,snap_root):
    root = out/session/case["id"]
    lines, kind = case["lines"],case["kind"]
    # Independent cold CPC: LIST and RAM token bytes before RUN.
    list_cmds = ["MODE 1","NEW",*lines,"LIST",
        "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT",
        "LIST #8","CAP32_DELAY CAP32_EXIT"]
    snaps = snap_root/(session+"-"+case["id"]+"-list")
    snaps.mkdir()
    listed = prior.run(cap,root/"list",list_cmds,snaps)
    files = list(snaps.glob("*.sna"))
    need(len(files) == 1,"LIST_SNA_MISSING")
    parser = prior.ram_parser()
    listed_program,region = parser.extract_snapshot(read(files[0]),
                [int(x.split(" ",1)[0]) for x in lines])
    files[0].unlink()
    (root/"program.bin").write_bytes(listed_program)
    need(read(root/"list/printer.dat").strip(), "LIST_PRINTER_MISSING")
    # Same genuine CPC execution: STOP → one snapshot → CONT → PRINT values.
    # At STOP no PRINT #8 instruction has executed yet.
    snaps = snap_root/(session+"-"+case["id"]+"-stop")
    snaps.mkdir()
    controls = ["MODE 1","NEW",*lines]
    delays = case.get("pre_run_delays",0)
    if delays:
        controls.append(" ".join(["CAP32_DELAY"]*delays))
    controls += ["RUN","CAP32_DELAY CAP32_DELAY CAP32_SNAPSHOT",
                 "CONT","CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"]
    executed = prior.run(cap,root/"run",controls,snaps,
                         timeout=290 if delays else 110)
    files = list(snaps.glob("*.sna"))
    need(len(files) == 1,"STOP_SNA_MISSING")
    stop_program,window,stop = snapshot_window(read(files[0]),lines,kind)
    files[0].unlink()
    (root/"window.bin").write_bytes(window)
    (root/"stop_program.bin").write_bytes(stop_program)
    (root/"stop.json").write_bytes(canonical(stop))
    nums = validate_link(case,stop,root/"run/printer.dat")
    return {"kind":kind,"list":listed,"run":executed,
            "program_sha256":sha(listed_program),
            "stop_program_sha256":sha(stop_program),
            "window_sha256":sha(window),
            "list_printer_sha256":sha(read(root/"list/printer.dat")),
            "stop_sha256":sha(read(root/"stop.json")),
            "numbers":nums,"list_region":region,"pre_run_delays":delays}

def acquire(cap,out,head):
    cases = source_cases()
    need(SHA40.fullmatch(head or ""), "HEAD_INVALID")
    actual_head = subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],
                                          text=True).strip()
    need(head == actual_head, "HEAD_NOT_CHECKED_OUT")
    need(not out.exists(),"OUTPUT_EXISTS")
    need(subprocess.check_output(["git","-C",str(cap),"rev-parse","HEAD"],
        text=True).strip() == prior.CAP_SHA, "CAPRICE_SHA_MISMATCH")
    need(sha(read(cap/"rom/cpc6128.rom")) == prior.ROM_SHA,
         "ROM_SHA_MISMATCH")
    need((cap/"cap32").is_file() and (cap/"rom/amsdos.rom").is_file(),
         "CAPRICE_BINARY_OR_AMSDOS_MISSING")
    version = subprocess.check_output([str(cap/"cap32"),"--version"],
                                      text=True).strip()
    m = {"schema":1,"mission":"CLK-04-A1","status":"ACQUISITION_PARTIAL",
         "head":head,"corpus_sha256":SOURCE_SHA,**PINS,
         "caprice_version":version,"run_id":prior.os.getenv("GITHUB_RUN_ID","LOCAL"),
         "observation_class":"CPC6128_CAPRICE32_ROM_BACKED",
         "rom_archived":False,"snapshot_archived":False,
         "sessions":{},"files":{}}
    out.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix="clk04-a1-sna-") as temp:
            snaps = Path(temp)
            for session in SESSIONS:
                boot = prior.run(cap,out/session/"boot",
                    ["CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"],snaps)
                gate = prior.speed_gate(cap,out,session,snaps)
                records = {}
                for case in cases:
                    records[case["id"]] = capture_case(cap,out,session,case,snaps)
                m["sessions"][session] = {"boot":boot,"gate":gate,"cases":records}
        m["status"] = "ACQUIRED_PENDING_PNG_REVIEW"
    finally:
        m["files"] = prior.inventory(out)
        (out/"manifest.json").write_bytes(canonical(m))
    need(m["status"] == "ACQUIRED_PENDING_PNG_REVIEW",
         "ACQUISITION_INCOMPLETE")
    print("CLK-04-A1 ROM_ACQUIRED_PENDING_PNG_REVIEW",sha(read(out/"manifest.json")))

def verify(out,head,seal):
    cases = source_cases()
    need(SHA64.fullmatch(seal or "") and sha(read(out/"manifest.json")) == seal,
         "EXTERNAL_SEAL_REQUIRED")
    m = json.loads(read(out/"manifest.json"))
    need(SHA40.fullmatch(head or "") and m.get("head") == head,
         "HEAD_MISMATCH")
    need(m.get("schema") == 1 and m.get("mission") == "CLK-04-A1" and
         m.get("status") == "ACQUIRED_PENDING_PNG_REVIEW" and
         m.get("corpus_sha256") == SOURCE_SHA and
         all(m.get(k) == v for k,v in PINS.items()) and
         m.get("rom_archived") is False and
         m.get("snapshot_archived") is False and
         m.get("observation_class") == "CPC6128_CAPRICE32_ROM_BACKED",
         "PROVENANCE_MISMATCH")
    need(set(m.get("sessions",{})) == set(SESSIONS), "SESSIONS_MISSING")
    inv = prior.inventory(out)
    inv.pop("manifest.json",None)
    need(m.get("files") == inv and bool(inv) and
         all(re.fullmatch(r"(original|repeat)/[A-Z0-9_]+/.+",p)
             or re.fullmatch(r"(original|repeat)/(boot|gate_short|gate_long)/.+",p)
             for p in inv) and
         not any(p.endswith(".sna") or p.endswith(".rom") for p in inv),
         "FILE_INVENTORY_MISMATCH")
    timestamps = set()
    for session in SESSIONS:
        item = m["sessions"][session]
        gate = item["gate"]
        need(set(item["cases"]) == {c["id"] for c in cases},
             "CASES_MISSING")
        for part,meta in [("boot",item["boot"]),("gate_short",gate["short"]),
                          ("gate_long",gate["long"])]:
            commands = cfg_and_process(out/session/part,meta)
            if part.startswith("gate"):
                raw = read(out/session/part/"printer.dat")
                ticks = prior.parse_numbers(raw,2)
                need(ticks == meta["ticks"] and ticks[1]-ticks[0] == meta["delta_ticks"],
                     "GATE_PRINTER_DRIFT")
            need(meta["started_utc"] not in timestamps,"DUPLICATE_START_TIMESTAMP")
            timestamps.add(meta["started_utc"])
        short,long = gate["short"],gate["long"]
        delta_wall = long["wall_seconds"]-short["wall_seconds"]
        delta_ticks = long["delta_ticks"]-short["delta_ticks"]
        need(delta_wall > .5 and delta_ticks > 100 and
             abs(gate["delta_wall_seconds"]-delta_wall)<1e-6 and
             delta_ticks == gate["delta_ticks"] and
             abs(gate["ticks_per_wall_second"]-delta_ticks/delta_wall)<1e-5
             and 255 <= delta_ticks/delta_wall <= 345,
             "SPEED_GATE_FAILED")
        for case in cases:
            item2 = item["cases"][case["id"]]
            folder = out/session/case["id"]
            need(item2["kind"] == case["kind"] and
                 item2["pre_run_delays"] == case.get("pre_run_delays",0),
                 "CASE_METADATA_DRIFT")
            listed = cfg_and_process(folder/"list",item2["list"])
            run = cfg_and_process(folder/"run",item2["run"])
            expected_list = ["MODE 1","NEW",*case["lines"],"LIST",
                 "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT",
                 "LIST #8","CAP32_DELAY CAP32_EXIT"]
            expected_run = ["MODE 1","NEW",*case["lines"]]
            if case.get("pre_run_delays"):
                expected_run += [" ".join(["CAP32_DELAY"]*case["pre_run_delays"])]
            expected_run += ["RUN","CAP32_DELAY CAP32_DELAY CAP32_SNAPSHOT",
                 "CONT","CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"]
            need(listed == expected_list and run == expected_run,
                 "CHRONOLOGY_OR_SOURCE_DRIFT")
            for meta in (item2["list"],item2["run"]):
                need(meta["started_utc"] not in timestamps,"DUPLICATE_START_TIMESTAMP")
                timestamps.add(meta["started_utc"])
            raw = read(folder/"program.bin")
            parser = prior.ram_parser()
            nums,records = parser.records(raw)
            need(nums == [int(line.split(" ",1)[0]) for line in case["lines"]]
                 and sha(raw) == item2["program_sha256"] and
                 sha(read(folder/"stop_program.bin")) == item2["stop_program_sha256"]
                 and sha(read(folder/"list/printer.dat")) == item2["list_printer_sha256"]
                 and read(folder/"list/printer.dat").strip(),
                 "PROGRAM_OR_LIST_DRIFT")
            need((b"\xff\x46" in raw) == (case["kind"] == "time"),
                 "TOKEN_TIME_DRIFT")
            stop = json.loads(read(folder/"stop.json"))
            window = read(folder/"window.bin")
            ptr = stop["pointers"]
            need(stop["ram_window_sha256"] == sha(window) ==
                 item2["window_sha256"] and
                 stop["ram_window_start"] == ptr["scalar_start"] and
                 stop["ram_window_end"] == ptr["array_start"] and
                 ptr["array_start"]-ptr["scalar_start"] == len(window)
                 and 0x016f < ptr["program_end"] <= ptr["scalar_start"] <
                 ptr["array_start"] <= ptr["array_end"] < 0xac00,
                 "RAM_POINTER_OR_HASH_MISMATCH")
            ids = [ord("T")] if case["kind"] == "known" else [ord("T"),ord("U")]
            found = check_window(window,ptr["scalar_start"],ids)
            # JSON serialization turns numeric dictionary keys into strings.
            need({str(k):v for k,v in found.items()} == stop["entries"]
                 and sha(read(folder/"stop.json")) == item2["stop_sha256"],
                 "RAM_SCALAR_METADATA_MISMATCH")
            measurements = validate_link(case,stop["entries_as_int"]
                if False else {"entries":{int(k):v for k,v in stop["entries"].items()}},
                folder/"run/printer.dat")
            need(measurements == item2["numbers"],"PRINTER_DRIFT")
    print("CLK-04-A1 RAW_REPLAY_PASS (PNG_BOOT_AND_STOP_HUMAN_REVIEW_REQUIRED)")
    return True

def self_test():
    source_cases()
    need(numbers(b" 0.5 \r\n-2\n",2)==[Decimal(".5"),Decimal(-2)],
         "SELF_DECIMAL")
    for fake in (b"1 2\n",b"nope\n",b"1\n2\n"):
        try:
            numbers(fake,1)
        except prior.OracleError:
            pass
        else:
            raise prior.OracleError("SELF_BAD_NUM_ACCEPTED")
    try:
        check_window(bytes.fromhex("00 00 D4 05 00 00 00 00 81"),
                     100,[ord("T")])
    except prior.OracleError:
        pass
    else:
        raise prior.OracleError("SELF_BAD_TYPE_ACCEPTED")
    print("CLK-04-A1 SELF_TEST_PASS (SYNTHETIC_NOT_CPC)")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--self-test",action="store_true")
    a.add_argument("--acquire",action="store_true")
    a.add_argument("--verify",type=Path)
    a.add_argument("--caprice",type=Path)
    a.add_argument("--output",type=Path)
    a.add_argument("--head")
    a.add_argument("--seal")
    args=a.parse_args()
    if args.self_test:
        self_test()
    elif args.acquire:
        need(args.caprice is not None and args.output is not None and args.head,
             "ARGS_MISSING")
        acquire(args.caprice.resolve(),args.output.resolve(),args.head)
    elif args.verify:
        need(args.head and args.seal,"REPLAY_HEAD_AND_SEAL_REQUIRED")
        verify(args.verify.resolve(),args.head,args.seal)
    else:
        a.error("select --self-test, --acquire or --verify")

if __name__ == "__main__":
    try:
        main()
    except (prior.OracleError,ValueError,KeyError,IndexError) as exc:
        print("CLK-04-A1 REJECT",str(exc),file=sys.stderr)
        raise SystemExit(2)
