#!/usr/bin/env python3
"""C4 lab-only: diagnose e500 -> e008 with strict C3 qualification. Never alter gates."""
import argparse
import collections
import csv
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

E500 = "e500864b3be612a325559259250f41cc35b5252b"
E008 = "e0085a9e2d3b601359fc44fcfa3ea83430fc7056"
BASELINE = "21e95a7197413923bb5976067a0419bc729c20c1"
DIGEST = "espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84"
C3_RUN = 42239047408
ROOT = Path("reports")
DEST = ROOT / "c4-summary"
LINE = re.compile(r"^\s*(\.[A-Za-z0-9_.$-]+)\s+(\d+)\s+")
OPCODES = ("call8", "callx8", "l32r")
NEEDED = ("sections.txt", "firmware.elf", "firmware.map.gz", "sdkconfig",
          "CMakeCache.txt", "compile_commands.json", "config-verdict.txt",
          "source-sha.txt", "build-head.txt", "source-tree.txt",
          "iram-disassembly.txt", "symbols.txt", "readelf-sections.txt",
          "iram-calls.txt", "gcc-version.txt", "ld-version.txt",
          "idf-version.txt", "digests.txt")
KEYS = ("iram", "dram", "bss", "iram_text", "iram_vectors",
        "flash_code", "flash_rodata", "flash_total")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sizes(path):
    v = {}
    for line in path.read_text().splitlines():
        m = LINE.match(line)
        if m:
            v[m.group(1)] = int(m.group(2))
    for k in (".iram0.text", ".iram0.vectors", ".iram0.text_end",
              ".dram0.data", ".dram0.bss", ".flash.text", ".flash.rodata"):
        if k not in v:
            raise ValueError("missing size section: " + k + " in " + str(path))
    if v[".iram0.text_end"] != 1:
        raise ValueError("bad iram endpoint")
    return {
        "iram": sum(n for k, n in v.items() if k.startswith(".iram0.") and k != ".iram0.text_end"),
        "dram": sum(n for k, n in v.items() if k.startswith(".dram0.")),
        "bss": v[".dram0.bss"],
        "iram_text": v[".iram0.text"],
        "iram_vectors": v[".iram0.vectors"],
        "flash_code": v[".flash.text"],
        "flash_rodata": v[".flash.rodata"],
        "flash_total": v[".flash.text"] + v[".flash.rodata"] + v.get(".flash.appdesc", 256),
    }


def checks(case, location, exact_source):
    if (location / "job-exit.txt").read_text().strip() != "0":
        raise ValueError(case + " builder job returned nonzero")
    repodigests = json.loads((location / "docker-repodigests.json").read_text())
    if DIGEST not in repodigests:
        raise ValueError(case + " Docker digest mismatch: " + repr(repodigests))
    recs = []
    for index in (1, 2):
        p = location / ("run" + str(index))
        for f in NEEDED:
            if not (p / f).is_file():
                raise ValueError(str(p / f) + " absent")
        if (p / "source-sha.txt").read_text().strip() != exact_source:
            raise ValueError(case + " bad source-sha")
        if (p / "build-head.txt").read_text().strip() != exact_source:
            raise ValueError(case + " bad checked-out HEAD")
        if (p / "config-verdict.txt").read_text().strip() != "SPI40_STRICT=PASS":
            raise ValueError(case + " SPI40 absent")
        cache = (p / "CMakeCache.txt").read_text()
        commands = (p / "compile_commands.json").read_text()
        for flag in ("LOCO_CYD_PROFILE:STRING=CONSOLE", "CYD_LCD_SPI_HZ:STRING=40000000"):
            if flag not in cache.splitlines():
                raise ValueError(case + " cache flag missing: " + flag)
        if "-DLCD_CLOCK_HZ=40000000U" not in commands:
            raise ValueError(case + " compile-time clock flag missing")
        if "ESP-IDF v5.5.6" not in (p / "idf-version.txt").read_text():
            raise ValueError(case + " ESP-IDF != v5.5.6")
        metrics = sizes(p / "sections.txt")
        recs.append((p, metrics))
    if recs[0][1] != recs[1][1]:
        raise ValueError(case + " repetition size mismatch")
    if sha(recs[0][0] / "sdkconfig") != sha(recs[1][0] / "sdkconfig"):
        raise ValueError(case + " repetition sdkconfig mismatch")
    for f in ("gcc-version.txt", "ld-version.txt"):
        if sha(recs[0][0] / f) != sha(recs[1][0] / f):
            raise ValueError(case + " repetition tool version mismatch")
    return recs


