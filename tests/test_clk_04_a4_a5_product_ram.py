#!/usr/bin/env python3
"""A5 isolated synthetic falsifiers: not a substitute for CPC/RAW evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/clk_04_a4_a5_product_ram.py"
S = importlib.util.spec_from_file_location("clk_04_a4_a5_product_ram", SCRIPT)
a5 = importlib.util.module_from_spec(S)
S.loader.exec_module(a5)


def rejected(call, label):
    with unittest.TestCase().assertRaisesRegex(a5.prior.OracleError, label):
        call()


class Corpus(unittest.TestCase):
    def test_freeze_and_separate_capture_sources(self):
        cases = a5.source_cases()
        self.assertEqual([int(c["value"]) for c in cases], list(a5.VALUES))
        self.assertEqual(a5.sha(a5.read(a5.CORPUS)), a5.CORPUS_SHA)
        self.assertEqual([c["id"] for c in cases],
                         ["P%02d" % j for j in range(1, 9)])
        self.assertEqual([c["printer_numeric_count"] for c in cases],
                         [5, 5, 5, 10, 10, 10, 10, 10])
        for c in cases:
            self.assertIn("20 U!=T!*2", c["lines"])
            self.assertEqual(c["lines"][0], "10 T!=" + c["value"])
            self.assertLess(c["lines"].index("90 STOP"),
                            c["lines"].index("100 PRINT #8,@T!"))
            self.assertEqual(c["arithmetic"],
                             a5.a4.alternative(int(c["value"])))
            self.assertNotIn("TIME", "\n".join(c["lines"]))
        a5.self_test()

    def test_corrupt_corpus_sha_and_source_even_after_reseal(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "corpus.json"
            obj = json.loads(a5.read(a5.CORPUS))
            raw = a5.canonical(obj)
            p.write_bytes(raw)
            self.assertEqual(a5.sha(raw), a5.CORPUS_SHA)
            bad = copy.deepcopy(obj)
            bad["cases"][4]["lines"][1] = "20 U!=T!*3"
            p.write_bytes(a5.canonical(bad))
            with mock.patch.object(a5, "CORPUS", p):
                rejected(a5.source_cases, "A5_CORPUS_SHA_DRIFT")
                with mock.patch.object(a5, "CORPUS_SHA", a5.sha(a5.read(p))):
                    rejected(a5.source_cases, "A5_SOURCE_CONSTRUCTION")
            bad = copy.deepcopy(obj)
            bad["cases"][6]["arithmetic"] = "2^30"
            p.write_bytes(a5.canonical(bad))
            with mock.patch.object(a5, "CORPUS", p), \
                 mock.patch.object(a5, "CORPUS_SHA", a5.sha(a5.read(p))):
                rejected(a5.source_cases, "A5_SOURCE_CONSTRUCTION")


class RawAuthenticity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.head = "a" * 40

    def write_manifest(self, overrides=None):
        obj = {"schema": 1, "mission": "CLK-04-A5",
               "status": a5.RAW_STATUS, "head": self.head,
               "corpus_sha256": a5.CORPUS_SHA, **a5.PINS,
               "observation_class": "CPC6128_CAPRICE32_ROM_BACKED",
               "rom_archived": False, "snapshot_archived": False,
               "sessions": {"original": {}, "repeat": {}},
               "files": {"original/P01/fake": {"size": 3, "sha256": "0" * 64}}}
        if overrides:
            obj.update(overrides)
        (self.out / "manifest.json").write_bytes(a5.canonical(obj))
        return a5.sha(a5.read(self.out / "manifest.json")), obj

    def valid(self, seal):
        with mock.patch.object(a5.prior, "inventory", return_value={
                "original/P01/fake": {"size": 3, "sha256": "0" * 64}}):
            return a5.authenticated_manifest(self.out, self.head, seal)

    def test_manifest_seal_and_head_rom_session_fail_closed(self):
        seal, _ = self.write_manifest()
        self.assertEqual(self.valid(seal)["head"], self.head)
        self.write_manifest({"head": "b" * 40})
        rejected(lambda: self.valid(seal), "A5_EXTERNAL_MANIFEST_SEAL")
        badcases = [
            ({"head": "b" * 40}, "A5_HEAD_MISMATCH"),
            ({"rom_sha256": "f" * 64}, "A5_ROM_IMAGE_OR_SOURCE"),
            ({"image": "evil"}, "A5_ROM_IMAGE_OR_SOURCE"),
            ({"corpus_sha256": "f" * 64}, "A5_ROM_IMAGE_OR_SOURCE"),
            ({"sessions": {"original": {}}}, "A5_INDEPENDENT_SESSIONS"),
            ({"sessions": {"original": {}, "repeat": {}, "third": {}}},
             "A5_INDEPENDENT_SESSIONS"),
            ({"snapshot_archived": True}, "A5_ROM_IMAGE_OR_SOURCE"),
            ({"rom_archived": True}, "A5_ROM_IMAGE_OR_SOURCE"),
        ]
        for override, error in badcases:
            with self.subTest(forgery=override):
                newseal, _ = self.write_manifest(override)
                rejected(lambda: self.valid(newseal), error)

    def test_archive_member_and_size_digest_mutation(self):
        seal, _ = self.write_manifest()
        with mock.patch.object(a5.prior, "inventory", return_value={
                "original/P01/fake": {"size": 4, "sha256": "0" * 64}}):
            rejected(lambda: a5.authenticated_manifest(
                self.out, self.head, seal), "A5_RAW_INVENTORY")
        with mock.patch.object(a5.prior, "inventory", return_value={
                "original/P01/fake": {"size": 3, "sha256": "1" * 64}}):
            rejected(lambda: a5.authenticated_manifest(
                self.out, self.head, seal), "A5_RAW_INVENTORY")
        for member in ("original/P01/capture.sna", "original/P01/cpc6128.rom"):
            override = {"files": {member: {"size": 3, "sha256": "0" * 64}}}
            seal, _ = self.write_manifest(override)
            with mock.patch.object(a5.prior, "inventory",
                                   return_value=override["files"]):
                rejected(lambda: a5.authenticated_manifest(
                    self.out, self.head, seal), "A5_RAW_INVENTORY")

    def test_t_u_ram_bytes_are_distinct_and_product_falsification_detectable(self):
        # The scalar descriptor is 2 opaque bytes, name|0x80, type 04, REAL5.
        window = bytes([0, 0, 0xd4, 4, 0, 0, 0, 0, 0,
                        0, 0, 0xd5, 4, 0, 0, 0, 0, 0x82])
        entries = a5.a1.check_window(window, 0x3000, [ord("T"), ord("U")])
        self.assertEqual(entries[ord("T")]["type_byte"], 4)
        self.assertEqual(entries[ord("U")]["value_hex"], "00 00 00 00 82")
        forged = bytearray(window)
        forged[9 + 7] ^= 1  # Only the REAL5 U! product byte.
        reread = a5.a1.check_window(forged, 0x3000, [ord("T"), ord("U")])
        self.assertNotEqual(entries, reread)
        self.assertEqual(entries[ord("T")], reread[ord("T")])
        forged = bytearray(window)
        forged[9 + 3] = 2
        rejected(lambda: a5.a1.check_window(
            forged, 0x3000, [ord("T"), ord("U")]), "RAM_SCALAR_IDENTITY_OR_TYPE")

    def test_read_printer_address_guard_and_separate_raw_product(self):
        case = a5.source_cases()[0]
        stop = {"entries": {
            "84": {"address": 1234, "type_byte": 4,
                   "value_hex": "00 00 00 00 00"},
            "85": {"address": 1243, "type_byte": 4,
                   "value_hex": "00 00 00 00 00"}}}
        raw = b" 1234 \r\n 1243 \r\n 0 \r\n 0 \r\n 0 \r\n"
        p = self.out / "printer.dat"
        p.write_bytes(raw)
        observed = a5.read_values(case, stop, p)
        self.assertEqual(observed["RAW_INPUT_REAL5_CPC"]["hex"],
                         "00 00 00 00 00")
        self.assertEqual(observed["RAW_PRODUCT_REAL5_CPC"]["hex"],
                         "00 00 00 00 00")
        self.assertEqual(len(observed["RAW_PRINT_CPC"]["full_printer_lines_hex"]),
                         5)
        p.write_bytes(raw.replace(b" 1243 ", b" 1244 "))
        rejected(lambda: a5.read_values(case, stop, p),
                 "A5_AT_ADDRESS_OR_TYPE")
        p.write_bytes(raw + b" 999 \r\n")
        rejected(lambda: a5.read_values(case, stop, p),
                 "PRINTER_CARDINALITY")


class CandidateIsNotOracle(unittest.TestCase):
    def test_product_mismatch_and_print_unsupported_both_explicit(self):
        rows = []
        lines = []
        for _ in range(2):
            for n in a5.VALUES:
                rows.append({"value_requested": str(n),
                    "RAW_INPUT_REAL5_CPC": {"hex": "00 00 00 00 00"},
                    "RAW_PRODUCT_REAL5_CPC": {"hex": "00 00 00 00 00"},
                    "RAW_PRINT_CPC": {"full_printer_lines_hex":
                                      ["00", "00", "00", "00", "00"]}})
                fields = [str(n), "0000000000", str(n * 2), "0000000000",
                          "-1", "0", "UNSUPPORTED", "UNSUPPORTED",
                          "UNSUPPORTED", "UNSUPPORTED"]
                lines.append("\t".join(fields))
        proc = mock.Mock(returncode=0,
                         stdout=("\n".join(lines) + "\n").encode(),
                         stderr=b"")
        with mock.patch.object(a5.subprocess, "run", return_value=proc), \
             mock.patch.object(Path, "is_file", return_value=True):
            match = a5.compare_candidate(copy.deepcopy(rows), Path("/bin/candidate"))
            self.assertEqual(match["CANDIDATE_MATCH"], 16)
            self.assertEqual(match["CANDIDATE_PRINT_UNSUPPORTED"], 16)
            forged = copy.deepcopy(rows)
            forged[8]["RAW_PRODUCT_REAL5_CPC"]["hex"] = "00 00 00 01 00"
            mismatch = a5.compare_candidate(forged, Path("/bin/candidate"))
            self.assertEqual(mismatch["CANDIDATE_MISMATCH"], 1)
            self.assertEqual(forged[8]["C99_CANDIDATE"]["product_status"],
                             "CANDIDATE_MISMATCH")
            self.assertEqual(forged[8]["C99_CANDIDATE"]["input_status"],
                             "CANDIDATE_MATCH")

    def test_no_candidate_invoked_until_archive_replay_authenticated(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(a5, "compare_candidate") as candidate:
                rejected(lambda: a5.verify(Path(temp), "a" * 40, "0" * 64,
                                            Path("/bin/false")),
                         "ABSENT_OR_SYMLINK")
                candidate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
