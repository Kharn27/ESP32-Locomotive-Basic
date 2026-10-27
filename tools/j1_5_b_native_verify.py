#!/usr/bin/env python3
"""J1.5-B live native F9 INTEGER division vs immutable J1.5-A CPC6128 acquisitions.

Compare complete token RAM program images, not CPC screenshot pixels.
CPC printer CRLF and native stdout LF are separate presentation channels.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_integer_division"
SOURCES = ROOT / "tests/oracles/inputs/j1_5_a"
sys.path.insert(0, str(ROOT / "tools"))
from j1_5_division_verify import (verify as verify_historical,
                                        self_test as historical_self_test)

# Immutable SHA256 anchors transcribed from sealed J1.5-A ROM-backed captures.
# ERR=11 zero-divisor probes are NOT arithmetic results.
CASES = {
    "P6_ID3": (6, 3, 2, "d4fbb0dfe3f6b874eb6932eb90b16598d6c7514af8790a3aa6c26eea740cdb07"),
    "P7_ID2": (7, 2, 3, "0ff9fdee358a91cbef00a47219ce904b786f20d5a5bef930315ca13f5faa4e1a"),
    "P5_ID2": (5, 2, 2, "dae3e2d47ba7f3f1f7156c077ba50b87c758d855711c53dbd7eefc1b26806f4f"),
    "N7_ID2": (-7, 2, -3, "c0068ea334a9e941e528c4d491831ec371e33e3aa862c46e916c22ec96d295e8"),
    "N5_ID2": (-5, 2, -2, "d08422983da6d4ab45ca2648f4beea41a26154050d36b51b708a5f98ae98b58e"),
    "NMIN_ID1": (-32768, 1, -32768, "31ce0ad77b0f7f76eda2ebaefc61acfa89f3b33fe4faee330a313e8876b9fed9"),
    "PMAX_ID1": (32767, 1, 32767, "dabc95d3be65f5649f3f442fed897b69dfc669fc7d7f4246a6ffdb79e2ad52be"),
    "PMAX_ID2": (32767, 2, 16383, "515aedc84ff55093ea78de78e3cc1ebefbc48191f557006caa6957c340fbdc81"),
    "P1_ID0": (1, 0, None, "7368cdec51577a2d3db10a1b56eb80c6ef042cef5a0cc299b19725bc6f110753"),
    "P0_ID0": (0, 0, None, "556cf7ec33b79af8d191dc1aab8656fe11552de5f81e51e915772a08c7450ab7"),
    "P255_ID255": (255, 255, 1, "05d99328ff550cd3e719665b6ed2041180cf5b9499c9e1241b4e81c582079209"),
    "P2_ID255": (2, 255, 0, "b52011685b947e4d20d7b642aef2243a1f0ded2ba695c56e643bf24adde575b3"),
}
MANIFEST_SHA = "af4b873f62e0fa8304f9389c149dcc6475463c498eea6834d4ce6ffda60ba5b9"

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
    source = (f"10 A%={lhs}\n20 B%=A%\\{n}\n"
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
        r"B%=A%\256", r"B%=A%\-1", r"B%=A%\ -1", r"B%=A%\+1",
        r"B%=A%\1\2", r"B%=A%\1+2", r"B%=A%\C%", r"B%=A!\2",
        r"B%=A$\2", r"B%=A%\(2)", r"B%=A%\1.2", r"B%=A%\1E2",
        r"B%=A%\1:PRINT 2:", r"B%=A%\32768", "B%=A%\\",
        "B%=A%/2", r"B%=A%\2/2"
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
                   "10 B%=A%*3\n20 END\n"):
        require(execute(image_cli,legacy.encode("ascii"),"LEGACY")
                .stdout.endswith(b"\x00\x00"),"OLD_GRAMMAR_REGRESSED")
    # A tokenizable but forbidden compound assignment is covered by the C
    # be_step atomicity test; this differential tests the exact CPC corpus.
    print("PASS 17 negative lexical grammars + legacy plus/minus/multiply/NMIN",
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
                "J1_5_A_ORIGINAL_MANIFEST_CHANGED")
        require(len(manifest["captures"]) == len(CASES) and
                all(c["pre_run"]["comparison"]["classification"] == "UNSUPPORTED"
                    for c in manifest["captures"]),
                "HISTORICAL_CASE_SET_CHANGED")
        if args.self_test:
            historical_self_test(EVIDENCE)
        for case in CASES:
            check_case(case,args.cli,args.image_cli)
        negative(args.image_cli)
        print("PASS J1.5-B 12/12 MATCH_EXACT, 10/10 values, 2/2 division-by-zero",
              "J1.5-A UNSUPPORTED classifications retained",flush=True)
    except (Invalid, ValueError, OSError, KeyError, TypeError,
            subprocess.TimeoutExpired) as err:
        print("J1.5-B DIFFERENTIAL FAILED:",err,file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
