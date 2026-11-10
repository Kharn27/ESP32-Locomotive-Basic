"""#354 host adversarial tests; no Xtensa or GitHub network in unit tests."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SRC = Path(__file__).resolve().parents[1]/'tools'/'ci'
import sys
sys.path.insert(0,str(SRC))
# import historic parse contract from merged trusted main; never modify it
import hw4_mem_c6_b2_d1 as d


def sample_event():
    return {'repo':d.REPO, 'lab_head':'1'*40,'lab_number':355,
            'run_id':123,'attempt':1,'name':'pull_request','branch':d.BRANCH}


def refs():
    e=sample_event()
    main={'commit':{'sha':d.M}}
    pr={'number':330,'state':'open','merged_at':None,
        'base':{'sha':d.B,'ref':'main','repo':{'full_name':d.REPO}},
        'head':{'sha':d.H,'repo':{'full_name':d.REPO}},
        'merge_commit_sha':'e'*40}
    lab={'number':e['lab_number'],'state':'open',
        'base':{'sha':d.M,'ref':'main'},
        'head':{'sha':e['lab_head'],'repo':{'full_name':d.REPO}}}
    return main,pr,lab,e


def runs(e=None):
    e=e or sample_event()
    return [{'id':e['run_id'],'head_sha':e['lab_head'],
             'run_attempt':1,'name':d.LAB_WORKFLOW,
             'head_branch':d.BRANCH,'event':'pull_request'}]


class RefContract(unittest.TestCase):
    def test_good_snapshot(self):
        x=d.validate_snap(*refs());self.assertEqual(x['base'],d.B)
    def test_wrong_true_base(self):
        m,p,l,e=refs();p['base']['sha']=d.M
        with self.assertRaisesRegex(d.Invalid,'PR330_REAL_BASE_HEAD_DRIFT'):
            d.validate_snap(m,p,l,e)
    def test_head_moved(self):
        m,p,l,e=refs();p['head']['sha']='a'*40
        with self.assertRaisesRegex(d.Invalid,'PR330_REAL_BASE_HEAD_DRIFT'):
            d.validate_snap(m,p,l,e)
    def test_main_moved(self):
        m,p,l,e=refs();m['commit']['sha']='a'*40
        with self.assertRaisesRegex(d.Invalid,'MAIN_DRIFT'):
            d.validate_snap(m,p,l,e)
    def test_closed_pr(self):
        m,p,l,e=refs();p['state']='closed'
        with self.assertRaisesRegex(d.Invalid,'PR330_CLOSED'):
            d.validate_snap(m,p,l,e)
    def test_wrong_repo(self):
        m,p,l,e=refs();p['head']['repo']['full_name']='other/other'
        with self.assertRaisesRegex(d.Invalid,'PR330_REAL_BASE_HEAD_DRIFT'):
            d.validate_snap(m,p,l,e)
    def test_lab_head_moved(self):
        m,p,l,e=refs();l['head']['sha']='f'*40
        with self.assertRaisesRegex(d.Invalid,'LAB_HEAD_BASE_REPO_DRIFT'):
            d.validate_snap(m,p,l,e)
    def test_lab_base_moved(self):
        m,p,l,e=refs();l['base']['sha']=d.B
        with self.assertRaisesRegex(d.Invalid,'LAB_HEAD_BASE_REPO_DRIFT'):
            d.validate_snap(m,p,l,e)
    def test_spoofed_lab_source(self):
        m,p,l,e=refs();l['head']['repo']['full_name']='attacker/other'
        with self.assertRaisesRegex(d.Invalid,'LAB_HEAD_BASE_REPO_DRIFT'):
            d.validate_snap(m,p,l,e)


class OneShot(unittest.TestCase):
    def test_single_run_ok(self):
        e=sample_event();self.assertEqual(d.one_shot(runs(e),e)['candidate_runs'],1)
    def test_rerun_attempt_blocked(self):
        e=sample_event();e['attempt']=2
        with self.assertRaisesRegex(d.Invalid,'LAB_ALREADY_STARTED'):
            d.one_shot([{**runs(e)[0],'run_attempt':2}],e)
    def test_future_new_head_still_blocked(self):
        e=sample_event(); a=runs(e)+[{**runs(e)[0],'id':144,'head_sha':'f'*40}]
        with self.assertRaisesRegex(d.Invalid,'LAB_ALREADY_STARTED'):
            d.one_shot(a,e)
    def test_old_completed_branch_run_blocks(self):
        e=sample_event(); a=runs(e)+[{**runs(e)[0],'id':111,'head_sha':'a'*40,'status':'completed'}]
        with self.assertRaisesRegex(d.Invalid,'LAB_ALREADY_STARTED'):
            d.one_shot(a,e)
    def test_current_run_absent(self):
        e=sample_event()
        with self.assertRaisesRegex(d.Invalid,'CURRENT_LAB_RUN_NOT_FOUND'):
            d.one_shot([],e)
    def test_no_trust_in_unrelated_runs(self):
        e=sample_event();a=runs(e)+[{**runs(e)[0],'id':456,'name':'other'}]
        self.assertEqual(d.one_shot(a,e)['candidate_runs'],1)
    def test_event_not_first(self):
        e=sample_event()
        env={'GITHUB_REPOSITORY':d.REPO,'LAB_HEAD':e['lab_head'],
             'LAB_PR_NUMBER':str(e['lab_number']),'GITHUB_RUN_ID':str(e['run_id']),
             'GITHUB_RUN_ATTEMPT':'2','GITHUB_EVENT_NAME':'pull_request',
             'GITHUB_HEAD_REF':d.BRANCH}
        with mock.patch.dict(os.environ,env):
            with self.assertRaisesRegex(d.Invalid,'NOT_FIRST_TRUSTED_PULL_REQUEST_RUN'):
                d.current_event()
    def test_not_from_dispatch(self):
        e=sample_event()
        env={'GITHUB_REPOSITORY':d.REPO,'LAB_HEAD':e['lab_head'],
             'LAB_PR_NUMBER':str(e['lab_number']),'GITHUB_RUN_ID':str(e['run_id']),
             'GITHUB_RUN_ATTEMPT':'1','GITHUB_EVENT_NAME':'workflow_dispatch',
             'GITHUB_HEAD_REF':d.BRANCH}
        with mock.patch.dict(os.environ,env):
            with self.assertRaisesRegex(d.Invalid,'NOT_FIRST_TRUSTED_PULL_REQUEST_RUN'):
                d.current_event()


class ArtifactGuards(unittest.TestCase):
    def test_corrupt_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t,'SHA256SUMS.txt').write_text('fake\n')
            with self.assertRaisesRegex(d.Invalid,'ORACLE_MANIFEST_SHA'):
                d.verify_oracle(t,{})
    def test_missing_target_relocation(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(d.Invalid,'MISSING_PRELINK_MEMBER'):
                d.summarize_prelink(Path(t))
    def test_falsified_artifact_sections(self):
        with tempfile.TemporaryDirectory() as t:
            o=Path(t);(o/'base').mkdir()
            (o/'base'/'sections.txt').write_text('bad')
            with self.assertRaises((ValueError,KeyError,d.Invalid)):
                d.verify_context('base',None,o,o)
    def test_budget_is_strict_in_source(self):
        self.assertEqual(len(d.EXPECTED),2)
        self.assertEqual(list(d.EXPECTED),['base','head'])
        self.assertEqual(d.IMAGE_ID,'sha256:b5ed7387fed7f3c0cc613272ee7dedab5dddfac6f771ee66af41d93f8d46c0bc')
        self.assertEqual(sum(len(x) for x in d.TARGETS.values()),18)
        self.assertIn("require(attempted<2,'TWO_BUILD_BUDGET_EXCEEDED')",Path(d.__file__).read_text())
    def test_binary_app_not_used_as_source_sha(self):
        text=Path(d.__file__).read_text()
        self.assertNotIn('app_version.startswith',text)
        self.assertIn('source_tree',text)
    def test_no_relink_in_capture_script(self):
        self.assertEqual(d.CAPTURE_SHELL.count('idf.py -B "$BUILD"'),2)
        self.assertNotIn('--no-relax',d.CAPTURE_SHELL)
        self.assertNotIn('GH_TOKEN=',d.CAPTURE_SHELL)
        self.assertIn('test -z "${GH_TOKEN:-}"',d.CAPTURE_SHELL)


if __name__=='__main__':unittest.main()