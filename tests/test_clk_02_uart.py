"""CLK-02 synthetic 15-RUN tests: NEVER hardware evidence."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from clk_01_uart import Reject
from clk_02_uart import (BASELINE_HEAD, BASELINE_RAW_SHA256,
                         analyze, reports)
from test_clk_01_uart import example

SHA = "f" * 40
SCOPE = "RUN_slices_including_repaint_excluding_final_prompt"


def phase_line(i, full=0):
    duration = 1000 + i
    extra = 1 if full else 0
    bands = 3 + 30 * full
    return ("HW4-CLK02 RUN_PHASE_SUMMARY version=1 run=%d "
            "duration_us=%d step_call_wall_us=200 "
            "repaint_call_wall_us=150 yield_call_wall_us=400 "
            "other_wall_us=%d step_calls=3 repaint_calls=%d "
            "repaint_flushes=1 repaint_bands=%d full_repaints=%d "
            "yield_calls=2 probe_clock_reads=%d valid=1 "
            "unit=us clock=esp_timer_task_wall scope=%s "
            "step_scope=scheduler_slice_call "
            "repaint_scope=dirty_plus_touch_full_calls "
            "yield_scope=cooperative_vTaskDelay_call "
            "attribution=task_wall_not_cpu_or_gram sha=%s" %
            (i, duration, duration - 750, 2 + extra, bands,
             full, 14 + 2 * extra, SCOPE, SHA))


def sample(full=0):
    # CLK-01 fixture remains untouched. Substitute the boot + RUN attestation
    # expected for the new HEAD; add one post-terminal line per RUN.
    old = example()
    old = old.replace("c8cec8b1b4d0cab553cdc8b97b751aef3dd1370d", SHA)
    old = old.replace("version=c8cec8b", "version=" + SHA[:7])
    out = []
    i = 0
    for row in old.splitlines():
        out.append(row)
        if "HW4-RUN-B RUN_TERMINAL " in row:
            i += 1
            out.append(phase_line(i, full if i == 1 else 0))
    assert i == 15
    return "\n".join(out) + "\n"


class TestClk02(unittest.TestCase):
    def setUp(self):
        self.raw = sample()

    def test_valid_all_15_and_report(self):
        answer = analyze(self.raw, SHA)
        self.assertEqual(len(answer["samples"]), 15)
        self.assertEqual(len(answer["scenarios"]), 5)
        self.assertFalse(answer["baseline"])
        self.assertEqual(answer["samples"][0]["other_wall_us"], 251)
        csv_text, md = reports(answer)
        self.assertEqual(len(csv_text.splitlines()), 16)
        self.assertIn("NOT_COMPARABLE", md)
        self.assertIn("NON MESURÉ", md)

    def test_touch_full_repaint_disjoint(self):
        answer = analyze(sample(full=1), SHA)
        self.assertEqual(answer["samples"][0]["repaint_bands"], 33)
        self.assertEqual(answer["samples"][0]["full_repaints"], 1)

    def test_falsification_matrix(self):
        src = self.raw
        line = phase_line(1)
        needles = {
            "missing_line": src.replace(line + "\n", "", 1),
            "duplicate_line": src.replace(line + "\n", line + "\n" + line + "\n", 1),
            "missing_field": src.replace(" step_calls=3", "", 1),
            "extra_field": src.replace(" step_calls=3", " step_calls=3 cpu_us=123", 1),
            "duplicate_field": src.replace(" step_calls=3", " step_calls=3 step_calls=3", 1),
            "wrong_version": src.replace("version=1", "version=2", 1),
            "wrong_head": src.replace("sha=" + SHA, "sha=" + ("a" * 40), 1),
            "negative_number": src.replace("other_wall_us=251", "other_wall_us=-1", 1),
            "overflow_u64": src.replace("step_call_wall_us=200",
                                        "step_call_wall_us=18446744073709551616", 1),
            "overflow_u32": src.replace("step_calls=3", "step_calls=4294967296", 1),
            "nonnumeric": src.replace("step_calls=3", "step_calls=NaN", 1),
            "duration_tampered": src.replace("duration_us=1001", "duration_us=1002", 1),
            "not_additive": src.replace("other_wall_us=251", "other_wall_us=250", 1),
            "step_calls": src.replace("step_calls=3", "step_calls=2", 1),
            "yield_calls": src.replace("yield_calls=2", "yield_calls=3", 1),
            "repaint_calls": src.replace("repaint_calls=2", "repaint_calls=3", 1),
            "flushes_too_many": src.replace("repaint_flushes=1", "repaint_flushes=3", 1),
            "bands_too_many": src.replace("repaint_bands=3", "repaint_bands=53", 1),
            "bands_too_few_for_full": sample(full=1).replace(
                "repaint_bands=33", "repaint_bands=3", 1),
            "full_repaints_bad": src.replace("full_repaints=0", "full_repaints=1", 1),
            "probe_clock_count": src.replace("probe_clock_reads=14",
                                              "probe_clock_reads=12", 1),
            "valid_zero": src.replace("valid=1", "valid=0", 1),
            "clock_scope": src.replace("clock=esp_timer_task_wall",
                                        "clock=cpu_cycles", 1),
            "run_scope": src.replace(SCOPE, "CPU_BASIC_ONLY", 1),
            "step_scope": src.replace("step_scope=scheduler_slice_call",
                                       "step_scope=pure_basic_cpu", 1),
            "repaint_scope": src.replace("repaint_scope=dirty_plus_touch_full_calls",
                                          "repaint_scope=gram_visible", 1),
            "yield_scope": src.replace("yield_scope=cooperative_vTaskDelay_call",
                                        "yield_scope=cpu_sleep", 1),
            "attribution": src.replace("task_wall_not_cpu_or_gram",
                                        "cpu_exclusive", 1),
            "wrong_run": src.replace("RUN_PHASE_SUMMARY version=1 run=1",
                                     "RUN_PHASE_SUMMARY version=1 run=9", 1),
            "wrong_unit": src.replace("unit=us", "unit=ticks", 1),
            "dma_failure": src.replace("dma_fault=0", "dma_fault=1", 1),
            "timeout": src.replace("dma_timeouts=0", "dma_timeouts=1", 1),
            "terminal_error": src.replace("RUN_TERMINAL state=5",
                                           "RUN_TERMINAL state=4", 1),
            "source_tamper": src.replace("length=7 hex=31302041253d30",
                                         "length=7 hex=31302041253d31", 1),
            "missing_terminal": src.replace("RUN_TERMINAL state=5",
                                              "NOT_TERMINAL state=5", 1),
            "phase_wrong_position": src.replace(
                "HW4-RUN-B RUN_TERMINAL state=5",
                phase_line(1) + "\nHW4-RUN-B RUN_TERMINAL state=5", 1),
        }
        for key, bad in needles.items():
            with self.subTest(mutation=key), self.assertRaises(Reject):
                analyze(bad, SHA)

    def test_untrusted_baseline_rejected(self):
        for raw in (b"", b"fake", self.raw.encode("utf-8")):
            with self.subTest(n=len(raw)), self.assertRaises(Reject):
                analyze(self.raw, SHA, raw)
        self.assertEqual(len(BASELINE_HEAD), 40)
        self.assertEqual(len(BASELINE_RAW_SHA256), 64)

    def test_bad_head(self):
        for head in ("x" * 40, SHA[:7], "a" * 40):
            with self.subTest(head=head), self.assertRaises(Reject):
                analyze(self.raw, head)


if __name__ == "__main__":
    unittest.main()
