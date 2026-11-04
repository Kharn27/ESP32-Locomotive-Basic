#!/usr/bin/env python3
"""#298: collect ORIGINAL Caprice32 CPC6128 direct-input screenshots only.

Imports the prior independent CPC acquisition driver, NEVER the native C99
BASIC implementation. A clean CPC process/boot per word and repetition.
An image is a candidate, NOT a historical interpretation until inspected.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from hw4_diag_a_cpc import PIN, ROM_SHA, CONTAINER, run_one

CASES = (("01_listt_direct", "LISTT"), ("02_runn_direct", "RUNN"))
REPETITIONS = ("original", "repeat")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(ok, code):
    if not ok:
        raise ValueError(code)


def self_test():
    require(len(CASES) == 2 and len({w for _, w in CASES}) == 2, "TWO_DISTINCT_DIRECT_COMMANDS_REQUIRED")
    require([w for _, w in CASES] == ["LISTT", "RUNN"], "FIXED_CPC_INPUT_MATRIX")
    require(len(REPETITIONS) == 2 and len(set(REPETITIONS)) == 2, "TWO_SESSIONS_PER_WORD")
    require(all(re.fullmatch(r"[A-Z]{4,8}", w) for _, w in CASES), "BARE_DIRECT_ASCII_INPUTS")
    print("HW4-DIAG-ORACLE-R1 SELF_TEST PASS 2 words x 2 fresh CPC sessions")


def acquire(args):
    self_test()
    require(args.caprice is not None and args.output is not None,
            "CAPRICE_AND_OUTPUT_REQUIRED")
    root = Path(__file__).resolve().parents[1]
    cap = args.caprice.resolve()
    out = args.output.resolve()
    require(not out.exists(), "REFUSE_EXISTING_OUTPUT_OR_SEALED_FIXTURES")
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    required_head = os.getenv("GITHUB_HEAD_SHA") or args.expected_head
    require(re.fullmatch("[0-9a-f]{40}", head) is not None and head == required_head,
            "CHECKOUT_SHA_NOT_ATTESTED")
    emu = subprocess.check_output(["git", "-C", str(cap), "rev-parse", "HEAD"], text=True).strip()
    require(emu == PIN, "UNPINNED_CPC_EMULATOR")
    rom = cap / "rom/cpc6128.rom"
    require(rom.is_file() and len(rom.read_bytes()) == 32768 and
            sha(rom.read_bytes()) == ROM_SHA, "CPC6128_ROM_PIN_FAILURE")
    require((cap / "rom/amsdos.rom").is_file(), "AMSDOS_ROM_ABSENT")
    require((cap / "cap32").is_file(), "CAPRICE32_BINARY_ABSENT")
    ver = subprocess.check_output([str(cap / "cap32"), "--version"],
                                  text=True, cwd=cap).strip()
    out.mkdir(parents=True)
    manifest = {
        "schema": 1, "mission": "HW4-DIAG-ORACLE-R1", "issue": 298,
        "repo_head": head, "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "acquired_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "CPC_SCREEN_CANDIDATE_NOT_YET_VISUALLY_REVIEWED",
        "oracle": {
            "name": "Caprice32", "commit": PIN, "version": ver,
            "system_rom_sha256": ROM_SHA, "model": "CPC6128",
            "basic_version": "BASIC 1.1 (to be checked on screenshots)",
            "ram_kib": 128, "keyboard": "English 0", "rom_archived": False,
            "container_image": CONTAINER,
            "acquisition_driver_sha256": sha((root / "tools/hw4_diag_a_cpc.py").read_bytes()),
            "mission_script_sha256": sha(Path(__file__).read_bytes()),
        },
        "c99_code_executed": False, "screen_not_printer": True,
        "diagnostic_interpretation": None, "ready_interpretation": None,
        "cases": [],
    }
    for name, word in CASES:
        entry = {"id": name, "direct_command": word,
                 "keyboard_inputs": [word], "runs": []}
        for rep in REPETITIONS:
            folder = out / rep / name
            record = run_one(cap, folder, name, [word])
            require(record["independent_cpc_process"] is True and
                    record["emulator_exit_code"] == 0 and
                    record["screen_reading_status"] == "TO_REVIEW", "FRESH_CPC_SESSION_FAILED")
            entry["runs"].append({"repetition": rep, **record})
            print("R1 CPC CANDIDATE", name, rep, record["screen_sha256"], flush=True)
        manifest["cases"].append(entry)
    manifest["artifact_hashes"] = {
        str(p.relative_to(out)): {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
        for p in sorted(out.rglob("*")) if p.is_file()
    }
    raw = (json.dumps(manifest, indent=2, ensure_ascii=True) + "\n").encode()
    (out / "manifest.json").write_bytes(raw)
    print("HW4_DIAG_ORACLE_R1_MANIFEST_SHA256=" + sha(raw))
    print("HW4_DIAG_ORACLE_R1_CAPTURED=4 CASES=2 DISTINCT_CPC_PROCESSES=4 "+
          "VERDICT=CANDIDATE_UNINSPECTED")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--caprice", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--expected-head", type=str, help="required for non-Actions reproduction")
    args = p.parse_args()
    if args.self_test:
        self_test()
    else:
        acquire(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("HW4-DIAG-ORACLE-R1 ACQUISITION FAILED:", exc, file=sys.stderr)
        sys.exit(1)
