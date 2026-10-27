#!/usr/bin/env python3
"""J1.3-B: LIVE C99 execution vs IMMUTABLE independent CPC6128 subtraction proof.

The J1.3-A seal and historical C99 UNSUPPORTED classifications are never
rewritten. Exact comparison applies only to BASIC RAM images; CPC printer
CRLF, CPC screenshot pixels and host stdout LF are distinct transport channels.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_integer_subtraction"
SOURCES = ROOT / "tests/oracles/inputs/j1_3_a"
sys.path.insert(0, str(ROOT / "tools"))
from j1_3_subtraction_verify import verify as verify_historical

# Anchors from the actual ROM-backed acquisition #40498357272, NOT C99.
CASES = {
    "P5_M3": (5, 3, 2, "be4d19eea32a0c978e25ac313610ee011e6da1ff3a82b3f833b5770b97695d23"),
    "P2_M3": (2, 3, -1, "e64a4df6b48d784bc79b66a7f8c9683f37b85774e92877500ecc3796fe149dd2"),
    "NMIN_M0": (-32768, 0, -32768, "5ff6b68e9009a4238a6ed4d848e46d79c8b2c92fbfa4d786b32753d7c4aba992"),
    "PMAX_M1": (32767, 1, 32766, "5f04316b99b442732f94760fb4c2e12620c1eb34f60d08a9c11be8e70ba32784"),
    "NMIN_M1": (-32768, 1, None, "9d28ff50bb13698edf41992dcfdd98495211346eee25a8617c4e98b835dfeb92"),
    "ZERO_M255": (0, 255, -255, "a7173a1d7cb49100ddf5379f57a49d3b96dfc9f40cf466bd9c14e5e9aa22d323"),
}
ORIGINAL_MANIFEST_SHA = "d36d775c857d45edb8eebe91ad5479d458ddeabcbc9c6a531180fb85f4eb75d9"

class Invalid(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise Invalid(reason)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    require(path.is_file() and not path.is_symlink(),
            "MISSING_ORIGINAL_PROOF " + str(path))
    return path.read_bytes()

def assert_cpc(name, raw, expected_sha=None):
    target = CASES[name][3] if expected_sha is None else expected_sha
    require(digest(raw) == target, name + ": ORIGINAL_IMAGE_SHA_CHANGED")
    require(raw.endswith(b"\x00\x00") and len(raw) >= 40,
            name + ": INVALID_ORIGINAL_CPC_PROGRAM")

def run(binary, source, case):
    try:
        p = subprocess.run([str(binary)], input=source, capture_output=True,
                           timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise Invalid(case + ": PROCESS_FAILED " + str(err)) from err
    require(p.returncode == 0, case + ": PROCESS_NONZERO " +
            repr(p.stderr[:200]))
    return p

def check_case(case, cli, image_cli):
    lhs, n, result, anchor = CASES[case]
    source = (f"10 A%={lhs}\n20 B%=A%-{n}\n"
              "30 PRINT B%\n40 END\n").encode("ascii")
    require(read(SOURCES / (case.lower()+".bas")) == source and
            read(EVIDENCE / case / "original.bas") == source,
            case + ": ORIGINAL_SOURCE_CHANGED")
    raw = read(EVIDENCE / case / "program.bin")
    assert_cpc(case, raw)
    native = run(image_cli, source, case + "/IMAGE")
    require(native.stdout == raw and digest(native.stdout) == anchor,
            case + ": NOT_MATCH_EXACT")
    listed = run(cli, source + b"LIST\n:quit\n", case + "/LIST")
    require(listed.stdout == source and
            b"[cli] LIST\n" in listed.stderr and
            b"[cli:error]" not in listed.stderr,
            case + ": LIST_DIFF")
    printer = read(EVIDENCE / case / "run/printer.dat")
    if result is None:
        # CPC issued Overflow in 20 / ERR 6, but later B%=0 is NOT a
        # proven mathematical result or proof of historical full atomicity.
        require(printer == b" 6 \r\n 0 \r\n",
                case + ": ORIGINAL_OVERFLOW_EVIDENCE_CHANGED")
        h = run(cli, source + b"RUN\n:step 2\n:quit\n", case + "/RUN")
        require(h.stdout == b"" and
                b"[cli] STEPPED 1\n" in h.stderr and
                b"BSR_EXECUTOR_ERROR" in h.stderr and
                b"BE_INTEGER_OVERFLOW" in h.stderr,
                case + ": NATIVE_OVERFLOW_NOT_REPORTED")
        print("PASS",case,"MATCH_EXACT SHA="+anchor,
              "CPC=Overflow_in_20 ERR=6",
              "C99=BE_INTEGER_OVERFLOW", "OUTPUT=EMPTY",
              "CPC_ATOMICITY=NOT_INFERRED", flush=True)
    else:
        h = run(cli, source + b"RUN\n:step 4\n:step\n:quit\n", case + "/RUN")
        expected_print = (b" " if result >= 0 else b"") + str(result).encode() + b" "
        require(b"[cli] RUNNING\n" in h.stderr and
                b"[cli] STEPPED 4\n" in h.stderr and
                b"[cli] END\n" in h.stderr and
                b"[cli:error]" not in h.stderr, case + ": NO_END")
        require(h.stdout == expected_print + b"\n",
                case + ": WRONG_NATIVE_VALUE")
        require(printer == b" 0 \r\n" + expected_print + b"\r\n",
                case + ": CPC_PRINTER_VALUE_CHANGED")
        require(printer.split(b"\r\n")[1] + b"\n" == h.stdout and
                printer != h.stdout,
                case + ": CHANNELS_CONFUSED")
        print("PASS",case,"MATCH_EXACT SHA="+anchor,
              "RUN=END", "CPC_ERR=0", "VALUE="+str(result),
              "PRINT=MATCH_PRESENTATION",
              "CPC_PRINTER_CRLF_NATIVE_LF=SEPARATE", flush=True)

def test_negative(cli, image_cli):
    # Intentionally ONLY forms forbidden by the strict J1.3-B grammar.
    bad = [
        "B%=A%-256", "B%=A%--1", "B%=A%- -1", "B%=A%-+1",
        "B%=A%-1-2", "B%=A%-1+2", "B%=A%-C%", "B%=A!-1",
        "B%=A%-32768", "B%=A%-1.2", "B%=A%-1:PRINT 2:",
    ]
    for item in bad:
        raw = ("10 A%=5\n20 "+item+"\n30 END\n").encode()
        p = subprocess.run([str(image_cli)],input=raw,capture_output=True,
                           timeout=20,check=False)
        require(p.returncode == 2 and not p.stdout and
                b"image-cli: input rejected:" in p.stderr,
                item + ": OUT_OF_SCOPE_EXPORT_ACCEPTED")
    for old in ("10 B%=A%+3\n", "10 B%=-32768\n"):
        # Both old grammars must remain accepted.
        p = run(image_cli, old.encode("ascii") + b"20 END\n", "EXISTING_GRAMMAR")
        require(p.stdout.endswith(b"\x00\x00"),"REGRESSION_OLD_GRAMMAR")
    print("PASS J1.3-B 11 forbidden forms rejected, addition and NMIN preserved")

def self_test():
    name = "P5_M3"
    raw = read(EVIDENCE/name/"program.bin")
    assert_cpc(name,raw)
    changed = bytearray(raw)
    changed[10] ^= 1
    try:
        assert_cpc(name,bytes(changed))
    except Invalid as exc:
        require(str(exc) == name+": ORIGINAL_IMAGE_SHA_CHANGED",
                "WRONG_BINARY_REJECTION")
    else:
        raise Invalid("MUTATED_ORIGINAL_ACCEPTED")
    try:
        assert_cpc(name,raw,"0"*64)
    except Invalid as exc:
        require(str(exc) == name+": ORIGINAL_IMAGE_SHA_CHANGED",
                "WRONG_SHA_REJECTION")
    else:
        raise Invalid("MUTATED_SHA_ACCEPTED")
    try:
        read(EVIDENCE/name/"missing-original")
    except Invalid as exc:
        require(str(exc).startswith("MISSING_ORIGINAL_PROOF"),
                "WRONG_MISSING_REJECTION")
    else:
        raise Invalid("MISSING_ORIGINAL_ACCEPTED")
    print("PASS J1.3-B negative changed-image, changed-SHA, missing-evidence")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli",type=Path,required=True)
    parser.add_argument("--image-cli",type=Path,required=True)
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    try:
        verify_historical(EVIDENCE,permanent=True)
        require(digest(read(EVIDENCE/"manifest.json")) == ORIGINAL_MANIFEST_SHA,
                "SEALED_J1_3_A_MANIFEST_CHANGED")
        for case in CASES:
            check_case(case,args.cli,args.image_cli)
        test_negative(args.cli,args.image_cli)
        if args.self_test:
            self_test()
        print("PASS J1.3-B SIX C99 NATIVE IMAGES MATCH_EXACT; "
              "FIVE EXECUTABLE, ONE ATOMIC NATIVE OVERFLOW",flush=True)
    except (Invalid, ValueError, KeyError, TypeError, OSError,
            subprocess.TimeoutExpired) as err:
        print("J1.3-B DIFFERENTIAL FAILED:",err,file=sys.stderr)
        return 1
    return 0

if __name__=="__main__":
    sys.exit(main())
