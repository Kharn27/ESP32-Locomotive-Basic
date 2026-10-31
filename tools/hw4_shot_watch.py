#!/usr/bin/env python3
"""Live, fail-closed PNG extraction from a util-linux script -f UART log.

Keeps the UART journal untouched; reuses the approved P0 decoder.
Only complete, CRC-validated captures become images.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import signal
import sys
import time

from hw4_shot_decode import (
    PREFIX, FAMILY, ShotError, _transport_line,
    decode, png_from_rgb565le, atomic_write,
)

MAX_RECORDS = 242
MAX_RAW_LINE_BYTES = 4096
POLL_SECONDS = 0.10
_stop = False


def request_stop(_signum: int, _frame: object) -> None:
    global _stop
    _stop = True


class Watcher:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.records: list[str] = []
        self.active = False
        self.count = 0
        self.bad = 0

    def reject(self, reason: str) -> None:
        self.bad += 1
        print(f"[SHOT][REJECT] {reason}", flush=True)
        self.active = False
        self.records.clear()

    def feed(self, raw: bytes) -> None:
        if len(raw) > MAX_RAW_LINE_BYTES:
            if self.active:
                self.reject("UART line too long")
            return
        line = raw.decode("utf-8", errors="replace")
        try:
            record = _transport_line(line, 0)
        except ShotError as exc:
            if self.active or FAMILY in line:
                self.reject(f"malformed transport: {exc}")
            return
        if record is None:
            if self.active and FAMILY in line:
                self.reject("unrecognized/malformed screenshot framing")
            return

        kind = record.split("|", 1)[0]
        if kind == "BEGIN":
            if self.active:
                self.reject("nested BEGIN before DONE")
            self.active = True
            self.records = [PREFIX + record + "\n"]
            return
        if not self.active:
            if kind in ("DONE", "ABORT"):
                print(f"[SHOT][IGNORE] {kind} without BEGIN", flush=True)
            return
        self.records.append(PREFIX + record + "\n")
        if len(self.records) > MAX_RECORDS:
            self.reject("too many records before DONE")
            return
        if kind == "ABORT":
            self.reject("device reported ABORT")
            return
        if kind != "DONE":
            return

        try:
            metadata, frame = decode(io.StringIO("".join(self.records)))
            png = png_from_rgb565le(frame)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            stem = f"cyd-{time.strftime('%Y%m%d-%H%M%S')}-{metadata['id']}-{time.time_ns()}"
            target = self.output_dir / f"{stem}.png"
            if target.exists():
                raise ShotError("output already exists")
            atomic_write(target, png)
            self.count += 1
            print(f"[SHOT][PNG] {target} (320x240, CRC OK, sha={metadata['sha']})", flush=True)
        except (ShotError, OSError) as exc:
            self.reject(str(exc))
            return
        self.active = False
        self.records.clear()


def watch(log: Path, output_dir: Path) -> int:
    watcher = Watcher(output_dir)
    pending = bytearray()
    oversized = False
    while not log.exists() and not _stop:
        time.sleep(POLL_SECONDS)
    if not log.exists():
        return 0

    with log.open("rb", buffering=0) as src:
        while True:
            block = src.read(16384)
            if block:
                for b in block:
                    if b == 10:
                        if oversized:
                            if watcher.active:
                                watcher.reject("oversized or truncated UART line")
                        else:
                            watcher.feed(bytes(pending) + b"\n")
                        pending.clear()
                        oversized = False
                    elif not oversized:
                        if len(pending) >= MAX_RAW_LINE_BYTES:
                            oversized = True
                            pending.clear()
                        else:
                            pending.append(b)
            elif _stop:
                break
            else:
                time.sleep(POLL_SECONDS)
    if watcher.active:
        watcher.reject("monitor ended before DONE")
    print(f"[SHOT][SUMMARY] PNG={watcher.count} rejected={watcher.bad}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live UART CYDSHOT to PNG watcher")
    parser.add_argument("log", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    return watch(args.log, args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
