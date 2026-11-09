"""C6-B2-A: host-only falsifications of the non-required trusted CLI workflow.

No API token, networking, Xtensa or physical device involved in this module.
The real API evidence must come from the separate GitHub Actions live job.
"""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/hw4-mem-c6-b2-a-live.yml'
SENTINEL = '0d5315be79262bb0355f8141a351937272f548fd'
PATHS = (
    '.github/workflows/hw4-mem-c6-b2-a-live.yml',
    'tools/ci/opt3_routing.py',
    'tools/ci/hw4_mem_c6_refs.py',
    'tests/test_hw4_mem_c6_refs.py',
    'tests/test_hw4_mem_c6_b2_a_live.py',
    'docs/HW4-MEM-C6-B2-A-live.md',
)


class ContractViolation(Exception):
    pass


def require(condition, code):
    if not condition:
        raise ContractViolation(code)


def check_workflow(s):
    """Independent exact negative-check of routing and trusted-source contract."""
    before_permissions = s.split('\npermissions:', 1)
    require(len(before_permissions) == 2, 'PERMISSIONS_MISSING')
    events = re.findall(r'(?m)^  ([a-z][\w-]*):', before_permissions[0])
    require(events == ['pull_request', 'workflow_dispatch'], 'UNSAFE_EVENT')
    paths = re.findall(r"(?m)^      - '([^']+)'$", before_permissions[0])
    require(tuple(paths) == PATHS, 'UNSAFE_PATH_FILTER')
    require('permissions:\n  contents: read\n' in s and
            not re.search(r'(?m)^\s+(?:contents|pull-requests|actions|checks): write\s*$', s) and
            'secrets.' not in s, 'PERMISSIONS_ESCALATED')
    require('cancel-in-progress: false' in s, 'CANCEL_RISK')
    require('continue-on-error:' not in s and 'if: false' not in s and
            '|| true' not in s and 'set -euo pipefail' in s, 'FAILURE_MASKED')
    require('NOT_MEMORY_GATE' in s and 'PROVENANCE_ONLY' in s,
            'MISLEADING_GATE_NAME')
    require('if: success()' in s and 'if-no-files-found: error' in s and
            'actions/upload-artifact@v4' in s, 'UNSAFE_ARTIFACT')
    require('name: host-adversarial' not in s and
            '  host-adversarial:' in s and '  live-github-provenance:' in s and
            'needs: host-adversarial' in s, 'HOST_TEST_DEPENDENCY_REMOVED')
    require("-p 'test_hw4_mem_c6_refs.py' -v" in s and
            "-p 'test_hw4_mem_c6_b2_a_live.py' -v" in s and
            'python3 -m py_compile' in s, 'MISSING_ADVERSARIAL_TESTS')
    require('persist-credentials: false' in s and
            'ref: ${{ github.event.pull_request.head.sha || github.sha }}' in s,
            'HEAD_NOT_AUTHENTICATED')
    live = s.split('\n  live-github-provenance:', 1)
    require(len(live) == 2, 'NO_LIVE_JOB')
    require('ref: ${{ steps.pin.outputs.trusted_main_sha }}' in live[1] and
            'EXPECTED_MAIN: ' + SENTINEL in live[1] and
            'git rev-parse HEAD' in live[1] and
            "get('/branches/main')['commit']['sha'] == expected" in live[1],
            'TRUSTED_MAIN_BYPASS')
    require('GITHUB_TOKEN: ${{ github.token }}' in live[1] and
            'github.event.pull_request.head.sha' in live[1] and
            "live['head']['sha'] == os.environ['EVENT_HEAD']" in live[1],
            'EVENT_HEAD_UNVERIFIED')
    for essential in ('--pr 330', '--pr 339', 'pr-330.json', 'pr-339.json',
                      'source-provenance.json', 'SHA256SUMS.txt',
                      "'MEASUREMENT_INVALID'", 'PREVIEW_API_REFUSED',
                      'PREVIEW_PARENT_DRIFT', 'MAIN_DRIFT_AFTER_CLI'):
        # Accept explicit MEASUREMENT_INVALID state from the CLI module itself;
        # the wrapper must never promise a memory PASS for a green run.
        if essential == "'MEASUREMENT_INVALID'":
            continue
        require(essential in live[1], 'MISSING_LIVE_PROOF_' + essential)
    require("report['PR_INCREMENTAL_VERDICT'] == 'UNVERIFIED'" in live[1] and
            "report['INTEGRATION_MEMORY_VERDICT'] == 'UNVERIFIED'" in live[1] and
            "'BLOCKED_STALE_BASE'" in live[1] and
            'FALSE_READY' in live[1], 'MEMORY_PASS_SPOOF')
    require('GITHUB_TOKEN' not in s.split('\n  live-github-provenance:', 1)[0],
            'TOKEN_EXPOSED_TO_PR_TESTS')
    return True


class TrustedWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding='utf-8')

    def test_unmodified_contract(self):
        self.assertTrue(check_workflow(self.source))

    def mutate(self, before, after, expected):
        self.assertIn(before, self.source)
        candidate = self.source.replace(before, after, 1)
        self.assertNotEqual(self.source, candidate)
        with self.assertRaises(ContractViolation) as caught:
            check_workflow(candidate)
        self.assertEqual(str(caught.exception), expected)

    def test_broad_filter_rejected(self):
        self.mutate("      - 'docs/HW4-MEM-C6-B2-A-live.md'", "      - 'docs/**'", 'UNSAFE_PATH_FILTER')

    def test_duplicate_route_rejected(self):
        path = "      - 'tools/ci/hw4_mem_c6_refs.py'"
        self.mutate(path, path + '\n' + path, 'UNSAFE_PATH_FILTER')

    def test_missing_self_route_rejected(self):
        self.mutate("      - '.github/workflows/hw4-mem-c6-b2-a-live.yml'\n", '', 'UNSAFE_PATH_FILTER')

    def test_unallowed_event_rejected(self):
        self.mutate('  workflow_dispatch:\n', '  push:\n    branches: [main]\n  workflow_dispatch:\n', 'UNSAFE_EVENT')

    def test_pull_request_target_rejected(self):
        self.mutate('  pull_request:\n', '  pull_request_target:\n', 'UNSAFE_EVENT')

    def test_permissions_write_rejected(self):
        self.mutate('  contents: read\n', '  contents: write\n', 'PERMISSIONS_ESCALATED')

    def test_failures_cannot_be_silenced(self):
        self.mutate('set -euo pipefail', 'set +e\n          continue-on-error: true', 'FAILURE_MASKED')

    def test_fake_proposed_head_rejected(self):
        self.mutate('ref: ${{ github.event.pull_request.head.sha || github.sha }}',
                    'ref: refs/heads/main', 'HEAD_NOT_AUTHENTICATED')

    def test_fake_trusted_checkout_rejected(self):
        self.mutate('ref: ${{ steps.pin.outputs.trusted_main_sha }}',
                    'ref: ${{ github.event.pull_request.head.sha }}', 'TRUSTED_MAIN_BYPASS')

    def test_wrong_trusted_sha_rejected(self):
        self.mutate('EXPECTED_MAIN: ' + SENTINEL, 'EXPECTED_MAIN: ' + '0'*40, 'TRUSTED_MAIN_BYPASS')

    def test_host_dependency_removed_rejected(self):
        self.mutate('    needs: host-adversarial\n', '', 'HOST_TEST_DEPENDENCY_REMOVED')

    def test_artifact_missing_no_green_result(self):
        self.mutate('if-no-files-found: error', 'if-no-files-found: ignore', 'UNSAFE_ARTIFACT')

    def test_false_memory_pass_rejected(self):
        self.mutate("report['PR_INCREMENTAL_VERDICT'] == 'UNVERIFIED'",
                    "report['PR_INCREMENTAL_VERDICT'] == 'PASS'", 'MEMORY_PASS_SPOOF')

    def test_missing_second_pr_rejected(self):
        self.mutate('--pr 339', '--pr 331', 'MISSING_LIVE_PROOF_--pr 339')

    def test_preview_refusal_not_accepted(self):
        self.mutate('PREVIEW_API_REFUSED', 'PREVIEW_WEAK_OK', 'MISSING_LIVE_PROOF_PREVIEW_API_REFUSED')


if __name__ == '__main__':
    unittest.main()