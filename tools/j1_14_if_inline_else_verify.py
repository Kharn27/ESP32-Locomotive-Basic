#!/usr/bin/env python3
"""J1.14-A: fail-closed verifier of independent CPC6128 IF-relational captures.

Two separate Caprice32 LIST/SNA and RUN/printer process pairs per source.
No native stack inference and no promotion of the experimental syntax.
The first bot acquisition is an observation; permanent anchors are transcribed
only from its sealed artifacts after the original GHCR run has completed.
"""
import argparse
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
from j1_14_if_inline_else_oracle import MAIN_CASES, EXPLORATORY, GHCR_PIN, checkout_identity

BASE = ROOT / "tests/fixtures/cpc6128/j1_14_if_inline_else"
# EXTERNAL FIRST-CAPTURE ANCHORS: absent until the original GHCR archive is
# produced by the GitHub bot. An empty value always fails permanent mode.
# Transcribed from independent GHCR original run 40615245342
# acquired at HEAD 9ef54a01f9b8c12eb11c559c3930cd3d37729a2a; seal remains PENDING_PILOTAGE.
# External anchors intentionally absent until real CPC archival.
# External immutable anchors are populated only after the first original GHCR
# acquisition has been archived and independently inspected. Fail closed.
PINNED_MANIFEST_SHA = ""
PINNED_RAM = {}
PINNED_PRINTER = {}
PINNED_OUTCOMES = {}

