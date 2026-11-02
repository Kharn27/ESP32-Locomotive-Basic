#!/usr/bin/env python3
"""Host-only contract checks. These are NOT observations by the CPC."""
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "j123_oracle", ROOT / "tools/j1_23_a_locate_border_evidence.py")
oracle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oracle)


class J123OracleContract(unittest.TestCase):
    def test_mission_matrix(self):
        self.assertEqual(len(oracle.CASES), 20)
        self.assertEqual(len([c for c in oracle.CASES if c.startswith("L_")]), 10)
        self.assertEqual(len([c for c in oracle.CASES if c.startswith("B_")]), 10)

    def test_origin_and_bounds_are_questions_not_results(self):
        self.assertEqual(oracle.CASES["L_01_01"], "LOCATE 1,1")
        self.assertEqual(oracle.CASES["L_40_25"], "LOCATE 40,25")
        for case in ("L_00_01","L_41_01","L_01_00","L_01_26",
                     "L_NEG_01","L_MISSING"):
            self.assertTrue(oracle.program(case).startswith(b"10 LOCATE"))

    def test_border_arity_positive_negative(self):
        for case in ("B_00","B_26","B_27","B_NEG",
                     "B_00_26","B_26_00","B_26_27","B_NEG_01",
                     "B_EXPR","B_MISSING"):
            self.assertTrue(oracle.program(case).startswith(b"10 BORDER"))

    def test_ram_tokens_are_hypotheses(self):
        self.assertEqual(oracle.OPCODES, {"L":0xA9,"B":0x82})
        self.assertEqual(oracle.program("L_EXPR"),
                         b'10 LOCATE 1+2,2+3\n20 PRINT "LBLOC"\n30 END\n')
        self.assertEqual(oracle.program("B_EXPR"),
                         b'10 BORDER 1+2,3+4\n20 PRINT "LBBOR"\n30 END\n')

    def test_session_inventory(self):
        self.assertEqual(len(oracle.inventory()), 20*2*9)
        self.assertIn("repeat/B_26_00/program.bin", oracle.inventory())
        self.assertNotIn("repeat/B_26_00/snapshot.sna", oracle.inventory())

    def test_oracle_separation(self):
        self.assertEqual(oracle.BASE, "3c9d3a679d5c5d9db4d659e7d2e1367914d7b7d8")
        self.assertNotIn("core", oracle.setup())
        self.assertEqual(oracle.list_commands("L_02_03")[-2:],
                         ["LIST #8","CAP32_DELAY CAP32_EXIT"])
        self.assertIn("PRINT #8,ERR", oracle.run_commands("B_26_00"))
        self.assertIn("PRINT #8,ERL", oracle.run_commands("B_26_00"))

    def test_no_fake_oracle_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(oracle.OracleError, "ABSENT_OR_SYMLINK"):
                oracle.verify(Path(tmp))

    def test_capture_roi_contract(self):
        self.assertIn("border_left", oracle.RECTS)
        self.assertIn("text", oracle.RECTS)
        self.assertTrue(all(0 <= x0 < x1 <= 768 and 0 <= y0 < y1 <= 540
                            for x0,y0,x1,y1 in oracle.RECTS.values()))


    def test_independent_sha256_of_committed_archive(self):
        evidence = ROOT / "tests/fixtures/cpc6128/j1_23_a_locate_border"
        manifest = (evidence/"manifest.json").read_bytes()
        self.assertEqual(hashlib.sha256(manifest).hexdigest(),
                         "31addf9025214ea4f4f5ea3d8f592cb0cffbfac4c0fd962d2fee9fa30266a1f8")
        data = json.loads(manifest)
        self.assertEqual(data["acquisition_head"],
                         "83a78f17bfb9a2233e372922c3bed4ad785d9f3f")
        self.assertEqual(set(data["files"]),oracle.inventory())
        for path, expected in data["files"].items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((evidence/path).read_bytes()).hexdigest(),
                                 expected)

    def test_cpc_captured_repeat_and_counterexamples(self):
        evidence = ROOT / "tests/fixtures/cpc6128/j1_23_a_locate_border"
        for case in oracle.CASES:
            original = json.loads((evidence/"original"/case/"capture.json").read_bytes())
            repeat = json.loads((evidence/"repeat"/case/"capture.json").read_bytes())
            with self.subTest(case=case):
                self.assertEqual(original["token_observed_ram"],oracle.OPCODES[case[0]])
                self.assertTrue(original["token_hypothesis_matches"])
                self.assertEqual((original["err"],original["erl"]),
                                 (repeat["err"],repeat["erl"]))
                self.assertEqual(original["program_hex"],repeat["program_hex"])
                self.assertEqual(original["printer_hex"],repeat["printer_hex"])
                self.assertEqual(original["list_after_hex"],repeat["list_after_hex"])
        def capture(case):
            return json.loads((evidence/"original"/case/"capture.json").read_bytes())
        self.assertEqual((capture("L_41_01")["err"],capture("L_01_26")["err"]),
                         (0,0))
        self.assertEqual((capture("B_27")["err"],capture("B_27")["erl"]),
                         (0,0))
        self.assertEqual((capture("B_MISSING")["err"],capture("B_MISSING")["erl"]),
                         (22,10))
        self.assertFalse(capture("L_MISSING")["list_equal"])
        self.assertEqual((capture("L_MISSING")["err"],capture("L_MISSING")["erl"]),
                         (0,10))  # Printer probe is not the screen Syntax error.

if __name__ == "__main__":
    unittest.main()
