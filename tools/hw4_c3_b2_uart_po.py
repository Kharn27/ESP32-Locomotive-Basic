#!/usr/bin/env python3
"""HW4-C3-B2 PO UART scenarios; real hardware only when --port is supplied.

Do not use at the same time as 'idf.py monitor' on the same serial device.
Does not evaluate TFT appearance and cannot report ON_DEVICE_PASS itself.
"""
import argparse
from pathlib import Path
import sys
import time

def commands():
    result = [("!CLS", 0.4)]
    for n in range(1, 27):
        result.append((f"{n*10} PRINT 7", 0.15))
    result += [("LIST", 1.1), ("LIST", 1.1)]
    for n in range(27, 33):
        result.append((f"{n*10} PRINT 7", 0.15))
    result += [("LIST", 1.1), ("LIST", 1.1), ("!CLS", 0.4),
               ("LIST", 1.1), ("RUN", 1.4),
               ("NEW", 0.5), ("LIST", 0.5), ("!CLS", 0.5)]
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="/dev/ttyUSB0 (exclusive, stop idf.py monitor)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--log", type=Path, help="UART diagnostics captured during run")
    parser.add_argument("--dry-run", action="store_true", help="print commands only")
    parser.add_argument("--analyze-log", type=Path, help="read existing C1 UART telemetry offline, no serial port")
    args = parser.parse_args()
    plan = commands()
    if args.analyze_log:
        # Analysis never opens the CYD. Read telemetry from a previous capture.
        raw = args.analyze_log.read_bytes().decode("utf-8", errors="replace")
        rows = [line.strip() for line in raw.splitlines()
                if "HW4-C3-B2-C1 LCD_METRICS " in line]
        if not rows:
            parser.error("no B2-C1 LCD_METRICS in log (wrong firmware or empty capture)")
        for index in (0, len(rows) - 1):
            if index == 0 or len(rows) > 1:
                print(("FIRST: " if index == 0 else "LAST: ") + rows[index])
        print("These are cumulative device measurements, not a PO visual PASS.")
        return
    if args.dry_run:
        for source, delay in plan:
            print(f"{source}  # wait {delay:g}s")
        return
    if not args.port or not args.log:
        parser.error("--port and --log are mandatory for real serial I/O")
    try:
        import serial  # pyserial, no other device or web access
    except ImportError:
        parser.error("pyserial required: python3 -m pip install pyserial")
    if args.log.exists():
        parser.error("refusing to overwrite an existing hardware log")
    with serial.Serial(args.port, baudrate=args.baud, timeout=0.15,
                       write_timeout=3.0) as uart, args.log.open("wb") as capture:
        for source, delay in plan:
            print(f">> {source}", flush=True)
            uart.write(source.encode("ascii") + b"\r")
            uart.flush()
            time.sleep(delay)
            # Raw UART log, including unsolicited diagnostics and errors.
            while uart.in_waiting:
                capture.write(uart.read(min(uart.in_waiting, 4096)))
            capture.flush()
        time.sleep(0.3)
        while uart.in_waiting:
            capture.write(uart.read(min(uart.in_waiting, 4096)))
    print(f"UART log: {args.log}. Inspect CYD TFT yourself; this is not a PASS assertion.")

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f"UART PO test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
