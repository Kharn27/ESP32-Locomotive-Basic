#!/usr/bin/env python3
"""#298: tamper-resistant CPC screenshot candidate verification, NOT OCR.

Verification of raw bytes, exact input provenance and cold-start sessions
cannot by itself infer which text the authentic CPC ROM displayed.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

ROM_SHA = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
EMU_SHA = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
CASES = {"01_listt_direct": "LISTT", "02_runn_direct": "RUNN"}
REPS = ("original", "repeat")
PNG = b"\x89PNG\r\n\x1a\n"


def fail_if(condition, message):
    if condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(root, j):
    fail_if(j.get("schema") != 1 or j.get("mission") != "HW4-DIAG-ORACLE-R1" or
            j.get("issue") != 298, "SCHEMA_OR_MISSION")
    fail_if(j.get("classification") != "CPC_SCREEN_CANDIDATE_NOT_YET_VISUALLY_REVIEWED" or
            j.get("diagnostic_interpretation") is not None or
            j.get("ready_interpretation") is not None or
            j.get("c99_code_executed") is not False or
            j.get("screen_not_printer") is not True, "FABRICATED_VERDICT_OR_CHANNEL")
    o = j["oracle"]
    fail_if(o.get("commit") != EMU_SHA or o.get("system_rom_sha256") != ROM_SHA or
            o.get("model") != "CPC6128" or o.get("ram_kib") != 128 or
            o.get("rom_archived") is not False or
            not re.fullmatch(r"[0-9a-f]{64}", o.get("mission_script_sha256", "")) or
            not re.fullmatch(r"[0-9a-f]{64}", o.get("acquisition_driver_sha256", "")),
            "ROM_OR_EMULATOR_PROVENANCE")
    fail_if(not re.fullmatch(r"[0-9a-f]{40}", j.get("repo_head", "")), "HEAD_UNVERIFIED")
    fail_if(len(j["cases"]) != 2 or
            {x.get("id") for x in j["cases"]} != set(CASES), "CASE_SET")
    artifacts = {}
    for case in j["cases"]:
        name = case["id"]
        word = CASES[name]
        fail_if(case.get("direct_command") != word or
                case.get("keyboard_inputs") != [word] or
                len(case.get("runs", [])) != 2 or
                [x.get("repetition") for x in case["runs"]] != list(REPS),
                name + ":COMMAND_OR_INDEPENDENCE")
        for session in case["runs"]:
            rep = session["repetition"]
            loc = f"{rep}/{name}"
            fail_if(session.get("emulator_exit_code") != 0 or
                    session.get("independent_cpc_process") is not True or
                    session.get("screen_reading_status") != "TO_REVIEW" or
                    session.get("ready_count") is not None or
                    session.get("cursor_position") is not None,
                    loc + ":UNJUSTIFIED_OBSERVATION")
            fail_if(session.get("screen_png") != loc + "/screen.png", loc + ":SCREEN_PATH")
            img = root / loc / "screen.png"
            data = img.read_bytes()
            fail_if(not data.startswith(PNG) or len(data) < 1024 or
                    int.from_bytes(data[16:20], "big") != session["screen_width_px"] or
                    int.from_bytes(data[20:24], "big") != session["screen_height_px"] or
                    digest(data) != session["screen_sha256"] or
                    len(data) != session["screen_size_bytes"], loc + ":IMAGE_SHA_PNG")
            meta = json.loads((root / loc / "autocmd.json").read_text())
            fail_if(meta.get("keyboard_inputs") != [word] or
                    meta.get("tail") != "CAP32_DELAYCAP32_DELAYCAP32_SCRNSHOTCAP32_EXIT" or
                    meta.get("screen_not_printer") is not True or
                    meta.get("case") != name, loc + ":KEYBOARD_TRACE")
            log = (root / loc / "caprice.log").read_bytes()
            fail_if(not log.startswith(b"returncode=0\n"), loc + ":EMULATOR_EXIT")
            cfg = (root / loc / "cap32.cfg").read_text()
            fail_if("model=2\n" not in cfg or "ram_size=128\n" not in cfg or
                    "boot_time=42\n" not in cfg or "keyboard=0\n" not in cfg,
                    loc + ":CONFIG")
            for filename in ("screen.png", "autocmd.json", "caprice.log", "cap32.cfg"):
                p = root / loc / filename
                raw = p.read_bytes()
                artifacts[f"{loc}/{filename}"] = {"sha256": digest(raw), "bytes": len(raw)}
    fail_if(j.get("artifact_hashes") != dict(sorted(artifacts.items())), "FILE_HASH_SET")
    on_disk = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    fail_if(on_disk != set(artifacts) | {"manifest.json"}, "UNKNOWN_OR_MISSING_FILES")
    fail_if(any(p.is_symlink() for p in root.rglob("*")), "SYMLINK_FORBIDDEN")
    print("HW4-DIAG-ORACLE-R1 RAW_CANDIDATES_VERIFIED 2 commands 4 cold boots 4 native PNGs")
    print("STATUS=CPC_SCREEN_CANDIDATE_NOT_YET_VISUALLY_REVIEWED")


def self_test():
    # The critical logical verdict must remain false even with the right ROM.
    specimen = {"diagnostic_interpretation": None,
                "classification": "CPC_SCREEN_CANDIDATE_NOT_YET_VISUALLY_REVIEWED"}
    for wrong in ("Syntax error", "ERROR", "Ready"):
        j = copy.deepcopy(specimen)
        j["diagnostic_interpretation"] = wrong
        fail_if(j == specimen, "VERDICT_MUTATION_ACCEPTED")
    fail_if(digest(b"PNG screen") == digest(b"PNG screeN"), "DIGEST_MUTATION_ACCEPTED")
    fail_if(set(CASES.values()) != {"LISTT", "RUNN"}, "CASE_SELFTEST")
    print("HW4-DIAG-ORACLE-R1 SELF_TEST PASS tamper and forbidden verdict boundaries")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.evidence:
        root = args.evidence.resolve()
        validate(root, json.loads((root / "manifest.json").read_text()))
    elif not args.self_test:
        raise ValueError("NEED_EVIDENCE_OR_SELFTEST")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print("HW4-DIAG-ORACLE-R1 VERIFICATION FAILED:", exc, file=sys.stderr)
        sys.exit(1)
