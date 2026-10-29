#!/usr/bin/env python3
"""HW4-SCROLL-OPT-A0: strict cumulative UART evidence auditor (stdlib only)."""
import argparse
import json
import re
import sys
from pathlib import Path

BOUNDS = (500, 1000, 2000, 4000, 8000, 16000,
          32000, 64000, 128000, 256000, 512000, 4294967295)
PREFIX = "HW4-SCROLL-A0 "
STAGES = {"after_line", "after_rejected"}

class EvidenceError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise EvidenceError(message)

def fields(line, marker):
    tail = line.split(marker, 1)[1]
    pairs = tail.split()
    result = {}
    for item in pairs:
        require("=" in item, "malformed field " + item)
        key, value = item.split("=", 1)
        require(key and value and key not in result, "duplicate/empty key " + key)
        result[key] = value
    return result

def number(d, key):
    require(key in d and re.fullmatch(r"[0-9]+", d[key]) is not None,
            "missing or invalid " + key)
    return int(d[key])

def quantile(hist, count, percentile):
    if count == 0:
        return 0
    rank = (count * percentile + 99) // 100
    seen = 0
    for value, bound in zip(hist, BOUNDS):
        seen += value
        if seen >= rank:
            return bound
    raise EvidenceError("histogram rank unavailable")

def check_class(data, name, bytes_per_band):
    require(data.get("name") == name, "class mismatch")
    hist_str = data.get("hist", "")
    require(re.fullmatch(r"[0-9]+(,[0-9]+){11}", hist_str) is not None,
            "12 histogram bins required")
    hist = [int(item) for item in hist_str.split(",")]
    counters = ("flushes", "bands", "spi_bytes", "us_total", "min_us", "max_us",
                "p50_upper_us", "p95_upper_us", "up", "down", "reset_tagged")
    out = {key: number(data, key) for key in counters}
    out["hist"] = hist
    count = out["flushes"]
    require(sum(hist) == count, "histogram sample count mismatch")
    require(out["bands"] <= 25 * count, "more than 25 bands per flush")
    require(out["bands"] >= count, "flush without successful bands")
    require(out["spi_bytes"] == out["bands"] * bytes_per_band, "SPI byte mismatch")
    require(out["reset_tagged"] <= count, "too many tagged resets")
    require(out["p50_upper_us"] == quantile(hist, count, 50), "invalid p50")
    require(out["p95_upper_us"] == quantile(hist, count, 95), "invalid p95")
    if not count:
        require(not any(out[key] for key in
                        ("min_us", "max_us", "us_total", "up", "down", "reset_tagged")),
                "nonzero empty class")
    else:
        lo, hi = out["min_us"], out["max_us"]
        require(lo <= hi and count * lo <= out["us_total"] <= count * hi,
                "duration min/max/total inconsistent")
        first = next(i for i, n in enumerate(hist) if n)
        last = max(i for i, n in enumerate(hist) if n)
        require(lo <= BOUNDS[first] and
                (first == 0 or lo > BOUNDS[first-1]),
                "minimum outside first occupied histogram bin")
        require(hi <= BOUNDS[last] and
                (last == 0 or hi > BOUNDS[last-1]),
                "maximum outside last occupied histogram bin")
    if name == "ordinary":
        require(out["up"] == out["down"] == 0, "ordinary class contains scroll")
    else:
        require(out["up"] + out["down"] >= count, "scroll class missing scroll events")
    return out

