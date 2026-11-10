"""CLK-04-A1 host-only verifier tests: deliberate fabrications, NEVER CPC oracle."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "clk_04_real5_oracle",ROOT/"tools/clk_04_real5_oracle.py")
import sys
sys.path.insert(0,str(ROOT/"tools"))
a=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)

def must_fail(fun,fragment):
    try:
        fun()
    except (a.prior.OracleError,ValueError,KeyError) as exc:
        if fragment not in str(exc):
            raise AssertionError("Wrong failure: "+str(exc))
    else:
        raise AssertionError("Tampered evidence accepted: "+fragment)

class PositiveStructuralTests(unittest.TestCase):
    def test_sealed_corpus(self):
        cases=a.source_cases()
        self.assertEqual(len(cases),7)
        self.assertEqual([c["id"] for c in cases if c["kind"]=="time"],
                         ["T_DYNAMIC_PAIR","T_LATE_BOUNDED"])
        self.assertEqual(cases[-1]["pre_run_delays"],160)
    def test_real5_window_only_if_named_typed(self):
        entry=bytes.fromhex("00 00 D4 04 00 00 00 00 81")
        decoded=a.check_window(entry,0x400,[ord("T")])
        self.assertEqual(decoded[ord("T")]["value_hex"],"00 00 00 00 81")
        self.assertEqual(decoded[ord("T")]["address"],0x404)
    def test_decimal_parser_cpc_spaced(self):
        self.assertEqual([str(x) for x in a.numbers(b" 1.25 \r\n-1 \r\n",2)],
                         ["1.25","-1"])
    def test_fixed_value_link(self):
        entry={"address":0x400,"value_hex":"00 00 00 00 81"}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"printer.dat"
            p.write_bytes(b" 1024 \r\n 1 \r\n 2 \r\n-1\r\n 0\r\n")
            c=next(x for x in a.source_cases() if x["id"]=="F_ONE")
            self.assertEqual(a.validate_link(c,{"entries":{ord("T"):entry}},p)[1],"1")
    def test_self_test(self):
        a.self_test()

class ForgedEvidenceTests(unittest.TestCase):
    def test_wrong_type(self):
        must_fail(lambda:a.check_window(bytes.fromhex(
            "00 00 D4 05 00 00 00 00 81"),0x400,[84]),"RAM_SCALAR_IDENTITY")
    def test_wrong_name(self):
        must_fail(lambda:a.check_window(bytes.fromhex(
            "00 00 C1 04 00 00 00 00 81"),0x400,[84]),"RAM_SCALAR_IDENTITY")
    def test_window_short_or_overlong(self):
        for raw in (bytes(8),bytes(10),bytes(90)):
            must_fail(lambda raw=raw:a.check_window(raw,0x400,[84]),"RAM_WINDOW_INVALID")
    def test_duplicate_name(self):
        x=bytes.fromhex("00 00 D4 04 00 00 00 00 81")
        must_fail(lambda:a.check_window(x+x,0x400,[84,85]),"RAM_SCALAR_IDENTITY")
    def test_wrong_pointer_print(self):
        case=next(x for x in a.source_cases() if x["id"]=="F_ZERO")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"printer.dat"
            p.write_bytes(b" 123 \r\n 0\r\n 0\r\n-1\r\n 0\r\n")
            must_fail(lambda:a.validate_link(case,{"entries":{
                84:{"address":124,"value_hex":"00 00 00 00 00"}}},p),
                "AT_T_ADDRESS_MISMATCH")
    def test_changed_real_bytes(self):
        case=next(x for x in a.source_cases() if x["id"]=="F_ONE")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"printer.dat"
            p.write_bytes(b" 123 \r\n 1\r\n 2\r\n-1\r\n 0\r\n")
            must_fail(lambda:a.validate_link(case,{"entries":{
                84:{"address":123,"value_hex":"00 00 00 00 80"}}},p),
                "FIXED_REAL5_NOT_MEASURED")
    def test_absent_and_ambiguous_printer(self):
        for b in (b"",b"1 2\n",b"HELLO\n",b"1\n2\n"):
            must_fail(lambda b=b:a.numbers(b,1),
                      "PRINTER_CARDINALITY" if b in (b"",b"1\n2\n") else "PRINTER_AMBIGUOUS")
    def test_unsealed_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"manifest.json").write_bytes(b"{}\n")
            must_fail(lambda:a.verify(root,"a"*40,"b"*64),"EXTERNAL_SEAL_REQUIRED")
    def test_head_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            raw=a.canonical({"head":"a"*40})
            (root/"manifest.json").write_bytes(raw)
            must_fail(lambda:a.verify(root,"b"*40,a.sha(raw)),"HEAD_MISMATCH")
    def test_rom_and_image_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            base={"schema":1,"mission":"CLK-04-A1","head":"a"*40,
                  "status":"ACQUIRED_PENDING_PNG_REVIEW",
                  "corpus_sha256":a.SOURCE_SHA,**a.PINS,
                  "observation_class":"CPC6128_CAPRICE32_ROM_BACKED",
                  "rom_archived":False,"snapshot_archived":False}
            for field in ("rom_sha256","caprice_commit","image"):
                bad=dict(base)
                bad[field]="0"*64
                raw=a.canonical(bad)
                (root/"manifest.json").write_bytes(raw)
                must_fail(lambda:a.verify(root,"a"*40,a.sha(raw)),"PROVENANCE_MISMATCH")
    def test_session_omitted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            body={"schema":1,"mission":"CLK-04-A1","head":"a"*40,
                  "status":"ACQUIRED_PENDING_PNG_REVIEW",
                  "corpus_sha256":a.SOURCE_SHA,**a.PINS,
                  "observation_class":"CPC6128_CAPRICE32_ROM_BACKED",
                  "rom_archived":False,"snapshot_archived":False,"sessions":{"original":{}}}
            raw=a.canonical(body)
            (root/"manifest.json").write_bytes(raw)
            must_fail(lambda:a.verify(root,"a"*40,a.sha(raw)),"SESSIONS_MISSING")
    def test_source_sha_tamper(self):
        with mock.patch.object(a,"SOURCE_SHA","0"*64):
            must_fail(a.source_cases,"CORPUS_SHA_DRIFT")
    def test_missing_cfg_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            must_fail(lambda:a.prior.cfg_validate(Path(d)/"missing"),"CFG_MISSING")
    def test_sna_bad_header(self):
        # Parse must reject even if a fabricated memory window has a plausible name.
        with self.assertRaises((ValueError,a.prior.OracleError)):
            a.snapshot_window(bytes(256+128*1024),
                 a.source_cases()[0]["lines"],"known")

if __name__=="__main__":
    unittest.main()
