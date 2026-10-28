#!/usr/bin/env python3
"""J1.14-B: original ROM-backed IF line 30 byte-exact, native branch semantic.
Historical J1.14-A pre-B UNSUPPORTED classifications remain unchanged.
PRINT #8,C% is adapted ONLY on BASIC line 40 and ONLY in host memory.
No false claim of whole-program image or CPC-printer/stdout equality.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "tests/fixtures/cpc6128/j1_14_if_inline_else"
PIN = "dc1b30dee67d7bd9c9e5ac2db17bdb84730d48d41fec8d64924a1d2d4c6e0ec1"

class Failure(ValueError):
    pass

def require(condition, label):
    if not condition:
        raise Failure(label)

def read(path):
    require(path.is_file() and not path.is_symlink(), "MISSING "+str(path))
    return path.read_bytes()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def records(image, label):
    require(image.endswith(b"\x00\x00"), label+" SENTINEL")
    pos = 0
    end = len(image)-2
    rows = {}
    while pos < end:
        require(end-pos >= 5, label+" SHORT_HEADER")
        size = int.from_bytes(image[pos:pos+2],"little")
        number = int.from_bytes(image[pos+2:pos+4],"little")
        require(5 <= size <= end-pos and number not in rows,
                label+" BAD_RECORD")
        raw = image[pos:pos+size]
        require(raw[-1:] == b"\x00", label+" BAD_TERMINATOR")
        rows[number] = raw
        pos += size
    require(pos == end, label+" RECORD_END")
    return rows

def exact_record(cpc, native, expected, name):
    a = records(cpc, name+" CPC")[30]
    b = records(native, name+" NATIVE")[30]
    require(a == bytes.fromhex(expected), name+" ORIGINAL_RECORD_CHANGED")
    require(a == b, name+" IF_LINE_30_DIFF CPC="+a.hex(" ")+
            " C99="+b.hex(" "))
    return a

def adapted(source, name):
    lines = source.decode("ascii").splitlines(keepends=True)
    replaced = []
    count = 0
    for line in lines:
        if line == "40 PRINT #8,C%\n":
            replaced.append("40 PRINT C%\n")
            count += 1
        else:
            require("PRINT #8" not in line, name+" ILLEGAL_PRINTER_EDIT")
            replaced.append(line)
    require(count == 1, name+" PRINTER_NOT_LINE40")
    result = "".join(replaced).encode("ascii")
    require([s for s in source.splitlines() if s.startswith(b"30 ")] ==
            [s for s in result.splitlines() if s.startswith(b"30 ")],
            name+" IF_SOURCE_EDITED")
    return result

def process(exe, input_bytes, name):
    try:
        p = subprocess.run([str(exe)], input=input_bytes, capture_output=True,
                           timeout=40, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failure(name+" PROCESS "+str(exc)) from exc
    require(p.returncode == 0, name+" RETURN "+str(p.returncode)+
            " STDERR "+repr(p.stderr[-600:]))
    return p

def head_guard(actual, claimed):
    require(actual == claimed, "FALSE_HEAD")

def preflight():
    require(sha(read(ARCHIVE/"manifest.json")) == PIN, "ORIGINAL_MANIFEST_SHA")
    m = json.loads(read(ARCHIVE/"manifest.json"))
    seal = json.loads(read(ARCHIVE/"seal.json"))
    names = m["mandatory_cases"]
    require(m["phase"] == "J1.14-A" and
            len(names) == len(m["captures"]) == 24 and
            len(set(names)) == 24 and
            seal["manifest_sha256"] == PIN and
            len(m["exploratory_cases"]) == 6 and
            len(m["explorations"]) == 6, "HISTORICAL_CASE_SET")
    require(m["j1_14_b_authorized"] is False,
            "PRE_B_HISTORICAL_CLASSIFICATION_CHANGED")
    for cap in m["captures"]:
        name=cap["case"]
        source=read(ROOT/cap["source_path"])
        cpc=read(ARCHIVE/"original"/name/"program.bin")
        second=read(ARCHIVE/"repeat"/name/"program.bin")
        printer=read(ARCHIVE/"original"/name/"run"/"printer.dat")
        printer2=read(ARCHIVE/"repeat"/name/"run"/"printer.dat")
        ref=cap["original"]
        require(sha(source) == cap["source_sha256"] and
                source == read(ARCHIVE/"original"/name/"original.bas") and
                cpc == second and printer == printer2 and
                sha(cpc) == seal["program_sha256"][name] and
                sha(printer) == seal["printer_sha256"][name] and
                ref["pre_run"]["comparison"]["classification"] == "UNSUPPORTED" and
                ref["run"]["result_class"] == "OBSERVED" and
                ref["run"]["err_probe"] == ref["run"]["erl_probe"] == 0 and
                len(ref["pre_run"]["if_records"]) == 1 and
                ref["pre_run"]["if_records"][0]["line_number"] == 30 and
                len(ref["run"]["program_trace"]) == 1 and
                ref["run"]["program_trace"][0] in (42,81),
                name+" ORIGINAL_CPC_PROVENANCE")
    return m["captures"]

def compare_trace(actual, expected, name):
    require(actual == expected, name+" BRANCH_SEMANTIC_MISMATCH")

def one(cap, cli, image_cli):
    name=cap["case"]
    original=read(ROOT/cap["source_path"])
    cpc_image=read(ARCHIVE/"original"/name/"program.bin")
    host=adapted(original,name)
    image=process(image_cli,host,name+" IMAGE").stdout
    expected=cap["original"]["pre_run"]["if_records"][0]["record_hex"]
    raw=exact_record(cpc_image,image,expected,name)
    require(raw[4] == 0xa1 and b"\xeb" in raw,
            name+" NOT_CPC_IF")
    listing=process(cli,host+b"LIST\n:quit\n",name+" LIST")
    require(b"[cli:error]" not in listing.stderr and listing.stdout == host,
            name+" LIST_DIFFERENT "+repr(listing.stdout[-200:]))
    new_image=process(image_cli,listing.stdout,name+" RETOKEN").stdout
    require(records(new_image,name+" LIST_ROUNDTRIP")[30] == raw,
            name+" LIST_RETOKEN_RECORD_30")
    run=process(cli,host+b"RUN\n:step 100\n:quit\n",name+" EXECUTE")
    require(b"[cli:error]" not in run.stderr and
            b"[cli] END" in run.stderr,
            name+" EXECUTION_FAILED "+repr(run.stderr[-300:]))
    lines=run.stdout.splitlines()
    require(len(lines)==1 and re.fullmatch(rb"\s*(42|81)\s*",lines[0]),
            name+" HOST_STDOUT_INVALID "+repr(run.stdout))
    observed=int(lines[0].strip())
    expected_value=cap["original"]["run"]["program_trace"][0]
    compare_trace(observed,expected_value,name)
    print("J1.14-B",name,"MATCH_EXACT_RECORD_30",
          "MATCH_SEMANTIC_BRANCH",observed,flush=True)

def self_test():
    sample=bytes.fromhex("15 00 1e 00 a1 20 02 00 00 c1 20 eb 20 02 00 00 c3 ef 19 51 00")
    image=sample+b"\x00\x00"
    corrupt=bytearray(image)
    corrupt[18]^=1
    try:
        exact_record(image,bytes(corrupt),sample.hex(" "),"TAMPER")
    except Failure:
        pass
    else:
        raise Failure("TAMPER_RECORD_ACCEPTED")
    try:
        head_guard("f"*40,"0"*40)
    except Failure:
        pass
    else:
        raise Failure("TAMPER_HEAD_ACCEPTED")
    try:
        compare_trace(42,81,"TAMPER")
    except Failure:
        pass
    else:
        raise Failure("TAMPER_TRACE_ACCEPTED")
    try:
        adapted(b"30 IF A% THEN C%=81\n40 PRINT #8,81\n","TAMPER")
    except Failure:
        pass
    else:
        raise Failure("TAMPER_ADAPTATION_ACCEPTED")
    require(sha(b"manipulated") != PIN,"TAMPER_MANIFEST_ACCEPTED")
    print("PASS J1.14-B 5 DIFFERENTIAL FALSIFICATIONS",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cli",type=Path,required=True)
    p.add_argument("--image-cli",type=Path,required=True)
    p.add_argument("--expected-head")
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    if args.expected_head:
        result=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                              capture_output=True,text=True,check=True)
        head_guard(result.stdout.strip(),args.expected_head)
    if args.self_test:
        self_test()
    for cap in preflight():
        one(cap,args.cli,args.image_cli)
    print("PASS J1.14-B 24/24 MATCH_EXACT_RECORD_30")
    print("PASS J1.14-B 24/24 MATCH_SEMANTIC_BRANCH")
    print("CPC_PRINTER_VS_HOST_STDOUT: semantic number ONLY, never byte-exact")
    print("J1.14-A pre-B 24/24 UNSUPPORTED remains sealed; 6 explorations excluded")

if __name__=="__main__":
    try:
        main()
    except (Failure,ValueError,OSError,UnicodeError,KeyError,
            subprocess.CalledProcessError) as exc:
        print("FAIL J1.14-B:",exc,file=sys.stderr)
        sys.exit(1)
