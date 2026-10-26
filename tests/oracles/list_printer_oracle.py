#!/usr/bin/env python3
"""J0.24-C7: acquire genuine CPC6128 direct LIST-to-printer and native C99 LIST.

The CPC printer is a distinct channel from both the screenshot and C99 stdout.
A fresh emulator process loads each historical program; no RUN is injected.
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
AMSDOS_SHA = "ea65e0fb44ee93ede4b6c507509b7e5ddf497fb7155023bea91ef229469fa04d"
ROOT = Path(__file__).resolve().parents[2]
CASES = {
    "c_integer_add": ("tests/fixtures/cpc6128/sources/c_integer_add.bas",
                      "36afdbf24629f79f7753d1def84279374d54ee55eca7b03c2e0508da1ce396ec",
                      "LIST 10-40,#8"),
    "f_mixed_case": ("tests/fixtures/cpc6128/sources/f_mixed_case.bas",
                     "8b1c146b127009fec277794afa9ad8ee586ceeb8f0bac75c652ded59b73c34d6",
                     "LIST 10-30,#8"),
}
EXPECTED_FILES = ("source.bas", "autocmd.json", "cap32.cfg", "caprice.log",
                  "printer.dat", "native.stdin.bin", "native.stdout.bin",
                  "native.stderr.bin", "screen.png")
PNG = b"\x89PNG\r\n\x1a\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, check=False, **kwargs)


def difference(cpc, native):
    if cpc == native:
        return None
    offset = next((i for i, (a, b) in enumerate(zip(cpc, native)) if a != b),
                  min(len(cpc), len(native)))
    start = max(0, offset - 12)
    return {"offset": offset, "cpc_size": len(cpc), "native_size": len(native),
            "cpc_context_hex": cpc[start:offset + 16].hex(),
            "native_context_hex": native[start:offset + 16].hex()}


def classify(cpc, native, native_rc, native_stderr):
    if native_rc != 0 or b"[cli:error]" in native_stderr:
        return "UNSUPPORTED"
    if not cpc or not native:
        return "UNVERIFIED"
    return "MATCH_EXACT" if cpc == native else "DIFF"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--caprice", required=True, type=Path)
    p.add_argument("--native-cli", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    cap, cli, out = a.caprice.resolve(), a.native_cli.resolve(), a.output.resolve()
    if out.exists():
        raise ValueError("refuse to overwrite previous LIST evidence")
    if not cli.is_file():
        raise ValueError("missing native C99 CLI")
    revision = run(["git", "-C", str(cap), "rev-parse", "HEAD"], timeout=10)
    if revision.returncode or revision.stdout.decode().strip() != PIN:
        raise ValueError("Caprice32 commit not pinned")
    exe = cap / "cap32"
    version = run([str(exe), "--version"], cwd=cap, timeout=10)
    if version.returncode or b"4.6.0" not in version.stdout:
        raise ValueError("unapproved emulator binary")
    rom, amsdos = cap / "rom/cpc6128.rom", cap / "rom/amsdos.rom"
    if not rom.is_file() or len(rom.read_bytes()) != 32768 or digest(rom.read_bytes()) != ROM_SHA:
        raise ValueError("unapproved CPC6128 BASIC ROM")
    if not amsdos.is_file() or digest(amsdos.read_bytes()) != AMSDOS_SHA:
        raise ValueError("unapproved AMSDOS ROM")
    if not (cap / "cap32.cfg").is_file():
        raise ValueError("missing baseline CPC configuration")
    out.mkdir(parents=True)
    manifest = {
        "schema_version": 1, "phase": "J0.24-C7",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "github_sha": os.getenv("GITHUB_SHA"),
        "oracle": {"name": "Caprice32", "commit": PIN,
                   "version_output": version.stdout.decode(errors="replace").strip(),
                   "model": "CPC6128", "ram_kb": 128, "basic": "1.1",
                   "rom_sha256": ROM_SHA, "amsdos_sha256": AMSDOS_SHA,
                   "rom_archived": False, "snapshot_archived": False},
        "screen_bytes_captured": False, "printer_screen_byte_equivalence": False,
        "captures": [],
    }
    for case, (path, source_sha, list_command) in CASES.items():
        source = (ROOT / path).read_bytes()
        if digest(source) != source_sha or b"\r" in source or not source.endswith(b"\n"):
            raise ValueError(case + ": altered historical source")
        lines = source.decode("ascii").splitlines()
        if not all(re.fullmatch(r"[1-9][0-9]* .+", line) for line in lines):
            raise ValueError(case + ": malformed numbered program")
        work = out / case
        work.mkdir()
        (work / "source.bas").write_bytes(source)
        commands = lines + [list_command,
                            "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"]
        (work / "autocmd.json").write_text(json.dumps({
            "source_path": path, "source_sha256": source_sha,
            "commands": commands, "new_cpc_process": True,
            "direct_list_to_printer": True, "run_executed": False,
        }, indent=2) + "\n")
        cfg = configparser.ConfigParser(interpolation=None)
        if not cfg.read(cap / "cap32.cfg"):
            raise ValueError("bad original Caprice32 config")
        cfg["system"].update(model="2", ram_size="128", speed="4", auto_pause="0",
                             printer="1", mf2="0", keyboard="0", boot_time="42",
                             limit_speed="0")
        cfg["control"]["kbd_layout"] = "0"
        cfg["sound"]["enabled"] = "0"
        cfg["video"].update(scr_style="1", scr_window="1")
        cfg["file"]["printer_file"] = str(work / "printer.dat")
        cfg["file"]["sdump_dir"] = str(work)
        cfg["rom"]["rom_path"] = str(cap / "rom")
        cfg["rom"]["slot07"] = "amsdos.rom"
        cfg["rom"]["rom_mf2"] = ""
        cfg["system"]["resources_path"] = str(cap / "resources")
        with (work / "cap32.cfg").open("w") as file:
            cfg.write(file, space_around_delimiters=False)
        command = ["xvfb-run", "-a", str(exe), "-c", str(work / "cap32.cfg")]
        for part in commands:
            command += ["-a", part]
        env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
        cpc = run(command, cwd=cap, env=env, timeout=100)
        log = (b"$ cap32 -c <case-config> -a <historical numbered lines> "
               b"-a <direct LIST range,#8> -a <screenshot+exit>\n")
        log += b"exit code: " + str(cpc.returncode).encode() + b"\n"
        log += cpc.stdout + b"\n[stderr]\n" + cpc.stderr
        (work / "caprice.log").write_bytes(log)
        screenshots = list(work.glob("screenshot_*.png"))
        if cpc.returncode or len(screenshots) != 1:
            raise ValueError(case + ": CPC process or screenshot failed")
        original_screen_name = screenshots[0].name
        if not screenshots[0].read_bytes().startswith(PNG):
            raise ValueError(case + ": invalid screenshot")
        screenshots[0].rename(work / "screen.png")
        if not (work / "printer.dat").is_file():
            raise ValueError(case + ": no CPC printer file (LIST command may be invalid)")
        cpc_raw = (work / "printer.dat").read_bytes()
        # The historical source consists of precisely the numbered lines in
        # the requested range, so CLI LIST (without range support) is the
        # nearest non-mutating local operation. Record this limitation.
        native_stdin = source + b"LIST\n:quit\n"
        (work / "native.stdin.bin").write_bytes(native_stdin)
        native = run([str(cli)], input=native_stdin, timeout=15)
        (work / "native.stdout.bin").write_bytes(native.stdout)
        (work / "native.stderr.bin").write_bytes(native.stderr)
        status = classify(cpc_raw, native.stdout, native.returncode, native.stderr)
        capture = {
            "case": case, "source_path": path, "source_sha256": source_sha,
            "commands": commands, "original_screen_name": original_screen_name,
            "operation": "LIST_PRINTER_PROBE",
            "list_command_cpc": list_command, "list_command_native": "LIST",
            "selection_scope": "all stored historical lines, identical numbered range",
            "comparison": "exact-bytes", "classification": status,
            "first_difference": difference(cpc_raw, native.stdout),
            "cpc_returncode": cpc.returncode, "native_returncode": native.returncode,
            "cpc_channel": "printer.dat: CPC direct LIST <range>,#8 (no RUN)",
            "native_channel": "native.stdout.bin: C99 CLI LIST (no RUN)",
            "screen_channel": "screen.png: visual only, NOT byte-exact text",
            "files": {},
        }
        for name in EXPECTED_FILES:
            data = (work / name).read_bytes()
            capture["files"][name] = {"sha256": digest(data), "size_bytes": len(data)}
        manifest["captures"].append(capture)
        print(case, "CPC printer len", len(cpc_raw), "C99 stdout len",
              len(native.stdout), status, "first diff", capture["first_difference"], flush=True)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print("C7: two fresh CPC direct LIST observations, printer != screen")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, UnicodeError, subprocess.SubprocessError) as exc:
        print("C7 LIST ACQUISITION FAILED:", exc, file=sys.stderr)
        sys.exit(1)
