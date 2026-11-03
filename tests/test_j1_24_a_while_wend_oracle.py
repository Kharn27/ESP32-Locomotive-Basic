#!/usr/bin/env python3
"""J1.24-A host contract checks: NOT ROM-backed CPC observations."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "j124_evidence",ROOT/"tools/j1_24_a_while_wend_evidence.py")
oracle=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oracle)

class J124Contract(unittest.TestCase):
    def test_twenty_sources_are_distinct_and_bounded(self):
        oracle.check()
        self.assertEqual(len(oracle.CASES),20)
        self.assertEqual(len({oracle.program(c) for c in oracle.CASES}),20)
        self.assertTrue(all(lines[-1].endswith(" END")
                            for lines in oracle.CASES.values()))
        self.assertTrue(all(len(lines)<=12 for lines in oracle.CASES.values()))

    def test_no_predeclared_cpc_outcome(self):
        self.assertFalse(hasattr(oracle,"OPCODES"))
        self.assertFalse(hasattr(oracle,"EXPECTED_ERR"))
        self.assertFalse(hasattr(oracle,"EXPECTED_RUN"))
        self.assertEqual(oracle.BASE,
                         "355b9bd67ba8970abafcf67978854cebcb878273")

    def test_nested_and_both_colon_forms(self):
        self.assertEqual(sum("WHILE" in x for x in
                             oracle.CASES["NEST_2X2"]),2)
        self.assertEqual(sum("WEND" in x for x in
                             oracle.CASES["NEST_2X2"]),2)
        self.assertTrue(oracle.CASES["COLON_SAME_LINE"][0].count(":")>=3)
        self.assertTrue(oracle.CASES["COLON_CROSS_LINE"][1].count(":")>=1)

    def test_bad_structure_is_part_of_questions(self):
        for name in ("WEND_ORPHAN","WHILE_UNCLOSED","WHILE_MISSING",
                     "WEND_OPERAND","WHILE_BAD_REL"):
            self.assertTrue(oracle.program(name).startswith(b"10 "))
        self.assertFalse(any("WEND" in x for x in
                             oracle.CASES["WHILE_UNCLOSED"]))

    def test_strict_session_and_file_inventory(self):
        files=oracle.inventory()
        self.assertEqual(len(files),360)
        self.assertIn("original/ONCE_LT/program.bin",files)
        self.assertIn("repeat/WEND_ORPHAN/run/printer.dat",files)
        self.assertNotIn("original/ONCE_LT/snapshot.sna",files)
        self.assertFalse(any(x.endswith((".sna",".rom",".dsk",".cfg")) for x in files))

    def test_real_caprice_commands_are_independent(self):
        for case in oracle.CASES:
            a=oracle.list_commands(case)
            b=oracle.run_commands(case)
            self.assertIn("LIST #8",a)
            self.assertIn("RUN",b)
            self.assertIn('PRINT #8,"J124_DIAG_BEGIN"',b)
            self.assertIn("PRINT #8,ERR",b)
            self.assertIn("PRINT #8,ERL",b)
            self.assertIn("CAP32_DELAY CAP32_EXIT",a[-1])
            self.assertEqual(a[:2],["MODE 1","NEW"])

    def test_probe_partition_or_fail_closed(self):
        class FakeInk:
            @staticmethod
            def parse_integer(b):
                try: return {"numeric_value":int(b)}
                except ValueError: return None
        payload=b"START\r\nT\r\nJ124_DIAG_BEGIN\r\n 5 \r\n 20 \r\n10 WEND\r\n"
        out,codes,listing=oracle.parse_printer(payload,FakeInk)
        self.assertEqual(out,b"START\r\nT\r\n")
        self.assertEqual(codes,[5,20])
        self.assertEqual(listing,b"10 WEND\r\n")
        with self.assertRaisesRegex(oracle.OracleError,"DIAG_MARKER"):
            oracle.parse_printer(payload.replace(b"J124_DIAG_BEGIN",b"MISSING"),
                                 FakeInk)

    def test_archive_is_not_faked_or_created(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaisesRegex(oracle.OracleError,"ABSENT_OR_SYMLINK"):
                oracle.verify(Path(path))

    def test_archive_if_present_is_not_an_automatic_cpc_pass(self):
        path=ROOT/"tests/fixtures/cpc6128/j1_24_a_while_wend"
        if path.exists():
            self.assertTrue((path/"manifest.json").is_file())
            oracle.verify(path)
            # External independent manifest seal must also be checked
            # before declaring CPC_ORACLE_VERIFIED.
        else:
            self.assertFalse((path/"manifest.json").is_file())

if __name__=="__main__":
    unittest.main()
