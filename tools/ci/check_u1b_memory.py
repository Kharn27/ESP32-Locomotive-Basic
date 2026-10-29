#!/usr/bin/env python3
"""U1-B size gate plus strictly scoped J1.15-C CONSOLE STRING BSS exception.

The exception is only 4096 bytes for the exact 64x64 caller-owned arena in
BasicStorage, attested by production header/source AND the linked ELF symbol.
IRAM has no exception; HW3 and BASIC_PROBE must not own s_basic.
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
ARENA_BYTES = 4096
LEGACY_MARGIN = 2048
SYMBOL = re.compile(r"^([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([bB])\s+s_basic$", re.M)


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


def verify_arena_contract(header, source, nm):
    """Evidence must be from the actual CONSOLE compile and ELF; never a flag."""
    for phrase in (
        "J115C_VARIABLES_CAPACITY = 64,",
        "J115C_STRING_SLOT_BYTES = 64,",
        "J115C_STRING_ARENA_CAPACITY =",
        "J115C_VARIABLES_CAPACITY * J115C_STRING_SLOT_BYTES",
        "arena_bytes != (size_t)J115C_STRING_ARENA_CAPACITY",
        "bvs_init_with_arena(store, entries, entry_count,",
    ):
        if phrase not in header:
            raise ValueError("J1.15-C contract mismatch: " + phrase)
    for phrase in (
        "VARIABLES_CAPACITY = J115C_VARIABLES_CAPACITY,",
        "STRING_SLOT_BYTES = J115C_STRING_SLOT_BYTES,",
        "STRING_ARENA_CAPACITY = J115C_STRING_ARENA_CAPACITY,",
        "uint8_t string_arena[STRING_ARENA_CAPACITY];",
        "static BasicStorage s_basic;",
        "j115c_init_store(&s_basic.variables,s_basic.entries,",
        "sizeof(s_basic.string_arena))!=BVS_OK",
    ):
        if phrase not in source:
            raise ValueError("J1.15-C firmware wiring mismatch: " + phrase)
    hits = SYMBOL.findall(nm)
    if len(hits) != 1:
        raise ValueError("J1.15-C missing/duplicate CONSOLE BSS s_basic ELF symbol")
    basic_size = int(hits[0][1], 16)
    if basic_size < ARENA_BYTES or basic_size > 65536:
        raise ValueError("J1.15-C invalid s_basic ELF BSS extent: " + str(basic_size))
    return basic_size


def check(profile, values, arena_size=None, nm=None):
    base = BASELINE[profile]
    if profile != "CONSOLE" and nm is not None and re.search(r"\bs_basic\s*$", nm, re.M):
        raise ValueError("J1.15-C non-CONSOLE image unexpectedly links s_basic")
    for key, value in values.items():
        diff = value - base[key]
        print(f"U1-B {profile} {key.replace(' ', '_')}={value} BASE={base[key]} DELTA={diff:+d}")
        if profile == "CONSOLE" and key == "IRAM" and diff > LEGACY_MARGIN:
            raise ValueError(f"U1-B STOP: CONSOLE IRAM increased {diff} > {LEGACY_MARGIN}")
        if profile == "CONSOLE" and key == "DRAM":
            if diff > LEGACY_MARGIN + ARENA_BYTES:
                raise ValueError(f"J1.15-C STOP: CONSOLE DRAM delta {diff} > {LEGACY_MARGIN + ARENA_BYTES}")
            if diff > LEGACY_MARGIN and arena_size is None:
                raise ValueError("J1.15-C STOP: no exact CONSOLE arena ELF/source attestation")
        if profile != "CONSOLE" and key == "DRAM" and diff > LEGACY_MARGIN:
            raise ValueError(f"J1.15-C STOP: {profile} DRAM grew > {LEGACY_MARGIN}")
    if profile == "CONSOLE" and arena_size is not None:
        print(f"J1.15-C CONSOLE_ARENA_ELF_BSS_BYTES={arena_size} "
              f"ARENA_BYTES={ARENA_BYTES} EXTRA_BUDGET_BYTES={ARENA_BYTES} PASS")
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
    for delta, attestation, should_pass in (
        (2048, None, True), (2049, None, False),
        (2049, 24000, True), (6144, 24000, True),
        (6145, 24000, False),
    ):
        try:
            check("CONSOLE", dict(original, DRAM=original["DRAM"]+delta), attestation)
        except ValueError:
            if should_pass:
                raise
        else:
            if not should_pass:
                raise AssertionError("DRAM falsification escaped " + str(delta))
    for p in ("HW3", "BASIC_PROBE"):
        check(p, BASELINE[p], nm="")
        for delta in (2049, 4096):
            try:
                check(p, dict(BASELINE[p], DRAM=BASELINE[p]["DRAM"]+delta))
            except ValueError:
                pass
            else:
                raise AssertionError("non-CONSOLE budget falsification escaped")
        try:
            check(p, BASELINE[p], nm="3ff00000 00006000 b s_basic\n")
        except ValueError:
            pass
        else:
            raise AssertionError("non-CONSOLE arena ELF escaped")
    # Source/ELF proof negative: no forged symbol or wrong slot quota.
    h = ("J115C_VARIABLES_CAPACITY = 64,\nJ115C_STRING_SLOT_BYTES = 64,\n"
         "J115C_STRING_ARENA_CAPACITY =\n"
         "J115C_VARIABLES_CAPACITY * J115C_STRING_SLOT_BYTES\n"
         "arena_bytes != (size_t)J115C_STRING_ARENA_CAPACITY\n"
         "bvs_init_with_arena(store, entries, entry_count,\n")
    s = ("VARIABLES_CAPACITY = J115C_VARIABLES_CAPACITY,\n"
         "STRING_SLOT_BYTES = J115C_STRING_SLOT_BYTES,\n"
         "STRING_ARENA_CAPACITY = J115C_STRING_ARENA_CAPACITY,\n"
         "uint8_t string_arena[STRING_ARENA_CAPACITY];\n"
         "static BasicStorage s_basic;\n"
         "j115c_init_store(&s_basic.variables,s_basic.entries,\n"
         "sizeof(s_basic.string_arena))!=BVS_OK\n")
    n = "3ffb0000 00005dc0 b s_basic\n"
    assert verify_arena_contract(h, s, n) == 24000
    for wrong_h, wrong_s, wrong_n in (
        (h.replace("= 64,", "= 65,"), s, n),
        (h, s.replace("string_arena[STRING_ARENA_CAPACITY]", "string_arena[4097]"), n),
        (h, s, "3ffb0000 00005dc0 b other_symbol\n"),
        (h, s, "3ffb0000 00000fff b s_basic\n"),
        (h, s, n+n),
    ):
        try:
            verify_arena_contract(wrong_h, wrong_s, wrong_n)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid arena evidence escaped")
    print("U1-B J1.15-C SIZE_NEGATIVE_TESTS=PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", nargs="?", choices=sorted(BASELINE))
    parser.add_argument("size_txt", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--console-source")
    parser.add_argument("--contract")
    parser.add_argument("--nm-file")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.profile and args.size_txt:
        nm = pathlib.Path(args.nm_file).read_text(encoding="utf-8") if args.nm_file else None
        attested = None
        if args.profile == "CONSOLE":
            if not (args.console_source and args.contract and nm is not None):
                parser.error("CONSOLE requires --console-source, --contract and --nm-file")
            attested = verify_arena_contract(
                pathlib.Path(args.contract).read_text(encoding="utf-8"),
                pathlib.Path(args.console_source).read_text(encoding="utf-8"), nm)
        check(args.profile,
              parse(pathlib.Path(args.size_txt).read_text(encoding="utf-8")),
              arena_size=attested, nm=nm)
    else:
        parser.error("profile and size_txt required unless --self-test")
