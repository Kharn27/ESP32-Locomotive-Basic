#!/usr/bin/env python3
"""HW4-C3-B1: original ROM-backed CPC6128 screenshot acquisition, visual only.

Never asserts pixels equal native TFT nor extracts/forges screen characters.
Requires the pinned Caprice32 checkout (ROM from the checkout, not archived).
"""
import argparse
import configparser
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PIN = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
ROM = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
AMSDOS = "ea65e0fb44ee93ede4b6c507509b7e5ddf497fb7155023bea91ef229469fa04d"
PNG = bytes.fromhex("89504e470d0a1a0a")
DELAY = "CAP32_DELAY CAP32_DELAY"
END = DELAY + " CAP32_SCRNSHOT CAP32_EXIT"

def digest(data):
    return hashlib.sha256(data).hexdigest()

def numbered(count):
    return [f"{n * 10} REM L{n:02d}" for n in range(1, count + 1)]

# Source lines are entered BEFORE CLS; each run uses a brand-new CPC process.
# Measurements of row contents or timing require review of original PNGs.
CASES = {
    "list_26": (numbered(26), ["CLS", "LIST", END], 1),
    "list_32": (numbered(32), ["CLS", "LIST", END], 1),
    "wrap_40": (["10 REM " + "X" * 33], ["CLS", "LIST", END], 1),
    "wrap_80": (["10 REM " + "X" * 73], ["CLS", "LIST", END], 1),
    "wrap_120": (["10 REM " + "X" * 113], ["CLS", "LIST", END], 1),
    "input_after_list": (numbered(26), ["CLS", "LIST", DELAY, "PRINT 7", END], 1),
    "cursor_edges": ([], ["CLS", "LOCATE 1,1", 'PRINT "FIRST";',
                            "LOCATE 1,25", 'PRINT "LAST";', END], 1),
    "cr_last_row": ([], ["CLS", "LOCATE 1,25",
                         'PRINT "ABCDE";CHR$(13);"Z";', END], 1),
    "repeat_list_once": (numbered(27), ["CLS", "LIST", END], 1),
    "repeat_list_twice": (numbered(27), ["CLS", "LIST", DELAY, "LIST", DELAY, 'PRINT "AFTER2"', END], 1),
    "new_after_list": (numbered(27), ["CLS", "LIST", DELAY, "NEW", DELAY, "LIST", END], 1),
    "window_default": (numbered(26), ["WINDOW 1,40,1,25", "CLS", "LIST", END], 1),
}

def run(argv, **kwargs):
    return subprocess.run(argv, check=False, capture_output=True, **kwargs)

