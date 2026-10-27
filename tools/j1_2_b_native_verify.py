#!/usr/bin/env python3
"""J1.2-B: live C99 INTEGER16 capability vs immutable independent CPC J1.2-A.

Historical classification is validated by its own verifier; this file never
regenerates or modifies historical images, screenshots, printer bytes or statuses.
CPC printer output and Linux stdout are distinct channels: compare presentation
only after *explicit* CRLF -> LF normalization, never assert raw equality.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_integer_boundaries"
sys.path.insert(0, str(ROOT / "tools"))
from j1_2_boundary_verify import verify as verify_historical  # noqa: E402

# Hard anchors from J1.2-A independent acquisitions, not recalculated from C99.
SPECS = {
    "P255": (255, "19 FF", "6e15e0144aae0a5d411de9b4e41671306a2c489535a4fa19a943825404e5776b"),
    "N255": (-255, "F5 19 FF", "415d67d0bc7c42d5379c83ee3bd63049473edca2561c42f8215a70e3c232ae04"),
    "P256": (256, "1A 00 01", "b5b9e1e78e978aa27abcc69c6ef8fe22655117152fb3ff7b32431f88fde7eb2a"),
    "N256": (-256, "F5 1A 00 01", "c919dafaa0088e8a127bd3aa818da3e992b172abf9018109e3da993eae028040"),
    "PMAX": (32767, "1A FF 7F", "049afac7471df832cf9855d4a080f41ac1e2ed336ef37140e1e4902dda0b3f8e"),
}

class Invalid(ValueError):
    pass

def require(condition, reason):
    if not condition:
        raise Invalid(reason)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def assert_cpc_image(name, image):
    value, operand, sha = SPECS[name]
    require(digest(image) == sha, name + ": CPC_SHA_CHANGED")
    # CPC record 10's operand starts at offset 9, after header+explicit B%.
    require(image[9:9 + len(bytes.fromhex(operand))] == bytes.fromhex(operand),
            name + ": CPC_OPERAND_CHANGED")
    require(image[-2:] == b"\x00\x00", name + ": CPC_SENTINEL_CHANGED")
    return value

def command(binary, stdin, label):
    try:
        result = subprocess.run([str(binary)], input=stdin, capture_output=True,
                                timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise Invalid(label + ": PROCESS_FAILED " + str(err)) from err
    require(result.returncode == 0 and b"[cli:error]" not in result.stderr,
            label + ": CLI_FAILED " + repr(result.stderr[:150]))
    return result

def live(name, cli, image_cli):
    value, _, _ = SPECS[name]
    source = (f"10 B%={value}\n20 PRINT B%\n30 END\n").encode("ascii")
    require((EVIDENCE / name / "original.bas").read_bytes() == source,
            name + ": HISTORICAL_SOURCE_CHANGED")
    cpc = (EVIDENCE / name / "program.bin").read_bytes()
    assert_cpc_image(name, cpc)
    native = command(image_cli, source, name + "/IMAGE")
    require(native.stdout == cpc, name + ": NOT_MATCH_EXACT")
    listed = command(cli, source + b"LIST\n:quit\n", name + "/LIST")
    require(listed.stdout == source and b"[cli] LIST\n" in listed.stderr,
            name + ": LIST_DIFF")
    ran = command(cli, source + b"RUN\n:step 3\n:step\n:quit\n", name + "/RUN")
    require(b"[cli] RUNNING\n" in ran.stderr and
            b"[cli] STEPPED 3\n" in ran.stderr and
            b"[cli] END\n" in ran.stderr, name + ": END_NOT_REACHED")
    presentation = (b" " if value >= 0 else b"") + str(value).encode("ascii") + b" "
    expected_native = presentation + b"\n"
    require(ran.stdout == expected_native, name + ": NATIVE_NUMERIC_DIFF")
    printer = (EVIDENCE / name / "run/printer.dat").read_bytes()
    expected_printer = b" 0 \r\n" + presentation + b"\r\n"
    require(printer == expected_printer, name + ": PRINTER_PRESENTATION_CHANGED")
    require(printer.split(b"\r\n")[1] == ran.stdout[:-1],
            name + ": PRESENTATION_MISMATCH")
    require(printer != ran.stdout, name + ": TRANSPORT_CONFUSION")
    print("PASS J1.2-B", name, "MATCH_EXACT",
          "SHA256=" + digest(native.stdout), "LIST=EXACT RUN=END",
          "VALUE=" + str(value), "PRINT=MATCH_PRESENTATION",
          "TRANSPORT=CPC_CRLF_VS_C99_LF", flush=True)

def excluded(cli, image_cli):
    for value in (32768,):
        source = (f"10 B%={value}\n20 PRINT B%\n30 END\n").encode("ascii")
        for label, binary, payload in (
            ("IMAGE", image_cli, source),
            ("CLI", cli, source + b"RUN\n:step 3\n:quit\n"),
        ):
            try:
                result = subprocess.run([str(binary)], input=payload,
                                        capture_output=True, timeout=20, check=False)
            except (OSError, subprocess.TimeoutExpired) as err:
                raise Invalid(str(value) + "/" + label + ": EXECUTION_FAILED") from err
            if label == "IMAGE":
                require(result.returncode != 0 and not result.stdout,
                        str(value) + ": IMAGE_OUT_OF_SCOPE_ACCEPTED")
            else:
                require(b"[cli:error]" in result.stderr and not result.stdout,
                        str(value) + ": CLI_OUT_OF_SCOPE_ACCEPTED")
    print("PASS J1.2-B OUT_OF_SCOPE +32768 rejected; -32768 is J1.2-C", flush=True)

def self_test():
    for name in ("P256", "N256", "PMAX"):
        original = (EVIDENCE / name / "program.bin").read_bytes()
        assert_cpc_image(name, original)
        bad = bytearray(original)
        bad[9] ^= 1
        try:
            assert_cpc_image(name, bytes(bad))
        except Invalid as err:
            require(str(err) == name + ": CPC_SHA_CHANGED",
                    name + ": WRONG_NEGATIVE_CAUSE")
        else:
            raise Invalid(name + ": MUTATED_IMAGE_ACCEPTED")
    print("PASS J1.2-B three independent mutated-binary rejections", flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--image-cli", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        verify_historical(EVIDENCE, permanent=True)
        for name in SPECS:
            live(name, args.cli, args.image_cli)
        excluded(args.cli, args.image_cli)
        if args.self_test:
            self_test()
        print("PASS J1.2-B 3 NEW + 2 RETAINED CPC images; "
              "historical J1.2-A validated separately", flush=True)
    except (Invalid, ValueError, OSError, KeyError, TypeError) as err:
        print("J1.2-B FAILED:", err, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
