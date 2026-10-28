#!/usr/bin/env python3
"""J1.12-B1 sealed CPC FOR/NEXT *line-record* differential, not runtime.

J1.12-A's historical UNSUPPORTED and ROM evidence are immutable. The only
adaptation is PRINT #8,I% (or J%, decimal) to native PRINT I% in a temporary
stdin stream. This does NOT assert full-program RAM equality or CPC execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tests/fixtures/cpc6128/j1_12_for_next"
MANIFEST_SHA = "acc43227f6970ffa7ab04a135d04e49f09231f053606d8000fa313c06df42a1b"
RECORD_TOKEN = (0x9E, 0xB0)
HYBRID_CASE = "F_NEXT_NAMED"
HYBRID_LINE = 20

class DifferentialFailure(ValueError):
    pass

def require(predicate, text):
    if not predicate:
        raise DifferentialFailure(text)

def read(path):
    require(path.is_file() and not path.is_symlink(), "MISSING " + str(path))
    return path.read_bytes()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def records(image, label):
    require(image.endswith(b"\x00\x00"), label + " MISSING_SENTINEL")
    pos = 0
    found = {}
    while pos < len(image)-2:
        require(len(image)-2-pos >= 5, label + " SHORT_HEADER")
        length = int.from_bytes(image[pos:pos+2], "little")
        line = int.from_bytes(image[pos+2:pos+4], "little")
        require(5 <= length <= len(image)-2-pos, label + " BAD_RECORD_LENGTH")
        raw = image[pos:pos+length]
        require(raw[-1] == 0 and line not in found, label + " BAD_RECORD")
        found[line] = raw
        pos += length
    require(pos == len(image)-2, label + " RECORD_BOUNDARY")
    return found

def control_lines(image, label):
    result = {}
    for line, raw in records(image, label).items():
        body = raw[4:-1].lstrip(b" ")
        if body and body[0] in RECORD_TOKEN:
            result[line] = ("full", raw)
        elif b"\x01\xb0" in raw[4:-1]:
            # Exactly one admitted hybrid source line in the sealed corpus.
            require(label.endswith(HYBRID_CASE) and line == HYBRID_LINE,
                    label + " UNEXPECTED_HYBRID " + str(line))
            body_full = raw[4:-1]
            require(body_full.count(b"\x01\xb0") == 1,
                    label + " DUPLICATE_HYBRID")
            start = body_full.index(b"\x01\xb0")
            result[line] = ("suffix", body_full[start:] + b"\x00")
    return result

def compare(cpc, native, case):
    expected = control_lines(cpc, "CPC_" + case)
    actual = control_lines(native, "C99_" + case)
    require(expected and expected.keys() == actual.keys(),
            case + " DIFF CONTROL_LINE_SET CPC=" + str(sorted(expected)) +
            " C99=" + str(sorted(actual)))
    full = suffix = 0
    for line, (kind, wanted) in expected.items():
        actual_kind, got = actual[line]
        require(kind == actual_kind and wanted == got,
                case + " DIFF LINE=" + str(line) + " CPC=" + wanted.hex(" ") +
                " C99=" + got.hex(" ") + " KIND=" + kind + "/" + actual_kind)
        if kind == "full":
            full += 1
        else:
            suffix += 1
        print("J1.12-B1", case, "LINE", line,
              "MATCH_EXACT" if kind == "full" else "MATCH_EXACT_SUFFIX",
              "CPC=" + wanted.hex(" "), "C99=" + got.hex(" "))
    return full, suffix

def adapt(source, case):
    raw = source.decode("ascii")
    # Strictly the recorded channel-8 INTEGER scalar/byte numeric printer
    # forms, never quoted/comment text or general expressions.
    pattern = r"PRINT #8,([IJ]%|[0-9]{1,3})(?=[:\r\n]|$)"
    modified, count = re.subn(pattern, lambda m: "PRINT " + m.group(1), raw)
    require(count >= 1 and "PRINT #8" not in modified,
            case + " UNHANDLED_NON_NATIVE_PRINTER")
    return modified.encode("ascii")

def run_image(exe, source, case):
    try:
        result = subprocess.run([str(exe)], input=source, capture_output=True,
                                timeout=35, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DifferentialFailure(case + " PROCESS_ERROR " + str(error)) from error
    require(result.returncode == 0, case + " IMAGE_CLI_FAILED " +
            repr(result.stderr[-600:]))
    return result.stdout

def preflight():
    manifest_raw = read(BASE / "manifest.json")
    require(digest(manifest_raw) == MANIFEST_SHA, "J1.12-A MANIFEST_MUTATED")
    manifest = json.loads(manifest_raw)
    seal = json.loads(read(BASE / "seal.json"))
    cases = manifest["mandatory_cases"]
    require(manifest["phase"] == "J1.12-A" and len(cases) == 20 and
            len(set(cases)) == 20 and len(manifest["captures"]) == 20,
            "HISTORIC_CASE_SET_CHANGED")
    require(seal["manifest_sha256"] == MANIFEST_SHA and
            set(seal["program_sha256"]) == set(cases), "ORACLE_SEAL_CHANGED")
    captures = {x["case"]: x for x in manifest["captures"]}
    require(set(captures) == set(cases), "CAPTURE_SET_CHANGED")
    for case in cases:
        cap = captures[case]
        raw = read(BASE / "original" / case / "program.bin")
        require(digest(raw) == seal["program_sha256"][case],
                case + " CPC_PROGRAM_SHA_CHANGED")
        require(cap["original"]["pre_run"]["comparison"]["classification"]
                == "UNSUPPORTED", case + " HISTORIC_PRE_B_RECLASSIFIED")
        source = read(ROOT / cap["source_path"])
        require(digest(source) == cap["source_sha256"],
                case + " ORIGINAL_SOURCE_SHA_CHANGED")
    return cases, captures

def self_test():
    # Fail-closed: a single changed control byte cannot receive MATCH_EXACT.
    raw = bytes.fromhex("11 00 0a 00 9e 20 02 00 00 c9 ef 0f 20 ec 20 0f 00 00 00")
    changed = bytearray(raw)
    changed[11] = 0x10
    try:
        compare(raw, bytes(changed), "F_POS_IMPLICIT_ONE")
    except DifferentialFailure as err:
        require("DIFF LINE=10" in str(err), "FALSIFICATION_WRONG_REASON")
    else:
        raise DifferentialFailure("FALSIFICATION_NOT_REJECTED")
    print("PASS J1.12-B1 FALSE_BYTE_REJECTED")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-cli", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    cases, captures = preflight()
    full = suffix = 0
    for case in cases:
        cap = captures[case]
        cpc = read(BASE / "original" / case / "program.bin")
        source = read(ROOT / cap["source_path"])
        native = run_image(args.image_cli, adapt(source, case), case)
        a, b = compare(cpc, native, case)
        full += a
        suffix += b
    require(suffix == 1 and full >= 20,
            "UNEXPECTED_CPC_CONTROL_COVERAGE full=" + str(full) +
            " suffix=" + str(suffix))
    print("PASS J1.12-B1 20/20 SEALED_CASES CONTROL_RECORDS",
          full, "FULL_MATCH_EXACT", suffix, "COLON_SUFFIX_MATCH_EXACT")
    print("PASS J1.12-B1 HISTORICAL_PRE_B_UNSUPPORTED 20/20 IMMUTABLE")
    print("NOT_A_FULL_PROGRAM_RAM_COMPARISON; PRINT #8 adapted in checker only")
    print("NOT_FOR_NEXT_RUNTIME_SUPPORTED")

if __name__ == "__main__":
    try:
        main()
    except (DifferentialFailure, ValueError, KeyError, UnicodeError) as exc:
        print("J1.12-B1 DIFFERENTIAL FAILURE:", exc, file=sys.stderr)
        raise SystemExit(1) from exc
