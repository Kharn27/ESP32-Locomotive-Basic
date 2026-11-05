#!/usr/bin/env python3
"""HW4-DISP-RENDER-A: compare REAL Xtensa ELF sections with frozen main.

No threshold adjustment: inherited C3 DRAM limit is already exhausted.
Only identical or lower incremental DRAM / IRAM is acceptable.
"""
import argparse
from pathlib import Path
import re


def read_size(path):
    sections = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\.[A-Za-z0-9_.$-]+)\s+(\d+)\s+", line)
        if m:
            sections[m.group(1)] = int(m.group(2))
    for key in (".dram0.data", ".dram0.bss", ".iram0.vectors",
                ".iram0.text", ".flash.text", ".flash.rodata"):
        if key not in sections:
            raise ValueError("missing ELF section " + key + " in " + str(path))
    if sections.get(".iram0.text_end") != 1:
        raise ValueError("unexpected ESP-IDF IRAM endpoint marker")
    return {
        "dram": sum(v for k, v in sections.items() if k.startswith(".dram0.")),
        "bss": sections[".dram0.bss"],
        "iram": sum(v for k, v in sections.items()
                    if k.startswith(".iram0.") and k != ".iram0.text_end"),
        "flash_text": sections[".flash.text"],
        "flash_rodata": sections[".flash.rodata"],
    }


def validate(base, head):
    if base["dram"] != 54864 or base["iram"] != 67331:
        raise ValueError("baseline main@21e95a does not match accepted C3 ELF")
    if head["dram"] > base["dram"]:
        raise ValueError("RENDER-A introduces unauthorized incremental DRAM")
    if head["iram"] > base["iram"]:
        raise ValueError("RENDER-A introduces unauthorized incremental IRAM")
    return True


def self_test():
    sample = {
        "dram": 54864, "bss": 43792, "iram": 67331,
        "flash_text": 165370, "flash_rodata": 56228,
    }
    assert validate(sample, dict(sample))
    for key in ("dram", "iram"):
        bad = dict(sample)
        bad[key] += 1
        try:
            validate(sample, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("negative memory gate missing: " + key)
    bad_base = dict(sample)
    bad_base["dram"] -= 1
    try:
        validate(bad_base, sample)
    except ValueError:
        pass
    else:
        raise AssertionError("baseline drift was accepted")
    print("HW4_RENDER_A_MEMORY_SELF_TEST=PASS negatives=3")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--optimized", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        if args.baseline is None and args.optimized is None:
            return
    if args.baseline is None or args.optimized is None:
        ap.error("--baseline and --optimized required for ELF measurement")
    base, head = read_size(args.baseline), read_size(args.optimized)
    print("| Xtensa section (bytes) | main@21e95a baseline | RENDER-A | delta |")
    print("|---|---:|---:|---:|")
    for key in ("dram", "bss", "iram", "flash_text", "flash_rodata"):
        print(f"| {key} | {base[key]} | {head[key]} | {head[key] - base[key]:+d} |")
    validate(base, head)
    print("HW4_RENDER_A_INCREMENTAL_MEMORY=PASS DRAM_NO_INCREASE=1 "
          "IRAM_NO_INCREASE=1 BASE_SHA=21e95a7197413923bb5976067a0419bc729c20c1")


if __name__ == "__main__":
    main()
