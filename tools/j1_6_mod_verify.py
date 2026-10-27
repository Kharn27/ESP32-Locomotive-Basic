#!/usr/bin/env python3
"""J1.6-A CPC mod evidence: fail-closed independent archive checker.

The mod opcode and mod-by-zero observations MUST be measured from CPC RAM
and printer, not assumed from C99 or inferred using host arithmetic.
No screen/console/printer byte-equivalence is claimed.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/oracles"))
import token_ram_oracle as oracle
from signed_print_oracle import parse_integer
from j1_6_mod_oracle import CASES, validate_checkout_identity

BASE = ROOT / "tests/fixtures/cpc6128/j1_integer_mod"
# Known historical INTEGER literal signatures, but NO assumed mod token.
LHS = {
    "P6_M3": "14", "P7_M2": "15",
    "N7_M2": "F5 15", "N7_M3": "F5 15", "N5_M2": "F5 13",
    "NMIN_M1": "F5 1F 00 00 00 00 90",
    "NMIN_M255": "F5 1F 00 00 00 00 90",
    "PMAX_M255": "1A FF 7F", "P2_M255": "10",
    "P255_M255": "19 FF", "P1_M0": "0F", "P0_M0": "0E",
}
def magnitude_token(value):
    return bytes([0x0e + value]) if value < 10 else bytes([0x19, value])

PRE_ALLOWED = {"original.bas", "program.bin", "c99.bin", "c99_error.txt",
               "cap32.cfg", "autocmd.json", "caprice.log", "list.png",
               "comparison.json"}
RUN_ALLOWED = {"cap32.cfg", "autocmd.json", "caprice.log", "run.png",
               "printer.dat", "native.stdin.bin", "native.stdout.bin",
               "native.stderr.bin"}
FORBIDDEN = {".sna", ".rom", ".dsk", ".cpr", ".zip", ".img"}

class Invalid(ValueError):
    pass

def require(predicate, cause):
    if not predicate:
        raise Invalid(cause)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def checked_file(path, root, record, case):
    require(path.is_file() and not path.is_symlink() and
            path.resolve().is_relative_to(root.resolve()), case + ": FILE_ABSENT")
    require(path.suffix.lower() not in FORBIDDEN, case + ": FORBIDDEN_FILE")
    data = path.read_bytes()
    require(len(data) == record["size_bytes"] and sha(data) == record["sha256"],
            case + ": FILE_DIGEST_CHANGED")
    return data

def png(data, name):
    require(len(data) > 32 and data[:8] == b"\x89PNG\r\n\x1a\n" and
            data[12:16] == b"IHDR", name + ": INVALID_PNG")

def lines_of(raw, numbers):
    numbers_found, rows = oracle.records(raw)
    require(numbers_found == numbers, "PROGRAM_LINES_CHANGED")
    return [raw[x["offset"]:x["offset"] + x["length"]] for x in rows], rows

def seal_for(base, m):
    return {
        "schema": 1, "phase": "J1.6-A-PROVISIONAL",
        "approval": "PENDING_PILOTAGE",
        "manifest_sha256": sha((base / "manifest.json").read_bytes()),
        "acquisition_run_id": m["github_run_id"],
        "acquisition_head_sha": m["github_head_sha"],
        "program_sha256": {
            c["case"]: sha((base / c["case"] / "program.bin").read_bytes())
            for c in m["captures"]
        },
    }

def verify(base, permanent=False):
    require((base / "manifest.json").is_file(), "MANIFEST_ABSENT")
    m = json.loads((base / "manifest.json").read_text())
    require(m.get("schema_version") == 1 and m.get("phase") == "J1.6-A" and
            m.get("rom_archived") is False and
            m.get("snapshots_archived") is False and
            m.get("screen_bytes_extracted") is False and
            m.get("printer_screen_equivalent") is False and
            m.get("screen_vs_printer") == "NOT_BYTE_COMPARABLE" and
            m.get("j1_6_b_authorized") is False and
            m.get("historical_list_run") == "UNVERIFIED" and
            m.get("historical_archives_modified") is False,
            "HISTORICAL_GUARD_CHANGED")
    ref = m.get("oracle", {})
    require(ref.get("emulator") == "Caprice32" and
            ref.get("commit") == oracle.PIN and
            ref.get("rom_sha256") == oracle.ROM_SHA and
            ref.get("model") == "CPC6128" and ref.get("basic") == "1.1" and
            ref.get("ram_kb") == 128, "ORACLE_PROVENANCE_CHANGED")
    require(re.fullmatch("[0-9a-f]{40}", str(m.get("github_head_sha", ""))) and
            re.fullmatch("[0-9]+", str(m.get("github_run_id", ""))),
            "ACQUISITION_IDENTITY_MISSING")
    captures = m.get("captures", [])
    require(len(captures) == 12 and
            {c.get("case") for c in captures} == set(CASES),
            "CASE_SET_CHANGED")
    operator_values = set()
    inventory = {"manifest.json"} | ({"seal.json"} if permanent else set())
    for c in captures:
        name = c["case"]
        lhs, rhs = CASES[name]
        require(c.get("lhs") == lhs and c.get("rhs") == rhs and
                c.get("source_path") == f"tests/oracles/inputs/j1_6_a/{name.lower()}.bas",
                name + ": CASE_PARAMETERS_CHANGED")
        expected = (f"10 A%={lhs}\n20 B%=A% MOD {rhs}\n"
                    "30 PRINT B%\n40 END\n").encode("ascii")
        require((ROOT / c["source_path"]).read_bytes() == expected,
                name + ": SOURCE_CHANGED")
        pre = c["pre_run"]
        require(c.get("source_admission") == "STORED_PROGRAM" and
                 pre["case"] == name and
                pre["source_sha256"] == sha(expected) and
                pre["snapshot_taken_before_run"] is True and
                pre["list_requested"] is True, name + ": LIST_PROVENANCE_CHANGED")
        files = pre["files"]
        require(set(files).issubset(PRE_ALLOWED) and
                set(files) >= {"original.bas", "program.bin", "list.png",
                               "autocmd.json", "caprice.log", "cap32.cfg",
                               "comparison.json"} and
                (("c99.bin" in files) != ("c99_error.txt" in files)),
                name + ": PRE_INVENTORY_CHANGED")
        for key, item in files.items():
            checked_file(base / name / key, base, item, name)
            inventory.add(f"{name}/{key}")
        require((base / name / "original.bas").read_bytes() == expected,
                name + ": SOURCE_NOT_ACQUIRED")
        png((base / name / "list.png").read_bytes(), name + "/LIST")
        commands = json.loads((base / name / "autocmd.json").read_text())["commands"]
        require(commands[:4] == expected.decode("ascii").splitlines() and
                 "LIST" in commands and not any(x == "RUN" for x in commands),
                name + ": LIST_SEQUENCE_CHANGED")
        raw = (base / name / "program.bin").read_bytes()
        rows, records = lines_of(raw, [10, 20, 30, 40])
        require(pre["region"]["line_numbers"] == [10,20,30,40] and
                pre["region"]["length"] == len(raw) and
                pre["region"]["records"] == records and
                pre["region"]["sentinel_offset"] == len(raw)-2,
                name + ": PROGRAM_BOUNDS_CHANGED")
        require(rows[0].endswith(bytes.fromhex(LHS[name]) + b"\0") and
                rows[0].count(b"\xf5") == (1 if lhs < 0 else 0),
                name + ": UNARY_SIGN_SIGNATURE_CHANGED")
        # The operator was read from the original RAM, independently for each case.
        opcode_hex = pre.get("operator_observed_hex")
        require(isinstance(opcode_hex, str) and
                re.fullmatch(r"[0-9A-F]{2}(?: [0-9A-F]{2})?", opcode_hex),
                name + ": MISSING_CPC_OPERATOR_OBSERVATION")
        token = bytes.fromhex(opcode_hex)
        require(token[0] >= 0x80 and
                (len(token) == 1 or token[0] == 0xFF),
                name + ": MOD_NOT_A_TOKEN")
        operator_values.add(token)
        rhs_tail = magnitude_token(rhs) + b"\0"
        between = rows[1][13:-len(rhs_tail)]
        require(rows[1].endswith(rhs_tail) and
                between.strip(b" ") == token and
                between.hex(" ").upper() == pre["expression_bytes_hex"],
                name + ": BINARY_MOD_SIGNATURE_CHANGED")
        compare = pre["comparison"]
        require(json.loads((base / name / "comparison.json").read_text()) == compare,
                name + ": COMPARISON_REPORT_CHANGED")
        require(compare["cpc_sha256"] == sha(raw) and
                compare["cpc_size"] == len(raw),
                name + ": TOKEN_MANIFEST_CHANGED")
        if "c99.bin" in files:
            native = (base / name / "c99.bin").read_bytes()
            lines_of(native, [10,20,30,40])
            classification = "MATCH_EXACT" if native == raw else "DIFF"
            require(compare["classification"] == classification and
                    compare["c99_sha256"] == sha(native) and
                    compare["c99_size"] == len(native),
                    name + ": TOKEN_CLASSIFICATION_FALSE")
        else:
            rejection = (base / name / "c99_error.txt").read_bytes()
            require(compare["classification"] == "UNSUPPORTED" and
                    compare["c99_sha256"] is None and
                    compare["c99_size"] is None and
                    b"image-cli: input rejected:" in rejection,
                    name + ": TOKEN_CLASSIFICATION_FALSE")
        run = c["run"]
        require(run["fresh_cpc_run_session"] is True and
                 run.get("process_count_for_case") == 2 and
                run["screenshot"] == "VISUAL_OBSERVATION" and
                "never screen bytes" in run["printer_semantics"],
                name + ": RUN_CHANNELS_CHANGED")
        require(set(run["files"]) == RUN_ALLOWED,
                name + ": RUN_INVENTORY_CHANGED")
        for key, item in run["files"].items():
            checked_file(base / name / "run" / key, base, item, name + "/RUN")
            inventory.add(f"{name}/run/{key}")
        png((base / name / "run/run.png").read_bytes(), name + "/RUN")
        run_cmds = json.loads((base / name / "run/autocmd.json").read_text())["commands"]
        require(run_cmds[:4] == expected.decode("ascii").splitlines() and
                 "RUN" in run_cmds and "PRINT #8,ERR" in run_cmds and
                "PRINT #8,B%" in run_cmds and
                run_cmds.index("RUN") < run_cmds.index("PRINT #8,ERR") <
                run_cmds.index("PRINT #8,B%"),
                name + ": RUN_SEQUENCE_CHANGED")
        printer = (base / name / "run/printer.dat").read_bytes()
        require(run["printer_raw_hex"] == printer.hex(" ").upper(),
                name + ": PRINTER_TRANSCRIPTION_CHANGED")
        readings = [parse_integer(x) for x in printer.splitlines(keepends=True)]
        require(len(readings) == 2 and all(x is not None for x in readings),
                name + ": PRINTER_VALUES_MISSING")
        err, actual = [x["numeric_value"] for x in readings]
        require(run["err_probe"] == err and run["variable_probe"] == actual,
                name + ": PRINTER_OBSERVATION_CHANGED")
        # Errors and B% probes are observations, not presumed arithmetic
        # or proofs of CPC atomicity. The original bytes are SHA-sealed.
        require(isinstance(err, int) and isinstance(actual, int),
                name + ": PRINTER_OBSERVATION_NOT_NUMERIC")
        native_stdout = (base / name / "run/native.stdout.bin").read_bytes()
        native_stderr = (base / name / "run/native.stderr.bin").read_bytes()
        native_num = parse_integer(native_stdout)
        status = ("UNSUPPORTED" if run["native_returncode"] != 0 or
                  b"[cli:error]" in native_stderr else
                  "NUMERIC_OUTPUT" if native_num is not None else
                  "UNVERIFIED_OUTPUT")
        require(run["native_status"] == status and
                run["native_number"] ==
                (native_num["numeric_value"] if native_num else None),
                name + ": NATIVE_OBSERVATION_FALSE")
        expected_stdin = expected + b"RUN\n:step 100\n:quit\n"
        require((base / name / "run/native.stdin.bin").read_bytes() ==
                expected_stdin, name + ": NATIVE_INPUT_CHANGED")
    require(len(operator_values) == 1,
            "MOD_OPERATOR_INCONSISTENT_ACROSS_CPC_CASES")
    actual_paths = {p.relative_to(base).as_posix() for p in base.rglob("*")
                    if p.is_file() or p.is_symlink()}
    require(actual_paths == inventory, "UNEXPECTED_OR_MISSING_ARCHIVE_FILES")
    if permanent:
        require((base / "seal.json").is_file(), "SEAL_MISSING")
        require(json.loads((base / "seal.json").read_text()) == seal_for(base,m),
                "EXTERNAL_SEAL_CHANGED")
    return m

def write_manifest(base, change):
    path = base / "manifest.json"
    m = json.loads(path.read_text())
    change(m)
    path.write_text(json.dumps(m, indent=2) + "\n")

def self_test(base):
    # Each mutation starts from a successfully validated independent copy.
    def reject(label, mutation, code):
        with tempfile.TemporaryDirectory(prefix="j15-negative-") as tmp:
            root = Path(tmp) / "proof"
            shutil.copytree(base, root)
            verify(root, permanent=True)
            mutation(root)
            try:
                verify(root, permanent=True)
            except (Invalid, ValueError, KeyError, OSError) as exc:
                require(code in str(exc), label + ": WRONG_REJECTION " + str(exc))
                print("PASS J1.6-A negative", label, code, flush=True)
            else:
                raise Invalid(label + ": FORGERY_ACCEPTED")
    reject("mutated-source", lambda root:
           (root/"P6_M3/original.bas").write_bytes(b"10 A%=3\n"),
           "FILE_DIGEST_CHANGED")
    reject("missing-program", lambda root:
           (root/"P6_M3/program.bin").unlink(), "FILE_ABSENT")
    reject("mutated-token", lambda root:
           (root/"P6_M3/program.bin").write_bytes(
               (root/"P6_M3/program.bin").read_bytes()[:-1] + b"\1"),
           "FILE_DIGEST_CHANGED")
    reject("mutated-screen", lambda root:
           (root/"P6_M3/run/run.png").write_bytes(
               (root/"P6_M3/run/run.png").read_bytes() + b"fake"),
           "FILE_DIGEST_CHANGED")
    reject("missing-printer", lambda root:
           (root/"P6_M3/run/printer.dat").unlink(), "FILE_ABSENT")
    reject("false-token-class", lambda root:
           write_manifest(root, lambda m:
               m["captures"][0]["pre_run"]["comparison"].update(
                   classification="MATCH_EXACT" if
                   m["captures"][0]["pre_run"]["comparison"]["classification"] !=
                   "MATCH_EXACT" else "UNSUPPORTED")),
           "COMPARISON_REPORT_CHANGED")
    reject("forged-operator-with-rehashed-file", lambda root:
           mutate_operator(root), "BINARY_MOD_SIGNATURE_CHANGED")
    reject("forged-printer-with-rehashed-manifest", lambda root:
           mutate_printer(root), "EXTERNAL_SEAL_CHANGED")
    reject("manifest-provenance", lambda root:
           write_manifest(root, lambda m: m.update(rom_archived=True)),
           "HISTORICAL_GUARD_CHANGED")
    reject("missing-run-proof", lambda root:
           (root/"P6_M3/run/autocmd.json").unlink(), "FILE_ABSENT")
    reject("truncated-printer", lambda root:
           (root/"P6_M3/run/printer.dat").write_bytes(b""),
           "FILE_DIGEST_CHANGED")
    reject("manifest-changed", lambda root:
           write_manifest(root, lambda m: m.update(generated_at="tampered")),
           "EXTERNAL_SEAL_CHANGED")
    reject("seal-changed", lambda root:
           (root/"seal.json").write_text("{}\n"), "EXTERNAL_SEAL_CHANGED")
    actual = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                     text=True).strip()
    require(validate_checkout_identity(actual) == actual,
            "CHECKOUT_POSITIVE_FAILED")
    wrong = ("0" if actual[0] != "0" else "1") + actual[1:]
    try:
        validate_checkout_identity(wrong)
    except ValueError as exc:
        require("J16_ACQUISITION_CHECKOUT_SHA_MISMATCH" in str(exc),
                "WRONG_CHECKOUT_REJECTION")
    else:
        raise Invalid("FORGED_CHECKOUT_SHA_ACCEPTED")
    print("PASS J1.6-A thirteen falsifications + checkout mismatch", flush=True)

def mutate_operator(root):
    p = root/"P6_M3/program.bin"
    data = bytearray(p.read_bytes())
    rows, detail = lines_of(data, [10,20,30,40])
    token = bytes.fromhex(next(c for c in json.loads(
        (root/"manifest.json").read_text())["captures"]
        if c["case"] == "P6_M3")["pre_run"]["operator_observed_hex"])
    offset = detail[1]["offset"] + 13
    local = bytes(data[offset:detail[1]["offset"]+detail[1]["length"]])
    where = local.find(token)
    require(where >= 0, "NEGATIVE_TEST_SETUP")
    offset += where
    data[offset] ^= 1
    p.write_bytes(data)
    def upd(m):
        case = next(c for c in m["captures"] if c["case"] == "P6_M3")
        case["pre_run"]["files"]["program.bin"]["sha256"] = sha(data)
        case["pre_run"]["comparison"]["cpc_sha256"] = sha(data)
    write_manifest(root, upd)

def mutate_printer(root):
    # Rehash printer AND its manifest transcription/observations. The
    # independent provisional seal must still detect coordinated forgery.
    p = root/"P6_M3/run/printer.dat"
    raw = p.read_bytes()
    values = [parse_integer(x) for x in raw.splitlines(keepends=True)]
    require(len(values) == 2 and all(x is not None for x in values),
            "NEGATIVE_TEST_SETUP")
    new_value = values[1]["numeric_value"] + 1
    new = raw.splitlines(keepends=True)[0] + (
        (b" " if new_value >= 0 else b"") + str(new_value).encode() + b" \r\n")
    p.write_bytes(new)
    def upd(m):
        case = next(c for c in m["captures"] if c["case"] == "P6_M3")
        case["run"]["files"]["printer.dat"]["sha256"] = sha(new)
        case["run"]["files"]["printer.dat"]["size_bytes"] = len(new)
        case["run"]["printer_raw_hex"] = new.hex(" ").upper()
        case["run"]["variable_probe"] = new_value
    write_manifest(root, upd)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, default=BASE)
    p.add_argument("--write-provisional-seal", action="store_true")
    p.add_argument("--permanent", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    base = args.evidence.resolve()
    if args.write_provisional_seal:
        require(not (base/"seal.json").exists(), "SEAL_ALREADY_EXISTS")
        m = verify(base)
        (base/"seal.json").write_text(json.dumps(seal_for(base,m),indent=2)+"\n")
    m = verify(base, permanent=args.permanent)
    print("PASS J1.6-A",len(m["captures"]),"acquired CPC cases",
          "permanent",args.permanent,flush=True)
    if args.self_test:
        require(args.permanent, "SELF_TEST_REQUIRES_SEAL")
        self_test(base)

if __name__ == "__main__":
    try:
        main()
    except (Invalid, ValueError, OSError, KeyError, TypeError) as exc:
        print("J1.6-A evidence INVALID:",exc,file=sys.stderr)
        sys.exit(1)
