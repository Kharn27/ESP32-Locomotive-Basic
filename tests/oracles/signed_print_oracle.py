#!/usr/bin/env python3
"""J0.27-B1: acquire empirical CPC6128 BASIC 1.1 INTEGER PRINT evidence.

Each case/channel is a fresh Caprice32 process. No expected CPC numeric
formatting is encoded here. A CPC error remains visible in the screenshot,
even if it yields no printer bytes. Screen pixels are NEVER screen text bytes.
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

from run_behavior_oracle import PIN, ROM_SHA, ROOT, digest, run
from numeric_print_oracle import AMSDOS_SHA, CAPTURE, PNG

VALUES = {
    "zero": 0,
    "five": 5,
    "minus_one": -1,
    "minus_twelve": -12,
    "max_int16": 32767,
    "min_int16": -32768,
}
SOURCE_ROOT = ROOT / "tests/oracles/inputs/j027_b1"
INTEGER_LINE = re.compile(rb"( *)([+-]?)([0-9]+)( *)(\r\n|\n|\r)\Z")
SCREEN_FILES = ("original.bas", "source.bas", "autocmd.json", "cap32.cfg",
                "command_argv.json", "caprice.log", "screen.png",
                "native.stdin.bin", "native.stdout.bin", "native.stderr.bin")
PRINTER_FILES = ("original.bas", "source.bas", "autocmd.json", "cap32.cfg",
                 "command_argv.json", "caprice.log", "screen.png")


def variant(original):
    if original.count(b"20 PRINT B%\n") != 1:
        raise ValueError("PRINT B% source is not uniquely instrumentable")
    return original.replace(b"20 PRINT B%\n", b"20 PRINT #8,B%\n")


def commands_for(source):
    lines = source.decode("ascii").splitlines()
    if (len(lines) != 3 or
        not all(re.fullmatch(r"[1-9][0-9]* .+", line) for line in lines)):
        raise ValueError("expected exactly three numbered BASIC lines")
    return lines + ["RUN", CAPTURE]


def parse_integer(data):
    match = INTEGER_LINE.fullmatch(data)
    if match is None:
        return None
    sign = match.group(2).decode("ascii")
    digits = match.group(3).decode("ascii")
    return {
        "numeric_value": int(sign + digits),
        "leading_spaces": len(match.group(1)),
        "trailing_spaces": len(match.group(4)),
        "sign": sign,
        "digits": digits,
        "digit_count": len(digits),
        "terminator_hex": match.group(5).hex(" ").upper(),
    }


def write_bytes(path, data):
    path.write_bytes(data)


def produce(cap, exe, cli, out, case, value, mode, original):
    ident = case + "_" + mode
    work = out / ident
    work.mkdir()
    source = original if mode == "screen" else variant(original)
    write_bytes(work / "original.bas", original)
    write_bytes(work / "source.bas", source)
    commands = commands_for(source)
    trace = {
        "id": ident, "case": case, "mode": mode,
        "fresh_process": True, "run_executed": True,
        "direct_post_run_probe": False,
        "original_sha256": digest(original),
        "source_sha256": digest(source), "commands": commands,
    }
    write_bytes(work / "autocmd.json",
                (json.dumps(trace, indent=2) + "\n").encode("utf-8"))
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
    with (work / "cap32.cfg").open("w", encoding="utf-8") as stream:
        cfg.write(stream, space_around_delimiters=False)
    argv = ["xvfb-run", "-a", str(exe), "-c", str(work / "cap32.cfg")]
    for command in commands:
        argv.extend(["-a", command])
    write_bytes(work / "command_argv.json",
                (json.dumps(argv, indent=2) + "\n").encode("utf-8"))
    env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
    result = run(argv, cwd=cap, env=env, timeout=110)
    command_log = ("$ " + shlex.join(argv) + "\nexit code: " +
                   str(result.returncode) + "\n").encode("ascii")
    command_log += result.stdout + b"\n[stderr]\n" + result.stderr
    write_bytes(work / "caprice.log", command_log)
    pngs = sorted(work.glob("screenshot_*.png"))
    if result.returncode != 0 or len(pngs) != 1:
        raise ValueError(ident + ": missing screenshot or emulator execution failure")
    first_name = pngs[0].name
    png = pngs[0].read_bytes()
    if len(png) <= 1024 or not png.startswith(PNG):
        raise ValueError(ident + ": invalid CPC screenshot")
    pngs[0].rename(work / "screen.png")
    extra = work / "unexpected-printer.dat"
    if mode == "screen":
        if extra.exists() and extra.stat().st_size:
            raise ValueError(ident + ": unexpected CPC printer output")
        extra.unlink(missing_ok=True)
        stdin = original + b"RUN\n:step 100\n:quit\n"
        native = run([str(cli)], input=stdin, timeout=15)
        for name, data in (("native.stdin.bin", stdin),
                           ("native.stdout.bin", native.stdout),
                           ("native.stderr.bin", native.stderr)):
            write_bytes(work / name, data)
        native_parsed = parse_integer(native.stdout)
        native_status = ("UNSUPPORTED" if b"[cli:error]" in native.stderr
                         or native.returncode != 0 else
                         "OBSERVED" if native_parsed is not None else "UNVERIFIED")
        observed = None
        status = "VISUAL_OBSERVATION"
    else:
        printer = work / "printer.dat"
        raw = printer.read_bytes() if printer.is_file() else None
        observed = parse_integer(raw) if raw is not None else None
        status = ("PRINT_NUMERIC" if observed is not None else
                  "NO_NUMERIC_PRINTER_OUTPUT_REVIEW_REQUIRED")
        native_parsed, native_status, native = None, None, None
    file_names = list(SCREEN_FILES if mode == "screen" else PRINTER_FILES)
    if mode == "printer" and (work / "printer.dat").is_file():
        file_names.append("printer.dat")
    return {
        "id": ident, "case": case, "mode": mode, "hypothesis_integer": value,
        "source_path": "tests/oracles/inputs/j027_b1/" + case + ".bas",
        "original_sha256": digest(original), "source_sha256": digest(source),
        "commands": commands, "original_screenshot_name": first_name,
        "cpc_returncode": result.returncode,
        "cpc_printer_status": status,
        "printer_observation": observed,
        "printer_raw_hex": (raw.hex(" ").upper() if mode == "printer"
                            and raw is not None else None),
        "native_status": native_status,
        "native_observation": native_parsed,
        "native_returncode": native.returncode if native is not None else None,
        "screen_status": "VISUAL_OBSERVATION",
        "screen_text_bytes_extracted": False,
        "printer_screen_equivalent": False,
        "files": {name: {"sha256": digest((work / name).read_bytes()),
                         "size_bytes": (work / name).stat().st_size}
                  for name in file_names},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--caprice", required=True, type=Path)
    p.add_argument("--native-cli", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    cap, cli, out = args.caprice.resolve(), args.native_cli.resolve(), args.output.resolve()
    if out.exists():
        raise ValueError("output exists: fresh acquisition required")
    if not cli.is_file():
        raise ValueError("C99 CLI missing")
    rev = run(["git", "-C", str(cap), "rev-parse", "HEAD"], timeout=10)
    if rev.returncode or rev.stdout.decode().strip() != PIN:
        raise ValueError("Caprice32 commit mismatch")
    exe = cap / "cap32"
    version = run([str(exe), "--version"], cwd=cap, timeout=10)
    if version.returncode or b"4.6.0" not in version.stdout:
        raise ValueError("Caprice32 build identity incorrect")
    rom = cap / "rom/cpc6128.rom"
    amsdos = cap / "rom/amsdos.rom"
    if (not rom.is_file() or len(rom.read_bytes()) != 32768 or
            digest(rom.read_bytes()) != ROM_SHA or not amsdos.is_file() or
            digest(amsdos.read_bytes()) != AMSDOS_SHA):
        raise ValueError("CPC ROM hashes/size unapproved")
    out.mkdir(parents=True)
    m = {
        "schema_version": 1, "phase": "J0.27-B1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "github_sha": os.getenv("GITHUB_SHA"),
        "oracle": {"name": "Caprice32", "commit": PIN,
                   "version_output": version.stdout.decode(errors="replace").strip(),
                   "model": "CPC6128", "ram_kb": 128, "basic": "1.1",
                   "rom_sha256": ROM_SHA, "amsdos_sha256": AMSDOS_SHA,
                   "rom_archived": False, "snapshot_archived": False},
        "screen_bytes_extracted": False, "printer_screen_equivalent": False,
        "captures": [],
    }
    for case, value in VALUES.items():
        original = (SOURCE_ROOT / (case + ".bas")).read_bytes()
        if b"\r" in original or not original.endswith(b"\n"):
            raise ValueError(case + ": invalid source encoding")
        expected = (f"10 B%={value}\n20 PRINT B%\n30 END\n").encode("ascii")
        if original != expected:
            raise ValueError(case + ": source differs from defined corpus")
        for mode in ("screen", "printer"):
            record = produce(cap, exe, cli, out, case, value, mode, original)
            m["captures"].append(record)
            print(record["id"], "CPC status=", record["cpc_printer_status"],
                  "printer HEX=", record["printer_raw_hex"],
                  "C99 status=", record["native_status"], flush=True)
    write_bytes(out / "manifest.json",
                (json.dumps(m, indent=2) + "\n").encode("utf-8"))
    print("J0.27-B1 ACQUIRED 12 fresh CPC processes; "
          "CPC numeric syntax/error state requires empirical review", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError,
            configparser.Error) as err:
        print("J0.27-B1 acquisition failed:", err, file=sys.stderr)
        sys.exit(1)
