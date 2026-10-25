#!/usr/bin/env python3
"""Verify published J0.24-C3/C4/C5 program-only evidence; never consume a full SNA."""
import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/oracles"))
import token_ram_oracle as oracle

ALLOWED = {"program.bin", "c99.bin", "cap32.cfg",
           "autocmd.json", "caprice.log", "list.png", "comparison.json", "c99_error.txt"}
FORBIDDEN_SUFFIXES = {".sna", ".rom", ".dsk", ".cpr", ".zip", ".img"}
ROM = oracle.ROM_SHA
C3_SOURCE_SHA = {
    "b_integer_scalar": "7b000be0cd026bd73e309b24d2f57ab17f2dc6e650278e7e32776ab07a9039f1",
    "c_integer_add": "36afdbf24629f79f7753d1def84279374d54ee55eca7b03c2e0508da1ce396ec",
}
C4_SHA = {
    "a_print_constants": "0e4458cc0974f4cf4974917bbf52df4596bbb22341fd4db85dc7fffdf18abd05",
    "f_let_spacing": "cb6833e1f87945ebf164bcd017dcf9c7f761c552b37c51e7088526cfe32b28fe",
    "f_mixed_case": "984ad8367a45274de4aee19ffdf1eb0ef10fddea91aa975b68f2cc0851730056",
}
C3_SHA = {
    "b_integer_scalar": "20840377f8ec0181fe572e599f8eb63ab20a6e3edd8b448a201b14e8c23c8ee9",
    "c_integer_add": "931531da119e6c2b794482949b757203f5ddd1b5720694e723e74a97a001d188",
}

def require(ok, msg):
    if not ok:
        raise ValueError(msg)

def sha(buf):
    return hashlib.sha256(buf).hexdigest()

def compare(cpc, local):
    n = next((i for i, (x, y) in enumerate(zip(cpc,local)) if x != y),
             min(len(cpc),len(local)))
    same = cpc == local
    return same, None if same else {
        "first_offset": n,
        "cpc_byte": f"{cpc[n]:02x}" if n < len(cpc) else None,
        "c99_byte": f"{local[n]:02x}" if n < len(local) else None,
        "cpc_context_hex": cpc[max(0,n-8):n+9].hex(" "),
        "c99_context_hex": local[max(0,n-8):n+9].hex(" "),
        "hypothesis": "unresolved; no normalization or tokenizer modification",
    }

