"""CLK-04-A4 synthetic falsifications; never CPC data."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import clk_04_a4_oracle as a4

def rejected(fn,code):
    try:fn()
    except (a4.prior.OracleError,KeyError,ValueError,TypeError) as exc:
        if code not in str(exc):raise AssertionError("WRONG_REJECTION:"+str(exc))
    else:raise AssertionError("FALSIFICATION_ACCEPTED:"+code)

class SealedCorpus(unittest.TestCase):
    def test_count_and_seal(self):
        cases=a4.source_cases()
        self.assertEqual(len(cases),7)
        self.assertEqual([int(i["value"]) for c in cases for i in c["items"]],
                         a4.mandatory_values())
        self.assertEqual(a4.sha(a4.read(a4.SOURCE)),a4.SOURCE_SHA)
    def test_tampered_hash(self):
        with mock.patch.object(a4,"SOURCE_SHA","0"*64):
            rejected(a4.source_cases,"CORPUS_SHA_DRIFT")
    def test_tampered_source_with_updated_hash(self):
        x=json.loads(a4.read(a4.SOURCE))
        x["cases"][0]["lines"][0]="10 T!=999"
        raw=a4.canonical(x)
        with mock.patch.object(a4,"SOURCE_SHA",a4.sha(raw)),mock.patch.object(a4,"read",return_value=raw):
            rejected(a4.source_cases,"SOURCE_BASIC_OR_PRINT_COUNT_DRIFT")
    def test_tampered_identity_with_updated_hash(self):
        x=json.loads(a4.read(a4.SOURCE))
        x["cases"][4]["items"][3]["arithmetic"]="65536+1"
        raw=a4.canonical(x)
        with mock.patch.object(a4,"SOURCE_SHA",a4.sha(raw)),mock.patch.object(a4,"read",return_value=raw):
            rejected(a4.source_cases,"SOURCE_VARIABLE_OR_CONSTRUCTION_DRIFT")
    def test_source_order_and_no_time(self):
        for case in a4.source_cases():
            lines=case["lines"]
            self.assertIn("90 STOP",lines)
            self.assertTrue(any("*2" in x for x in lines))
            self.assertTrue(any(">=0" in x for x in lines))
            self.assertTrue(any(">32767" in x for x in lines))
            self.assertTrue(all("TIME" not in x.upper() for x in lines))
            names=[i["variable"] for i in case["items"]]
            names += [i["arithmetic_variable"] for i in case["items"]
                      if i["arithmetic"]]
            self.assertEqual(len(names),len(set(names)))
            self.assertLessEqual(len(names),8)

class AuthenticityNegatives(unittest.TestCase):
    def test_byte_exact_printer(self):
        rows=a4.raw_number_lines(b"  12  \r\n-1\r\n",2)
        self.assertEqual(rows[0]["raw_hex"],"2020313220200D0A")
        self.assertEqual(rows[1]["number"],-1)
    def test_scientific_parsed_without_reconstruction(self):
        row=a4.raw_number_lines(b" 4.2949673E+09\r\n",1)[0]
        self.assertTrue(row["raw_hex"].endswith("0D0A"))
        self.assertEqual(str(row["number"]),"4.2949673E+9")
    def test_printer_falsifications(self):
        for raw in (b"",b"1",b"1\n2\n",b"1\n\n",
                    b"1.2.3\n",b"1\x00\n",b"1\n"*200):
            with self.subTest(raw=raw[:12]):
                try:a4.raw_number_lines(raw,1)
                except a4.prior.OracleError:pass
                else:self.fail("forged printer accepted")
    def test_wrong_address(self):
        case={"items":[{"variable":"T!","value":"1","arithmetic":None}],
              "printer_numeric_count":5}
        stop={"entries":{"84":{"address":4096,"value_hex":"00 00 00 00 81"}}}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"printer.dat"
            p.write_bytes(b" 4097 \r\n 1 \r\n 2 \r\n -1 \r\n 0 \r\n")
            rejected(lambda:a4.read_values(case,stop,p),"AT_VARIABLE_ADDRESS_MISMATCH")
    def test_absent_archive(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(a4.prior.OracleError,"ABSENT_OR_SYMLINK_"):
                a4.verify(Path(td),"0"*40,"0"*64,None)
    def test_wrong_external_seal(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/"manifest.json").write_bytes(b"{}")
            rejected(lambda:a4.verify(p,"0"*40,"0"*64,None),
                     "EXTERNAL_SEAL_REQUIRED")
    def test_wrong_head_on_sealed_fake(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/"manifest.json").write_bytes(b"{}")
            rejected(lambda:a4.verify(p,"0"*40,a4.sha(b"{}"),None),
                     "HEAD_MISMATCH")
    def test_self_test(self):
        a4.self_test()


class ProductReal5EvidenceNegatives(unittest.TestCase):
    """Synthetic rows only; an input's RAM REAL5 is not the product's RAM REAL5."""

    @staticmethod
    def sample():
        return {
            "value_requested":"1", "cpc_real5_hex":"00 00 00 00 81",
            "cpc_print":"1", "cpc_twice":"2",
            "cpc_ge_zero":"-1", "cpc_gt_32767":"0",
            "raw_print_hex":{
                "value":"2031200D0A", "twice":"2032200D0A",
                "ge_zero":"2D31200D0A", "gt_32767":"2030200D0A"
            }
        }

    @staticmethod
    def record(product_hex, input_hex="0000000081"):
        return "\t".join(("1",input_hex,"2",product_hex,"-1","0",
                          "2031200D0A","2032200D0A","2D31200D0A","2030200D0A"))

    def test_product_real5_falsification_not_full_match(self):
        row=self.sample()
        # The ONLY mutated column is the product REAL5, not the stored input,
        # numeric 2, predicates, or byte-for-byte PRINT candidates.
        verdict=a4.classify_sample(row,self.record("0000000000"))
        self.assertNotEqual(verdict,"CANDIDATE_MATCH")
        self.assertEqual(verdict,"CANDIDATE_PARTIAL_MATCH")
        self.assertEqual(row["twice_real5_status"],"UNVERIFIED")
        self.assertEqual(row["c99_candidate"]["twice_real5_hex"],"00 00 00 00 00")
        self.assertEqual(set(row["c99_candidate"]["print_comparison"].values()),
                         {"CANDIDATE_MATCH"})

    def test_plausible_product_is_also_unverified_without_cpc_ram_bytes(self):
        row=self.sample()
        verdict=a4.classify_sample(row,self.record("0000000082"))
        self.assertEqual(verdict,"CANDIDATE_PARTIAL_MATCH")
        self.assertEqual(row["twice_real5_status"],"UNVERIFIED")

    def test_input_real5_still_checked_fail_closed(self):
        row=self.sample()
        verdict=a4.classify_sample(row,self.record("0000000082","0000000000"))
        self.assertEqual(verdict,"CPC_MISMATCH_STOP")

if __name__=="__main__":unittest.main()
