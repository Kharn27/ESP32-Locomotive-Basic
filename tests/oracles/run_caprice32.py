#!/usr/bin/env python3
"""Acquire independent Caprice32 CPC 6128 screenshots and printer *probes*.

Do not treat PNG pixels or PRINT #8 probes as CPC screen PRINT byte streams.
No ROM image or full snapshot is copied to the output directory.
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
PNG = bytes.fromhex("89504e470d0a1a0a")
CASES = {
    "minimal": ("tests/oracles/inputs/minimal.bas", "PRINT #8,5", 5),
    "witness": ("tests/fixtures/cpc6128/sources/c_integer_add.bas", "PRINT #8,B%", 5),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def command(args, cwd=None, timeout=30):
    return subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--caprice", type=Path, required=True, help="Caprice32 repository root")
    cli.add_argument("--native-cli", type=Path, required=True, help="independent C99 Linux CLI executable")
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--rom", type=Path, help="authorized cpc6128.rom; defaults to upstream ROM directory")
    cli.add_argument("--case", choices=tuple(CASES), action="append")
    args = cli.parse_args()
    root = Path(__file__).resolve().parents[2]
    cap = args.caprice.resolve()
    native_cli = args.native_cli.resolve()
    if not native_cli.is_file():
        raise RuntimeError(f"native C99 CLI missing: {native_cli}")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sha = command(["git", "-C", str(cap), "rev-parse", "HEAD"]).stdout.decode().strip()
    if sha != PIN:
        raise RuntimeError(f"Caprice32 SHA mismatch: {sha} != {PIN}")
    exe = cap / "cap32"
    if not exe.is_file():
        raise RuntimeError(f"Caprice32 executable missing: {exe}")
    version = command([str(exe), "--version"], cwd=cap).stdout.decode(errors="replace").strip()
    print(f"Caprice32 commit={sha}; version={version}", flush=True)
    # The emulator selects cpc6128.rom by *name* within rom_path.
    # Do not hash an arbitrary --rom path and accidentally execute its sibling.
    if args.rom and args.rom.name != "cpc6128.rom":
        raise RuntimeError("--rom must name cpc6128.rom (the filename selected by Caprice32)")
    romdir = args.rom.absolute().parent if args.rom else cap / "rom"
    rom = args.rom.absolute() if args.rom else romdir / "cpc6128.rom"
    if not rom.is_file():
        raise RuntimeError(f"CPC 6128 ROM missing: {rom}")
    system_rom = rom.read_bytes()
    if len(system_rom) != 32768:
        raise RuntimeError(f"expected 32768-byte combined CPC6128 ROM, got {len(system_rom)}")
    romhash = sha256(system_rom)
    amsdos = romdir / "amsdos.rom"
    amsdos_hash = sha256(amsdos.read_bytes()) if amsdos.is_file() else None
    print(f"CPC6128 ROM sha256={romhash}, 32768 bytes; BASIC 1.1 is expected, not independently verified by hash alone", flush=True)
    config_src = cap / "cap32.cfg"
    if not config_src.is_file():
        raise RuntimeError("Caprice32 cap32.cfg missing")
    manifest = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                "oracle": {"name": "Caprice32", "upstream": "ColinPitrat/caprice32",
                           "commit": sha, "version_output": version,
                           "model": "CPC6128", "ram_kb": 128, "keyboard": "English",
                           "rom_path_source": "upstream-or-authorized-override",
                           "rom_sha256": romhash, "amsdos_rom_sha256": amsdos_hash,
                           "basic_rom_version_claim": "1.1 (CPC6128; banner must be inspected)",
                           "rom_redistributed": False},
                "captures": []}
    for name in args.case or CASES:
        source_rel, probe, numeric = CASES[name]
        source_data = (root / source_rel).read_bytes()
        if b"\r" in source_data or not source_data.endswith(b"\n"):
            raise RuntimeError(f"{name}: source not LF-only and terminated")
        lines = source_data.decode("ascii").splitlines()
        if not all(re.fullmatch(r"[1-9][0-9]* .+", l) for l in lines):
            raise RuntimeError(f"{name}: unexpected source line syntax")
        work = out / name
        # Never accept stale screenshot/printer evidence as a new acquisition.
        if work.exists():
            raise RuntimeError(f"{name}: case directory already exists; use a fresh --output root")
        work.mkdir(parents=True, exist_ok=False)
        cfg = configparser.ConfigParser(interpolation=None)
        if not cfg.read(config_src):
            raise RuntimeError("cannot read Caprice32 config")
        cfg["system"].update(model="2", ram_size="128", speed="4",
                             auto_pause="0", printer="1", mf2="0",
                             keyboard="0", boot_time="42", limit_speed="0")
        cfg["control"]["kbd_layout"] = "0"
        cfg["sound"]["enabled"] = "0"
        cfg["video"].update(scr_style="1", scr_window="1")
        cfg["file"]["printer_file"] = str(work / "printer.dat")
        cfg["file"]["sdump_dir"] = str(work)
        cfg["rom"]["rom_path"] = str(romdir)
        cfg["rom"]["slot07"] = "amsdos.rom" if (romdir / "amsdos.rom").is_file() else ""
        cfg["rom"]["rom_mf2"] = ""
        cfg["system"]["resources_path"] = str(cap / "resources")
        with (work / "cap32.cfg").open("w", encoding="utf-8") as dest:
            # Caprice32 does not strip spaces after '=' for config values.
            cfg.write(dest, space_around_delimiters=False)
        calls = ["xvfb-run", "-a", str(exe), "-c", str(work / "cap32.cfg")]
        for line in lines:
            calls.extend(["-a", line])
        # The PRINT#8 probe runs separately after the original RUN.
        # Its bytes provide a numeric witness, NOT screen PRINT formatting.
        calls.extend(["-a", "RUN", "-a", probe,
                      "-a", "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"])
        env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
        (work / "autocmd.json").write_text(json.dumps({"source": source_rel,
                     "source_sha256": sha256(source_data), "commands": lines + [
                         "RUN", probe, "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"]}, indent=2) + "\n")
        print(f"Acquiring {name} with {len(lines)} numbered lines", flush=True)
        try:
            result = subprocess.run(calls, cwd=cap, env=env, capture_output=True,
                                    timeout=100, check=False)
        except subprocess.TimeoutExpired as exc:
            (work / "caprice.log").write_bytes((exc.stdout or b"") + b"\nTIMEOUT\n" + (exc.stderr or b""))
            raise RuntimeError(f"{name}: emulator timed out") from exc
        log = b"$ cap32 -c <case-config> -a <source lines> -a RUN -a <printer-probe> -a <screenshot+exit>\n"
        log += b"exit code: " + str(result.returncode).encode() + b"\n"
        log += result.stdout + b"\n[stderr]\n" + result.stderr
        (work / "caprice.log").write_bytes(log)
        if result.returncode:
            # Print error output in CI, not only in the archived failure log.
            print(log[-8000:].decode("utf-8", errors="replace"), file=sys.stderr)
            raise RuntimeError(f"{name}: Caprice32 exited with {result.returncode} (inspect caprice.log)")
        screenshots = sorted(work.glob("screenshot_*.png"))
        if len(screenshots) != 1:
            raise RuntimeError(f"{name}: expected exactly one screenshot, found {len(screenshots)}")
        screenshot = screenshots[0]
        pixels = screenshot.read_bytes()
        if not pixels.startswith(PNG) or len(pixels) < 1024:
            raise RuntimeError(f"{name}: invalid or empty screenshot")
        prn = work / "printer.dat"
        if not prn.is_file() or not prn.stat().st_size:
            raise RuntimeError(f"{name}: printer probe was not captured")
        printer_bytes = prn.read_bytes()
        # Numeric check of a separate direct-mode PRINT#8 probe, not screen output.
        values = [int(n) for n in re.findall(rb"(?<![0-9])[0-9]+(?![0-9])", printer_bytes)]
        if values != [numeric]:
            raise RuntimeError(f"{name}: printer probe value mismatch; found {values}, expected [{numeric}]")
        # A separate native execution. Only compare one INTEGER value, not bytes:
        # PRINT to the CPC screen is NOT PRINT#8 to an emulated printer.
        native_input = source_data + b"RUN\n:step 100\n:quit\n"
        native_result = subprocess.run([str(native_cli)], input=native_input,
                                       capture_output=True, timeout=15, check=False)
        (work / "native.stdout.bin").write_bytes(native_result.stdout)
        (work / "native.stderr.log").write_bytes(native_result.stderr)
        if native_result.returncode != 0:
            raise RuntimeError(f"{name}: native CLI process failure {native_result.returncode}")
        if b"[cli:error]" in native_result.stderr:
            raise RuntimeError(f"{name}: native CLI reported BASIC error")
        nmatch = re.fullmatch(rb"[ \t]*([+-]?[0-9]+)[ \t]*\n", native_result.stdout)
        if not nmatch:
            raise RuntimeError(f"{name}: native CLI did not output one integer line")
        native_number = int(nmatch.group(1))
        capture = {"case": name, "source_path": source_rel,
                   "source_sha256": sha256(source_data), "capture_method": "Caprice32 --autocmd SDL/Xvfb",
                   "operation": "numbered entry / RUN / direct printer probe / screenshot / exit",
                   "printer_interpretation": "direct-mode PRINT #8 probe, not PRINT screen byte equivalence",
                   "comparison": {
                       "status": "MATCH_SEMANTIC" if native_number == numeric else "DIFF",
                       "level": "strict single INTEGER value",
                       "local_channel": "C99 CLI PRINT stdout",
                       "oracle_channel": "CPC BASIC direct PRINT #8 probe after RUN",
                       "oracle_number": numeric, "native_number": native_number,
                       "format_exactness_claimed": False
                   },
                   "files": {}}
        for path in [screenshot, prn, work / "caprice.log", work / "cap32.cfg", work / "autocmd.json", work / "native.stdout.bin", work / "native.stderr.log"]:
            capture["files"][str(path.relative_to(out))] = {
                "sha256": sha256(path.read_bytes()), "size_bytes": path.stat().st_size}
        manifest["captures"].append(capture)
        print(f"{name}: screenshot={screenshot.name} sha256={sha256(pixels)} printer_probe={values} native={native_number} comparison={capture['comparison']['status']}", flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    print(f"COMPLETE {len(manifest['captures'])} independent ROM-backed executions; "
          "no exact CPC PRINT bytes / token images claimed", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, UnicodeError) as exc:
        print(f"ORACLE ACQUISITION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
