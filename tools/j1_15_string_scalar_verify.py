#!/usr/bin/env python3
"""J1.15-A: verify independent CPC6128 STRING captures; no native promotion."""
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
from j1_15_string_scalar_oracle import MAIN_CASES, EXPLORATORY, GHCR_PIN, checkout_identity, source

BASE = ROOT / "tests/fixtures/cpc6128/j1_15_string_scalar"
# Pinned independently only AFTER first real ROM acquisition, never synthesized.
PINNED_MANIFEST_SHA = None
PINNED_RAM = {}
PINNED_PRINTER = {}

class Invalid(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise Invalid(message)

def sha(b):
    return hashlib.sha256(b).hexdigest()

def read(path):
    require(path.is_file() and not path.is_symlink(), "MISSING_OR_SYMLINK "+str(path))
    return path.read_bytes()

def inventory(directory):
    require(directory.is_dir() and not directory.is_symlink(), "MISSING_DIRECTORY "+str(directory))
    files = {}
    for p in sorted(directory.rglob("*")):
        require(not p.is_symlink() and p.suffix.lower() not in (".rom",".sna",".dsk",".cpr",".zip"),
                "UNSAFE_ARCHIVE_ITEM "+str(p))
        if p.is_file():
            b = read(p)
            files[p.relative_to(directory).as_posix()] = {"sha256":sha(b),"size_bytes":len(b)}
    return files

def check_sources():
    require(len(MAIN_CASES) >= 12 and len(set(MAIN_CASES)) == len(MAIN_CASES),
            "MISSING_12_DISTINCT_POSITIVE_SOURCES")
    for name in (*MAIN_CASES, *EXPLORATORY):
        raw, nums = source(name)
        require(len(nums) >= 3 and nums == sorted(set(nums)), name+": LINE_SEQUENCE")
        if name in MAIN_CASES:
            require(b"PRINT #8," in raw.upper() and b"PRINT " in raw.upper()
                    and b"$" in raw and raw.splitlines()[-1].upper().endswith(b"END"),
                    name+": STRING_PRINTER_OR_END_MISSING")
    print("PASS J1.15-A",len(MAIN_CASES),"CANDIDATE +",
          len(EXPLORATORY),"EXPLORATORY SOURCES; NOT ROM EVIDENCE")

def string_records(image, lines, records):
    selected = []
    for original, rec in zip(lines.splitlines(),records):
        if b"$" not in original:
            continue
        record = image[rec["offset"]:rec["offset"]+rec["length"]]
        require(record[-1] == 0 and record[:2] == len(record).to_bytes(2,"little") and
                int.from_bytes(record[2:4],"little") == rec["line"],
                "STRING_RECORD_LENGTH_HEADER_INVALID")
        selected.append({"line_number":rec["line"],
                         "record_hex":record.hex(" ").upper(),
                         "record_length":len(record)})
    require(bool(selected), "NO_STRING_RECORD")
    return selected

def check_pre(base, name, mode, evidence, raw, nums):
    folder = base/mode/name
    info = evidence["pre_run"]
    program = read(folder/"program.bin")
    lines, records = oracle.records(program)
    require(lines == nums and program.endswith(b"\x00\x00"), name+": BAD_ROM_RECORDS")
    region = info["region"]
    require(info["case"] == name and info["source_sha256"] == sha(raw) and
            info["snapshot_taken_before_run"] is True and info["list_requested"] is True and
            region["records"] == records and region["line_numbers"] == nums and
            region["start_address"] == region["base_pointer_value"]+1 and
            region["end_exclusive"]-region["start_address"] == len(program) and
            region["sentinel_offset"] == len(program)-2 and
            info["string_records"] == string_records(program,raw,records),
            name+": ROM_REGION_OR_VARIABLE_RECORD_INVALID_"+mode)
    require(read(folder/"original.bas") == raw, name+": SOURCE_REWRITTEN_"+mode)
    listed = json.loads(read(folder/"autocmd.json"))
    require(listed["commands"][:len(nums)] == raw.decode("ascii").splitlines()
            and listed["commands"][len(nums)] == "LIST" and
            listed["snapshot_before_run"] is True and
            not any(x == "RUN" for x in listed["commands"]) and
            listed["source_sha256"] == sha(raw),
            name+": LIST_PRE_RUN_NOT_INDEPENDENT_"+mode)
    require(read(folder/"list.png")[:8] == b"\x89PNG\r\n\x1a\n",
            name+": LIST_SCREEN_MISSING_"+mode)
    comparison = info["comparison"]
    require(json.loads(read(folder/"comparison.json")) == comparison and
            comparison["cpc_size"] == len(program) and
            comparison["cpc_sha256"] == sha(program),
            name+": C99_COMPARISON_NOT_REPRODUCIBLE_"+mode)
    if comparison["classification"] == "UNSUPPORTED":
        require(comparison["c99_sha256"] is None and comparison["c99_size"] is None and
                comparison["first_difference"] is None and
                "image-cli: input rejected:" in comparison["c99_rejection"] and
                comparison["c99_rejection"] == read(folder/"c99_error.txt").decode().strip() and
                not (folder/"c99.bin").exists(),
                name+": FALSE_UNSUPPORTED_"+mode)
    else:
        c99 = read(folder/"c99.bin")
        require(comparison["classification"] in ("DIFF","MATCH_EXACT") and
                comparison["c99_sha256"] == sha(c99) and
                comparison["c99_size"] == len(c99) and
                (comparison["classification"] == "MATCH_EXACT") == (program == c99),
                name+": FALSE_NATIVE_CLASSIFICATION_"+mode)
    for filename, h in info["files"].items():
        content = read(folder/filename)
        require({"sha256":sha(content),"size_bytes":len(content)} == h,
                name+": PRE_MANIFEST_FILE_MISMATCH_"+mode+"/"+filename)
    return program

def check_run(base,name,mode,evidence,raw):
    folder = base/mode/name/"run"
    data = evidence["run"]
    require(data["fresh_cpc_run_process"] is True and data["returncode"] == 0 and
            data["screen_png_present"] is True and data["result_class"] == "OBSERVED" and
            data["numeric_err_erl_probes"] is True,
            name+": ROM_RUN_UNVERIFIED_"+mode)
    printer = read(folder/"printer.dat")
    lines = printer.splitlines(keepends=True)
    require(2 <= len(lines) <= 64, name+": PRINTER_PROBES_MISSING_"+mode)
    probes = [parse_integer(row) for row in lines[-2:]]
    require(all(p is not None for p in probes), name+": ERR_ERL_NONNUMERIC_"+mode)
    require(data["printer_raw_hex"] == printer.hex(" ").upper() and
            data["string_trace_hex"] == b"".join(lines[:-2]).hex(" ").upper() and
            data["err_probe"] == probes[0]["numeric_value"] and
            data["erl_probe"] == probes[1]["numeric_value"] and len(printer) <= 2048,
            name+": STRING_TRACE_OR_PROBES_CHANGED_"+mode)
    commands = json.loads(read(folder/"autocmd.json"))["commands"]
    require(commands[:len(raw.splitlines())] == raw.decode("ascii").splitlines() and
            commands[len(raw.splitlines())] == "RUN" and
            "PRINT #8,ERR" in commands and "PRINT #8,ERL" in commands,
            name+": RUN_COMMANDS_CHANGED_"+mode)
    require(read(folder/"run.png")[:8] == b"\x89PNG\r\n\x1a\n",
            name+": RUN_SCREEN_MISSING_"+mode)
    require(inventory(folder) == data["files"],
            name+": PRINTER_RUN_INVENTORY_CHANGED_"+mode)
    return printer

def seal_for(base,m):
    return {
        "schema":1, "phase":"J1.15-A-PROVISIONAL",
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
    require(m.get("schema_version")==1 and m.get("phase")=="J1.15-A" and
            m.get("ghcr_image")==GHCR_PIN and m.get("rom_archived") is False and
            m.get("full_snapshots_archived") is False and
            m.get("historical_archives_modified") is False and
            m.get("j1_15_b_authorized") is False and
            m.get("printer_is_screen_output") is False,
            "PROVENANCE_MANIFEST_INVALID")
    ident = m.get("oracle",{})
    require(ident.get("emulator")=="Caprice32" and ident.get("commit")==oracle.PIN and
            ident.get("rom_sha256")==oracle.ROM_SHA and ident.get("model")=="CPC6128" and
            ident.get("basic")=="1.1" and ident.get("ram_kb")==128,
            "UNPINNED_ROM_OR_MODEL")
    require(re.fullmatch("[0-9a-f]{40}",str(m.get("github_head_sha",""))) and
            re.fullmatch("[0-9]+",str(m.get("github_run_id",""))),
            "ORIGIN_CHECKOUT_RUN_ID_ABSENT")
    require(m.get("mandatory_cases")==list(MAIN_CASES) and
            m.get("exploratory_cases")==list(EXPLORATORY) and
            len(m.get("captures",[]))==len(MAIN_CASES) and
            [c["case"] for c in m["captures"]]==list(MAIN_CASES),
            "MISSING_OR_ADDED_CASE")
    expected_root={"original","repeat","exploratory","manifest.json"}
    if (base/"seal.json").exists():
        expected_root.add("seal.json")
    require({x.name for x in base.iterdir()}==expected_root,
            "ARCHIVE_ROOT_INVENTORY_CHANGED")
    for item in m["captures"]:
        name = item["case"]
        src, nums = source(name)
        require(item["source_path"]=="tests/oracles/inputs/j1_15_a/"+name.lower()+".bas"
                and item["source_sha256"]==sha(src) and item["lines"]==nums and
                item["two_independent_process_pairs"] is True and
                item["ram_exact_2of2"] is True and
                item["printer_exact_2of2"] is True,
                name+": ACQUISITION_CLAIM_CHANGED")
        checks=[]
        for mode in ("original","repeat"):
            entry=item[mode]
            rom=check_pre(base,name,mode,entry,src,nums)
            printer=check_run(base,name,mode,entry,src)
            require(inventory(base/mode/name)==entry["all_files_sha256"],
                    name+": FULL_INVENTORY_CHANGED_"+mode)
            checks.append((rom,printer))
        require(checks[0]==checks[1],name+": TWO_ROM_PROCESS_PAIRS_DIFFER")
    require(len(m.get("explorations",[]))==len(EXPLORATORY) and
            [i["case"] for i in m["explorations"]]==list(EXPLORATORY),
            "EXPLORATORY_CASES_MISSING")
    for exp in m["explorations"]:
        name=exp["case"]
        src,nums=source(name)
        folder=base/"exploratory"/name
        require(read(folder/"original.bas")==src and
                exp["original_source_sha256"]==sha(src) and
                exp["line_numbers"]==nums and
                exp["scope"]=="EXPLORATION_ONLY_NEVER_J1_15_B_PROOF" and
                exp["run"]["printer_raw_hex"]==
                  (read(folder/"run/printer.dat").hex(" ").upper()
                   if (folder/"run/printer.dat").is_file() else "") and
                inventory(folder/"run")==exp["run"]["files"],
                name+": EXPLORATORY_BOUNDS_OR_EVIDENCE_CHANGED")
    if (base/"seal.json").exists():
        require(json.loads(read(base/"seal.json"))==seal_for(base,m),
                "PROVISIONAL_SEAL_MISMATCH")
    else:
        require(not permanent,"NO_PERMANENT_SEAL")
    if permanent:
        require(re.fullmatch("[0-9a-f]{64}",str(PINNED_MANIFEST_SHA)) and
                set(PINNED_RAM)==set(MAIN_CASES) and
                set(PINNED_PRINTER)==set(MAIN_CASES),
                "EXTERNAL_PINS_PENDING_OR_INCOMPLETE")
        require(sha(read(base/"manifest.json"))==PINNED_MANIFEST_SHA,
                "EXTERNALLY_PINNED_MANIFEST_DIFFERENT")
        for name in MAIN_CASES:
            require(sha(read(base/"original"/name/"program.bin"))==PINNED_RAM[name] and
                    sha(read(base/"original"/name/"run/printer.dat"))==PINNED_PRINTER[name],
                    name+": EXTERNAL_ROM_OR_PRINTER_SHA_CHANGED")
    return m

def falsify(base):
    require(base.resolve()==BASE.resolve(),"FALSIFY_CANONICAL_ONLY")
    with tempfile.TemporaryDirectory(prefix="j115a-mutate-") as tmp:
        t = Path(tmp)/"candidate"
        shutil.copytree(base,t)
        name=MAIN_CASES[0]
        changes=[
            ("ROM_RECORD",t/"original"/name/"program.bin",4),
            ("ROM_REPEAT",t/"repeat"/name/"program.bin",5),
            ("PRINTER",t/"original"/name/"run/printer.dat",0),
            ("PRINTER_REPEAT",t/"repeat"/name/"run/printer.dat",0),
            ("LIST_SCREEN",t/"original"/name/"list.png",10),
            ("SOURCE",t/"original"/name/"original.bas",5),
            ("RUN_COMMANDS",t/"original"/name/"run/autocmd.json",3),
            ("C99_COMPARISON",t/"original"/name/"comparison.json",3),
            ("MANIFEST",t/"manifest.json",3),
            ("SEAL",t/"seal.json",3),
            ("EXPLORATORY",t/"exploratory"/EXPLORATORY[0]/"run/autocmd.json",3),
        ]
        for label,path,offset in changes:
            old=read(path)
            require(offset<len(old),"BAD_TEST_OFFSET")
            broken=bytearray(old)
            broken[offset]^=1
            path.write_bytes(broken)
            try: verify(t,permanent=True)
            except (Invalid,ValueError,TypeError,KeyError,UnicodeError):
                print("PASS J1.15-A REJECTED_MUTATION",label,flush=True)
            else:
                raise Invalid("ACCEPTED_MUTATION_"+label)
            path.write_bytes(old)
        # File deletion must fail before optional checksum checks.
        missing=t/"repeat"/name/"program.bin"
        missing.unlink()
        try: verify(t,permanent=True)
        except (Invalid,ValueError,TypeError,KeyError,UnicodeError):
            print("PASS J1.15-A REJECTED_MISSING_CASE_FILE",flush=True)
        else: raise Invalid("ACCEPTED_MISSING_CASE_FILE")
        actual=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip()
        require(checkout_identity(actual)==actual,"HEAD_BASELINE_BAD")
        false=("0" if actual[0]!="0" else "1")+actual[1:]
        try: checkout_identity(false)
        except ValueError: print("PASS J1.15-A REJECTED_FALSE_HEAD",flush=True)
        else: raise Invalid("ACCEPTED_FALSE_HEAD")
    print("PASS J1.15-A 12 MUTATIONS + FALSE HEAD",flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence",type=Path,default=BASE)
    p.add_argument("--check-sources",action="store_true")
    p.add_argument("--write-provisional-seal",action="store_true")
    p.add_argument("--permanent",action="store_true")
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    if args.check_sources:
        check_sources()
        return
    evidence=args.evidence.resolve()
    if args.write_provisional_seal:
        require(not (evidence/"seal.json").exists(),"REFUSE_RESEAL")
        manifest=verify(evidence)
        (evidence/"seal.json").write_text(json.dumps(seal_for(evidence,manifest),indent=2)+"\n")
    m=verify(evidence,args.permanent)
    print("PASS J1.15-A",len(m["captures"]),"CANDIDATES ORIGINAL+REPEAT",
          "PERMANENT="+str(args.permanent),flush=True)
    if args.self_test:
        require(args.permanent,"SELF_TEST_REQUIRES_PERMANENT")
        falsify(evidence)

if __name__=="__main__":
    try:
        main()
    except (Invalid,ValueError,TypeError,KeyError,UnicodeError,OSError,
            subprocess.SubprocessError) as exc:
        print("J1.15-A VERIFY FAILED:",exc,file=sys.stderr)
        sys.exit(1)
