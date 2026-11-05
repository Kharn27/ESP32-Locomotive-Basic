#!/usr/bin/env python3
"""J1.25-A: independent CPC6128 DATA/READ/RESTORE evidence; no native engine."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = "c8cec8b1b4d0cab553cdc8b97b751aef3dd1370d"
ROM = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
CAPRICE = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
IMAGE = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
         "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")
MISSION = "J1.25-A"
DIAG_MARKER = b"J125_DIAG_BEGIN"
SOURCES = ROOT / "tests/oracles/inputs/j1_25_a"
TOKENS = {"DATA":0x8c,"READ":0xc3,"RESTORE":0xc7}
EXTERNAL_MANIFEST_SHA256 = None
EXTERNAL_ACQUISITION_HEAD = None

# Each list is the EXACT experimental BASIC source, not a predicted CPC result.
# Inputs are distinct, finite by construction if normal INTEGER updates work;
# process wall-clock timeout is mandatory if they do not.
CASES = {
 "ONE_INTEGER": (
  "10 DATA 1",
  "20 READ A%",
  "30 PRINT #8,A%",
  "40 END"
 ),
 "TWO_INTEGERS": (
  "10 DATA 1,2",
  "20 READ A%,B%",
  "30 PRINT #8,A%",
  "40 PRINT #8,B%",
  "50 END"
 ),
 "ONE_STRING": (
  "10 DATA \"HELLO\"",
  "20 READ A$",
  "30 PRINT #8,A$",
  "40 END"
 ),
 "QUOTED_COMMA": (
  "10 DATA \"A,B\"",
  "20 READ A$",
  "30 PRINT #8,A$",
  "40 END"
 ),
 "MIXED_TYPES": (
  "10 DATA 3,\"Z\"",
  "20 READ A%,B$",
  "30 PRINT #8,A%",
  "40 PRINT #8,B$",
  "50 END"
 ),
 "NEXT_DATA_LINE": (
  "10 DATA 4",
  "20 DATA 5",
  "30 READ A%",
  "40 READ B%",
  "50 PRINT #8,A%",
  "60 PRINT #8,B%",
  "70 END"
 ),
 "JUMP_OVER_DATA": (
  "10 GOTO 30",
  "20 DATA 7",
  "30 READ A%",
  "40 PRINT #8,A%",
  "50 END"
 ),
 "RESTORE_BEGIN": (
  "10 DATA 6,7",
  "20 READ A%",
  "30 PRINT #8,A%",
  "40 RESTORE",
  "50 READ B%",
  "60 PRINT #8,B%",
  "70 END"
 ),
 "RESTORE_TARGET": (
  "10 DATA 1",
  "20 DATA 4",
  "30 READ A%",
  "40 RESTORE 100",
  "50 READ B%",
  "60 PRINT #8,B%",
  "70 GOTO 200",
  "100 DATA 9",
  "200 END"
 ),
 "DATA_COLON": (
  "10 DATA 1:PRINT #8,\"BEFORE\"",
  "20 READ A%",
  "30 PRINT #8,A%",
  "40 END"
 ),
 "DATA_EXHAUSTED": (
  "10 DATA 1",
  "20 READ A%",
  "30 PRINT #8,A%",
  "40 READ B%",
  "50 PRINT #8,\"AFTER\"",
  "60 END"
 ),
 "TYPE_MISMATCH": (
  "10 DATA \"HELLO\"",
  "20 READ A%",
  "30 PRINT #8,\"AFTER\"",
  "40 END"
 ),
}
SESSIONS = ("original", "repeat")
FILES = ("program.bin", "capture.json", "list/caprice.log", "list/screen.png",
         "list/printer.dat", "run/caprice.log", "run/screen_0.png",
         "run/screen_1.png", "run/printer.dat")
RECTS = {"text":(64,81,704,481), "text_top_left":(64,81,200,161)}

class OracleError(ValueError):
    pass

def need(ok, code):
    if not ok:
        raise OracleError(code)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    need(path.is_file() and not path.is_symlink(), "ABSENT_OR_SYMLINK_" + str(path))
    return path.read_bytes()

def canonical(obj):
    return (json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=True)+"\n").encode("ascii")

def program(case):
    need(case in CASES, "UNKNOWN_CASE")
    expected=("\n".join(CASES[case])+"\n").encode("ascii")
    need(read(SOURCES/(case+".bas"))==expected,"SOURCE_FILE_DRIFT_"+case)
    return expected

def line_numbers(case):
    return [int(line.split(" ",1)[0]) for line in CASES[case]]

def inventory():
    return {f"{session}/{case}/{part}"
            for session in SESSIONS for case in CASES for part in FILES} | {"index.json"}

def check():
    need(len(CASES)==12 and len({tuple(v) for v in CASES.values()})==12,
         "CORPUS_12_DRIFT")
    need(TOKENS=={"DATA":0x8c,"READ":0xc3,"RESTORE":0xc7},
         "ROM_TOKEN_REFERENCES")
    for case,lines in CASES.items():
        need(3<=len(lines)<=12 and
             len(set(line_numbers(case)))==len(lines) and
             line_numbers(case)==sorted(line_numbers(case)) and
             all(re.fullmatch(r"[0-9]+ [ -~]{1,180}",s) for s in lines) and
             any(re.match(r"[0-9]+ (DATA|READ|RESTORE)\b",s) for s in lines) and
             lines[-1].endswith(" END"),"SOURCE_INVALID_"+case)
        program(case)
    need(len(inventory())==12*2*len(FILES)+1,"ARCHIVE_MATRIX")
    print("J1.25-A SOURCE_CONTRACT_PASS 12_CASES 24_SESSIONS",flush=True)

def imports():
    sys.path.insert(0,str(ROOT/"tools"))
    import j1_18_a_ink_evidence as ink
    import j1_18_a_ink_pixels as png
    need(ink.cpc.PIN==CAPRICE and ink.cpc.ROM_SHA==ROM and ink.GHCR==IMAGE,
         "CAPRICE_PIN_DRIFT")
    return ink,png

def head():
    return subprocess.check_output(
        ["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip()

def ancestor(commit):
    return bool(re.fullmatch("[0-9a-f]{40}",commit or "")) and (
        subprocess.run(["git","-C",str(ROOT),"merge-base","--is-ancestor",
                        commit,"HEAD"],stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL).returncode==0)

def setup():
    return ["MODE 1","NEW"]

def list_commands(case):
    return setup()+list(CASES[case])+[
        "LIST","CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT",
        "LIST #8","CAP32_DELAY CAP32_EXIT"]

def run_commands(case):
    return setup()+list(CASES[case])+[
        "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT","RUN",
        " ".join(["CAP32_DELAY"]*96)+" CAP32_SCRNSHOT",
        'PRINT #8,"J125_DIAG_BEGIN"',
        "PRINT #8,ERR","PRINT #8,ERL","LIST #8",
        "CAP32_DELAY CAP32_EXIT"]

def roi(rows,rect):
    x0,y0,x1,y1=rect
    need(len(rows)==540 and all(len(r)==768*3 for r in rows),"PNG_SHAPE")
    return b"".join(bytes(r[x0*3:x1*3]) for r in rows[y0:y1])

def rgb_evidence(png,folder):
    before=png.png_rgb(folder/"screen_0.png")
    after=png.png_rgb(folder/"screen_1.png")
    result={}
    for key,rect in RECTS.items():
        a,b=roi(before,rect),roi(after,rect)
        result[key]={"before_sha256":sha(a),"after_sha256":sha(b),
                     "changed_bytes":sum(x!=y for x,y in zip(a,b))}
    return result

def parse_printer(printer,ink):
    lines=printer.splitlines(keepends=True)
    offsets=[i for i,v in enumerate(lines) if v.strip()==DIAG_MARKER]
    need(len(offsets)==1,"DIAG_MARKER_MISSING_OR_DUPLICATE")
    at=offsets[0]
    need(len(lines)>=at+4,"ERR_ERL_OR_LIST_MISSING")
    values=[ink.parse_integer(x) for x in lines[at+1:at+3]]
    need(all(x is not None for x in values),"ERR_ERL_INVALID")
    before=b"".join(lines[:at])
    after=b"".join(lines[at+3:])
    need(len(after)>0,"POST_RUN_LIST_EMPTY")
    return before,[v["numeric_value"] for v in values],after

def observed_keyword_lines(case,ram,records):
    samples=[]
    for src,rec in zip(CASES[case],records):
        stmt=src.split(" ",1)[1]
        m=re.match(r"(DATA|READ|RESTORE)\b",stmt)
        if not m:
            continue
        token=m.group(1)
        raw=ram[rec["offset"]:rec["offset"]+rec["length"]]
        body=raw[4:-1]
        need(bool(body) and body[0]==TOKENS[token],
             "RAM_TOKEN_"+case+"_"+str(rec["line"]))
        samples.append({"line":int(src.split(" ",1)[0]),
                        "keyword":token,"expected_rom_token":TOKENS[token],
                        "source_statement":stmt,"record_hex":raw.hex(" ").upper(),
                        "body_hex":body.hex(" ").upper(),
                        "first_body_byte":body[0]})
    need(bool(samples),"NO_KEYWORD_SAMPLES_"+case)
    return samples

def capture(cap,out,session,case,tmp,ink,png):
    dest=out/session/case
    snaps=tmp/(session+"-"+case)
    snaps.mkdir()
    list_meta=ink.launch(cap,dest/"list",snaps,list_commands(case),True)
    snapshots=list(snaps.glob("*.sna"))
    need(len(snapshots)==1,"SNA_COUNT_"+case)
    ram,region=ink.cpc.extract_snapshot(read(snapshots[0]),line_numbers(case))
    numbers,records=ink.cpc.records(ram)
    need(numbers==line_numbers(case),"RAM_LINES_"+case)
    (dest/"program.bin").write_bytes(ram)
    pre_list=read(dest/"list/printer.dat")
    need(len(pre_list)>0,"LIST_EMPTY_"+case)
    run_meta=ink.launch(cap,dest/"run",tmp,run_commands(case),True,shots=2)
    printer=read(dest/"run/printer.dat")
    run_output,(err,erl),post_list=parse_printer(printer,ink)
    if pre_list!=post_list:
        print("J1.25-A POST_RUN_LIST_DIVERGENCE",session,case,flush=True)
    record={
        "case":case,"session":session,"kind":"CPC6128_CAPRICE32_REAL_ONLY",
        "source_ascii":program(case).decode("ascii"),
        "source_sha256":sha(program(case)),
        "line_numbers":numbers,
        "observed_keyword_lines":observed_keyword_lines(case,ram,records),
        "program_sha256":sha(ram),"program_hex":ram.hex(" ").upper(),
        "region":region,"err":err,"erl":erl,
        "run_output_hex":run_output.hex(),"run_output_sha256":sha(run_output),
        "run_output_ascii":run_output.decode("ascii",errors="backslashreplace"),
        "list_sha256":sha(pre_list),
        "list_after_sha256":sha(post_list),
        "list_after_hex":post_list.hex(),
        "list_equal":pre_list==post_list,
        "printer_sha256":sha(printer),"printer_hex":printer.hex(),
        "screenshots":{p:sha(read(dest/"run"/p))
                       for p in ("screen_0.png","screen_1.png")},
        "roi_rgb":rgb_evidence(png,dest/"run"),
        "commands":{"list":list_commands(case),"run":run_commands(case)},
        "metadata":{"list":list_meta,"run":run_meta},
        "diagnostic_text":"INCONCLUSIVE_PENDING_SCREEN_INSPECTION",
        "program_complete":"NOT_INFERRED_FROM_ERR_ZERO",
        "timeout":"NO_TIMEOUT_FROM_SUCCESSFUL_PROCESS_EXIT"
    }
    (dest/"capture.json").write_bytes(canonical(record))
    print("J1.25-A CPC",session,case,"ERR",err,"ERL",erl,
          "RUN_OUTPUT_HEX",run_output.hex(),flush=True)

def acquire(cap,out,expected_head):
    check()
    need(not out.exists(),"DEST_EXISTS")
    need(head()==expected_head and ancestor(BASE) and ancestor(expected_head),
         "HEAD_OR_BASE")
    ink,png=imports()
    version=ink.check_caprice(cap)
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="j125-snap-") as t:
        for session in SESSIONS:
            for case in CASES:
                capture(cap,out,session,case,Path(t),ink,png)
    # Index source/session archive derived from the fresh CPC captures.
    index={"schema":1,"mission":MISSION,
           "sources":{c:sha(program(c)) for c in CASES},
           "sessions":[{"case":c,"session":s,
                        "capture_sha256":sha(read(out/s/c/"capture.json"))}
                       for s in SESSIONS for c in CASES]}
    (out/"index.json").write_bytes(canonical(index))
    manifest={
        "schema":1,"mission":MISSION,"base":BASE,
        "acquisition_head":expected_head,"rom_sha256":ROM,
        "caprice_commit":CAPRICE,"image":IMAGE,
        "caprice_version":version,"run_id":os.getenv("GITHUB_RUN_ID","LOCAL"),
        "status":"UNSEALED","cases":list(CASES),"sessions":list(SESSIONS),
        "snapshots_archived":False,"native_execution":False,
        "files":{p:sha(read(out/p)) for p in sorted(inventory())}
    }
    (out/"manifest.json").write_bytes(canonical(manifest))
    verify(out)
    print("J1.25-A CAPTURE_24_MANIFEST_SHA256",
          sha(read(out/"manifest.json")),flush=True)

def verify(out,seal=None,expected_head=None):
    check()
    manifest=read(out/"manifest.json")
    m=json.loads(manifest)
    need(m.get("schema")==1 and m.get("mission")==MISSION and
         m.get("base")==BASE and m.get("rom_sha256")==ROM and
         m.get("caprice_commit")==CAPRICE and m.get("image")==IMAGE and
         m.get("cases")==list(CASES) and m.get("sessions")==list(SESSIONS) and
         m.get("status")=="UNSEALED" and
         m.get("snapshots_archived") is False and
         m.get("native_execution") is False,"PROVENANCE")
    need(ancestor(m.get("acquisition_head")),"FAKE_HEAD")
    wanted=inventory()
    need(set(m["files"])==wanted,"MANIFEST_FILES")
    actual={str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()}
    need(actual==wanted|{"manifest.json"},"ARCHIVE_INVENTORY")
    if seal is not None:
        need(bool(re.fullmatch("[0-9a-f]{64}",seal)) and sha(manifest)==seal,
             "EXTERNAL_MANIFEST_SEAL")
        need(bool(re.fullmatch("[0-9a-f]{40}",expected_head or "")) and
             m["acquisition_head"]==expected_head,"EXTERNAL_HEAD_SEAL")
    for file in sorted(wanted):
        need(sha(read(out/file))==m["files"][file],"HASH_"+file)
    ink,png=imports()
    idx=json.loads(read(out/"index.json"))
    need(idx.get("schema")==1 and idx.get("mission")==MISSION and
         idx.get("sources")=={c:sha(program(c)) for c in CASES} and
         idx.get("sessions")==[
            {"case":c,"session":s,
             "capture_sha256":sha(read(out/s/c/"capture.json"))}
            for s in SESSIONS for c in CASES],
         "INDEX_SOURCE_SESSION_CONTRACT")
    for case in CASES:
        observations=[]
        for session in SESSIONS:
            d=out/session/case
            record=json.loads(read(d/"capture.json"))
            ram=read(d/"program.bin")
            nums,records=ink.cpc.records(ram)
            need(nums==line_numbers(case) and record["case"]==case and
                 record["session"]==session and
                 record["source_ascii"]==program(case).decode("ascii") and
                 record["source_sha256"]==sha(program(case)) and
                 record["line_numbers"]==nums and
                 record["program_sha256"]==sha(ram) and
                 record["program_hex"]==ram.hex(" ").upper() and
                 record["observed_keyword_lines"]==
                 observed_keyword_lines(case,ram,records) and
                 record["commands"]==
                 {"list":list_commands(case),"run":run_commands(case)} and
                 record["metadata"]["list"]["commands"]==list_commands(case) and
                 record["metadata"]["run"]["commands"]==run_commands(case),
                 "RAM_SOURCE_COMMAND_"+case+session)
            pre_list=read(d/"list/printer.dat")
            printer=read(d/"run/printer.dat")
            out_bytes,errors,post_list=parse_printer(printer,ink)
            need(errors==[record["err"],record["erl"]] and
                 record["run_output_hex"]==out_bytes.hex() and
                 record["run_output_sha256"]==sha(out_bytes) and
                 record["run_output_ascii"]==
                 out_bytes.decode("ascii",errors="backslashreplace") and
                 record["list_after_sha256"]==sha(post_list) and
                 record["list_after_hex"]==post_list.hex() and
                 record["list_equal"]==(post_list==pre_list) and
                 record["list_sha256"]==sha(pre_list) and
                 record["printer_sha256"]==sha(printer) and
                 record["printer_hex"]==printer.hex(),
                 "PRINTER_RUN_ERR_ERL_"+case+session)
            need(record["screenshots"]==
                 {p:sha(read(d/"run"/p))
                  for p in ("screen_0.png","screen_1.png")} and
                 record["roi_rgb"]==rgb_evidence(png,d/"run"),
                 "SCREEN_"+case+session)
            for part in ("list","run"):
                need(read(d/part/"caprice.log").startswith(b"exit code: 0\n"),
                     "CPC_EXIT_"+case+session+part)
            observations.append((ram,pre_list,post_list,out_bytes,
                                 record["err"],record["erl"],record))
        a,b=observations
        need(a[:6]==b[:6] and
             a[6]["metadata"]["list"]["started_utc"]!=
             b[6]["metadata"]["list"]["started_utc"] and
             a[6]["metadata"]["run"]["started_utc"]!=
             b[6]["metadata"]["run"]["started_utc"],
             "REPEAT_INDEPENDENCE_"+case)
    print("J1.25-A VERIFIED 12_CASES 24_SESSIONS "+
          ("EXTERNAL_SEAL" if seal else "UNSEALED"),flush=True)

def falsifications(out,seal=None,expected_head=None):
    # Independent counterfeits. Seal-bound tests cannot pass unsealed.
    jobs=[
      ("RAM","original/ONE_INTEGER/program.bin","HASH_"),
      ("LIST","original/TWO_INTEGERS/list/printer.dat","HASH_"),
      ("PRINTER","repeat/QUOTED_COMMA/run/printer.dat","HASH_"),
      ("SCREEN","original/TYPE_MISMATCH/run/screen_1.png","HASH_"),
      ("CAPTURE","repeat/RESTORE_BEGIN/capture.json","HASH_"),
      ("SESSION_REPLACEMENT","repeat/NEXT_DATA_LINE/capture.json","HASH_"),
      ("FALSE_ROM","manifest.json","PROVENANCE"),
      ("FALSE_HEAD","manifest.json","EXTERNAL_HEAD_SEAL"),
      ("MANIFEST_REHASH","manifest.json","EXTERNAL_MANIFEST_SEAL"),
      ("MANIFEST_RAW","manifest.json","EXTERNAL_MANIFEST_SEAL")
    ]
    tested=0
    for name,path,reason in jobs:
        if seal is None and name in ("FALSE_HEAD","MANIFEST_REHASH","MANIFEST_RAW"):
            continue
        with tempfile.TemporaryDirectory(prefix="j125-forgery-") as temp:
            clone=Path(temp)/"archive"
            shutil.copytree(out,clone)
            victim=clone/path
            if name=="SESSION_REPLACEMENT":
                victim.write_bytes(read(clone/"original/NEXT_DATA_LINE/capture.json"))
            elif name=="FALSE_ROM":
                m=json.loads(read(victim))
                m["rom_sha256"]="0"*64
                victim.write_bytes(canonical(m))
            elif name=="FALSE_HEAD":
                m=json.loads(read(victim))
                m["acquisition_head"]=BASE
                victim.write_bytes(canonical(m))
                # Preserve external manifest SHA to force seal fail first.
                reason="EXTERNAL_MANIFEST_SEAL"
            elif name=="MANIFEST_REHASH":
                target=clone/"original/ONE_INTEGER/program.bin"
                raw=bytearray(read(target));raw[0]^=1;target.write_bytes(raw)
                m=json.loads(read(victim))
                m["files"]["original/ONE_INTEGER/program.bin"]=sha(read(target))
                victim.write_bytes(canonical(m))
            else:
                raw=bytearray(read(victim))
                need(bool(raw),"EMPTY_FALSIFICATION_TARGET_"+name)
                raw[len(raw)//2]^=1
                victim.write_bytes(raw)
            try:
                verify(clone,seal,expected_head)
            except (OracleError,ValueError,KeyError,UnicodeError) as exc:
                got=str(exc)
                need(got.startswith(reason),"WRONG_REJECTION_"+name+"_"+got)
                print("J1.25-A FALSIFICATION_REJECTED",name,got,flush=True)
                tested+=1
            else:
                raise OracleError("FALSIFICATION_ACCEPTED_"+name)
    need(tested>=(10 if seal else 7),"INSUFFICIENT_FALSIFICATIONS")
    print("J1.25-A FALSIFICATIONS_REJECTED",tested,flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check",action="store_true")
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--acquire",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--head")
    p.add_argument("--verify",type=Path)
    p.add_argument("--external-manifest-sha256")
    p.add_argument("--external-acquisition-head")
    p.add_argument("--permanent",action="store_true")
    args=p.parse_args()
    need(args.check or args.self_test or args.acquire or args.verify or
         args.permanent,"ACTION_REQUIRED")
    if args.check or args.self_test:
        check()
    if args.acquire:
        need(args.output is not None and args.verify is None,"ARGUMENTS")
        acquire(args.acquire.resolve(),args.output.resolve(),args.head or "")
    if args.permanent:
        need(EXTERNAL_MANIFEST_SHA256 is not None and
             EXTERNAL_ACQUISITION_HEAD is not None,"EXTERNAL_SEAL_REQUIRED")
        need(args.verify is not None,"ARCHIVE_REQUIRED")
    if args.verify:
        seal=(EXTERNAL_MANIFEST_SHA256 if args.permanent else
              args.external_manifest_sha256)
        acq=(EXTERNAL_ACQUISITION_HEAD if args.permanent else
             args.external_acquisition_head)
        verify(args.verify.resolve(),seal,acq)
        if args.self_test:
            falsifications(args.verify.resolve(),seal,acq)
    if args.self_test and not args.verify:
        with tempfile.TemporaryDirectory() as t:
            try:
                verify(Path(t))
            except OracleError as e:
                need("ABSENT" in str(e),"FAIL_CLOSED")
            else:
                raise OracleError("FAKE_ARCHIVE_PASSED")
        print("J1.25-A OFFLINE_FAIL_CLOSED_PASS",flush=True)
if __name__=="__main__":
    try:
        main()
    except (OracleError,OSError,ValueError,KeyError,IndexError,UnicodeError,
            subprocess.SubprocessError) as e:
        print("J1.25-A FAIL",e,file=sys.stderr)
        sys.exit(1)
