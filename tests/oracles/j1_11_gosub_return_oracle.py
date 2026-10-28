#!/usr/bin/env python3
"""J1.11-A: ROM-backed CPC6128 independent GOSUB/RETURN oracle, no native stack.

The 16 mandatory sources each run twice in fully separate Caprice32 LIST/SNA
and RUN/printer processes. The original archives are not rewritten by
reacquisition. No GOSUB/RETURN native implementation is provided.
"""
import argparse
import configparser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import token_ram_oracle as oracle
from signed_print_oracle import parse_integer

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "tests/oracles/inputs/j1_11_a"
MAIN_CASES = ("F_DIRECT_FORWARD","F_DIRECT_BACK","F_REPEAT","F_NESTED2","F_LAST_RETURN","F_MISSING_TARGET","F_UNPAIRED_RETURN","F_END_IN_SUB","F_RETURN_AFTER_PRINTS","F_GOTO_IN_SUB","F_IF_TRUE_DISPATCH","F_IF_FALSE_DISPATCH","F_IF_INSIDE_SUB","F_GOTO_AFTER_RETURN","F_COLON_CONTINUATION","F_UNPAIRED_AFTER_CALL")
EXPLORATORY = ()  # future syntax explorations deliberately not treated as mandatory proof
GHCR_PIN = "ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c"

def check(ok, label):
    oracle.check(ok, label)

def checkout_identity(claim):
    actual = subprocess.check_output(["git", "-C", str(ROOT),
                                      "rev-parse", "HEAD"], text=True).strip()
    check(re.fullmatch("[a-f0-9]{40}", str(claim)) is not None,
          "ACQUISITION_EVENT_SHA_ABSENT")
    check(actual == claim, "ACQUISITION_FALSE_CHECKOUT actual="+actual+
          " expected="+str(claim))
    return actual

def source(name):
    path = SOURCES / (name.lower() + ".bas")
    raw = path.read_bytes()
    check(raw.endswith(b"\n") and b"\r" not in raw and
          all(re.fullmatch(rb"[1-9][0-9]* .+", l)
              for l in raw.splitlines()), name+": BAD_SOURCE")
    numbers = [int(l.split(b" ",1)[0]) for l in raw.splitlines()]
    check(numbers == sorted(set(numbers)) and 20 in numbers,
          name+": INVALID_LINE_SEQUENCE")
    return raw, numbers

def inventory(work):
    return {str(p.relative_to(work)): {"sha256": oracle.sha(p.read_bytes()),
                                      "size_bytes": p.stat().st_size}
            for p in sorted(work.rglob("*")) if p.is_file()}

