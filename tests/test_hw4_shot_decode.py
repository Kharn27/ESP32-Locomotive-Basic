#!/usr/bin/env python3
"""HW4-SHOT-P0 OFFLINE TEST_SYNTHETIC frames; NOT device evidence."""
from __future__ import annotations

import base64
import copy
import importlib.util
import io
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/hw4_shot_decode.py"
spec = importlib.util.spec_from_file_location("hw4_shot_decode", TOOL)
shot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shot)


def pixel565(x, y):
    """TEST_SYNTHETIC, deterministic borders and corner/centre colors."""
    if x == 0 or x == 319 or y == 0 or y == 239:
        if x == 319 and y == 239:
            return 0xFFE0   # yellow lower right wins over border
        if x == 0 and y == 0:
            return 0x001F   # blue upper left
        return 0xFFFF       # white border
    if (x, y) == (160, 120):
        return 0xF800       # red centre
    if (x, y) == (161, 120):
        return 0x07E0       # green centre neighbour
    if (x, y) == (162, 120):
        return 0x7BEF       # nontrivial channel expansion
    return 0x001F           # blue background


def synthetic_lines(capture_id="TEST_SCREEN_001", seq=7, width=320, height=240,
                    fmt="RGB565LE", orientation="LCD10_UNVERIFIED", firmware="TEST_SYNTHETIC",
                    sha="0123456789abcdef0123456789abcdef01234567", monitor=False):
    begin = (f"{shot.PREFIX}BEGIN|id={capture_id}|seq={seq}|w={width}|h={height}"
             f"|pix={fmt}|orient={orientation}|fw={firmware}|sha={sha}")
    lines = [begin]
    full_crc = 0
    for y in range(shot.HEIGHT):
        raw = b"".join(struct.pack("<H", pixel565(x, y)) for x in range(shot.WIDTH))
        crc = zlib.crc32(raw) & 0xFFFFFFFF
        full_crc = zlib.crc32(raw, full_crc) & 0xFFFFFFFF
        lines.append(f"{shot.PREFIX}ROW|id={capture_id}|n={y}|crc={crc:08X}"
                     f"|b64={base64.b64encode(raw).decode('ascii')}")
    lines.append(f"{shot.PREFIX}DONE|id={capture_id}|crc={full_crc:08X}")
    if monitor:
        lines = [f"I (2016) screenshot: {line}" for line in lines]
    return lines


def text_lines(lines):
    return io.StringIO("\n".join(lines) + "\n")


def corrupt_line(lines, idx, new_line):
    corrupted = list(lines)
    corrupted[idx] = new_line
    return corrupted


