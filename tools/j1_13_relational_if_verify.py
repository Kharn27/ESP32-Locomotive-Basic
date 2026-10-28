#!/usr/bin/env python3
"""J1.13-A: fail-closed verifier of independent CPC6128 IF-relational captures.

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
from j1_13_relational_if_oracle import MAIN_CASES, EXPLORATORY, GHCR_PIN, checkout_identity

BASE = ROOT / "tests/fixtures/cpc6128/j1_13_integer_relations"
# EXTERNAL FIRST-CAPTURE ANCHORS: absent until the original GHCR archive is
# produced by the GitHub bot. An empty value always fails permanent mode.
# Transcribed from independent GHCR original run 40615245342
# acquired at HEAD 9ef54a01f9b8c12eb11c559c3930cd3d37729a2a; seal remains PENDING_PILOTAGE.
# External anchors intentionally absent until real CPC archival.
PINNED_MANIFEST_SHA = "69ee185aa63fe6db1df8f6092af19df0a15dec70b991d918e8f99d2657a03070"
PINNED_RAM = {
    "R_EQ_TRUE": "0f79939f13668678076db8f343f2c2b9bac56bcf0f6d934a1bd487c11da237f7",
    "R_EQ_FALSE": "08266884653b12837c0cb113eedfdb119e4f1537c306b2b05e1f65cca8f2c796",
    "R_EQ_EQUAL": "d73c62aee922b85bd4a001e9323c81c457595856e8f6823e3ebf1234d3a2eaca",
    "R_EQ_SIGNED": "ef6b1f39009b04e6a90c47a357b9bcd786c17b0bee5d6de0fc063675fd4b35b5",
    "R_NE_TRUE": "5ef010e5eae894f810fa9c7ff77c9fdde05641f6d7e33b7694be8bf6074fa625",
    "R_NE_FALSE": "84a9e182bff4cda2992b180c88fe9e3e0c0f8b26d2d66ecac4bc8c4f472a0888",
    "R_NE_EQUAL": "277beddb3e9da52323224396bf68c4cd17858d7528e19982a280e41c000733c1",
    "R_NE_SIGNED": "c4f11e2205b022a2bcd5fc4064e9dcc3ebff83c9db615cc68b6ace8812d56dd6",
    "R_LT_TRUE": "2624946da42d3044f2000d6a6f55068fa769699daaed566b0b4b6da085a06c79",
    "R_LT_FALSE": "271f5f76dfa8e3b06a9c207deb25d99c45ea482f1e420dded5e914744f34ee22",
    "R_LT_EQUAL": "7a8c27302379cdd16c7b19b64bd87e62c3bc40755250a81d77a04a65302fb60b",
    "R_LT_SIGNED": "b0507b46077358c0eee7402ea82be3995f427c0222ad3f6be2a63c1e9dfd4eec",
    "R_LE_TRUE": "f9446b78a5ee44ac11ced5db6d5d948a6e600dd48913a5bfe4136a6201f1468b",
    "R_LE_FALSE": "fc6599dbc8966b89410e535628c615ae5a9cd0287fca5295921eee586c56b257",
    "R_LE_EQUAL": "19ec08d25f88769609b070a623514cc2ef741cd7768fd21c13f974fe048a259f",
    "R_LE_SIGNED": "9ad015ee766ca1894f5660e32f6a9c2356bf1a7ac0ffeeb2317f0502f9f91808",
    "R_GT_TRUE": "d0ab87b668ad4a1a694ca2af2be6eda9980b9bdc03f4a0d21b2d63bbf9ca23d1",
    "R_GT_FALSE": "9b8c88df1e78b672db613aa91ac0c8342edfc6e4cb30a9bd817b94d2c065a2e5",
    "R_GT_EQUAL": "b079ef07487757b5be57208964722e63844e5d20d7e37b34ab0db5660d7a2d7b",
    "R_GT_SIGNED": "1b03063b2798f9db98b093c3adba1216fdcf1e2cd88d5c945e18abfa2c2a1cbf",
    "R_GE_TRUE": "da350553e29ffa0f055afedbb38d5cc961d3df0580a8b94c2b6289b5c054dfdd",
    "R_GE_FALSE": "8da513af468dc6c2dd7590aef297a572aba357ebe8fae1ec0c05d7c569a5d91c",
    "R_GE_EQUAL": "e2ba53d08236d63c59e9b6fdab2245e2fd2da00cfa8606552f4df89b201bc2bd",
    "R_GE_SIGNED": "2c900e3bbe4452a880ad1ebdb4da5c9b7b48de7582fc849a63aeadaa4e21d635"
}
PINNED_PRINTER = {
    "R_EQ_TRUE": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_EQ_FALSE": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_EQ_EQUAL": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_EQ_SIGNED": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_NE_TRUE": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_NE_FALSE": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_NE_EQUAL": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_NE_SIGNED": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_LT_TRUE": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_LT_FALSE": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_LT_EQUAL": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_LT_SIGNED": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_LE_TRUE": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_LE_FALSE": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_LE_EQUAL": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_LE_SIGNED": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_GT_TRUE": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_GT_FALSE": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_GT_EQUAL": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_GT_SIGNED": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_GE_TRUE": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_GE_FALSE": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca",
    "R_GE_EQUAL": "4bb323d31e58432fbaadd114190987cb5d42f654136cf5ab3520a1e6bf8f7ad1",
    "R_GE_SIGNED": "1cc3739a064ab6cca380953f5c949a5216be05028db6e9846951f5d64bf12fca"
}
PINNED_OUTCOMES = {
    "R_EQ_TRUE": [
        [
            810
        ],
        0,
        0
    ],
    "R_EQ_FALSE": [
        [
            420
        ],
        0,
        0
    ],
    "R_EQ_EQUAL": [
        [
            810
        ],
        0,
        0
    ],
    "R_EQ_SIGNED": [
        [
            420
        ],
        0,
        0
    ],
    "R_NE_TRUE": [
        [
            810
        ],
        0,
        0
    ],
    "R_NE_FALSE": [
        [
            420
        ],
        0,
        0
    ],
    "R_NE_EQUAL": [
        [
            420
        ],
        0,
        0
    ],
    "R_NE_SIGNED": [
        [
            810
        ],
        0,
        0
    ],
    "R_LT_TRUE": [
        [
            810
        ],
        0,
        0
    ],
    "R_LT_FALSE": [
        [
            420
        ],
        0,
        0
    ],
    "R_LT_EQUAL": [
        [
            420
        ],
        0,
        0
    ],
    "R_LT_SIGNED": [
        [
            810
        ],
        0,
        0
    ],
    "R_LE_TRUE": [
        [
            810
        ],
        0,
        0
    ],
    "R_LE_FALSE": [
        [
            420
        ],
        0,
        0
    ],
    "R_LE_EQUAL": [
        [
            810
        ],
        0,
        0
    ],
    "R_LE_SIGNED": [
        [
            420
        ],
        0,
        0
    ],
    "R_GT_TRUE": [
        [
            810
        ],
        0,
        0
    ],
    "R_GT_FALSE": [
        [
            420
        ],
        0,
        0
    ],
    "R_GT_EQUAL": [
        [
            420
        ],
        0,
        0
    ],
    "R_GT_SIGNED": [
        [
            810
        ],
        0,
        0
    ],
    "R_GE_TRUE": [
        [
            810
        ],
        0,
        0
    ],
    "R_GE_FALSE": [
        [
            420
        ],
        0,
        0
    ],
    "R_GE_EQUAL": [
        [
            810
        ],
        0,
        0
    ],
    "R_GE_SIGNED": [
        [
            420
        ],
        0,
        0
    ]
}

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
    p = ROOT / "tests/oracles/inputs/j1_13_a" / (name.lower() + ".bas")
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
    found = []
    for idx, row in enumerate(lines.splitlines()):
        if re.search(rb"\bIF\b", row):
            rec = records[idx]
            binary = data[rec["offset"]:rec["offset"]+rec["length"]]
            require(binary[-1:] == b"\0" and
                    binary[:2] == len(binary).to_bytes(2, "little") and
                    int.from_bytes(binary[2:4], "little") == rec["line"],
                    "CPC_FLOW_LINE_HEADER_INVALID")
            # Observed ROM token layout of the IF line: IF=A1, 02 caches,
            # relation opcode, THEN=EB, direct line number 1E 46 00.
            opcodes = {b"=":0xef, b"<>":0xf2, b"<":0xf1,
                       b"<=":0xf3, b">":0xee, b">=":0xf0}
            match = re.search(rb"IF A%(<>|<=|>=|=|<|>)B% THEN 70", row)
            require(match is not None and len(binary)==22 and
                    binary[4]==0xa1 and binary[6]==0x02 and
                    binary[11]==0x02 and binary[10]==opcodes[match.group(1)] and
                    binary[16]==0xeb and binary[18:21]==b"\\x1e\\x46\\x00",
                    "CPC_IF_RELATIONAL_ROM_TOKEN_LAYOUT_CHANGED")
            found.append({"line_number":rec["line"],
                          "record_hex":binary.hex(" ").upper(),
                          "record_length":len(binary)})
    require(bool(found), "NO_IF_RELATIONAL")
    return found

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
        "schema": 1, "phase":"J1.13-A-PROVISIONAL",
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
    require(m.get("phase") == "J1.13-A" and m.get("schema_version") == 1 and
            m.get("rom_archived") is False and
            m.get("full_snapshots_archived") is False and
            m.get("printer_is_screen_output") is False and
            m.get("j1_13_b_authorized") is False and
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
            m.get("exploratory_cases") == list(EXPLORATORY) and
            m.get("explorations") == [],
            "CASE_SET_CHANGED")
    captures = m.get("captures", [])
    require(len(captures) == len(MAIN_CASES) == 24 and
            [c["case"] for c in captures] == list(MAIN_CASES),
            "MISSING_OR_ADDED_CASES")
    # Git does not retain a deliberately empty exploratory/ directory.
    # If it exists during the ephemeral acquisition it MUST remain empty;
    # an archived checkout may omit that empty directory entirely.
    exploratory = base/"exploratory"
    require((base/"original").is_dir() and (base/"repeat").is_dir() and
            (not exploratory.exists() or
             (exploratory.is_dir() and not exploratory.is_symlink() and
              not list(exploratory.iterdir()))),
            "ROOT_PROOF_LAYOUT_CHANGED")
    expected_root = {"original","repeat","manifest.json"}
    if exploratory.exists():
        expected_root.add("exploratory")
    if (base/"seal.json").exists():
        expected_root.add("seal.json")
    require({p.name for p in base.iterdir()} == expected_root,
            "ROOT_FILES_CHANGED")
    for c in captures:
        name = c["case"]
        src, nums = source(name)
        require(c["source_path"] ==
                "tests/oracles/inputs/j1_13_a/"+name.lower()+".bas" and
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
    with tempfile.TemporaryDirectory(prefix="j113a-falsify-") as tmp:
        copy = Path(tmp)/"candidate"
        shutil.copytree(base,copy)
        name = MAIN_CASES[0]
        targets = (
            ("RAM",copy/"original"/name/"program.bin"),
            ("IF_OPERATOR_TOKEN",copy/"original"/name/"program.bin"),
            ("INTEGER_CACHE",copy/"original"/name/"program.bin"),
            ("SECOND_INTEGER_CACHE",copy/"original"/name/"program.bin"),
            ("THEN_TOKEN",copy/"original"/name/"program.bin"),
            ("REPEAT_IF_RECORD",copy/"repeat"/name/"program.bin"),
            ("THEN_TARGET",copy/"original"/name/"program.bin"),
            ("PRINTER",copy/"original"/name/"run/printer.dat"),
            ("LIST_PNG",copy/"original"/name/"list.png"),
            ("RUN_PNG",copy/"original"/name/"run/run.png"),
            ("SOURCE",copy/"original"/name/"original.bas"),
            ("COMPARISON",copy/"original"/name/"comparison.json"),
            ("RUN_COMMANDS",copy/"original"/name/"run/autocmd.json"),
            ("MANIFEST",copy/"manifest.json"),
            ("SEAL",copy/"seal.json"),
            ("REPEAT_RAM",copy/"repeat"/name/"program.bin"),
            ("REPEAT_PRINTER",copy/"repeat"/name/"run/printer.dat"),
            ("REPEAT_LIST",copy/"repeat"/name/"list.png"),
        )
        for label,path in targets:
            raw = read(path)
            require(len(raw) >= 3,label+": SHORT_FALSIFICATION_TARGET")
            corrupt = bytearray(raw)
            byte_index = 2
            # Positions obtained from the archived IF records (line 30), not
            # from a C99-produced token stream: operator 10, cache 7/12,
            # THEN 16, literal target byte 19.
            targeted = {
                "IF_OPERATOR_TOKEN":10, "INTEGER_CACHE":7,
                "SECOND_INTEGER_CACHE":12, "THEN_TOKEN":16,
                "THEN_TARGET":19, "REPEAT_IF_RECORD":10
            }
            if label in targeted:
                observed,rows = oracle.records(raw)
                rec = next(row for row in rows if row["line"] == 30)
                require(observed == [10,20,30,40,50,70,80],
                        label+": CANNOT_LOCATE_AUTHENTIC_IF_RECORD")
                byte_index = rec["offset"] + targeted[label]
                require(byte_index < len(raw), label+": SHORT_IF_RECORD")
            elif label == "SOURCE":
                byte_index = raw.index(b"IF A%") + len(b"IF A%")
            corrupt[byte_index] ^= 1
            path.write_bytes(corrupt)
            try:
                verify(copy,permanent=True)
            except (Invalid,ValueError,UnicodeError,KeyError,TypeError):
                print("PASS J1.13-A FALSIFICATION_REJECTED",label,flush=True)
            else:
                raise Invalid("FALSIFICATION_ACCEPTED_"+label)
            path.write_bytes(raw)
            require(read(path) == raw,label+": FALSIFICATION_RESET_FAILED")
        actual = subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],
                                         text=True).strip()
        require(checkout_identity(actual) == actual,"ACTUAL_HEAD_NOT_ACCEPTED")
        fake = ("0" if actual[0] != "0" else "1") + actual[1:]
        try:
            checkout_identity(fake)
        except ValueError:
            print("PASS J1.13-A FALSE_HEAD_REJECTED",flush=True)
        else:
            raise Invalid("FALSE_HEAD_ACCEPTED")
        require(sha(read(base/"manifest.json")) == PINNED_MANIFEST_SHA,
                "CANONICAL_MANIFEST_CHANGED_BY_NEGATIVES")
    print("PASS J1.13-A 18 FALSIFICATIONS + FALSE HEAD",flush=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence",type=Path,default=BASE)
    p.add_argument("--write-provisional-seal",action="store_true")
    p.add_argument("--permanent",action="store_true")
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--check-sources",action="store_true")
    args = p.parse_args()
    if args.check_sources:
        for name in MAIN_CASES:
            src,nums = source(name)
            require(len(nums)==7 and b" IF " in src, name+": BAD_RELATIONAL_SOURCE")
        print("PASS J1.13-A 24 SOURCE_CASES, NOT ROM EVIDENCE")
        return
    base = args.evidence.resolve()
    if args.write_provisional_seal:
        require(not (base/"seal.json").exists(), "REFUSE_TO_RESEAL")
        m = verify(base)
        (base/"seal.json").write_text(json.dumps(seal_for(base,m),indent=2)+"\n")
    m = verify(base,args.permanent)
    print("PASS J1.13-A",len(m["captures"]),"CASES",
          "ORIGINAL+REPEAT", "PERMANENT="+str(args.permanent),flush=True)
    if args.self_test:
        require(args.permanent,"SELF_TEST_REQUIRES_PERMANENT")
        falsify(base)

if __name__ == "__main__":
    try:
        main()
    except (Invalid,ValueError,OSError,UnicodeError,KeyError,TypeError) as exc:
        print("J1.13-A VERIFY FAILED:",exc,file=sys.stderr)
        sys.exit(1)
