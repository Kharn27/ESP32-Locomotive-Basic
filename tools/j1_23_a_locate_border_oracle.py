#!/usr/bin/env python3
"""J1.23-A: original CPC6128 LOCATE/BORDER oracle, not a C99 implementation."""
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
BASE = "3c9d3a679d5c5d9db4d659e7d2e1367914d7b7d8"
ROM = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
CAPRICE = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
IMAGE = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
         "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")
# These commands are experiments, not claimed accepted CPC syntax.
CASES = {
 "L_01_01":"LOCATE 1,1", "L_40_25":"LOCATE 40,25",
 "L_02_03":"LOCATE 2,3", "L_00_01":"LOCATE 0,1",
 "L_41_01":"LOCATE 41,1", "L_01_00":"LOCATE 1,0",
 "L_01_26":"LOCATE 1,26", "L_NEG_01":"LOCATE -1,1",
 "L_EXPR":"LOCATE 1+2,2+3", "L_MISSING":"LOCATE 1",
 "B_00":"BORDER 0", "B_26":"BORDER 26",
 "B_27":"BORDER 27", "B_NEG":"BORDER -1",
 "B_00_26":"BORDER 0,26", "B_26_00":"BORDER 26,0",
 "B_26_27":"BORDER 26,27", "B_NEG_01":"BORDER -1,1",
 "B_EXPR":"BORDER 1+2,3+4", "B_MISSING":"BORDER 1,",
}
SESSIONS = ("original","repeat")
FILES = ("program.bin","capture.json","list/caprice.log","list/screen.png",
         "list/printer.dat","run/caprice.log","run/screen_0.png",
         "run/screen_1.png","run/printer.dat")
OPCODES = {"L":0xA9,"B":0x82}   # Competing hypotheses: inspect real RAM.
RECTS = {"border_left":(8,110,48,430),"text":(64,81,704,481),
         "text_top_left":(64,81,200,161)}
class OracleError(ValueError):
    pass
def need(ok, code):
    if not ok: raise OracleError(code)
def sha(data):
    return hashlib.sha256(data).hexdigest()
def read(path):
    need(path.is_file() and not path.is_symlink(),"ABSENT_OR_SYMLINK_"+str(path))
    return path.read_bytes()
def canonical(obj):
    return (json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=True)+"\n").encode("ascii")
def program(case):
    label="LBLOC" if case.startswith("L_") else "LBBOR"
    return (f'10 {CASES[case]}\n20 PRINT "{label}"\n30 END\n').encode("ascii")
def inventory():
    return {f"{s}/{c}/{p}" for s in SESSIONS for c in CASES for p in FILES}
def check():
    need(len(CASES)==20 and len(set(CASES.values()))==20 and
         all(c[0] in OPCODES for c in CASES), "MATRIX_DRIFT")
    need(all(program(c).endswith(b"30 END\n") for c in CASES),"SOURCE_INVALID")
    print("J1.23-A SOURCE_CONTRACT_PASS 20_CASES 40_SESSIONS",flush=True)
def imports():
    sys.path.insert(0,str(ROOT/"tools"))
    import j1_18_a_ink_evidence as ink
    import j1_18_a_ink_pixels as png
    need(ink.cpc.PIN==CAPRICE and ink.cpc.ROM_SHA==ROM and ink.GHCR==IMAGE,
         "CAPRICE_PIN_DRIFT")
    return ink,png
def head():
    return subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip()
