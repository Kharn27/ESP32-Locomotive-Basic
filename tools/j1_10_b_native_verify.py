#!/usr/bin/env python3
"""J1.10-B: post-implementation native IF checked against sealed CPC6128 ROM.

Only PRINT #8,<decimal> in the ORIGINAL CPC sources is adapted to PRINT
<decimal> for the host runtime. Full program.bin is intentionally not claimed
MATCH_EXACT. Instead compare every IF record byte-for-byte (including caches)
and program numeric traces against independent, immutable J1.10-A anchors.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "tests/fixtures/cpc6128/j1_10_if_then"
SOURCES = ROOT / "tests/oracles/inputs/j1_10_a"
MANIFEST_SHA = "4439054c55c9422aba315c3e5e4cc4303c38b34c4b1f2f13ba56e60f69661796"
# (numeric program trace, original CPC ERR, original CPC ERL). Independently
# transcribed from the sealed J1.10-A CPC measurements, never native C output.
EXPECTED = {
    "F_ZERO_FORWARD": ([31], 0, 0),
    "F_ONE_FORWARD": ([61], 0, 0),
    "F_NEGONE_FORWARD": ([61], 0, 0),
    "F_NMIN_FORWARD": ([61], 0, 0),
    "F_PMAX_FORWARD": ([61], 0, 0),
    "F_FALSE_MISSING": ([31], 0, 0),
    "F_TRUE_MISSING": ([], 8, 20),
    "F_TRUE_SKIP_TWO": ([71], 0, 0),
    "F_FALSE_TWO_PRINT": ([31, 41], 0, 0),
    "F_TRUE_BACK": ([71, 31], 0, 0),
    "F_TRUE_TARGET_END": ([], 0, 0),
    "F_FALSE_TARGET_END": ([31], 0, 0),
    "F_TRUE_AFTER_PRINT": ([21, 71], 0, 0),
    "F_ZERO_AFTER_PRINT": ([21, 41], 0, 0),
}


class Mismatch(ValueError):
    pass


def require(test, message):
    if not test:
        raise Mismatch(message)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink(), "MISSING " + str(path))
    return path.read_bytes()


def process(executable, content, label):
    try:
        run = subprocess.run([str(executable)], input=content,
                             capture_output=True, check=False, timeout=40)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Mismatch(label + " PROCESS_FAILED " + str(exc)) from exc
    require(run.returncode == 0,
            label + " EXIT=" + str(run.returncode) +
            " stderr=" + repr(run.stderr[-500:]))
    return run


def records(program):
    require(program.endswith(b"\x00\x00"), "MISSING_SENTINEL")
    result = {}
    offset = 0
    end = len(program) - 2
    while offset < end:
        require(end - offset >= 5, "TRUNCATED_RECORD")
        length = int.from_bytes(program[offset:offset+2], "little")
        require(5 <= length <= end-offset, "INVALID_RECORD_LENGTH")
        raw = program[offset:offset+length]
        require(raw[-1] == 0 and raw[4] != 0, "BAD_RECORD_END")
        number = int.from_bytes(raw[2:4], "little")
        require(number not in result, "DUPLICATE_LINE")
        result[number] = raw
        offset += length
    require(offset == end, "BAD_RECORD_BOUNDARY")
    return result


def if_records(program):
    # The sealed J1.10-A sources have IF as the sole statement on its line.
    return {n: raw for n, raw in records(program).items()
            if raw[4:-1].lstrip(b" ").startswith(b"\xa1")}


def compare_if(actual, expected):
    require(set(actual) == set(expected) and len(actual) > 0,
            "IF_LINE_SET_MISMATCH")
    for number in expected:
        require(actual[number] == expected[number],
                "IF_RECORD_MISMATCH line=" + str(number) +
                " native=" + actual[number].hex(" ") +
                " cpc=" + expected[number].hex(" "))


def adapted(raw, name):
    lines = raw.decode("ascii").splitlines()
    replaced = []
    changes = 0
    for line in lines:
        match = re.fullmatch(r"([1-9][0-9]*) PRINT #8,([0-9]+)", line)
        if match:
            replaced.append(match.group(1) + " PRINT " + match.group(2))
            changes += 1
        else:
            require("PRINT #8" not in line,
                    name + " UNHANDLED_PRINTER_SOURCE " + line)
            replaced.append(line)
    require(changes >= 1, name + " NO_PRINTER_ADAPTATION")
    return ("\n".join(replaced) + "\n").encode("ascii")


def original_manifest():
    raw = read(ARCHIVE / "manifest.json")
    require(sha(raw) == MANIFEST_SHA, "ORIGINAL_MANIFEST_CHANGED")
    manifest = json.loads(raw)
    captures = manifest["captures"]
    require(manifest["phase"] == "J1.10-A" and
            len(captures) == 14 and
            set(x["case"] for x in captures) == set(EXPECTED),
            "ORIGINAL_CAPTURE_SET_CHANGED")
    for case in captures:
        name = case["case"]
        trace, err, erl = EXPECTED[name]
        original = case["original"]
        require(case["ram_exact_2of2"] and case["printer_exact_2of2"] and
                original["pre_run"]["comparison"]["classification"] ==
                "UNSUPPORTED" and
                original["run"]["program_trace"] == trace and
                original["run"]["err_probe"] == err and
                original["run"]["erl_probe"] == erl,
                name + " HISTORICAL_RESULT_CHANGED")
    return captures


def permanent():
    check = subprocess.run(
        [sys.executable, str(ROOT / "tools/j1_10_if_then_verify.py"),
         "--permanent", "--self-test"],
        capture_output=True, check=False, timeout=240)
    require(check.returncode == 0, "ORIGINAL_ORACLE_PERMANENCE_FAILED " +
            repr(check.stderr[-1000:]))
    print("PASS immutable J1.10-A oracle --permanent --self-test", flush=True)


def case_verify(case, cli, image_cli):
    name = case["case"]
    original = case["original"]
    source = read(SOURCES / (name.lower() + ".bas"))
    require(sha(source) == case["source_sha256"] and
            source == read(ARCHIVE / "original" / name / "original.bas"),
            name + " ORIGINAL_SOURCE_CHANGED")
    cpc_program = read(ARCHIVE / "original" / name / "program.bin")
    require(sha(cpc_program) ==
            original["pre_run"]["comparison"]["cpc_sha256"],
            name + " ORIGINAL_RAM_CHANGED")
    rewritten = adapted(source, name)
    native_program = process(image_cli, rewritten, name + "/IMAGE").stdout
    real = if_records(native_program)
    measured = if_records(cpc_program)
    compare_if(real, measured)
    require(len(real) == (2 if name == "F_TRUE_BACK" else 1),
            name + " IF_COUNT_CHANGED")
    for num, raw in measured.items():
        if num == original["pre_run"]["if_line_number"]:
            require(raw.hex(" ").upper() ==
                    original["pre_run"]["if_line_raw_hex"],
                    name + " ORIGINAL_IF_RECORD_CHANGED")
    listed = process(cli, rewritten+b"LIST\n:quit\n", name + "/LIST")
    require(listed.stdout == rewritten and b"[cli:error]" not in listed.stderr,
            name + " ADAPTED_LIST_MISMATCH")
    executed = process(cli, rewritten+b"RUN\n:step 100\n:quit\n", name + "/RUN")
    expected_trace, err, erl = EXPECTED[name]
    try:
        trace = [int(line.strip()) for line in executed.stdout.splitlines()]
    except ValueError as exc:
        raise Mismatch(name + " NON_NUMERIC_OUTPUT " +
                       repr(executed.stdout)) from exc
    require(trace == expected_trace,
            name + " TRACE_DIFFERENT native=" + repr(trace) +
            " cpc=" + repr(expected_trace))
    if err == 8:
        require(erl == 20 and
                b"BE_MISSING_TARGET" in executed.stderr and
                b"[cli] END\n" not in executed.stderr,
                name + " HOST_MISSING_TARGET_NOT_OBSERVED")
    else:
        require(err == 0 and erl == 0 and
                b"[cli] END\n" in executed.stderr and
                b"[cli:error]" not in executed.stderr,
                name + " HOST_END_OR_ERROR_MISMATCH")
    print("PASS", name, "IF_RECORD_MATCH_EXACT",
          "TRACE=" + repr(trace), "CPC_ERR=" + str(err),
          "CPC_ERL=" + str(erl), flush=True)


def falsifications():
    sample = {20: bytes.fromhex(
        "11 00 14 00 A1 20 02 00 00 C1 20 EB 20 1E 3C 00 00")}
    tampered = dict(sample)
    broken = bytearray(sample[20])
    broken[7] ^= 1  # IF cache/reference field is not skippable
    tampered[20] = bytes(broken)
    rejected = False
    try:
        compare_if(tampered, sample)
    except Mismatch:
        rejected = True
    require(rejected, "IF_BYTE_FALSIFICATION_NOT_REJECTED")
    wrong = dict(EXPECTED)
    wrong["F_ONE_FORWARD"] = ([31], 0, 0)
    rejected = False
    try:
        require(wrong["F_ONE_FORWARD"] ==
                (EXPECTED["F_ONE_FORWARD"][0],
                 EXPECTED["F_ONE_FORWARD"][1],
                 EXPECTED["F_ONE_FORWARD"][2]),
                "TRACE_FALSIFICATION")
    except Mismatch:
        rejected = True
    require(rejected, "TRACE_FALSIFICATION_NOT_REJECTED")
    print("PASS independent IF-byte and pinned trace falsifications", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", type=Path, required=True)
    ap.add_argument("--image-cli", type=Path, required=True)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    captures = original_manifest()
    permanent()
    for case in captures:
        case_verify(case, args.cli, args.image_cli)
    if args.self_test:
        falsifications()
    print("PASS J1.10-B post-B 14/14 CPC IF records and numerical traces",
          "full_program_RAM_NOT_CLAIMED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (Mismatch, OSError, ValueError, KeyError) as exc:
        print("FAIL J1.10-B:", str(exc), file=sys.stderr)
        sys.exit(1)
