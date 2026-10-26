#!/usr/bin/env python3
"""J0.27-A: fresh CPC6128 integer PRINT screen/printer acquisitions.

A screen screenshot is pixels, never inferred printer or screen text bytes.
Program PRINT #8 happens *during* RUN, unlike the archived C6 direct probe.
No ROM, full RAM, or snapshot is archived.
"""
import argparse
import configparser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from run_behavior_oracle import PIN, ROM_SHA, ROOT, CASES, digest, run

AMSDOS_SHA = "ea65e0fb44ee93ede4b6c507509b7e5ddf497fb7155023bea91ef229469fa04d"
CAPTURE = "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"
PNG = b"\x89PNG\r\n\x1a\n"
# Separate CPC processes and independent source files for all four observations.
MODES = ("screen", "printer")
FILES = {
    "screen": ("source.bas", "autocmd.json", "cap32.cfg", "command_argv.json",
               "caprice.log", "screen.png", "native.stdin.bin",
               "native.stdout.bin", "native.stderr.bin"),
    "printer": ("source.bas", "autocmd.json", "cap32.cfg", "command_argv.json",
                "caprice.log", "screen.png", "printer.dat"),
}


def instrument(original):
    if original.count(b"30 PRINT B%\n") != 1:
        raise ValueError("original line 30 not uniquely identified")
    return original.replace(b"30 PRINT B%\n", b"30 PRINT #8,B%\n")


def commands_for(source):
    lines = source.decode("ascii").splitlines()
    if len(lines) != 4 or not all(re.fullmatch(r"[1-9][0-9]* .+", line)
                                      for line in lines):
        raise ValueError("unexpected BASIC source syntax")
    return lines + ["RUN", CAPTURE]


def save(path, content):
    path.write_bytes(content)


