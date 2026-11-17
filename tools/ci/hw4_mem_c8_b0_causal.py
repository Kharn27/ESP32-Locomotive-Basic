#!/usr/bin/env python3
"""C8-B0 (#390): read-only, sealed attribution of prelink/link-time IRAM changes.

The output establishes *where* the link differs, not the exact linker
decision or the safety of a production patch. Requires both real C6 ZIPs.
No calls to a compiler, linker, emulator, git checkout, or firmware writer.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re

from hw4_mem_c8_forensic import verify_archive, allocated_sections

SECTION_ROW = re.compile(
    r"^\s*(\.[\w.$-]+)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+(.+\.a\([^)]+\))\s*$")
CONTINUATION = re.compile(
    r"^\s*0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+(.+\.a\([^)]+\))\s*$")
SECTION = re.compile(r"^\s*(\.[\w.$-]+)\s*$")
FILL = re.compile(r"^\s*\*fill\*\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)")
LIB = re.compile(r"^esp-idf/([^/]+)/lib[^/]+\.a\(([^)]+)\)$")
REL_SECTION = re.compile(r"Relocation section '\.rela\.([^']+)'")
EXPAND = re.compile(r"^([0-9a-f]{8})\s+\S+\s+R_XTENSA_ASM_EXPAND\s+[0-9a-f]+\s+(\S+)")
SYMBOL = re.compile(
    r"^\s*\d+:\s*([0-9a-f]{8})\s+\d+\s+\w+\s+\w+\s+\w+\s+\S+\s+(.*)$")


def demand(ok, message):
    if not ok:
        raise ValueError("C8_B0_EVIDENCE_INVALID: " + message)


def parse_map(z, path):
    lines = z.read(path).decode("utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(".iram0.text "))
    stop = next(i for i in range(start + 1, len(lines))
                if lines[i].startswith(".dram0.data "))
    extent = int(lines[start].split()[-1], 16)
    demand(any("size before relaxing" in x for x in lines[start:stop]),
           "linker relaxation annotation missing: " + path)
    rows, fill, section = [], 0, ""
    for line in lines[start + 1:stop]:
        m = SECTION_ROW.match(line)
        if m:
            section, address, size, obj = m.groups()
            rows.append((obj, section, int(address, 16), int(size, 16)))
            continue
        m = CONTINUATION.match(line)
        if m:
            address, size, obj = m.groups()
            rows.append((obj, section, int(address, 16), int(size, 16)))
            continue
        m = SECTION.match(line)
        if m:
            section = m[1]
        m = FILL.match(line)
        if m:
            fill += int(m[2], 16)
    demand(sum(row[3] for row in rows) + fill == extent,
           "complete IRAM map reconciliation: " + path)
    return extent, rows, fill


def group(rows):
    result = defaultdict(list)
    for obj, sec, address, size in rows:
        result[obj].append((sec, address, size))
    return result


def normalized(s):
    for label in ("base", "head"):
        s = s.replace(".c6-d1-worktrees/" + label + "/",
                      ".c6-d1-worktrees/SIDE/")
        s = s.replace("build-d1-" + label + "-spi40",
                      "build-d1-SIDE-spi40")
    return s


def symbols(z, side):
    result = defaultdict(list)
    for line in z.read(side + "/linked-symbols.txt").decode().splitlines():
        m = SYMBOL.match(line)
        if m:
            result[m[2]].append(int(m[1], 16))
    return result


def audit(b2b, d1):
    z1, z2 = verify_archive(b2b, "b2b"), verify_archive(d1, "d1")
    maps = {label: parse_map(z2, label + "/firmware.map")
            for label in ("base", "head")}
    for label, expected in (("base", 66303), ("head", 66523)):
        demand(maps[label][0] == expected, "historic .iram0.text extent")
        for hz in ("spi40", "spi20"):
            other = parse_map(z1, label + "/" + hz + "/firmware.map")
            demand(other[0] == expected and group(other[1]) == group(maps[label][1]),
                   "C6 archives disagree: " + label + "/" + hz)
    for filename in ("link-command.txt",
                     "link-scripts/esp-idf/esp_system/ld/sections.ld"):
        a = normalized(z2.read("base/" + filename).decode())
        h = normalized(z2.read("head/" + filename).decode())
        demand(a == h, "link command/section script drift: " + filename)
    demand(z2.read("base/link-scripts/esp-idf/esp_system/ld/memory.ld") ==
           z2.read("head/link-scripts/esp-idf/esp_system/ld/memory.ld"),
           "memory linker script drift")
    before, after = group(maps["base"][1]), group(maps["head"][1])
    table = []
    for name in sorted(set(before) | set(after)):
        aa, bb = before.get(name, []), after.get(name, [])
        demand([x[0] for x in aa] == [x[0] for x in bb],
               "input section ordering changed: " + name)
        code = sum(y[2] - x[2] for x, y in zip(aa, bb)
                   if "literal" not in x[0])
        literal = sum(y[2] - x[2] for x, y in zip(aa, bb)
                      if "literal" in x[0])
        if code or literal:
            demand(name.startswith("esp-idf/"), "application IRAM changed")
            sections = [{"section": a[0], "base_address": hex(a[1]),
                         "head_address": hex(h[1]), "base_size": a[2],
                         "head_size": h[2]}
                        for a, h in zip(aa, bb) if a[2] != h[2]]
            table.append({"object": name, "code": code, "literal": literal,
                          "sections": sections})
    demand(len(table) == 16 and sum(x["code"] for x in table) == 88 and
           sum(x["literal"] for x in table) == 128 and
           maps["head"][2] - maps["base"][2] == 4,
           "16 IDF objects / +88 code +128 literal +4 fill")
    names = sorted(x[len("base/prelink/"):] for x in z2.namelist()
                   if x.startswith("base/prelink/") and x.endswith(".obj"))
    demand(len(names) == 18, "18 prelink members")
    changed = []
    for name in names:
        a, h = "base/prelink/" + name, "head/prelink/" + name
        if allocated_sections(z2.read(a)) != allocated_sections(z2.read(h)):
            changed.append(name)
        if not name.startswith("loco_core/"):
            for suffix in (".relocs.txt", ".sections-symbols.txt"):
                demand(z2.read(a + suffix) == z2.read(h + suffix),
                       "IDF prelink relocation/symbol changed: " + name + suffix)
    demand(changed == ["loco_core/basic_executor.c.obj",
                       "loco_core/basic_session_runtime.c.obj"],
           "application allocated prelink changes differ")
    symb, symh = symbols(z2, "base"), symbols(z2, "head")
    expansions = 0
    resolved = 0
    crossings = 0
    examples = []
    for row in table:
        obj = row["object"]
        m = LIB.match(obj)
        demand(m is not None, "unrecognized IDF archive name")
        file = m[1] + "/" + m[2]
        reloc = z2.read("base/prelink/" + file + ".relocs.txt").decode()
        base_rows = {sec: (addr, size) for sec, addr, size in before[obj]}
        head_rows = {sec: (addr, size) for sec, addr, size in after[obj]}
        section = ""
        for line in reloc.splitlines():
            m = REL_SECTION.match(line)
            if m:
                section = "." + m[1]
            m = EXPAND.match(line)
            if not m or section not in base_rows or section not in head_rows:
                continue
            expansions += 1
            off, target = int(m[1], 16), m[2]
            if len(symb.get(target, [])) != 1 or len(symh.get(target, [])) != 1:
                continue
            resolved += 1
            db = symb[target][0] - base_rows[section][0] - off
            dh = symh[target][0] - head_rows[section][0] - off
            # 0x80000 is a falsifiable *hypothesis*, not an established
            # criterion for the Xtensa linker and not a no-regression pass.
            crossings += (abs(db) <= 0x80000) != (abs(dh) <= 0x80000)
            if obj.endswith("(esp_err.c.obj)") and target == "esp_rom_printf":
                examples.append({"section": section, "offset": hex(off),
                                 "target": target, "distance_base": db,
                                 "distance_head": dh})
    demand(expansions == 437 and resolved == 377,
           "expanded-relocation/source matching changed")
    demand(crossings == 0, "simple 512KiB hypothesis has new crossings")
    return {"status": "ARCHIVAL_LINK_RELAXATION_WITNESS", "root_cause": "UNVERIFIED",
            "production_patch": "NOT_AUTHORIZED_WITHOUT_CAUSAL_COUNTERTEST",
            "source_elf_allocated_changes": changed,
            "system_elf_allocated_unchanged": 16,
            "system_relocations_identical": 16,
            "link_command_normalized_equal": True, "linker_script_normalized_equal": True,
            "archives_sha256_members_verified": {"B2B": 134, "D1": 228},
            "iram_base": 67331, "iram_head": 67551,
            "iram_text_base": 66303, "iram_text_head": 66523,
            "delta": {"code": 88, "literal": 128, "fill": 4, "iram": 220},
            "asm_expand_sections_relocations": expansions,
            "relocation_targets_resolvable": resolved,
            "relocation_targets_unresolved": expansions - resolved,
            "hypothesis_512KiB_crossings_resolved": crossings,
            "hypothesis_512KiB_is_not_verified_linker_rule": True,
            "changed_idf": table, "esp_err_relocation_samples": examples,
            "exploratory_xtensa_builds": 0,
            "missing_counterevidence": [
                "Complete frozen linker input tree and Xtensa binutils unavailable in archived ZIPs",
                "No exact mapping of retained/removed literal word to postlink relocation",
                "No controlled identical-input one-factor relink in same toolchain"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b2b", required=True, type=Path)
    parser.add_argument("--d1", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.b2b, args.d1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("C8_B0_SEALS=PASS B2B=134/134 D1=228/228")
    print("C8_B0_PRELINK_RELOCS=IDENTICAL system=16/16")
    print("C8_B0_LINK_DELTA=+220 code=+88 literal=+128 fill=+4")
    print("C8_B0_ROOT_CAUSE=UNVERIFIED NO_SAFE_PATCH exploratory_builds=0")


if __name__ == "__main__":
    main()
