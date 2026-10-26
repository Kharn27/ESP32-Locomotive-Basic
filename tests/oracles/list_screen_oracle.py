#!/usr/bin/env python3
"""J0.24-C8: acquire genuine CPC6128 LIST SCREEN pixels (not printer bytes).

One freshly started Caprice32 process per unmodified historical program.
No RUN and no LIST #8. The PNG is a visual observation, never text bytes.
"""
import argparse
import configparser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from list_printer_oracle import (PIN, ROM_SHA, AMSDOS_SHA, ROOT, CASES as C7_CASES,
                                 digest, run, PNG)

CASES = {
    name: (path, source_sha, command.replace(",#8", ""))
    for name, (path, source_sha, command) in C7_CASES.items()
}
EXPECTED_FILES = ("source.bas", "autocmd.json", "cap32.cfg", "caprice.log",
                  "native.stdin.bin", "native.stdout.bin", "native.stderr.bin",
                  "screen.png")
CAPTURE_MACRO = "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"


def commands_for(source, list_cmd):
    lines = source.decode("ascii").splitlines()
    if not lines or not all(re.fullmatch(r"[1-9][0-9]* .+", s) for s in lines):
        raise ValueError("historical source is not numbered BASIC")
    return lines + ["CLS", list_cmd, CAPTURE_MACRO]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caprice", required=True, type=Path)
    parser.add_argument("--native-cli", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cap, cli, out = (args.caprice.resolve(), args.native_cli.resolve(),
                     args.output.resolve())
    if out.exists():
        raise ValueError("refuse to overwrite earlier screen acquisition")
    if not cli.is_file():
        raise ValueError("C99 CLI missing")
    rev = run(["git", "-C", str(cap), "rev-parse", "HEAD"], timeout=10)
    if rev.returncode or rev.stdout.decode().strip() != PIN:
        raise ValueError("unapproved Caprice32 commit")
    exe = cap / "cap32"
    ver = run([str(exe), "--version"], cwd=cap, timeout=10)
    if ver.returncode or b"4.6.0" not in ver.stdout:
        raise ValueError("unapproved Caprice32 version")
    rom = cap / "rom/cpc6128.rom"
    amsdos = cap / "rom/amsdos.rom"
    if (not rom.is_file() or len(rom.read_bytes()) != 32768 or
            digest(rom.read_bytes()) != ROM_SHA or not amsdos.is_file() or
            digest(amsdos.read_bytes()) != AMSDOS_SHA):
        raise ValueError("CPC 6128 ROM or AMSDOS mismatch")
    out.mkdir(parents=True)
    manifest = {
        "schema_version": 1, "phase": "J0.24-C8",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "github_sha": os.getenv("GITHUB_SHA"),
        "oracle": {
            "name": "Caprice32", "commit": PIN,
            "version_output": ver.stdout.decode(errors="replace").strip(),
            "model": "CPC6128", "ram_kb": 128, "basic": "1.1",
            "rom_sha256": ROM_SHA, "amsdos_sha256": AMSDOS_SHA,
            "rom_archived": False, "snapshot_archived": False,
        },
        "screen_text_bytes_extracted": False,
        "screen_printer_equivalence": False,
        "captures": [],
    }
    for case, (path, source_sha, list_cmd) in CASES.items():
        source = (ROOT / path).read_bytes()
        if digest(source) != source_sha or b"\r" in source or not source.endswith(b"\n"):
            raise ValueError(case + ": historical source changed")
        commands = commands_for(source, list_cmd)
        work = out / case
        work.mkdir()
        (work / "source.bas").write_bytes(source)
        (work / "autocmd.json").write_text(json.dumps({
            "source_path": path, "source_sha256": source_sha,
            "commands": commands, "new_cpc_process": True,
            "direct_cls_before_list": True,
            "list_to_screen_only": True, "run_executed": False,
            "screen_text_bytes_extracted": False
        }, indent=2) + "\n", encoding="utf-8")
        cfg = configparser.ConfigParser(interpolation=None)
        if not cfg.read(cap / "cap32.cfg"):
            raise ValueError("baseline Caprice32 config missing")
        cfg["system"].update(model="2", ram_size="128", speed="4", auto_pause="0",
                             printer="0", mf2="0", keyboard="0", boot_time="42",
                             limit_speed="0")
        cfg["control"]["kbd_layout"] = "0"
        cfg["sound"]["enabled"] = "0"
        cfg["video"].update(scr_style="1", scr_window="1")
        # No printer device is used. Reserve its path only to detect mistakes.
        cfg["file"]["printer_file"] = str(work / "unexpected-printer.dat")
        cfg["file"]["sdump_dir"] = str(work)
        cfg["rom"]["rom_path"] = str(cap / "rom")
        cfg["rom"]["slot07"] = "amsdos.rom"
        cfg["rom"]["rom_mf2"] = ""
        cfg["system"]["resources_path"] = str(cap / "resources")
        with (work / "cap32.cfg").open("w", encoding="utf-8") as fd:
            cfg.write(fd, space_around_delimiters=False)
        cmd = ["xvfb-run", "-a", str(exe), "-c", str(work / "cap32.cfg")]
        for part in commands:
            cmd.extend(["-a", part])
        env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
        cpc = run(cmd, cwd=cap, env=env, timeout=100)
        log = (b"$ cap32 -c <case-config> -a <historical lines> -a CLS "
               b"-a <direct LIST screen range> -a <screenshot+exit>\n")
        log += b"exit code: " + str(cpc.returncode).encode() + b"\n"
        log += cpc.stdout + b"\n[stderr]\n" + cpc.stderr
        (work / "caprice.log").write_bytes(log)
        images = sorted(work.glob("screenshot_*.png"))
        if cpc.returncode or len(images) != 1:
            raise ValueError(case + ": CPC failed or exactly one screenshot not acquired")
        raw = images[0].read_bytes()
        if len(raw) <= 1024 or not raw.startswith(PNG):
            raise ValueError(case + ": PNG screenshot not valid")
        original_name = images[0].name
        images[0].rename(work / "screen.png")
        prn = work / "unexpected-printer.dat"
        if prn.is_file() and prn.stat().st_size:
            raise ValueError(case + ": unexpected printer output")
        prn.unlink(missing_ok=True)
        native_in = source + b"LIST\n:quit\n"
        (work / "native.stdin.bin").write_bytes(native_in)
        native = run([str(cli)], input=native_in, timeout=15)
        (work / "native.stdout.bin").write_bytes(native.stdout)
        (work / "native.stderr.bin").write_bytes(native.stderr)
        if native.returncode or b"[cli:error]" in native.stderr or not native.stdout:
            raise ValueError(case + ": native C99 LIST unavailable")
        c = {
            "case": case, "source_path": path, "source_sha256": source_sha,
            "commands": commands, "original_screen_name": original_name,
            "operation": "LIST_SCREEN_VISUAL",
            "list_command_cpc": list_cmd, "list_command_native": "LIST",
            "selection_scope": "all historical lines match requested CPC range",
            "classification": "VISUAL_OBSERVATION",
            "visual_review_status": "PENDING_MANUAL_INSPECTION",
            "visual_review": None,
            "byte_exactness_claimed": False,
            "cpc_returncode": cpc.returncode,
            "native_returncode": native.returncode,
            "cpc_channel": "screen.png: original CPC DISPLAY PIXELS (no RUN, no printer)",
            "printer_channel": "not acquired (disabled, no LIST #8)",
            "native_channel": "native.stdout.bin: original C99 CLI LIST bytes",
            "files": {}
        }
        for fname in EXPECTED_FILES:
            file = work / fname
            c["files"][fname] = {"sha256": digest(file.read_bytes()),
                                  "size_bytes": file.stat().st_size}
        manifest["captures"].append(c)
        print(f"{case}: CPC SCREEN PNG sha256={c['files']['screen.png']['sha256']} "
              f"C99={len(native.stdout)} bytes; VISUAL_OBSERVATION only", flush=True)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print("C8 COMPLETE: two independent CPC screenshots; no extracted screen text "
          "bytes, no equivalence claim", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"C8 SCREEN ACQUISITION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
