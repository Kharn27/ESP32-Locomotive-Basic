#!/usr/bin/env python3
"""HW4-EDIT-P1: two reproducible RED->GREEN tests against real C99 sources."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "video" / "cpc_video.c"
SOURCES = [
    ROOT / "video" / "cpc_palette.c",
    ROOT / "video" / "cpc_text.c",
    ROOT / "video" / "cpc_boot.c",
    ROOT / "io" / "uart_line.c",
    ROOT / "io" / "cpc_uart_console.c",
    ROOT / "tests" / "test_hw4_edit_p1.c",
]
MUTATIONS = {
    "scroll_validity_shift": (
        "memmove(v->cell_valid, v->cell_valid + valid_shift, valid_remain);",
        "/* RED: deliberately skip E2 valid-bit scroll */",
    ),
    "pixel_invalidation": (
        "forget_cell(v, cell_index(x / 8U, y / 8U));",
        "(void)v; /* RED: deliberately omit graphics invalidation */",
    ),
}

def run(binary: Path, source: Path):
    cc = os.environ.get("CC", "cc")
    cmd = [cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-I",
           str(ROOT / "video"), "-I", str(ROOT / "io"),
           str(source), *map(str, SOURCES), "-o", str(binary)]
    subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE, text=True)
    return subprocess.run([str(binary)], cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, check=False)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.parse_args()
    original = VIDEO.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="hw4-edit-p1-mutations-") as temp:
        folder = Path(temp)
        green = run(folder / "green", VIDEO)
        if green.returncode:
            raise SystemExit("GREEN baseline failed: " + green.stderr[-1200:])
        print("GREEN: unmodified source passes test_hw4_edit_p1")
        for name, (needle, replacement) in MUTATIONS.items():
            if original.count(needle) != 1:
                raise SystemExit(f"RED fixture anchor mismatch: {name}")
            source = folder / (name + ".c")
            source.write_text(original.replace(needle, replacement),
                              encoding="utf-8")
            result = run(folder / name, source)
            if result.returncode == 0:
                raise SystemExit(f"RED NOT DETECTED: {name}")
            if "Assertion" not in result.stderr and "assertion" not in result.stderr:
                raise SystemExit(f"Unexpected RED failure for {name}: {result.stderr[-1200:]}")
            print(f"RED detected: {name} (assertion failure), GREEN baseline remains PASS")
    print("HW4-EDIT-P1 TWO MUTATIONS RED->GREEN PASS")

if __name__ == "__main__":
    main()
