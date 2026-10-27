#!/usr/bin/env python3
"""J1.6-A: twelve independent CPC6128 INTEGER modulo experiments.

Pre-RUN LIST/SNA capture uses the approved J0.24 oracle. RUN is performed
in a second fresh CPC process on the EXACT original program. The later
direct-mode printer probes are separate from screen PRINT.
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

import token_ram_oracle as oracle
from signed_print_oracle import parse_integer

ROOT = Path(__file__).resolve().parents[2]
CASES = {"P6_M3": (6, 3), "P7_M2": (7, 2),
         "N7_M2": (-7, 2), "N7_M3": (-7, 3), "N5_M2": (-5, 2),
         "NMIN_M1": (-32768, 1), "NMIN_M255": (-32768, 255),
         "PMAX_M255": (32767, 255), "P2_M255": (2, 255),
         "P255_M255": (255, 255), "P1_M0": (1, 0), "P0_M0": (0, 0)}
SOURCE_DIR = ROOT / "tests/oracles/inputs/j1_6_a"

def validate_checkout_identity(declared_sha):
    """Fail closed: the PR event SHA must be the commit actually checked out.

    The manifest must use the measured checkout SHA, never environment text
    without verification. Call before writing any acquisition output.
    """
    measured_sha = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    if (not isinstance(declared_sha, str) or
            not re.fullmatch(r"[0-9a-f]{40}", declared_sha)):
        raise ValueError("J16_ACQUISITION_EVENT_SHA_MISSING")
    if measured_sha != declared_sha:
        raise ValueError(
            "J16_ACQUISITION_CHECKOUT_SHA_MISMATCH "
            f"actual={measured_sha} declared={declared_sha}"
        )
    return measured_sha


def run_observation(cap, work, original, cli):
    """Capture actual RUN screen and non-equivalent direct printer probes."""
    dest = work / "run"
    dest.mkdir()
    cfg = configparser.ConfigParser(interpolation=None)
    oracle.check(bool(cfg.read(cap / "cap32.cfg")), "missing Caprice32 config")
    cfg["system"].update(model="2", ram_size="128", speed="4",
                         auto_pause="0", printer="1", mf2="0", keyboard="0",
                         boot_time="42", limit_speed="0")
    cfg["control"]["kbd_layout"] = "0"
    cfg["sound"]["enabled"] = "0"
    cfg["video"].update(scr_style="1", scr_window="1")
    cfg["file"]["printer_file"] = str(dest / "printer.dat")
    cfg["file"]["sdump_dir"] = str(dest)
    cfg["rom"]["rom_path"] = str(cap / "rom")
    cfg["rom"]["slot07"] = "amsdos.rom"
    cfg["rom"]["rom_mf2"] = ""
    cfg["system"]["resources_path"] = str(cap / "resources")
    with (dest / "cap32.cfg").open("w") as f:
        cfg.write(f, space_around_delimiters=False)
    # The screenshot is taken BEFORE the two direct-mode printer probes.
    commands = original.decode("ascii").splitlines() + [
        "RUN", "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT",
        "PRINT #8,ERR", "PRINT #8,B%", "CAP32_DELAY CAP32_EXIT"]
    (dest / "autocmd.json").write_text(json.dumps({
        "commands": commands, "original_sha256": oracle.sha(original),
        "screenshot_after_run_before_direct_printer_probes": True,
        "printer_is_not_screen_bytes": True}, indent=2) + "\n")
    argv = ["xvfb-run", "-a", str(cap / "cap32"), "-c", str(dest / "cap32.cfg")]
    for c in commands:
        argv.extend(["-a", c])
    env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
    result = subprocess.run(argv, cwd=cap, env=env,
                            capture_output=True, timeout=120, check=False)
    (dest / "caprice.log").write_bytes(
        f"exit code: {result.returncode}\n".encode() +
        result.stdout + b"\n[stderr]\n" + result.stderr)
    oracle.check(result.returncode == 0, "RUN Caprice32 process failed")
    images = sorted(dest.glob("screenshot_*.png"))
    oracle.check(len(images) == 1 and
                 images[0].read_bytes().startswith(b"\x89PNG\r\n\x1a\n"),
                 "missing post-RUN screenshot")
    images[0].rename(dest / "run.png")
    # No synthesized CPC output on missing printer data.
    printer_path = dest / "printer.dat"
    printer = printer_path.read_bytes() if printer_path.is_file() else b""
    chunks = printer.splitlines(keepends=True)
    observed = [parse_integer(chunk) for chunk in chunks]
    valid = len(observed) == 2 and all(x is not None for x in observed)
    err_value = observed[0]["numeric_value"] if valid else None
    variable = observed[1]["numeric_value"] if valid else None
    stdin = original + b"RUN\n:step 100\n:quit\n"
    native = subprocess.run([str(cli)], input=stdin, capture_output=True,
                            check=False, timeout=25)
    (dest / "native.stdin.bin").write_bytes(stdin)
    (dest / "native.stdout.bin").write_bytes(native.stdout)
    (dest / "native.stderr.bin").write_bytes(native.stderr)
    native_number = parse_integer(native.stdout)
    native_status = (
        "UNSUPPORTED" if native.returncode != 0 or b"[cli:error]" in native.stderr
        else "NUMERIC_OUTPUT" if native_number is not None
        else "UNVERIFIED_OUTPUT")
    return {"fresh_cpc_run_session": True, "process_count_for_case": 2, "screenshot": "VISUAL_OBSERVATION",
            "printer_semantics": "direct-mode PRINT #8,ERR then PRINT #8,B% AFTER screenshot, never screen bytes",
            "printer_raw_hex": printer.hex(" ").upper(),
            "err_probe": err_value, "variable_probe": variable,
            "native_status": native_status,
            "native_number": native_number["numeric_value"] if native_number else None,
            "native_returncode": native.returncode,
            "files": {p.name: {"sha256": oracle.sha(p.read_bytes()),
                                "size_bytes": p.stat().st_size}
                      for p in dest.iterdir() if p.is_file()}}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--caprice", type=Path, required=True)
    p.add_argument("--image-cli", type=Path, required=True)
    p.add_argument("--native-cli", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    cap, out = args.caprice.resolve(), args.output.resolve()
    measured_sha = validate_checkout_identity(os.environ.get("GITHUB_HEAD_SHA"))
    oracle.self_test()
    oracle.check(not out.exists(), "fresh output directory required")
    oracle.check(subprocess.check_output(
        ["git", "-C", str(cap), "rev-parse", "HEAD"], text=True
    ).strip() == oracle.PIN, "Caprice32 commit mismatch")
    oracle.check(oracle.sha((cap / "rom/cpc6128.rom").read_bytes()) ==
                 oracle.ROM_SHA, "CPC6128 ROM hash mismatch")
    version = subprocess.check_output([str(cap / "cap32"), "--version"],
                                      cwd=cap, text=True).strip()
    out.mkdir(parents=True)
    manifest = {
        "schema_version": 1, "phase": "J1.6-A",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_head_sha": measured_sha,
        "oracle": {"emulator": "Caprice32", "commit": oracle.PIN,
                   "version_output": version, "rom_sha256": oracle.ROM_SHA,
                   "model": "CPC6128", "basic": "1.1", "ram_kb": 128},
        "rom_archived": False, "snapshots_archived": False,
        "screen_bytes_extracted": False, "printer_screen_equivalent": False,
        "historical_list_run": "UNVERIFIED",
        "screen_vs_printer": "NOT_BYTE_COMPARABLE",
        "j1_6_b_authorized": False,
        "historical_archives_modified": False,
        "captures": []
    }
    for name, (lhs, rhs) in CASES.items():
        source = (SOURCE_DIR / (name.lower() + ".bas")).read_bytes()
        expected = (f"10 A%={lhs}\n20 B%=A% MOD {rhs}\n30 PRINT B%\n40 END\n").encode("ascii")
        oracle.check(source == expected, f"{name}: BASIC source changed")
        pre = oracle.acquire(cap, cap / "rom", name, source, [10,20,30,40],
                             args.image_cli.resolve(), out)
        # Read the modulo opcode from the authentic CPC RAM image.
        # It is neither assumed in advance nor produced by the host tokenizer.
        ram = (out / name / "program.bin").read_bytes()
        _, records = oracle.records(ram)
        second = records[1]
        raw_line = ram[second["offset"]:second["offset"] + second["length"]]
        magnitude = (bytes([0x0e + rhs]) if rhs < 10
                     else bytes([0x19, rhs]))
        oracle.check(raw_line.endswith(magnitude + b"\x00"),
                     f"{name}: CPC literal not recognised; retain raw evidence")
        # Inspect the real keyword bytes between the explicit A% reference
        # (offset 13 in the CPC line record) and encoded RHS literal.
        # Spaces may survive CPC tokenization; do not assume MOD's token.
        between = raw_line[13:-len(magnitude)-1]
        token = between.strip(b" ")
        oracle.check(len(token) in (1, 2) and token[0] >= 0x80 and
                     (len(token) == 1 or token[0] == 0xFF),
                     f"{name}: MOD is not a single/prefixed CPC token: {between.hex()}")
        pre["operator_observed_hex"] = token.hex(" ").upper()
        pre["expression_bytes_hex"] = between.hex(" ").upper()
        work = out / name
        (work / "original.bas").write_bytes(source)
        pre["files"]["original.bas"] = {
            "sha256": oracle.sha(source), "size_bytes": len(source)}
        run = run_observation(cap, work, source, args.native_cli.resolve())
        record = {"case": name, "source_admission": "STORED_PROGRAM", "lhs": lhs, "rhs": rhs,
                  "source_path": f"tests/oracles/inputs/j1_6_a/{name.lower()}.bas",
                  "pre_run": pre, "run": run}
        manifest["captures"].append(record)
        print(name, "CPC_SHA256", pre["comparison"]["cpc_sha256"],
              "OPERATOR_OBSERVED", pre["operator_observed_hex"],
              "C99_TOKEN", pre["comparison"]["classification"],
              "ERR_PROBE", run["err_probe"], "B_PROBE", run["variable_probe"],
              "NATIVE", run["native_status"], flush=True)
    (out / "manifest.json").write_text(json.dumps(
        manifest, indent=2, ensure_ascii=True) + "\n")
    print("J1.6-A twelve original CPC pre-RUN/token and post-RUN captures completed "
          f"CHECKOUT_SHA_VERIFIED={measured_sha}", flush=True)

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError,
            UnicodeError, KeyError, configparser.Error) as exc:
        print("J1.6-A ACQUISITION FAILED:", exc, file=sys.stderr)
        sys.exit(1)
