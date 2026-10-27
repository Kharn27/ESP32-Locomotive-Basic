#!/usr/bin/env python3
"""J1.6-B live native FB INTEGER MOD vs immutable J1.6-A CPC6128 acquisitions.

Compare complete token RAM program images, not CPC screenshot pixels.
CPC printer CRLF and native stdout LF are separate presentation channels.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_integer_mod"
SOURCES = ROOT / "tests/oracles/inputs/j1_6_a"
sys.path.insert(0, str(ROOT / "tools"))
from j1_6_mod_verify import (verify as verify_historical,
                                        self_test as historical_self_test)

# Immutable SHA256 anchors transcribed from sealed J1.6-A ROM-backed captures.
# ERR=11 zero-divisor probes are NOT arithmetic results.
CASES = {
    "P6_M3": (6, 3, 0, "300eeea397cbaf353e25dbd90fadfc2ed7b1978255f2c7e50b0dcb68b89c1973"),
    "P7_M2": (7, 2, 1, "8d21f6423b25998e36c3b84f6b804c925375666fe2b1b89cdf6b4d16c0e0b22a"),
    "N7_M2": (-7, 2, -1, "3208e5d4de3f7c89fbff449bf98b6cbb644ed793d3065b58f4c2b9fd0d98a991"),
    "N7_M3": (-7, 3, -1, "f1eee10243a6b5e76c7ab434d0d707d93ece4a47362e5756400eb20e60a2e130"),
    "N5_M2": (-5, 2, -1, "87d838b031655cf874bf50e218bad12dc0ae01fc85581e5ee3cfa481f7623802"),
    "NMIN_M1": (-32768, 1, 0, "71045966b11fcda69f44a528f4ae30285a422b89d888f467d495a977edcfac97"),
    "NMIN_M255": (-32768, 255, -128, "c2830d045d215f5a6225fb8141398c5434f3923a3a83c6e918b2da9220cdaddb"),
    "PMAX_M255": (32767, 255, 127, "69fa01db463889099097ff1b4f33addd2df0194fbdcff79abbe991f7d57cf20c"),
    "P2_M255": (2, 255, 2, "1e28add2cd86a5070fb60db6dd1b36c353113ad13dccf786b69cd22b34ae9d32"),
    "P255_M255": (255, 255, 0, "8e9aa789258df3a145b8f56cdbff39e46066ca3b7d88c7a3fd31c7e882b87440"),
    "P1_M0": (1, 0, None, "744f98325a441cba9370b0ab05ef741f60f15848aae0489c65548e81c7b9480d"),
    "P0_M0": (0, 0, None, "f4a6eb1eb56b8da02977fcf08d24fd8069a722f9391ba3d4ecdea0fe893d4f7b"),
}
MANIFEST_SHA = "998c3768c61f8c2981ffabb8e138542fd575653b2f9a9c81f7919473f4cd9822"

class Invalid(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise Invalid(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    require(path.is_file() and not path.is_symlink(), "MISSING_ORIGINAL " + str(path))
    return path.read_bytes()

def execute(binary, source, label):
    try:
        result = subprocess.run([str(binary)], input=source, capture_output=True,
                                timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Invalid(label + ": NATIVE_PROCESS_FAILED " + str(error)) from error
    require(result.returncode == 0,
            label + ": NATIVE_PROCESS_ERROR " + repr(result.stderr[:200]))
    return result

def check_case(case, cli, image_cli):
    lhs, n, expected, anchor = CASES[case]
    source = (f"10 A%={lhs}\n20 B%=A% MOD {n}\n"
              "30 PRINT B%\n40 END\n").encode("ascii")
    require(read(SOURCES / (case.lower()+".bas")) == source and
            read(EVIDENCE/case/"original.bas") == source,
            case + ": ORIGINAL_SOURCE_CHANGED")
    image = read(EVIDENCE/case/"program.bin")
    require(digest(image) == anchor and image.endswith(b"\x00\x00"),
            case + ": ORIGINAL_IMAGE_SHA_CHANGED")
    native = execute(image_cli,source,case+"/IMAGE")
    require(native.stdout == image and digest(native.stdout) == anchor,
            case + ": NOT_MATCH_EXACT")
    listing = execute(cli,source+b"LIST\n:quit\n",case+"/LIST")
    require(listing.stdout == source and
            b"[cli] LIST\n" in listing.stderr and
            b"[cli:error]" not in listing.stderr,
            case + ": LIST_MISMATCH")
    printer = read(EVIDENCE/case/"run/printer.dat")
    if expected is None:
        # The CPC's B%=0 was measured after the error, not as a quotient.
        require(printer == b" 11 \r\n 0 \r\n",
                case + ": HISTORICAL_ZERO_DIAGNOSTIC_CHANGED")
        result = execute(cli,source+b"RUN\n:step 2\n:quit\n",case+"/ZERO")
        require(result.stdout == b"" and
                b"[cli] STEPPED 1\n" in result.stderr and
                b"BSR_EXECUTOR_ERROR" in result.stderr and
                b"BE_DIVISION_BY_ZERO" in result.stderr,
                case + ": NATIVE_DIVISION_BY_ZERO_NOT_REPORTED")
        print("PASS",case,"MATCH_EXACT SHA="+anchor,
              "CPC_ERR=11 C99=BE_DIVISION_BY_ZERO OUTPUT=EMPTY",
              "CPC_ATOMICITY=NOT_INFERRED",flush=True)
    else:
        number = (b" " if expected >= 0 else b"") + str(expected).encode() + b" "
        require(printer == b" 0 \r\n" + number + b"\r\n",
                case + ": HISTORICAL_PRINTER_CHANGED")
        result = execute(cli,source+b"RUN\n:step 4\n:step\n:quit\n",case+"/RUN")
        require(result.stdout == number+b"\n" and
                b"[cli] RUNNING\n" in result.stderr and
                b"[cli] STEPPED 4\n" in result.stderr and
                b"[cli] END\n" in result.stderr and
                b"[cli:error]" not in result.stderr,
                case + ": NATIVE_VALUE_OR_END_MISMATCH")
        require(printer.split(b"\r\n")[1]+b"\n" == result.stdout and
                printer != result.stdout,case+": CHANNELS_CONFUSED")
        print("PASS",case,"MATCH_EXACT SHA="+anchor,
              "CPC_ERR=0 VALUE="+str(expected),"RUN=END",
              "PRINTER_CRLF_NATIVE_LF_SEPARATE",flush=True)

def negative(image_cli):
    invalid = [
        "B%=A% MOD 256", "B%=A% MOD -1", "B%=A% MOD +1",
        "B%=A% MOD C%-D%", "B%=A% MOD (2)", "B%=A% MOD 1.2",
        "B%=A% MOD 1E2", "B%=A% MOD 1 MOD 2", "B%=A% MOD 1+2",
        "B%=A% MOD 1:PRINT 3:", "B%=A% MOD 2/2",
        "B%=A% MOD 1 MOD 1", "B%=A% MODER 2", "B%=A% MOD1",
        "B%=A% M OD 2", "B%=A% MOD ", "B%=A% MOD MOD 2",
        "B%=A% / 2", "B%=A% MOD 65535"
    ]
    for expression in invalid:
        source=("10 A%=5\n20 "+expression+"\n30 END\n").encode("ascii")
        p=subprocess.run([str(image_cli)],input=source,capture_output=True,
                         timeout=20,check=False)
        require(p.returncode == 2 and not p.stdout and
                b"image-cli: input rejected:" in p.stderr,
                expression + ": UNEXPECTED_ACCEPTANCE")
    for legacy in ("10 B%=A%+3\n20 END\n",
                   "10 B%=A%-3\n20 END\n",
                   "10 B%=-32768\n20 END\n",
                   "10 B%=A%*3\n20 END\n",
                   "10 B%=A%\\3\n20 END\n"):
        require(execute(image_cli,legacy.encode("ascii"),"LEGACY")
                .stdout.endswith(b"\x00\x00"),"OLD_GRAMMAR_REGRESSED")
    # A tokenizable but forbidden compound assignment is covered by the C
    # be_step atomicity test; this differential tests the exact CPC corpus.
    print("PASS 19 negative lexical grammars + legacy plus/minus/multiply/divide/NMIN",
          flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli",type=Path,required=True)
    parser.add_argument("--image-cli",type=Path,required=True)
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    try:
        # Fail closed on ALL original proof bytes before comparing native output.
        manifest=verify_historical(EVIDENCE,permanent=True)
        require(digest(read(EVIDENCE/"manifest.json")) == MANIFEST_SHA,
                "J1_6_A_ORIGINAL_MANIFEST_CHANGED")
        require(len(manifest["captures"]) == len(CASES) and
                all(c["pre_run"]["comparison"]["classification"] == "UNSUPPORTED"
                    for c in manifest["captures"]),
                "HISTORICAL_CASE_SET_CHANGED")
        if args.self_test:
            historical_self_test(EVIDENCE)
        for case in CASES:
            check_case(case,args.cli,args.image_cli)
        negative(args.image_cli)
        print("PASS J1.6-B 12/12 MATCH_EXACT, 10/10 values, 2/2 MOD-by-zero",
              "J1.6-A UNSUPPORTED classifications retained",flush=True)
    except (Invalid, ValueError, OSError, KeyError, TypeError,
            subprocess.TimeoutExpired) as err:
        print("J1.6-B DIFFERENTIAL FAILED:",err,file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
