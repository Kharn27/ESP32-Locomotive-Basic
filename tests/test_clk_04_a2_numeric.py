"""CLK-04-A2: synthetic structural negatives, NEVER a CPC acquisition."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import clk_04_a2_numeric as model
import clk_04_a2_oracle as a2


def rejected(fn, code):
    try:
        fn()
    except (a2.prior.OracleError,ValueError,TypeError,KeyError) as exc:
        if code not in str(exc):
            raise AssertionError("WRONG_REJECTION: "+str(exc))
    else:
        raise AssertionError("FORGED_DATA_ACCEPTED: "+code)


class CandidateModel(unittest.TestCase):
    def test_integer_samples_and_a1_regression(self):
        a1={0:"00 00 00 00 00",1:"00 00 00 00 81",
            5256:"00 00 40 24 8D",50376:"00 00 C8 44 90"}
        for n,hx in a1.items():
            self.assertEqual(model.encode_uint32(n),bytes.fromhex(hx))
            self.assertEqual(model.decode_nonnegative_integer(bytes.fromhex(hx)),n)

    def test_all_corpus_values_roundtrip(self):
        values=[int(i["value"]) for c in a2.source_cases() for i in c["items"]]
        self.assertEqual(values,a2.mandatory_values())
        self.assertEqual(len(values),37)
        for n in values:
            self.assertEqual(model.decode_nonnegative_integer(
                model.encode_uint32(n)),n)

    def test_boundaries_and_neighbor_distinctions(self):
        for n in (23,24,30,31):
            raw=[model.encode_uint32(2**n+delta) for delta in (-1,0,1)]
            self.assertEqual(len(set(raw)),3)
        self.assertNotEqual(model.encode_uint32(4294967294),
                            model.encode_uint32(4294967295))

    def test_rejected_input_types(self):
        for item in (True,False,1.0,DecimalFake(),"5",None,bytearray(b"5")):
            rejected(lambda item=item:model.encode_uint32(item),
                     "A2_INPUT_NOT_PLAIN_INTEGER")

    def test_out_of_uint32(self):
        for item in (-1,-999,4294967296,2**99):
            rejected(lambda item=item:model.encode_uint32(item),
                     "A2_INPUT_OUTSIDE_UINT32")

    def test_decoder_rejects_malformed_type(self):
        for raw in (None,bytearray(5),b"",b"\0"*4,b"\0"*6):
            rejected(lambda raw=raw:model.decode_nonnegative_integer(raw),
                     "A2_REAL5_EXPECTS_FIVE_BYTES")

    def test_decoder_rejects_negative_and_fraction(self):
        rejected(lambda:model.decode_nonnegative_integer(
            bytes.fromhex("00 00 00 80 81")),"A2_REAL5_SIGN_NOT_SUPPORTED")
        rejected(lambda:model.decode_nonnegative_integer(
            bytes.fromhex("00 00 00 00 80")),"A2_REAL5_EXPONENT_UNSUPPORTED")
        rejected(lambda:model.decode_nonnegative_integer(
            bytes.fromhex("01 00 00 00 81")),"A2_REAL5_NOT_INTEGER_UINT32")

    def test_model_self_test(self):
        model.self_test()


class DecimalFake:
    pass


class CorpusAndPrinter(unittest.TestCase):
    def test_sealed_corpus_and_independent_methods(self):
        groups=a2.source_cases()
        self.assertEqual(len(groups),11)
        self.assertEqual(sum(i["arithmetic"] is not None for c in groups
                             for i in c["items"]),14)
        for c in groups:
            self.assertEqual(c["lines"],a2.source_lines(c["items"]))

    def test_corpus_tamper_rejected(self):
        with mock.patch.object(a2,"SOURCE_SHA","0"*64):
            rejected(a2.source_cases,"CORPUS_SHA_DRIFT")

    def test_wrong_print_cardinality_or_syntax(self):
        for b, code in ((b"","PRINTER_CARDINALITY"),
                        (b"1\n2\n","PRINTER_CARDINALITY"),
                        (b"ABC\n","PRINTER_AMBIGUOUS"),
                        (b"1 2\n","PRINTER_AMBIGUOUS")):
            rejected(lambda b=b:a2.decimal_numbers(b,1),code)

    def test_scientific_not_host_float(self):
        self.assertEqual(
            [str(v) for v in a2.decimal_numbers(b" 4.2949673E+09\r\n -1\r\n",2)],
            ["4.2949673E+9","-1"])

    def test_accurate_variable_address_and_original_ram(self):
        case=a2.source_cases()[0]
        entries={}
        raw=b""
        for j,item in enumerate(case["items"]):
            label=ord(item["variable"][0])
            entry=bytes((0,0,label|0x80,4,0,0,0,0,0x81))
            entries[str(label)]={"address":0x400+9*j+4,
                "value_hex":entry[4:9].hex(" ").upper()}
            raw+=entry
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"printer.dat"
            data=b"".join(("%d\n%d\n"%(entries[str(ord(i["variable"][0]))]["address"],
                              int(i["value"]))).encode()
                         for i in case["items"])
            path.write_bytes(data)
            result=a2.read_values(case,{"entries":entries},path)
            self.assertEqual(result[0]["value_requested"],"0")
            self.assertEqual(len(result),4)
            self.assertEqual(len(a2.a1.check_window(raw,0x400,list(
                map(lambda s:ord(s["variable"][0]),case["items"])))),4)
            path.write_bytes(data.replace(b"1028",b"1029",1))
            rejected(lambda:a2.read_values(case,{"entries":entries},path),
                     "AT_VARIABLE_ADDRESS_MISMATCH")

    def test_wrong_type_and_address_window(self):
        rejected(lambda:a2.a1.check_window(
            bytes.fromhex("00 00 C1 05 00 00 00 00 81"),0x400,[65]),
            "RAM_SCALAR_IDENTITY")
        rejected(lambda:a2.a1.check_window(bytes(8),0x400,[65]),
            "RAM_WINDOW_INVALID")

    def test_sna_truncation(self):
        c=a2.source_cases()[0]
        with self.assertRaises((ValueError,a2.prior.OracleError,IndexError)):
            a2.snapshot_window(bytes(256+128*1024),c["lines"],c["items"])

    def test_oracle_self_test(self):
        a2.self_test()


class ProvenanceNegatives(unittest.TestCase):
    def test_external_seal_required(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            (path/"manifest.json").write_bytes(b"{}\n")
            rejected(lambda:a2.verify(path,"a"*40,"b"*64),
                     "EXTERNAL_SEAL_REQUIRED")

    def test_head_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            body=a2.canonical({"head":"a"*40})
            (path/"manifest.json").write_bytes(body)
            rejected(lambda:a2.verify(path,"b"*40,a2.sha(body)),
                     "HEAD_MISMATCH")

    def test_rom_pin_config_and_image_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            template={"schema":1,"mission":"CLK-04-A2","head":"a"*40,
                "status":"ACQUIRED_PENDING_PNG_REVIEW",
                "corpus_sha256":a2.SOURCE_SHA,**a2.PINS,
                "observation_class":"CPC6128_CAPRICE32_ROM_BACKED",
                "rom_archived":False,"snapshot_archived":False}
            for key in ("rom_sha256","caprice_commit","image"):
                doc={**template,key:"WRONG"}
                blob=a2.canonical(doc)
                (path/"manifest.json").write_bytes(blob)
                rejected(lambda:a2.verify(path,"a"*40,a2.sha(blob)),
                         "PROVENANCE_MISMATCH")

    def test_missing_second_session(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            doc={"schema":1,"mission":"CLK-04-A2","head":"a"*40,
                 "status":"ACQUIRED_PENDING_PNG_REVIEW",
                 "corpus_sha256":a2.SOURCE_SHA,**a2.PINS,
                 "observation_class":"CPC6128_CAPRICE32_ROM_BACKED",
                 "rom_archived":False,"snapshot_archived":False,
                 "sessions":{"original":{}}}
            blob=a2.canonical(doc)
            (path/"manifest.json").write_bytes(blob)
            rejected(lambda:a2.verify(path,"a"*40,a2.sha(blob)),
                     "SESSIONS_MISSING")

    def test_missing_printer_config_or_screens_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            rejected(lambda:a2.prior.cfg_validate(path/"missing.cfg"),
                     "CFG_MISSING")
            rejected(lambda:a2.cfg_process(path,{"returncode":0,
                     "wall_seconds":1,"started_utc":"2026-11-09T00:00:00+00:00"}),
                     "PROCESS_PROVENANCE")


if __name__=="__main__":
    unittest.main()