def comparable(e500, e008):
    for i in (0, 1):
        a, b = e500[i][0], e008[i][0]
        for f in ("sdkconfig", "gcc-version.txt", "ld-version.txt", "idf-version.txt"):
            if sha(a / f) != sha(b / f):
                raise ValueError("cross-state mismatch: " + f + " rep " + str(i + 1))
    return True


def output_csv(path, fieldnames, rows):
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def disasm_counts(path):
    text = path.read_text()
    return {op: len(re.findall(r"\b" + op + r"\b", text, re.IGNORECASE)) for op in OPCODES}


def iram_range(path, length):
    # readelf -SW wide output: [Nr] Name Type Address Off Size ...
    pattern = re.compile(r"^\s*\[\s*\d+\]\s+\.iram0\.text\s+\S+\s+([0-9a-fA-F]+)\s+")
    for line in path.read_text().splitlines():
        m = pattern.match(line)
        if m:
            start = int(m.group(1), 16)
            return start, start + length
    raise ValueError("IRAM section address not parsed in readelf")


def functions(path, lower, upper):
    # nm -S output: addr size type name; sum by name, preserving a CSV trail.
    symbols = collections.defaultdict(int)
    for line in path.read_text().splitlines():
        m = re.match(r"^([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([Tt])\s+(.+)$", line)
        if not m:
            continue
        address, size = int(m[1], 16), int(m[2], 16)
        if lower <= address < upper and size:
            symbols[m[4]] += size
    return symbols


def map_excerpts(path):
    import gzip
    with gzip.open(path, "rt", errors="replace") as handle:
        lines = handle.readlines()
    matches = []
    for i, line in enumerate(lines):
        if ("esp_system_get_time" in line or
            re.search(r"^\s+\.literal[.\s]", line) or
            re.search(r"^\s+\.iram[01]\.text[.\s]", line)):
            if "esp_system_get_time" in line:
                matches.extend(f"{j + 1}: {lines[j].rstrip()}" for j in range(max(0, i - 3), min(len(lines), i + 4)))
            else:
                matches.append(f"{i + 1}: {line.rstrip()}")
    return matches[:15000]