def independently_verify_png(data):
    """Independent PNG verifier (no call to shot._chunk/png_from_rgb565le)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("PNG signature")
    ptr = 8
    chunks = []
    while ptr < len(data):
        length = struct.unpack_from(">I", data, ptr)[0]
        name = data[ptr + 4:ptr + 8]
        payload = data[ptr + 8:ptr + 8 + length]
        crc = struct.unpack_from(">I", data, ptr + 8 + length)[0]
        if crc != zlib.crc32(name + payload) & 0xFFFFFFFF:
            raise AssertionError("PNG chunk CRC invalid")
        chunks.append((name, payload))
        ptr += length + 12
    if ptr != len(data):
        raise AssertionError("trailing PNG bytes")
    if [c[0] for c in chunks] != [b"IHDR", b"IDAT", b"IEND"]:
        raise AssertionError("unexpected PNG structure")
    if chunks[0][1] != struct.pack(">IIBBBBB", 320, 240, 8, 2, 0, 0, 0):
        raise AssertionError("wrong PNG IHDR")
    if chunks[-1][1]:
        raise AssertionError("nonempty PNG IEND")
    raw = zlib.decompress(chunks[1][1])
    if len(raw) != 240 * (1 + 320 * 3):
        raise AssertionError("wrong PNG decompressed size")
    pixels = []
    for y in range(240):
        row = raw[y * 961:(y + 1) * 961]
        if row[0] != 0:
            raise AssertionError("nonzero PNG filter")
        pixels.append(row[1:])
    return pixels


class HW4ShotP0(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = synthetic_lines()

    def bad(self, lines, capture_id=None):
        with self.assertRaises(shot.ShotError):
            shot.decode(text_lines(lines), capture_id)

    def test_01_valid_240_rows_and_metadata(self):
        meta, pixels = shot.decode(text_lines(self.lines))
        self.assertEqual((meta["id"], meta["seq"], meta["pix"]),
                         ("TEST_SCREEN_001", 7, "RGB565LE"))
        self.assertEqual(len(pixels), 320 * 240 * 2)
        self.assertEqual(pixels[:2], b"\x1f\x00")
        self.assertEqual(pixels[-2:], b"\xe0\xff")

    def test_02_independent_png_crc_ihdr_idat_iend_and_all_pixels(self):
        _, frame = shot.decode(text_lines(self.lines))
        rows = independently_verify_png(shot.png_from_rgb565le(frame))
        for y in range(240):
            for x in range(320):
                v = pixel565(x, y)
                expected = bytes(((((v >> 11) & 31) << 3) | ((v >> 11) & 31) >> 2,
                                  (((v >> 5) & 63) << 2) | ((v >> 5) & 63) >> 4,
                                  ((v & 31) << 3) | ((v & 31) >> 2)))
                self.assertEqual(rows[y][3 * x:3 * x + 3], expected, (x, y))

    def test_03_named_blue_yellow_red_green_and_white_border(self):
        _, raw = shot.decode(text_lines(self.lines))
        rows = independently_verify_png(shot.png_from_rgb565le(raw))
        self.assertEqual(rows[0][:3], b"\x00\x00\xff")
        self.assertEqual(rows[239][-3:], b"\xff\xff\x00")
        self.assertEqual(rows[120][480:483], b"\xff\x00\x00")
        self.assertEqual(rows[120][483:486], b"\x00\xff\x00")
        self.assertEqual(rows[0][480:483], b"\xff\xff\xff")

    def test_04_monitor_wrappers_and_noise(self):
        decorated = ["ordinary BASIC: print 42", "\x1b[0mI (100) main: screen ready"]
        decorated += synthetic_lines(monitor=True)
        decorated.append("foobar garbage @CYDSHOT:1|DONE|id=IGNORED|crc=00000000")
        self.assertEqual(shot.decode(text_lines(decorated))[0]["id"], "TEST_SCREEN_001")

    def test_05_select_only_requested_id_from_two_complete_frames(self):
        both = self.lines + synthetic_lines(capture_id="OTHER_ID", seq=8)
        self.bad(both)  # no ambiguous default selection
        self.assertEqual(shot.decode(text_lines(both), "OTHER_ID")[0]["seq"], 8)
        self.assertEqual(shot.decode(text_lines(both), "TEST_SCREEN_001")[0]["seq"], 7)

    def test_06_unknown_id_rejected(self):
        self.bad(self.lines, "WRONG_ID")

    def test_07_duplicate_capture_id_even_with_explicit_selector(self):
        self.bad(self.lines + self.lines, "TEST_SCREEN_001")

    def test_08_truncated_missing_done(self):
        self.bad(self.lines[:-1])

    def test_09_missing_middle_row(self):
        self.bad(self.lines[:115] + self.lines[116:])

    def test_10_reversed_row_order(self):
        data = list(self.lines)
        data[100], data[101] = data[101], data[100]
        self.bad(data)

    def test_11_duplicated_row(self):
        self.bad(self.lines[:40] + [self.lines[39]] + self.lines[40:])

    def test_12_excess_row(self):
        self.bad(self.lines[:-1] + [self.lines[240]] + [self.lines[-1]])

    def test_13_corrupted_row_crc(self):
        bad = self.lines[42].replace("crc=", "crc=FFFFFFFF|bad=")
        self.bad(corrupt_line(self.lines, 42, bad))

    def test_14_exact_length_crc_wrong(self):
        line = self.lines[42]
        crc, b64 = line.split("|crc=")[1].split("|b64=")
        wrong = "00000000" if crc != "00000000" else "FFFFFFFF"
        self.bad(corrupt_line(self.lines, 42, line.replace("|crc=" + crc, "|crc=" + wrong)))

    def test_15_global_crc_wrong(self):
        self.bad(corrupt_line(self.lines, -1, self.lines[-1][:-8] + "00000000"))

    def test_16_bad_base64_character(self):
        self.bad(corrupt_line(self.lines, 4, self.lines[4][:-9] + "!" + self.lines[4][-8:]))

    def test_17_bad_base64_padding(self):
        self.bad(corrupt_line(self.lines, 5, self.lines[5][:-1] + "A"))

    def test_18_short_decoded_row(self):
        self.bad(corrupt_line(self.lines, 7, self.lines[7][:-8]))

    def test_19_bad_width(self):
        self.bad(corrupt_line(self.lines, 0, self.lines[0].replace("w=320", "w=319")))

    def test_20_bad_height(self):
        self.bad(corrupt_line(self.lines, 0, self.lines[0].replace("h=240", "h=241")))

    def test_21_wrong_endianness(self):
        self.bad(corrupt_line(self.lines, 0, self.lines[0].replace("RGB565LE", "RGB565BE")))

    def test_22_invalid_header_firmware_sha_orientation(self):
        for old, new in (("0123456789abcdef0123456789abcdef01234567", "NON_SHA"),
                         ("fw=TEST_SYNTHETIC", "fw=foo/bar"),
                         ("orient=LCD10_UNVERIFIED", "orient=LCD 10")):
            with self.subTest(old=old):
                self.bad(corrupt_line(self.lines, 0, self.lines[0].replace(old, new)))

    def test_23_interleaved_different_begin(self):
        self.bad(self.lines[:40] + [synthetic_lines(capture_id="OTHER")[0]] + self.lines[40:])

    def test_24_interleaved_different_row(self):
        row = self.lines[15].replace("id=TEST_SCREEN_001", "id=WRONG")
        self.bad(corrupt_line(self.lines, 15, row))

    def test_25_false_done_before_rows_completed(self):
        self.bad(self.lines[:33] + [self.lines[-1]] + self.lines[33:])

    def test_26_done_id_mismatch(self):
        self.bad(corrupt_line(self.lines, -1, self.lines[-1].replace("id=TEST_SCREEN_001", "id=WRONG")))

    def test_27_abort_explicit(self):
        self.bad(self.lines[:50] + [f"{shot.PREFIX}ABORT|id=TEST_SCREEN_001|reason=UART_TIMEOUT"])

    def test_28_abort_without_begin_or_wrong_id(self):
        self.bad([f"{shot.PREFIX}ABORT|id=NOPE|reason=TIMEOUT"])
        self.bad(self.lines[:50] + [f"{shot.PREFIX}ABORT|id=NOPE|reason=TIMEOUT"])

    def test_29_invalid_wrong_version_or_partial_marker(self):
        self.bad([self.lines[0].replace("@CYDSHOT:1", "@CYDSHOT:2")] + self.lines[1:])
        self.bad(["@CYDSHO"] + self.lines[1:])
        self.bad(self.lines[:30] + ["@CYDSHOT:"] + self.lines[30:])

    def test_30_wrong_id_crc_done_or_aborted_not_silently_ignored(self):
        self.bad(self.lines[:-1] + [f"{shot.PREFIX}DONE|id=UNRELATED|crc=00000000"])

    def test_31_extra_unknown_frame_record(self):
        self.bad(self.lines[:20] + [f"{shot.PREFIX}FOO|id=TEST_SCREEN_001"] + self.lines[20:])

    def test_32_line_too_long(self):
        self.bad(self.lines[:2] + ["x" * 1025] + self.lines[2:])

    def test_33_bad_id_and_noncanonical_sequence(self):
        self.bad(corrupt_line(self.lines, 0, self.lines[0].replace("id=TEST_SCREEN_001", "id=../BAD")))
        self.bad(corrupt_line(self.lines, 0, self.lines[0].replace("seq=7", "seq=007")))

    def test_34_double_done_rejected(self):
        self.bad(self.lines + [self.lines[-1]])

    def test_35_no_png_and_old_file_protected_for_bad_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "kept.png"
            for bad in (self.lines[:-1],
                        corrupt_line(self.lines, 0, self.lines[0].replace("w=320", "w=321")),
                        self.lines[:90] + [f"{shot.PREFIX}ABORT|id=TEST_SCREEN_001|reason=CANCEL"]):
                output.write_bytes(b"PREEXISTING_IMAGE_TEST")
                inp = Path(temp) / "input.log"
                inp.write_text("\n".join(bad) + "\n", encoding="ascii")
                done = subprocess.run([sys.executable, str(TOOL), str(inp), "--output", str(output)],
                                      capture_output=True, text=True, check=False)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertEqual(output.read_bytes(), b"PREEXISTING_IMAGE_TEST")
                self.assertFalse(list(Path(temp).glob(".hw4-shot-*.tmp")))

    def test_36_no_output_file_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "result.png"
            log = Path(temp) / "bad.log"
            log.write_text("\n".join(self.lines[:-1]) + "\n", encoding="ascii")
            done = subprocess.run([sys.executable, str(TOOL), str(log), "-o", str(out)],
                                  capture_output=True, text=True, check=False)
            self.assertEqual(done.returncode, 2)
            self.assertFalse(out.exists())

    def test_37_cli_success_from_log_and_png_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "result.png"
            log = Path(temp) / "synthetic.log"
            log.write_text("\n".join(self.lines) + "\n", encoding="ascii")
            done = subprocess.run([sys.executable, str(TOOL), str(log), "--id", "TEST_SCREEN_001",
                                   "-o", str(out)], capture_output=True, text=True, check=False)
            self.assertEqual(done.returncode, 0, done.stderr)
            rows = independently_verify_png(out.read_bytes())
            self.assertEqual(rows[120][480:483], b"\xff\x00\x00")

    def test_38_cli_stdin(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "stdin.png"
            done = subprocess.run([sys.executable, str(TOOL), "-o", str(out)],
                                  input="\n".join(self.lines) + "\n", capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(len(independently_verify_png(out.read_bytes())), 240)

    def test_39_invalid_no_session(self):
        self.bad(["just an ordinary CPC BASIC console log", "@CYDSHO"])

    def test_40_wrong_row_id_in_nonselected_frame_still_rejected(self):
        other = synthetic_lines(capture_id="OTHER_ID")
        other[15] = other[15].replace("id=OTHER_ID", "id=WRONG_ID")
        self.bad(self.lines + other, "TEST_SCREEN_001")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--emit-synthetic":
        path = Path(sys.argv[2])
        path.write_text("# TEST_SYNTHETIC - generated on the PC, NOT a real CYD screenshot\n" +
                        "\n".join(synthetic_lines(monitor=True)) + "\n", encoding="ascii")
        print(f"TEST_SYNTHETIC UART fixture: {path} ({path.stat().st_size} bytes)")
    else:
        unittest.main()