class Invalid(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise Invalid(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    require(path.is_file() and not path.is_symlink(),
            "MISSING_OR_SYMLINK:" + str(path))
    return path.read_bytes()

def inventory(directory):
    require(directory.is_dir() and not directory.is_symlink(),
            "MISSING_DIRECTORY:" + str(directory))
    files = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "SYMLINK_FORBIDDEN:" + str(path))
        require(path.suffix.lower() not in (".rom", ".sna", ".dsk", ".cpr", ".zip"),
                "PROHIBITED_ARCHIVE:" + str(path))
        if path.is_file():
            data = read(path)
            files[str(path.relative_to(directory))] = {
                "sha256": sha(data), "size_bytes": len(data)}
    return files

def matches_inventory(directory, expected, label):
    require(inventory(directory) == expected, label + ": FILE_INVENTORY_CHANGED")

def source(name):
    p = ROOT / "tests/oracles/inputs/j1_14_a" / (name.lower() + ".bas")
    data = read(p)
    require(data.endswith(b"\n") and b"\r" not in data, name + ": BAD_SOURCE_NEWLINE")
    numbers = []
    for row in data.splitlines():
        match = re.fullmatch(rb"([1-9][0-9]*) .+", row)
        require(match is not None, name + ": BAD_BASIC_SOURCE")
        numbers.append(int(match.group(1)))
    require(numbers == sorted(set(numbers)) and len(numbers) >= 2,
            name + ": DUPLICATE_OR_UNSORTED_LINES")
    return data, numbers

def if_records(data, lines, records):
    flows = []
    for src, rec in zip(lines.splitlines(), records):
        if rec["line"] != 30:
            continue
        require(src.startswith(b"30 IF "), "IF_SOURCE_NOT_AUTONOMOUS_LINE30")
        raw = data[rec["offset"]:rec["offset"] + rec["length"]]
        require(raw[-1] == 0 and raw[:2] == len(raw).to_bytes(2,"little")
                and int.from_bytes(raw[2:4],"little") == 30,
                "INVALID_IF_FULL_RECORD")
        # The observed bytes come only from the real CPC snapshot.
        # Check structural A1 and EB, but never synthesize cache bytes
        # or assume a fixed offset for the ELSE token.
        body = raw[4:-1]
        require(body.startswith(b"\xa1") and b"\xeb" in body,
                "CPC_IF_THEN_STRUCTURAL_TOKEN_ABSENT")
        if b" ELSE " in src:
            require(b"\x97" in body, "CPC_ELSE_TOKEN_ABSENT")
        flows.append({"line_number":30,"record_hex":raw.hex(" ").upper(),
                      "record_length":len(raw)})
    require(len(flows) == 1, "ONE_IF_LINE30_REQUIRED")
    return flows

def verify_run(base, name, mode, item, src):
    folder = base/mode/name/"run"
    r = item["run"]
    require(r["fresh_cpc_run_process"] is True and
            r["returncode"] == 0 and r["screen_png_present"] is True and
            r["result_class"] == "OBSERVED" and
            r["all_printer_lines_numeric"] is True,
            name+": RUN_PROVENANCE_INVALID_"+mode)
    png = read(folder/"run.png")
    require(png[:8] == b"\x89PNG\r\n\x1a\n" and
            png[12:16] == b"IHDR", name+": RUN_PNG_INVALID_"+mode)
    printer = read(folder/"printer.dat")
    parsed = [parse_integer(row) for row in printer.splitlines(keepends=True)]
    require(2 <= len(parsed) <= 64 and all(row is not None for row in parsed),
            name+": ERR_ERL_PRINTER_MISSING_"+mode)
    values = [row["numeric_value"] for row in parsed]
    require(len(printer) <= 2048 and
            r["printer_raw_hex"] == printer.hex(" ").upper() and
            r["printer_lines"] == values and
            r["program_trace"] == values[:-2] and
            r["err_probe"] == values[-2] and
            r["erl_probe"] == values[-1],
            name+": RUN_TRACE_OR_DIAGNOSTIC_INVALID_"+mode)
    commands = json.loads(read(folder/"autocmd.json"))["commands"]
    require(commands[:len(src.splitlines())] ==
            src.decode("ascii").splitlines() and
            commands[len(src.splitlines())] == "RUN" and
            "PRINT #8,ERR" in commands and "PRINT #8,ERL" in commands,
            name+": RUN_COMMAND_SEQUENCE_CHANGED_"+mode)
    matches_inventory(folder, r["files"], name+": RUN_FILES_"+mode)
    return printer

def verify_pre(base, name, mode, item, src, numbers):
    folder = base/mode/name
    pre = item["pre_run"]
    raw = read(folder/"program.bin")
    observed, rows = oracle.records(raw)
    require(observed == numbers and raw.endswith(b"\0\0"),
            name+": CPC_RAM_RECORDS_INVALID_"+mode)
    require(pre["case"] == name and
            pre["source_sha256"] == sha(src) and
            pre["snapshot_taken_before_run"] is True and
            pre["list_requested"] is True and
            pre["region"]["records"] == rows and
            pre["region"]["line_numbers"] == numbers and
            pre["region"]["length"] == len(raw) and
            pre["region"]["sentinel_offset"] == len(raw)-2,
            name+": PRE_RUN_REGION_INVALID_"+mode)
    require(pre["if_records"] == if_records(raw, src, rows),
            name+": IF_RECORD_OR_CACHE_CHANGED_"+mode)
    require(read(folder/"original.bas") == src,
            name+": ORIGINAL_SOURCE_DIFFERENT_"+mode)
    png = read(folder/"list.png")
    require(png[:8] == b"\x89PNG\r\n\x1a\n" and png[12:16] == b"IHDR",
            name+": LIST_PNG_INVALID_"+mode)
    listed = json.loads(read(folder/"autocmd.json"))
    require(listed["commands"][:len(numbers)] ==
            src.decode("ascii").splitlines() and
            listed["commands"][len(numbers)] == "LIST" and
            listed["snapshot_before_run"] is True and
            "RUN" not in listed["commands"],
            name+": LIST_COMMAND_SEQUENCE_CHANGED_"+mode)
    cmp = pre["comparison"]
    require(cmp["cpc_sha256"] == sha(raw) and
            cmp["cpc_size"] == len(raw) and
            cmp["classification"] in ("UNSUPPORTED","DIFF","MATCH_EXACT"),
            name+": PRE_NATIVE_CLASSIFICATION_CHANGED_"+mode)
    if cmp["classification"] == "UNSUPPORTED":
        require(cmp["c99_size"] is None and cmp["c99_sha256"] is None and
                cmp["first_difference"] is None and
                "image-cli: input rejected:" in cmp["c99_rejection"] and
                (folder/"c99_error.txt").is_file() and not (folder/"c99.bin").exists(),
                name+": C99_UNSUPPORTED_UNPROVEN_"+mode)
    else:
        candidate = read(folder/"c99.bin")
        require(cmp["c99_size"] == len(candidate) and
                cmp["c99_sha256"] == sha(candidate) and
                not (folder/"c99_error.txt").exists() and
                (cmp["classification"] == "MATCH_EXACT") == (candidate == raw),
                name+": C99_CLASSIFICATION_INVALID_"+mode)
    require(json.loads(read(folder/"comparison.json")) == cmp,
            name+": C99_REJECTION_EVIDENCE_MISSING_"+mode)
    for filename, meta in pre["files"].items():
        data = read(folder/filename)
        require({"sha256":sha(data),"size_bytes":len(data)} == meta,
                name+": PRE_FILE_DIGEST_CHANGED_"+mode+"/"+filename)
    return raw

def seal_for(base, m):
    return {
        "schema": 1, "phase":"J1.14-A-PROVISIONAL",
        "approval":"PENDING_PILOTAGE",
        "acquisition_head_sha":m["github_head_sha"],
        "acquisition_run_id":m["github_run_id"],
        "manifest_sha256":sha(read(base/"manifest.json")),
        "program_sha256":{c["case"]:sha(read(base/"original"/c["case"]/"program.bin"))
                          for c in m["captures"]},
        "printer_sha256":{c["case"]:sha(read(base/"original"/c["case"]/"run/printer.dat"))
                          for c in m["captures"]}
    }

def verify(base, permanent=False):
    m = json.loads(read(base/"manifest.json"))
    require(m.get("phase") == "J1.14-A" and m.get("schema_version") == 1 and
            m.get("rom_archived") is False and
            m.get("full_snapshots_archived") is False and
            m.get("printer_is_screen_output") is False and
            m.get("j1_14_b_authorized") is False and
            m.get("historical_archives_modified") is False and
            m.get("ghcr_image") == GHCR_PIN,
            "MANIFEST_PROVENANCE_CHANGED")
    rom = m.get("oracle",{})
    require(rom.get("commit") == oracle.PIN and
            rom.get("rom_sha256") == oracle.ROM_SHA and
            rom.get("model") == "CPC6128" and
            rom.get("basic") == "1.1" and
            rom.get("ram_kb") == 128 and
            rom.get("emulator") == "Caprice32",
            "PINNED_ROM_OR_EMULATOR_CHANGED")
    require(re.fullmatch(r"[a-f0-9]{40}", str(m.get("github_head_sha",""))) and
            re.fullmatch(r"[0-9]+", str(m.get("github_run_id",""))),
            "ACQUISITION_GITHUB_IDENTITY_ABSENT")
    require(m.get("mandatory_cases") == list(MAIN_CASES) and
            m.get("exploratory_cases") == list(EXPLORATORY),
            "CASE_SET_CHANGED")
    captures = m.get("captures", [])
    require(len(captures) == len(MAIN_CASES) == 24 and
            [c["case"] for c in captures] == list(MAIN_CASES),
            "MISSING_OR_ADDED_CASES")
    require((base/"original").is_dir() and
            (base/"repeat").is_dir() and
            (base/"exploratory").is_dir(),
            "ROOT_PROOF_LAYOUT_CHANGED")
    expected_root = {"original","repeat","exploratory","manifest.json"}
    if (base/"seal.json").exists():
        expected_root.add("seal.json")
    require({p.name for p in base.iterdir()} == expected_root,
            "ROOT_FILES_CHANGED")
    require(len(m.get("explorations", [])) == len(EXPLORATORY) == 6 and
            [x["case"] for x in m["explorations"]] == list(EXPLORATORY),
            "EXPLORATORY_SET_CHANGED")
    for experiment in m["explorations"]:
        name = experiment["case"]
        source_data, numbers = source(name)
        folder = base/"exploratory"/name
        require(read(folder/"original.bas") == source_data and
                experiment["original_source_sha256"] == sha(source_data) and
                experiment["line_numbers"] == numbers and
                experiment["scope"] == "EXPLORATION_ONLY_NEVER_J1_14_B_PROOF",
                name+": EXPLORATORY_SOURCE_OR_SCOPE_CHANGED")
        run = experiment["run"]
        require(run["fresh_cpc_run_process"] is True and
                run["printer_raw_hex"] ==
                   (read(folder/"run/printer.dat").hex(" ").upper()
                    if (folder/"run/printer.dat").is_file() else "") and
                run["screen_png_present"] == (folder/"run/run.png").is_file(),
                name+": EXPLORATORY_CHANNEL_CHANGED")
        matches_inventory(folder/"run", run["files"],
                          name+": EXPLORATORY_RUN_ARCHIVE_CHANGED")

    for c in captures:
        name = c["case"]
        src, nums = source(name)
        require(c["source_path"] ==
                "tests/oracles/inputs/j1_14_a/"+name.lower()+".bas" and
                c["source_sha256"] == sha(src) and c["lines"] == nums and
                c["two_independent_process_pairs"] is True and
                c["ram_exact_2of2"] is True and
                c["printer_exact_2of2"] is True,
                name+": SOURCE_OR_DOUBLE_ACQUISITION_CLAIM_CHANGED")
        originals = []
        for mode in ("original","repeat"):
            record = c[mode]
            ram = verify_pre(base,name,mode,record,src,nums)
            printer = verify_run(base,name,mode,record,src)
            matches_inventory(base/mode/name,record["all_files_sha256"],
                              name+": ALL_FILES_"+mode)
            originals.append((ram,printer))
        require(originals[0] == originals[1],
                name+": TWO_SESSIONS_RAM_OR_PRINTER_MISMATCH")
        if permanent:
            outcome = [c["original"]["run"]["program_trace"],
                       c["original"]["run"]["err_probe"],
                       c["original"]["run"]["erl_probe"]]
            require(outcome == PINNED_OUTCOMES[name],
                    name+": INDEPENDENTLY_PINNED_CPC_OBSERVATION_MISMATCH")
    if permanent:
        require(re.fullmatch("[a-f0-9]{64}",PINNED_MANIFEST_SHA) and
                set(PINNED_RAM) == set(MAIN_CASES) and
                set(PINNED_PRINTER) == set(MAIN_CASES) and
                set(PINNED_OUTCOMES) == set(MAIN_CASES),
                "EXTERNAL_ANCHORS_NOT_ESTABLISHED")
        require(sha(read(base/"manifest.json")) == PINNED_MANIFEST_SHA,
                "EXTERNAL_MANIFEST_SHA_MISMATCH")
        for name in MAIN_CASES:
            require(sha(read(base/"original"/name/"program.bin")) ==
                    PINNED_RAM[name],name+": EXTERNAL_RAM_SHA_MISMATCH")
            require(sha(read(base/"original"/name/"run/printer.dat")) ==
                    PINNED_PRINTER[name],name+": EXTERNAL_PRINTER_SHA_MISMATCH")
    seal = base/"seal.json"
    if seal.exists():
        require(json.loads(read(seal)) == seal_for(base,m),
                "PROVISIONAL_SEAL_CHANGED")
        if permanent:
            original = json.loads(read(seal))
            require(original["manifest_sha256"] == PINNED_MANIFEST_SHA and
                    original["program_sha256"] == PINNED_RAM and
                    original["printer_sha256"] == PINNED_PRINTER,
                    "EXTERNALLY_PINNED_SEAL_MISMATCH")
    else:
        require(not permanent, "PERMANENT_SEAL_MISSING")
    return m

def falsify(base):
    require(base.resolve() == BASE.resolve(),
            "FALSIFICATIONS_ONLY_FOR_CANONICAL_ARCHIVE")
    with tempfile.TemporaryDirectory(prefix="j114a-falsify-") as tmp:
        target = Path(tmp)/"candidate"
        shutil.copytree(base, target)
        name = MAIN_CASES[0]
        original_record = bytes.fromhex(
            json.loads(read(target/"manifest.json"))["captures"][0]
            ["original"]["pre_run"]["if_records"][0]["record_hex"])
        require(b"\xa1" in original_record and b"\xeb" in original_record
                and b"\x97" in original_record, "AUTHENTIC_IF_STRUCTURE_MISSING")
        original_ram_path = target/"original"/name/"program.bin"
        original_ram = read(original_ram_path)
        _, rows = oracle.records(original_ram)
        start = next(x["offset"] for x in rows if x["line"] == 30)
        cache_pos = original_record.index(b"\x02") + 1
        changes = [
            ("IF_TOKEN", original_ram_path, start+4),
            ("INTEGER_CACHE", original_ram_path, start+cache_pos),
            ("THEN_TOKEN", original_ram_path,
             start+original_record.index(b"\xeb")),
            ("ELSE_TOKEN", original_ram_path,
             start+original_record.index(b"\x97")),
            ("REPEAT_RAM", target/"repeat"/name/"program.bin", 5),
            ("PRINTER", target/"original"/name/"run/printer.dat", 2),
            ("REPEAT_PRINTER", target/"repeat"/name/"run/printer.dat", 2),
            ("SOURCE", target/"original"/name/"original.bas", 6),
            ("RUN_COMMANDS", target/"original"/name/"run/autocmd.json", 2),
            ("COMPARISON", target/"original"/name/"comparison.json", 2),
            ("MANIFEST", target/"manifest.json", 2),
            ("SEAL", target/"seal.json", 2),
            ("EXPLORATORY", target/"exploratory"/EXPLORATORY[0]/
             "run/autocmd.json", 2)
        ]
        for label,path,offset in changes:
            original = read(path)
            require(0 <= offset < len(original), "INVALID_FALSIFICATION_OFFSET")
            corrupted = bytearray(original)
            corrupted[offset] ^= 1
            path.write_bytes(corrupted)
            try:
                verify(target,permanent=True)
            except (Invalid,ValueError,UnicodeError,KeyError,TypeError):
                print("PASS J1.14-A FALSIFICATION_REJECTED",label,flush=True)
            else:
                raise Invalid("FALSIFICATION_ACCEPTED_"+label)
            path.write_bytes(original)
        actual = subprocess.check_output(["git","-C",str(ROOT),
                                          "rev-parse","HEAD"],text=True).strip()
        require(checkout_identity(actual) == actual, "ACTUAL_SHA_REJECTED")
        false = ("0" if actual[0] != "0" else "1") + actual[1:]
        try:
            checkout_identity(false)
        except ValueError:
            print("PASS J1.14-A FALSE_HEAD_REJECTED",flush=True)
        else:
            raise Invalid("FALSE_HEAD_ACCEPTED")
    print("PASS J1.14-A 13 MUTATIONS + FALSE HEAD",flush=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence",type=Path,default=BASE)
    p.add_argument("--write-provisional-seal",action="store_true")
    p.add_argument("--permanent",action="store_true")
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--check-sources",action="store_true")
    args = p.parse_args()
    if args.check_sources:
        for name in tuple(MAIN_CASES) + tuple(EXPLORATORY):
            src,nums = source(name)
            require(nums == [10,20,25,30,40,50] and
                    b"30 " in src and
                    b"40 PRINT #8,C%\n50 END\n" in src,
                    name+": BAD_J1_14_SOURCE")
            if name in MAIN_CASES:
                require(b"30 IF " in src and b" THEN C%=81" in src,
                        name+": NON_INLINE_POSITIVE_SOURCE")
        print("PASS J1.14-A 24 POSITIVE + 6 EXPLORATORY SOURCES; NOT ROM EVIDENCE")
        return
    base = args.evidence.resolve()
    if args.write_provisional_seal:
        require(not (base/"seal.json").exists(), "REFUSE_TO_RESEAL")
        m = verify(base)
        (base/"seal.json").write_text(json.dumps(seal_for(base,m),indent=2)+"\n")
    m = verify(base,args.permanent)
    print("PASS J1.14-A",len(m["captures"]),"CASES",
          "ORIGINAL+REPEAT", "PERMANENT="+str(args.permanent),flush=True)
    if args.self_test:
        require(args.permanent,"SELF_TEST_REQUIRES_PERMANENT")
        falsify(base)

if __name__ == "__main__":
    try:
        main()
    except (Invalid,ValueError,OSError,UnicodeError,KeyError,TypeError) as exc:
        print("J1.14-A VERIFY FAILED:",exc,file=sys.stderr)
        sys.exit(1)
