#!/usr/bin/env python3
"""J1.25-B2-C3: strict lab aggregation; historical RENDER-A gate unchanged."""
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

CASES = {
 "ref": "21e95a7197413923bb5976067a0419bc729c20c1",
 "b1": "4d261f2a76374ab99a4dd7415cae7a097330c46b",
 "main_e008": "e0085a9e2d3b601359fc44fcfa3ea83430fc7056",
 "c1": "64b0087d5087903fee175c4f149c65a65bb43fe6",
 "main_ae07": "ae07e039a08f6fff66f752228dc2ebed3fcf4220",
 "combo": "ae07e039a08f6fff66f752228dc2ebed3fcf4220",
}
ROOT = Path("reports/c3")
DEST = Path("reports/c3-summary")
METRICS = ("iram", "dram", "bss", "iram_text", "iram_vectors",
           "flash_code", "flash_rodata", "flash_data", "flash_total",
           "image_bytes", "bin_bytes")
FIELDS = ("case", "source_sha", "run", *METRICS, "elf_sha256", "tree_sha",
          "docker_digest", "gate_rc", "gate_status")
LINE = re.compile(r"^\s*(\.[A-Za-z0-9_.$-]+)\s+(\d+)\s+")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as file:
        for data in iter(lambda: file.read(1048576), b""):
            h.update(data)
    return h.hexdigest()


def sections(path):
    values = {}
    for line in path.read_text().splitlines():
        match = LINE.match(line)
        if match:
            values[match.group(1)] = int(match.group(2))
    needed = (".dram0.data", ".dram0.bss", ".iram0.text",
              ".iram0.vectors", ".iram0.text_end", ".flash.text",
              ".flash.rodata")
    for key in needed:
        if key not in values:
            raise ValueError("MISSING_SECTION " + key + " " + str(path))
    if values[".iram0.text_end"] != 1:
        raise ValueError("BAD_IRAM_ENDPOINT")
    flash_data = values[".flash.rodata"] + values.get(".flash.appdesc", 256)
    return {
        "iram": sum(v for k, v in values.items()
                    if k.startswith(".iram0.") and k != ".iram0.text_end"),
        "dram": sum(v for k, v in values.items() if k.startswith(".dram0.")),
        "bss": values[".dram0.bss"],
        "iram_text": values[".iram0.text"],
        "iram_vectors": values[".iram0.vectors"],
        "flash_code": values[".flash.text"],
        "flash_rodata": values[".flash.rodata"],
        "flash_data": flash_data,
        "flash_total": flash_data + values[".flash.text"],
    }


