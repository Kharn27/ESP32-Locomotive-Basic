#!/usr/bin/env python3
"""CLK-01 strict UART evidence checker. It never declares a physical PO PASS."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import statistics
import sys

CORPUS = Path(__file__).resolve().parents[1] / "tests/fixtures/cpc6128/clk_01_speed/manifest.json"
SCOPE = "RUN_slices_including_repaint_excluding_final_prompt"
CLASS_NAMES = {"full25", "partial", "scroll_associated"}


class Reject(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise Reject(reason)


def fields(line, tag):
    values = {}
    for token in line.split(tag, 1)[1].split():
        need("=" in token, "BROKEN_KEY_VALUE")
        key, value = token.split("=", 1)
        need(bool(key) and bool(value) and key not in values, "DUPLICATE_OR_EMPTY_FIELD")
        values[key] = value
    return values


def integer(obj, key):
    value = obj.get(key, "")
    need(re.fullmatch("[0-9]+", value) is not None, "INVALID_NUMBER_" + key)
    return int(value)


def corpus(path=CORPUS):
    obj = json.loads(path.read_text())
    need(obj["schema"] == 1 and len(obj["programs"]) == 5, "BAD_CORPUS")
    for p in obj["programs"]:
        raw = (path.parent / p["file"]).read_bytes()
        need(raw.endswith(b"\n") and b"\r" not in raw, "BAD_BASIC_SOURCE")
        need(hashlib.sha256(raw).hexdigest() == p["sha256"], "SOURCE_SHA_MISMATCH")
    return obj


def validate(run, sequence):
    need(run is not None and run["duration"] is not None and
         run["terminal"] and run["memory"] and run["summary"] and
         run["classes"] == CLASS_NAMES, "INCOMPLETE_RUN_" + str(sequence))
    need(run["seq"] == sequence, "RUN_SEQ_MISMATCH")


def analyze(raw, expected_head, programs, repetitions=3):
    need(re.fullmatch("[0-9a-f]{40}", expected_head) is not None, "HEAD_FULL_SHA_REQUIRED")
    need(repetitions >= 3, "REPETITION_COUNT_TOO_LOW")
    rows = raw.splitlines()
    starts = [row for row in rows if "HW4-C2 START " in row]
    need(len(starts) == 1, "BOOT_COUNT_NOT_ONE")
    need(starts[0].endswith(" ON_DEVICE_UNVERIFIED"), "BOOT_MARKER_MISSING")
    boot = fields(starts[0].removesuffix(" ON_DEVICE_UNVERIFIED"), "HW4-C2 START ")
    version = boot.get("version", "")
    need(re.fullmatch("[0-9a-f]{7,40}", version) is not None and
         expected_head.startswith(version), "WRONG_APP_VERSION")
    need(boot.get("idf") == "v5.5.6", "WRONG_IDF_VERSION")
    spi = [fields(row, "HW4-DISP-PROFILE BOOT ") for row in rows
           if "HW4-DISP-PROFILE BOOT " in row]
    need(len(spi) == 1 and spi[0].get("sha") == expected_head and
         spi[0].get("variant") == "SPI40" and
         integer(spi[0], "spi_request_hz") == 40000000, "WRONG_SPI_OR_HEAD")
    need(any(" LCD_METRICS " in row for row in rows), "MISSING_LCD_METRICS")
    need(not any(re.search(r"Guru Meditation|panic|Backtrace:|LCD_FAIL_STOP|HW4-C2 FAIL |MEMORY_FAIL|VIDEO_REJECT|HW4_RUN_DISPLAY_.*FAILED", row, re.I)
                 for row in rows), "FIRMWARE_FAILURE")
    result = []
    active = None
    for row in rows:
        if " DEVICE_MEMORY " in row:
            m = fields(row, " DEVICE_MEMORY ")
            need(integer(m, "dma_fault") == integer(m, "dma_timeouts") == 0
                 and m.get("lcd_error") == "ESP_OK"
                 and min(integer(m, k) for k in ("heap8_free", "heap8_largest",
                                                   "stack_margin_bytes")) > 0,
                 "UNHEALTHY_DEVICE_MEMORY")
            if m.get("stage") == "run_terminal":
                need(active is not None and active["terminal"] and
                     not active["memory"], "ORPHAN_MEMORY")
                active["memory"] = True
        if "HW4-RUN-B RUN_START " in row:
            if active is not None:
                validate(active, len(result) + 1)
                result.append(active)
            d = fields(row, "HW4-RUN-B RUN_START ")
            need(d.get("sha") == expected_head and
                 d.get("budget") == "none" and integer(d, "quantum") == 8,
                 "BAD_RUN_START")
            active = dict(duration=None, terminal=False, memory=False,
                          summary=False, classes=set(), seq=None)
        elif "HW4-DISP-PROFILE RUN_DURATION " in row:
            need(active is not None and active["duration"] is None, "ORPHAN_DURATION")
            d = fields(row, "HW4-DISP-PROFILE RUN_DURATION ")
            need(d.get("scope") == SCOPE, "INCOMPATIBLE_RUN_SCOPE")
            active["seq"] = integer(d, "run")
            active["duration"] = integer(d, "core_us")
            need(active["duration"] > 0, "ZERO_DURATION")
        elif "HW4-RUN-B RUN_TERMINAL " in row:
            need(active is not None and active["duration"] is not None
                 and not active["terminal"], "ORPHAN_TERMINAL")
            d = fields(row, "HW4-RUN-B RUN_TERMINAL ")
            need(d.get("sha") == expected_head and integer(d, "state") == 5
                 and d.get("break_source") == "none"
                 and integer(d, "stop_calls") == 0
                 and integer(d, "overflow_input_lines") == 0
                 and integer(d, "ignored_input_lines") == 0
                 and integer(d, "steps") > 0, "RUN_NOT_FINISHED_NORMALLY")
            active["terminal"] = True
        elif "HW4-DISP-PROFILE SUMMARY " in row and "stage=run_terminal_after_prompt" in row:
            need(active is not None and active["terminal"] and not active["summary"], "BAD_SUMMARY")
            d = fields(row, "HW4-DISP-PROFILE SUMMARY ")
            need(integer(d, "run") == active["seq"], "SUMMARY_WRONG_RUN")
            active["summary"] = True
        elif "HW4-DISP-PROFILE CLASS " in row and "stage=run_terminal_after_prompt" in row:
            need(active is not None and active["terminal"], "ORPHAN_CLASS")
            d = fields(row, "HW4-DISP-PROFILE CLASS ")
            name = d.get("name")
            need(name in CLASS_NAMES and name not in active["classes"] and
                 integer(d, "run") == active["seq"], "DUPLICATE_OR_BAD_CLASS")
            for key in ("n", "wall_us", "render_pack_us", "sem_wait_us"):
                integer(d, key)
            active["classes"].add(name)
    validate(active, len(result) + 1)
    result.append(active)
    expected = len(programs["programs"]) * repetitions
    need(len(result) == expected, "RUN_COUNT_%d_EXPECTED_%d" % (len(result), expected))
    aggregate = []
    for i, p in enumerate(programs["programs"]):
        selected = [r["duration"] for r in result[i*repetitions:(i+1)*repetitions]]
        aggregate.append({"scenario": p["id"], "profile": p["profile"],
                          "n": len(selected), "min_us": min(selected),
                          "median_us": statistics.median(selected), "max_us": max(selected),
                          "comparison": "NOT_COMPARABLE"})
    return {"sha": expected_head, "runs": aggregate, "scope": SCOPE,
            "status": "UART_CANDIDATE_ON_DEVICE_PO_REVIEW_REQUIRED"}


def format_report(data):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    keys = ("scenario", "profile", "n", "min_us", "median_us", "max_us", "comparison")
    writer.writerow(keys)
    for row in data["runs"]:
        writer.writerow([row[k] for k in keys])
    md = ["# CLK-01 UART measurement candidate", "",
          "HEAD: " + data["sha"], "", "Scope: " + data["scope"], "",
          "| Scenario | n | min µs | median µs | max µs | ratio |",
          "|---|---:|---:|---:|---:|---|"]
    for row in data["runs"]:
        md.append("| %s | %d | %d | %g | %d | NOT_COMPARABLE |" %
                  (row["scenario"], row["n"], row["min_us"],
                   row["median_us"], row["max_us"]))
    md += ["", "Post-prompt CLASS telemetry cannot be subtracted as BASIC CPU time.",
           "No CPC/CYD ratio until independent CPC speed and aligned-window review.", ""]
    return out.getvalue(), "\n".join(md)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("uart", type=Path)
    p.add_argument("--sha", required=True)
    p.add_argument("--csv", type=Path)
    p.add_argument("--markdown", type=Path)
    a = p.parse_args(argv)
    try:
        result = analyze(a.uart.read_bytes().decode("utf-8", "replace"), a.sha, corpus())
        csv_text, md_text = format_report(result)
        if a.csv:
            a.csv.write_text(csv_text, encoding="utf-8")
        if a.markdown:
            a.markdown.write_text(md_text, encoding="utf-8")
        print(csv_text, end="")
        print("CLK-01 NOT_COMPARABLE - candidate only; not PO acceptance")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print("CLK-01 REJECT: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
