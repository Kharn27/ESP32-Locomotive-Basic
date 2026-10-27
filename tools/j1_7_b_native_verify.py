#!/usr/bin/env python3
"""J1.7-B live C99 F4 addition versus immutable original CPC6128 J1.7-A.

A CPC post-ERR probe cannot establish ROM assignment atomicity. The C99
rollback is independently covered by test_basic_integer_add_vars.c.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_integer_add_vars"
SOURCES = ROOT / "tests/oracles/inputs/j1_7_a"

# Copied independently from J1.7-A's accepted seal, not learnt from C99 output.
MANIFEST_SHA = "0608ba7d9548bae7972f02d0a929d0abde70fc325f49af97175f915aae08e2d5"
CASES = {
    "P2_P3": (2,3,5,"f6633183dcec7b06efdabd5a4d17b1d100352c1c9f23fe934b5f4cf443842220"),
    "P7_N2": (7,-2,5,"847cc4a6210d112ae40ff6077ce03a53c3f1d393313502d855b838f21f28bd1e"),
    "N7_P2": (-7,2,-5,"8b56356703e3738f091da3cf99c86cc9b261ec8c4d0ea383dac61722f7b6118d"),
    "N7_N3": (-7,-3,-10,"fe78f54904512e20bf8bccaf2e226fc1cb5bc3d0238730be9b378dde241a8d0c"),
    "NMIN_P1": (-32768,1,-32767,"15bdf377f4c8365d612e46db77b235067695a63f21631d2d6be5affec05c54fc"),
    "NMIN_Z": (-32768,0,-32768,"aeba202bcc5ffc715d7b617b671463e1b2d381dc35b932679b8e8476af4a4d3a"),
    "PMAX_Z": (32767,0,32767,"decbdbbd4049ae524219648f13f8deeefdc422c3089ba273278c366d46397103"),
    "PMAX_P1": (32767,1,None,"36a9f5ccb3f358a53c5822bbbbb98fa09adb6f3cfad36e44d9e08cea1ffbe010"),
    "NMIN_N1": (-32768,-1,None,"694845f8a620834b2150bb818e9bb9782ec395354154a7675d8304e5f857559d"),
    "P255_P255": (255,255,510,"7ee4fa53dad3a6b8bb645749ddea737c26c149ae2f8980e0dc66a5f14b3f4c9b"),
    "Z_Z": (0,0,0,"19c2e42164e0a26fcaef634df9d17ceee19b9c297f33be3497f72e3df3c96c87"),
    "P1_N1": (1,-1,0,"a5c10abb1a874c2c6c75b1ae63a310080a8f9d24aef7c2b74ce72b37d64ed08d"),
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
    # Force the historical 14 mutation tests + forged HEAD test to execute.
    cmd = [sys.executable, str(ROOT / "tools/j1_7_add_vars_verify.py"),
           "--permanent", "--self-test"]
    result = subprocess.run(cmd, capture_output=True, check=False, timeout=180)
    require(result.returncode == 0,
            "J1.7-A PERMANENCE/14 FALSIFICATIONS FAILED: " +
            repr(result.stderr[-500:]))
    require(sha(read(EVIDENCE / "manifest.json")) == MANIFEST_SHA,
            "J1.7-A MANIFEST UNSEALED")
    seal = json.loads(read(EVIDENCE / "seal.json"))
    require(seal["manifest_sha256"] == MANIFEST_SHA and
            len(seal["program_sha256"]) == 12 and
            set(seal["program_sha256"]) == set(CASES),
            "J1.7-A SEAL METADATA CHANGED")
    manifest = json.loads(read(EVIDENCE / "manifest.json"))
    require(len(manifest["captures"]) == 12 and
            {c["case"] for c in manifest["captures"]} == set(CASES) and
            all(c["pre_run"]["comparison"]["classification"] == "UNSUPPORTED"
                for c in manifest["captures"]), "HISTORICAL_CLASSIFICATION_MODIFIED")
    for name, (_, _, _, anchor) in CASES.items():
        require(seal["program_sha256"][name] == anchor, name+": SEALED_SHA_CHANGED")
    print("PASS J1.7-A --permanent --self-test, 14 falsifications + forged HEAD")

def one(name, values, cli, image_cli):
    a, b, result, anchor = values
    source = (f"10 A%={a}\n20 B%={b}\n30 C%=A%+B%\n"
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
    lexical = ("C%=A%+B%+C%", "C%=A%+(B%)", "C%=A%+B%*C%",
               "C%=A%+B%=C%", "C%=A%+2+B%", "C%=A%+B$",
               "C%=A%+B!", "C%=A%*B%", "C%=A%-B%", "C%=A%\\B%",
               "C%=A% MOD B%", "C%=A%+B%%")
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
    print("PASS 12 out-of-scope lexical rejections and 6 legacy syntaxes")

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
        print("PASS J1.7-B 12/12 RAM MATCH_EXACT, 12/12 LIST,",
              "10/10 INTEGER, 2/2 OVERFLOW;",
              "historical UNSUPPORTED remains sealed", flush=True)
    except (Invalid, ValueError, OSError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print("J1.7-B DIFFERENTIAL FAILED:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
