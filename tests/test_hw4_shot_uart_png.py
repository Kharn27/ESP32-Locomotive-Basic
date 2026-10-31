#!/usr/bin/env python3
"""HW4-SHOT-A: compiled CpcVideo->UART emitter->P0 decoder->PNG end-to-end."""
import pathlib
import struct
import subprocess
import sys
import tempfile
import zlib

WIDTH, HEIGHT = 320, 240

def run(*cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"{cmd}: {result.returncode}: {result.stderr}\n{result.stdout}")

def pixels(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    i, raw = 8, b""
    while i < len(data):
        n = struct.unpack_from(">I", data, i)[0]
        tag = data[i + 4:i + 8]
        block = data[i + 8:i + 8 + n]
        crc = struct.unpack_from(">I", data, i + 8 + n)[0]
        assert zlib.crc32(tag + block) & 0xFFFFFFFF == crc
        i += 12 + n
        if tag == b"IHDR":
            assert struct.unpack(">IIBBBBB", block) == (WIDTH, HEIGHT, 8, 2, 0, 0, 0)
        elif tag == b"IDAT":
            raw += zlib.decompress(block)
        elif tag == b"IEND":
            assert i == len(data)
            break
    assert len(raw) == HEIGHT * (1 + 3 * WIDTH)
    assert all(raw[y*(1+3*WIDTH)] == 0 for y in range(HEIGHT))
    def at(x, y):
        p = y * (1 + WIDTH*3) + 1 + 3*x
        return tuple(raw[p:p+3])
    return at

def rejects(decoder, directory, lines, name):
    log = directory / (name + ".log")
    output = directory / (name + ".png")
    log.write_text("".join(lines), encoding="ascii")
    output.write_bytes(b"EXISTING_PNG_MUST_SURVIVE")
    done = subprocess.run([sys.executable, str(decoder), str(log),
                           "--id", "HOST_001", "--output", str(output)],
                          capture_output=True, text=True, check=False)
    assert done.returncode != 0, (name, done.stdout, done.stderr)
    assert output.read_bytes() == b"EXISTING_PNG_MUST_SURVIVE", name

def main():
    emitter = pathlib.Path(sys.argv[1])
    decoder = pathlib.Path(sys.argv[2])
    with tempfile.TemporaryDirectory(prefix="hw4-shot-a-") as directory:
        d = pathlib.Path(directory)
        log, png = d / "uart.log", d / "capture.png"
        run(str(emitter), "--emit", str(log))
        lines = log.read_text(encoding="ascii").splitlines(keepends=True)
        assert len(lines) == 242
        assert lines[0].startswith("@CYDSHOT:1|BEGIN|id=HOST_001|seq=1|w=320|h=240|pix=RGB565LE|")
        assert lines[-1].startswith("@CYDSHOT:1|DONE|id=HOST_001|crc=")
        for row, line in enumerate(lines[1:-1]):
            assert f"|n={row}|crc=" in line
            assert len(line) < 1024
        run(sys.executable, str(decoder), str(log), "--id", "HOST_001",
            "--output", str(png))
        at = pixels(png)
        assert at(0, 0) == (0, 0, 132)       # blue border
        assert at(319, 239) == (0, 0, 132)   # bottom border
        assert at(0, 20) == (0, 0, 132)      # blue paper
        assert at(16, 36) == (255, 0, 0)     # PEN 2 red
        assert at(17, 36) == (0, 255, 0)     # PEN 3 green
        assert at(40, 60) == (255, 255, 0)   # read-only cursor inverse
        assert at(39, 60) == (0, 0, 132)     # outside cursor
        # No false PNGs from corrupt/partial logs, regardless of existing file.
        rejects(decoder, d, lines[:-1], "no_done")
        rejects(decoder, d, lines[:15] + lines[16:], "missing_row")
        wrong = list(lines)
        wrong[-1] = wrong[-1].replace("|crc=", "|crc=F", 1)
        rejects(decoder, d, wrong, "bad_crc")
        wrong = list(lines)
        wrong[12] = wrong[12].replace("|id=HOST_001|", "|id=OTHER_001|", 1)
        rejects(decoder, d, wrong, "mixed_id")
        wrong = list(lines)
        wrong[0] = wrong[0].replace("pix=RGB565LE", "pix=RGB565BE", 1)
        rejects(decoder, d, wrong, "wrong_endian")
        wrong = list(lines)
        wrong[0] = wrong[0].replace("w=320", "w=319", 1)
        rejects(decoder, d, wrong, "wrong_width")
        print("HW4-SHOT-A HOST ROUNDTRIP: 320x240 pixels, CRC/atomic negatives PASS")

if __name__ == "__main__":
    main()