def validate(base, manifest):
    require(manifest.get("schema_version") == 1, "invalid manifest schema")
    identity = manifest["oracle"]
    require(identity["emulator"] == "Caprice32" and
            identity["commit"] == oracle.PIN and
            identity["rom_sha256"] == ROM and
            identity["model"] == "CPC6128" and
            identity["basic"] == "1.1" and identity["ram_kb"] == 128,
            "unverified oracle identity")
    require(manifest["snapshots_archived"] is False and
            manifest["rom_archived"] is False, "prohibited complete image")
    require(len(manifest["captures"]) == len(oracle.CASES) and
            {c["case"] for c in manifest["captures"]} == set(oracle.CASES),
            "exactly the registered distinct cases required")
    present = {x.relative_to(base).as_posix() for x in base.rglob("*") if x.is_file()}
    expected = {"manifest.json"}
    for name, (source_rel, nums) in oracle.CASES.items():
        cap = next(c for c in manifest["captures"] if c["case"] == name)
        files = cap["files"]
        expected_keys = ALLOWED - {"c99_error.txt"}
        unsupported_keys = (ALLOWED - {"c99.bin"})
        require(set(files) in (expected_keys, unsupported_keys),
                "unexpected case file inventory")
        require(cap["snapshot_taken_before_run"] is True and
                cap["list_requested"] is True, "LIST / before RUN not documented")
        src = (ROOT / "tests/fixtures/cpc6128" / source_rel).read_bytes()
        require(sha(src) == cap["source_sha256"], "source SHA mismatch")
        for key in files:
            f = base / name / key
            require(f.is_file() and not f.is_symlink() and
                    f.resolve().is_relative_to(base.resolve()),
                    "missing/unsafe evidence file")
            require(f.suffix not in FORBIDDEN_SUFFIXES, "forbidden memory export")
            d = f.read_bytes()
            require(len(d) == files[key]["size_bytes"] and
                    sha(d) == files[key]["sha256"], "file digest/size mismatch: "+key)
            expected.add(f"{name}/{key}")
        auto = json.loads((base/name/"autocmd.json").read_text())
        commands = auto["commands"]
        input_lines = src.decode("ascii").splitlines()
        require(commands[:len(input_lines)] == input_lines and
                commands[len(input_lines)] == "LIST" and
                not any(x == "RUN" for x in commands) and
                auto["snapshot_before_run"] is True and
                auto["source_sha256"] == sha(src),
                "input altered, LIST absent or RUN was sent")
        require(commands[-1].endswith("CAP32_EXIT") and
                "CAP32_SNAPSHOT" in commands[-1], "snapshot command missing")
        require("exit code: 0" in (base/name/"caprice.log").read_text(),
                "Caprice32 process did not succeed")
        require((base/name/"list.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"),
                "LIST visual evidence invalid")
        cpc = (base/name/"program.bin").read_bytes()
        local = (base/name/"c99.bin").read_bytes() if "c99.bin" in files else None
        cpc_lines, cpc_records = oracle.records(cpc)
        local_lines = oracle.records(local)[0] if local is not None else nums
        require(cpc_lines == nums and local_lines == nums, "wrong stored line numbers")
        region = cap["region"]
        require(region["start_address"] == region["base_pointer_value"]+1 and
                region["end_exclusive"] == region["start_address"]+len(cpc) and
                region["length"] == len(cpc) and
                region["snapshot_data_offset"] == 256 and
                region["snapshot_program_offset"] == 256+region["start_address"] and
                region["base_pointer_address"] == 0xAE64 and
                region["end_pointer_address"] == 0xAE66 and
                region["records"] == cpc_records and
                region["sentinel_offset"] == len(cpc)-2 and
                region["terminator_hex"] == "0000", "region bounds inconsistent")
        report = json.loads((base/name/"comparison.json").read_text())
        require(report == cap["comparison"], "comparison report differs from manifest")
        if local is None:
            rejection = (base/name/"c99_error.txt").read_text().strip()
            require(rejection.startswith("image-cli: input rejected:") and
                    report["classification"] == "UNSUPPORTED" and
                    report["first_difference"] is None and
                    report["c99_sha256"] is None and
                    report["c99_size"] is None and
                    report["c99_rejection"] == rejection,
                    "native rejection evidence inconsistent")
        else:
            same, diff = compare(cpc,local)
            require(report["classification"] == ("MATCH_EXACT" if same else "DIFF") and
                    report["first_difference"] == diff and
                    report["c99_sha256"] == sha(local) and
                    report["c99_size"] == len(local) and
                    report["c99_rejection"] is None,
                    "comparison is not reproducible")
        require(report["cpc_sha256"] == sha(cpc) and
                report["cpc_size"] == len(cpc), "CPC comparison hash invalid")
        print(name, "CPC", sha(cpc), report["classification"], flush=True)
    require(present == expected, "unexpected files, potentially a full SNA/ROM: "+
            str(sorted(present-expected)))
    print(f"PASS: {len(oracle.CASES)} delimited ROM-backed program images; no complete SNA/ROM files")