def acquire(cap, exe, native_cli, output, case, path, expected_sha, expected):
    original = (ROOT / path).read_bytes()
    if digest(original) != expected_sha or b"\r" in original or not original.endswith(b"\n"):
        raise ValueError(case + ": original historical source changed")
    records = []
    for mode in MODES:
        id_ = case + "_" + mode
        work = output / id_
        work.mkdir(exist_ok=False)
        source = original if mode == "screen" else instrument(original)
        save(work / "source.bas", source)
        commands = commands_for(source)
        trace = {
            "case": case, "channel": mode, "new_cpc_process": True,
            "programmed_print": True, "run_executed": True,
            "direct_probe_after_run": False, "commands": commands,
            "source_sha256": digest(source), "original_source_sha256": expected_sha,
        }
        save(work / "autocmd.json", (json.dumps(trace, indent=2) + "\n").encode())
        cfg = configparser.ConfigParser(interpolation=None)
        if not cfg.read(cap / "cap32.cfg"):
            raise ValueError("missing baseline Caprice32 config")
        cfg["system"].update(model="2", ram_size="128", speed="4", auto_pause="0",
                             printer="1" if mode == "printer" else "0", mf2="0",
                             keyboard="0", boot_time="42", limit_speed="0")
        cfg["control"]["kbd_layout"] = "0"
        cfg["sound"]["enabled"] = "0"
        cfg["video"].update(scr_style="1", scr_window="1")
        cfg["file"]["printer_file"] = str(work / ("printer.dat" if mode == "printer"
                                                   else "unexpected-printer.dat"))
        cfg["file"]["sdump_dir"] = str(work)
        cfg["rom"]["rom_path"] = str(cap / "rom")
        cfg["rom"]["slot07"] = "amsdos.rom"
        cfg["rom"]["rom_mf2"] = ""
        cfg["system"]["resources_path"] = str(cap / "resources")
        with (work / "cap32.cfg").open("w", encoding="utf-8") as out:
            cfg.write(out, space_around_delimiters=False)
        argv = ["xvfb-run", "-a", str(exe), "-c", str(work / "cap32.cfg")]
        for command in commands:
            argv += ["-a", command]
        save(work / "command_argv.json",
             (json.dumps(argv, indent=2) + "\n").encode())
        env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
        result = run(argv, cwd=cap, env=env, timeout=100)
        log = ("$ " + shlex.join(argv) + "\nexit code: " +
               str(result.returncode) + "\n").encode() + result.stdout + b"\n[stderr]\n" + result.stderr
        images = sorted(work.glob("screenshot_*.png"))
        if result.returncode != 0 or len(images) != 1:
            raise ValueError(id_ + ": Caprice32 failed or screenshot absent")
        save(work / "caprice.log", log)
        original_screen_name = images[0].name
        if len(images[0].read_bytes()) < 1024 or not images[0].read_bytes().startswith(PNG):
            raise ValueError(id_ + ": invalid original PNG")
        images[0].rename(work / "screen.png")
        if mode == "screen":
            unexpected = work / "unexpected-printer.dat"
            if unexpected.exists() and unexpected.stat().st_size:
                raise ValueError(id_ + ": printer bytes in screen-only acquisition")
            unexpected.unlink(missing_ok=True)
            stdin = original + b"RUN\n:step 100\n:quit\n"
            native = run([str(native_cli)], input=stdin, timeout=15)
            save(work / "native.stdin.bin", stdin)
            save(work / "native.stdout.bin", native.stdout)
            save(work / "native.stderr.bin", native.stderr)
            if native.returncode or b"[cli:error]" in native.stderr:
                raise ValueError(id_ + ": native CLI cannot execute original C/D")
            native_rc = native.returncode
        else:
            if not (work / "printer.dat").is_file() or not (work / "printer.dat").stat().st_size:
                raise ValueError(id_ + ": programmed printer channel absent or empty")
            native_rc = None
        files = {name: {"sha256": digest((work / name).read_bytes()),
                        "size_bytes": (work / name).stat().st_size}
                 for name in FILES[mode]}
        records.append({
            "id": id_, "case": case, "mode": mode,
            "source_path": path, "original_source_sha256": expected_sha,
            "source_sha256": digest(source), "numeric_hypothesis": expected,
            "commands": commands, "original_screen_name": original_screen_name,
            "cpc_returncode": result.returncode, "native_returncode": native_rc,
            "screen_classification": "VISUAL_OBSERVATION",
            "screen_bytes_extracted": False, "printer_screen_equivalent": False,
            "printer_channel": "programmed PRINT #8 during RUN" if mode == "printer"
                               else "disabled; no printer output",
            "native_channel": "C99 stdout during RUN" if mode == "screen"
                              else "not executed in printer session",
            "files": files,
        })
        print(id_, "screenshot sha256=", files["screen.png"]["sha256"], flush=True)
        if mode == "printer":
            print(id_, "printer HEX=", (work / "printer.dat").read_bytes().hex(" ").upper(), flush=True)
        else:
            print(id_, "native HEX=", (work / "native.stdout.bin").read_bytes().hex(" ").upper(), flush=True)
    return records


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--caprice", type=Path, required=True)
    p.add_argument("--native-cli", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    cap, cli, output = args.caprice.resolve(), args.native_cli.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError("output already exists; refusing stale acquisitions")
    if not cli.is_file():
        raise ValueError("missing C99 CLI")
    git = run(["git", "-C", str(cap), "rev-parse", "HEAD"], timeout=10)
    if git.returncode or git.stdout.decode().strip() != PIN:
        raise ValueError("Caprice32 revision not pinned")
    exe = cap / "cap32"
    ver = run([str(exe), "--version"], cwd=cap, timeout=10)
    if ver.returncode or b"4.6.0" not in ver.stdout:
        raise ValueError("Caprice32 version unapproved")
    rom = cap / "rom/cpc6128.rom"
    amsdos = cap / "rom/amsdos.rom"
    if not rom.is_file() or len(rom.read_bytes()) != 32768 or digest(rom.read_bytes()) != ROM_SHA:
        raise ValueError("wrong/missing CPC BASIC ROM")
    if not amsdos.is_file() or digest(amsdos.read_bytes()) != AMSDOS_SHA:
        raise ValueError("wrong/missing AMSDOS ROM")
    output.mkdir(parents=True)
    manifest = {
        "schema_version": 1, "phase": "J0.27-A",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_run_id": os.getenv("GITHUB_RUN_ID"), "github_sha": os.getenv("GITHUB_SHA"),
        "oracle": {"name": "Caprice32", "commit": PIN, "version_output":
                   ver.stdout.decode(errors="replace").strip(), "model": "CPC6128",
                   "ram_kb": 128, "basic": "1.1", "rom_sha256": ROM_SHA,
                   "amsdos_sha256": AMSDOS_SHA, "rom_archived": False,
                   "snapshot_archived": False},
        "screen_bytes_extracted": False, "printer_screen_equivalent": False,
        "captures": [],
    }
    for case, (path, hash_, expected) in CASES.items():
        manifest["captures"].extend(acquire(cap, exe, cli, output, case, path, hash_, expected))
    save(output / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    print("J0.27-A four independent CPC boot sessions acquired; no byte-exact screen claim", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print("J0.27-A acquisition FAILED:", exc, file=sys.stderr)
        sys.exit(1)
