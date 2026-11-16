#!/usr/bin/env python3
"""C7-C1: check a REAL old-comparator rc=1 against structural ELF evidence.

The old RENDER-A/C3 programs are not edited, rebaselined or bypassed. Their
first exception can be DRAM before IRAM. An unexpected rc, exception or
measurements always STOP before the independent PR-incremental C7 verdict.
"""
import argparse
import sys
from pathlib import Path

from hw4_a0_compare_memory import read_size

ANCHORS = {"render": (67331, 54864), "c3": (67331, 54168)}
RENDER_DRAM = "RENDER-A introduces unauthorized incremental DRAM"
RENDER_IRAM = "RENDER-A introduces unauthorized incremental IRAM"
C3_DRAM = "C3-INT conditional DRAM cap"
C3_COST = "C3 instrumentation cost exceeds +696"
C3_IRAM = "IRAM changed"


def require(ok, reason):
    if not ok:
        raise ValueError("MEASUREMENT_INVALID: old comparator witness " + reason)


def attest(mode, rc, legacy_log, historical, spi40, spi20):
    require(mode in ANCHORS, "unknown mode")
    require(rc == 1, "unexpected rc=" + str(rc))
    h, a, b = (read_size(Path(path)) for path in (historical, spi40, spi20))
    require((h["iram"], h["dram"]) == ANCHORS[mode],
            "frozen historical ELF metric substituted")
    require(a["iram"] == b["iram"] and a["dram"] == b["dram"] and
            a["bss"] == b["bss"], "SPI mismatch before legacy verdict")
    log = Path(legacy_log).read_text(encoding="utf-8")
    require("Traceback (most recent call last):" in log,
            "missing actual historical exception traceback")
    if mode == "render":
        if a["dram"] > h["dram"]:
            expected, cause = RENDER_DRAM, "DRAM"
        elif a["iram"] > h["iram"]:
            expected, cause = RENDER_IRAM, "IRAM"
        else:
            raise ValueError("MEASUREMENT_INVALID: historical RENDER-A rc=1 without eligible measured failure")
        require("ValueError: " + expected in log,
                "RENDER-A rc=1 differs from measured first failure")
    else:
        if a["dram"] > 54864:
            expected, cause = C3_DRAM, "DRAM"
        elif not 0 <= a["dram"] - h["dram"] <= 696:
            expected, cause = C3_COST, "DRAM_COST"
        elif a["iram"] != 67331:
            expected, cause = C3_IRAM, "IRAM"
        else:
            raise ValueError("MEASUREMENT_INVALID: historical C3 rc=1 without eligible measured failure")
        require("AssertionError:" in log and expected in log,
                "C3 rc=1 differs from measured first failure")
    return {"status": "HISTORICAL_FAILURE", "old_rc": 1,
            "mode": mode, "first_failed_metric": cause,
            "historic_iram": h["iram"], "historic_dram": h["dram"],
            "head_iram": a["iram"], "head_dram": a["dram"],
            "spi_parity": "PASS"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", required=True, choices=tuple(ANCHORS))
    ap.add_argument("--old-rc", type=int, required=True)
    ap.add_argument("--legacy-log", required=True, type=Path)
    ap.add_argument("--historical", required=True, type=Path)
    ap.add_argument("--spi40", required=True, type=Path)
    ap.add_argument("--spi20", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        proof = attest(args.mode, args.old_rc, args.legacy_log,
                       args.historical, args.spi40, args.spi20)
    except (OSError, ValueError, UnicodeError) as e:
        print(e, file=sys.stderr)
        return 2
    print("HISTORICAL_FAILURE=TRUE old_exit=1 mode=" + proof["mode"] +
          " first=" + proof["first_failed_metric"] +
          " head_iram=" + str(proof["head_iram"]) +
          " head_dram=" + str(proof["head_dram"]) +
          " history=NOT_REQUALIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