def validate_permanent(root, manifest):
    """Independent offline check of the promoted program-only fixtures."""
    phase = manifest.get("phase")
    expected_names = (set(C3_SHA) if phase is None else
                      set(C3_SHA) | set(C4_SHA) if phase == "J0.24-C4" else
                      set(oracle.CASES) if phase == "J0.24-C5" else set())
    if manifest.get("phase") == "J0.24-C4":
        p4 = manifest.get("c4_acquisition")
        require(isinstance(p4, dict) and p4.get("workflow") == "J0.24-C4 one-shot import" and
                isinstance(p4.get("artifact_id"), int) and not isinstance(p4.get("artifact_id"), bool) and
                p4["artifact_id"] > 0 and isinstance(p4.get("artifact_digest"), str) and
                re.fullmatch(r"sha256:[0-9a-f]{64}", p4["artifact_digest"]) and
                isinstance(p4.get("run_id"), int) and p4["run_id"] > 0,
                "C4 archival artifact provenance missing")
    if phase == "J0.24-C5":
        p5 = manifest.get("c5_acquisition")
        require(isinstance(p5, dict) and
                p5.get("workflow") == "J0.24-C5 one-shot import" and
                isinstance(p5.get("run_id"), int) and not isinstance(p5.get("run_id"), bool) and p5["run_id"] > 0 and
                isinstance(p5.get("artifact_id"), int) and not isinstance(p5.get("artifact_id"), bool) and p5["artifact_id"] > 0 and
                re.fullmatch(r"sha256:[0-9a-f]{64}", p5.get("artifact_digest", "")),
                "C5 acquisition provenance missing")
    require(manifest["schema_version"] == 1 and
            phase in (None, "J0.24-C4", "J0.24-C5") and
            len(manifest["cases"]) == len(expected_names),
            "invalid permanent evidence manifest")
    p = manifest["provenance"]
    require(p["caprice32_commit"] == oracle.PIN and
            p["system_rom_sha256"] == ROM and
            p["basic_rom_banner"] == "BASIC 1.1" and
            p["cpc_model"] == "CPC6128" and p["ram_kb"] == 128 and
            p["snapshot_or_rom_published"] is False,
            "unverified CPC provenance")
    require(len(p["artifact_zip_sha256"]) == 64 and
            len(p["original_acquisition_manifest_sha256"]) == 64 and
            p["github_actions_artifact_id"] == 12609729713 and
            p["github_actions_run_id"] == 40223535739,
            "missing or changed acquisition provenance")
    base = root / "tests/fixtures/cpc6128/token_ram"
    expected_files = {"manifest.json"}
    require({x["id"] for x in manifest["cases"]} == expected_names,
            "missing/extra permanent case")
    for case in manifest["cases"]:
        name = case["id"]
        source, numbers = oracle.CASES[name]
        expected_source = "tests/fixtures/cpc6128/" + source
        require(case["source_path"] == expected_source, "unexpected source")
        raw_source = (root / expected_source).read_bytes()
        require(sha(raw_source) == case["source_sha256"],
                "source digest mismatch")
        require("no RUN" in case["command_sequence"] and
                "LIST" in case["command_sequence"] and
                "CAP32_SNAPSHOT" in case["command_sequence"],
                "invalid acquisition method")
        native_supported = case.get("comparison") != "UNSUPPORTED"
        require(case["program_path"] ==
                f"tests/fixtures/cpc6128/token_ram/{name}/program.bin" and
                (case.get("c99_path") ==
                 f"tests/fixtures/cpc6128/token_ram/{name}/c99.bin"
                 if native_supported else
                 (phase == "J0.24-C5" and name not in C3_SHA and
                  name not in C4_SHA and case.get("c99_path") is None and
                  case.get("c99_sha256") is None and case.get("c99_bytes") is None)),
                "unexpected binary path")
        for key, sha_key, size_key in (
                [("program_path", "program_sha256", "program_bytes")] +
                ([("c99_path", "c99_sha256", "c99_bytes")] if native_supported else [])):
            file = root / case[key]
            require(file.is_file() and not file.is_symlink() and
                    file.resolve().is_relative_to(base.resolve()),
                    "unsafe/missing permanent fixture")
            binary = file.read_bytes()
            require(len(binary) == case[size_key] and
                    sha(binary) == case[sha_key], "binary SHA mismatch")
            expected_files.add(file.relative_to(base).as_posix())
        if name in C3_SHA:
            require(case["source_sha256"] == C3_SOURCE_SHA[name] and
                    case["program_sha256"] == C3_SHA[name] and
                    case["c99_sha256"] == C3_SHA[name] and
                    case["comparison"] == "MATCH_EXACT" and
                    "acquisition" not in case, "immutable C3 evidence changed")
        elif name in C4_SHA:
            require(case["program_sha256"] == C4_SHA[name] and
                    case["c99_sha256"] == C4_SHA[name] and
                    case["comparison"] == "MATCH_EXACT",
                    "immutable C4 evidence changed")
            origin = case.get("acquisition")
            require(isinstance(origin, dict) and
                    origin.get("workflow") == "J0.24-C4 one-shot import" and
                    isinstance(origin.get("run_id"), int) and
                    not isinstance(origin.get("run_id"), bool) and
                    origin["run_id"] > 0 and
                    origin.get("artifact_name") == "cpc6128-c4-original-evidence" and
                    origin.get("artifact_id") == manifest["c4_acquisition"]["artifact_id"] and
                    origin.get("artifact_digest") == manifest["c4_acquisition"]["artifact_digest"] and
                    origin["run_id"] == manifest["c4_acquisition"]["run_id"] and
                    origin.get("caprice32_commit") == oracle.PIN and
                    origin.get("rom_sha256") == ROM and
                    origin.get("source_sha256") == case["source_sha256"],
                    "missing or inconsistent C4 origin run")
            require(isinstance(case.get("original_list_png_sha256"), str) and
                    len(case["original_list_png_sha256"]) == 64 and
                    "first_difference" in case,
                    "missing C4 visual provenance or difference report")
        else:
            require(phase == "J0.24-C5", "unpromoted case")
            origin = case.get("acquisition")
            p5 = manifest["c5_acquisition"]
            require(isinstance(origin, dict) and
                    origin.get("workflow") == p5["workflow"] and
                    origin.get("run_id") == p5["run_id"] and
                    origin.get("run_url") ==
                      "https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/" + str(p5["run_id"]) and
                    origin.get("artifact_name") == p5["artifact_name"] and
                    origin.get("artifact_id") == p5["artifact_id"] and
                    origin.get("artifact_digest") == p5["artifact_digest"] and
                    origin.get("source_sha256") == case["source_sha256"] and
                    origin.get("rom_sha256") == ROM and
                    origin.get("caprice32_commit") == oracle.PIN and
                    isinstance(case.get("original_list_png_sha256"), str) and
                    re.fullmatch(r"[0-9a-f]{64}", case["original_list_png_sha256"]),
                    "C5 evidence provenance missing/inconsistent")
        cpc = (root / case["program_path"]).read_bytes()
        local = ((root / case["c99_path"]).read_bytes()
                 if native_supported else None)
        found, rows = oracle.records(cpc)
        local_numbers = oracle.records(local)[0] if local is not None else numbers
        require(found == numbers and local_numbers == numbers,
                "stored line numbers invalid")
        require([r["length"] for r in rows] == case["line_record_lengths"],
                "record lengths changed")
        require(case["line_numbers"] == numbers and
                case["base_pointer_value"] + 1 == case["program_start_cpc"] and
                case["program_end_exclusive_cpc"] ==
                   case["program_start_cpc"] + len(cpc) and
                case["snapshot_header_length"] == 256 and
                case["snapshot_program_file_offset"] ==
                   256 + case["program_start_cpc"] and
                case["start_pointer_ram"] == 0xae64 and
                case["end_pointer_ram"] == 0xae66 and
                case["ram_bank"] == 0 and
                case["line_terminator_hex"] == "00" and
                case["program_terminator_hex"] == "0000",
                "memory boundaries/record metadata changed")
        exact, diff = compare(cpc, local) if local is not None else (False, None)
        effective = ("UNSUPPORTED" if local is None else "MATCH_EXACT" if exact else "DIFF")
        require(case["comparison"] == effective and
                (name in C3_SHA or case["first_difference"] == diff) and
                case["normalization"] == "none" and
                case["raw_acquisition_preserved"] is True,
                "fabricated or non-raw comparison")
        if local is None:
            require(isinstance(case.get("c99_rejection"), str) and
                    case["c99_rejection"].startswith("image-cli: input rejected:"),
                    "missing native rejection diagnostic")
        print("PERMANENT", name, case["comparison"],
              case["program_sha256"],flush=True)
    present = {f.relative_to(base).as_posix() for f in base.rglob("*")
               if f.is_file()}
    require(present == expected_files,
            "unlisted/forbidden evidence files: "+repr(present-expected_files))
    print(f"PASS: permanently archived {len(expected_names)} CPC program-only token images")

