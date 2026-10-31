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
            self.assertEqual(sum(x.count("CAP32_SCRNSHOT") for x in run),2)
            before=run.index(shot)
            target=run.index(action,before+1)  # skip the setup's own CLS
            after=run.index(cls.CHRONO_DELAY+" CAP32_SCRNSHOT",target+1)
            self.assertLess(before,target)
            self.assertLess(target,after)
            self.assertLess(after,run.index("PRINT #8,ERR"))
            self.assertEqual(cls.CHRONO_DELAY.split().count("CAP32_DELAY"),96)
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

    def test_seal_matches_independent_original_artifact(self):
        self.assertEqual(cls.SEALED_MANIFEST_SHA256,
                         "dfe668e3ec5b799e22deec017049fd132b28a72a16036ccbfdfc8214e7f59a65")
        self.assertEqual(cls.SEALED_ACQUISITION_HEAD,
                         "4ae73a2c054b7332f64fb77eaf68e41b89d36ddb")
        self.assertEqual(set(cls.SEALED_FILE_SHA256),cls.paths())
        self.assertEqual(len(cls.SEALED_FILE_SHA256),252)

    def test_timestamp_title_is_excluded_but_text_pixels_are_exact(self):
        a=[bytearray(768*3) for _ in range(540)]
        b=[bytearray(row) for row in a]
        rect=cls.ROIS["text_area"]
        b[12][15]=77  # Caprice screenshot filename/title outside CPC text.
        self.assertEqual(cls.roi_rgb_sha(a,rect),cls.roi_rgb_sha(b,rect))
        b[120][80*3]=99  # Genuine visible CPC region is discriminant.
        self.assertNotEqual(cls.roi_rgb_sha(a,rect),cls.roi_rgb_sha(b,rect))

    def test_roi_sanity(self):
        for box in cls.ROIS.values():
            x0,y0,x1,y1=box
            self.assertLess(x0,x1)
            self.assertLess(y0,y1)
            self.assertLessEqual(x1,768)
            self.assertLessEqual(y1,540)


if __name__=="__main__":
    unittest.main()
