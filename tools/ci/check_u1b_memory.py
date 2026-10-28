#!/usr/bin/env python3
"""U1-B size gate: parse IDF v5.5.6 size.txt, compare U1-A numbers.

Only console DRAM/IRAM increases > 2048 bytes are automatic STOP;
all changes are printed for Pilotage explanation.
"""
import argparse
import pathlib
import re

BASELINE = {
    "CONSOLE": {"Flash Code": 111082, "IRAM": 67279, "DRAM": 49368, "image": 237533},
    "HW3": {"Flash Code": 82878, "IRAM": 67279, "DRAM": 31520, "image": 208753},
    "BASIC_PROBE": {"Flash Code": 74990, "IRAM": 51807, "DRAM": 31020, "image": 166477},
}
LINE = re.compile(r"^[│┃]\s*(Flash Code|IRAM|DRAM)\s*[│┃]\s*(\d+)\s*[│┃]")
IMAGE = re.compile(r"Total image size:\s*(\d+) bytes")


def parse(content):
    values = {}
    for line in content.splitlines():
        found = LINE.search(line)
        if found:
            values[found.group(1)] = int(found.group(2))
    match = IMAGE.search(content)
    if match:
        values["image"] = int(match.group(1))
    if set(values) != {"Flash Code", "IRAM", "DRAM", "image"}:
        raise ValueError("IDF size output missing size fields: " + str(values))
    return values


def check(profile, values):
    base = BASELINE[profile]
    for key, value in values.items():
        diff = value - base[key]
        print(f"U1-B {profile} {key.replace(' ', '_')}={value} BASE={base[key]} DELTA={diff:+d}")
        if profile == "CONSOLE" and key in ("IRAM", "DRAM") and diff > 2048:
            raise ValueError(f"U1-B STOP: CONSOLE {key} increased {diff} > 2048")
    print(f"U1-B SIZE_{profile}=PASS")


def self_test():
    sample = "│ Flash Code │ 111082 │\n│ IRAM │ 67279 │\n│ DRAM │ 49368 │\nTotal image size: 237533 bytes\n"
    original = parse(sample)
    assert original == BASELINE["CONSOLE"]
    check("CONSOLE", original)
    try:
        parse(sample.replace("DRAM", "UNKNOWN"))
    except ValueError:
        pass
    else:
        raise AssertionError("missing field escaped")
    try:
        check("CONSOLE", dict(original, DRAM=49368 + 2049))
    except ValueError:
        pass
    else:
        raise AssertionError("DRAM limit escaped")
    print("U1-B SIZE_NEGATIVE_TESTS=PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", nargs="?", choices=sorted(BASELINE))
    parser.add_argument("size_txt", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.profile and args.size_txt:
        check(args.profile, parse(pathlib.Path(args.size_txt).read_text(encoding="utf-8")))
    else:
        parser.error("profile and size_txt required unless --self-test")
