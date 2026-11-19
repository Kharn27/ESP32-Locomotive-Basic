#!/usr/bin/env python3
"""Falsifications HOST_ONLY; never treated as CPC evidence or replacements."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
mod_spec = importlib.util.spec_from_file_location(
    "clk04_a7_audit", ROOT / "tools/clk_04_a7_a2_print_audit.py")
a7 = importlib.util.module_from_spec(mod_spec)
mod_spec.loader.exec_module(a7)


def make_zip(data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, value in data.items():
            z.writestr(name, value)
    return buf.getvalue()


def mock_stop():
    # 1 fake value, NOT a CPC reading. 9-byte RAM structure is deliberately
    # simple so offset/type/address corruption can be falsified independently.
    raw = b"\x00\x00\xc1\x04\x00\x00\x00\x00\x81"
    return raw, {
        "pointers": {"program_end": 999, "scalar_start": 1000,
                     "array_start": 1009, "array_end": 1009},
        "ram_window_start": 1000, "ram_window_end": 1009,
        "ram_window_sha256": a7.sha(raw),
        "entries": {"65": {"entry_offset": 0, "address": 1004,
                           "name_byte": 193, "type_byte": 4,
                           "link_hex": "00 00", "value_hex": "00 00 00 00 81"}}
    }


def mock_case():
    program = ["10 A!=1", "90 STOP", "100 PRINT #8,@A!",
               "110 PRINT #8,A!", "120 END"]
    case = {"id": "D0_MOCK", "tier": "D0", "lines": program,
            "items": [{"variable": "A!", "value": "1", "arithmetic": None,
                       "arithmetic_variable": None}], "printer_numeric_count": 2}
    window, stop = mock_stop()
    pre = "original/D0_MOCK"
    content = {
        pre + "/window.bin": window,
        pre + "/stop.json": json.dumps(stop).encode(),
        pre + "/run/printer.dat": b" 1004 \r\n 1 \r\n",
        pre + "/list/printer.dat": ("\r\n".join(program) + "\r\n").encode(),
        pre + "/run/autocmd.json": json.dumps({"commands": [
            "MODE 1", "NEW", *program, "RUN", "STOP_SNAPSHOT", "CONT"]}).encode(),
        pre + "/program.bin": b"demo",
        pre + "/stop_program.bin": b"demo",
    }
    comparison = {("original", case["id"], "A!"): {
        "value_requested": "1", "address": 1004,
        "cpc_print": "1", "cpc_real5_hex": "00 00 00 00 81"}}
    return content, case, comparison


class A7FalsificationTests(unittest.TestCase):
    def assert_reject(self, f, code):
        with self.assertRaisesRegex(a7.AuditError, code):
            f()

    def test_original_source_corpus_hash(self):
        path = ROOT / "tests/fixtures/cpc6128/clk_04_a2_numeric/corpus.json"
        # The corpus is fetched from the repository at checkout, not test-generated.
        self.assertEqual(len(a7.check_corpus(path.read_bytes())), 11)
        corrupt = path.read_bytes().replace(b'"8388607"', b'"8388606"')
        self.assert_reject(lambda: a7.check_corpus(corrupt), "CORPUS_SHA_DRIFT")

    def test_zip_pins_reject_byte_mutation_and_substitution(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "raw.zip"
            baseline = make_zip({"a.txt": b"HOST_ONLY"})
            path.write_bytes(baseline)
            self.assertEqual(a7.zip_verified(path, a7.sha(baseline), 2000).namelist(),
                             ["a.txt"])
            path.write_bytes(baseline + b"extra")
            self.assert_reject(lambda: a7.zip_verified(path, a7.sha(baseline), 2000),
                               "ZIP_SHA_DRIFT")
            path.write_bytes(make_zip({"a.txt": b"SUBSTITUTION"}))
            self.assert_reject(lambda: a7.zip_verified(path, a7.sha(baseline), 2000),
                               "ZIP_SHA_DRIFT")
            bad = make_zip({"../outside": b"x"})
            path.write_bytes(bad)
            self.assert_reject(lambda: a7.zip_verified(path, a7.sha(bad), 2000),
                               "ZIP_UNSAFE_MEMBER")

    def test_inventoried_file_corruption_size_sha_and_membership(self):
        content = {"data/%03d" % i: b"HOST_ONLY" for i in range(360)}
        metadata = {name: {"bytes": len(data), "sha256": a7.sha(data)}
                    for name, data in content.items()}
        manifest = {"schema": 1, "mission": "CLK-04-A2", "head": a7.A2_HEAD,
                    "run_id": "42653720557", "caprice_commit": a7.CAPRICE,
                    "rom_sha256": a7.ROM, "image": a7.IMAGE,
                    "corpus_sha256": a7.A2_CORPUS_SHA,
                    "observation_class": "CPC6128_CAPRICE32_ROM_BACKED",
                    "rom_archived": False, "snapshot_archived": False,
                    "files": metadata}
        stamp = json.dumps(manifest).encode()
        raw = {"manifest.json": stamp, **content}
        self.assertEqual(len(a7.check_inventory(zipfile.ZipFile(
            io.BytesIO(make_zip(raw)), "r"), a7.sha(stamp))["files"]), 360)
        changed = dict(raw)
        changed["data/000"] = b"CHANGED!!"
        self.assert_reject(lambda: a7.check_inventory(zipfile.ZipFile(
            io.BytesIO(make_zip(changed)), "r"), a7.sha(stamp)), "INVENTORY_SHA")
        changed["data/000"] = b"SHORT"
        self.assert_reject(lambda: a7.check_inventory(zipfile.ZipFile(
            io.BytesIO(make_zip(changed)), "r"), a7.sha(stamp)), "INVENTORY_SIZE")
        changed = dict(raw)
        del changed["data/000"]
        self.assert_reject(lambda: a7.check_inventory(zipfile.ZipFile(
            io.BytesIO(make_zip(changed)), "r"), a7.sha(stamp)), "INVENTORY_MEMBERSHIP")
        for key, newval in (("head", "0"*40), ("rom_sha256", "0"*64),
                            ("caprice_commit", "1"*40), ("image", "BAD")):
            altered = dict(manifest, **{key: newval})
            altered_bytes = json.dumps(altered).encode()
            changed = dict(raw, **{"manifest.json": altered_bytes})
            self.assert_reject(lambda: a7.check_inventory(zipfile.ZipFile(
                io.BytesIO(make_zip(changed)), "r"), a7.sha(altered_bytes)),
                "MANIFEST_PROVENANCE")
        self.assert_reject(lambda: a7.check_inventory(zipfile.ZipFile(
            io.BytesIO(make_zip(raw)), "r"), "0"*64), "EXTERNAL_MANIFEST_SHA_DRIFT")

    def test_printer_crlf_cardinality_and_numeric_grammar(self):
        self.assertEqual(a7.lines(b" 1004 \r\n 1 \r\n", 2),
                         [b" 1004 \r\n", b" 1 \r\n"])
        for raw, count in ((b" 1 \n", 1), (b" 1 \r\nX", 1),
                           (b" 1 \r\n", 2), (b" 1.2x \r\n", 1),
                           (b" 1 \r\n\r\n", 1)):
            self.assert_reject(lambda raw=raw,count=count: a7.lines(raw,count),
                               "PRINTER_")

    def test_offset_address_type_value_and_print_mutations(self):
        content, case, comp = mock_case()
        prefix = "original/D0_MOCK"
        actual = a7.check_case(zipfile.ZipFile(io.BytesIO(make_zip(content))),
                               "original", case, comp)
        self.assertEqual([x["role"] for x in actual], ["address", "primary"])
        for path, modifier, code in (
            ("/run/printer.dat", lambda b:b.replace(b"1004", b"1005"),
             "PRINTER_ADDRESS_OR_ALIGNMENT"),
            ("/run/printer.dat", lambda b:b.replace(b" 1 ", b" 2 "),
             "REPORT_PRINTER_TEXT_DRIFT"),
            ("/run/printer.dat", lambda b:b.replace(b"\r\n", b"\n"),
             "PRINTER_CRLF"),
            ("/window.bin", lambda b:b[:3]+bytes([3])+b[4:],
             "STOP_WINDOW_POINTER_OR_SHA"),
        ):
            changed = dict(content)
            changed[prefix+path] = modifier(changed[prefix+path])
            self.assert_reject(lambda: a7.check_case(zipfile.ZipFile(
                io.BytesIO(make_zip(changed))), "original", case, comp), code)
        for property, changed_to in (("entry_offset",1),("address",1005),
                                     ("type_byte",5)):
            changed=dict(content)
            stop=json.loads(changed[prefix+"/stop.json"])
            stop["entries"]["65"][property]=changed_to
            changed[prefix+"/stop.json"]=json.dumps(stop).encode()
            self.assert_reject(lambda: a7.check_case(zipfile.ZipFile(
                io.BytesIO(make_zip(changed))), "original", case, comp),
                "STOP_RAM_ENTRY_OR_OFFSET")
        changed=dict(content)
        changed[prefix+"/run/autocmd.json"] = json.dumps(
            {"commands": ["MODE 1", "NEW", "BAD"]}).encode()
        self.assert_reject(lambda: a7.check_case(zipfile.ZipFile(
            io.BytesIO(make_zip(changed))), "original", case, comp),
            "AUTOCMD_PROGRAM_DRIFT")
        changed=dict(content)
        changed[prefix+"/list/printer.dat"] = b"BAD\r\n"
        self.assert_reject(lambda: a7.check_case(zipfile.ZipFile(
            io.BytesIO(make_zip(changed))), "original", case, comp),
            "BASIC_LIST_COUNT")

    def test_baseline_candidate_git_blobs_and_unsupported_unchanged(self):
        src=ROOT / "tools/clk_04_a4_numeric_lab.c"
        head=ROOT / "tools/clk_04_a4_numeric_lab.h"
        self.assertEqual(a7.github_blob_sha(src.read_bytes()), a7.A6_BLOBS["c"])
        self.assertEqual(a7.github_blob_sha(head.read_bytes()), a7.A6_BLOBS["h"])
        with tempfile.TemporaryDirectory() as td:
            for cc in ("gcc", "clang"):
                candidate = a7.Candidate(src, head, cc, td)
                self.assertEqual(candidate.compare(0, b" 0 \r\n")[0],
                                 "C99_CANDIDATE_MATCH")
                self.assertEqual(candidate.compare(0, b" 1 \r\n")[0],
                                 "C99_CANDIDATE_MISMATCH")
                self.assertEqual(candidate.compare(8388607, b" 8388607 \r\n"),
                                 ("C99_UNSUPPORTED", ""))
        with tempfile.TemporaryDirectory() as td:
            bad=Path(td) / "candidate.c"
            bad.write_bytes(src.read_bytes()+b"\n")
            self.assert_reject(lambda: a7.Candidate(bad, head, "gcc", td),
                               "A6_CANDIDATE_GIT_BLOB_DRIFT")

    def test_seal_head_and_session_rejection(self):
        fake = {"mission": "CLK-04-A2", "head": a7.A2_HEAD,
                "manifest_sha256": a7.A2_MANIFEST_SHA,
                "origin": "GitHub Actions acquisition job logs / output"}
        a7.check_seal(fake)
        for key, value in (("head", "0"*40), ("manifest_sha256", "0"*64),
                           ("mission", "BAD"), ("origin", "BAD")):
            self.assert_reject(lambda: a7.check_seal(dict(fake, **{key: value})),
                               "EXTERNAL_SEAL_DRIFT")
        cases = [{"id": "D0_01"}]
        def run(): return {"returncode": 0}
        original = {"boot": {"returncode": 0, "started_utc": "boot-A"},
                    "gate": {"short": run(), "long": run()},
                    "cases": {"D0_01": {"list": run(), "run": run()}}}
        repeated = json.loads(json.dumps(original))
        repeated["boot"]["started_utc"] = "boot-B"
        manifest = {"sessions": {"original": original, "repeat": repeated}}
        a7.check_sessions(manifest, cases)
        changed = json.loads(json.dumps(manifest))
        changed["sessions"]["repeat"]["boot"]["started_utc"] = "boot-A"
        self.assert_reject(lambda: a7.check_sessions(changed, cases),
                           "SESSIONS_NOT_DISTINCT")
        changed = json.loads(json.dumps(manifest))
        changed["sessions"]["repeat"]["cases"]["D0_01"]["run"]["returncode"] = 1
        self.assert_reject(lambda: a7.check_sessions(changed, cases),
                           "SESSION_INCOMPLETE")
        changed = json.loads(json.dumps(manifest))
        del changed["sessions"]["repeat"]
        self.assert_reject(lambda: a7.check_sessions(changed, cases),
                           "SESSION_SET")


if __name__ == "__main__":
    unittest.main()
