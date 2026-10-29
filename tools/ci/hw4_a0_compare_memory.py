#!/usr/bin/env python3
"""A0: exact-base/head ESP-IDF Xtensa section and image comparison."""
import argparse
import re
from pathlib import Path

def sections(path):
    found = {}
    for line in path.read_text().splitlines():
        match = re.match(r"\s*(\.[A-Za-z0-9_.$-]+)\s+(\d+)\s+", line)
        if match:
            found[match.group(1)] = int(match.group(2))
    if not any(s.startswith(".dram0.") for s in found):
        raise ValueError(f"{path}: missing DRAM section table")
    if not any(s.startswith(".iram0.") for s in found):
        raise ValueError(f"{path}: missing IRAM section table")
    return found

def report(base, head, base_bin, head_bin, profile, base_sha):
    if re.fullmatch(r"[0-9a-f]{40}", base_sha) is None:
        raise ValueError("full comparison base SHA required")
    a, b = sections(base), sections(head)
    def category(data, prefixes):
        return sum(v for k, v in data.items() if any(k.startswith(p) for p in prefixes))
    groups = {
        "Flash code (.flash.text)": (".flash.text", ".irom0.text"),
        "Flash rodata (.flash.rodata)": (".flash.rodata", ".drom0.rodata"),
        "IRAM (.iram0.*)": (".iram0.",),
        "DRAM incl BSS (.dram0.*)": (".dram0.",),
        "BSS (.dram0.bss)": (".dram0.bss",),
    }
    result = []
    result.append(f"### {profile}: base {base_sha} vs instrumented HEAD\n")
    result.append("| Metric | base bytes | HEAD bytes | delta bytes |")
    result.append("|---|---:|---:|---:|")
    for title, prefixes in groups.items():
        x, y = category(a, prefixes), category(b, prefixes)
        result.append(f"| {title} | {x} | {y} | {y-x:+d} |")
        if title.startswith("IRAM") and x != y:
            raise ValueError(f"{profile}: IRAM changed {x} -> {y}")
        if title.startswith("DRAM incl") and y-x > 256:
            raise ValueError(f"{profile}: RAM budget exceeded ({y-x} bytes)")
    x, y = base_bin.stat().st_size, head_bin.stat().st_size
    result.append(f"| Firmware BIN | {x} | {y} | {y-x:+d} |")
    return "\n".join(result) + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-size", type=Path, required=True)
    ap.add_argument("--head-size", type=Path, required=True)
    ap.add_argument("--base-bin", type=Path, required=True)
    ap.add_argument("--head-bin", type=Path, required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--base-sha", required=True)
    args = ap.parse_args()
    print(report(args.base_size, args.head_size, args.base_bin,
                 args.head_bin, args.profile, args.base_sha))

if __name__ == "__main__":
    main()