def ancestor(sha_):
    return bool(re.fullmatch("[0-9a-f]{40}",sha_ or "")) and \
       subprocess.run(["git","-C",str(ROOT),"merge-base","--is-ancestor",sha_,"HEAD"],
                      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def setup():
    return ["MODE 1","NEW"]    # controlled environment, not a MODE study
def list_commands(case):
    return setup()+program(case).decode("ascii").splitlines()+[
        "LIST","CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT",
        "LIST #8","CAP32_DELAY CAP32_EXIT"]
def run_commands(case):
    return setup()+program(case).decode("ascii").splitlines()+[
        "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT","RUN",
        " ".join(["CAP32_DELAY"]*96)+" CAP32_SCRNSHOT",
        "PRINT #8,ERR","PRINT #8,ERL","LIST #8","CAP32_DELAY CAP32_EXIT"]
def roi(rows,rect):
    x0,y0,x1,y1=rect
    need(len(rows)==540 and all(len(r)==768*3 for r in rows),"PNG_SHAPE")
    return b"".join(bytes(r[x0*3:x1*3]) for r in rows[y0:y1])
def rgb_evidence(png,folder):
    a=png.png_rgb(folder/"screen_0.png")
    b=png.png_rgb(folder/"screen_1.png")
    result={}
    for key,rect in RECTS.items():
        x,y=roi(a,rect),roi(b,rect)
        result[key]={"before_sha256":sha(x),"after_sha256":sha(y),
                     "changed_bytes":sum(i!=j for i,j in zip(x,y))}
    return result
def capture(cap,out,sess,case,tmp,ink,png):
    dest=out/sess/case
    snaps=tmp/(sess+"-"+case)
    snaps.mkdir()
    ml=ink.launch(cap,dest/"list",snaps,list_commands(case),True)
    snas=list(snaps.glob("*.sna"))
    need(len(snas)==1,"SNA_COUNT_"+case)
    prog,region=ink.cpc.extract_snapshot(read(snas[0]),[10,20,30])
    nums,records=ink.cpc.records(prog)
    need(nums==[10,20,30],"RAM_LINES_"+case)
    token=prog[records[0]["offset"]+4]    # observed, never patched
    (dest/"program.bin").write_bytes(prog)
    listing=read(dest/"list/printer.dat")
    need(len(listing)>0,"LIST_EMPTY_"+case)
    mr=ink.launch(cap,dest/"run",tmp,run_commands(case),True,shots=2)
    printer=read(dest/"run/printer.dat")
    parts=printer.splitlines(keepends=True)
    need(len(parts)>=3,"ERR_ERL_LIST_MISSING_"+case)
    numbers=[ink.parse_integer(x) for x in parts[:2]]
    need(all(n is not None for n in numbers),"ERR_ERL_INVALID_"+case)
    err,erl=[n["numeric_value"] for n in numbers]
    need(b"".join(parts[2:])==listing,"LIST_MUTATION_"+case)
    screenshots={p:sha(read(dest/"run"/p)) for p in ("screen_0.png","screen_1.png")}
    rec={
      "case":case,"session":sess,"kind":"CPC6128_CAPRICE32_REAL_ONLY",
      "source_ascii":program(case).decode("ascii"),
      "source_sha256":sha(program(case)),"command":CASES[case],
      "token_expected_hypothesis":OPCODES[case[0]],
      "token_observed_ram":token,"token_hypothesis_matches":token==OPCODES[case[0]],
      "program_sha256":sha(prog),"program_hex":prog.hex(" ").upper(),
      "region":region,"line_numbers":nums,"err":err,"erl":erl,
      "list_sha256":sha(listing),"printer_sha256":sha(printer),
      "printer_hex":printer.hex(),"screenshots":screenshots,
      "roi_rgb":rgb_evidence(png,dest/"run"),
      "commands":{"list":list_commands(case),"run":run_commands(case)},
      "metadata":{"list":ml,"run":mr},
      "diagnostic_text":"PENDING_MANUAL_SCREEN_INSPECTION",
      "cursor":"PENDING_VISUAL_INSPECTION",
      "border_flash":"NOT_INFERRED_FROM_STILL_PNG"
    }
    (dest/"capture.json").write_bytes(canonical(rec))
    print("J1.23-A CPC",sess,case,"TOKEN",hex(token),
          "ERR",err,"ERL",erl,flush=True)
def acquire(cap,out,sha_):
    check()
    need(not out.exists(),"DEST_EXISTS")
    need(head()==sha_ and ancestor(BASE) and ancestor(sha_),"HEAD_OR_BASE")
    ink,png=imports()
    version=ink.check_caprice(cap)
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="j123-snap-") as t:
        for sess in SESSIONS:
            for case in CASES:
                capture(cap,out,sess,case,Path(t),ink,png)
    m={"schema":1,"mission":"J1.23-A","base":BASE,"acquisition_head":sha_,
       "rom_sha256":ROM,"caprice_commit":CAPRICE,"image":IMAGE,
       "caprice_version":version,"run_id":os.getenv("GITHUB_RUN_ID","LOCAL"),
       "status":"UNSEALED","cases":list(CASES),"sessions":list(SESSIONS),
       "snapshots_archived":False,"native_execution":False,
       "files":{p:sha(read(out/p)) for p in sorted(inventory())}}
    (out/"manifest.json").write_bytes(canonical(m))
    verify(out)
    print("J1.23-A CAPTURE_40_MANIFEST_SHA256",sha(read(out/"manifest.json")),flush=True)