def run_observation(cap, work, raw, exploratory=False):
    dest = work / "run"
    dest.mkdir(parents=True, exist_ok=False)
    cfg = configparser.ConfigParser(interpolation=None)
    check(bool(cfg.read(cap / "cap32.cfg")), "CPC32_CONFIG_MISSING")
    cfg["system"].update(model="2", ram_size="128", speed="4",
                         auto_pause="0", printer="1", mf2="0", keyboard="0",
                         boot_time="42", limit_speed="0")
    cfg["control"]["kbd_layout"] = "0"
    cfg["sound"]["enabled"] = "0"
    cfg["video"].update(scr_style="1", scr_window="1")
    cfg["file"]["printer_file"] = str(dest / "printer.dat")
    cfg["file"]["sdump_dir"] = str(dest)
    cfg["rom"]["rom_path"] = str(cap / "rom")
    cfg["rom"]["slot07"] = "amsdos.rom"
    cfg["rom"]["rom_mf2"] = ""
    cfg["system"]["resources_path"] = str(cap / "resources")
    with (dest / "cap32.cfg").open("w") as f:
        cfg.write(f, space_around_delimiters=False)
    commands = raw.decode("ascii").splitlines() + [
        "RUN", "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT",
        "PRINT #8,ERR", "PRINT #8,ERL",
        "CAP32_DELAY CAP32_EXIT"]
    (dest / "autocmd.json").write_text(json.dumps({
        "commands": commands, "program_sha256": oracle.sha(raw),
        "runtime_printer_in_program": True,
        "post_run_direct_probe": ["ERR","ERL"],
        "screenshot_before_post_run_probes": True,
        "printer_is_not_screen_output": True
    }, indent=2)+"\n")
    cmd = ["xvfb-run","-a",str(cap/"cap32"),"-c",str(dest/"cap32.cfg")]
    for command in commands:
        cmd += ["-a",command]
    env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
    start = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(cmd,cwd=cap,env=env,capture_output=True,
                            timeout=120,check=False)
    end = datetime.now(timezone.utc).isoformat()
    (dest/"caprice.log").write_bytes(
        f"exit code: {result.returncode}\n".encode()+
        result.stdout+b"\n[stderr]\n"+result.stderr)
    if result.returncode != 0 and not exploratory:
        raise ValueError("CPC_RUN_PROCESS_FAILED "+repr(result.stderr[-300:]))
    pngs = sorted(dest.glob("screenshot_*.png"))
    if len(pngs) == 1:
        check(pngs[0].read_bytes().startswith(b"\x89PNG\r\n\x1a\n"),
              "INVALID_RUN_PNG")
        pngs[0].rename(dest/"run.png")
    elif not exploratory:
        raise ValueError("RUN_PNG_ABSENT")
    raw_printer = (dest/"printer.dat").read_bytes() if (dest/"printer.dat").is_file() else b""
    rows = [parse_integer(l) for l in raw_printer.splitlines(keepends=True)]
    numeric = [r["numeric_value"] if r is not None else None for r in rows]
    parsed = len(numeric) >= 2 and None not in numeric
    return {
        "session_start_utc":start, "session_end_utc":end,
        "fresh_cpc_run_process":True, "returncode":result.returncode,
        "screen_png_present": (dest/"run.png").is_file(),
        "printer_raw_hex":raw_printer.hex(" ").upper(),
        "printer_lines":numeric,"all_printer_lines_numeric":parsed,
        "program_trace":numeric[:-2] if parsed else None,
        "err_probe":numeric[-2] if parsed else None,
        "erl_probe":numeric[-1] if parsed else None,
        "result_class":"OBSERVED" if parsed else "UNVERIFIED",
        "files":inventory(dest)
    }

def one(cap, dest, name, raw, numbers, image_cli):
    before=datetime.now(timezone.utc).isoformat()
    pre=oracle.acquire(cap,cap/"rom",name,raw,numbers,image_cli,dest)
    after=datetime.now(timezone.utc).isoformat()
    pre["session_start_utc"]=before
    pre["session_end_utc"]=after
    work=dest/name
    (work/"original.bas").write_bytes(raw)
    ram=(work/"program.bin").read_bytes()
    nums, records=oracle.records(ram)
    check(nums == numbers, name+": CPC_LINE_SET_CHANGED")
    # Every GOSUB/RETURN line is recorded as the full original CPC RAM
    # record, including line header, opaque caches and final 00 terminator.
    flow=[]
    for index,source_line in enumerate(raw.splitlines()):
        if re.search(rb"\b(?:GOSUB|RETURN)\b",source_line):
            rec=records[index]
            encoded=ram[rec["offset"]:rec["offset"]+rec["length"]]
            flow.append({"line_number":numbers[index],
                         "record_hex":encoded.hex(" ").upper(),
                         "record_length":len(encoded)})
    check(bool(flow),name+": NO_FLOW_IN_SOURCE")
    pre["flow_records"]=flow
    pre["files"]["original.bas"]={"sha256":oracle.sha(raw),
                                   "size_bytes":len(raw)}
    run=run_observation(cap,work,raw)
    return {"pre_run":pre,"run":run,
            "all_files_sha256":inventory(work)}

