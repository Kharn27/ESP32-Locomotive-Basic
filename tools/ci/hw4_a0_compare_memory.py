#!/usr/bin/env python3
"""HW4-A0: immutable historical debt and authoritative PR-incremental Xtensa guard.

All three ELF inventories must come from successful ESP-IDF 5.5.6 builds.
SHA-to-Git-object verification is performed separately by hw4_a0_provenance.py.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

A0_SHA = "5799c774a3a5b3d453c17012a2328b379bd587bd"
PROFILES = ("CONSOLE", "HW3", "BASIC_PROBE")
REQUIRED = (".dram0.data", ".dram0.bss", ".iram0.vectors", ".iram0.text",
            ".iram0.text_end", ".flash.text", ".flash.rodata")
SECTION = re.compile(r"^\s*(\.[A-Za-z0-9_.$-]+)\s+(\d+)\s+(?:0x[0-9A-Fa-f]+|\d+)\s*$")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def checked_sha(value):
    if not SHA.fullmatch(value) or value == "0" * 40:
        raise ValueError("FAIL_CLOSED: full nonzero lowercase SHA required")
    return value


def read_size(path):
    contents = Path(path).read_text(encoding="utf-8")
    if not contents.strip():
        raise ValueError(f"FAIL_CLOSED: empty sections file: {path}")
    sections = {}
    totals = []
    for line in contents.splitlines():
        if line.lstrip().startswith("Total"):
            if not re.fullmatch(r"\s*Total\s+\d+\s*", line):
                raise ValueError(f"FAIL_CLOSED: malformed total in {path}")
            totals.append(int(line.strip().split()[1]))
        elif line.lstrip().startswith("."):
            match = SECTION.fullmatch(line)
            if match is None:
                raise ValueError(f"FAIL_CLOSED: malformed section line in {path}: {line!r}")
            name, value = match.group(1), int(match.group(2))
            if name in sections:
                raise ValueError(f"FAIL_CLOSED: duplicate section {name} in {path}")
            sections[name] = value
    if len(totals) != 1:
        raise ValueError(f"FAIL_CLOSED: missing/duplicated ELF Total in {path}")
    if totals[0] != sum(sections.values()):
        raise ValueError(f"FAIL_CLOSED: ELF Total disagrees with section sum in {path}")
    missing = sorted(set(REQUIRED) - sections.keys())
    if missing:
        raise ValueError(f"FAIL_CLOSED: missing ELF sections {missing} in {path}")
    if sections[".iram0.text_end"] != 1:
        raise ValueError(f"FAIL_CLOSED: unexpected IRAM endpoint in {path}")
    if any(sections[k] <= 0 for k in REQUIRED):
        raise ValueError(f"FAIL_CLOSED: empty required section in {path}")
    return {
        "dram": sum(v for k, v in sections.items() if k.startswith(".dram0.")),
        "bss": sections[".dram0.bss"],
        "iram": sum(v for k, v in sections.items()
                    if k.startswith(".iram0.") and k != ".iram0.text_end"),
        "flash_text": sections[".flash.text"],
        "flash_rodata": sections[".flash.rodata"],
        "section_count": len(sections),
    }


def read_image(path):
    data = Path(path).read_bytes()
    if not data:
        raise ValueError(f"FAIL_CLOSED: empty BIN: {path}")
    return {"bin": len(data), "bin_sha256": hashlib.sha256(data).hexdigest()}


def evaluate(a0, base, head, a0_sha, base_sha, head_sha, profile):
    if profile not in PROFILES:
        raise ValueError("FAIL_CLOSED: unsupported Xtensa profile")
    if a0_sha != A0_SHA:
        raise ValueError("FAIL_CLOSED: immutable A0 SHA mismatch")
    checked_sha(base_sha)
    checked_sha(head_sha)
    if base_sha == head_sha:
        raise ValueError("FAIL_CLOSED: base SHA equals HEAD SHA")
    for label, value in (("A0", a0), ("BASE", base), ("HEAD", head)):
        for key in ("dram", "bss", "iram", "flash_text", "flash_rodata", "bin"):
            if type(value.get(key)) is not int or value[key] <= 0:
                raise ValueError(f"FAIL_CLOSED: {label}: invalid {key}")
        if value["bss"] > value["dram"]:
            raise ValueError(f"FAIL_CLOSED: {label}: BSS exceeds DRAM")
        if not re.fullmatch(r"[0-9a-f]{64}", value.get("bin_sha256", "")):
            raise ValueError(f"FAIL_CLOSED: {label}: missing BIN digest")
    delta = lambda a, b, key: b[key] - a[key]
    def gate(left, right):
        return {
            "iram_delta": delta(left, right, "iram"),
            "dram_delta": delta(left, right, "dram"),
            "bss_delta": delta(left, right, "bss"),
            "iram": "PASS" if delta(left, right, "iram") == 0 else "FAIL",
            "dram": "PASS" if delta(left, right, "dram") <= 256 else "FAIL",
        }
    historic_base, historic_head, incremental = gate(a0, base), gate(a0, head), gate(base, head)
    historic_status = lambda g: "HISTORICAL_PASS" if g["iram"] == "PASS" and g["dram"] == "PASS" else "HISTORICAL_DEBT"
    verdict = "INCREMENTAL_PASS" if incremental["iram"] == "PASS" and incremental["dram"] == "PASS" else "INCREMENTAL_FAIL"
    return {
        "profile": profile,
        "idf": "v5.5.6",
        "references": {"A0": a0_sha, "BASE": base_sha, "HEAD": head_sha},
        "metrics": {"A0": a0, "BASE": base, "HEAD": head},
        "historical_base": {"status": historic_status(historic_base), **historic_base},
        "historical_head": {"status": historic_status(historic_head), **historic_head},
        "incremental": {"status": verdict, **incremental},
    }


def markdown(data):
    names = data["references"]
    measured = data["metrics"]
    lines = [f"### HW4-A0 {data['profile']} — ESP-IDF {data['idf']}", "",
             f"- A0 historique IMMUTABLE: {names['A0']}",
             f"- Base PR GitHub: {names['BASE']}",
             f"- HEAD PR réel: {names['HEAD']}", "",
             "| ELF / BIN bytes | A0 | Base PR | HEAD PR | A0→Base | A0→HEAD | Base→HEAD |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for key in ("flash_text", "flash_rodata", "iram", "dram", "bss", "bin"):
        a, b, h = (measured[label][key] for label in ("A0", "BASE", "HEAD"))
        lines.append(f"| {key} | {a} | {b} | {h} | {b-a:+d} | {h-a:+d} | {h-b:+d} |")
    lines.extend(["", "| Guard | IRAM delta=0 | DRAM delta≤+256 B (BSS incl.) | Verdict |",
                  "|---|---|---|---|"])
    for key, title in (("historical_base", "A0→Base PR (historique)"),
                       ("historical_head", "A0→HEAD PR (historique)"),
                       ("incremental", "Base PR→HEAD PR (AUTORITATIF)")):
        check = data[key]
        lines.append(f"| {title} | {check['iram']} ({check['iram_delta']:+d}) | "
                     f"{check['dram']} ({check['dram_delta']:+d}, BSS {check['bss_delta']:+d}) | "
                     f"**{check['status']}** |")
    lines.extend(["", "Historical debt is never reclassified as historical success; only the PR incremental guard decides this job.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("a0-size", "base-size", "head-size", "a0-bin", "base-bin", "head-bin",
                 "a0-sha", "base-sha", "head-sha", "profile", "output-md", "output-json"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    output_md, output_json = Path(args.output_md), Path(args.output_json)
    try:
        metrics = {}
        for label in ("a0", "base", "head"):
            metrics[label.upper()] = {**read_size(getattr(args, label + "_size")),
                                      **read_image(getattr(args, label + "_bin"))}
        result = evaluate(metrics["A0"], metrics["BASE"], metrics["HEAD"],
                          args.a0_sha, args.base_sha, args.head_sha, args.profile)
        md = markdown(result)
        exit_code = 0 if result["incremental"]["status"] == "INCREMENTAL_PASS" else 1
    except (ValueError, OSError, UnicodeError) as exc:
        result = {"status": "FAIL_CLOSED", "error": str(exc), "profile": args.profile}
        md = f"### HW4-A0 {args.profile}: **FAIL_CLOSED**\n\n{exc}\n"
        exit_code = 2
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(md, encoding="utf-8")
    output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(md)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
