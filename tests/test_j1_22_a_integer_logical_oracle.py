"""Offline-only contract tests; no CPC acquisition is simulated."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

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

    def test_provenance_original_head_still_accepted(self):
        original = o.EXTERNAL_ACQUISITION_HEAD
        with mock.patch.object(o, 'head_is_ancestor', side_effect=lambda h: h == original):
            self.assertTrue(o.provenance_is_authorized(original, permanent=True))
            self.assertTrue(o.provenance_is_authorized(original, permanent=False))

    def test_provenance_post_squash_exact_integration_accepted(self):
        original = o.EXTERNAL_ACQUISITION_HEAD
        with mock.patch.object(o, 'head_is_ancestor',
                               side_effect=lambda h: h == o.SQUASH_INTEGRATION_SHA) as ancestor:
            self.assertTrue(o.provenance_is_authorized(original, permanent=True))
            self.assertEqual(ancestor.call_args_list,
                             [mock.call(original), mock.call(o.SQUASH_INTEGRATION_SHA)])

    def test_provenance_post_squash_is_not_unsealed_escape(self):
        original = o.EXTERNAL_ACQUISITION_HEAD
        with mock.patch.object(o, 'head_is_ancestor',
                               side_effect=lambda h: h == o.SQUASH_INTEGRATION_SHA) as ancestor:
            self.assertFalse(o.provenance_is_authorized(original, permanent=False))
            ancestor.assert_called_once_with(original)

    def test_provenance_detached_and_unrelated_refused(self):
        with mock.patch.object(o, 'head_is_ancestor', return_value=False):
            self.assertFalse(o.provenance_is_authorized(
                o.EXTERNAL_ACQUISITION_HEAD, permanent=True))
            self.assertFalse(o.provenance_is_authorized(
                o.EXTERNAL_ACQUISITION_HEAD, permanent=False))

    def test_provenance_fake_manifest_head_never_inherits_squash(self):
        with mock.patch.object(o, 'head_is_ancestor', return_value=True) as ancestor:
            for invalid in ('0' * 40, 'f' * 40, '123', None):
                with self.subTest(invalid=invalid):
                    self.assertFalse(o.provenance_is_authorized(
                        invalid, permanent=True))
            ancestor.assert_not_called()

    def test_provenance_wrong_squash_anchor_cannot_pass(self):
        original = o.EXTERNAL_ACQUISITION_HEAD
        with mock.patch.object(o, 'head_is_ancestor',
                               side_effect=lambda h: h == 'e' * 40):
            self.assertFalse(o.provenance_is_authorized(original, permanent=True))

    def test_provenance_requires_pinned_original_even_if_false_head_ancestor(self):
        with mock.patch.object(o, 'head_is_ancestor', return_value=True):
            self.assertFalse(o.provenance_is_authorized('e' * 40, permanent=True))
            self.assertTrue(o.provenance_is_authorized('e' * 40, permanent=False))


if __name__ == '__main__':
    unittest.main()