def permanent_self_test(root, original):
    for change in ("token", "classification", "start", "rom", "source", "proof", "missing", "artifact", "c4_immutable", "c5_origin"):
        altered = copy.deepcopy(original)
        if change == "token":
            altered["cases"][0]["program_sha256"] = "0"*64
        elif change == "classification":
            altered["cases"][0]["comparison"] = "DIFF"
        elif change == "start":
            altered["cases"][0]["program_start_cpc"] += 1
        elif change == "source":
            altered["cases"][0]["source_sha256"] = "0"*64
        elif change == "proof":
            if "phase" in altered:
                altered["cases"][-1]["acquisition"]["run_id"] = 0
            else:
                altered["provenance"]["github_actions_run_id"] = 0
        elif change == "missing":
            altered["cases"][0]["program_path"] = "tests/fixtures/cpc6128/token_ram/MISSING/program.bin"
        elif change == "artifact":
            if "phase" in altered:
                altered["cases"][-1]["acquisition"]["artifact_digest"] = "sha256:" + "0"*64
            else:
                altered["provenance"]["original_acquisition_manifest_sha256"] = ""
        elif change == "c4_immutable":
            if altered.get("phase") == "J0.24-C5":
                next(c for c in altered["cases"] if c["id"] in C4_SHA)["program_sha256"] = "0"*64
            else:
                continue
        elif change == "c5_origin":
            if altered.get("phase") == "J0.24-C5":
                altered["c5_acquisition"]["artifact_id"] = 0
            else:
                continue
        else:
            altered["provenance"]["system_rom_sha256"] = "0"*64
        try:
            validate_permanent(root,altered)
        except ValueError:
            continue
        raise ValueError("negative permanent validator did not reject "+change)
    print("PASS: permanent evidence SHA/classification/bounds/ROM tampering rejected")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path)
    p.add_argument("--permanent", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.permanent:
        path = ROOT/"tests/fixtures/cpc6128/token_ram/manifest.json"
        manifest = json.loads(path.read_text())
        validate_permanent(ROOT,manifest)
        if args.self_test:
            permanent_self_test(ROOT,manifest)
        return
    require(args.evidence is not None, "--evidence or --permanent required")
    base = args.evidence.resolve()
    manifest = json.loads((base/"manifest.json").read_text())
    validate(base, manifest)
    if args.self_test:
        for field, value in [("snapshots_archived", True), ("rom_archived", True)]:
            malformed = copy.deepcopy(manifest)
            malformed[field] = value
            try:
                validate(base, malformed)
            except ValueError:
                pass
            else:
                raise ValueError("negative test not rejected: "+field)
        altered = copy.deepcopy(manifest)
        altered["captures"][0]["comparison"]["classification"] = "MATCH_EXACT" if (
            altered["captures"][0]["comparison"]["classification"] == "DIFF") else "DIFF"
        try:
            validate(base, altered)
        except ValueError:
            pass
        else:
            raise ValueError("fabricated classification accepted")
        print("PASS: prohibited images and fabricated classification rejected")

if __name__ == "__main__":
    try:
        main()
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print("TOKEN EVIDENCE INVALID:",exc,file=sys.stderr)
        sys.exit(1)