def aggregate():
    DEST.mkdir(parents=True, exist_ok=True)
    rows, errors, digests = [], [], set()
    baseline = ROOT / "ref/run1/sections.txt"
    comparator = Path("tools/ci/hw4_render_a_memory.py")
    if not comparator.is_file():
        raise RuntimeError("MISSING_HISTORICAL_GATE")
    combo_tree = None
    for case, rev in CASES.items():
        root = ROOT / case
        try:
            if (root / "job-exit.txt").read_text().strip() != "0":
                raise ValueError("SOURCE_JOB_FAILED")
            if "source_ref=" + rev not in (root / "provenance.txt").read_text():
                raise ValueError("BAD_PROVENANCE_SHA")
            if case == "combo":
                parents = (root / "synthetic-parents.txt").read_text().split()
                if len(parents) != 3 or parents[1:] != [CASES["main_ae07"], CASES["c1"]]:
                    raise ValueError("BAD_SYNTHETIC_PARENTS")
                if "merge_exit=0" not in (root / "provenance.txt").read_text():
                    raise ValueError("MERGE_FAILED")
                combo_tree = (root / "synthetic-tree.txt").read_text().strip()
            repeated = []
            elf_hashes = []
            for run in (1, 2):
                p = root / ("run" + str(run))
                files = ("sections.txt", "firmware.elf", "firmware.bin",
                         "CMakeCache.txt", "compile_commands.json", "sdkconfig",
                         "idf-size.txt", "size-components.txt", "symbols.txt",
                         "readelf-sections.txt", "iram-disassembly.txt",
                         "iram-calls.txt", "firmware.map.gz", "gcc-version.txt",
                         "ld-version.txt", "build-head.txt", "source-sha.txt",
                         "source-tree.txt", "config-verdict.txt", "digests.txt")
                for f in files:
                    if not (p / f).is_file():
                        raise ValueError("MISSING " + str(p / f))
                if (p / "source-sha.txt").read_text().strip() != rev:
                    raise ValueError("BAD_SOURCE_SHA")
                if (p / "config-verdict.txt").read_text().strip() != "SPI40_STRICT=PASS":
                    raise ValueError("SPI40_NOT_VERIFIED")
                if "LOCO_CYD_PROFILE:STRING=CONSOLE" not in (p / "CMakeCache.txt").read_text():
                    raise ValueError("PROFILE_MISMATCH")
                if "CYD_LCD_SPI_HZ:STRING=40000000" not in (p / "CMakeCache.txt").read_text():
                    raise ValueError("SPI40_CACHE_MISMATCH")
                if "-DLCD_CLOCK_HZ=40000000U" not in (p / "compile_commands.json").read_text():
                    raise ValueError("SPI40_COMPILE_FLAG_MISSING")
                if case != "combo" and (p / "build-head.txt").read_text().strip() != rev:
                    raise ValueError("BAD_GIT_HEAD")
                if case == "combo" and (p / "source-tree.txt").read_text().strip() != combo_tree:
                    raise ValueError("BAD_COMBO_TREE")
                measurements = sections(p / "sections.txt")
                match = re.search(r"Total image size:\s*(\d+)\s+bytes",
                                  (p / "idf-size.txt").read_text())
                if match is None:
                    raise ValueError("NO_IDF_IMAGE_SIZE")
                measurements["image_bytes"] = int(match.group(1))
                measurements["bin_bytes"] = (p / "firmware.bin").stat().st_size
                repeated.append(measurements)
                test = subprocess.run(
                    [sys.executable, str(comparator), "--baseline", str(baseline),
                     "--optimized", str(p / "sections.txt")],
                    capture_output=True, text=True)
                (p / "historical-gate.stdout.txt").write_text(test.stdout)
                (p / "historical-gate.stderr.txt").write_text(test.stderr)
                (p / "historical-gate.returncode.txt").write_text(str(test.returncode) + "\n")
                if case == "ref" and test.returncode != 0:
                    raise ValueError("FROZEN_GATE_BASELINE_REJECTED")
                docker_digests = json.loads((root / "docker-repodigests.json").read_text())
                if not docker_digests or "sha256:" not in docker_digests[0]:
                    raise ValueError("NO_DOCKER_DIGEST")
                digests.add(docker_digests[0])
                elf_hash = sha(p / "firmware.elf")
                elf_hashes.append(elf_hash)
                rows.append({
                    "case": case, "source_sha": rev, "run": run,
                    **measurements,
                    "elf_sha256": elf_hash,
                    "tree_sha": (p / "source-tree.txt").read_text().strip(),
                    "docker_digest": docker_digests[0],
                    "gate_rc": test.returncode,
                    "gate_status": "PASS" if test.returncode == 0 else "FAIL",
                })
            if repeated[0] != repeated[1]:
                raise ValueError("COLD_REPETITIONS_DIFFER " + repr(repeated))
            (DEST / (case + "-repeat.txt")).write_text(
                "SECTIONS_REPEAT=IDENTICAL\n"
                + "ELF_SHA_IDENTICAL=" + str(elf_hashes[0] == elf_hashes[1]) + "\n"
                + "ELF1=" + elf_hashes[0] + "\nELF2=" + elf_hashes[1] + "\n")
        except (OSError, ValueError) as e:
            errors.append(case + ": " + str(e))
    with (DEST / "measurements.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    index = {row["case"]: row for row in rows if row["run"] == 1}
    if len(rows) == 12 and len(index) == 6 and not errors:
        delta = {k: index["combo"][k] - index["main_ae07"][k] for k in METRICS}
        (DEST / "incremental.json").write_text(json.dumps({
            "main_sha": CASES["main_ae07"], "pr330_sha": CASES["c1"],
            "combo_tree": combo_tree,
            "delta_main_to_combo": delta,
            "iram_dram_no_increase": delta["iram"] <= 0 and delta["dram"] <= 0,
            "historical_render_a_gate": index["combo"]["gate_status"],
        }, indent=2) + "\n")
        lines = ["# C3 — six états × deux builds propres CONSOLE/SPI40",
                 "", "| État | IRAM | DRAM | BSS | .iram0.text | Flash_Code | Flash_Data | Gate historique |",
                 "|---|---:|---:|---:|---:|---:|---:|---|"]
        for case in CASES:
            row = index[case]
            lines.append(f'| {case} | {row["iram"]} | {row["dram"]} | '
                         f'{row["bss"]} | {row["iram_text"]} | '
                         f'{row["flash_code"]} | {row["flash_data"]} | '
                         f'{row["gate_status"]} (rc={row["gate_rc"]}) |')
        lines += ["", "## Delta strict main ae07 vers main + C1",
                  "", "~~~json", json.dumps(delta, indent=2), "~~~",
                  "", "Un job laboratoire SUCCESS ne remplace PAS le gate RENDER-A.",
                  "", "DOCKER_DIGESTS=" + json.dumps(sorted(digests))]
        (DEST / "summary.md").write_text("\n".join(lines) + "\n")
        if len(digests) != 1:
            errors.append("TOOLCHAIN_IMAGE_DIGEST_NOT_IDENTICAL")
    else:
        errors.append("INCOMPLETE_6x2 expected 12 rows, got " + str(len(rows)))
    (DEST / "errors.txt").write_text("\n".join(errors) + ("\n" if errors else ""))
    if (DEST / "summary.md").exists():
        print((DEST / "summary.md").read_text())
    if errors:
        for e in errors:
            print("MEASUREMENT_INVALID: " + e, file=sys.stderr)
        return 1
    print("C3_SIX_CASES_TWO_BUILDS=PASS MEASUREMENTS_VALID=12")
    return 0


if __name__ == "__main__":
    sys.exit(aggregate())