def analyze(log, *, sha, idf, profile, spi_hz, cpu_mhz, orientation=9,
            require_bidirectional=False):
    require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "full SHA required")
    require(profile == "CONSOLE", "only CONSOLE is instrumented")
    require(spi_hz == 20000000 and cpu_mhz > 0,
            "SPI manifest must match driver LCD_CLOCK_HZ=20000000")
    require(orientation == 9, "orientation case 9 required")
    require("HW4-C2 START " in log and "HW4-C2 ORIENTATION_PASS case=9" in log,
            "boot/orientation evidence missing")
    starts = [line for line in log.splitlines() if "HW4-C2 START " in line]
    require(len(starts) == 1, "exactly one firmware boot/version required")
    boot = fields(starts[0].split(" ON_DEVICE_UNVERIFIED", 1)[0],
                  "HW4-C2 START ")
    require(boot.get("idf") == idf, "ESP-IDF manifest differs from device")
    version = boot.get("version", "")
    # Only clean 7..40 lowercase hex app versions can be verified against
    # the full expected commit SHA. Reject dirty, tag and arbitrary labels.
    require(re.fullmatch(r"[0-9a-f]{7,40}", version) is not None and
            sha.startswith(version), "unverifiable firmware app version/SHA")
    require("LCD_FAIL_STOP" not in log and "HW4-C2 FAIL " not in log and
            "MEMORY_FAIL" not in log, "hardware failure in log")
    memory = [fields(line, " DEVICE_MEMORY ") for line in log.splitlines()
              if " DEVICE_MEMORY " in line]
    require(any(m.get("stage") == "after_line" for m in memory),
            "post-command DEVICE_MEMORY evidence missing")
    for m in memory:
        require(number(m, "dma_fault") == 0 and
                number(m, "dma_timeouts") == 0 and
                m.get("lcd_error") == "ESP_OK", "DMA/LCD health failure")
        require(number(m, "heap8_free") > 0 and
                number(m, "stack_margin_bytes") > 0, "invalid heap/stack evidence")
    old, sample, classes = {}, {}, {}
    snapshots = []
    for line in log.splitlines():
        if " LCD_METRICS stage=" in line:
            d = fields(line, " LCD_METRICS ")
            require(d.get("stage") in STAGES, "invalid legacy stage")
            require(old == {}, "unpaired legacy LCD_METRICS")
            old = d
        elif PREFIX + "SAMPLE " in line:
            d = fields(line, PREFIX + "SAMPLE ")
            require(bool(old) and not sample, "orphan/duplicate sample")
            require(d.get("stage") == old.get("stage"), "stage mismatch")
            require(number(d, "schema") == 1 and
                    d.get("classes") == "cumulative", "unexpected schema")
            require(number(d, "cpu_mhz") == cpu_mhz, "CPU clock mismatch")
            require(number(d, "bytes_per_band") == 5120, "DMA band ABI changed")
            sample = d
        elif PREFIX + "CLASS " in line:
            d = fields(line, PREFIX + "CLASS ")
            require(bool(sample), "orphan class")
            require(d.get("seq") == sample.get("seq"), "seq mismatch")
            name = d.get("name")
            require(name in ("ordinary", "scroll_associated") and name not in classes,
                    "duplicate/unknown class")
            classes[name] = check_class(d, name, number(sample, "bytes_per_band"))
            if len(classes) == 2:
                seq = number(sample, "seq")
                require(seq == len(snapshots) + 1, "missing/reordered sequence")
                a, b = classes["ordinary"], classes["scroll_associated"]
                for key in ("flushes", "bands", "spi_bytes", "us_total"):
                    old_name = "repaint_us_total" if key == "us_total" else key
                    require(a[key] + b[key] == number(old, old_name),
                            "legacy/class counter contradiction: " + key)
                require(number(old, "scrolls") == number(sample, "text_scrolls"),
                        "legacy vs sample text scrolls mismatch")
                require(a["up"] + b["up"] + number(sample, "pending_up") >=
                        number(sample, "text_scrolls"), "up scroll undercount")
                require(number(sample, "pending_down") >= 0, "invalid pending count")
                require(a["reset_tagged"] + b["reset_tagged"] <=
                        number(sample, "resets"), "reset tagged > actual resets")
                snapshot = {"seq": seq, "stage": sample["stage"],
                            "resets": number(sample, "resets"),
                            "text_scrolls": number(sample, "text_scrolls"),
                            "pending_up": number(sample, "pending_up"),
                            "pending_down": number(sample, "pending_down"),
                            "ordinary": a, "scroll_associated": b}
                if snapshots:
                    prev = snapshots[-1]
                    require(snapshot["resets"] >= prev["resets"], "reset count reversed")
                    for name in ("ordinary", "scroll_associated"):
                        for key in ("flushes", "bands", "spi_bytes", "us_total",
                                    "up", "down", "reset_tagged"):
                            require(snapshot[name][key] >= prev[name][key],
                                    "cumulative counter reversed: " + name + "." + key)
                        for i in range(12):
                            require(snapshot[name]["hist"][i] >= prev[name]["hist"][i],
                                    "cumulative histogram reversed")
                    if snapshot["resets"] == prev["resets"]:
                        require(snapshot["text_scrolls"] >= prev["text_scrolls"],
                                "text scroll counter reset not reported")
                    prev_sc = prev["scroll_associated"]["up"] + prev["scroll_associated"]["down"] + prev["pending_up"] + prev["pending_down"]
                    this_sc = snapshot["scroll_associated"]["up"] + snapshot["scroll_associated"]["down"] + snapshot["pending_up"] + snapshot["pending_down"]
                    require(this_sc >= prev_sc, "scroll event total reversed")
                    delta_resets = snapshot["resets"] - prev["resets"]
                    delta_tag = sum(snapshot[n]["reset_tagged"] -
                                    prev[n]["reset_tagged"] for n in
                                    ("ordinary", "scroll_associated"))
                    require(delta_tag <= delta_resets, "unjustified reset tag delta")
                snapshots.append(snapshot)
                old, sample, classes = {}, {}, {}
    require(not old and not sample and not classes, "incomplete final snapshot")
    require(len(snapshots) >= 1, "no complete paired snapshot")
    last = snapshots[-1]
    up = last["scroll_associated"]["up"]
    down = last["scroll_associated"]["down"]
    if require_bidirectional:
        require(up >= 20 and down >= 20 and last["resets"] >= 1,
                "bidirectional 20/20 and !CLS evidence required")
        require(last["pending_up"] == last["pending_down"] == 0,
                "unflushed scroll events remain")
    return {"manifest": {"sha": sha, "app_version": version, "idf": idf,
                          "profile": profile, "spi_hz": spi_hz, "cpu_mhz": cpu_mhz,
                          "orientation": orientation, "method": "cumulative_dirty_flush",
                          "classification": "associated_not_exclusive",
                          "p50_p95": "nearest_rank_histogram_upper_bound_us"},
            "snapshots": snapshots,
            "last": {"ordinary": last["ordinary"],
                     "scroll_associated": last["scroll_associated"],
                     "scroll_up_observed": up, "scroll_down_observed": down,
                     "resets": last["resets"]}}

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("uart_log", type=Path)
    p.add_argument("--sha", required=True)
    p.add_argument("--idf", required=True)
    p.add_argument("--profile", default="CONSOLE")
    p.add_argument("--spi-hz", type=int, required=True)
    p.add_argument("--cpu-mhz", type=int, required=True)
    p.add_argument("--orientation", type=int, default=9)
    p.add_argument("--require-bidirectional", action="store_true")
    p.add_argument("--out", type=Path, help="write audited JSON")
    args = p.parse_args(argv)
    try:
        result = analyze(args.uart_log.read_text(encoding="utf-8", errors="replace"),
                         sha=args.sha, idf=args.idf, profile=args.profile,
                         spi_hz=args.spi_hz, cpu_mhz=args.cpu_mhz,
                         orientation=args.orientation,
                         require_bidirectional=args.require_bidirectional)
        if args.out:
            args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        for name in ("ordinary", "scroll_associated"):
            d = result["last"][name]
            print(f"{name}: n={d['flushes']} bands={d['bands']} bytes={d['spi_bytes']} "
                  f"min={d['min_us']} p50<={d['p50_upper_us']} "
                  f"p95<={d['p95_upper_us']} max={d['max_us']} us "
                  f"up={d['up']} down={d['down']} reset_tagged={d['reset_tagged']}")
        print("HW4-SCROLL-A0 AUDIT PASS; scroll_associated != exclusive scroll cost")
        return 0
    except (EvidenceError, OSError) as error:
        print(f"HW4-SCROLL-A0 AUDIT FAIL: {error}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
