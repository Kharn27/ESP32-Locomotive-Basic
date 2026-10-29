"""HW4-SCROLL-A0: positive and mutation-negative UART fixtures."""
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hw4_scroll_a0_uart import analyze, EvidenceError

DATA = ROOT / "tests" / "fixtures" / "hw4_scroll_a0"
KW = dict(sha="319e8872c88842840e0992f305ec047fe516cb38",
          idf="v5.5.6", profile="CONSOLE", spi_hz=40000000, cpu_mhz=240)

class TestA0(unittest.TestCase):
    def test_positive(self):
        r = analyze((DATA/"valid.uart.log").read_text(), **KW)
        self.assertEqual(len(r["snapshots"]), 2)
        self.assertEqual(r["last"]["scroll_up_observed"], 3)
        self.assertEqual(r["last"]["scroll_down_observed"], 1)
        self.assertEqual(r["last"]["resets"], 1)
        self.assertEqual(r["last"]["scroll_associated"]["reset_tagged"], 1)
        self.assertEqual(r["last"]["ordinary"]["bands"], 3)
    def test_negatives(self):
        for name in ("truncated", "bytes_mismatch", "reset_reversed",
                     "hist_mismatch", "collision_lost"):
            with self.subTest(name=name), self.assertRaises(EvidenceError):
                analyze((DATA/(name+".uart.log")).read_text(), **KW)
    def test_manifest_mismatches(self):
        text=(DATA/"valid.uart.log").read_text()
        for change in (dict(cpu_mhz=160),dict(idf="v5.5.5"),
                       dict(profile="HW3"),dict(spi_hz=0),
                       dict(sha="1234")):
            kw=dict(KW);kw.update(change)
            with self.subTest(change=change), self.assertRaises(EvidenceError):
                analyze(text, **kw)
    def test_full_protocol_requires_20_each(self):
        with self.assertRaises(EvidenceError):
            analyze((DATA/"valid.uart.log").read_text(),
                    require_bidirectional=True, **KW)
    def test_no_missing_measurements(self):
        text=(DATA/"valid.uart.log").read_text()
        for fragment in ("HW4-C2 START ", "HW4-C2 ORIENTATION_PASS case=9",
                         "HW4-SCROLL-A0 SAMPLE seq=1"):
            with self.subTest(fragment=fragment), self.assertRaises(EvidenceError):
                analyze(text.replace(fragment,"REMOVED "), **KW)

if __name__ == "__main__":
    unittest.main()
