#!/usr/bin/env python3
"""J1.11-B: independent post-B token/flow comparison to sealed CPC6128 J1.11-A.

Only literal PRINT #8,<decimal> in original source is adapted to host PRINT.
CPC printer bytes, host console bytes, CPC error codes and host BE status
are distinct evidence categories. Full program RAM equality is NOT asserted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tests/fixtures/cpc6128/j1_11_gosub_return"
INPUT = ROOT / "tests/oracles/inputs/j1_11_a"
MANIFEST_SHA = "9cc8a9a4e6b40d278e3fe4fd03b7c671f6b8912374135888b074ab42630424c0"
# Independently transcribed from the original CPC J1.11-A observations.
EXPECTED = {
    "F_DIRECT_FORWARD": ([101, 21], 0, 0),
    "F_DIRECT_BACK": ([201, 61], 0, 0),
    "F_REPEAT": ([101, 101, 31], 0, 0),
    "F_NESTED2": ([101, 201, 121, 21], 0, 0),
    "F_LAST_RETURN": ([21], 0, 0),
    "F_MISSING_TARGET": ([], 8, 10),
    "F_UNPAIRED_RETURN": ([], 3, 10),
    "F_END_IN_SUB": ([101], 0, 0),
    "F_RETURN_AFTER_PRINTS": ([101, 111, 21], 0, 0),
    "F_GOTO_IN_SUB": ([121, 21], 0, 0),
    "F_IF_TRUE_DISPATCH": ([101, 61], 0, 0),
    "F_IF_FALSE_DISPATCH": ([101], 0, 0),
    "F_IF_INSIDE_SUB": ([121, 31], 0, 0),
    "F_GOTO_AFTER_RETURN": ([101, 41], 0, 0),
    "F_COLON_CONTINUATION": ([101, 22], 0, 0),
    "F_UNPAIRED_AFTER_CALL": ([101], 3, 20),
}

class DifferentialFailure(ValueError):
    pass

def check(value, message):
    if not value:
        raise DifferentialFailure(message)

def read(path):
    check(path.is_file() and not path.is_symlink(), "MISSING " + str(path))
    return path.read_bytes()

def sha(value):
    return hashlib.sha256(value).hexdigest()

def run(exe, source, label):
    try:
        result = subprocess.run([str(exe)], input=source, capture_output=True,
                                timeout=40, check=False)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise DifferentialFailure(label + ": PROCESS_FAILED " + str(err)) from err
    check(result.returncode == 0, label + " EXIT " + str(result.returncode) +
          " stderr=" + repr(result.stderr[-600:]))
    return result

def records(program):
    check(program.endswith(b"\0\0"), "INVALID_SENTINEL")
    offset = 0
    found = {}
    while offset < len(program) - 2:
        check(offset + 5 <= len(program) - 2, "TRUNCATED_HEADER")
        n = int.from_bytes(program[offset:offset+2], "little")
        check(5 <= n <= len(program)-2-offset, "INVALID_RECORD_LENGTH")
        raw = program[offset:offset+n]
        check(raw[-1] == 0, "INVALID_RECORD_TERMINATOR")
        line = int.from_bytes(raw[2:4], "little")
        check(line not in found, "DUPLICATE_LINE")
        found[line] = raw
        offset += n
    check(offset == len(program)-2, "INVALID_RECORD_BOUNDARY")
    return found

def control_records(program):
    result = {}
    for line, raw in records(program).items():
        body = raw[4:-1].lstrip(b" ")
        if body.startswith((b"\x9f", b"\xc9")):
            result[line] = raw
    return result

def compare_controls(cpc, native, label):
    a, b = control_records(cpc), control_records(native)
    check(a and set(a) == set(b), label + " CONTROL_LINE_SET")
    semantic = 0
    for line, raw in a.items():
        actual = b[line]
        # CPC PRINT #8 has different source tokens from host PRINT;
        # a colon suffix can only be compared before the separator.
        if b"\x01" in raw[4:-1]:
            cpc_prefix = raw[4:-1].split(b"\x01",1)[0]
            native_prefix = actual[4:-1].split(b"\x01",1)[0]
            check(cpc_prefix == native_prefix, label + " COLON_PREFIX_DIFF " + str(line))
            check(actual[4:-1].count(b"\x01") == 1,
                  label + " COLON_DELIMITER_DIFFERENCE")
            semantic += 1
        else:
            check(raw == actual, label + " CONTROL_RECORD_DIFF " + str(line) +
                  " CPC=" + raw.hex(" ") + " HOST=" + actual.hex(" "))
    return len(a), semantic

def adapted(source, label):
    text = source.decode("ascii")
    # Strictly the permitted numeric printer calls. No source lines or other
    # PRINT targets are rewritten, and the CPC source remains read-only.
    def sub(match):
        return "PRINT " + match.group(1)
    transformed, n = re.subn(r"PRINT #8,([0-9]+)(?![0-9A-Za-z_])", sub, text)
    check(n > 0, label + " NO_NUMERIC_PRINTER_ADAPTATION")
    check("PRINT #8" not in transformed, label + " NON_LITERAL_PRINTER_SYNTAX")
    return transformed.encode("ascii")

def permanent_manifest():
    raw = read(BASE / "manifest.json")
    check(sha(raw) == MANIFEST_SHA, "J1_11_A_MANIFEST_CHANGED")
    manifest = json.loads(raw)
    captures = manifest["captures"]
    check(manifest["phase"] == "J1.11-A" and len(captures) == 16 and
          set(c["case"] for c in captures) == set(EXPECTED),
          "ORACLE_SET_CHANGED")
    for item in captures:
        name = item["case"]
        t, err, erl = EXPECTED[name]
        check(item["ram_exact_2of2"] and item["printer_exact_2of2"] and
              item["original"]["pre_run"]["comparison"]["classification"] == "UNSUPPORTED" and
              item["original"]["run"]["program_trace"] == t and
              item["original"]["run"]["err_probe"] == err and
              item["original"]["run"]["erl_probe"] == erl,
              name + " SEALED_CPC_OBSERVATION_CHANGED")
    return captures

def permanent_oracle():
    gate = subprocess.run([sys.executable, str(ROOT/"tools/j1_11_gosub_return_verify.py"),
                           "--permanent","--self-test"], capture_output=True,
                          check=False, timeout=240)
    check(gate.returncode == 0, "PERMANENT_CPC_GATE_FAILED " +
          repr(gate.stderr[-1000:]))
    print("PASS original J1.11-A permanent gate and falsification",flush=True)

def verify(item, cli, image):
    name = item["case"]
    source = read(INPUT/(name.lower()+".bas"))
    check(sha(source) == item["source_sha256"] and
          source == read(BASE/"original"/name/"original.bas"),
          name + " SOURCE_CHANGED")
    cpc = read(BASE/"original"/name/"program.bin")
    check(sha(cpc) == item["original"]["pre_run"]["comparison"]["cpc_sha256"],
          name + " CPC_RAM_CHANGED")
    host = adapted(source,name)
    image_bytes = run(image,host,name+"/IMAGE").stdout
    matched, semantic = compare_controls(cpc,image_bytes,name)
    listed = run(cli,host+b"LIST\n:quit\n",name+"/LIST")
    check(listed.stdout == host and b"[cli:error]" not in listed.stderr,
          name + " NATIVE_LIST_ROUNDTRIP_FAILED " + repr(listed.stdout))
    executed = run(cli,host+b"RUN\n:step 100\n:quit\n",name+"/RUN")
    try:
        trace = [int(v.strip()) for v in executed.stdout.splitlines()]
    except ValueError as exc:
        raise DifferentialFailure(name + " HOST_NON_NUMERIC " +
                                  repr(executed.stdout)) from exc
    expected, cpc_err, cpc_erl = EXPECTED[name]
    check(trace == expected, name + " TRACE_DIFFERENT CPC=" +
          repr(expected) + " HOST=" + repr(trace))
    if cpc_err:
        check(b"[cli:error] BSR_EXECUTOR_ERROR" in executed.stderr and
              b"[cli] END\n" not in executed.stderr,
              name + " EXPECTED_HOST_ERROR_NOT_REPORTED")
    else:
        check(b"[cli] END\n" in executed.stderr and
              b"[cli:error]" not in executed.stderr,
              name + " UNEXPECTED_HOST_ERROR_OR_MISSING_END")
    classification = "MATCH_SEMANTIC" if semantic else "MATCH_EXACT"
    print("PASS",name,classification,
          "CONTROL_RECORDS="+str(matched),"CPC_ERR="+str(cpc_err),
          "CPC_ERL="+str(cpc_erl),"TRACE="+repr(trace),flush=True)
    return classification

def self_test():
    raw = bytes.fromhex("0a 00 0a 00 9f 20 1e 64 00 00 00 00")
    changed = bytearray(raw)
    changed[7] ^= 1
    try:
        compare_controls(raw,bytes(changed),"FALSIFIED_TOKEN")
    except DifferentialFailure:
        pass
    else:
        raise DifferentialFailure("CONTROL_BYTE_FALSIFICATION_ACCEPTED")
    try:
        check([101,22] == [101,23],"FALSIFIED_TRACE")
    except DifferentialFailure:
        pass
    else:
        raise DifferentialFailure("TRACE_FALSIFICATION_ACCEPTED")
    print("PASS controls and numeric-trace falsifications",flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli",type=Path,required=True)
    ap.add_argument("--image-cli",type=Path,required=True)
    ap.add_argument("--self-test",action="store_true")
    args = ap.parse_args()
    captures = permanent_manifest()
    permanent_oracle()
    classifications = [verify(c,args.cli,args.image_cli) for c in captures]
    check(len(classifications)==16 and all(x in ("MATCH_EXACT","MATCH_SEMANTIC")
                                           for x in classifications),
          "NOT_ALL_16_CASES_EVALUATED")
    if args.self_test:
        self_test()
    print("PASS J1.11-B 16/16 CPC semantic control/trace comparisons;"
          " original pre-B UNSUPPORTED preserved;"
          " FULL_RAM_NOT_CLAIMED PRINTER_BYTES_NOT_CLAIMED",flush=True)

if __name__=="__main__":
    try:
        main()
    except (DifferentialFailure,OSError,KeyError,UnicodeError,ValueError) as err:
        print("FAIL J1.11-B:",str(err),file=sys.stderr)
        sys.exit(1)