def explore(cap,root,name,raw,numbers):
    work=root/name
    work.mkdir(parents=True,exist_ok=False)
    (work/"original.bas").write_bytes(raw)
    observation=run_observation(cap,work,raw,exploratory=True)
    return {"original_source_sha256":oracle.sha(raw),
            "line_numbers":numbers,"run":observation,
            "scope":"EXPLORATION_ONLY_NEVER_J1_10_B_PROOF"}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--caprice",type=Path,required=True)
    p.add_argument("--image-cli",type=Path,required=True)
    p.add_argument("--native-cli",type=Path,required=True)  # reserved for pre-B classification proof
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    cap=args.caprice.resolve()
    out=args.output.resolve()
    head=checkout_identity(os.environ.get("GITHUB_HEAD_SHA"))
    oracle.self_test()
    check(not out.exists(),"EVIDENCE_OUTPUT_MUST_BE_FRESH")
    check(subprocess.check_output(["git","-C",str(cap),"rev-parse","HEAD"],
                                  text=True).strip()==oracle.PIN,"CAPRICE_PIN_MISMATCH")
    check(oracle.sha((cap/"rom/cpc6128.rom").read_bytes())==oracle.ROM_SHA,
          "CPC_ROM_SHA_MISMATCH")
    check((cap/"cap32").is_file(),"CPC_CAP32_BINARY_MISSING")
    version=subprocess.check_output([str(cap/"cap32"),"--version"],
                                    cwd=cap,text=True).strip()
    manifest={
        "schema_version":1,"phase":"J1.11-A",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "github_head_sha":head,"github_run_id":os.environ.get("GITHUB_RUN_ID"),
        "oracle":{"emulator":"Caprice32","commit":oracle.PIN,
                  "rom_sha256":oracle.ROM_SHA,"model":"CPC6128",
                  "basic":"1.1","ram_kb":128,"version_output":version},
        "ghcr_image":GHCR_PIN,
        "rom_archived":False,"full_snapshots_archived":False,
        "printer_is_screen_output":False,"j1_11_b_authorized":False,
        "historical_archives_modified":False,
        "mandatory_cases":list(MAIN_CASES),
        "exploratory_cases":list(EXPLORATORY),
        "captures":[],"explorations":[]
    }
    out.mkdir(parents=True)
    original, repeated, exploratory = (out/"original",out/"repeat",out/"exploratory")
    for d in (original,repeated,exploratory):
        d.mkdir()
    image_cli=args.image_cli.resolve()
    for name in MAIN_CASES:
        raw,numbers=source(name)
        first=one(cap,original,name,raw,numbers,image_cli)
        second=one(cap,repeated,name,raw,numbers,image_cli)
        ram0=(original/name/"program.bin").read_bytes()
        ram1=(repeated/name/"program.bin").read_bytes()
        printer0=(original/name/"run/printer.dat").read_bytes()
        printer1=(repeated/name/"run/printer.dat").read_bytes()
        check(ram0==ram1,name+": TWO_CPC_RAM_ACQUISITIONS_DISAGREE")
        check(printer0==printer1,name+": TWO_CPC_PRINTER_ACQUISITIONS_DISAGREE")
        check(first["run"]["all_printer_lines_numeric"] and
              second["run"]["all_printer_lines_numeric"],
              name+": DIRECT_ERR_ERL_PROBE_NOT_NUMERIC")
        manifest["captures"].append({
            "case":name,"source_path":"tests/oracles/inputs/j1_11_a/"+name.lower()+".bas",
            "source_sha256":oracle.sha(raw),"lines":numbers,
            "original":first,"repeat":second,
            "two_independent_process_pairs":True,
            "ram_exact_2of2":True,"printer_exact_2of2":True
        })
        print("J1.11-A",name,"RAM_SHA",oracle.sha(ram0),
              "PRINTER_SHA",oracle.sha(printer0),
              "TRACE",first["run"]["program_trace"],
              "ERR",first["run"]["err_probe"],
              "ERL",first["run"]["erl_probe"],
              "C99",first["pre_run"]["comparison"]["classification"],flush=True)
    for name in EXPLORATORY:
        raw,numbers=source(name)
        item=explore(cap,exploratory,name,raw,numbers)
        manifest["explorations"].append({"case":name,**item})
        print("J1.11-A EXPLORE",name,"TRACE",item["run"]["program_trace"],
              "ERR",item["run"]["err_probe"],"ERL",item["run"]["erl_probe"],
              "CLASS",item["run"]["result_class"],flush=True)
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,
                                                 ensure_ascii=True)+"\n")
    print("J1.11-A ACQUIRED 16 MANDATORY PAIRS; HEAD="+head,
          flush=True)

if __name__=="__main__":
    try:
        main()
    except (ValueError,OSError,subprocess.SubprocessError,
            configparser.Error,KeyError,UnicodeError) as exc:
        print("J1.11-A ACQUISITION FAILED:",exc,file=sys.stderr)
        sys.exit(1)
