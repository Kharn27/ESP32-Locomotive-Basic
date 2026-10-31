"""J1.21-A host-only contract tests. Never synthetic CPC oracle evidence."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "j121cls", ROOT/"tools/j1_21_a_cls_oracle.py")
cls = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cls)


class TestOfflineCLSOracle(unittest.TestCase):
    def test_case_inventory_and_sources(self):
        self.assertEqual(len(cls.CASES),14)
        self.assertTrue(cls.check_sources())
        self.assertEqual(len(cls.paths()),14*2*9)

    def test_direct_and_numbered_distinct(self):
        self.assertEqual(sum(v[0]=="direct" for v in cls.CASES.values()),7)
        self.assertEqual(sum(v[0]=="numbered" for v in cls.CASES.values()),7)
        self.assertTrue(all(v[1]=="RUN" for v in cls.CASES.values() if v[0]=="numbered"))
        self.assertTrue(all("REM" in cls.SOURCE_LINES[k][0]
                            for k,v in cls.CASES.items() if v[0]=="direct"))

    def test_window_probes_outside_before_inside(self):
        for key in ("D_WINDOW","N_WINDOW"):
            steps=cls.preparation(key)
            self.assertLess(steps.index('PRINT "OUTSIDE"'), steps.index("WINDOW 10,30,8,20"))
            self.assertGreater(steps.index('PRINT "INSIDE"'),steps.index("WINDOW 10,30,8,20"))

    def test_timeline_has_before_and_after_in_one_run(self):
        for case,(_mode,action,_screen,_shape) in cls.CASES.items():
            run=cls.command_run(case)
            shot="CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT"
            self.assertEqual(run.count(shot),2)
            self.assertLess(run.index(shot),run.index(action))
            self.assertLess(run.index(action),len(run)-run[::-1].index(shot)-1)
            self.assertLess(run.index(shot,run.index(action)),run.index("PRINT #8,ERR"))
            self.assertLess(run.index("PRINT #8,ERL"),run.index("LIST #8"))

    def test_mode_and_paper_controls(self):
        self.assertEqual(cls.setup("N_MODE0")[0],"MODE 0")
        self.assertEqual(cls.setup("N_MODE2")[0],"MODE 2")
        self.assertIn("PAPER 2",cls.setup("D_PAPER"))
        self.assertEqual(cls.CASES["D_HASH8"][1],"CLS #8")

    def test_no_archive_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(cls.Invalid,"ARCHIVE_ABSENT"):
                cls.verify(Path(t),permanent=True)

    def test_forged_minimal_manifest_refused(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t)/"manifest.json").write_text(json.dumps({"schema":1}))
            with self.assertRaisesRegex(cls.Invalid,"MANIFEST_PROVENANCE"):
                cls.verify(Path(t),permanent=True)

    def test_output_requires_real_caprice(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(cls.Invalid,"HEAD_FORMAT"):
                cls.acquire(Path(t),Path(t)/"never","BAD_HEAD")

    def test_not_presealed(self):
        self.assertFalse(cls.SEALED_MANIFEST_SHA256)
        self.assertFalse(cls.SEALED_FILE_SHA256)
        self.assertFalse(cls.SEALED_ACQUISITION_HEAD)

    def test_roi_sanity(self):
        for box in cls.ROIS.values():
            x0,y0,x1,y1=box
            self.assertLess(x0,x1)
            self.assertLess(y0,y1)
            self.assertLessEqual(x1,768)
            self.assertLessEqual(y1,540)


if __name__=="__main__":
    unittest.main()
