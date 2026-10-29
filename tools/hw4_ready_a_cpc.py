#!/usr/bin/env python3
"""HW4-READY-A / A0: capture authentic CPC6128 BASIC 1.1 screen transitions.

This script NEVER labels a Ready transition as observed from a ROM listing,
a printer file, a native emulator or a synthetic screen.
"""
import argparse
import configparser
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

PIN = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
ROM_SHA = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
CONTAINER = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
             "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")
# All inputs are ordinary CPC keyboard commands except the *empty* command,
# which is the bare Enter. Each case starts from a fresh original CPC boot.
CASES = {
    "00_boot": [],
    "01_numbered_10": ["10 PRINT 2"],
    "02_numbered_20": ["10 PRINT 2", "20 END"],
    "03_empty_enter": ["10 PRINT 2", "20 END", ""],
    "04_list": ["10 PRINT 2", "20 END", "LIST"],
    "05_new": ["10 PRINT 2", "20 END", "NEW"],
    "06_run_normal": ["10 PRINT 2", "20 END", "RUN"],
    "07_stop": ["10 PRINT 2", "20 STOP", "RUN"],
    "08_error": ["10 PRINT 2", "20 END", "GOTO 999"],
    "09_run_new": ["10 PRINT 2", "20 END", "RUN", "NEW"],
}
CPC_TAIL = "CAP32_DELAYCAP32_DELAYCAP32_SCRNSHOTCAP32_EXIT"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def expected_argv(cap, cfg, commands):
    argv = ["xvfb-run", "-a", str(cap / "cap32"), "-c", str(cfg)]
    for command in [*commands, CPC_TAIL]:
        argv.extend(["-a", command])
    return argv

def self_test():
    require(len(CASES) == 10 and len(set(CASES)) == len(CASES), "CASE_COUNT")
    for name, commands in CASES.items():
        require(re.fullmatch(r"[0-9]{2}_[a-z0-9_]+", name) is not None, "CASE_NAME")
        require(all("\n" not in cmd and "\r" not in cmd for cmd in commands),
                "INVALID_KEYBOARD_INPUT")
        argv = expected_argv(Path("/cap"), Path("/cap/cap32.cfg"), commands)
        require(argv[-2:] == ["-a", CPC_TAIL] and " " not in CPC_TAIL,
                "SCREENSHOT_TAIL_MUST_NOT_TYPE_HOST_SPACES")
        if name == "03_empty_enter":
            require("" in commands and argv.count("") == 1, "BARE_ENTER_MISSING")
    print("HW4-READY-A A0 SELF_TEST PASS cases=10 fresh_process_pairs=10 "
          "no_Ready_inferences=1")