def acquire(cap, out):
    if out.exists():
        raise ValueError("refuse overwrite of previously acquired screenshots")
    submodule = run(["git", "-C", str(cap), "rev-parse", "HEAD"], timeout=10)
    if submodule.returncode or submodule.stdout.decode().strip() != PIN:
        raise ValueError("Caprice32 submodule revision mismatch")
    cap32 = cap / "cap32"
    version = run([str(cap32), "--version"], timeout=10)
    if version.returncode or b"4.6.0" not in version.stdout:
        raise ValueError("Caprice32 4.6.0 executable mismatch")
    for path, expected in ((cap / "rom/cpc6128.rom", ROM),
                           (cap / "rom/amsdos.rom", AMSDOS)):
        if not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError(f"ROM/AMSDOS provenance mismatch: {path.name}")
    if len((cap / "rom/cpc6128.rom").read_bytes()) != 32768:
        raise ValueError("unexpected CPC6128 ROM length")
    if not (cap / "cap32.cfg").is_file():
        raise ValueError("Caprice32 config absent")
    out.mkdir(parents=True)
    manifest = {
        "phase": "HW4-C3-B1",
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "github_sha": os.getenv("GITHUB_SHA"),
        "repository_baseline": "1e6dc4ae7974b32423a9511fa761d292876784fd",
        "oracle": {
            "name": "Caprice32", "version": version.stdout.decode(errors="replace").strip(),
            "commit": PIN, "model": "CPC6128", "ram_kb": 128, "basic": "1.1",
            "rom_sha256": ROM, "amsdos_sha256": AMSDOS,
            "rom_in_archive": False, "snapshot_in_archive": False
        },
        "channel": "unmodified Caprice32 screen PNG; no printer, no screen byte extraction",
        "screen_text_bytes_extracted": False,
        "pixel_identity_vs_CYD_claimed": False,
        "visual_review": "PENDING_MANUAL_INSPECTION",
        "cases": [],
    }
    for case_id, (program, actions, screenshots_expected) in CASES.items():
        work = out / case_id
        work.mkdir()
        (work / "source.bas").write_text("\n".join(program) + ("\n" if program else ""),
                                         encoding="ascii")
        operations = program + actions
        (work / "commands.json").write_text(json.dumps({
            "source": program, "operations": operations,
            "reboot_between_cases": True, "program_is_not_an_oracle": True,
            "screenshots_expected": screenshots_expected,
        }, indent=2) + "\n", encoding="utf-8")
        cfg = configparser.ConfigParser(interpolation=None)
        if not cfg.read(cap / "cap32.cfg"):
            raise ValueError("bad Caprice32 original config")
        cfg["system"].update(model="2", ram_size="128", speed="4",
                              auto_pause="0", printer="0", mf2="0",
                              keyboard="0", boot_time="42", limit_speed="0")
        cfg["control"]["kbd_layout"] = "0"
        cfg["sound"]["enabled"] = "0"
        cfg["video"].update(scr_style="1", scr_window="1")
        cfg["file"]["sdump_dir"] = str(work)
        cfg["file"]["printer_file"] = str(work / "unexpected-printer.dat")
        cfg["rom"]["rom_path"] = str(cap / "rom")
        cfg["rom"]["slot07"] = "amsdos.rom"
        cfg["rom"]["rom_mf2"] = ""
        cfg["system"]["resources_path"] = str(cap / "resources")
        with (work / "cap32.cfg").open("w", encoding="utf-8") as fd:
            cfg.write(fd, space_around_delimiters=False)
        cmd = ["xvfb-run", "-a", str(cap32), "-c", str(work / "cap32.cfg")]
        for operation in operations:
            cmd.extend(["-a", operation])
        env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
        proc = run(cmd, cwd=cap, env=env, timeout=120)
        (work / "caprice.log").write_bytes(
            ("command=cap32 --config <case> --auto <commands>\n"
             f"exit_code={proc.returncode}\n").encode("ascii")
            + proc.stdout + b"\n[stderr]\n" + proc.stderr)
        found = sorted(work.glob("screenshot_*.png"))
        if proc.returncode or len(found) != screenshots_expected:
            raise ValueError(f"{case_id}: exit={proc.returncode}, "
                             f"screenshots={len(found)}, expected={screenshots_expected}")
        images = []
        for index, original in enumerate(found, start=1):
            data = original.read_bytes()
            if not data.startswith(PNG) or len(data) < 1024:
                raise ValueError(f"{case_id}: invalid PNG #{index}")
            name = f"screen_{index:02d}.png"
            original_name = original.name
            original.rename(work / name)
            images.append({"name": name, "original_name": original_name,
                           "sha256": digest(data), "bytes": len(data)})
        prn = work / "unexpected-printer.dat"
        if prn.exists() and prn.stat().st_size:
            raise ValueError(f"{case_id}: unexpected CPC printer output")
        prn.unlink(missing_ok=True)
        files = {}
        for path in sorted(work.iterdir()):
            if path.is_file():
                raw = path.read_bytes()
                files[path.name] = {"sha256": digest(raw), "bytes": len(raw)}
        manifest["cases"].append({
            "id": case_id, "source": program, "operations": operations,
            "screenshots": images, "files": files,
            "classification": "SCREEN_CAPTURED_VISUAL_REVIEW_PENDING",
            "screen_text_bytes_verified": False,
        })
        print(f"B1 {case_id}: CPC screenshots={len(images)} "
              + " ".join(image["sha256"] for image in images), flush=True)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"B1 acquisition complete: {len(CASES)} cases; visual review PENDING",
          flush=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--caprice", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    acquire(args.caprice.resolve(), args.output.resolve())

if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"HW4-C3-B1 ORACLE ACQUISITION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
