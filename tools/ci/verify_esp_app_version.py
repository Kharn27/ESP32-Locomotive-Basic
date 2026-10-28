#!/usr/bin/env python3
"""Check actual boot app descriptor in a built ESP-IDF binary, not git HEAD.

HW4-EDIT-A-C1: default build/ after a branch switch must identify the
new source revision when ESP32 boots, not silently reuse a stale appdesc.
No external Python packages or mutations, and an exact project-name guard.
"""
import pathlib
import struct
import sys

MAGIC = struct.pack("<I", 0xABCD5432)


def boot_version(data: bytes, project: str) -> str:
    start = 0
    matches = []
    while True:
        offset = data.find(MAGIC, start)
        if offset < 0:
            break
        start = offset + len(MAGIC)
        if offset + 80 > len(data):
            continue
        version = data[offset + 16 : offset + 48].split(b"\0", 1)[0]
        name = data[offset + 48 : offset + 80].split(b"\0", 1)[0]
        if name == project.encode("ascii"):
            matches.append(version.decode("ascii"))
    if len(matches) != 1:
        raise ValueError(f"expected one {project} app descriptor, found {len(matches)}")
    return matches[0]


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: verify_esp_app_version.py APP.bin FULL_SHA PROJECT")
    binary = pathlib.Path(sys.argv[1])
    expected_sha = sys.argv[2]
    project = sys.argv[3]
    if len(expected_sha) != 40 or any(ch not in "0123456789abcdef" for ch in expected_sha):
        raise ValueError("expected an exact lowercase SHA-1")
    result = boot_version(binary.read_bytes(), project)
    print(f"PO_STANDARD_BIN_VERSION={result}")
    if not result.startswith(expected_sha[:7]):
        raise AssertionError(
            f"stale application version: {result!r}, expected source {expected_sha[:7]!r}"
        )
    print("PO_STANDARD_BOOT_SHA=PASS")


if __name__ == "__main__":
    main()
