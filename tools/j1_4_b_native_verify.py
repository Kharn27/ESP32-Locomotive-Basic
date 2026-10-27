#!/usr/bin/env python3
"""J1.4-B live native multiplication vs immutable J1.4-A CPC6128 acquisitions.

Compare complete token RAM program images, not CPC screenshot pixels.
CPC printer CRLF and native stdout LF are separate presentation channels.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_integer_multiplication"
SOURCES = ROOT / "tests/oracles/inputs/j1_4_a"
sys.path.insert(0, str(ROOT / "tools"))
from j1_4_multiplication_verify import (verify as verify_historical,
                                        self_test as historical_self_test)

# Measurements from J1.4-A PR #69; none are derived from native C99.
CASES = {
    "P2_MUL3": (2,3,6,"dfe132427cf99a5965071d8acff1adcd9fa6e4722e49bce7d964c38753100395"),
    "N2_MUL3": (-2,3,-6,"1d62e1f01619a61858248c216e714b6de114d74cb4f5388966fc133c1d0a5c99"),
    "NMIN_MUL0": (-32768,0,0,"e55a95924413a0cec5d20a527ec8a218a926da3581110906867650d01f299c00"),
    "NMIN_MUL1": (-32768,1,-32768,"411992b454c5588d9fd1ce8fd281dd8641a61928869bec1a5212bb9fdc24645f"),
    "PMAX_MUL1": (32767,1,32767,"366c5be2858df72189edc50e48fbad4b6cf3b91319514b8c132255143b45eb71"),
    "PMAX_MUL2": (32767,2,None,"62b006a4bf870ab5ed00f68b23bd6432fdaade235eb66eaae1d7d37e24d65cf1"),
    "P2_MUL255": (2,255,510,"d49706339952a27337d3bc2a2c912d5d2720bc96044c21cb7aa14a42d19328ac"),
    "P255_MUL255": (255,255,None,"90d6a6f88313af1a7e9458f865f5c1882bb76e1d36e799a738322d9130df60c7"),
}
MANIFEST_SHA = "611f655ef0b7100fb51d90a0b473b11ddebd1b41fc7dfbeecf883649214bd26b"

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
    source = (f"10 A%={lhs}\n20 B%=A%*{n}\n"
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
        # The CPC's B%=0 was measured after the error, not as a product.
        require(printer == b" 6 \r\n 0 \r\n",
                case + ": HISTORICAL_OVERFLOW_CHANGED")
        result = execute(cli,source+b"RUN\n:step 2\n:quit\n",case+"/OVERFLOW")
        require(result.stdout == b"" and
                b"[cli] STEPPED 1\n" in result.stderr and
                b"BSR_EXECUTOR_ERROR" in result.stderr and
                b"BE_INTEGER_OVERFLOW" in result.stderr,
                case + ": NATIVE_OVERFLOW_NOT_REPORTED")
        print("PASS",case,"MATCH_EXACT SHA="+anchor,
              "CPC_ERR=6 C99=BE_INTEGER_OVERFLOW OUTPUT=EMPTY",
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
        "B%=A%*256", "B%=A%*-1", "B%=A%* -1", "B%=A%*+1",
        "B%=A%*1*2", "B%=A%*1+2", "B%=A%*C%+D%", "B%=A!*2",
        "B%=A$*2", "B%=A%*(2)", "B%=A%*1.2", "B%=A%*1E2",
        "B%=A%*1:PRINT 2:", "B%=A%*32768", "B%=A%*",
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
                   "10 B%=-32768\n20 END\n"):
        require(execute(image_cli,legacy.encode("ascii"),"LEGACY")
                .stdout.endswith(b"\x00\x00"),"OLD_GRAMMAR_REGRESSED")
    print("PASS 15 negative grammar + legacy addition/subtraction/NMIN",flush=True)

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
                "J1_4_A_ORIGINAL_MANIFEST_CHANGED")
        require(len(manifest["captures"]) == len(CASES),
                "HISTORICAL_CASE_SET_CHANGED")
        if args.self_test:
            historical_self_test(EVIDENCE)
        for case in CASES:
            check_case(case,args.cli,args.image_cli)
        negative(args.image_cli)
        print("PASS J1.4-B 8/8 MATCH_EXACT, 6/6 values, 2/2 overflow",
              "J1.4-A UNSUPPORTED classifications retained",flush=True)
    except (Invalid, ValueError, OSError, KeyError, TypeError,
            subprocess.TimeoutExpired) as err:
        print("J1.4-B DIFFERENTIAL FAILED:",err,file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
