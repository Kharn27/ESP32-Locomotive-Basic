#!/usr/bin/env python3
"""CLK-01 independent CPC6128 SPEED acquisition; stdout/CYD are NOT its oracle."""
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
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tests/fixtures/cpc6128/clk_01_speed"
CAP32_SHA = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
ROM_SHA = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
IMAGE = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
         "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")


class AcquisitionError(ValueError):
    pass


def need(ok, msg):
    if not ok:
        raise AcquisitionError(msg)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    need(path.is_file() and not path.is_symlink(), "MISSING_FILE_" + str(path))
    return path.read_bytes()


def manifest():
    doc = json.loads(read(BASE / "manifest.json"))
    need(len(doc["programs"]) == 5, "WRONG_CORPUS")
    for p in doc["programs"]:
        text = read(BASE / p["file"])
        need(sha(text) == p["sha256"] and text.endswith(b"\n") and
             b"\r" not in text, "SOURCE_SEAL_" + p["id"])
        lines = text.decode("ascii").splitlines()
        need(all(re.fullmatch(r"[1-9][0-9]* .+", line) for line in lines),
             "BAD_NUMBERED_LINE_" + p["id"])
        need(sum(line.endswith(" END") for line in lines) == 1,
             "END_COUNT_" + p["id"])
    return doc


def cpc_number(raw):
    match = re.fullmatch(rb"[ \t]*([+-]?[0-9]+)[ \t\r\n]*", raw)
    need(match is not None, "BAD_CPC_PRINTER_NUMERIC_PAYLOAD")
    return int(match.group(1))


def setup(cap, dest):
    cfg = configparser.ConfigParser(interpolation=None)
    need(bool(cfg.read(cap / "cap32.cfg")), "CAP32_CONFIG_MISSING")
    cfg["system"].update(model="2", ram_size="128", speed="4",
                         auto_pause="0", printer="1", mf2="0",
                         keyboard="0", boot_time="42", limit_speed="1")
    cfg["control"]["kbd_layout"] = "0"
    cfg["sound"]["enabled"] = "0"
    cfg["video"].update(scr_style="1", scr_window="1")
    cfg["file"]["printer_file"] = str(dest / "printer.dat")
    cfg["file"]["sdump_dir"] = str(dest)
    cfg["rom"]["rom_path"] = str(cap / "rom")
    cfg["rom"]["slot07"] = "amsdos.rom"
    cfg["rom"]["rom_mf2"] = ""
    cfg["system"]["resources_path"] = str(cap / "resources")
    config = dest / "cap32.cfg"
    with config.open("w") as stream:
        cfg.write(stream, space_around_delimiters=False)
    return config


