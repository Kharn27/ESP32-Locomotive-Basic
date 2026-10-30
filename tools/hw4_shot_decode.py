#!/usr/bin/env python3
"""HW4-SHOT-P0: strict ASCII UART screenshot v1 -> RGB PNG (host only).

No firmware actions or external Python dependencies.  All input is untrusted.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import zlib

PREFIX = "@CYDSHOT:1|"
FAMILY = "@CYDSHOT:"
WIDTH = 320
HEIGHT = 240
ROW_BYTES = WIDTH * 2
MAX_LINE_CHARS = 1024  # includes monitor decoration and record newline
MAX_ID = 32
MAX_FIRMWARE = 48
MAX_ORIENTATION = 24
_MAX_SEQUENCE = (1 << 32) - 1
_SIG = b"\x89PNG\r\n\x1a\n"
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,32}\Z", re.ASCII)
_FW_RE = re.compile(r"[A-Za-z0-9_.-]{1,48}\Z", re.ASCII)
_ORIENT_RE = re.compile(r"[A-Za-z0-9_-]{1,24}\Z", re.ASCII)
_SHA_RE = re.compile(r"[0-9a-f]{7,40}\Z", re.ASCII)
_CRC_RE = re.compile(r"[0-9A-F]{8}\Z", re.ASCII)
_MONITOR_RE = re.compile(
    r"^(?:\x1b\[[0-9;]*m)*(?:\[[0-9 :.,+-]{1,64}\]\s*)?"
    r"(?:[IWEVD] \([0-9]{1,12}\) [A-Za-z0-9_.-]{1,48}: )?"
)


class ShotError(ValueError):
    """Rejected capture; no image may be published."""


def _fields(record: str, kind: str, keys: tuple[str, ...]) -> dict[str, str]:
    pieces = record.split("|")
    if len(pieces) != len(keys) + 1 or pieces[0] != kind:
        raise ShotError(f"invalid {kind} field count or ordering")
    result = {}
    for piece, expected in zip(pieces[1:], keys):
        name, sep, value = piece.partition("=")
        if sep != "=" or name != expected or not value:
            raise ShotError(f"invalid {kind} field {expected}")
        result[name] = value
    return result


def _id(value: str) -> str:
    if not _ID_RE.fullmatch(value):
        raise ShotError("invalid capture id")
    return value


def _crc(value: str) -> int:
    if not _CRC_RE.fullmatch(value):
        raise ShotError("CRC must be eight uppercase hexadecimal digits")
    return int(value, 16)


def _begin(record: str) -> dict[str, str | int]:
    data = _fields(record, "BEGIN", ("id", "seq", "w", "h", "pix", "orient", "fw", "sha"))
    _id(data["id"])
    seq = data["seq"]
    if not seq.isascii() or not seq.isdecimal() or (len(seq) > 1 and seq[0] == "0"):
        raise ShotError("invalid decimal capture sequence")
    if int(seq) > _MAX_SEQUENCE:
        raise ShotError("capture sequence out of range")
    if (data["w"], data["h"], data["pix"]) != ("320", "240", "RGB565LE"):
        raise ShotError("unsupported dimensions or pixel format / endianness")
    if not _ORIENT_RE.fullmatch(data["orient"]):
        raise ShotError("invalid orientation metadata")
    if not _FW_RE.fullmatch(data["fw"]):
        raise ShotError("invalid firmware version")
    if not _SHA_RE.fullmatch(data["sha"]):
        raise ShotError("invalid firmware SHA")
    return {**data, "seq": int(seq)}


def _row(record: str, expected_id: str, expected_number: int) -> bytes:
    data = _fields(record, "ROW", ("id", "n", "crc", "b64"))
    if _id(data["id"]) != expected_id:
        raise ShotError("interleaved capture id in ROW")
    number = data["n"]
    if not number.isascii() or not number.isdecimal() or (len(number) > 1 and number[0] == "0"):
        raise ShotError("invalid ROW index")
    if int(number) != expected_number:
        raise ShotError(f"ROW out of order: expected {expected_number}, got {number}")
    # 640 bytes -> exactly 856 base64 chars. No whitespace, extra padding or alternative spelling.
    token = data["b64"]
    if len(token) != 856 or not token.isascii():
        raise ShotError("incorrect ROW base64 length")
    try:
        raw = base64.b64decode(token, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ShotError("invalid ROW base64 encoding") from exc
    if len(raw) != ROW_BYTES or base64.b64encode(raw).decode("ascii") != token:
        raise ShotError("non-canonical ROW base64 or wrong decoded size")
    if zlib.crc32(raw) & 0xFFFFFFFF != _crc(data["crc"]):
        raise ShotError(f"ROW {expected_number} CRC mismatch")
    return raw


def _transport_line(line: str, lineno: int) -> str | None:
    if len(line) > MAX_LINE_CHARS:
        raise ShotError(f"line {lineno}: transport line exceeds {MAX_LINE_CHARS} chars")
    line = line.rstrip("\r\n")
    # Strip ONLY known monitor decorations, not arbitrary substrings containing a marker.
    prefix = _MONITOR_RE.match(line)
    record = line[prefix.end():] if prefix else line
    if not record.startswith(FAMILY):
        return None
    if not record.startswith(PREFIX):
        raise ShotError(f"line {lineno}: unsupported or malformed screenshot protocol version")
    if not record.isascii():
        raise ShotError(f"line {lineno}: non-ASCII frame record")
    return record[len(PREFIX):]


def _lines(source):
    """Bound input line allocations (also for unrelated monitor noise)."""
    lineno = 0
    while True:
        line = source.readline(MAX_LINE_CHARS + 1)
        if not line:
            break
        lineno += 1
        if len(line) > MAX_LINE_CHARS:
            raise ShotError(f"line {lineno}: transport line too long")
        yield lineno, line


def decode(source, capture_id: str | None = None) -> tuple[dict, bytes]:
    """Validate all recognized sessions; return metadata and a single RGB565LE frame.

    If multiple complete captures are in the log, --id is mandatory. Duplicate
    IDs or any interleaving are errors even when another capture was requested.
    """
    if capture_id is not None:
        _id(capture_id)
    current = None
    seen: set[str] = set()
    selected = None
    for lineno, line in _lines(source):
        record = _transport_line(line, lineno)
        if record is None:
            continue  # unrelated UART log line
        kind, _, _ = record.partition("|")
        try:
            if kind == "BEGIN":
                if current is not None:
                    raise ShotError("nested/interleaved BEGIN before DONE")
                meta = _begin(record)
                if meta["id"] in seen:
                    raise ShotError("repeated capture id in log")
                seen.add(meta["id"])
                current = {"meta": meta, "rows": [], "crc": 0}
            elif kind == "ROW":
                if current is None:
                    raise ShotError("ROW without BEGIN")
                if len(current["rows"]) >= HEIGHT:
                    raise ShotError("excess ROW records")
                raw = _row(record, current["meta"]["id"], len(current["rows"]))
                current["rows"].append(raw)
                current["crc"] = zlib.crc32(raw, current["crc"]) & 0xFFFFFFFF
            elif kind == "DONE":
                data = _fields(record, "DONE", ("id", "crc"))
                if current is None:
                    raise ShotError("DONE without BEGIN or repeated DONE")
                if _id(data["id"]) != current["meta"]["id"]:
                    raise ShotError("DONE capture id mismatch")
                if len(current["rows"]) != HEIGHT:
                    raise ShotError(f"incomplete capture: {len(current['rows'])}/{HEIGHT} ROWs")
                if current["crc"] != _crc(data["crc"]):
                    raise ShotError("global frame CRC mismatch")
                meta = current["meta"]
                if capture_id is None or meta["id"] == capture_id:
                    if selected is not None:
                        raise ShotError("multiple captures: select exactly one --id")
                    selected = (meta, b"".join(current["rows"]))
                current = None
            elif kind == "ABORT":
                data = _fields(record, "ABORT", ("id", "reason"))
                if current is None or _id(data["id"]) != current["meta"]["id"]:
                    raise ShotError("unmatched ABORT")
                if not _ORIENT_RE.fullmatch(data["reason"]):
                    raise ShotError("invalid ABORT reason")
                raise ShotError(f"capture {data['id']} explicitly aborted: {data['reason']}")
            else:
                raise ShotError(f"unknown screenshot record {kind!r}")
        except ShotError as exc:
            raise ShotError(f"line {lineno}: {exc}") from exc
    if current is not None:
        raise ShotError(f"truncated capture {current['meta']['id']}: no DONE")
    if selected is None:
        raise ShotError("no complete capture found for requested id")
    return selected


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_from_rgb565le(frame: bytes) -> bytes:
    """PNG RGB8 type=2. Never swap or rotate rows/pixels from the wire."""
    if len(frame) != HEIGHT * ROW_BYTES:
        raise ShotError("invalid full RGB565LE frame length")
    scan = bytearray()
    for row in range(HEIGHT):
        scan.append(0)  # PNG filter method: None
        offset = row * ROW_BYTES
        for p in range(offset, offset + ROW_BYTES, 2):
            value = frame[p] | frame[p + 1] << 8
            r5, g6, b5 = (value >> 11) & 31, (value >> 5) & 63, value & 31
            scan.extend(((r5 << 3) | (r5 >> 2),
                         (g6 << 2) | (g6 >> 4),
                         (b5 << 3) | (b5 >> 2)))
    ihdr = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return _SIG + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(scan), 9)) + _chunk(b"IEND", b"")


def atomic_write(path: Path, image: bytes) -> None:
    """Write in same directory then atomic rename; leave existing output intact on errors."""
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".hw4-shot-", suffix=".tmp",
                                         dir=path.parent, delete=False) as f:
            temp = Path(f.name)
            f.write(image)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        temp = None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="HW4-SHOT-P0: verified UART RGB565LE -> PNG (host-only)")
    ap.add_argument("log", nargs="?", default="-", help="UART log path; '-' for stdin (default)")
    ap.add_argument("--id", dest="capture_id", help="exact capture ID if log has multiple captures")
    ap.add_argument("--output", "-o", required=True, type=Path, help="result PNG; written atomically on success")
    args = ap.parse_args(argv)
    try:
        if args.log == "-":
            meta, frame = decode(sys.stdin, args.capture_id)
        else:
            with open(args.log, "r", encoding="utf-8", errors="replace", newline="") as src:
                meta, frame = decode(src, args.capture_id)
        image = png_from_rgb565le(frame)
        atomic_write(args.output, image)
    except (ShotError, OSError) as exc:
        print(f"HW4-SHOT-P0 ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"HW4-SHOT-P0: HOST decoded (input provenance unverified) id={meta['id']} seq={meta['seq']} "
          f"{WIDTH}x{HEIGHT} RGB565LE -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
