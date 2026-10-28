#!/usr/bin/env python3
"""J1.12-B2: compare bounded numeric runtime traces against sealed CPC captures.
No historical image/source is rewritten and no host ERR/ERL is invented.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from j1_12_b1_native_verify import BASE, ROOT, MANIFEST_SHA, adapt, preflight, read, require, DifferentialFailure

ERRORS = {"F_NEXT_ORPHAN": ("BE_NEXT_WITHOUT_FOR", 20),
          "F_NEXT_WRONG_VAR": ("BE_NEXT_VARIABLE_MISMATCH", 30)}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def head_guard(actual, expected):
    require(actual == expected, "FALSE_HEAD checkout=" + actual + " expected=" + expected)

def oracle(case, cap, seal):
    raw = read(BASE / "original" / case / "run" / "printer.dat")
    require(digest(raw) == seal["printer_sha256"][case], case + " PRINTER_SHA_CHANGED")
    expected = cap["original"]["run"]
    require(digest(bytes.fromhex(expected["printer_raw_hex"])) == digest(raw),
            case + " PRINTER_RECORD_DIFF")
    require(expected["result_class"] == "OBSERVED" and
            cap["two_independent_process_pairs"] and
            cap["ram_exact_2of2"] and cap["printer_exact_2of2"],
            case + " INDEPENDENCE_CHANGED")
    trace = expected["program_trace"]
    if case in ERRORS:
        require(expected["err_probe"] == 1 and
                expected["erl_probe"] == ERRORS[case][1],
                case + " CPC_ERROR_PROBE_CHANGED")
    else:
        require(expected["err_probe"] == 0 and expected["erl_probe"] == 0,
                case + " CPC_UNEXPECTED_ERROR")
    return trace

def execute(cli, source, case):
    adapted = adapt(source, case)
    try:
        r = subprocess.run([str(cli)], input=adapted + b"RUN\n:step 100\n:quit\n",
                           capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise DifferentialFailure(case + " PROCESS " + str(e)) from e
    require(r.returncode == 0, case + " CLI_EXIT " + str(r.returncode))
    trace = []
    for line in r.stdout.splitlines():
        require(re.fullmatch(rb"[ \t]*-?[0-9]+[ \t]*", line) is not None,
                case + " INVALID_NUMERIC_OUTPUT " + repr(line))
        trace.append(int(line.strip()))
    diagnostic = re.findall(rb"\[cli:error\] BSR_EXECUTOR_ERROR[^\r\n]*", r.stderr)
    require(len(diagnostic) <= 1, case + " MULTIPLE_DIAGNOSTICS")
    diag = diagnostic[0].decode("ascii") if diagnostic else ""
    other = r.stderr.count(b"[cli:error]")
    require(other == len(diagnostic), case + " EXTRA_HOST_ERROR")
    return trace, diag

def compare(case, expected, got, diag):
    host_error = ERRORS.get(case)
    require(got == expected, case + " DIFF TRACE CPC=" + repr(expected) +
            " HOST=" + repr(got))
    if host_error:
        require(host_error[0] in diag, case + " DIFF DIAGNOSTIC " + diag)
    else:
        require(not diag, case + " DIFF UNEXPECTED_DIAGNOSTIC " + diag)
    print("J1.12-B2", case, "MATCH_SEMANTIC", "CPC=" + repr(expected),
          "HOST=" + repr(got), "HOST_DIAG=" + (host_error[0] if host_error else "NONE"),
          "CPC_ERR_ERL=" + ("1/" + str(host_error[1]) if host_error else "0/0"))

def self_test():
    for name, action in [
        ("TRACE", lambda: compare("F_POS_IMPLICIT_ONE", [1], [2], "")),
        ("ERROR", lambda: compare("F_NEXT_WRONG_VAR", [], [], "")),
        ("HEAD", lambda: head_guard("wrong", "genuine")),
    ]:
        try:
            action()
        except DifferentialFailure:
            pass
        else:
            raise DifferentialFailure("FALSIFICATION_" + name + "_NOT_REJECTED")
    # Fingerprint guards are checked with mutated in-memory copies, not archives.
    seal = json.loads(read(BASE / "seal.json"))
    manifest = read(BASE / "manifest.json")
    require(digest(manifest) == MANIFEST_SHA, "ORACLE_MANIFEST_CHANGED")
    require(digest(manifest + b"x") != MANIFEST_SHA, "MANIFEST_FALSIFICATION_FAILED")
    case = "F_POS_IMPLICIT_ONE"
    for kind in ("program_sha256", "printer_sha256"):
        path = (BASE / "original" / case /
                ("program.bin" if kind == "program_sha256" else "run/printer.dat"))
        raw = read(path)
        require(digest(raw) == seal[kind][case] and
                digest(raw + b"x") != seal[kind][case],
                kind + " FALSIFICATION_FAILED")
    print("PASS J1.12-B2 FALSIFICATIONS TRACE ERROR HEAD MANIFEST RAM PRINTER")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cli", required=True, type=Path)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--expected-head", default=None)
    args = p.parse_args()
    if args.self_test: self_test()
    if args.expected_head:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True, check=True)
        head_guard(result.stdout.strip(), args.expected_head)
    cases, captures = preflight()
    seal = json.loads(read(BASE / "seal.json"))
    require(seal["manifest_sha256"] == MANIFEST_SHA and
            set(seal["printer_sha256"]) == set(cases),
            "ORACLE_PRINTER_SEAL_CHANGED")
    for case in cases:
        cap = captures[case]
        expected = oracle(case, cap, seal)
        got, diag = execute(args.cli, read(ROOT / cap["source_path"]), case)
        compare(case, expected, got, diag)
    print("PASS J1.12-B2 20/20 MATCH_SEMANTIC (numeric trace + terminal error class)")
    print("CPC ERR/ERL are reference-only; host BE_* are not CPC error codes")

if __name__ == "__main__":
    try:
        main()
    except (DifferentialFailure, ValueError, KeyError, UnicodeError) as exc:
        print("J1.12-B2 DIFF:", exc, file=sys.stderr)
        raise SystemExit(1) from exc
