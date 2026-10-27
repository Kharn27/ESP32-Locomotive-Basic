#!/usr/bin/env python3
"""J1.8-B live C99 F5 subtraction versus immutable original CPC6128 J1.8-A.

A CPC post-ERR probe cannot establish ROM assignment atomicity. The C99
rollback is independently covered by test_basic_integer_sub_vars.c.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_integer_sub_vars"
SOURCES = ROOT / "tests/oracles/inputs/j1_8_a"

# Copied independently from J1.8-A's accepted seal, not learnt from C99 output.
MANIFEST_SHA = "d087c7f9d1dccf4670ad0bb5e2b3443b2ba1ec7646e7a8da5f52de090cea1a3d"
CASES = {
    "P2_P3": (2,3,-1,"f4c0a93362bb621b5c2b5e294fe33d11fb7fcf88ad3c0dc8aaec69899cbdca86"),
    "P7_N2": (7,-2,9,"20d00ca4e89cb20981a348f386e4d22489be64092b4bb56a0a4e530c0ae678e1"),
    "N7_P2": (-7,2,-9,"db6de6512a1c2764af1a28fdf48f33b40f11d95363ae3179df4e39a0c7bf24be"),
    "N7_N3": (-7,-3,-4,"013560abb954eaa41547bd7a8ddd76689a8583c0a4ed7062c14b97da967719bc"),
    "NMIN_N1": (-32768,-1,-32767,"6ba2eb93abb43c91efb16e504775732c72e80768a464f9fa8e4c1658fa32d09e"),
    "NMIN_Z": (-32768,0,-32768,"f75849f897986a151dbc8db6488351df333079bc1bbebf0e70df1ba590733304"),
    "PMAX_Z": (32767,0,32767,"21baa2bfcbf07df0be4afdab144305cc87a25063cd61cb4e3bac29f9dd7641bc"),
    "PMAX_N1": (32767,-1,None,"cbed61c9685aa50e291c3246ac77413402963aa9011ac650b2b062ccea2f7245"),
    "NMIN_P1": (-32768,1,None,"da36695d14a6fe11382153c28aa55cbcd8de127feb14818f2a8d9573199b3cd8"),
    "P255_P255": (255,255,0,"8a86c014f995573d2c3393fac608d4edd274e59710617394be8425114d5a856a"),
    "Z_Z": (0,0,0,"a5a39d734b0fcd2a8d1ec46d8fc8edf4199fcd933a1ee75360736213bc3c9e30"),
    "P1_N1": (1,-1,2,"d3de0932d1c5681e54c52054813475485aae650cd1db992870288cff44c92aa7"),
}
class Invalid(ValueError):
    pass

def require(ok, label):
    if not ok:
        raise Invalid(label)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    require(path.is_file() and not path.is_symlink(),
            "ORIGINAL_MISSING_OR_SYMLINK " + str(path))
    return path.read_bytes()

def run(binary, data, case):
    try:
        outcome = subprocess.run([str(binary)], input=data, capture_output=True,
                                 check=False, timeout=25)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Invalid(case + ": EXECUTION_FAILED " + str(exc)) from exc
    require(outcome.returncode == 0,
            case + ": NATIVE_FAILED " + repr(outcome.stderr[:240]))
    return outcome

def historical():
    # Force the historical 18 mutation tests + forged HEAD test to execute.
    cmd = [sys.executable, str(ROOT / "tools/j1_8_sub_vars_verify.py"),
           "--permanent", "--self-test"]
    result = subprocess.run(cmd, capture_output=True, check=False, timeout=180)
    require(result.returncode == 0,
            "J1.8-A PERMANENCE/14 FALSIFICATIONS FAILED: " +
            repr(result.stderr[-500:]))
    require(sha(read(EVIDENCE / "manifest.json")) == MANIFEST_SHA,
            "J1.8-A MANIFEST UNSEALED")
    seal = json.loads(read(EVIDENCE / "seal.json"))
    require(seal["manifest_sha256"] == MANIFEST_SHA and
            len(seal["program_sha256"]) == 12 and
            set(seal["program_sha256"]) == set(CASES),
            "J1.8-A SEAL METADATA CHANGED")
    manifest = json.loads(read(EVIDENCE / "manifest.json"))
    require(len(manifest["captures"]) == 12 and
            {c["case"] for c in manifest["captures"]} == set(CASES) and
            all(c["pre_run"]["comparison"]["classification"] == "UNSUPPORTED"
                for c in manifest["captures"]), "HISTORICAL_CLASSIFICATION_MODIFIED")
    for name, (_, _, _, anchor) in CASES.items():
        require(seal["program_sha256"][name] == anchor, name+": SEALED_SHA_CHANGED")
    print("PASS J1.8-A --permanent --self-test, 18 falsifications + forged HEAD")

def one(name, values, cli, image_cli):
    a, b, result, anchor = values
    source = (f"10 A%={a}\n20 B%={b}\n30 C%=A%-B%\n"
              "40 PRINT C%\n50 END\n").encode("ascii")
    require(read(SOURCES/(name.lower()+".bas")) == source and
            read(EVIDENCE/name/"original.bas") == source,
            name+": SOURCE_CHANGED")
    original = read(EVIDENCE/name/"program.bin")
    require(sha(original) == anchor and original.endswith(b"\0\0"),
            name+": ORIGINAL_IMAGE_CHANGED")
    binary = run(image_cli, source, name+"/IMAGE").stdout
    require(binary == original and sha(binary) == anchor,
            name+": RAM_NOT_MATCH_EXACT")
    # Full contiguous CPC 5-record program, including opaque BVR cache,
    # lengths, line numbers, separators and final two-zero sentinel.
    listing = run(cli, source+b"LIST\n:quit\n", name+"/LIST")
    require(listing.stdout == source and b"[cli:error]" not in listing.stderr,
            name+": LIST_MISMATCH")
    printer = read(EVIDENCE/name/"run/printer.dat")
    if result is None:
        require(printer == b" 6 \r\n 0 \r\n",
                name+": HISTORICAL_ERR6_PRINTER_CHANGED")
        actual = run(cli, source+b"RUN\n:step 5\n:quit\n", name+"/OVERFLOW")
        require(actual.stdout == b"" and
                b"BE_INTEGER_OVERFLOW" in actual.stderr and
                b"[cli] STEPPED 2\n" in actual.stderr,
                name+": OVERFLOW_NOT_ATOMIC_OR_STATUS_MISMATCH")
        print("PASS",name,"MATCH_EXACT LIST_EXACT CPC_ERR=6",
              "C99=BE_INTEGER_OVERFLOW OUTPUT=EMPTY CPC_ATOMICITY=UNKNOWN",
              "SHA="+anchor,flush=True)
    else:
        text = (b" " if result >= 0 else b"") + str(result).encode("ascii") + b" "
        require(printer == b" 0 \r\n"+text+b"\r\n",
                name+": HISTORICAL_PRINTER_CHANGED")
        actual = run(cli, source+b"RUN\n:step 5\n:step\n:quit\n", name+"/RUN")
        require(actual.stdout == text+b"\n" and
                b"[cli] STEPPED 5\n" in actual.stderr and
                b"[cli] END\n" in actual.stderr and
                b"[cli:error]" not in actual.stderr,
                name+": NUMERIC_VALUE_OR_END_DIFFERENT")
        # Only transport CRLF (printer) -> LF (Linux) is normalized.
        require(printer.split(b"\r\n")[1]+b"\n" == actual.stdout and
                printer != actual.stdout, name+": CHANNELS_NOT_DISTINGUISHED")
        print("PASS",name,"MATCH_EXACT LIST_EXACT CPC_ERR=0",
              "VALUE="+str(result),"CPC_PRINTER_CRLF_NATIVE_LF",
              "SHA="+anchor,flush=True)

def negative(image_cli):
    lexical = ("C%=A%-B%-D%", "C%=A%-(B%)", "C%=A%-B%*C%",
               "C%=A%-B%=D%", "C%=A%-2-B%", "C%=A%-B$",
               "C%=A%-B!", "C%=A%-B%%", "C%=A%--B%",
               "C%=A%+B%+C%", "C%=A%+(B%)", "C%=A%+B%*C%",
               "C%=A%+B%=C%", "C%=A%+2+B%", "C%=A%+B$",
               "C%=A%+B!", "C%=A%*B%+D%", "C%=A%-B%-D%", "C%=A%\\B%*C%",
               "C%=A% MOD B%-D%", "C%=A%+B%%")
    for expr in lexical:
        data = ("10 A%=1\n20 B%=2\n30 "+expr+"\n40 END\n").encode("ascii")
        outcome = subprocess.run([str(image_cli)], input=data,
                                 capture_output=True, check=False, timeout=25)
        require(outcome.returncode == 2 and outcome.stdout == b"",
                expr+": UNEXPECTED_LEXICAL_ADMISSION")
    for old in ("B%=A%+3", "B%=A%-3", "B%=A%*3",
                "B%=A%\\3", "B%=A% MOD 3", "B%=-32768"):
        image = run(image_cli, ("10 "+old+"\n20 END\n").encode(),
                    "LEGACY")
        require(image.stdout.endswith(b"\x00\x00"),
                "LEGACY_REGRESSION "+old)
    print("PASS out-of-scope lexical rejections and 6 legacy syntaxes")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli",type=Path,required=True)
    parser.add_argument("--image-cli",type=Path,required=True)
    parser.add_argument("--self-test",action="store_true")
    args = parser.parse_args()
    try:
        historical()
        for name, values in CASES.items():
            one(name,values,args.cli,args.image_cli)
        negative(args.image_cli)
        print("PASS J1.8-B 12/12 RAM MATCH_EXACT, 12/12 LIST,",
              "10/10 INTEGER, 2/2 OVERFLOW;",
              "historical UNSUPPORTED remains sealed", flush=True)
    except (Invalid, ValueError, OSError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print("J1.8-B DIFFERENTIAL FAILED:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
