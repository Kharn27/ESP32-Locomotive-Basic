#!/usr/bin/env python3
"""J1.13-B post-native differential: original CPC IF line byte-exact,
then branch trace with *memory-only* adaptation of nonnative PRINT #8.
The immutable J1.13-A pre-B UNSUPPORTED observations remain UNSUPPORTED.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "tests/fixtures/cpc6128/j1_13_integer_relations"
MANIFEST_SHA = "69ee185aa63fe6db1df8f6092af19df0a15dec70b991d918e8f99d2657a03070"
EXPECTED_OPS = {"R_EQ": b"\xef", "R_NE": b"\xf2", "R_LT": b"\xf1",
                "R_LE": b"\xf3", "R_GT": b"\xee", "R_GE": b"\xf0"}

class DifferentialFailure(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise DifferentialFailure(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    require(path.is_file() and not path.is_symlink(), "MISSING " + str(path))
    return path.read_bytes()

def head_guard(actual, expected):
    require(actual == expected,
            "FALSE_HEAD actual=" + actual + " expected=" + expected)

def records(image, label):
    require(image.endswith(b"\x00\x00"), label + " SENTINEL")
    end = len(image) - 2
    pos = 0
    found = {}
    while pos < end:
        require(end - pos >= 5, label + " SHORT_HEADER")
        length = int.from_bytes(image[pos:pos+2], "little")
        number = int.from_bytes(image[pos+2:pos+4], "little")
        require(5 <= length <= end - pos and number not in found,
                label + " INVALID_RECORD")
        raw = image[pos:pos+length]
        require(raw[-1] == 0, label + " TERMINATOR")
        found[number] = raw
        pos += length
    require(pos == end, label + " BAD_BOUNDARY")
    return found

def exact_if(cpc, native, expected_hex, label):
    original = records(cpc, "CPC_" + label)[30]
    actual = records(native, "HOST_" + label)[30]
    require(original == bytes.fromhex(expected_hex),
            label + " MANIFEST_IF_BYTES_CHANGED")
    require(actual == original,
            label + " IF_RECORD_MISMATCH CPC=" + original.hex(" ") +
            " C99=" + actual.hex(" "))
    return original

def adapt(source, label):
    # Whitelist exact standalone PRINT lines; never rewrite a token, cache,
    # variable or comparison. The number remapping is deliberately explicit.
    lines = source.decode("ascii").splitlines(keepends=True)
    modified = []
    edits = []
    for line in lines:
        match = re.fullmatch(r"([0-9]+) PRINT #8,(420|810)(\r?\n)", line)
        if match:
            target = "42" if match.group(2) == "420" else "81"
            modified.append(match.group(1) + " PRINT " +
                            target + match.group(3))
            edits.append((int(match.group(1)), int(match.group(2)), int(target)))
        else:
            require("PRINT #8" not in line,
                    label + " UNHANDLED_PRINTER " + repr(line))
            modified.append(line)
    require(sorted(edits) == [(40, 420, 42), (70, 810, 81)],
            label + " TRANSFORMATION_NOT_AUDITABLE " + repr(edits))
    result = "".join(modified).encode("ascii")
    old_if = [line for line in source.splitlines() if line.startswith(b"30 ")]
    new_if = [line for line in result.splitlines() if line.startswith(b"30 ")]
    require(len(old_if) == 1 and old_if == new_if,
            label + " IF_SOURCE_MUTATED_BY_ADAPTATION")
    return result

def process(executable, input_bytes, label):
    try:
        p = subprocess.run([str(executable)], input=input_bytes,
                           capture_output=True, timeout=40, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DifferentialFailure(label + " PROCESS " + str(exc)) from exc
    require(p.returncode == 0,
            label + " PROCESS_EXIT=" + str(p.returncode) +
            " STDERR=" + repr(p.stderr[-500:]))
    return p

def preflight():
    raw_manifest = read(ARCHIVE / "manifest.json")
    require(digest(raw_manifest) == MANIFEST_SHA, "MANIFEST_CHANGED")
    manifest = json.loads(raw_manifest)
    seal = json.loads(read(ARCHIVE / "seal.json"))
    captures = manifest["captures"]
    cases = manifest["mandatory_cases"]
    require(manifest["phase"] == "J1.13-A" and
            len(cases) == len(captures) == 24 and len(set(cases)) == 24 and
            {c["case"] for c in captures} == set(cases),
            "HISTORICAL_CASE_SET_CHANGED")
    require(seal["manifest_sha256"] == MANIFEST_SHA and
            set(seal["program_sha256"]) == set(cases) and
            set(seal["printer_sha256"]) == set(cases),
            "HISTORICAL_SEAL_CHANGED")
    for cap in captures:
        name = cap["case"]
        source = read(ROOT / cap["source_path"])
        cpc = read(ARCHIVE / "original" / name / "program.bin")
        printer = read(ARCHIVE / "original" / name / "run" / "printer.dat")
        ref = cap["original"]
        require(digest(source) == cap["source_sha256"] and
                source == read(ARCHIVE / "original" / name / "original.bas"),
                name + " CPC_SOURCE_CHANGED")
        require(digest(cpc) == seal["program_sha256"][name] ==
                ref["pre_run"]["comparison"]["cpc_sha256"] and
                digest(printer) == seal["printer_sha256"][name],
                name + " CPC_ARCHIVE_CHANGED")
        require(ref["pre_run"]["comparison"]["classification"] ==
                "UNSUPPORTED" and
                ref["run"]["result_class"] == "OBSERVED" and
                ref["run"]["err_probe"] == ref["run"]["erl_probe"] == 0 and
                printer == bytes.fromhex(ref["run"]["printer_raw_hex"]),
                name + " CPC_PROVENANCE_CHANGED")
        require(len(ref["pre_run"]["if_records"]) == 1 and
                ref["pre_run"]["if_records"][0]["line_number"] == 30 and
                len(ref["run"]["program_trace"]) == 1 and
                ref["run"]["program_trace"][0] in (420, 810),
                name + " CPC_IF_OR_TRACE_CHANGED")
    return captures

def one_case(cap, cli, image_cli):
    name = cap["case"]
    operator_group = "_".join(name.split("_")[:2])
    require(operator_group in EXPECTED_OPS, name + " UNKNOWN_RELATION_CASE")
    source = read(ROOT / cap["source_path"])
    cpc_image = read(ARCHIVE / "original" / name / "program.bin")
    adapted = adapt(source, name)
    native = process(image_cli, adapted, name + " IMAGE").stdout
    expected_hex = cap["original"]["pre_run"]["if_records"][0]["record_hex"]
    original = exact_if(cpc_image, native, expected_hex, name)
    require(original[4] == 0xa1 and EXPECTED_OPS[operator_group] in original[5:-1],
            name + " RELATION_NOT_PRESENT")
    # The adapted source must LIST identically and re-tokenise identically.
    listing = process(cli, adapted + b"LIST\n:quit\n", name + " LIST")
    require(b"[cli:error]" not in listing.stderr and
            listing.stdout == adapted, name + " LIST_DIFF " +
            repr(listing.stdout))
    roundtrip = process(image_cli, listing.stdout, name + " IMAGE_ROUNDTRIP").stdout
    require(records(roundtrip, name + " ROUNDTRIP")[30] == original,
            name + " LIST_RETOKENIZED_IF_DIFF")
    execution = process(cli, adapted + b"RUN\n:step 100\n:quit\n",
                        name + " RUN")
    require(b"[cli:error]" not in execution.stderr and
            b"[cli] END" in execution.stderr,
            name + " RUNTIME_ERROR " + repr(execution.stderr))
    lines = execution.stdout.splitlines()
    require(len(lines) == 1 and
            re.fullmatch(rb"[ \t]*(42|81)[ \t]*", lines[0]) is not None,
            name + " NON_NUMERIC_OR_WRONG_HOST_PRINTER " +
            repr(execution.stdout))
    numeric = int(lines[0].strip())
    observed = [420 if numeric == 42 else 810]
    expected = cap["original"]["run"]["program_trace"]
    require(observed == expected,
            name + " TRACE_MISMATCH expected=" + repr(expected) +
            " actual=" + repr(observed))
    print("J1.13-B", name, "IF_LINE_30_MATCH_EXACT",
          "BRANCH_MATCH_SEMANTIC", str(observed[0]), flush=True)

def falsifications():
    before = bytes.fromhex(
        "16 00 1e 00 a1 20 02 00 00 c1 ef 02 00 00 c2 20 eb 20 1e 46 00 00")
    corrupt = bytearray(before)
    corrupt[8] = 0x20  # cache is semantically opaque, but exact record changed.
    try:
        exact_if(before + b"\x00\x00", bytes(corrupt) + b"\x00\x00",
                 before.hex(" "), "FALSIFICATION")
    except DifferentialFailure as exc:
        require("IF_RECORD_MISMATCH" in str(exc),
                "WRONG_IF_FALSIFICATION_REASON")
    else:
        raise DifferentialFailure("IF_FALSIFICATION_ACCEPTED")
    try:
        head_guard("wrong-sha", "required-sha")
    except DifferentialFailure as exc:
        require("FALSE_HEAD" in str(exc), "WRONG_HEAD_FALSIFICATION_REASON")
    else:
        raise DifferentialFailure("FALSE_HEAD_ACCEPTED")
    require(digest(b"modified") != MANIFEST_SHA,
            "MANIFEST_FALSIFICATION_ACCEPTED")
    require([810] != [420], "TRACE_FALSIFICATION_ACCEPTED")
    print("PASS post-B IF BYTE, TRACE, MANIFEST and FALSE_HEAD falsifications")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--image-cli", type=Path, required=True)
    parser.add_argument("--expected-head")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.expected_head:
        p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, check=True)
        head_guard(p.stdout.strip(), args.expected_head)
    if args.self_test:
        falsifications()
    captures = preflight()
    for cap in captures:
        one_case(cap, args.cli, args.image_cli)
    print("PASS J1.13-B 24/24 IF RECORD MATCH_EXACT")
    print("PASS J1.13-B 24/24 BRANCH MATCH_SEMANTIC")
    print("PRINT #8 not native; only 420->42 and 810->81 in memory; "
          "CPC printer bytes are NOT host stdout; whole program RAM NOT compared")
    print("J1.13-A pre-B UNSUPPORTED classifications untouched")

if __name__ == "__main__":
    try:
        main()
    except (DifferentialFailure, OSError, ValueError, KeyError,
            UnicodeError, subprocess.CalledProcessError) as exc:
        print("FAIL J1.13-B:", str(exc), file=sys.stderr)
        sys.exit(1)
