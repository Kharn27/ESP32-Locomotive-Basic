#!/usr/bin/env python3
"""CLK-02 strict 15-RUN phase auditor; all measurements remain PO candidates.

Uses the immutable CLK-01 source/UART/DMA checks, then enforces an exact,
additive RUN-window phase contract. CPU-exclusive/GRAM-visible are NOT measured.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
import re
import statistics
import sys

from clk_01_uart import (Reject, SCOPE, analyze as analyze_clk01,
                         corpus, fields, need)

BASELINE_HEAD = "3c4b2289cf9e7e806402aa997d9a711003c19623"
BASELINE_RAW_SHA256 = "38ba7108602e0a8424d0da90ccb6454c69307f977a5a197dd345497a11f4c586"
U64 = (1 << 64) - 1
U32 = (1 << 32) - 1
PHASE = "HW4-CLK02 RUN_PHASE_SUMMARY "
START = "HW4-RUN-B RUN_START "
DURATION = "HW4-DISP-PROFILE RUN_DURATION "
TERMINAL = "HW4-RUN-B RUN_TERMINAL "
MEMORY = "HW4-C2 DEVICE_MEMORY "
KEYS = {
    "version", "run", "duration_us", "step_call_wall_us",
    "repaint_call_wall_us", "yield_call_wall_us", "other_wall_us",
    "step_calls", "repaint_calls", "repaint_flushes", "repaint_bands",
    "full_repaints", "yield_calls", "probe_clock_reads", "valid",
    "unit", "clock", "scope", "step_scope", "repaint_scope",
    "yield_scope", "attribution", "sha",
}
NUMBERS = {
    "version", "run", "duration_us", "step_call_wall_us",
    "repaint_call_wall_us", "yield_call_wall_us", "other_wall_us",
    "step_calls", "repaint_calls", "repaint_flushes", "repaint_bands",
    "full_repaints", "yield_calls", "probe_clock_reads", "valid",
}
COUNTERS = {"step_calls", "repaint_calls", "repaint_flushes",
            "repaint_bands", "full_repaints", "yield_calls"}


def bounded(d, key):
    raw = d.get(key, "")
    need(re.fullmatch(r"[0-9]+", raw) is not None,
         "CLK02_INVALID_NUMBER_" + key)
    v = int(raw)
    need(v <= (U32 if key in COUNTERS or key in ("version", "run", "valid")
               else U64), "CLK02_OVERFLOW_" + key)
    return v


def validate_phase(d, expected_head, run_number, duration_us, quanta):
    need(set(d) == KEYS, "CLK02_MISSING_OR_EXTRA_FIELDS")
    n = {k: bounded(d, k) for k in NUMBERS}
    need(n["version"] == 1 and n["valid"] == 1,
         "CLK02_VERSION_OR_ACCOUNTING_INVALID")
    need(n["run"] == run_number and d["sha"] == expected_head,
         "CLK02_WRONG_RUN_OR_HEAD")
    need(n["duration_us"] == duration_us and duration_us > 0,
         "CLK02_DURATION_MISMATCH")
    expected_text = {
        "unit": "us",
        "clock": "esp_timer_task_wall",
        "scope": SCOPE,
        "step_scope": "scheduler_slice_call",
        "repaint_scope": "dirty_plus_touch_full_calls",
        "yield_scope": "cooperative_vTaskDelay_call",
        "attribution": "task_wall_not_cpu_or_gram",
    }
    for key, want in expected_text.items():
        need(d[key] == want, "CLK02_SCOPE_MISMATCH_" + key)
    need(n["step_calls"] == quanta and quanta > 0 and
         n["yield_calls"] == quanta - 1,
         "CLK02_QUANTUM_CALL_MISMATCH")
    need(n["repaint_calls"] == n["yield_calls"] + n["full_repaints"],
         "CLK02_REPAINT_CALL_MISMATCH")
    need(n["repaint_flushes"] <= n["yield_calls"],
         "CLK02_DIRTY_FLUSH_MISMATCH")
    need(30 * n["full_repaints"] <= n["repaint_bands"] <=
         25 * n["yield_calls"] + 30 * n["full_repaints"],
         "CLK02_BAND_COUNT_MISMATCH")
    need(n["probe_clock_reads"] ==
         2 * (n["step_calls"] + n["repaint_calls"] + n["yield_calls"]),
         "CLK02_PROBE_COUNT_MISMATCH")
    need(sum(n[k] for k in ("step_call_wall_us", "repaint_call_wall_us",
                            "yield_call_wall_us", "other_wall_us")) ==
         n["duration_us"], "CLK02_NONADDITIVE_WINDOW")
    return n


def analyze(raw, expected_head, baseline_raw=None):
    programs = corpus()
    # Preserves strict boot/HEAD, TX, full corpus, terminal, LCD and DMA tests.
    prior = analyze_clk01(raw, expected_head, programs)
    samples = []
    active = None
    for line in raw.splitlines():
        if START in line:
            need(active is None or active["phase"] is not None,
                 "CLK02_MISSING_PHASE")
            active = {"duration": None, "quanta": None, "phase": None}
        elif DURATION in line:
            need(active is not None and active["duration"] is None,
                 "CLK02_UNEXPECTED_DURATION")
            d = fields(line, DURATION)
            active["duration"] = bounded(d, "core_us")
        elif TERMINAL in line:
            need(active is not None and active["duration"] is not None and
                 active["quanta"] is None, "CLK02_UNEXPECTED_TERMINAL")
            d = fields(line, TERMINAL)
            active["quanta"] = bounded(d, "quanta")
        elif PHASE in line:
            need(active is not None and active["quanta"] is not None and
                 active["phase"] is None, "CLK02_DUPLICATE_OR_EARLY_PHASE")
            d = fields(line, PHASE)
            n = validate_phase(d, expected_head, len(samples) + 1,
                               active["duration"], active["quanta"])
            active["phase"] = n
            samples.append(n)
        elif MEMORY in line and "stage=run_terminal" in line:
            need(active is not None and active["phase"] is not None,
                 "CLK02_PHASE_NOT_BEFORE_MEMORY")
    need(active is not None and active["phase"] is not None,
         "CLK02_FINAL_PHASE_ABSENT")
    need(len(samples) == 15, "CLK02_EXPECTED_15_PHASES")
    baseline = None
    if baseline_raw is not None:
        need(hashlib.sha256(baseline_raw).hexdigest() == BASELINE_RAW_SHA256,
             "CLK02_BASELINE_RAW_SHA_MISMATCH")
        base_report = analyze_clk01(
            baseline_raw.decode("utf-8", "replace"), BASELINE_HEAD, programs)
        baseline = base_report["runs"]

    scenarios = []
    for i, spec in enumerate(programs["programs"]):
        triples = samples[3 * i:3 * (i + 1)]
        duration = [p["duration_us"] for p in triples]
        stats = {"scenario": spec["id"], "profile": spec["profile"],
                 "n": 3, "min_us": min(duration),
                 "median_us": statistics.median(duration),
                 "max_us": max(duration),
                 "spread_us": max(duration) - min(duration)}
        if baseline is not None:
            ref = baseline[i]
            need(ref["scenario"] == spec["id"] and ref["n"] == 3,
                 "CLK02_BASELINE_PROFILE_MISMATCH")
            old = ref["median_us"]
            need(old > 0, "CLK02_BASELINE_ZERO_MEDIAN")
            stats.update(baseline_median_us=old,
                         baseline_spread_us=ref["max_us"] - ref["min_us"],
                         delta_pct=(stats["median_us"] - old) * 100.0 / old,
                         drift_over_5pct=abs(stats["median_us"] - old) >
                                          0.05 * old)
        scenarios.append(stats)
    return {"head": expected_head, "samples": samples,
            "scenarios": scenarios, "baseline": baseline is not None,
            "status": "ON_DEVICE_PO_REVIEW_REQUIRED",
            "cpc_comparison": "NOT_COMPARABLE",
            "clk01_status": prior["status"]}


def reports(data):
    out = io.StringIO()
    cols = ("run", "scenario", "attempt", "duration_us",
            "step_call_wall_us", "repaint_call_wall_us",
            "yield_call_wall_us", "other_wall_us", "step_calls",
            "repaint_calls", "repaint_flushes", "repaint_bands",
            "full_repaints", "yield_calls", "probe_clock_reads")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(cols)
    for i, sample in enumerate(data["samples"]):
        row = {**sample, "run": i + 1,
               "scenario": data["scenarios"][i // 3]["scenario"],
               "attempt": 1 + i % 3}
        w.writerow([row[col] for col in cols])
    md = ["# CLK-02 RUN phase UART candidate", "",
          "HEAD: `" + data["head"] + "`", "",
          "All durations: task elapsed wall µs, not CPU-exclusive or GRAM-visible.",
          "Windows: step calls + repaint calls + vTaskDelay calls + residual",
          "equals RUN_DURATION; nested CLASS wall_us are not subtracted.", "",
          "| Profil | n | min / médiane / max µs | dispersion µs | baseline µs | delta % |",
          "|---|---:|---|---:|---:|---:|"]
    for row in data["scenarios"]:
        base = str(row["baseline_median_us"]) if data["baseline"] else "NON FOURNIE"
        delta = ("%.2f%%" % row["delta_pct"]) if data["baseline"] else "NON MESURÉ"
        md.append("| %s | 3 | %d / %g / %d | %d | %s | %s |" %
                  (row["scenario"], row["min_us"], row["median_us"],
                   row["max_us"], row["spread_us"], base, delta))
    md += ["", "Baseline source: " + (BASELINE_RAW_SHA256 if data["baseline"]
                    else "RAW PO CLK-01 NON FOURNI : overhead NON MESURÉ"),
           "Delta is cross-firmware RUN wall-time drift, NOT isolated CPU probe cost.",
           "A median drift >5% flags review; dispersion and hardware conditions matter.",
           "CPC TIME ↔ CYD RUN_DURATION: NOT_COMPARABLE.",
           "Result: ON_DEVICE_PO_REVIEW_REQUIRED; Pilotage alone accepts.", ""]
    return out.getvalue(), "\n".join(md)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("uart", type=Path)
    p.add_argument("--sha", required=True, help="exact SHA flashed on CYD")
    p.add_argument("--baseline-uart", type=Path,
                   help="authentic original CLK-01 UART bytes, SHA-256 pinned")
    p.add_argument("--csv", type=Path)
    p.add_argument("--markdown", type=Path)
    args = p.parse_args(argv)
    try:
        raw = args.uart.read_bytes().decode("utf-8", "replace")
        baseline = args.baseline_uart.read_bytes() if args.baseline_uart else None
        result = analyze(raw, args.sha, baseline)
        csv_text, md = reports(result)
        if args.csv:
            args.csv.write_text(csv_text, encoding="utf-8")
        if args.markdown:
            args.markdown.write_text(md, encoding="utf-8")
        print(csv_text, end="")
        print("CLK-02", result["status"], "CPC_CYD_NOT_COMPARABLE",
              "BASELINE_VERIFIED" if result["baseline"] else "BASELINE_MISSING")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print("CLK-02 REJECT:", str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