def verify(out,seal=None):
    check()
    manifest=read(out/"manifest.json")
    m=json.loads(manifest)
    need(m.get("schema")==1 and m.get("mission")=="J1.23-A" and
         m.get("base")==BASE and m.get("rom_sha256")==ROM and
         m.get("caprice_commit")==CAPRICE and m.get("image")==IMAGE and
         m.get("cases")==list(CASES) and m.get("sessions")==list(SESSIONS) and
         m.get("status")=="UNSEALED" and m.get("snapshots_archived") is False and
         m.get("native_execution") is False,"PROVENANCE")
    need(ancestor(m.get("acquisition_head")),"FAKE_HEAD")
    wanted=inventory()
    need(set(m["files"])==wanted,"MANIFEST_FILES")
    actual={str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()}
    need(actual==wanted|{"manifest.json"},"ARCHIVE_INVENTORY")
    if seal is not None:
        need(bool(re.fullmatch("[0-9a-f]{64}",seal)) and sha(manifest)==seal,
             "EXTERNAL_MANIFEST_SEAL")
    for p in sorted(wanted):
        need(sha(read(out/p))==m["files"][p],"HASH_"+p)
    ink,png=imports()
    for case in CASES:
        observations=[]
        for sess in SESSIONS:
            d=out/sess/case
            rec=json.loads(read(d/"capture.json"))
            raw=read(d/"program.bin")
            line,rows=ink.cpc.records(raw)
            tok=raw[rows[0]["offset"]+4]
            need(line==[10,20,30] and rec["case"]==case and rec["session"]==sess and
                 rec["source_ascii"]==program(case).decode("ascii") and
                 rec["source_sha256"]==sha(program(case)) and
                 rec["command"]==CASES[case] and rec["program_sha256"]==sha(raw) and
                 rec["program_hex"]==raw.hex(" ").upper() and
                 rec["token_observed_ram"]==tok and
                 rec["token_expected_hypothesis"]==OPCODES[case[0]] and
                 rec["token_hypothesis_matches"]==(tok==OPCODES[case[0]]) and
                 rec["commands"]=={"list":list_commands(case),"run":run_commands(case)} and
                 rec["metadata"]["list"]["commands"]==list_commands(case) and
                 rec["metadata"]["run"]["commands"]==run_commands(case),
                 "RAM_SOURCE_COMMAND_"+case+sess)
            before=read(d/"list/printer.dat")
            printer=read(d/"run/printer.dat")
            parts=printer.splitlines(keepends=True)
            pars=[ink.parse_integer(x) for x in parts[:2]]
            need(len(parts)>=3 and len(pars)==2 and all(x is not None for x in pars) and
                 [x["numeric_value"] for x in pars]==[rec["err"],rec["erl"]] and
                 b"".join(parts[2:])==before and rec["list_sha256"]==sha(before) and
                 rec["printer_sha256"]==sha(printer) and rec["printer_hex"]==printer.hex(),
                 "PRINTER_ERR_ERL_"+case+sess)
            need(rec["screenshots"]=={p:sha(read(d/"run"/p))
                     for p in ("screen_0.png","screen_1.png")} and
                 rec["roi_rgb"]==rgb_evidence(png,d/"run"),"SCREEN_"+case+sess)
            for part in ("list","run"):
                need(read(d/part/"caprice.log").startswith(b"exit code: 0\n"),
                     "CPC_EXIT_"+case+sess+part)
            observations.append((raw,rec["err"],rec["erl"],before,rec))
        a,b=observations
        need(a[:4]==b[:4] and
             a[4]["metadata"]["list"]["started_utc"]!=b[4]["metadata"]["list"]["started_utc"] and
             a[4]["metadata"]["run"]["started_utc"]!=b[4]["metadata"]["run"]["started_utc"],
             "REPEAT_INDEPENDENCE_"+case)
    print("J1.23-A VERIFIED 20_CASES 40_SESSIONS "+
          ("EXTERNAL_SEAL" if seal else "UNSEALED"),flush=True)
def falsifications(out):
    for name,path in [
      ("RAM","original/L_01_01/program.bin"),
      ("LIST","original/B_00/list/printer.dat"),
      ("PNG","repeat/L_02_03/run/screen_1.png"),
      ("MANIFEST","manifest.json")]:
        with tempfile.TemporaryDirectory() as t:
            clone=Path(t)/"data"
            shutil.copytree(out,clone)
            victim=clone/path
            buf=bytearray(read(victim))
            need(bool(buf),"EMPTY_TARGET")
            buf[len(buf)//2]^=1
            victim.write_bytes(buf)
            try: verify(clone)
            except (OracleError,ValueError,KeyError,UnicodeError,IndexError):
                print("J1.23-A FALSIFICATION_REJECTED",name,flush=True)
            else: raise OracleError("FALSIFICATION_ACCEPTED_"+name)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check",action="store_true")
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--acquire",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--head")
    p.add_argument("--verify",type=Path)
    p.add_argument("--external-manifest-sha256")
    a=p.parse_args()
    need(a.check or a.self_test or a.acquire or a.verify,"ACTION_REQUIRED")
    if a.check or a.self_test: check()
    if a.acquire:
        need(a.output is not None and a.verify is None,"ARGUMENTS")
        acquire(a.acquire.resolve(),a.output.resolve(),a.head or "")
    if a.verify:
        verify(a.verify.resolve(),a.external_manifest_sha256)
        if a.self_test: falsifications(a.verify.resolve())
    if a.self_test and not a.verify:
        with tempfile.TemporaryDirectory() as t:
            try: verify(Path(t))
            except OracleError as e: need("ABSENT" in str(e),"FAIL_CLOSED")
            else: raise OracleError("FAKE_ARCHIVE_PASSED")
        print("J1.23-A OFFLINE_FAIL_CLOSED_PASS",flush=True)
if __name__=="__main__":
    try: main()
    except (OracleError,OSError,ValueError,KeyError,IndexError,UnicodeError,
            subprocess.SubprocessError) as e:
        print("J1.23-A FAIL",e,file=sys.stderr)
        sys.exit(1)
