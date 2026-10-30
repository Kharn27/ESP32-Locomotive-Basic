#!/usr/bin/env python3
"""J1.19-A OFFLINE contract/falsification tests; no simulated CPC results."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
from unittest import TestCase, main, mock
import tempfile
import sys

ROOT=Path(__file__).resolve().parents[1]
modpath=ROOT/'tools/j1_19_a_paper_oracle.py'
spec=importlib.util.spec_from_file_location('j119',modpath)
paper=importlib.util.module_from_spec(spec)
spec.loader.exec_module(paper)


def blank_archive(tmp):
    """DUMMY INVALID archive only to check resistance; never CPC oracle."""
    root=Path(tmp)/'TEST_SYNTHETIC_NOT_A_CPC_ORACLE'
    root.mkdir()
    files=paper.file_map()
    for name in files:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'TEST_SYNTHETIC')
    m={'schema_version':1,'phase':paper.PHASE,'origin':'CAPRICE32_REAL_ONLY',
       'cases':list(paper.CASES),'sessions':list(paper.SESSIONS),
       'full_snapshots_archived':False,'native_changes':False,
       'oracle':{'rom_sha256':paper.ROM_SHA256,'caprice_commit':paper.CAPRICE_COMMIT,'ghcr':paper.GHCR},
       'acquisition_head':'a'*40,
       'files':{name:paper.digest((root/name).read_bytes()) for name in files}}
    (root/'manifest.json').write_bytes(paper.canonical(m))
    return root,m


class TestCorpus(TestCase):
    def test_has_12_distinct_experiments(self):
        self.assertEqual(len(paper.CASES),12)
        self.assertEqual(len(set(paper.CASES)),12)
        self.assertEqual(len(paper.BASIC),8)
        self.assertEqual(len(paper.SCENARIOS),4)

    def test_all_sources_exact_and_ordered(self):
        self.assertTrue(paper.check_sources())
        for case in paper.CASES:
            src=paper.source(case)
            self.assertTrue(src.endswith(b'\n'))
            lines=[int(x.split(b' ',1)[0]) for x in src.splitlines()]
            self.assertEqual(lines,sorted(lines))
            self.assertEqual(len(lines),len(set(lines)))

    def test_all_candidate_boundaries_preserved_not_assumed(self):
        self.assertEqual(set(paper.BASIC.values()),{'0','1','2','3','4','15','16','-1'})
        for case,n in paper.BASIC.items():
            self.assertIn(f'20 PAPER {n}'.encode(),paper.source(case))

    def test_programmed_colour_bank(self):
        self.assertEqual(paper.SETUP[0],'MODE 1')
        for statement in ('INK 0,0','INK 1,26','INK 2,6','INK 3,18','PAPER 0','PEN 1','CLS','NEW'):
            self.assertIn(statement,paper.SETUP)

    def test_visual_stimuli_include_four_discriminants(self):
        self.assertIn('PRINT', ' '.join(paper.SCENARIOS['SPRINT']))
        self.assertEqual(' '.join(paper.SCENARIOS['SCHANGE']).count('PRINT'),2)
        self.assertIn('CLS',' '.join(paper.SCENARIOS['SCLS']))
        self.assertIn('INK 2,6',' '.join(paper.SCENARIOS['SINK']))

    def test_direct_error_candidates_are_extra(self):
        self.assertEqual(paper.DIRECT_CASES,{'D16':'PAPER 16','DN1':'PAPER -1'})
        self.assertEqual(len(paper.file_map()),264)

    def test_static_hypotheses_are_not_observations(self):
        self.assertIsNone(paper.SEALED_MANIFEST_SHA256)
        self.assertFalse(paper.SEALED_FILE_SHA256)
        self.assertNotIn(b'BA 20',paper.source('P01'))

    def test_roi_histogram_real_bytes_not_colour_guess(self):
        synthetic=[bytearray(768*3) for _ in range(540)]
        synthetic[305][64*3:64*3+3]=bytes([255,0,0])
        h=paper.histogram(synthetic,paper.ROI)
        self.assertEqual(h['255,0,0'],1)
        self.assertEqual(h['0,0,0'],2015)

    def test_roi_outside_image_rejected(self):
        with self.assertRaisesRegex(paper.Invalid,'ROI_RANGE'):
            paper.histogram([bytearray(3)],paper.ROI)


class TestFailClosed(TestCase):
    def test_missing_real_archive_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(paper.Invalid,'ARCHIVE_ABSENT'):
                paper.verify(Path(t),permanent=True)

    def test_fake_manifest_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'manifest.json').write_bytes(b'{}')
            with self.assertRaisesRegex(paper.Invalid,'MANIFEST_PROVENANCE'):
                paper.verify(root,permanent=True)

    def test_invalid_or_unreachable_git_ancestor_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root,_=blank_archive(t)
            with mock.patch.object(paper,'is_ancestor',return_value=False):
                with self.assertRaisesRegex(paper.Invalid,'FALSE_HEAD_OR_ANCESTRY'):
                    paper.verify(root,permanent=True)

    def test_missing_file_rejected_not_inferred_from_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            root,_=blank_archive(t)
            (root/'original/P00/program.bin').unlink()
            with mock.patch.object(paper,'is_ancestor',return_value=True):
                with self.assertRaisesRegex(paper.Invalid,'FILE_INVENTORY'):
                    paper.verify(root)

    def test_extra_file_and_false_archive_insert_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root,_=blank_archive(t)
            (root/'original/P00/forged.png').write_bytes(b'fake')
            with mock.patch.object(paper,'is_ancestor',return_value=True):
                with self.assertRaisesRegex(paper.Invalid,'FILE_INVENTORY'):
                    paper.verify(root)

    def test_permanent_never_trusts_manifest_self_hashes(self):
        with tempfile.TemporaryDirectory() as t:
            root,_=blank_archive(t)
            with mock.patch.object(paper,'is_ancestor',return_value=True):
                with self.assertRaisesRegex(paper.Invalid,'EXTERNAL_SEAL_NOT_ACQUIRED'):
                    paper.verify(root,permanent=True)

    def test_coordinated_fake_archive_and_updated_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root,m=blank_archive(t)
            name='repeat/P16/program.bin'
            (root/name).write_bytes(b'FORGED_RAM_AND_CPC_ERROR')
            m['files'][name]=paper.digest((root/name).read_bytes())
            (root/'manifest.json').write_bytes(paper.canonical(m))
            with mock.patch.object(paper,'is_ancestor',return_value=True):
                with self.assertRaisesRegex(paper.Invalid,'EXTERNAL_SEAL_NOT_ACQUIRED'):
                    paper.verify(root,permanent=True)

    def test_unsealed_mutation_rejected_by_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            root,_=blank_archive(t)
            (root/'repeat/P03/run/screen.png').write_bytes(b'PNG_TAMPER')
            with mock.patch.object(paper,'is_ancestor',return_value=True):
                with self.assertRaisesRegex(paper.Invalid,'SHA_repeat/P03/run/screen.png'):
                    paper.verify(root,permanent=False)

    def test_wrong_manifest_inventory_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root,m=blank_archive(t)
            m['files'].pop('repeat/SINK/capture.json')
            (root/'manifest.json').write_bytes(paper.canonical(m))
            with mock.patch.object(paper,'is_ancestor',return_value=True):
                with self.assertRaisesRegex(paper.Invalid,'MANIFEST_FILES'):
                    paper.verify(root)

    def test_forged_ancestor_syntax_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root,m=blank_archive(t)
            m['acquisition_head']='a'*39
            (root/'manifest.json').write_bytes(paper.canonical(m))
            with self.assertRaisesRegex(paper.Invalid,'FALSE_HEAD_OR_ANCESTRY'):
                paper.verify(root)

    def test_already_existing_capture_target_is_protected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'archive';root.mkdir()
            sentinel=root/'important.txt';sentinel.write_text('NO_OVERWRITE')
            with self.assertRaisesRegex(paper.Invalid,'OUTPUT_ALREADY_EXISTS'):
                paper.acquire(Path('/nonexistent'),root,'0'*40)
            self.assertEqual(sentinel.read_text(),'NO_OVERWRITE')


if __name__=='__main__':
    main()
