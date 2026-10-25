#!/usr/bin/env python3
"""J0.24-C5: ROM-backed CPC BASIC program RAM oracle, independent of the C99 tokenizer.

Only the delimited BASIC program is exported. Full SNA snapshots exist in a
TemporaryDirectory outside output/ and are removed, including on error.
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
import tempfile

PIN = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
ROM_SHA = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
CASES = {
    "b_integer_scalar": ("sources/b_integer_scalar.bas", [10, 20, 30]),
    "c_integer_add": ("sources/c_integer_add.bas", [10, 20, 30, 40]),
    "d_self_reference": ("sources/d_self_reference.bas", [10, 20, 30, 40]),
    "e_goto": ("sources/e_goto.bas", [10, 20, 30, 40]),
    "g_uninitialized": ("sources/g_uninitialized.bas", [10, 20]),
    "a_print_constants": ("sources/a_print_constants.bas", [10, 20, 30]),
    "f_let_spacing": ("sources/f_let_spacing.bas", [10, 20, 30]),
    "f_mixed_case": ("sources/f_mixed_case.bas", [10, 20, 30]),
}
HEADER = 256
RAM_BYTES = 128 * 1024
# ROM BASIC 1.1: (&AE64) is the program base with an unused first byte;
# the first length word begins at base+1. (&AE66) is the first free byte,
# immediately following the 00 00 sentinel. See basic.asm e761-e76b/e864.
PROGRAM_BASE_PTR = 0xAE64
PROGRAM_END_PTR = 0xAE66
SNA_RAM_CONFIG = 0x41
SNA_RAM_KB = 0x6B
SNA_MODEL = 0x6D

def check(ok, message):
    if not ok:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def u16(data, offset):
    return int.from_bytes(data[offset:offset + 2], "little")

def records(data):
    pos = 0
    numbers = []
    detail = []
    while True:
        check(pos + 2 <= len(data), "truncated line length/sentinel")
        size = u16(data, pos)
        if size == 0:
            check(pos + 2 == len(data), "sentinel must be final two bytes")
            return numbers, detail
        check(5 <= size <= len(data) - pos, "invalid line record length")
        number = u16(data, pos + 2)
        check(1 <= number <= 65535 and (not numbers or number > numbers[-1]),
              "invalid, unordered or duplicate line number")
        check(data[pos + size - 1] == 0, "missing line terminator")
        detail.append({"line": number, "offset": pos, "length": size,
                       "terminator_offset": pos + size - 1})
        numbers.append(number)
        pos += size

def extract_snapshot(snapshot, expected_lines):
    check(len(snapshot) == HEADER + RAM_BYTES, "SNA size must be 256+128KiB")
    head = snapshot[:HEADER]
    check(head[:8] == b"MV - SNA" and head[0x10] == 3, "not a Caprice32 SNA v3")
    check(u16(head, SNA_RAM_KB) == 128 and head[SNA_MODEL] == 2,
          "snapshot not CPC6128 128KiB")
    check(head[SNA_RAM_CONFIG] & 7 == 0, "CPC RAM bank 0 not configured")
    ram = memoryview(snapshot)[HEADER:]
    base = u16(ram, PROGRAM_BASE_PTR)
    end = u16(ram, PROGRAM_END_PTR)
    check(0x016F <= base < 0x8000 and base + 3 < end <= 0x8000,
          f"ROM BASIC program pointers inconsistent: base={base:04x} end={end:04x}")
    check(ram[base] == 0, "BASIC prelude byte must be zero")
    start = base + 1
    program = bytes(ram[start:end])
    found, detail = records(program)
    check(found == expected_lines, f"line numbers {found} != {expected_lines}")
    check(len(program) == end - start, "unexpected image span")
    return program, {"base_pointer_address": PROGRAM_BASE_PTR,
                     "end_pointer_address": PROGRAM_END_PTR,
                     "base_pointer_value": base,
                     "start_address": start, "end_exclusive": end,
                     "snapshot_data_offset": HEADER,
                     "snapshot_program_offset": HEADER + start,
                     "length": len(program), "records": detail,
                     "line_numbers": found, "terminator_hex": "0000",
                     "bank": "physical bank 0, Gate Array RAM config 0",
                     "sentinel_offset": len(program) - 2}

def run(command, cwd, timeout=100, **kwargs):
    return subprocess.run(command, cwd=cwd, timeout=timeout, check=False,
                          capture_output=True, **kwargs)

def acquire(cap, romdir, case, source, numbers, image_cli, out):
    work = out / case
    check(not work.exists(), "refusing to reuse output case directory")
    work.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="loco-c5-sna-") as temporary:
        snaps = Path(temporary)
        cfg = configparser.ConfigParser(interpolation=None)
        check(bool(cfg.read(cap / "cap32.cfg")), "Caprice32 config missing")
        cfg["system"].update(model="2", ram_size="128", speed="4",
                             auto_pause="0", printer="0", mf2="0",
                             keyboard="0", boot_time="42", limit_speed="0")
        cfg["control"]["kbd_layout"] = "0"
        cfg["sound"]["enabled"] = "0"
        cfg["video"].update(scr_style="1", scr_window="1")
        cfg["file"]["snap_path"] = str(snaps)
        cfg["file"]["sdump_dir"] = str(work)
        cfg["rom"]["rom_path"] = str(romdir)
        cfg["rom"]["slot07"] = "amsdos.rom"
        cfg["rom"]["rom_mf2"] = ""
        cfg["system"]["resources_path"] = str(cap / "resources")
        with (work / "cap32.cfg").open("w") as f:
            cfg.write(f, space_around_delimiters=False)
        lines = source.decode("ascii").splitlines()
        check(len(lines) == len(numbers) and
              [int(x.split(" ", 1)[0]) for x in lines] == numbers,
              "input lines unexpectedly changed")
        # Snapshot BEFORE RUN; LIST is requested and visible in the screenshot.
        last = "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT"
        commands = lines + ["LIST", last]
        (work / "autocmd.json").write_text(json.dumps({
            "commands": commands, "snapshot_before_run": True,
            "source_sha256": sha(source), "list_requested": True}, indent=2) + "\n")
        cmd = ["xvfb-run", "-a", str(cap / "cap32"), "-c",
               str(work / "cap32.cfg")]
        # Caprice32 pinned argparse.cpp replaceCap32Keys() omits
        # CAP32_SNAPSHOT although keyboard.h defines it at MOD_EMU_KEY+13.
        # StringToEvents recognizes form-feed plus the low byte 0x0d.
        # Send that documented wire encoding; do NOT patch the emulator.
        for entry in commands:
            cmd.extend(["-a", entry.replace("CAP32_SNAPSHOT", "\x0c\x0d")])
        env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="x11")
        result = run(cmd, cap, env=env)
        # Caprice32 stdout+stderr contain no binary snapshot or ROM.
        log = (f"exit code: {result.returncode}\n".encode() +
               result.stdout + b"\n[stderr]\n" + result.stderr)
        (work / "caprice.log").write_bytes(log)
        check(result.returncode == 0, "Caprice32 failed: " +
              log[-1500:].decode("utf8", "replace"))
        screenshots = sorted(work.glob("screenshot_*.png"))
        check(len(screenshots) == 1 and
              screenshots[0].read_bytes().startswith(b"\x89PNG\r\n\x1a\n"),
              "LIST screenshot absent/invalid")
        # Screenshot is an independent visual witness of LIST. No OCR claims.
        screenshot = work / "list.png"
        screenshots[0].rename(screenshot)
        files = list(snaps.glob("*.sna"))
        if len(files) != 1:
            print("SNA DIAGNOSTIC: temporary dir:", [p.name for p in snaps.iterdir()],
                  "config snap_path:", cfg["file"].get("snap_path"),
                  "cap snap/:", [p.name for p in (cap/"snap").glob("*.sna")],
                  "cap cwd:", [p.name for p in cap.glob("*.sna")], flush=True)
            print("SNA DIAGNOSTIC Caprice32 log:",
                  log[-6000:].decode("utf8","replace"), flush=True)
        check(len(files) == 1, f"expected one temporary snapshot, found {len(files)}")
        snap = files[0].read_bytes()
        program, region = extract_snapshot(snap, numbers)
        # TemporaryDirectory removes the full SNA. Never copy it to work.
    capture = work / "program.bin"
    capture.write_bytes(program)
    local = run([str(image_cli)], None, timeout=15, input=source)
    supported = local.returncode == 0
    if not supported:
        # Only the CLI's explicit, clean rejection is an unsupported export.
        # Unexpected host crashes and other errors abort the acquisition.
        check(local.returncode == 2 and
              b"image-cli: input rejected:" in local.stderr and
              not local.stdout, "unexpected C99 image CLI failure: " +
              local.stderr.decode("utf8", "replace"))
        (work / "c99_error.txt").write_bytes(local.stderr)
    else:
        local_numbers, _ = records(local.stdout)
        check(local_numbers == numbers, "C99 output has invalid line numbers")
        (work / "c99.bin").write_bytes(local.stdout)
    disagreement = None
    if supported:
        first = next((i for i, (u, v) in enumerate(zip(program, local.stdout))
                      if u != v), min(len(program), len(local.stdout)))
        if program != local.stdout:
            disagreement = {
                "first_offset": first,
                "cpc_byte": f"{program[first]:02x}" if first < len(program) else None,
                "c99_byte": f"{local.stdout[first]:02x}" if first < len(local.stdout) else None,
                "cpc_context_hex": program[max(first-8, 0):first+9].hex(" "),
                "c99_context_hex": local.stdout[max(first-8, 0):first+9].hex(" "),
                "hypothesis": "unresolved; no normalization or tokenizer modification"}
    classification = ("UNSUPPORTED" if not supported else
                      "MATCH_EXACT" if disagreement is None else "DIFF")
    report = {"classification": classification,
              "basis": "raw contiguous RAM records including 0000 sentinel",
              "first_difference": disagreement,
              "cpc_size": len(program),
              "c99_size": len(local.stdout) if supported else None,
              "cpc_sha256": sha(program),
              "c99_sha256": sha(local.stdout) if supported else None,
              "c99_rejection": local.stderr.decode("utf8", "replace").strip()
                               if not supported else None}
    (work / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    info = {"case": case, "source_sha256": sha(source),
            "snapshot_taken_before_run": True, "list_requested": True,
            "region": region, "comparison": report, "files": {}}
    for p in work.iterdir():
        check(p.suffix not in (".sna", ".rom", ".dsk"), "forbidden output type")
        if p.is_file():
            info["files"][p.name] = {"size_bytes": p.stat().st_size,
                                     "sha256": sha(p.read_bytes())}
    print(f"{case} CPC_RAW_HEX={program.hex()} CPC_SHA256={sha(program)}", flush=True)
    if supported:
        print(f"{case} C99_RAW_HEX={local.stdout.hex()} C99_SHA256={sha(local.stdout)}", flush=True)
    else:
        print(f"{case} C99_EXPORT_UNSUPPORTED={report['c99_rejection']}", flush=True)
    print(f"{case} CPC_ADDR=[{region['start_address']:04x},{region['end_exclusive']:04x}) "
          f"C99_SHA256={report['c99_sha256']} STATUS={report['classification']} "
          f"DIFF={disagreement}", flush=True)
    return info

def self_test():
    image = b"\x06\x00\x0a\x00\x0e\x00\x00\x00"
    # A length 6 record followed by zero sentinel; no reliance on C99.
    nums, rows = records(image)
    check(nums == [10] and rows[0]["length"] == 6, "record parsing failed")
    for bad in (image[:-1], image + b"\0", b"\x04\x00\x0a\x00\x00\x00",
                b"\x06\x00\x0a\x00\x0e\x01\x00\x00"):
        try:
            records(bad)
        except ValueError:
            continue
        raise ValueError("negative validator test did not fail")
    # Synthetic SNA with independently encoded pointer and region.
    ram = bytearray(RAM_BYTES)
    ram[PROGRAM_BASE_PTR:PROGRAM_BASE_PTR+2] = (0x170).to_bytes(2, "little")
    ram[PROGRAM_END_PTR:PROGRAM_END_PTR+2] = (0x171 + len(image)).to_bytes(2,"little")
    ram[0x170] = 0
    ram[0x171:0x171 + len(image)] = image
    head = bytearray(HEADER)
    head[:8] = b"MV - SNA"
    head[0x10],head[SNA_MODEL] = 3,2
    head[SNA_RAM_KB:SNA_RAM_KB+2] = (128).to_bytes(2,"little")
    raw, region = extract_snapshot(bytes(head)+ram, [10])
    check(raw == image and region["snapshot_program_offset"] == 0x271,
          "SNA offset or boundaries wrong")
    print("PASS independent record/SNA parser tests and negative cases")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--caprice", type=Path)
    parser.add_argument("--image-cli", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    self_test()
    if args.self_test:
        return
    check(args.caprice is not None and args.image_cli is not None and
          args.output is not None, "--caprice, --image-cli and --output required")
    cap = args.caprice.resolve()
    image_cli = args.image_cli.resolve()
    check(image_cli.is_file(), "missing C99 image CLI")
    sha_git = subprocess.check_output(["git","-C",str(cap),"rev-parse","HEAD"],
                                      text=True).strip()
    check(sha_git == PIN, "incorrect Caprice32 commit " + sha_git)
    romdir = cap / "rom"
    check(sha((romdir / "cpc6128.rom").read_bytes()) == ROM_SHA,
          "system ROM SHA mismatch")
    version = subprocess.check_output([str(cap / "cap32"), "--version"],
                                      cwd=cap, text=True).strip()
    root = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    check(not list(out.iterdir()), "output directory must be empty")
    captures = []
    for case, (rel, nums) in CASES.items():
        source = (root / "tests/fixtures/cpc6128" / rel).read_bytes()
        check(source.endswith(b"\n") and b"\r" not in source,
              "unexpected source newline")
        captures.append(acquire(cap, romdir, case, source, nums, image_cli, out))
    manifest = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                "oracle": {"emulator": "Caprice32", "commit": PIN,
                           "version_output": version, "rom_sha256": ROM_SHA,
                           "model": "CPC6128", "basic": "1.1", "ram_kb": 128},
                "snapshots_archived": False, "rom_archived": False,
                "captures": captures}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("TOKEN_MANIFEST_JSON=" + json.dumps(manifest, separators=(",", ":")), flush=True)
    print(f"COMPLETE {len(captures)} CPC RAM-token acquisitions (full SNA erased); "
          "comparisons are observations, not compatibility assertions", flush=True)

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError,
            UnicodeError, KeyError) as err:
        print("J0.24-C5 ACQUISITION FAILED:",err,file=sys.stderr)
        sys.exit(1)
