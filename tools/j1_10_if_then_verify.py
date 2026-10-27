#!/usr/bin/env python3
"""J1.10-A: fail-closed verification of original IF/THEN ROM oracle material.

Pre-implementation: no native IF expected. Original raw CPC archives (including
opaque caches, unmodified printer and screenshot bytes) are authority. The
self-test falsifies temporary copies only, never the evidence or old fixtures.
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tests/oracles"))
import token_ram_oracle as oracle
from signed_print_oracle import parse_integer
from j1_10_if_then_oracle import MAIN_CASES, EXPLORATORY, GHCR_PIN, checkout_identity

BASE=ROOT/"tests/fixtures/cpc6128/j1_10_if_then"
# Filled ONLY AFTER the first original GHCR acquisition, from its bot archive.
# Do not infer these values from C99, an emulator guess or a hand-built image.
PINNED_MANIFEST_SHA=None
PINNED_RAM={}
PINNED_PRINTER={}

class Invalid(ValueError):
    pass

def require(ok,message):
    if not ok: raise Invalid(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path):
    require(path.is_file() and not path.is_symlink(),
            "MISSING_OR_SYMLINK:"+str(path))
    return path.read_bytes()

def hash_listing(directory):
    require(directory.is_dir() and not directory.is_symlink(),
            "MISSING_DIRECTORY:"+str(directory))
    content={}
    for p in sorted(directory.rglob("*")):
        require(not p.is_symlink(),"SYMLINK_FORBIDDEN:"+str(p))
        require(p.suffix.lower() not in (".rom",".sna",".dsk",".cpr",".zip"),
                "PROHIBITED_ARCHIVE:"+str(p))
        if p.is_file():
            data=read(p)
            content[str(p.relative_to(directory))]={
                "sha256":sha(data),"size_bytes":len(data)}
    return content

def same_files(directory,expected,label):
    require(hash_listing(directory)==expected,label+": FILE_INVENTORY_OR_SHA_CHANGED")

def proof_path(name):
    return ROOT/"tests/oracles/inputs/j1_10_a"/(name.lower()+".bas")

def verify_run(base,name,mode,record):
    folder=base/mode/name
    run=record["run"]
    require(run.get("fresh_cpc_run_process") is True and
            run.get("returncode")==0 and
            run.get("screen_png_present") is True and
            run.get("result_class")=="OBSERVED" and
            run.get("all_printer_lines_numeric") is True,
            name+": RUN_PROOF_MISSING_"+mode)
    require(read(folder/"run/run.png")[:8]==b"\x89PNG\r\n\x1a\n",
            name+": INVALID_RUN_PNG_"+mode)
    printer=read(folder/"run/printer.dat")
    parse=[parse_integer(x) for x in printer.splitlines(keepends=True)]
    require(len(parse)>=2 and all(x is not None for x in parse),
            name+": INVALID_CPC_PRINTER_"+mode)
    values=[x["numeric_value"] for x in parse]
    require(run["printer_raw_hex"]==printer.hex(" ").upper() and
            run["printer_lines"]==values and
            run["program_trace"]==values[:-2] and
            run["err_probe"]==values[-2] and
            run["erl_probe"]==values[-1],
            name+": PRINTER_MISMATCH_"+mode)
    same_files(folder/"run",run["files"],name+"/RUN/"+mode)
    require(read(folder/"run/autocmd.json") and
            "PRINT #8,ERR" in json.loads(read(folder/"run/autocmd.json"))["commands"] and
            "PRINT #8,ERL" in json.loads(read(folder/"run/autocmd.json"))["commands"],
            name+": POSTRUN_PROBE_ABSENT")
    return printer

def verify_pre(base,name,mode,record,source,nums):
    folder=base/mode/name
    pre=record["pre_run"]
    raw=read(folder/"program.bin")
    count, rows=oracle.records(raw)
    require(count==nums and raw.endswith(b"\x00\x00"),
            name+": CPC_RECORDS_OR_SENTINEL_CHANGED_"+mode)
    if_lines=[i for i,s in enumerate(source.splitlines())
              if re.search(rb"\bIF\b",s)]
    require(if_lines and pre["if_line_number"]==nums[if_lines[0]],
            name+": IF_LINE_NOT_FOUND_"+mode)
    line=rows[if_lines[0]]
    encoded=raw[line["offset"]:line["offset"]+line["length"]]
    require(encoded.hex(" ").upper()==pre["if_line_raw_hex"] and
            len(encoded)==pre["if_line_record_length"] and
            encoded.endswith(b"\x00"),
            name+": TOKEN_CACHE_OR_IF_RECORD_TAMPERED_"+mode)
    comparison=pre["comparison"]
    require(comparison["cpc_sha256"]==sha(raw) and
            comparison["classification"] in ("UNSUPPORTED","DIFF","MATCH_EXACT"),
            name+": C99_HISTORICAL_CLASSIFICATION_CHANGED_"+mode)
    require(pre["snapshot_taken_before_run"] is True and
            pre["list_requested"] is True,
            name+": PRE_RUN_PROVENANCE_CHANGED_"+mode)
    require(read(folder/"list.png")[:8]==b"\x89PNG\r\n\x1a\n",
            name+": INVALID_LIST_PNG_"+mode)
    require(read(folder/"original.bas")==source,name+": ORIGINAL_SOURCE_CHANGED_"+mode)
    for file,metadata in pre["files"].items():
        p=folder/file
        data=read(p)
        require({"sha256":sha(data),"size_bytes":len(data)}==metadata,
                name+": PRE_FILE_CHANGED_"+file+"_"+mode)
    return raw

def seal_for(base,manifest):
    return {
        "schema":1,"phase":"J1.10-A-PROVISIONAL",
        "approval":"PENDING_PILOTAGE",
        "acquisition_head_sha":manifest["github_head_sha"],
        "acquisition_run_id":manifest["github_run_id"],
        "manifest_sha256":sha(read(base/"manifest.json")),
        "program_sha256":{row["case"]:sha(read(base/"original"/row["case"]/"program.bin"))
                          for row in manifest["captures"]},
        "printer_sha256":{row["case"]:sha(read(base/"original"/row["case"]/"run/printer.dat"))
                          for row in manifest["captures"]}
    }

def verify(base,permanent=False):
    m=json.loads(read(base/"manifest.json"))
    require(m.get("phase")=="J1.10-A" and m.get("schema_version")==1 and
            m.get("rom_archived") is False and
            m.get("full_snapshots_archived") is False and
            m.get("printer_is_screen_output") is False and
            m.get("j1_10_b_authorized") is False and
            m.get("historical_archives_modified") is False and
            m.get("ghcr_image")==GHCR_PIN,
            "ACQUISITION_PROVENANCE_CHANGED")
    info=m.get("oracle",{})
    require(info.get("commit")==oracle.PIN and
            info.get("rom_sha256")==oracle.ROM_SHA and
            info.get("model")=="CPC6128" and
            info.get("basic")=="1.1" and info.get("ram_kb")==128 and
            info.get("emulator")=="Caprice32",
            "ORACLE_ROM_OR_VERSION_CHANGED")
    require(re.fullmatch("[a-f0-9]{40}",str(m.get("github_head_sha",""))) and
            re.fullmatch("[0-9]+",str(m.get("github_run_id",""))),
            "GHCR_CHECKOUT_IDENTITY_ABSENT")
    require(m.get("mandatory_cases")==list(MAIN_CASES) and
            m.get("exploratory_cases")==list(EXPLORATORY),
            "CASE_INVENTORY_CHANGED")
    captures=m.get("captures",[])
    require(len(captures)==len(MAIN_CASES) and
            {r["case"] for r in captures}==set(MAIN_CASES),
            "MANDATORY_CASES_MISSING")
    explore=m.get("explorations",[])
    require(len(explore)==len(EXPLORATORY) and
            {r["case"] for r in explore}==set(EXPLORATORY),
            "EXPLORATORY_CASES_MISSING")
    for item in captures:
        name=item["case"]
        src=read(proof_path(name))
        nums=[int(s.split(b" ",1)[0]) for s in src.splitlines()]
        require(item["source_path"]==
                "tests/oracles/inputs/j1_10_a/"+name.lower()+".bas" and
                item["source_sha256"]==sha(src) and
                item["lines"]==nums and
                item["two_independent_process_pairs"] is True and
                item["ram_exact_2of2"] is True and
                item["printer_exact_2of2"] is True,
                name+": TWO_PROCESS_PROVENANCE_CHANGED")
        first,second=[],[]
        for mode,target in (("original",first),("repeat",second)):
            proof=item[mode]
            target.append(verify_pre(base,name,mode,proof,src,nums))
            target.append(verify_run(base,name,mode,proof))
            same_files(base/mode/name,proof["all_files_sha256"],
                       name+"/ALL/"+mode)
        require(first==second,name+": TWO_CPC_SESSIONS_DISAGREE")
    for item in explore:
        name=item["case"]
        require(item["scope"]=="EXPLORATION_ONLY_NEVER_J1_10_B_PROOF",
                name+": EXPLORATION_SCOPE_CHANGED")
        src=read(proof_path(name))
        folder=base/"exploratory"/name
        require(item["original_source_sha256"]==sha(src) and
                read(folder/"original.bas")==src,
                name+": EXPLORATION_SOURCE_CHANGED")
        run=item["run"]
        require(run["fresh_cpc_run_process"] is True and
                run["printer_raw_hex"]==
                (read(folder/"run/printer.dat").hex(" ").upper()
                 if (folder/"run/printer.dat").is_file() else ""),
                name+": EXPLORATION_RAW_PRINTER_CHANGED")
        same_files(folder/"run",run["files"],name+"/EXPLORATION")
    inventory={"manifest.json"} | ({"seal.json"} if (base/"seal.json").is_file() else set())
    for mode in ("original","repeat"):
        inventory.add(mode)
    inventory.add("exploratory")
    require({x.name for x in base.iterdir()}==inventory,
            "ARCHIVE_ROOT_INVENTORY_CHANGED")
    seal_path=base/"seal.json"
    if permanent:
        require(isinstance(PINNED_MANIFEST_SHA,str) and
                len(PINNED_MANIFEST_SHA)==64 and
                set(PINNED_RAM)==set(MAIN_CASES) and
                set(PINNED_PRINTER)==set(MAIN_CASES),
                "PERMANENT_ANCHORS_NOT_ESTABLISHED_EXTERNALLY")
        require(sha(read(base/"manifest.json"))==PINNED_MANIFEST_SHA,
                "INDEPENDENT_MANIFEST_ANCHOR_MISMATCH")
        for name in MAIN_CASES:
            require(sha(read(base/"original"/name/"program.bin"))==PINNED_RAM[name],
                    name+": INDEPENDENT_RAM_ANCHOR_MISMATCH")
            require(sha(read(base/"original"/name/"run/printer.dat"))==
                    PINNED_PRINTER[name],
                    name+": INDEPENDENT_PRINTER_ANCHOR_MISMATCH")
    if seal_path.exists():
        actual=json.loads(read(seal_path))
        require(actual==seal_for(base,m),"ORIGINAL_SEAL_MISMATCH")
        if permanent:
            require(actual["manifest_sha256"]==PINNED_MANIFEST_SHA and
                    actual["program_sha256"]==PINNED_RAM and
                    actual["printer_sha256"]==PINNED_PRINTER,
                    "PROVISIONAL_SEAL_NOT_EXTERNALLY_PINNED")
    else:
        require(not permanent,"PERMANENT_REQUIRES_SEAL")
    return m

def falsify(base):
    # Deep copies guarantee the historical evidence is left untouched.
    with tempfile.TemporaryDirectory(prefix="loco-j110-falsify-") as tmp:
        dst=Path(tmp)/"copy"
        shutil.copytree(base,dst)
        for label,path in (
            ("RAM",dst/"original/F_ONE_FORWARD/program.bin"),
            ("PRINTER",dst/"original/F_ONE_FORWARD/run/printer.dat"),
            ("LIST",dst/"original/F_ONE_FORWARD/list.png"),
            ("SOURCE_ARCHIVED",dst/"original/F_ONE_FORWARD/original.bas"),
            ("MANIFEST",dst/"manifest.json"),
            ("SEAL",dst/"seal.json")
        ):
            old=read(path)
            require(len(old)>3,label+": TEST_SOURCE_EMPTY")
            modified=bytearray(old)
            modified[2]^=0x01
            path.write_bytes(modified)
            try:
                verify(dst,permanent=True)
            except (Invalid,ValueError,UnicodeError,KeyError,TypeError):
                print("PASS J1.10-A FALSE_PROOF_REJECTED",label,flush=True)
            else:
                raise Invalid("FORGED_"+label+"_ACCEPTED")
            path.write_bytes(old)
            require(sha(read(path))==sha(old),label+": RESET_FAILED")
        # A forged source with no fixture modification must still be rejected
        # before any acquisition writes to disk.
        fake="f"*40
        actual=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],
                                       text=True).strip()
        if fake==actual: fake="0"*40
        try:
            checkout_identity(fake)
        except ValueError:
            print("PASS J1.10-A FORGED_CHECKOUT_REJECTED",flush=True)
        else:
            raise Invalid("FORGED_CHECKOUT_ACCEPTED")
        require(sha(read(base/"manifest.json"))==PINNED_MANIFEST_SHA,
                "ORIGINAL_ARCHIVE_MUTATED")
    print("PASS J1.10-A SIX_FALSIFICATIONS_AND_FAKE_HEAD",flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence",type=Path,default=BASE)
    p.add_argument("--write-provisional-seal",action="store_true")
    p.add_argument("--permanent",action="store_true")
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    base=args.evidence.resolve()
    if args.write_provisional_seal:
        require(not (base/"seal.json").exists(),"CANNOT_OVERWRITE_ORIGINAL_SEAL")
        m=verify(base)
        (base/"seal.json").write_text(json.dumps(seal_for(base,m),indent=2)+"\n")
    m=verify(base,permanent=args.permanent)
    print("J1.10-A ARCHIVE_VERIFIED",len(m["captures"]),
          "TWO_CPC_ACQUISITIONS_EACH",len(m["explorations"]),
          "EXPLORATIONS", "PERMANENT="+str(args.permanent),flush=True)
    if args.self_test:
        require(args.permanent,"SELF_TEST_REQUIRES_PERMANENT_SEAL")
        falsify(base)

if __name__=="__main__":
    try:
        main()
    except (Invalid,ValueError,OSError,UnicodeError,KeyError,TypeError) as exc:
        print("J1.10-A EVIDENCE INVALID:",exc,file=sys.stderr)
        sys.exit(1)
