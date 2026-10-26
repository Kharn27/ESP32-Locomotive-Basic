#!/usr/bin/env python3
"""J0.24-C6: acquire two independent CPC 6128 RUN executions and numeric probes.

Every case boots a *new* Caprice32 process, enters an unchanged numbered program,
executes RUN, then issues PRINT #8,B% in direct mode without a reset.
A printer probe is NEVER treated as CPC screen bytes.
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
ROOT = Path(__file__).resolve().parents[2]
CASES = {
    "c_integer_add": ("tests/fixtures/cpc6128/sources/c_integer_add.bas",
                      "36afdbf24629f79f7753d1def84279374d54ee55eca7b03c2e0508da1ce396ec", 5),
    "d_self_reference": ("tests/fixtures/cpc6128/sources/d_self_reference.bas",
                         "618271a360f538c5a68bc3dae662dbce3d875fe01cacd2375e1e2bf3dc8d2e15", 2),
}
# A single signed decimal INTEGER with CPC/CLI spaces and one final newline.
# No regex search inside unrelated bytes, no general stream normalization.
INTEGER = re.compile(rb"[ \t]*([+-]?[0-9]+)[ \t]*(?:\r\n|\n|\r)\Z")
PNG = b"\x89PNG\r\n\x1a\n"
EXPECTED_FILES = ("source.bas", "autocmd.json", "cap32.cfg", "caprice.log",
                  "printer.dat", "native.stdin.bin", "native.stdout.bin",
                  "native.stderr.bin", "screen.png")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def integer(data):
    match = INTEGER.fullmatch(data)
    if not match:
        return None
    n = int(match.group(1))
    return n if -32768 <= n <= 32767 else None


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, check=False, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caprice", required=True, type=Path)
    parser.add_argument("--native-cli", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cap, cli, out = args.caprice.resolve(), args.native_cli.resolve(), args.output.resolve()
    if out.exists():
        raise ValueError("output already exists; refusing stale or overwritten evidence")
    out.mkdir(parents=True)
    if not cli.is_file():
        raise ValueError("missing native CLI")
    commit = run(["git", "-C", str(cap), "rev-parse", "HEAD"], timeout=10)
    if commit.returncode or commit.stdout.decode().strip() != PIN:
        raise ValueError("unpinned Caprice32 commit")
    exe = cap / "cap32"
    version = run([str(exe), "--version"], cwd=cap, timeout=10)
    if version.returncode:
        raise ValueError("cannot identify Caprice32 executable")
    rom = cap / "rom/cpc6128.rom"
    if not rom.is_file() or digest(rom.read_bytes()) != ROM_SHA or len(rom.read_bytes()) != 32768:
        raise ValueError("CPC 6128 system/BASIC ROM not authenticated")
    amsdos = cap / "rom/amsdos.rom"
    if not amsdos.is_file():
        raise ValueError("missing AMSDOS ROM")
    original_config = cap / "cap32.cfg"
    if not original_config.is_file():
        raise ValueError("missing Caprice32 config")
    manifest = {
        "schema_version": 1, "phase": "J0.24-C6",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "github_sha": os.getenv("GITHUB_SHA"),
        "oracle": {"name": "Caprice32", "commit": PIN,
                   "version_output": version.stdout.decode(errors="replace").strip(),
                   "model": "CPC6128", "ram_kb": 128, "basic": "1.1",
                   "rom_sha256": ROM_SHA, "amsdos_sha256": digest(amsdos.read_bytes()),
                   "rom_archived": False, "snapshot_archived": False},
        "screen_bytes_captured": False,
        "printer_screen_byte_equivalence": False,
        "captures": [],
    }
    for case, (source_path, source_sha, hypothesis) in CASES.items():
        source = (ROOT / source_path).read_bytes()
        if digest(source) != source_sha or b"\r" in source or not source.endswith(b"\n"):
            raise ValueError(case + ": historical BASIC source altered")
        lines = source.decode("ascii").splitlines()
        if not all(re.fullmatch(r"[1-9][0-9]* .+", line) for line in lines):
            raise ValueError(case + ": unexpected source lines")
        work = out / case
        work.mkdir(exist_ok=False)
        (work / "source.bas").write_bytes(source)
        commands = lines + ["RUN", "PRINT #8,B%",
                            "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"]
        (work / "autocmd.json").write_text(json.dumps({
            "source_path": source_path, "source_sha256": source_sha, "commands": commands,
            "new_cpc_process": True, "probe_is_direct_after_run": True,
        }, indent=2) + "\n", encoding="utf-8")
        cfg = configparser.ConfigParser(interpolation=None)
        if not cfg.read(original_config):
            raise ValueError("invalid Caprice32 config")
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
        with (work / "cap32.cfg").open("w", encoding="utf-8") as file:
            cfg.write(file, space_around_delimiters=False)
        command = ["xvfb-run", "-a", str(exe), "-c", str(work / "cap32.cfg")]
        for part in commands:
            command += ["-a", part]
        env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
        try:
            cpc = run(command, cwd=cap, env=env, timeout=100)
        except subprocess.TimeoutExpired as exc:
            raise ValueError(case + ": Caprice32 timeout") from exc
        log = b"$ cap32 -c <case-config> -a <numbered lines> -a RUN -a PRINT#8 -a <screenshot+exit>\n"
        log += b"exit code: " + str(cpc.returncode).encode() + b"\n"
        log += cpc.stdout + b"\n[stderr]\n" + cpc.stderr
        (work / "caprice.log").write_bytes(log)
        screenshots = list(work.glob("screenshot_*.png"))
        if cpc.returncode != 0 or len(screenshots) != 1:
            raise ValueError(case + ": CPC run failed or screenshot absent")
        if not screenshots[0].read_bytes().startswith(PNG):
            raise ValueError(case + ": invalid screen PNG")
        original_screen_name = screenshots[0].name
        screenshots[0].rename(work / "screen.png")
        if not (work / "printer.dat").is_file():
            raise ValueError(case + ": printer channel missing")
        cpc_raw = (work / "printer.dat").read_bytes()
        cpc_number = integer(cpc_raw)
        native_stdin = source + b"RUN\n:step 100\n:quit\n"
        (work / "native.stdin.bin").write_bytes(native_stdin)
        native = run([str(cli)], input=native_stdin, timeout=15)
        (work / "native.stdout.bin").write_bytes(native.stdout)
        (work / "native.stderr.bin").write_bytes(native.stderr)
        native_number = integer(native.stdout)
        if native.returncode or b"[cli:error]" in native.stderr:
            status = "UNSUPPORTED"
        elif cpc_number is None or native_number is None:
            status = "UNVERIFIED"
        elif cpc_number == native_number:
            status = "MATCH_SEMANTIC"
        else:
            status = "DIFF"
        capture = {
            "case": case, "source_path": source_path, "source_sha256": source_sha,
            "original_screen_name": original_screen_name,
            "commands": commands, "hypothesis_not_oracle": hypothesis,
            "cpc_integer": cpc_number, "native_integer": native_number,
            "native_returncode": native.returncode, "cpc_returncode": cpc.returncode,
            "classification": status, "comparison": "strict-signed-integer",
            "operation": "RUN_NUMERIC_PROBE",
            "cpc_channel": "printer.dat: direct-mode PRINT #8,B% after RUN",
            "native_channel": "native.stdout.bin: C99 PRINT during RUN",
            "screen_channel": "screen.png: visual only; NOT byte-exact text",
            "files": {},
        }
        for name in EXPECTED_FILES:
            data = (work / name).read_bytes()
            capture["files"][name] = {"sha256": digest(data), "size_bytes": len(data)}
        manifest["captures"].append(capture)
        print(case, "CPC observed=", cpc_number, "C99 observed=", native_number,
              "classification=", status, "hypothesis=", hypothesis, flush=True)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("TWO FRESH CPC RUN ACQUISITIONS; no CPC screen byte-equivalence claimed")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, UnicodeError, subprocess.SubprocessError) as exc:
        print("RUN BEHAVIOR ACQUISITION FAILED:", exc, file=sys.stderr)
        sys.exit(1)
