#!/usr/bin/env python3
"""HW4 A1-P0 falsifiable software-only VSCR permutation contract."""
import importlib.util
import random
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "tools" / "hw4_vscr_case10_model.py"
spec = importlib.util.spec_from_file_location("hw4_vscr_case10_model", MODULE)
assert spec and spec.loader
import sys
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def model(start=0):
    return m.Case10Model(m.Candidate(visible_start=start, scan_axis_y=True))


class GeometryTests(unittest.TestCase):
    def test_datasheet_sum_320_not_240(self):
        for start, expected in ((0, (20, 200, 100)), (80, (100, 200, 20))):
            with self.subTest(start=start):
                p = m.assess(m.Candidate(visible_start=start, scan_axis_y=True))
                self.assertEqual(p.status, "MODEL_FEASIBLE_CONTROLLER_UNVERIFIED")
                self.assertTrue(p.fallback)
                self.assertEqual((p.tfa, p.vsa, p.bfa), expected)
                self.assertEqual(sum(expected), 320)
                self.assertNotEqual(sum(expected), 240)

    def test_unknown_capability_never_enables_hardware(self):
        c = m.Candidate(visible_start=0, scan_axis_y=True)
        for known in (False, True):
            p = m.assess(c, capabilities_known=known)
            self.assertTrue(p.fallback)
            self.assertNotEqual(p.status, "VSCR_FEASIBLE")
            self.assertIn("UNVERIFIED", p.status)

    def test_negative_falsifications(self):
        good = dict(visible_start=0, scan_axis_y=True)
        variants = {
            "unknown_visible_slice": dict(visible_start=None),
            "offset_unsupported": dict(visible_start=40),
            "axis_unknown": dict(scan_axis_y=None),
            "axis_x": dict(scan_axis_y=False),
            "orientation_9": dict(case=9),
            "mirror_y_wrong": dict(mirror_y=False),
            "mirror_x_wrong": dict(mirror_x=True),
            "swap_wrong": dict(swap_xy=True),
            "margin_top_wrong": dict(top=19),
            "margin_bottom_wrong": dict(bottom=19),
            "height_wrong": dict(height=199),
            "width_wrong": dict(width=240),
            "physical_height_wrong": dict(visible_height=320),
        }
        for name, change in variants.items():
            with self.subTest(falsification=name):
                p = m.assess(m.Candidate(**(good | change)))
                self.assertEqual(p.status, "MODEL_NOT_FEASIBLE")
                self.assertTrue(p.fallback)
        for kw in ({"dma_ok": False}, {"lcd_fault": True}):
            p = m.assess(m.Candidate(**good), **kw)
            self.assertEqual(p.reason, "DMA_FAIL_STOP_OR_STICKY_LCD_FAULT")
            self.assertTrue(p.fallback)

    def test_forbidden_plan_cannot_construct(self):
        with self.assertRaises(m.ModelReject):
            m.Case10Model(m.Candidate(scan_axis_y=True, visible_start=None))


