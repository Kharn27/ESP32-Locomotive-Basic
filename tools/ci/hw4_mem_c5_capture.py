#!/usr/bin/env python3
"""Capture attested C5 build evidence immediately from a successful Xtensa build.

Invoked inside the pinned ESP-IDF Docker container. No synthetic ELF metrics.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from hw4_mem_c5_v2 import FILES, IMAGE, CLOCKS, build_metrics, require
from verify_esp_app_version import boot_version


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--source-tree", required=True)
    ap.add_argument("--label", required=True, choices=("base", "head"))
    ap.add_argument("--variant", required=True, choices=tuple(CLOCKS))
    ap.add_argument("--image-id", required=True)
    a = ap.parse_args()
    folder = a.out
    require(all((folder / n).is_file() and (folder / n).stat().st_size for n in FILES),
            "incomplete actual Xtensa build")
    require(boot_version((folder / "firmware.bin").read_bytes(),
                         "loco_esp32_display_probe").startswith(a.source_sha[:7]),
            "embedded BIN SHA does not match built Git HEAD")
    meta = {"source_sha": a.source_sha, "source_tree": a.source_tree,
            "app_source_sha": a.source_sha, "source_label": a.label,
            "variant": a.variant, "clock_hz": CLOCKS[a.variant],
            "profile": "CONSOLE", "container_image": IMAGE,
            "docker_image_id": a.image_id,
            "digests": {n: sha((folder / n).read_bytes()) for n in FILES},
            "sdkconfig_sha256": sha((folder / "sdkconfig").read_bytes())}
    (folder / "source.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    # Check the complete manifest against its own real capture once.
    metrics = build_metrics(folder.parents[1], a.label, a.variant,
                            a.source_sha, a.source_tree)
    print("C5_CAPTURE=PASS label=" + a.label + " variant=" + a.variant +
          " IRAM=" + str(metrics["iram"]) + " DRAM=" + str(metrics["dram"]) +
          " BSS=" + str(metrics["bss"]))


if __name__ == "__main__":
    main()
