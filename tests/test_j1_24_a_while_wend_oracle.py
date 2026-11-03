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

    def test_independently_sealed_archive_sha_and_all_360_files(self):
        path=ROOT/"tests/fixtures/cpc6128/j1_24_a_while_wend"
        seal="11b8450e0d8d772e9c4049aabb78ae2cf32595d7764199fa3904cbc0ba2ca441"
        manifest=(path/"manifest.json").read_bytes()  # FAIL if absent
        self.assertEqual(hashlib.sha256(manifest).hexdigest(),seal)
        obj=json.loads(manifest)
        self.assertEqual(obj["acquisition_head"],
                         "a1659e814c8db7075a2bb08b54e30063de20d128")
        self.assertEqual(obj["run_id"],"41624453081")
        self.assertEqual(len(obj["files"]),360)
        self.assertEqual(set(obj["files"]),oracle.inventory())
        for relative,expected in obj["files"].items():
            with self.subTest(file=relative):
                self.assertEqual(hashlib.sha256(
                    (path/relative).read_bytes()).hexdigest(),expected)

    def test_observed_cpc_tokens_and_repeats_not_predictions(self):
        evidence=ROOT/"tests/fixtures/cpc6128/j1_24_a_while_wend"
        for case in oracle.CASES:
            original=json.loads((evidence/"original"/case/"capture.json").read_bytes())
            repeat=json.loads((evidence/"repeat"/case/"capture.json").read_bytes())
            with self.subTest(case=case):
                self.assertEqual(original["program_hex"],repeat["program_hex"])
                self.assertEqual(original["list_sha256"],repeat["list_sha256"])
                self.assertEqual(original["list_after_hex"],repeat["list_after_hex"])
                self.assertEqual(original["run_output_hex"],repeat["run_output_hex"])
                self.assertEqual((original["err"],original["erl"]),
                                 (repeat["err"],repeat["erl"]))
        def tokens(case):
            capture=json.loads((evidence/"original"/case/"capture.json").read_bytes())
            return [v["first_body_byte"] for v in
                    capture["observed_keyword_lines"]]
        self.assertEqual(tokens("ZERO_LITERAL"),[0xd6,0xd5])
        self.assertEqual(tokens("WEND_ORPHAN"),[0xd5])
        self.assertEqual(tokens("NEST_2X2"),[0xd6,0xd6,0xd5,0xd5])

    def test_exact_cpc_output_and_diagnostic_counterexamples(self):
        evidence=ROOT/"tests/fixtures/cpc6128/j1_24_a_while_wend"
        outputs={
            "ZERO_LITERAL":"ZERO\r\n",
            "ONCE_LT":"T\r\nEND\r\n",
            "THREE_LT":"T\r\nT\r\nT\r\nEND\r\n",
            "NEST_2X2":"I\r\nI\r\nI\r\nI\r\nEND\r\n",
            "COLON_SAME_LINE":"C\r\nC\r\nEND\r\n",
            "COLON_CROSS_LINE":"C\r\nC\r\nEND\r\n",
        }
        errors={
            "WEND_ORPHAN":(30,10),
            "WHILE_UNCLOSED":(29,10),
            "WHILE_MISSING":(22,10),
            "WEND_OPERAND":(0,20),  # screen Syntax error in 20, NOT success
            "WHILE_BAD_REL":(22,20),
        }
        for session in oracle.SESSIONS:
            for case,output in outputs.items():
                with self.subTest(session=session,case=case):
                    cap=json.loads((evidence/session/case/"capture.json").read_bytes())
                    self.assertEqual(bytes.fromhex(cap["run_output_hex"]),
                                     output.encode("ascii"))
                    self.assertEqual((cap["err"],cap["erl"]),(0,0))
            for case,expected in errors.items():
                with self.subTest(session=session,case=case):
                    cap=json.loads((evidence/session/case/"capture.json").read_bytes())
                    self.assertEqual((cap["err"],cap["erl"]),expected)
                    self.assertEqual(cap["run_output_hex"],"")
                    if case=="WEND_OPERAND":
                        self.assertFalse(cap["list_equal"])
                    else:
                        self.assertTrue(cap["list_equal"])

if __name__=="__main__":
    unittest.main()
