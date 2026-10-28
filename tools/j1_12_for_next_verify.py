#!/usr/bin/env python3
"""J1.12-A: fail-closed verifier of independent CPC6128 FOR/NEXT captures.

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
from j1_12_for_next_oracle import MAIN_CASES, EXPLORATORY, GHCR_PIN, checkout_identity

BASE = ROOT / "tests/fixtures/cpc6128/j1_12_for_next"
# EXTERNAL FIRST-CAPTURE ANCHORS: absent until the original GHCR archive is
# produced by the GitHub bot. An empty value always fails permanent mode.
# Transcribed from independent GHCR original run 40615245342
# acquired at HEAD 9ef54a01f9b8c12eb11c559c3930cd3d37729a2a; seal remains PENDING_PILOTAGE.
# External anchors intentionally absent until real CPC archival.
PINNED_MANIFEST_SHA = "acc43227f6970ffa7ab04a135d04e49f09231f053606d8000fa313c06df42a1b"
PINNED_RAM = {
    "F_POS_IMPLICIT_ONE": "2a0721c05ddf8aba3f0e99f683fbb433fc8d959b81b999232be94dae0d776da6",
    "F_POS_IMPLICIT_THREE": "e6ba8ee63f6d84e6e08bf47cbb3e096ac45e5b6f9bc510556e48c3df9561707e",
    "F_POS_EXPLICIT_TWO": "bb7bccae8484c2436ac3e0947ea90c099d391c11c399344bb8cc18f01ad61f0c",
    "F_NEG_STEP_THREE": "19dc2c80dcbcf3b9b80113cece602a65588f2d9916a16e6670314128566340b9",
    "F_NEG_STEP_TWO": "1a1919c1912fe3c10241f1650e2c204e1b39a2c4045fb02cc18a7d9c6151df7e",
    "F_REVERSED_POS": "d5eaf951f19cc0c65ab236dd3bb4d4237551116934d7d19cbf02521fc086d53b",
    "F_REVERSED_NEG": "07778a26cd9a5bad884476169b22576a3ece191b90c5ba88713d34cb7d4d4545",
    "F_ZERO_BOUND": "ac27a159a3c4184e47888ea86a7bcf2ee2bccf4060d0a6cea8ff264a36831476",
    "F_NMIN_EQ": "8ec1e85e55674350241f3932765450c3768c2d57f7a5d7b2ead797d092fe6af6",
    "F_PMAX_NEAR": "d8b77c54ccf1dbd8e6f531d4ade5ad58f94dc5f03ed45d17b012f0e0c1bf720e",
    "F_NMIN_ASCEND": "809493e7a87c5ddea47aeea9de74b3e5fcb9a457c6a6f58dd93cf47ececb07ff",
    "F_PMAX_DESCEND": "61f6f6b341dba50ceba995f8754c93eaa0dbfab4517b4b84a4dd5e1751f4b252",
    "F_NEXT_BARE": "46fd71d58d4ea144b493a7c84315dd9d9eabaf8ee98202c0305fdb296f99baeb",
    "F_NEXT_NAMED": "29614feb152a17b8647269454d631ba6c83a85755ba354719f6a7906d5169cce",
    "F_NESTED2": "0eb65e9f165c6f603aa5a03b178dab515eacf23d33d2adf0053e12fca727255c",
    "F_REPEAT": "ee03ccb56a00000e093a0ff34f804fd4e2fa48eab01fdc3510f0319086be616e",
    "F_GOTO_EXIT": "8dcc9659c375aee0d618635dff6669b88d66d7d266667c0bd5db281c93d38ebd",
    "F_END_EARLY": "792edcc282547d0f0f702417040ee842dd6a5c23b7a807aafa7d71ac45c68fb6",
    "F_NEXT_ORPHAN": "e0f24541a1027ff200e5fb2bf267787921e7976f9e46258f3d402d9478c1270b",
    "F_NEXT_WRONG_VAR": "457d4e362a29d3ccc62d895734c50cf6068b6984e494841477e802450d8bf5c9"
}
PINNED_PRINTER = {
    "F_POS_IMPLICIT_ONE": "7d86a31a45b2e1f6cbaec323f0cc3c6c42fcc8efe0c7320de54b401f44cbee1b",
    "F_POS_IMPLICIT_THREE": "6bef7868253a610c6affd6bbf3a2016a07b6617edd0b9323a9e5fb80dd362a22",
    "F_POS_EXPLICIT_TWO": "c45c7ee6c98eb62a42d0e61e43bad0b48c3e69f58d19ebefcf87ba37cf950a42",
    "F_NEG_STEP_THREE": "d2a49a9698f66dfcb0279f244481a5f4f74d00ba4550acff6496fc5218db6075",
    "F_NEG_STEP_TWO": "1143636902e0417f19101ff9b27d84b5fdc57020cf82cb1cc793ac5b24c4f626",
    "F_REVERSED_POS": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "F_REVERSED_NEG": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
    "F_ZERO_BOUND": "599e8a6c46a024ba4d2882b33a7f9a631c06fb4bc994129c6a1603f839b2da66",
    "F_NMIN_EQ": "3e8f0cd7fcbf769487797f0319a2d1bc56759f7380f0117c12cdcb22ab84ae56",
    "F_PMAX_NEAR": "944af74414daf372179c556e83bd21522e8409db0d1e0ed1f7b5788e2f1d5275",
    "F_NMIN_ASCEND": "edc4b621af6a04373f2cc5f895f86873e3b79aceef78818a4247451f72330379",
    "F_PMAX_DESCEND": "86895ada931bcf9594adc5ebf0585dc76a6775cf16f75ed494bffc50befd3d5e",
    "F_NEXT_BARE": "8b7ae42f59c89f4ca6d46bab5ffcf7458f879e185def62172bf9fd9de12c887c",
    "F_NEXT_NAMED": "8b7ae42f59c89f4ca6d46bab5ffcf7458f879e185def62172bf9fd9de12c887c",
    "F_NESTED2": "76b04e6d4f7a1f4abbae29c39ff6a557858ac5e561adecb508c70f5ad032f4cd",
    "F_REPEAT": "625e94d38cc2eafd248257b3f30cf37408a7556942f4bba4733cc40f885e55f8",
    "F_GOTO_EXIT": "5e4efb79ac02644dbc815633846e8d3ebdb8ee12227085859ed87595e1f79515",
    "F_END_EARLY": "7d86a31a45b2e1f6cbaec323f0cc3c6c42fcc8efe0c7320de54b401f44cbee1b",
    "F_NEXT_ORPHAN": "ea61f6d4a642d22fa4e825d8e6d8979ba3d5fbde47f951090e18d3fc6e1972ba",
    "F_NEXT_WRONG_VAR": "2bc5b4aa31243696d97a91989d9f187babb7662f5e40759666c1291aa3276f12"
}
PINNED_OUTCOMES = {
    "F_POS_IMPLICIT_ONE": [
        [
            1
        ],
        0,
        0
    ],
    "F_POS_IMPLICIT_THREE": [
        [
            1,
            2,
            3
        ],
        0,
        0
    ],
    "F_POS_EXPLICIT_TWO": [
        [
            1,
            3,
            5
        ],
        0,
        0
    ],
    "F_NEG_STEP_THREE": [
        [
            3,
            2,
            1
        ],
        0,
        0
    ],
    "F_NEG_STEP_TWO": [
        [
            6,
            4,
            2
        ],
        0,
        0
    ],
    "F_REVERSED_POS": [
        [],
        0,
        0
    ],
    "F_REVERSED_NEG": [
        [],
        0,
        0
    ],
    "F_ZERO_BOUND": [
        [
            0
        ],
        0,
        0
    ],
    "F_NMIN_EQ": [
        [
            -32768
        ],
        0,
        0
    ],
    "F_PMAX_NEAR": [
        [
            32766
        ],
        0,
        0
    ],
    "F_NMIN_ASCEND": [
        [
            -32768,
            -32767,
            -32766
        ],
        0,
        0
    ],
    "F_PMAX_DESCEND": [
        [
            32767,
            32766,
            32765
        ],
        0,
        0
    ],
    "F_NEXT_BARE": [
        [
            1,
            2
        ],
        0,
        0
    ],
    "F_NEXT_NAMED": [
        [
            1,
            2
        ],
        0,
        0
    ],
    "F_NESTED2": [
        [
            1,
            3,
            1,
            4,
            2,
            3,
            2,
            4
        ],
        0,
        0
    ],
    "F_REPEAT": [
        [
            1,
            2,
            4,
            5
        ],
        0,
        0
    ],
    "F_GOTO_EXIT": [
        [
            1,
            99
        ],
        0,
        0
    ],
    "F_END_EARLY": [
        [
            1
        ],
        0,
        0
    ],
    "F_NEXT_ORPHAN": [
        [
            77
        ],
        1,
        20
    ],
    "F_NEXT_WRONG_VAR": [
        [],
        1,
        30
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
    p = ROOT / "tests/oracles/inputs/j1_12_a" / (name.lower() + ".bas")
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
        if re.search(rb"\b(?:FOR|NEXT|TO|STEP)\b", row):
            rec = records[idx]
            binary = data[rec["offset"]:rec["offset"]+rec["length"]]
            require(binary[-1:] == b"\0" and
                    binary[:2] == len(binary).to_bytes(2, "little") and
                    int.from_bytes(binary[2:4], "little") == rec["line"],
                    "CPC_FLOW_LINE_HEADER_INVALID")
            found.append({"line_number":rec["line"],
                          "record_hex":binary.hex(" ").upper(),
                          "record_length":len(binary)})
    require(bool(found), "NO_FOR_OR_NEXT")
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
        "schema": 1, "phase":"J1.12-A-PROVISIONAL",
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
    require(m.get("phase") == "J1.12-A" and m.get("schema_version") == 1 and
            m.get("rom_archived") is False and
            m.get("full_snapshots_archived") is False and
            m.get("printer_is_screen_output") is False and
            m.get("j1_12_b_authorized") is False and
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
    require(len(captures) == len(MAIN_CASES) == 20 and
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
                "tests/oracles/inputs/j1_12_a/"+name.lower()+".bas" and
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
    with tempfile.TemporaryDirectory(prefix="j112a-falsify-") as tmp:
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
                print("PASS J1.12-A FALSIFICATION_REJECTED",label,flush=True)
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
            print("PASS J1.12-A FALSE_HEAD_REJECTED",flush=True)
        else:
            raise Invalid("FALSE_HEAD_ACCEPTED")
        require(sha(read(base/"manifest.json")) == PINNED_MANIFEST_SHA,
                "CANONICAL_MANIFEST_CHANGED_BY_NEGATIVES")
    print("PASS J1.12-A 10 FALSIFICATIONS + FALSE HEAD",flush=True)

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
    print("PASS J1.12-A",len(m["captures"]),"CASES",
          "ORIGINAL+REPEAT", "PERMANENT="+str(args.permanent),flush=True)
    if args.self_test:
        require(args.permanent,"SELF_TEST_REQUIRES_PERMANENT")
        falsify(base)

if __name__ == "__main__":
    try:
        main()
    except (Invalid,ValueError,OSError,UnicodeError,KeyError,TypeError) as exc:
        print("J1.12-A VERIFY FAILED:",exc,file=sys.stderr)
        sys.exit(1)
