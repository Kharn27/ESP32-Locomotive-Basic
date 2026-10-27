#!/usr/bin/env python3
"""J1.9-B independent native/CPC INTEGER binary-family comparator.

The original J1.9-A seal and all 24 SHA-256 anchors were copied from the
accepted original ROM-backed archive, NEVER from native C99 output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_integer_binary_family"
SOURCES = ROOT / "tests/oracles/inputs/j1_9_a"
MANIFEST_SHA = "8fbe0a11e0d67079980f2344bb9acbde255e1afbc26e4b27f5de2f8bc154fc95"
# Value None means one of the original CPC error observations.
# Each digest is a separate hardcoded independent immutable CPC anchor.
CASES = {
    "M_P2_P3": ("*", 2, 3, 6, 0, "d3cb66026efc6826e04c63c260bfdbc99fae776a20fd54e6b621ab898cb24b98"),
    "M_N3_P4": ("*", -3, 4, -12, 0, "27bc654c89d96545b7d7c6dff2efd668e1cd728546112072e861a620e998e627"),
    "M_N7_N2": ("*", -7, -2, 14, 0, "8f0959db7ede137b729549dda0fdfdd84b2e8961a3300c2d4fc0bc6ca8b9f279"),
    "M_Z_PMAX": ("*", 0, 32767, 0, 0, "6b1ca9c0b4c8b286874afa26a4a0efbe62bf60ca983d2eb2b9430ccc501cb432"),
    "M_NMIN_P1": ("*", -32768, 1, -32768, 0, "4c196f0de970cd847e331d3f18dbe8ecfaa367fbae1246c727351703ed6a5e15"),
    "M_NMIN_N1": ("*", -32768, -1, None, 6, "da0f08dc59f8cecf3455299c0f2091ad458f3b0081cb039b3b6c5e3392c45178"),
    "M_PMAX_P2": ("*", 32767, 2, None, 6, "8a9b774d5ef6567e80c8c454701973186da29946d223927607d29981ac6473ff"),
    "M_P127_P128": ("*", 127, 128, 16256, 0, "d9e4dceda0fac64f294ac0d3097d76e63cded7827611054f1a702ffbdd2ba096"),
    "D_P7_P2": ("\\", 7, 2, 3, 0, "7222953979f82c0d548e9acda401aa5234c58b2ef9aaf553b3fbbaa01c7e331c"),
    "D_N7_P2": ("\\", -7, 2, -3, 0, "19d154dd7779e64be651d932fe69bc251e3acdadd58c098687898bb2a7f885a7"),
    "D_P7_N2": ("\\", 7, -2, -3, 0, "4ed6480ad610a828d3258cf3b3b93176c375b0621c950165c3c40fba2a280d22"),
    "D_N7_N2": ("\\", -7, -2, 3, 0, "9fce0539da372b49b2d609f17b065df7a872fabff817b834fc584e9e8043b42b"),
    "D_NMIN_P1": ("\\", -32768, 1, -32768, 0, "2994aa9aa469562db8e4ae73e40a84ca1e511267e4e57a5368b0148599398be2"),
    "D_NMIN_N1": ("\\", -32768, -1, None, 6, "cf05109b53a2f528f5e170795d7b1fde4f3e371fc90020e53bab2d6f29415f62"),
    "D_P7_Z": ("\\", 7, 0, None, 11, "a4431e0b903a18686c67b260d27704d3cb4b93021ce33af5fbfc1788e6e00376"),
    "D_PMAX_P1": ("\\", 32767, 1, 32767, 0, "886e25388acbd521e24e51056664c0175634f1f5ce3a7721d8dcfcdaa0d6e5ae"),
    "R_P7_P3": (" MOD ", 7, 3, 1, 0, "ffb8666c2e3dd912300db7204ed701000962bec23377779ca149408c8bf0b934"),
    "R_N7_P3": (" MOD ", -7, 3, -1, 0, "b0e38acb8f723440665026613fa3b742786a279800d8658c7eb8a6f03c3d3f32"),
    "R_P7_N3": (" MOD ", 7, -3, 1, 0, "cbc54928c7399b3da62fa53f0adbd5363758ff8d584e2fa9a8b98da41e02efd7"),
    "R_N7_N3": (" MOD ", -7, -3, -1, 0, "5c130ade222817f04efb4a01f68b9834b09d778b2415d3291ac6d9c7f8348a6d"),
    "R_NMIN_N1": (" MOD ", -32768, -1, 0, 0, "61f94553f6f89882718ca6d89f32df9c0dea7e6d5138c007bfb21d68527de574"),
    "R_Z_P3": (" MOD ", 0, 3, 0, 0, "afa62fbc1f70bb6dc53c358daa387cd062cadd8e142318c8c2b6b69d41c3522a"),
    "R_P7_Z": (" MOD ", 7, 0, None, 11, "02f597dc06eac0610a4c9fd0b066b110f3a5752235928a5af58f7605e2c3be4a"),
    "R_NMIN_P255": (" MOD ", -32768, 255, -128, 0, "a5b618a35667b9069f991cf1c209a6e8999a9589abe5e72f5b7037cbaf60554d"),
}
OPCODES = {"*": "F6", "\\": "F9", " MOD ": "FB"}

class Invalid(ValueError):
    pass

def require(ok, label):
    if not ok:
        raise Invalid(label)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    require(path.is_file() and not path.is_symlink(),
            "MISSING_OR_SYMLINK " + str(path))
    return path.read_bytes()

def run(binary, data, label):
    try:
        outcome = subprocess.run([str(binary)], input=data, capture_output=True,
                                 check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Invalid(label + ": C99_PROCESS_FAILED " + str(exc)) from exc
    require(outcome.returncode == 0,
            label + ": C99_EXIT " + repr(outcome.stderr[-280:]))
    return outcome

def check_anchor(name, raw, anchor):
    require(sha(raw) == anchor and raw.endswith(b"\x00\x00"),
            name + ": PINNED_CPC_RAM_DIGEST_MISMATCH")

def historical():
    cmd = [sys.executable, str(ROOT / "tools/j1_9_binary_family_verify.py"),
           "--permanent", "--self-test"]
    p = subprocess.run(cmd, capture_output=True, check=False, timeout=240)
    require(p.returncode == 0,
            "J1.9-A PERMANENCE_FAILED: " + repr(p.stderr[-600:]))
    require(sha(read(EVIDENCE / "manifest.json")) == MANIFEST_SHA,
            "ORIGINAL_MANIFEST_SHA_CHANGED")
    seal = json.loads(read(EVIDENCE / "seal.json"))
    require(seal.get("manifest_sha256") == MANIFEST_SHA and
            set(seal.get("program_sha256", {})) == set(CASES),
            "ORIGINAL_SEAL_CHANGED")
    manifest = json.loads(read(EVIDENCE / "manifest.json"))
    captures = manifest.get("captures", [])
    require(len(captures) == 24 and
            {x["case"] for x in captures} == set(CASES) and
            manifest.get("phase") == "J1.9-A" and
            manifest.get("j1_9_b_authorized") is False,
            "ORIGINAL_PROVENANCE_CHANGED")
    for name, (op, a, b, result, err, anchor) in CASES.items():
        item = next(x for x in captures if x["case"] == name)
        require(item["operation"] == ("MUL" if op == "*" else
                                      "IDIV" if op == "\\" else "MOD") and
                item["lhs"] == a and item["rhs"] == b and
                item["pre_run"]["comparison"]["classification"] == "UNSUPPORTED" and
                item["run"]["native_status"] == "UNSUPPORTED" and
                item["pre_run"]["operator_observed_hex"] == OPCODES[op] and
                item["run"]["err_probe"] == err and
                item["run"]["variable_probe"] == (0 if result is None else result) and
                item["pre_run"]["comparison"]["cpc_sha256"] == anchor and
                seal["program_sha256"][name] == anchor,
                name + ": ORIGINAL_HISTORICAL_OBSERVATION_CHANGED")
        check_anchor(name, read(EVIDENCE / name / "program.bin"), anchor)
    print("PASS J1.9-A permanent self-test, original immutable 24 SHA and manifest",
          flush=True)

def one(name, values, cli, image_cli):
    op, a, b, result, err, anchor = values
    source = (f"10 A%={a}\n20 B%={b}\n30 C%=A%{op}B%\n"
              "40 PRINT C%\n50 END\n").encode("ascii")
    require(read(SOURCES / (name.lower()+".bas")) == source and
            read(EVIDENCE / name / "original.bas") == source,
            name + ": ORIGINAL_SOURCE_CHANGED")
    original = read(EVIDENCE / name / "program.bin")
    check_anchor(name, original, anchor)
    native = run(image_cli, source, name + "/IMAGE").stdout
    require(native == original and sha(native) == anchor,
            name + ": RAM_NOT_MATCH_EXACT")
    listed = run(cli, source+b"LIST\n:quit\n", name+"/LIST")
    require(listed.stdout == source and b"[cli:error]" not in listed.stderr,
            name + ": FULL_LIST_MISMATCH")
    # Direct CPC printer probes are not screen bytes. Never compare PNG pixels.
    printer = read(EVIDENCE / name / "run/printer.dat")
    expected_printer = (
        (" " + str(err) + " \r\n" +
         (" " if (result is None or result >= 0) else "") +
         str(0 if result is None else result) + " \r\n").encode("ascii")
    )
    require(printer == expected_printer, name + ": CPC_PRINTER_OR_ERROR_CHANGED")
    if result is None:
        expected = b"BE_INTEGER_OVERFLOW" if err == 6 else b"BE_DIVISION_BY_ZERO"
        actual = run(cli, source+b"RUN\n:step 5\n:quit\n", name+"/ERROR")
        require(actual.stdout == b"" and expected in actual.stderr and
                b"[cli] STEPPED 2\n" in actual.stderr,
                name+": ERROR_CLASS_OR_OUTPUT_MISMATCH")
    else:
        actual = run(cli, source+b"RUN\n:step 5\n:step\n:quit\n",
                     name+"/EXEC")
        text = ((b" " if result >= 0 else b"") +
                str(result).encode("ascii") + b" \n")
        require(actual.stdout == text and
                b"[cli] STEPPED 5\n" in actual.stderr and
                b"[cli] END\n" in actual.stderr and
                b"[cli:error]" not in actual.stderr,
                name+": PRINT_OR_END_MISMATCH")
        # Only printer transport CRLF -> LF is normalized.
        require(printer.split(b"\r\n")[1] + b"\n" == actual.stdout,
                name+": PRINTER_TRANSPORT_NORMALIZATION_FAILED")
    print("PASS",name, "MATCH_EXACT", "LIST_EXACT",
          "VALUE="+str(result) if result is not None else "ERR="+str(err),
          "CPC_ATOMICITY_UNVERIFIED", "RAM_SHA="+anchor, flush=True)

def negative(image_cli):
    invalid = (
        r"C%=A%*B%+D%", r"C%=A%\B%*C%", "C%=A% MOD B%-D%",
        r"C%=A%/(B%)", r"C%=A%/B%", "C%=A% MODX B%",
        "C%=A% MOD B!", "C%=A%*B$", r"C%=A%\B%=D%",
        r"C%=A%\B%*D%", "C%=A% MOD B%+C%"
    )
    for expr in invalid:
        data = ("10 A%=7\n20 B%=3\n30 "+expr+"\n40 END\n").encode("ascii")
        p = subprocess.run([str(image_cli)], input=data,
                           capture_output=True, check=False, timeout=25)
        require(p.returncode == 2 and p.stdout == b"",
                expr+": FORBIDDEN_GRAMMAR_ACCEPTED")
    for old in ("C%=A%+B%", "C%=A%-B%", "C%=A%-3",
                "B%=-32768", "C%=A%*3", r"C%=A%\3",
                "C%=A% MOD 3"):
        p = run(image_cli, ("10 "+old+"\n20 END\n").encode(), "LEGACY")
        require(p.stdout.endswith(b"\x00\x00"), "LEGACY_BROKEN "+old)
    print("PASS restricted grammar + seven legacy syntaxes", flush=True)

def self_test():
    # Corrupt a separate temporary copy of an original from EACH family.
    # The original archived bytes and pinned source digests never change.
    with tempfile.TemporaryDirectory(prefix="j19b-falsify-") as folder:
        for case in ("M_P2_P3", "D_P7_P2", "R_P7_P3"):
            anchor = CASES[case][-1]
            clone = Path(folder) / (case+".bin")
            shutil.copyfile(EVIDENCE / case / "program.bin", clone)
            data = bytearray(read(clone))
            data[6] ^= 0x01
            clone.write_bytes(data)
            try:
                check_anchor(case, read(clone), anchor)
            except Invalid as exc:
                require("PINNED_CPC_RAM_DIGEST_MISMATCH" in str(exc),
                        case+": UNEXPECTED_FALSIFICATION_REJECTION")
            else:
                raise Invalid(case+": CORRUPTED_REFERENCE_ACCEPTED")
            check_anchor(case, read(EVIDENCE/case/"program.bin"), anchor)
            print("PASS",case,"temporary corrupted original rejected",flush=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cli", type=Path, required=True)
    p.add_argument("--image-cli", type=Path, required=True)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    try:
        historical()
        for name, row in CASES.items():
            one(name,row,args.cli,args.image_cli)
        negative(args.image_cli)
        if args.self_test: self_test()
        normal = sum(v[3] is not None for v in CASES.values())
        over = sum(v[4] == 6 for v in CASES.values())
        zero = sum(v[4] == 11 for v in CASES.values())
        require((normal,over,zero) == (19,3,2),
                "CASE_COVERAGE_CHANGED")
        print("J1.9-B PASS 24/24 RAM MATCH_EXACT, 24/24 LIST,",
              "19/19 NUMERIC, 3/3 OVERFLOW, 2/2 DIV_ZERO;",flush=True)
        return 0
    except (Invalid, OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print("J1.9-B DIFFERENTIAL FAILED:",exc,file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
