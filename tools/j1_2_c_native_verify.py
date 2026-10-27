#!/usr/bin/env python3
"""J1.2-C differential: immutable CPC6128 NMIN versus live native C99.

J1.2-A is a historical archive. Its then-unsupported native outcome is
deliberately sealed, never overwritten by the current J1.2-C capability.
CPC printer (CRLF), CPC screen (visual only), and Linux stdout (LF)
are three separate channels, not byte-identical artifacts.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_integer_boundaries"
NMIN = EVIDENCE / "NMIN"
sys.path.insert(0, str(ROOT / "tools"))
from j1_2_boundary_verify import verify as verify_historical  # noqa: E402

SOURCE = b"10 B%=-32768\n20 PRINT B%\n30 END\n"
OPERAND = bytes.fromhex("F5 1F 00 00 00 00 90")
PROGRAM_SHA256 = "dad9d7f1cff60feac8f16fed4374e4f50aac78d17bf5f342468841c0cce01a58"
PRINTER_BYTES = b" 0 \r\n-32768 \r\n"
NATIVE_RUN_BYTES = b"-32768 \n"


class Invalid(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Invalid(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_proof(path):
    require(path.is_file() and not path.is_symlink(),
            "ARCHIVED_PROOF_MISSING " + str(path))
    return path.read_bytes()


def assert_cpc_image(image, expected_sha=PROGRAM_SHA256):
    require(digest(image) == expected_sha, "NMIN: CPC_SHA_CHANGED")
    require(len(image) == 36, "NMIN: CPC_SIZE_CHANGED")
    require(image[9:9 + len(OPERAND)] == OPERAND,
            "NMIN: CPC_REAL5_OPERAND_CHANGED")
    require(image[-2:] == b"\x00\x00", "NMIN: CPC_SENTINEL_CHANGED")


def command(binary, stdin, description):
    try:
        process = subprocess.run([str(binary)], input=stdin,
                                 capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Invalid(description + ": PROCESS_FAILED " + str(exc)) from exc
    require(process.returncode == 0 and b"[cli:error]" not in process.stderr,
            description + ": CLI_FAILED " + repr(process.stderr[:180]))
    return process


def verify_live(cli, image_cli):
    verify_historical(EVIDENCE, permanent=True)
    require(read_proof(NMIN / "original.bas") == SOURCE,
            "NMIN: SOURCE_CHANGED")
    cpc = read_proof(NMIN / "program.bin")
    assert_cpc_image(cpc)
    printed = read_proof(NMIN / "run/printer.dat")
    require(printed == PRINTER_BYTES,
            "NMIN: ARCHIVED_PRINTER_SEMANTICS_CHANGED")
    require(read_proof(NMIN / "run/autocmd.json").find(
            b"PRINT #8,ERR") != -1 and read_proof(
            NMIN / "run/autocmd.json").find(b"PRINT #8,B%") != -1,
            "NMIN: ARCHIVED_PRINTER_PROBE_MISSING")

    native = command(image_cli, SOURCE, "NMIN/IMAGE")
    require(native.stdout == cpc, "NMIN: NOT_MATCH_EXACT")
    require(digest(native.stdout) == PROGRAM_SHA256,
            "NMIN: NATIVE_SHA_CHANGED")
    listed = command(cli, SOURCE + b"LIST\n:quit\n", "NMIN/LIST")
    require(listed.stdout == SOURCE and b"[cli] LIST\n" in listed.stderr,
            "NMIN: LIST_DIFF")
    ran = command(cli, SOURCE + b"RUN\n:step 3\n:step\n:quit\n",
                  "NMIN/RUN")
    require(b"[cli] RUNNING\n" in ran.stderr and
            b"[cli] STEPPED 3\n" in ran.stderr and
            b"[cli] END\n" in ran.stderr,
            "NMIN: END_NOT_REACHED")
    require(ran.stdout == NATIVE_RUN_BYTES, "NMIN: NATIVE_PRINT_DIFF")
    # Explicit CRLF -> LF normalization of the CPC printer number line
    # only; raw streams differ, and the screen is never treated as text.
    require(printed.split(b"\r\n") == [b" 0 ", b"-32768 ", b""],
            "NMIN: CPC_ERR_OR_VALUE_DIFF")
    require(printed.split(b"\r\n")[1] + b"\n" == ran.stdout,
            "NMIN: PRESENTATION_MISMATCH")
    require(printed != ran.stdout,
            "NMIN: CROSS_TRANSPORT_RAW_EQUALITY_FORBIDDEN")
    print("PASS J1.2-C NMIN MATCH_EXACT CPC_RAM_SHA256=" + PROGRAM_SHA256,
          "LIST=EXACT RUN=END CPC_ERR=0 CPC_VALUE=-32768",
          "PRINT=MATCH_PRESENTATION CPC_PRINTER=CRLF NATIVE=LF",
          "SCREEN=VISUAL_OBSERVATION", flush=True)


def self_test():
    original = read_proof(NMIN / "program.bin")
    assert_cpc_image(original)
    broken = bytearray(original)
    broken[10] ^= 1
    try:
        assert_cpc_image(bytes(broken))
    except Invalid as exc:
        require(str(exc) == "NMIN: CPC_SHA_CHANGED",
                "NMIN: WRONG_OPERAND_CORRUPTION_CAUSE")
    else:
        raise Invalid("NMIN: ALTERED_OPERAND_ACCEPTED")
    bad_expected = "0" + PROGRAM_SHA256[1:]
    try:
        assert_cpc_image(original, bad_expected)
    except Invalid as exc:
        require(str(exc) == "NMIN: CPC_SHA_CHANGED",
                "NMIN: WRONG_HASH_CORRUPTION_CAUSE")
    else:
        raise Invalid("NMIN: ALTERED_ANCHOR_ACCEPTED")
    try:
        read_proof(NMIN / "missing-required-file")
    except Invalid as exc:
        require(str(exc).startswith("ARCHIVED_PROOF_MISSING"),
                "NMIN: WRONG_MISSING_PROOF_CAUSE")
    else:
        raise Invalid("NMIN: MISSING_PROOF_ACCEPTED")
    print("PASS J1.2-C NMIN altered operand, altered hash and missing proof rejected",
          flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--image-cli", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        verify_live(args.cli, args.image_cli)
        if args.self_test:
            self_test()
    except (Invalid, ValueError, KeyError, TypeError, OSError) as exc:
        print("J1.2-C FAILED:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
