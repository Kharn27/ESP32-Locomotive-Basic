#!/usr/bin/env python3
"""J1.11-A: fail-closed verifier of independent CPC6128 GOSUB/RETURN captures.

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
from j1_11_gosub_return_oracle import MAIN_CASES, EXPLORATORY, GHCR_PIN, checkout_identity

BASE = ROOT / "tests/fixtures/cpc6128/j1_11_gosub_return"
# EXTERNAL FIRST-CAPTURE ANCHORS: absent until the original GHCR archive is
# produced by the GitHub bot. An empty value always fails permanent mode.
# Transcribed from independent GHCR original run 40615245342
# acquired at HEAD 9ef54a01f9b8c12eb11c559c3930cd3d37729a2a; seal remains PENDING_PILOTAGE.
PINNED_MANIFEST_SHA = "9cc8a9a4e6b40d278e3fe4fd03b7c671f6b8912374135888b074ab42630424c0"
PINNED_RAM = {
    "F_DIRECT_FORWARD": "5b33c77dd8f0b40d3da682ef15487c1c50acd8db1894fd5ac59a3edcf94b45dd",
    "F_DIRECT_BACK": "0d64c9ec31873aee81d6d5f6fa16c67eecfbc28f4e98ae8ffa031d2ab8a993ff",
    "F_REPEAT": "38f4f8ae5e2b4cd4e5e140fae053ac7b88f0bcb6307093c229bfc08e888e0494",
    "F_NESTED2": "61423873188df48265ce794a70c96f41bfcee0739628e2418d552d2929593cef",
    "F_LAST_RETURN": "e7edcaf39fc0e9347b92ed0809afa667a9f52da2546ee90728b82791122881e4",
    "F_MISSING_TARGET": "03eaa77e5c0fb3e3dbf9b16e3ce31849d9ca3bc1708675cfc4237155e2cd89ee",
    "F_UNPAIRED_RETURN": "d58af5c9b8e64cde910f05a5a50b2b71e9ad673cf88d46398f308bbd2cd77b65",
    "F_END_IN_SUB": "64bdf86326fd056b2ade7cf8e89a1a57f6c7f1eb35eaa21e594bbc1bce6f1a53",
    "F_RETURN_AFTER_PRINTS": "161015062a92339813691f92f6d2efa0e69829cae694c55ac3e075ef50070cb8",
    "F_GOTO_IN_SUB": "1be24e4f496e241094c37550cf9a2b08291479e9ff765bbb86c367115449efb5",
    "F_IF_TRUE_DISPATCH": "89bb6eb3c3badb73667513c52bab4e29064d889d6579c126fcce608e15caf1c3",
    "F_IF_FALSE_DISPATCH": "e38ec6cd9e475e19e27f9c1387e7333d2403b1dd5bbaf02ef6357d891406bba0",
    "F_IF_INSIDE_SUB": "c9bc0db08a57f885c941e0e27a03fac5a0a6a40eddd2e7d9948a9cea9aabf8d4",
    "F_GOTO_AFTER_RETURN": "77e6532cebe126ded5407d1484ca61075ac69e536fe47d887010823603e17d54",
    "F_COLON_CONTINUATION": "c74a48aa8c1bb6181b8307e02762a8468c89c469d3736a1ff5fe6851a207d6b2",
    "F_UNPAIRED_AFTER_CALL": "6bc353ba94b7368b22958dd76951455b51673a5aa490ba0a26f37483be3a42c5"
}
PINNED_PRINTER = {
    "F_DIRECT_FORWARD": "3e55c75e57cfc0d75bfe6abeecaf60d0ffd63009fd610d5e46602e5c6b6e91c3",
    "F_DIRECT_BACK": "571d43b29f08dbbde84b24be0192f6be10c0d40e0c90028cb78929c1377c66c5",
    "F_REPEAT": "acd5bd107889b9e65b73cc06d49a038a7138cadbdfbd8fbf733e9ca327af569f",
    "F_NESTED2": "f8f0614052049e821ceb9a4787f1ecc19ca0634f3ac8f2f161cf245ca3c3fb51",
    "F_LAST_RETURN": "1625663ea41dcfed2c5634c89944ca8bb1754570115fcad8fbd25db9a07b5cb3",
    "F_MISSING_TARGET": "51b494ed5910394c2d1f3a28da5b3fee0f627eaa732e357b963f53c2478740b5",
    "F_UNPAIRED_RETURN": "d55a7a0b93a7cca4403d43efc4569a096e4c3c580a770e4ddfc4241ce521c87f",
    "F_END_IN_SUB": "70f4bfb329bf8cc1c7e7865c188f0f6e2db49725c5f3d06a2fed90737b59459e",
    "F_RETURN_AFTER_PRINTS": "f0f4e855970a128fde6fa2252a481eb49ae5a3784ccc1da821bde7e52a8fb09d",
    "F_GOTO_IN_SUB": "b521ba495798745f76ce640a1466e46651572e3b7856f6737d1015f7a5674ab1",
    "F_IF_TRUE_DISPATCH": "2f18c764d67b3b5fef64904810394c618d7418f6a5d91fdb5d5c672da52efee0",
    "F_IF_FALSE_DISPATCH": "70f4bfb329bf8cc1c7e7865c188f0f6e2db49725c5f3d06a2fed90737b59459e",
    "F_IF_INSIDE_SUB": "9e2a236c109c024ec6a138cbd718664bd9fcaabe9bbf1b3f6afd5aac1829d218",
    "F_GOTO_AFTER_RETURN": "df72fdede71e4553f8741cce5295c43aa8dadb018d1671e0a19a6946a062230e",
    "F_COLON_CONTINUATION": "11571c3482cc65be0aae161ad8a133cc14fa1248c48fe0c8a9ec7979f588231a",
    "F_UNPAIRED_AFTER_CALL": "9ba64c4fe2e9aaf39c72194d24ffcfb4e8f51985490044421ee3f1ac85a50222"
}
PINNED_OUTCOMES = {
    "F_DIRECT_FORWARD": [
        [
            101,
            21
        ],
        0,
        0
    ],
    "F_DIRECT_BACK": [
        [
            201,
            61
        ],
        0,
        0
    ],
    "F_REPEAT": [
        [
            101,
            101,
            31
        ],
        0,
        0
    ],
    "F_NESTED2": [
        [
            101,
            201,
            121,
            21
        ],
        0,
        0
    ],
    "F_LAST_RETURN": [
        [
            21
        ],
        0,
        0
    ],
    "F_MISSING_TARGET": [
        [],
        8,
        10
    ],
    "F_UNPAIRED_RETURN": [
        [],
        3,
        10
    ],
    "F_END_IN_SUB": [
        [
            101
        ],
        0,
        0
    ],
    "F_RETURN_AFTER_PRINTS": [
        [
            101,
            111,
            21
        ],
        0,
        0
    ],
    "F_GOTO_IN_SUB": [
        [
            121,
            21
        ],
        0,
        0
    ],
    "F_IF_TRUE_DISPATCH": [
        [
            101,
            61
        ],
        0,
        0
    ],
    "F_IF_FALSE_DISPATCH": [
        [
            101
        ],
        0,
        0
    ],
    "F_IF_INSIDE_SUB": [
        [
            121,
            31
        ],
        0,
        0
    ],
    "F_GOTO_AFTER_RETURN": [
        [
            101,
            41
        ],
        0,
        0
    ],
    "F_COLON_CONTINUATION": [
        [
            101,
            22
        ],
        0,
        0
    ],
    "F_UNPAIRED_AFTER_CALL": [
        [
            101
        ],
        3,
        20
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
    p = ROOT / "tests/oracles/inputs/j1_11_a" / (name.lower() + ".bas")
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

def flow_records(data, lines, records):
    found = []
    for idx, row in enumerate(lines.splitlines()):
        if re.search(rb"\b(?:GOSUB|RETURN)\b", row):
            rec = records[idx]
            binary = data[rec["offset"]:rec["offset"]+rec["length"]]
            require(binary[-1:] == b"\0" and
                    binary[:2] == len(binary).to_bytes(2, "little") and
                    int.from_bytes(binary[2:4], "little") == rec["line"],
                    "CPC_FLOW_LINE_HEADER_INVALID")
            found.append({"line_number":rec["line"],
                          "record_hex":binary.hex(" ").upper(),
                          "record_length":len(binary)})
    require(bool(found), "NO_GOSUB_OR_RETURN")
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
    require(len(parsed) >= 2 and all(row is not None for row in parsed),
            name+": ERR_ERL_PRINTER_MISSING_"+mode)
    values = [row["numeric_value"] for row in parsed]
    require(r["printer_raw_hex"] == printer.hex(" ").upper() and
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
    require(pre["flow_records"] == flow_records(raw, src, rows),
            name+": FLOW_RECORD_OR_CACHE_CHANGED_"+mode)
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
            cmp["classification"] == "UNSUPPORTED" and
            cmp["c99_size"] is None and cmp["c99_sha256"] is None and
            cmp["first_difference"] is None and
            "image-cli: input rejected:" in cmp["c99_rejection"],
            name+": PRE_NATIVE_CLASSIFICATION_CHANGED_"+mode)
    require(json.loads(read(folder/"comparison.json")) == cmp and
            (folder/"c99_error.txt").is_file() and
            not (folder/"c99.bin").exists(),
            name+": C99_REJECTION_EVIDENCE_MISSING_"+mode)
    for filename, meta in pre["files"].items():
        data = read(folder/filename)
        require({"sha256":sha(data),"size_bytes":len(data)} == meta,
                name+": PRE_FILE_DIGEST_CHANGED_"+mode+"/"+filename)
    return raw

def seal_for(base, m):
    return {
        "schema": 1, "phase":"J1.11-A-PROVISIONAL",
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
    require(m.get("phase") == "J1.11-A" and m.get("schema_version") == 1 and
            m.get("rom_archived") is False and
            m.get("full_snapshots_archived") is False and
            m.get("printer_is_screen_output") is False and
            m.get("j1_11_b_authorized") is False and
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
    require(len(captures) == len(MAIN_CASES) == 16 and
            [c["case"] for c in captures] == list(MAIN_CASES),
            "MISSING_OR_ADDED_CASES")
    require((base/"original").is_dir() and (base/"repeat").is_dir() and
            (base/"exploratory").is_dir() and
            not list((base/"exploratory").iterdir()),
            "ROOT_PROOF_LAYOUT_CHANGED")
    require({p.name for p in base.iterdir()} ==
            {"original","repeat","exploratory","manifest.json"} |
            ({"seal.json"} if (base/"seal.json").exists() else set()),
            "ROOT_FILES_CHANGED")
    for c in captures:
        name = c["case"]
        src, nums = source(name)
        require(c["source_path"] ==
                "tests/oracles/inputs/j1_11_a/"+name.lower()+".bas" and
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
    with tempfile.TemporaryDirectory(prefix="j111a-falsify-") as tmp:
        copy = Path(tmp)/"candidate"
        shutil.copytree(base,copy)
        name = MAIN_CASES[0]
        targets = (
            ("RAM",copy/"original"/name/"program.bin"),
            ("PRINTER",copy/"original"/name/"run/printer.dat"),
            ("LIST_PNG",copy/"original"/name/"list.png"),
            ("RUN_PNG",copy/"original"/name/"run/run.png"),
            ("SOURCE",copy/"original"/name/"original.bas"),
            ("COMPARISON",copy/"original"/name/"comparison.json"),
            ("RUN_COMMANDS",copy/"original"/name/"run/autocmd.json"),
            ("MANIFEST",copy/"manifest.json"),
            ("SEAL",copy/"seal.json"),
            ("REPEAT_RAM",copy/"repeat"/name/"program.bin"),
        )
        for label,path in targets:
            raw = read(path)
            require(len(raw) >= 3,label+": SHORT_FALSIFICATION_TARGET")
            corrupt = bytearray(raw)
            corrupt[2] ^= 1
            path.write_bytes(corrupt)
            try:
                verify(copy,permanent=True)
            except (Invalid,ValueError,UnicodeError,KeyError,TypeError):
                print("PASS J1.11-A FALSIFICATION_REJECTED",label,flush=True)
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
            print("PASS J1.11-A FALSE_HEAD_REJECTED",flush=True)
        else:
            raise Invalid("FALSE_HEAD_ACCEPTED")
        require(sha(read(base/"manifest.json")) == PINNED_MANIFEST_SHA,
                "CANONICAL_MANIFEST_CHANGED_BY_NEGATIVES")
    print("PASS J1.11-A 10 FALSIFICATIONS + FALSE HEAD",flush=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence",type=Path,default=BASE)
    p.add_argument("--write-provisional-seal",action="store_true")
    p.add_argument("--permanent",action="store_true")
    p.add_argument("--self-test",action="store_true")
    args = p.parse_args()
    base = args.evidence.resolve()
    if args.write_provisional_seal:
        require(not (base/"seal.json").exists(), "REFUSE_TO_RESEAL")
        m = verify(base)
        (base/"seal.json").write_text(json.dumps(seal_for(base,m),indent=2)+"\n")
    m = verify(base,args.permanent)
    print("PASS J1.11-A",len(m["captures"]),"CASES",
          "ORIGINAL+REPEAT", "PERMANENT="+str(args.permanent),flush=True)
    if args.self_test:
        require(args.permanent,"SELF_TEST_REQUIRES_PERMANENT")
        falsify(base)

if __name__ == "__main__":
    try:
        main()
    except (Invalid,ValueError,OSError,UnicodeError,KeyError,TypeError) as exc:
        print("J1.11-A VERIFY FAILED:",exc,file=sys.stderr)
        sys.exit(1)
