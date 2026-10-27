#!/usr/bin/env python3
"""J1.8-A CPC variable subtraction evidence: fail-closed independent archive checker.

The subtraction opcode and overflow observations MUST be measured from CPC RAM
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
from j1_8_sub_vars_oracle import CASES, validate_checkout_identity

BASE = ROOT / "tests/fixtures/cpc6128/j1_integer_sub_vars"
# Known historical INTEGER literal signatures, but NO assumed subtraction token.
# These INTEGER scalar encodings are historical CPC signatures, not
# a computed prediction for the new variable/variable operator.
def scalar_token(value):
    magnitude = abs(value)
    if magnitude == 32768:
        payload = bytes.fromhex("1F 00 00 00 00 90")
    elif magnitude < 10:
        payload = bytes([0x0e + magnitude])
    elif magnitude <= 255:
        payload = bytes([0x19, magnitude])
    elif magnitude <= 32767:
        payload = bytes([0x1a, magnitude & 255, magnitude >> 8])
    else:
        raise Invalid("SCALAR_MAGNITUDE_OUT_OF_RANGE")
    return (b"\xf5" if value < 0 else b"") + payload

EXPECTED_IMAGE = "ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c"

# Permanent original anchors copied from the one-time ROM-backed bot acquisition.
# Never derive these expected values from a newly generated native image.
PINNED_MANIFEST_SHA = ""  # set exclusively from acquired original manifest
PINNED_PROGRAM_SHA = {}  # add 12 independent original RAM hashes after bot archive

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

def expression_signature(raw):
    """Parse all three explicit INTEGER refs and preserve opaque CPC caches."""
    require(len(raw) >= 19 and raw[-1] == 0, "EXPRESSION_BAD_LENGTH")
    cursor = 4
    refs = []
    def read(label):
        nonlocal cursor
        require(cursor+4 <= len(raw) and raw[cursor] == 2 and
                raw[cursor+3] == (ord(label)|0x80),
                "EXPRESSION_REF_"+label+"_MALFORMED")
        refs.append({"name":label+"%", "record_relative_offset":cursor,
                     "cache_hex":raw[cursor+1:cursor+3].hex(" ").upper(),
                     "encoded_hex":raw[cursor:cursor+4].hex(" ").upper()})
        cursor += 4
    def spaces():
        nonlocal cursor
        while cursor < len(raw) and raw[cursor] == 0x20:
            cursor += 1
    read("C")
    spaces()
    require(cursor < len(raw) and raw[cursor] == 0xef, "EXPRESSION_EQUAL_MISSING")
    assignment = raw[cursor]
    cursor += 1
    spaces()
    read("A")
    spaces()
    require(cursor < len(raw)-1 and raw[cursor] >= 0x80, "EXPRESSION_OPCODE_MISSING")
    start = cursor
    cursor += 1
    if raw[start] == 0xff:
        require(cursor < len(raw)-1, "EXPRESSION_PREFIX_TRUNCATED")
        cursor += 1
    token = raw[start:cursor]
    spaces()
    read("B")
    require(raw[cursor:] == b"\x00", "EXPRESSION_TRAILING")
    return {"assignment": f"{assignment:02X}",
            "operator":token.hex(" ").upper(),
            "variable_refs":refs,
            "expression_record_hex":raw.hex(" ").upper()}

def seal_for(base, m):
    return {
        "schema": 1, "phase": "J1.8-A-PROVISIONAL",
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
    require(m.get("schema_version") == 1 and m.get("phase") == "J1.8-A" and
            m.get("rom_archived") is False and
            m.get("snapshots_archived") is False and
            m.get("screen_bytes_extracted") is False and
            m.get("printer_screen_equivalent") is False and
            m.get("screen_vs_printer") == "NOT_BYTE_COMPARABLE" and
            m.get("j1_8_b_authorized") is False and
            m.get("historical_list_run") == "UNVERIFIED" and
            m.get("historical_archives_modified") is False and
            m.get("ghcr_image") == EXPECTED_IMAGE,
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
    inventory = {"manifest.json"} | ({"seal.json"} if (base / "seal.json").is_file() else set())
    for c in captures:
        name = c["case"]
        lhs, rhs = CASES[name]
        require(c.get("lhs") == lhs and c.get("rhs") == rhs and
                c.get("source_path") == f"tests/oracles/inputs/j1_8_a/{name.lower()}.bas",
                name + ": CASE_PARAMETERS_CHANGED")
        expected = (f"10 A%={lhs}\n20 B%={rhs}\n30 C%=A%-B%\n"
                    "40 PRINT C%\n50 END\n").encode("ascii")
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
        require(commands[:5] == expected.decode("ascii").splitlines() and
                commands[5] == "LIST" and not any(x == "RUN" for x in commands),
                name + ": LIST_SEQUENCE_CHANGED")
        raw = (base / name / "program.bin").read_bytes()
        rows, records = lines_of(raw, [10,20,30,40,50])
        require(pre["region"]["line_numbers"] == [10,20,30,40,50] and
                pre["region"]["length"] == len(raw) and
                pre["region"]["records"] == records and
                pre["region"]["sentinel_offset"] == len(raw)-2,
                name + ": PROGRAM_BOUNDS_CHANGED")
        require(rows[0].endswith(scalar_token(lhs)+b"\0") and
                rows[1].endswith(scalar_token(rhs)+b"\0"),
                name + ": SCALAR_SIGNATURE_CHANGED")
        parsed = expression_signature(rows[2])
        require(pre["assignment_observed_hex"] == parsed["assignment"] and
                pre["operator_observed_hex"] == parsed["operator"] and
                pre["variable_refs"] == parsed["variable_refs"] and
                pre["expression_record_hex"] == parsed["expression_record_hex"] and
                pre["expression_line_number"] == 30,
                name + ": BINARY_SUB_VARS_SIGNATURE_CHANGED")
        operator_values.add(parsed["operator"])
        require(len(parsed["variable_refs"]) == 3 and
                [r["name"] for r in parsed["variable_refs"]] == ["C%","A%","B%"],
                name + ": REFERENCE_ORDER_CHANGED")
        require(isinstance(pre.get("session_start_utc"),str) and
                isinstance(pre.get("session_end_utc"),str) and
                pre["session_start_utc"] <= pre["session_end_utc"],
                name + ": LIST_CHRONOLOGY_CHANGED")
        compare = pre["comparison"]
        require(json.loads((base / name / "comparison.json").read_text()) == compare,
                name + ": COMPARISON_REPORT_CHANGED")
        require(compare["cpc_sha256"] == sha(raw) and
                compare["cpc_size"] == len(raw),
                name + ": TOKEN_MANIFEST_CHANGED")
        if "c99.bin" in files:
            native = (base / name / "c99.bin").read_bytes()
            lines_of(native, [10,20,30,40,50])
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
                 isinstance(run.get("session_start_utc"),str) and
                 isinstance(run.get("session_end_utc"),str) and
                 pre["session_end_utc"] <= run["session_start_utc"] and
                 run["session_start_utc"] <= run["session_end_utc"] and
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
        require(run_cmds[:5] == expected.decode("ascii").splitlines() and
                 "RUN" in run_cmds and "PRINT #8,ERR" in run_cmds and
                "PRINT #8,C%" in run_cmds and
                run_cmds.index("RUN") < run_cmds.index("PRINT #8,ERR") <
                run_cmds.index("PRINT #8,C%"),
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
        # Errors and C% probes are observations, not presumed arithmetic
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
            "SUB_VARS_OPERATOR_INCONSISTENT_ACROSS_CPC_CASES")
    actual_paths = {p.relative_to(base).as_posix() for p in base.rglob("*")
                    if p.is_file() or p.is_symlink()}
    require(actual_paths == inventory, "UNEXPECTED_OR_MISSING_ARCHIVE_FILES")
    if permanent:
        require(bool(re.fullmatch(r"[0-9a-f]{64}", PINNED_MANIFEST_SHA)) and
                set(PINNED_PROGRAM_SHA) == set(CASES) and
                all(re.fullmatch(r"[0-9a-f]{64}", s) for s in PINNED_PROGRAM_SHA.values()),
                "ORIGINAL_INDEPENDENT_ANCHORS_NOT_SET")
        require(sha((base / "manifest.json").read_bytes()) == PINNED_MANIFEST_SHA,
                "PINNED_ORIGINAL_MANIFEST_MISMATCH")
        for case, digest in PINNED_PROGRAM_SHA.items():
            require(sha((base / case / "program.bin").read_bytes()) == digest,
                    "PINNED_ORIGINAL_RAM_MISMATCH")
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
        with tempfile.TemporaryDirectory(prefix="j18-negative-") as tmp:
            root = Path(tmp) / "proof"
            shutil.copytree(base, root)
            verify(root, permanent=True)
            mutation(root)
            try:
                verify(root, permanent=True)
            except (Invalid, ValueError, KeyError, OSError) as exc:
                require(code in str(exc), label + ": WRONG_REJECTION " + str(exc))
                print("PASS J1.8-A negative", label, code, flush=True)
            else:
                raise Invalid(label + ": FORGERY_ACCEPTED")
    reject("mutated-source", lambda root:
           (root/"P2_P3/original.bas").write_bytes(b"10 A%=3\n"),
           "FILE_DIGEST_CHANGED")
    reject("missing-program", lambda root:
           (root/"P2_P3/program.bin").unlink(), "FILE_ABSENT")
    reject("mutated-token", lambda root:
           (root/"P2_P3/program.bin").write_bytes(
               (root/"P2_P3/program.bin").read_bytes()[:-1] + b"\1"),
           "FILE_DIGEST_CHANGED")
    reject("mutated-screen", lambda root:
           (root/"P2_P3/run/run.png").write_bytes(
               (root/"P2_P3/run/run.png").read_bytes() + b"fake"),
           "FILE_DIGEST_CHANGED")
    reject("missing-printer", lambda root:
           (root/"P2_P3/run/printer.dat").unlink(), "FILE_ABSENT")
    reject("false-token-class", lambda root:
           write_manifest(root, lambda m:
               m["captures"][0]["pre_run"]["comparison"].update(
                   classification="MATCH_EXACT" if
                   m["captures"][0]["pre_run"]["comparison"]["classification"] !=
                   "MATCH_EXACT" else "UNSUPPORTED")),
           "COMPARISON_REPORT_CHANGED")
    reject("forged-operator-with-rehashed-file", lambda root:
           mutate_operator(root), "BINARY_SUB_VARS_SIGNATURE_CHANGED")
    reject("forged-printer-with-rehashed-manifest", lambda root:
           mutate_printer(root), "PINNED_ORIGINAL_MANIFEST_MISMATCH")
    reject("manifest-provenance", lambda root:
           write_manifest(root, lambda m: m.update(rom_archived=True)),
           "HISTORICAL_GUARD_CHANGED")
    reject("missing-run-proof", lambda root:
           (root/"P2_P3/run/autocmd.json").unlink(), "FILE_ABSENT")
    reject("mutated-log-with-rehashed-manifest", lambda root:
           mutate_run_log(root), "PINNED_ORIGINAL_MANIFEST_MISMATCH")
    reject("truncated-printer", lambda root:
           (root/"P2_P3/run/printer.dat").write_bytes(b""),
           "FILE_DIGEST_CHANGED")
    reject("manifest-changed", lambda root:
           write_manifest(root, lambda m: m.update(generated_at="tampered")),
           "PINNED_ORIGINAL_MANIFEST_MISMATCH")
    # Additional independent tamper classes covering critical CPC record bytes.
    def corrupt_record(root, which):
        p = root / "P2_P3/program.bin"
        b = bytearray(p.read_bytes())
        _, rows = lines_of(b, [10,20,30,40,50])
        row = rows[2]
        record = bytes(b[row["offset"]:row["offset"]+row["length"]])
        if which == "cache": pos = row["offset"]+5
        elif which == "destination": pos = row["offset"]+7
        elif which == "length": pos = row["offset"]
        elif which == "end": pos = len(b)-1
        else: raise Invalid("UNKNOWN_FALSIFICATION")
        b[pos] ^= 1
        p.write_bytes(b)
    for kind in ("cache", "destination", "length", "end"):
        reject("mutated-" + kind, lambda root, k=kind: corrupt_record(root, k),
               "FILE_DIGEST_CHANGED")
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
        require("J18_ACQUISITION_CHECKOUT_SHA_MISMATCH" in str(exc),
                "WRONG_CHECKOUT_REJECTION")
    else:
        raise Invalid("FORGED_CHECKOUT_SHA_ACCEPTED")
    print("PASS J1.8-A eighteen falsifications + checkout mismatch", flush=True)

def mutate_run_log(root):
    # An attacker changes the process log AND rehashes its manifest entry,
    # but cannot silently replace the independently sealed original.
    path = root/"P2_P3/run/caprice.log"
    raw = path.read_bytes() + b"\\nFORGED_PROCESS_LOG\\n"
    path.write_bytes(raw)
    def updater(manifest):
        row = next(c for c in manifest["captures"] if c["case"] == "P2_P3")
        row["run"]["files"]["caprice.log"] = {
            "sha256": sha(raw), "size_bytes": len(raw)}
    write_manifest(root, updater)

def mutate_operator(root):
    p = root/"P2_P3/program.bin"
    data = bytearray(p.read_bytes())
    _, rows = lines_of(data, [10,20,30,40,50])
    row = rows[2]
    token = bytes.fromhex(next(c for c in json.loads(
        (root/"manifest.json").read_text())["captures"]
        if c["case"] == "P2_P3")["pre_run"]["operator_observed_hex"])
    offset = row["offset"] + 4
    local = bytes(data[offset:row["offset"]+row["length"]])
    pos = local.find(token)
    require(pos >= 0, "NEGATIVE_TEST_SETUP")
    offset += pos
    data[offset] ^= 1
    p.write_bytes(data)
    def upd(m):
        c = next(x for x in m["captures"] if x["case"]=="P2_P3")
        c["pre_run"]["files"]["program.bin"]["sha256"] = sha(data)
        c["pre_run"]["comparison"]["cpc_sha256"] = sha(data)
    write_manifest(root, upd)

def mutate_printer(root):
    # Rehash printer AND its manifest transcription/observations. The
    # independent provisional seal must still detect coordinated forgery.
    p = root/"P2_P3/run/printer.dat"
    raw = p.read_bytes()
    values = [parse_integer(x) for x in raw.splitlines(keepends=True)]
    require(len(values) == 2 and all(x is not None for x in values),
            "NEGATIVE_TEST_SETUP")
    new_value = values[1]["numeric_value"] + 1
    new = raw.splitlines(keepends=True)[0] + (
        (b" " if new_value >= 0 else b"") + str(new_value).encode() + b" \r\n")
    p.write_bytes(new)
    def upd(m):
        case = next(c for c in m["captures"] if c["case"] == "P2_P3")
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
    print("PASS J1.8-A",len(m["captures"]),"acquired CPC cases",
          "permanent",args.permanent,flush=True)
    if args.self_test:
        require(args.permanent, "SELF_TEST_REQUIRES_SEAL")
        self_test(base)

if __name__ == "__main__":
    try:
        main()
    except (Invalid, ValueError, OSError, KeyError, TypeError) as exc:
        print("J1.8-A evidence INVALID:",exc,file=sys.stderr)
        sys.exit(1)