def execute(cap, dest, commands, timeout=140):
    dest.mkdir(parents=True, exist_ok=False)
    cfg = setup(cap, dest)
    argv = ["xvfb-run", "-a", str(cap / "cap32"), "-c", str(cfg)]
    for c in commands:
        need("\n" not in c and "\r" not in c, "ILLEGAL_COMMAND")
        argv.extend(["-a", c])
    (dest / "autocmd.json").write_text(json.dumps(
        {"commands": commands, "argv": argv, "nominal_speed": True}, indent=2) + "\n")
    env = dict(os.environ, SDL_VIDEODRIVER="x11", SDL_AUDIODRIVER="dummy")
    before = time.monotonic()
    try:
        process = subprocess.run(argv, cwd=cap, env=env, capture_output=True,
                                 timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        (dest / "caprice.log").write_bytes((exc.stdout or b"") + b"\nTIMEOUT\n" +
                                          (exc.stderr or b""))
        raise AcquisitionError("CPC_PROCESS_TIMEOUT_" + str(dest)) from exc
    wall = time.monotonic() - before
    (dest / "caprice.log").write_bytes(
        ("returncode=%d\nwall_seconds=%.9f\n" % (process.returncode, wall)).encode() +
        process.stdout + b"\n[stderr]\n" + process.stderr)
    need(process.returncode == 0, "CPC_NONZERO_EXIT_" + str(dest))
    return wall


def speed_gate(cap, out):
    """Differential CPC TIME and host wall, eliminating nominal boot overhead.

    CAP32_DELAY is automation pacing, not a trusted wall-clock source.
    Two pairs with independent processes; compare delta of LONG vs SHORT runs.
    """
    trials = []
    for trial in range(2):
        pair = {}
        for label, delays in (("short", 2), ("long", 16)):
            folder = out / ("gate_%d_%s" % (trial + 1, label))
            commands = ["PRINT #8,TIME",
                        " ".join(["CAP32_DELAY"] * delays),
                        "PRINT #8,TIME", "CAP32_DELAY CAP32_EXIT"]
            wall = execute(cap, folder, commands)
            samples = re.findall(rb"[+-]?[0-9]+", read(folder / "printer.dat"))
            need(len(samples) == 2, "SPEED_GATE_PROBE_COUNT")
            ticks = int(samples[1]) - int(samples[0])
            need(ticks > 0, "SPEED_GATE_NONPOSITIVE_TICKS")
            pair[label] = (wall, ticks)
        delta_wall = pair["long"][0] - pair["short"][0]
        delta_ticks = pair["long"][1] - pair["short"][1]
        need(delta_wall > 0.5 and delta_ticks > 100, "SPEED_GATE_TOO_SHORT")
        rate = delta_ticks / delta_wall
        trials.append({"short": pair["short"], "long": pair["long"],
                       "delta_wall_seconds": delta_wall, "delta_ticks": delta_ticks,
                       "ticks_per_wall_second": rate,
                       "status": "PASS" if 255 <= rate <= 345 else "FAIL"})
    need(all(t["status"] == "PASS" for t in trials),
         "EMULATOR_SPEED_UNVERIFIED")
    return trials


def instrumented(p):
    """CPC-only TIME probes: load/input time not covered; CYD uses raw source."""
    text = read(BASE / p["file"]).decode("ascii")
    lines = text.splitlines()
    target = str(p["end_line"]) + " END"
    need(lines.count(target) == 1, "END_ANCHOR_DRIFT")
    new = ["5 T=TIME"]
    for line in lines:
        if line == target:
            new.append(str(p["cpc_probe_line"]) + " PRINT #8,TIME-T")
        new.append(line)
    return new


def fingerprint(dest):
    result = {}
    for path in sorted(dest.rglob("*")):
        if path.is_file():
            name = str(path.relative_to(dest))
            result[name] = {"sha256": sha(read(path)), "bytes": path.stat().st_size}
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--caprice", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    doc = manifest()
    for p in doc["programs"]:
        lines = instrumented(p)
        need(lines[0] == "5 T=TIME" and
             sum("PRINT #8,TIME-T" in x for x in lines) == 1,
             "PROBE_WINDOW_INVALID")
    if args.self_test:
        need(cpc_number(b" 123 \r\n") == 123, "PRINTER_PARSE")
        try:
            cpc_number(b" 123 456 \r\n")
        except AcquisitionError:
            pass
        else:
            raise AcquisitionError("PRINTER_MUTATION_ACCEPTED")
        print("CLK-01 CPC SOURCE_SELF_TEST PASS 5/5; no emulator executed")
        return 0
    need(args.caprice is not None and args.output is not None,
         "CAPRICE_AND_OUTPUT_REQUIRED")
    cap = args.caprice.resolve()
    out = args.output.resolve()
    need(not out.exists(), "OUTPUT_EXISTS_NO_OVERWRITE")
    out.mkdir(parents=True)
    provenance = {"mission": "CLK-01", "generated_utc": datetime.now(timezone.utc).isoformat(),
                  "caprice_sha_expected": CAP32_SHA, "container_pin": IMAGE,
                  "rom_sha_expected": ROM_SHA, "speed": "EMULATOR_SPEED_UNVERIFIED",
                  "cpc": "UNVERIFIED", "comparison": "NOT_COMPARABLE",
                  "corpus": doc["programs"], "captures": [],
                  "screen_reset": "CPC CLS direct before RUN, outside TIME window"}
    try:
        git = subprocess.check_output(["git", "-C", str(cap), "rev-parse", "HEAD"],
                                      text=True).strip()
        need(git == CAP32_SHA, "CAP32_GIT_PIN")
        need(sha(read(cap / "rom/cpc6128.rom")) == ROM_SHA, "ROM_SHA_MISMATCH")
        need((cap / "cap32").is_file(), "CAP32_BINARY_MISSING")
        provenance["caprice_version"] = subprocess.check_output(
            [str(cap / "cap32"), "--version"], text=True).strip()
        execute(cap, out / "boot", ["CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"])
        provenance["gate"] = speed_gate(cap, out)
        provenance["speed"] = "NOMINAL_GATE_VERIFIED"
        for p in doc["programs"]:
            for repeat in range(1, 6):
                name = p["id"] + "/r%02d" % repeat
                folder = out / name
                # Direct screen reset before RUN: outside CPC TIME-T.
                cmds = ["NEW", "MODE 1"] + instrumented(p) + [
                    "CLS", "RUN", "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"]
                host_wall = execute(cap, folder, cmds)
                png = list(folder.glob("screenshot_*.png"))
                need(len(png) == 1 and read(png[0]).startswith(b"\x89PNG\r\n\x1a\n"),
                     "SCREEN_PNG_MISSING_" + name)
                ticks = cpc_number(read(folder / "printer.dat"))
                need(ticks > 0, "RUN_CPC_TICKS_ZERO_" + name)
                provenance["captures"].append({
                    "profile": p["id"], "repeat": repeat,
                    "ticks_300hz_probe_window": ticks,
                    "host_process_wall_seconds_not_run": host_wall,
                    "evidence_directory": name,
                    "source_sha256": p["sha256"]})
        provenance["cpc"] = "CPC_TIMING_ACQUIRED_PROBE_SCOPE"
    finally:
        provenance["files"] = fingerprint(out)
        (out / "manifest.json").write_text(json.dumps(provenance, indent=2) + "\n")
    need(provenance["cpc"] == "CPC_TIMING_ACQUIRED_PROBE_SCOPE", "INCOMPLETE_CPC_EVIDENCE")
    print("CLK-01 CPC acquired 25 independent runs at nominal-speed gate")
    print("CPC/CYD NOT_COMPARABLE: TIME probe and CYD RUN_DURATION differ in scope")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AcquisitionError, OSError, ValueError, subprocess.CalledProcessError) as err:
        print("CLK-01 CPC ACQUISITION FAILED:", err, file=sys.stderr)
        sys.exit(2)
