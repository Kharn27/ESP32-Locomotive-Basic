#!/usr/bin/env python3
"""HW4-RUN-BREAK-B: PO-only UART0 proof. No ESP-IDF, ROM or CYD simulation.
Install pyserial on PC. Own the serial port exclusively (not idf.py monitor).
Uses only the console's existing log names and a real CYD firmware flash.
"""
import argparse
import re
import sys
import time
import serial

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--log", default="hw4-run-break-b-po-uart.log")
    ap.add_argument("--timeout", type=float, default=600.0)
    args = ap.parse_args()
    if args.timeout <= 0:
        ap.error("--timeout must be positive")
    with serial.Serial(args.port, 115200, timeout=0.2, write_timeout=3) as uart:
        # No second reader/monitor, no reset_input_buffer during RUN.
        with open(args.log, "w", encoding="utf-8") as log:
            def record(buf):
                text = buf.decode("utf-8", errors="replace")
                log.write(text)
                log.flush()
                sys.stdout.write(text)
                sys.stdout.flush()
                return text
            def send(data):
                uart.write(data)
                uart.flush()
                print(f"\nPO_TX hex={data.hex()} time_ns={time.monotonic_ns()}\n",
                      file=log, flush=True)
            # Physical startup may already have elapsed. Program preparation
            # is serialized with modest settling delays, no concurrent SHOT.
            for line in (b"NEW\r", b'10 PEN 3:PRINT "SCROLL GREEN"\r',
                         b"20 GOTO 10\r"):
                send(line)
                time.sleep(0.35)
                record(uart.read(4096))
            send(b"RUN\r")
            started = time.monotonic()
            deadline = started + args.timeout
            text_tail = ""
            observed = 0
            while time.monotonic() < deadline:
                text_tail = (text_tail + record(uart.read(4096)))[-12000:]
                for match in re.finditer(
                    r"HW4-RUN-B YIELD quanta=(\d+) steps=(\d+)",
                    text_tail,
                ):
                    observed = max(observed, int(match.group(2)))
                if observed > 4096:
                    break
            if observed <= 4096:
                raise SystemExit("PO FAIL: no UART proof beyond 4096 steps")
            # Command deliberately fragmented across two serial writes.
            send(b"!Br")
            time.sleep(0.25)
            send(b"eAk\r\n")
            requested = time.monotonic()
            observed_terminal = False
            terminal_tail = ""
            while time.monotonic() < deadline:
                terminal_tail = (terminal_tail + record(uart.read(4096)))[-12000:]
                if "HW4-RUN-B RUN_TERMINAL state=4" in terminal_tail and \
                   "break_source=UART_CR" in terminal_tail and \
                   "HW4-READY-A READY_POLICY transition=RUN_RETURN emitted=1" in terminal_tail:
                    observed_terminal = True
                    break
            if not observed_terminal:
                raise SystemExit("PO FAIL: missing BREAK terminal/Ready log")
            print(f"\nPO PASS_CANDIDATE steps={observed} "
                  f"break_wall_ms={(time.monotonic()-requested)*1000:.0f}\n",
                  file=log, flush=True)
            # This is after the RUN terminal only. On-screen verification,
            # no late PRINT and a *single* Ready still require the PO.
            time.sleep(0.5)
            send(b"LIST\r")
            time.sleep(0.7)
            record(uart.read(4096))
            send(b"NEW\r")
            time.sleep(0.5)
            record(uart.read(4096))
    print(f"Serial transcript saved: {args.log}")
    print("PO: photos + PRINT stop + Ready count + DMA/heap/pile review mandatory.")

if __name__ == "__main__":
    main()
