"""C6-B2-B host-only adversarial fixtures. NEVER an Xtensa build result."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

CI = Path(__file__).resolve().parents[1] / 'tools' / 'ci'
sys.path.insert(0, str(CI))
# This test imports the frozen C5 verifier from the actual repository in GH CI.
import hw4_mem_c6_b2b as c


def cell(iram=67551, dram=54864, bss=43792, binhash='f'*64,
         sdk='e'*64):
    return {'iram':iram,'dram':dram,'bss':bss,'flash_text':126000,
            'flash_rodata':40000,'bin_sha256':binhash,'elf_sha256':'c'*64,
            'sdkconfig':sdk,'gcc':'gcc 14.2.0','ld':'ld 2.43.1',
            'idf':'ESP-IDF v5.5.6','docker_image_id':'sha256:'+'a'*64}


def matrix():
    return {label:{'spi40':cell(),
                   'spi20':cell(binhash='d'*64)} for label in c.LABELS}


class C6B2BHost(unittest.TestCase):
    def test_budget_exact(self):
        self.assertEqual(c.MAX_BUILDS,8)
        self.assertEqual(len(c.LABELS)*len(c.VARIANTS),8)
        self.assertEqual(set(c.PAIRS),{'PR_INCREMENTAL','INTEGRATION_CANDIDATE'})

    def test_pair_pass_not_other_pair(self):
        m=matrix(); m['candidate']['spi40']['iram']+=1
        m['candidate']['spi20']['iram']+=1
        self.assertEqual(c.decide_pair(m,'base','head')['verdict'],'PASS')
        self.assertEqual(c.decide_pair(m,'main','candidate')['verdict'],'FAIL')

    def test_other_pair_pass_not_pr(self):
        m=matrix(); m['head']['spi40']['dram']+=1
        m['head']['spi20']['dram']+=1
        self.assertEqual(c.decide_pair(m,'base','head')['verdict'],'FAIL')
        self.assertEqual(c.decide_pair(m,'main','candidate')['verdict'],'PASS')

    def test_iram_one_byte_regression(self):
        m=matrix(); m['head']['spi40']['iram']+=1
        self.assertEqual(c.decide_pair(m,'base','head')['verdict'],'FAIL')

    def test_dram_one_byte_regression(self):
        m=matrix(); m['candidate']['spi20']['dram']+=1
        self.assertEqual(c.decide_pair(m,'main','candidate')['verdict'],'FAIL')

    def test_bss_in_dram_regression(self):
        m=matrix(); m['head']['spi40']['dram']+=1
        m['head']['spi40']['bss']+=1
        self.assertIn('spi40:IRAM_OR_DRAM_INCREASE',
                      c.decide_pair(m,'base','head')['faults'])

    def test_spi_parity_failure(self):
        m=matrix(); m['base']['spi20']['iram']+=1
        self.assertIn('base:SPI_IRAM_DRAM_PARITY',
                      c.decide_pair(m,'base','head')['faults'])

    def test_identical_bin_spi_rejected(self):
        m=matrix(); m['head']['spi20']['bin_sha256']='f'*64
        self.assertIn('head:IDENTICAL_SPI_BIN',
                      c.decide_pair(m,'base','head')['faults'])

    def test_sdkconfig_spi_drift_rejected(self):
        m=matrix();m['main']['spi20']['sdkconfig']='a'*64
        with self.assertRaisesRegex(c.Invalid, 'PAIR_CONFIG_DRIFT'):
            c.decide_pair(m,'main','candidate')

    def test_cross_pair_toolchain_drift_invalid(self):
        m=matrix();m['head']['spi40']['ld']='ld FAKE'
        with self.assertRaisesRegex(c.Invalid,'PAIR_CONFIG_DRIFT'):
            c.decide_pair(m,'base','head')

    def test_historical_b3_dram_cap(self):
        m=matrix();m['main']['spi40']['dram']=54865
        self.assertIn('spi40:main:C3_DRAM_CAP',
                      c.decide_pair(m,'main','candidate')['faults'])

    def test_no_ready_even_both_pass(self):
        with patch.object(c,'validate_cell',side_effect=lambda *args: cell(binhash='f'*64 if args[2]=='spi40' else 'd'*64)):
            p={'B':'b'*40,'H':'c'*40,'M':'a'*40,'C':'d'*40,
               'trees':{x:'e'*40 for x in c.LABELS}}
            result=c.evaluate(Path('/not/real'),p,8)
        self.assertEqual(result['PR_INCREMENTAL_VERDICT'],'PASS')
        self.assertEqual(result['INTEGRATION_MEMORY_VERDICT'],'PASS')
        self.assertNotEqual(result['INTEGRATION_READINESS'],'READY')
        self.assertEqual(result['historical']['RENDER_A_HISTORICAL'],'FAILURE')
        self.assertEqual(result['historical']['C3_HISTORICAL'],'FAILURE')
        self.assertEqual(result['historical']['A0_HISTORICAL'],'HISTORICAL_DEBT')

    def test_partial_matrix_is_invalid(self):
        with self.assertRaisesRegex(c.Invalid,'INCOMPLETE_EIGHT_BUILDS'):
            c.evaluate(Path('/not/real'),{},7)

    def test_missing_token_is_invalid(self):
        with self.assertRaisesRegex(c.Invalid,'GITHUB_TOKEN_MISSING'):
            c.get('/branches/main',None)

    def test_wrong_api_path_is_invalid(self):
        with self.assertRaisesRegex(c.Invalid,'UNSAFE_API_PATH'):
            c.get('//foo','valid')

    def test_snapshot_wrong_pr_base(self):
        fake={'commit':{'sha':c.POLICY_MAIN}}
        pr={'number':330,'state':'open','merged_at':None,
            'base':{'ref':'main','repo':{'full_name':c.REPO},'sha':'f'*40},
            'head':{'repo':{'full_name':c.REPO},'sha':c.EXPECTED_H},
            'merge_commit_sha':c.LEGACY_PREVIEW}
        with patch.object(c,'get',side_effect=[fake,pr]):
            with self.assertRaisesRegex(c.Invalid,'GITHUB_REF_DRIFT'):
                c.snapshot('token')

    def test_snapshot_main_moves(self):
        fake={'commit':{'sha':'f'*40}}
        with patch.object(c,'get',return_value=fake):
            with self.assertRaises((c.Invalid,KeyError)):
                c.snapshot('token')

    def test_wrong_merge_base_refused(self):
        p={'M':c.POLICY_MAIN,'B':c.EXPECTED_B,'H':c.EXPECTED_H,
           'old_preview':c.LEGACY_PREVIEW}
        fake=lambda root,*args: ('f'*40 if args[0]=='merge-base' else 'commit' if args[0]=='cat-file' else os.environ.get('LAB_HEAD','1'*40))
        with patch.dict(os.environ,{'LAB_HEAD':'1'*40,'LAB_BASE':c.POLICY_MAIN}):
            with patch.object(c,'git',side_effect=fake):
                with self.assertRaisesRegex(c.Invalid,'WRONG_MERGE_BASE'):
                    c.pin_git('/none',p)

    def test_candidate_merge_conflict_refused(self):
        p={'M':c.POLICY_MAIN,'B':c.EXPECTED_B,'H':c.EXPECTED_H,
           'old_preview':c.LEGACY_PREVIEW}
        def fakegit(root,*args):
            if args[0]=='rev-parse': return '1'*40
            if args[0]=='cat-file': return 'commit'
            if args[0]=='merge-base': return c.EXPECTED_B
            return ''
        def fakesh(command,**kwargs):
            if 'merge-tree' in command: raise c.Invalid('MEASUREMENT_INVALID: MERGE_CONFLICT')
            return ''
        with patch.dict(os.environ,{'LAB_HEAD':'1'*40,'LAB_BASE':c.POLICY_MAIN}):
            with patch.object(c,'git',side_effect=fakegit),patch.object(c,'sh',side_effect=fakesh):
                with self.assertRaisesRegex(c.Invalid,'MERGE_CONFLICT'):
                    c.pin_git('/none',p)

    def test_cell_other_run_or_head_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'base'/'spi40';path.mkdir(parents=True)
            (path/'source.json').write_text(json.dumps({
                'source_sha':'a'*40,'source_tree':'b'*40,
                'source_label':'base','variant':'spi40',
                'map_sha256':'1'*64,'github_run_id':'other',
                'github_run_attempt':'1','lab_head':'d'*40}))
            (path/'firmware.map').write_bytes(b'fake')
            with patch.dict(os.environ,{'GITHUB_RUN_ID':'real','GITHUB_RUN_ATTEMPT':'1','LAB_HEAD':'d'*40}):
                with self.assertRaisesRegex(c.Invalid,'MAP_DIGEST'):
                    c.validate_cell(Path(tmp),'base','spi40','a'*40,'b'*40)
                meta=json.loads((path/'source.json').read_text());meta['map_sha256']=c.digest(path/'firmware.map')
                (path/'source.json').write_text(json.dumps(meta))
                with self.assertRaisesRegex(c.Invalid,'FOREIGN_RUN_OR_HEAD_ARTIFACT'):
                    c.validate_cell(Path(tmp),'base','spi40','a'*40,'b'*40)

    def test_sh_failed_build_not_silently_passed(self):
        with patch.object(c.subprocess,'run',return_value=type('R',(),{'returncode':1,'stdout':'','stderr':'fail'})()):
            with self.assertRaisesRegex(c.Invalid,'COMMAND_FAILURE'):
                c.sh(['git','merge-tree'])

    def test_old_preview_is_not_candidate(self):
        self.assertNotEqual(c.LEGACY_PREVIEW,c.POLICY_MAIN)
        self.assertNotEqual(c.LEGACY_PREVIEW,c.EXPECTED_H)

    def test_source_sha7_not_full_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'base'/'spi40';path.mkdir(parents=True)
            (path/'firmware.map').write_bytes(b'xxx')
            (path/'source.json').write_text(json.dumps({
                'source_sha':'a'*40,'source_tree':'b'*40,
                'source_label':'base','variant':'spi40',
                'map_sha256':c.digest(path/'firmware.map'),
                'github_run_id':'R','github_run_attempt':'1','lab_head':'d'*40,
                'app_source_sha7':'a'*40}))
            with patch.dict(os.environ,{'GITHUB_RUN_ID':'R','GITHUB_RUN_ATTEMPT':'1','LAB_HEAD':'d'*40}):
                with self.assertRaisesRegex(c.Invalid,'SHA7_ONLY'):
                    c.validate_cell(Path(tmp),'base','spi40','a'*40,'b'*40)


if __name__=='__main__':
    unittest.main()