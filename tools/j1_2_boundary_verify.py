#!/usr/bin/env python3
"""J1.2-A evidence verification, separate from the C99 tokenizer.

Checks original ROM-backed program-only captures, LIST/RUN artifacts, SHA-256,
sign, numeric observations, native status, provenance and historical barriers.
The first acquisition may generate a *provisional* seal; only Pilotage can approve.
"""
import argparse
import copy
import json
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/oracles"))
import token_ram_oracle as oracle
from signed_print_oracle import parse_integer
from j0_post_c1_audit import POLICY, reject_if_invalid_policy

VALUES = {"P255": 255, "P256": 256, "PMAX": 32767,
          "N255": -255, "N256": -256, "NMIN": -32768}
BASE = ROOT / "tests/fixtures/cpc6128/j1_integer_boundaries"
ALLOWED_PRE = {"original.bas", "program.bin", "c99.bin", "cap32.cfg",
               "autocmd.json", "caprice.log", "list.png",
               "comparison.json", "c99_error.txt"}
ALLOWED_RUN = {"cap32.cfg", "autocmd.json", "caprice.log", "run.png",
               "printer.dat", "native.stdin.bin", "native.stdout.bin",
               "native.stderr.bin"}
FORBIDDEN = {".rom", ".sna", ".dsk", ".cpr", ".zip", ".img"}

class Invalid(ValueError):
    pass

