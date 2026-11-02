"""Offline-only contract tests; no CPC acquisition is simulated."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('j122', ROOT / 'tools/j1_22_a_integer_logical_oracle.py')
o = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(o)

class OracleContract(unittest.TestCase):
    def test_sources(self):
        self.assertEqual(len(o.check_sources()), 24)

    def test_raw_printer_parse_only(self):
        raw = b'VALUE= 3\r\n@@J122ERR@@ 0 , 0 \r\n10 A%=3\r\n'
        self.assertEqual(o.parse_output(raw), (b'VALUE= 3\r\n', 0, 0, b'10 A%=3\r\n'))

    def test_no_missing_or_duplicate_probe(self):
        for raw in (b'VALUE= 1\r\n', b'@@J122ERR@@1,0\r\n@@J122ERR@@2,0\r\n'):
            with self.subTest(raw=raw), self.assertRaises(o.Invalid):
                o.parse_output(raw)

    def test_truncated_probe_rejected(self):
        for raw in (b'@@J122ERR@@0,', b'@@J122ERR@@0,0\r\n'):
            with self.subTest(raw=raw), self.assertRaises(o.Invalid):
                o.parse_output(raw)

    def test_missing_and_partial_archive_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(o.Invalid):
                o.verify(root, permanent=True)
            (root / 'manifest.json').write_text('{}\n')
            with self.assertRaises(o.Invalid):
                o.verify(root, permanent=True)

    def test_source_corruption_on_temp_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            temporary = Path(temp) / 'fixture'
            shutil.copytree(o.DIR, temporary)
            corrupted = temporary / 'sources/a00_zero.bas'
            corrupted.write_bytes(corrupted.read_bytes() + b'X')
            old = o.DIR
            try:
                o.DIR = temporary
                with self.assertRaises(o.Invalid):
                    o.check_sources()
            finally:
                o.DIR = old

if __name__ == '__main__':
    unittest.main()