def report(e500, e008, ref, provenance):
    DEST.mkdir(parents=True, exist_ok=True)
    src, dst = e500[0][1], e008[0][1]
    delta = {k: dst[k] - src[k] for k in KEYS}
    if src["iram"] != 67331 or dst["iram"] != 67551 or delta["iram_text"] != 220 or delta["dram"] != 0:
        raise ValueError("HISTORICAL_SIZES_MISMATCH " + repr((src, dst, delta)))
    if ref[0][1]["iram"] != 67331 or ref[0][1]["dram"] != 54864:
        raise ValueError("C3 baseline does not match RENDER-A immutable contract")
    rows = []
    for case, samples in (("e500", e500), ("e008", e008)):
        for idx, (p, metrics) in enumerate(samples, 1):
            rows.append({"case": case, "run": idx, "source_sha": E500 if case == "e500" else E008,
                         "source_tree": (p / "source-tree.txt").read_text().strip(),
                         "image_digest": DIGEST, "elf_sha256": sha(p / "firmware.elf"),
                         "sdkconfig_sha256": sha(p / "sdkconfig"), **metrics})
    output_csv(DEST / "measurements.csv",
               ("case", "run", "source_sha", "source_tree", "image_digest",
                "elf_sha256", "sdkconfig_sha256", *KEYS), rows)
    a, b = e500[0][0], e008[0][0]
    opcode_rows = []
    for idx in (0, 1):
        counts_a = disasm_counts(e500[idx][0] / "iram-disassembly.txt")
        counts_b = disasm_counts(e008[idx][0] / "iram-disassembly.txt")
        for op in OPCODES:
            opcode_rows.append({"run": idx + 1, "opcode": op, "e500": counts_a[op],
                                "e008": counts_b[op], "delta": counts_b[op] - counts_a[op]})
    output_csv(DEST / "opcodes.csv", ("run", "opcode", "e500", "e008", "delta"), opcode_rows)
    start_a, end_a = iram_range(a / "readelf-sections.txt", src["iram_text"])
    start_b, end_b = iram_range(b / "readelf-sections.txt", dst["iram_text"])
    fa = functions(a / "symbols.txt", start_a, end_a)
    fb = functions(b / "symbols.txt", start_b, end_b)
    changes = []
    for symbol in sorted(fa.keys() | fb.keys()):
        va, vb = fa.get(symbol, 0), fb.get(symbol, 0)
        if va != vb:
            changes.append({"symbol": symbol, "e500_symbol_bytes": va,
                            "e008_symbol_bytes": vb, "delta": vb - va})
    output_csv(DEST / "named-symbol-deltas.csv",
               ("symbol", "e500_symbol_bytes", "e008_symbol_bytes", "delta"), changes)
    # These sizes can alias/overlap; never assign the unaccounted remainder to linker alignment.
    sym_delta = sum(row["delta"] for row in changes)
    ma = map_excerpts(a / "firmware.map.gz")
    mb = map_excerpts(b / "firmware.map.gz")
    (DEST / "iram-map-e500-excerpts.txt").write_text("\n".join(ma) + "\n")
    (DEST / "iram-map-e008-excerpts.txt").write_text("\n".join(mb) + "\n")
    (DEST / "iram-map-excerpt-diff.txt").write_text("\n".join(difflib.unified_diff(
        ma, mb, fromfile="e500.map selection", tofile="e008.map selection", lineterm="")) + "\n")
    comparator = Path("tools/ci/hw4_render_a_memory.py")
    gate_records = []
    base_file = ref[0][0] / "sections.txt"
    test = subprocess.run([sys.executable, str(comparator), "--self-test"],
                          text=True, capture_output=True)
    (DEST / "gate-self-test.txt").write_text(f"exit={test.returncode}\n" + test.stdout + test.stderr)
    if test.returncode:
        raise ValueError("historical gate self-test failed")
    for case, data in (("e500", e500), ("e008", e008)):
        for idx, (p, _) in enumerate(data, 1):
            cmd = [sys.executable, str(comparator), "--baseline", str(base_file),
                   "--optimized", str(p / "sections.txt")]
            process = subprocess.run(cmd, text=True, capture_output=True)
            file = DEST / f"gate-{case}-run{idx}.txt"
            file.write_text("command=" + " ".join(cmd) + f"\nexit={process.returncode}\n"
                            + process.stdout + process.stderr)
            gate_records.append({"case": case, "run": idx, "exit": process.returncode,
                                 "verdict": "PASS" if process.returncode == 0 else "FAIL"})
            if process.returncode != (0 if case == "e500" else 1):
                raise ValueError("unexpected historical gate rc: " + str(file))
    output_csv(DEST / "historical-gate.csv", ("case", "run", "exit", "verdict"), gate_records)
    result = {
        "C4": "SPI40_VERIFIED_REPEATED",
        "comparison_provenance": provenance, "c3_reference_run": C3_RUN,
        "historic_base": E500, "historic_head": E008, "historical_delta_bytes": delta,
        "opcode_changes": opcode_rows, "changed_named_symbols": len(changes),
        "sum_named_symbol_size_changes_NOT_ADDITIVE_PROOF": sym_delta,
        "unattributed_iram_bytes_NOT_AN_ALIGNMENT_CLAIM": 220 - sym_delta,
        "root_cause": "ROOT_CAUSE_UNVERIFIED",
        "historical_gate": "RENDER_A_HISTORICAL=FAILURE_ON_E008",
        "main_to_combo_c3": {"iram": 0, "dram": 0, "bss": 0,
                             "flash_code": 1880, "combo_tree": "a7c2183632d1dac055c1cabc57aa6867e3d1c833"},
    }
    (DEST / "diagnostic.json").write_text(json.dumps(result, indent=2) + "\n")
    op_line = "; ".join(f"{r['opcode']} {r['e500']}→{r['e008']} ({r['delta']:+d})"
                        for r in opcode_rows if r["run"] == 1)
    lines = [
        "# C4 diagnostic IRAM — LAB_ONLY_NEVER_MERGE",
        "", f"Provenance e008: **{provenance}**; reference gate ref from C3 run {C3_RUN}.",
        f"Two clean, strict-SPI40 repetitions per historical state, digest **{DIGEST}**.",
        "", "| Metric (bytes) | e500 after CLK-02 | e008 after A4 | Δ |",
        "|---|---:|---:|---:|",
    ]
    for metric in KEYS:
        lines.append(f"| {metric} | {src[metric]} | {dst[metric]} | {delta[metric]:+d} |")
    lines.extend([
        "", "## CALL / literal evidence",
        f"Disassembly opcodes in .iram0.text, run 1: **{op_line}**. Run 2 in opcodes.csv.",
        f"Changed nm-defined T/t IRAM symbols: **{len(changes)}**; sum of size differences "
        f"**{sym_delta:+d} B**. Remaining arithmetic **{220-sym_delta:+d} B** is "
        "**NOT** a proven linker alignment or literal attribution: symbols may alias or overlap.",
        "See named-symbol-deltas.csv and authentic .map excerpts / diff; no guessed exclusive partition.",
        "", "## Distinct gate semantics",
        "Historical RENDER-A baseline from C3 reference: 67,331 IRAM / 54,864 DRAM; "
        "e500 **PASS rc=0**, e008 **FAIL rc=1** in both repeats.",
        "Independently, C3 main ae07→combo incremental IRAM 0 / DRAM 0 / BSS 0; "
        "Flash Code +1,880, tree a7c2183632d1dac055c1cabc57aa6867e3d1c833.",
        "", "## Arbitrage non exécutoire (Pilotage uniquement)",
        "Option A: authorise a *separate future* narrowly targeted technical remediation "
        "after the causing symbols/placement are proven and risk evaluated.",
        "Option B: study a distinct main→candidate incremental gate while retaining "
        "RENDER_A_HISTORICAL=FAILURE visibly until a formal policy decision.",
        "No linker flags, thresholds, gates, core, firmware, PR #330, or main have been changed.",
        "ROOT_CAUSE_UNVERIFIED; ON_DEVICE_UNVERIFIED.",
    ])
    (DEST / "summary.md").write_text("\n".join(lines) + "\n")
    print((DEST / "summary.md").read_text())
    print("C4_REPEAT_SPI40=PASS SAMPLES=4 ROOT_CAUSE_UNVERIFIED")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualify-only", action="store_true")
    args = parser.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    try:
        e500 = checks("e500", ROOT / "c4/e500", E500)
    except Exception as err:
        print("MEASUREMENT_INVALID e500: " + repr(err), file=sys.stderr)
        return 2
    c3path = ROOT / "c3/main_e008"
    try:
        c3_e008 = checks("c3_e008", c3path, E008)
        comparable(e500, c3_e008)
        source = "C3_ARTIFACTS_13514271072"
    except Exception as err:
        (DEST / "c3-comparability.txt").write_text("C3_COMPARISON_IMPOSSIBLE\n"
                                                    + repr(err) + "\n")
        if args.qualify_only:
            print("C3_COMPARISON_IMPOSSIBLE; TWO_E008_BUILDS_REQUIRED " + repr(err))
            return 3
        try:
            c3_e008 = checks("c4_fallback_e008", ROOT / "c4/main_e008", E008)
            comparable(e500, c3_e008)
            source = "TWO_EXTRA_C4_BUILDS_REASON_" + type(err).__name__
        except Exception as fallback_error:
            print("MEASUREMENT_INVALID fallback: " + repr(fallback_error), file=sys.stderr)
            return 2
    else:
        (DEST / "c3-comparability.txt").write_text("C3_COMPARISON=QUALIFIED\n"
                                                   "toolchain, sdkconfig, SPI40 and source pins verified\n")
    if args.qualify_only:
        print("C3_COMPARISON=QUALIFIED; NO_EXTRA_E008_BUILDS")
        return 0
    try:
        ref = checks("c3_ref", ROOT / "c3/ref", BASELINE)
        if sha(ref[0][0] / "sdkconfig") != sha(e500[0][0] / "sdkconfig"):
            raise ValueError("historical ref sdkconfig mismatch")
        return report(e500, c3_e008, ref, source)
    except Exception as err:
        print("MEASUREMENT_INVALID report: " + repr(err), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