def require(ok, reason):
    if not ok:
        raise Invalid(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def checked_file(path, root, info, cause):
    require(path.is_file() and not path.is_symlink() and
            path.resolve().is_relative_to(root.resolve()), cause + ": FILE_ABSENT")
    require(path.suffix.lower() not in FORBIDDEN, cause + ": FORBIDDEN_FILE")
    b = path.read_bytes()
    require(len(b) == info["size_bytes"] and sha(b) == info["sha256"],
            cause + ": FILE_DIGEST_CHANGED")
    return b

def seal_for(base, manifest):
    return {"schema": 1, "phase": "J1.2-A-PROVISIONAL",
            "approval": "PENDING_PILOTAGE",
            "manifest_sha256": sha((base / "manifest.json").read_bytes()),
            "acquisition_run_id": manifest["github_run_id"],
            "acquisition_head_sha": manifest["github_head_sha"],
            "program_sha256": {
                c["case"]: sha((base / c["case"] / "program.bin").read_bytes())
                for c in manifest["captures"]},
            "first_operand_hex": {
                c["case"]: (base / c["case"] / "program.bin").read_bytes()[9:12].hex()
                for c in manifest["captures"]}}

def verify(base, permanent=False):
    manifest_path = base / "manifest.json"
    require(manifest_path.is_file() and not manifest_path.is_symlink(),
            "MANIFEST_ABSENT")
    m = json.loads(manifest_path.read_bytes())
    require(m.get("schema_version") == 1 and m.get("phase") == "J1.2-A" and
            m.get("rom_archived") is False and
            m.get("snapshots_archived") is False and
            m.get("screen_bytes_extracted") is False and
            m.get("printer_screen_equivalent") is False and
            m.get("historical_list_run") == "UNVERIFIED" and
            m.get("historical_archives_modified") is False,
            "HISTORICAL_GUARD_CHANGED")
    ref = m.get("oracle", {})
    require(ref.get("emulator") == "Caprice32" and
            ref.get("commit") == oracle.PIN and
            ref.get("rom_sha256") == oracle.ROM_SHA and
            ref.get("model") == "CPC6128" and ref.get("basic") == "1.1" and
            ref.get("ram_kb") == 128,
            "PROVENANCE_CHANGED")
    require(m.get("github_run_id") and m.get("github_head_sha") and
            len(m["github_head_sha"]) == 40, "PROVENANCE_MISSING")
    caps = m.get("captures", [])
    require(len(caps) == 6 and {c["case"] for c in caps} == set(VALUES),
            "CASE_SET_CHANGED")
    expected_paths = {"manifest.json"}
    for c in caps:
        name = c["case"]
        value = VALUES[name]
        require(c.get("value") == value and
                c.get("source_path") ==
                f"tests/oracles/inputs/j1_2_a/{name.lower()}.bas",
                name + ": VALUE_CHANGED")
        original = (f"10 B%={value}\n20 PRINT B%\n30 END\n").encode("ascii")
        source = ROOT / c["source_path"]
        require(source.read_bytes() == original, name + ": SOURCE_CHANGED")
        pre = c["pre_run"]
        require(pre.get("case") == name and
                pre.get("source_sha256") == sha(original) and
                pre.get("snapshot_taken_before_run") is True and
                pre.get("list_requested") is True,
                name + ": PRE_RUN_PROVENANCE_CHANGED")
        raw_files = pre["files"]
        require(set(raw_files).issubset(ALLOWED_PRE) and
                set(raw_files) >= {"original.bas", "program.bin", "cap32.cfg",
                                   "autocmd.json", "caprice.log",
                                   "list.png", "comparison.json"} and
                (("c99.bin" in raw_files) != ("c99_error.txt" in raw_files)),
                name + ": PRE_RUN_INVENTORY_CHANGED")
        for fname, desc in raw_files.items():
            p = base / name / fname
            checked_file(p, base, desc, name)
            expected_paths.add(f"{name}/{fname}")
        require((base / name / "original.bas").read_bytes() == original,
                name + ": ORIGINAL_SOURCE_CHANGED")
        raw = (base / name / "program.bin").read_bytes()
        lines, records = oracle.records(raw)
        require(lines == [10,20,30], name + ": RECORDS_CHANGED")
        require(pre["region"]["line_numbers"] == lines and
                pre["region"]["length"] == len(raw) and
                pre["region"]["records"] == records,
                name + ": RAM_BOUNDS_CHANGED")
        require(raw[9] == 0xF5 if name in ("N255", "N256") else True,
                name + ": UNARY_SIGN_CHANGED")
        require(raw[9] != 0xF5 if value > 0 else True,
                name + ": POSITIVE_SIGN_CHANGED")
        comp = pre["comparison"]
        require(comp["cpc_sha256"] == sha(raw) and
                comp["cpc_size"] == len(raw) and
                comp["classification"] in ("UNSUPPORTED", "MATCH_EXACT", "DIFF"),
                name + ": COMPARISON_CHANGED")
        if "c99.bin" in raw_files:
            c99 = (base / name / "c99.bin").read_bytes()
            actual = "MATCH_EXACT" if c99 == raw else "DIFF"
            require(comp["classification"] == actual and
                    comp["c99_sha256"] == sha(c99) and
                    comp["c99_size"] == len(c99),
                    name + ": CLASSIFICATION_CHANGED")
        else:
            require(comp["classification"] == "UNSUPPORTED" and
                    comp["c99_sha256"] is None and
                    comp["c99_size"] is None,
                    name + ": CLASSIFICATION_CHANGED")
        run = c["run"]
        require(run.get("fresh_cpc_run_session") is True and
                run.get("screenshot") == "VISUAL_OBSERVATION" and
                "never screen bytes" in run.get("printer_semantics",""),
                name + ": CHANNEL_PROVENANCE_CHANGED")
        files = run["files"]
        require(set(files).issubset(ALLOWED_RUN) and
                set(files) >= ALLOWED_RUN - {"printer.dat"},
                name + ": RUN_INVENTORY_CHANGED")
        for fname, desc in files.items():
            checked_file(base / name / "run" / fname, base, desc, name + "/RUN")
            expected_paths.add(f"{name}/run/{fname}")
        require((base / name / "run/run.png").read_bytes().startswith(
                    b"\x89PNG\r\n\x1a\n"), name + ": RUN_SCREEN_INVALID")
        printer = ((base / name / "run/printer.dat").read_bytes()
                   if "printer.dat" in files else b"")
        require(run.get("printer_raw_hex") == printer.hex(" ").upper(),
                name + ": PRINTER_BYTES_CHANGED")
        parsed = [parse_integer(x) for x in printer.splitlines(keepends=True)]
        good = len(parsed) == 2 and all(x is not None for x in parsed)
        err = parsed[0]["numeric_value"] if good else None
        variable = parsed[1]["numeric_value"] if good else None
        require(run.get("err_probe") == err and
                run.get("variable_probe") == variable,
                name + ": OBSERVED_VALUES_CHANGED")
        stdout = (base / name / "run/native.stdout.bin").read_bytes()
        stderr = (base / name / "run/native.stderr.bin").read_bytes()
        native_num = parse_integer(stdout)
        rc = run["native_returncode"]
        status = ("UNSUPPORTED" if rc != 0 or b"[cli:error]" in stderr
                  else "NUMERIC_OUTPUT" if native_num is not None
                  else "UNVERIFIED_OUTPUT")
        require(run.get("native_status") == status and
                run.get("native_number") ==
                (native_num["numeric_value"] if native_num else None),
                name + ": NATIVE_CLASSIFICATION_CHANGED")
    present = {p.relative_to(base).as_posix()
               for p in base.rglob("*") if p.is_file()}
    if permanent:
        expected_paths.add("seal.json")
    require(present == expected_paths, "UNAPPROVED_FILE_INVENTORY")
    reject_if_invalid_policy(POLICY)
    if permanent:
        seal_path = base / "seal.json"
        require(seal_path.is_file() and not seal_path.is_symlink(),
                "SEAL_MISSING")
        seal = json.loads(seal_path.read_bytes())
        require(seal == seal_for(base, m), "SEAL_OR_BYTES_CHANGED")
    return m

def reject_case(base, label, mutate, expected):
    with tempfile.TemporaryDirectory(prefix="j12-negative-") as temp:
        root = Path(temp) / "proof"
        shutil.copytree(base, root)
        verify(root, permanent=True)  # first test the intact copy
        mutate(root)
        try:
            verify(root, permanent=True)
        except (Invalid, ValueError) as err:
            require(expected in str(err),
                    label + ": WRONG_REJECTION " + str(err))
            print("PASS EXPECTED_REJECTION", label, expected, flush=True)
        else:
            raise Invalid(label + ": MUTATION_ACCEPTED")

def self_test(base):
    def tweak_manifest(root, fn):
        path = root / "manifest.json"
        m = json.loads(path.read_bytes())
        fn(m)
        path.write_text(json.dumps(m, indent=2) + "\n")
    def alter_program(root, with_hash):
        path = root / "P255/program.bin"
        raw = bytearray(path.read_bytes())
        raw[9] ^= 1
        path.write_bytes(raw)
        if with_hash:
            def change(m):
                c = next(x for x in m["captures"] if x["case"] == "P255")
                c["pre_run"]["files"]["program.bin"]["sha256"] = sha(raw)
                c["pre_run"]["comparison"]["cpc_sha256"] = sha(raw)
                if "c99.bin" in c["pre_run"]["files"]:
                    native = (root / "P255/c99.bin").read_bytes()
                    c["pre_run"]["comparison"]["classification"] = ("MATCH_EXACT" if native == raw else "DIFF")
            tweak_manifest(root, change)
    reject_case(base, "raw-byte", lambda r: alter_program(r, False),
                "FILE_DIGEST_CHANGED")
    reject_case(base, "forged-sha-and-byte",
                lambda r: alter_program(r, True), "SEAL_OR_BYTES_CHANGED")
    reject_case(base, "sign", lambda r: (r / "N255/program.bin").write_bytes(
                (r / "N255/program.bin").read_bytes().replace(b"\xF5", b"\xF4", 1)),
                "FILE_DIGEST_CHANGED")
    reject_case(base, "provenance",
                lambda r: tweak_manifest(r, lambda m: m["oracle"].update(
                    commit="0" * 40)), "PROVENANCE_CHANGED")
    reject_case(base, "value",
                lambda r: tweak_manifest(r, lambda m: m["captures"][0].update(
                    value=256)), "VALUE_CHANGED")
    reject_case(base, "native-status",
                lambda r: tweak_manifest(r, lambda m: m["captures"][0]["run"].update(
                    native_status="NUMERIC_OUTPUT_FORGED")), "NATIVE_CLASSIFICATION_CHANGED")
    reject_case(base, "historical-run",
                lambda r: tweak_manifest(r, lambda m: m.update(
                    historical_list_run="VERIFIED")), "HISTORICAL_GUARD_CHANGED")
    print("PASS J1.2-A intact proof + seven controlled negative cases", flush=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, default=BASE)
    p.add_argument("--write-provisional-seal", action="store_true")
    p.add_argument("--permanent", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    base = args.evidence.resolve()
    if args.write_provisional_seal:
        require(not (base / "seal.json").exists(), "SEAL_ALREADY_EXISTS")
        m = verify(base, False)
        (base / "seal.json").write_text(json.dumps(
            seal_for(base, m), indent=2) + "\n")
    m = verify(base, args.permanent)
    print("PASS J1.2-A", len(m["captures"]), "original CPC records",
          "permanent =", args.permanent, flush=True)
    if args.self_test:
        require(args.permanent, "SELF_TEST_REQUIRES_SEAL")
        self_test(base)

if __name__ == "__main__":
    try:
        main()
    except (Invalid, ValueError, OSError, KeyError, TypeError) as exc:
        print("J1.2-A EVIDENCE FAILED:", exc, file=sys.stderr)
        sys.exit(1)