def run_one(cap, out, name, commands):
    out.mkdir(parents=True, exist_ok=False)
    cfg = configparser.ConfigParser(interpolation=None)
    require(bool(cfg.read(cap / "cap32.cfg")), "CAP32_CONFIG_MISSING")
    cfg["system"].update(model="2", ram_size="128", speed="4",
                         auto_pause="0", printer="0", mf2="0",
                         keyboard="0", boot_time="42", limit_speed="0")
    cfg["control"]["kbd_layout"] = "0"
    cfg["sound"]["enabled"] = "0"
    cfg["video"].update(scr_style="1", scr_window="1")
    cfg["file"]["sdump_dir"] = str(out)
    cfg["rom"]["rom_path"] = str(cap / "rom")
    cfg["rom"]["slot07"] = "amsdos.rom"
    cfg["rom"]["rom_mf2"] = ""
    cfg["system"]["resources_path"] = str(cap / "resources")
    conf = out / "cap32.cfg"
    with conf.open("w", encoding="utf-8") as stream:
        cfg.write(stream, space_around_delimiters=False)
    argv = expected_argv(cap, conf, commands)
    (out / "autocmd.json").write_text(json.dumps({
        "case": name, "keyboard_inputs": commands,
        "bare_enter": name == "03_empty_enter",
        "tail": CPC_TAIL, "argv": argv, "screen_not_printer": True
    }, indent=2) + "\n", encoding="utf-8")
    env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
    started = datetime.now(timezone.utc).isoformat()
    p = subprocess.run(argv, cwd=cap, env=env, capture_output=True,
                       timeout=60, check=False)
    finished = datetime.now(timezone.utc).isoformat()
    (out / "caprice.log").write_bytes(
        ("returncode=" + str(p.returncode) + "\n").encode() +
        p.stdout + b"\n[stderr]\n" + p.stderr)
    pictures = sorted(out.glob("screenshot_*.png"))
    require(p.returncode == 0 and len(pictures) == 1,
            name + ": BAD_CPC_PROCESS_OR_SCREENSHOT " +
            str(p.returncode) + " count=" + str(len(pictures)))
    screenshot = out / "screen.png"
    pictures[0].rename(screenshot)
    raw = screenshot.read_bytes()
    require(len(raw) > 1024 and raw[:8] == b"\x89PNG\r\n\x1a\n",
            name + ": BAD_PNG")
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    require(width >= 320 and height >= 200, name + ": IMAGE_SIZE")
    return {
        "started_utc": started, "finished_utc": finished,
        "emulator_exit_code": p.returncode,
        "screen_png": str(screenshot.relative_to(out.parent.parent)),
        "screen_sha256": sha(raw), "screen_size_bytes": len(raw),
        "screen_width_px": width, "screen_height_px": height,
        "keyboard_sequence_sha256": sha(json.dumps(commands).encode()),
        "screen_reading_status": "TO_REVIEW", "ready_count": None,
        "cursor_position": None, "independent_cpc_process": True
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--caprice", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    self_test()
    if args.self_test:
        return
    require(args.caprice is not None and args.output is not None,
            "CAPRICE_AND_OUTPUT_REQUIRED")
    cap = args.caprice.resolve()
    out = args.output.resolve()
    require(not out.exists(), "REFUSE_REUSE_EVIDENCE_DIR")
    root = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                   text=True).strip()
    require(re.fullmatch(r"[a-f0-9]{40}", head) is not None and
            head == os.environ.get("GITHUB_HEAD_SHA"), "FALSE_CHECKOUT")
    emu = subprocess.check_output(
        ["git", "-C", str(cap), "rev-parse", "HEAD"], text=True).strip()
    require(emu == PIN, "CAPRICE_COMMIT_MISMATCH")
    require(sha((cap / "rom/cpc6128.rom").read_bytes()) == ROM_SHA,
            "CPC_ROM_MISMATCH")
    require((cap / "rom/amsdos.rom").is_file(), "AMSDOS_ROM_ABSENT")
    require((cap / "cap32").is_file(), "CAPRICE_BINARY_ABSENT")
    version = subprocess.check_output([str(cap / "cap32"), "--version"],
                                      cwd=cap, text=True).strip()
    out.mkdir(parents=True)
    manifest = {
        "schema": 1, "mission": "HW4-READY-A", "phase": "A0",
        "repo_head": head, "run_id": os.environ.get("GITHUB_RUN_ID"),
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "oracle": {"emulator": "Caprice32", "commit": PIN, "version": version,
                   "rom_sha256": ROM_SHA, "model": "CPC6128",
                   "rom": "CPC6128 BASIC 1.1", "ram_kib": 128,
                   "container": CONTAINER},
        "capture_purpose": "VISUAL_INSPECTION_REQUIRED",
        "screen_is_not_printer": True, "rom_archived": False,
        "original_archives_untouched": True, "cases": []
    }
    for name, commands in CASES.items():
        item = {"id": name, "keyboard": commands, "runs": []}
        for repetition in ("original", "repeat"):
            folder = out / repetition / name
            result = run_one(cap, folder, name, commands)
            item["runs"].append({"repetition": repetition, **result})
        manifest["cases"].append(item)
        print("HW4-READY-A A0 CAPTURE", name,
              *(r["screen_sha256"] for r in item["runs"]), flush=True)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8")
    print("HW4-READY-A A0 20 ROM-backed screenshots; "
          "no Ready conclusion before visual inspection; HEAD=" + head)

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError,
            configparser.Error) as error:
        print("HW4-READY-A A0 FAILED:", error, file=sys.stderr)
        sys.exit(1)
