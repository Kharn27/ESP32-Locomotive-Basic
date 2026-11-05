#!/usr/bin/env python3
"""CLK-01 PO-only serial capture: 5 programs x 3 RUN; not automatic PO approval.

Run ONLY after GO TEST PILOTAGE. Exclusive UART0 ownership; do not run monitor.
Raw file contains received device bytes only; TX events go to a separate sidecar.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from clk_01_uart import analyze, corpus, format_report


def local_head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                   text=True).strip()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--go-test-pilotage", action="store_true",
                   help="explicit confirmation that Pilotage authorized physical tests")
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--sha", required=True, help="exact SHA of flashed firmware")
    p.add_argument("--raw", type=Path, default=Path("clk01-uart-raw.log"))
    p.add_argument("--timeout", type=float, default=120.0)
    args = p.parse_args(argv)
    if not args.go_test_pilotage:
        p.error("GO TEST PILOTAGE required; never run hardware capture otherwise")
    if args.sha != local_head():
        p.error("checkout SHA does not match --sha; flash exactly this HEAD")
    if args.timeout <= 0:
        p.error("timeout must be positive")
    program_manifest = corpus()
    raw_path = args.raw.resolve()
    sidecar = raw_path.with_suffix(".tx.jsonl")
    if raw_path.exists() or sidecar.exists():
        p.error("refusing to overwrite raw UART or TX sidecar")
    try:
        import serial
    except ImportError as e:
        p.error("pyserial required (python3 -m pip install pyserial): " + str(e))
    tx_events = []
    try:
        with serial.Serial(args.port, baudrate=115200, timeout=0.1,
                           write_timeout=5) as uart, raw_path.open("wb") as raw:
            tail = ""
            def read_once():
                nonlocal tail
                data = uart.read(8192)
                if data:
                    raw.write(data)
                    raw.flush()
                    tail = (tail + data.decode("utf-8", "replace"))[-25000:]
                return data

            def wait_for(marker, seconds=None):
                limit = time.monotonic() + (seconds or args.timeout)
                while time.monotonic() < limit:
                    read_once()
                    if marker in tail:
                        return
                    if "Guru Meditation" in tail or "HW4-C2 FAIL " in tail:
                        raise RuntimeError("FIRMWARE_ERROR_DURING_CAPTURE")
                raise RuntimeError("UART_TIMEOUT waiting for " + marker)

            print("PO: press the CYD RESET button NOW to capture one complete boot.",
                  flush=True)
            wait_for("HW4-C2 UART_READY", seconds=30)
            if "HW4-C2 START " not in tail:
                raise RuntimeError("NO_FULL_BOOT_START_IN_RAW_LOG")

            def submit(line, marker, seconds=None):
                nonlocal tail
                tail = ""
                packet = line.encode("ascii") + b"\r"
                tx_events.append({"utc": datetime.now(timezone.utc).isoformat(),
                                  "command": line, "payload_hex": packet.hex()})
                uart.write(packet)
                uart.flush()
                wait_for(marker, seconds=seconds)

            for spec in program_manifest["programs"]:
                print("PO scenario", spec["id"], flush=True)
                submit("NEW", "LCD_METRICS stage=after_line")
                for row in (Path(program_manifest_path()).parent /
                            spec["file"]).read_text(encoding="ascii").splitlines():
                    submit(row, "LCD_METRICS stage=after_line")
                for attempt in range(1, 4):
                    sequence = (program_manifest["programs"].index(spec) * 3 + attempt)
                    print("PO RUN", spec["id"], attempt, "sequence", sequence,
                          flush=True)
                    # Screen-only reset OUTSIDE timed RUN, equivalent to CPC direct CLS.
                    submit("!CLS", "LCD_METRICS stage=after_line")
                    submit("RUN",
                           "SUMMARY run=%d stage=run_terminal_after_prompt" % sequence,
                           seconds=args.timeout)
            # Flush trailing telemetry bytes without injecting a command.
            stop = time.monotonic() + 0.7
            while time.monotonic() < stop:
                read_once()
        sidecar.write_text("".join(json.dumps(ev) + "\n" for ev in tx_events),
                           encoding="utf-8")
        data = raw_path.read_bytes()
        verified = analyze(data.decode("utf-8", "replace"),
                           args.sha, program_manifest)
        table, md = format_report(verified)
        raw_path.with_suffix(".csv").write_text(table, encoding="utf-8")
        raw_path.with_suffix(".md").write_text(md, encoding="utf-8")
        print("CLK-01 UART captured, parse candidate accepted. PO must review.")
        print("RAW_SHA256", hashlib.sha256(data).hexdigest())
        print(table)
    except (RuntimeError, OSError, ValueError) as err:
        if tx_events and not sidecar.exists():
            sidecar.write_text("".join(json.dumps(ev) + "\n" for ev in tx_events),
                               encoding="utf-8")
        print("CLK-01 UART FAIL:", err, file=sys.stderr)
        print("Keep partial RAW UART and TX sidecar for Pilotage investigation.",
              file=sys.stderr)
        return 2
    return 0


def program_manifest_path():
    return Path(__file__).resolve().parents[1] / "tests/fixtures/cpc6128/clk_01_speed/manifest.json"


if __name__ == "__main__":
    sys.exit(main())