class PixelMappingTests(unittest.TestCase):
    def check(self, v):
        self.assertEqual(v.physical(), v.shot())
        self.assertEqual(v.physical()[:20], [f"TOP:{i}" for i in range(20)])
        self.assertEqual(v.physical()[220:], [f"BOTTOM:{i}" for i in range(20)])
        self.assertTrue(all(x.startswith("HIDDEN:") for i, x in enumerate(v.gram)
                            if i < v.cfg.visible_start or i >= v.cfg.visible_start + 240))

    def test_initial_and_margin_preservation(self):
        for start in (0, 80):
            self.check(model(start))

    def test_single_line_up_down_and_exposure(self):
        for start in (0, 80):
            with self.subTest(start=start):
                v = model(start)
                before = v.shot()[20:220]
                self.assertEqual(v.scroll("up"), 5120)
                self.assertEqual(v.shot()[20:220], before[8:] + ["PAPER"] * 8)
                self.check(v)
                v = model(start)
                self.assertEqual(v.scroll("down"), 5120)
                self.assertEqual(v.shot()[20:220], ["PAPER"] * 8 + before[:-8])
                self.check(v)

    def test_wrap_cadence_and_consecutive_scrolls(self):
        for start in (0, 80):
            for sequence in (("up",) * 51, ("down",) * 51,
                             ("up", "down") * 75):
                v = model(start)
                for direction in sequence:
                    v.scroll(direction)
                    self.check(v)
                self.assertEqual(v.offset % 8, 0)

    def test_25_rows_both_directions(self):
        for start in (0, 80):
            for direction in ("up", "down"):
                v = model(start)
                self.assertEqual(v.scroll(direction, 25), 128000)
                self.assertEqual(v.shot()[20:220], ["PAPER"] * 200)
                self.check(v)

    def test_write_after_scroll_and_dirty_generation(self):
        for start in (0, 80):
            v = model(start)
            stale = v.generation
            v.scroll("up", 2)
            with self.assertRaisesRegex(m.ModelReject, "STALE_DIRTY"):
                v.write_raster(70, "stale", generation=stale)
            self.assertEqual(v.shot()[70], "ROW:66")  # after 16px up: original logical y=86 -> ROW:66
            addr = v.write_raster(70, "graphics", generation=v.generation)
            self.assertEqual(v.gram[addr], "graphics")
            self.check(v)
            v.scroll("down", 3)
            addr = v.write_raster(35, "text/E2")
            self.assertEqual(v.gram[addr], "text/E2")
            self.check(v)

    def test_overlay_and_shot_are_logical(self):
        v = model(80)
        before = v.shot()
        v.set_cursor(20, 150)
        self.assertNotEqual(v.visible_with_cursor(), before)
        self.assertEqual(v.shot(), before)
        v.scroll("down", 1)
        self.assertEqual(v.visible_with_cursor()[150], "OVERLAY:x20:" + v.shot()[150])
        self.check(v)

    def test_clear_disable_restart(self):
        for start in (0, 80):
            v = model(start)
            v.scroll("up", 17)
            v.clear()
            self.assertEqual(v.offset, 0)
            self.assertEqual(v.shot()[20:220], ["PAPER"] * 200)
            self.check(v)
            v.write_raster(50, "ink3")
            v.scroll("down", 5)
            v.disable()
            self.assertEqual(v.offset, 0)
            self.check(v)
            self.check(model(start))  # restart

    def test_independent_reference_mixed_raster_edits(self):
        # The reference is a separate list with no knowledge of GRAM offsets.
        for start in (0, 80):
            v = model(start)
            ref = v.shot()
            rng = random.Random(156 + start)
            for step in range(220):
                op = rng.choice(("up", "down", "write", "write", "clear"))
                if op in ("up", "down"):
                    rows = rng.randint(1, 25)
                    delta = rows * 8
                    before = ref[20:220]
                    ref[20:220] = (before[delta:] + ["PAPER"] * delta
                                   if op == "up" else
                                   ["PAPER"] * delta + before[:200 - delta])
                    v.scroll(op, rows)
                elif op == "write":
                    y = rng.randrange(20, 220)
                    value = f"pixel:{start}:{step}"
                    ref[y] = value
                    v.write_raster(y, value)
                else:
                    ref[20:220] = ["PAPER"] * 200
                    v.clear()
                self.assertEqual(v.physical(), ref, f"step={step} start={start}")
                self.assertEqual(v.shot(), ref)

    def test_reject_invalid_rows_margins_and_fail_stop(self):
        v = model(0)
        pre = (v.shot(), v.physical(), v.offset, v.generation)
        for direction, rows in (("side", 1), ("up", 0), ("up", 26), ("down", -1)):
            with self.assertRaises(m.ModelReject):
                v.scroll(direction, rows)
        for y in (-1, 0, 19, 220, 239, 240):
            with self.assertRaises(m.ModelReject):
                v.write_raster(y, "bad")
        self.assertEqual((v.shot(), v.physical(), v.offset, v.generation), pre)
        with self.assertRaisesRegex(m.ModelReject, "DMA_FAILURE"):
            v.scroll("up", dma_ok=False)
        with self.assertRaisesRegex(m.ModelReject, "STICKY_FAULT"):
            v.scroll("up")
        with self.assertRaisesRegex(m.ModelReject, "STICKY_FAULT"):
            v.clear()
        self.assertEqual((v.shot(), v.physical(), v.offset, v.generation), pre)


if __name__ == "__main__":
    unittest.main(verbosity=2)
