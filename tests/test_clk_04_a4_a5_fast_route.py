#!/usr/bin/env python3
"""No CPC evidence in routing tests. Synthetic Git trees protect old A4 FAST."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "clk04_a4_fast", ROOT / "tools/ci/clk_04_a4_fast_route.py")
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)


class A5Routing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.git("config", "user.name", "A5 synthetic")
        for prefix in route.INPUTS:
            if prefix == "tests/oracles/caprice32":
                continue
            target = (prefix + "/corpus.json" if
                      prefix == "tests/fixtures/cpc6128/clk_04_a4_numeric"
                      else prefix)
            self.write(target, "historical A4 " + target)
        self.write(route.WORKFLOW, (ROOT / route.WORKFLOW).read_text())
        self.git("add", ".")
        (self.root / "tests/oracles/caprice32").mkdir(parents=True)
        self.git("update-index", "--add", "--cacheinfo",
                 "160000," + "a" * 40 + ",tests/oracles/caprice32")
        self.git("commit", "-qm", "A4 baseline")
        self.base = self.sha()
        self.write(route.A5_PREFIX + "corpus.json", "new A5 source")
        self.write("tools/clk_04_a4_a5_product_ram.py", "A5 native reader")
        self.write("tools/clk_04_a4_numeric_lab.c", "baseline C99 candidate")
        self.write("tools/clk_04_a4_numeric_lab.h", "baseline C99 header")
        self.git("add", ".")
        self.git("commit", "-qm", "A5 source")
        self.head = self.sha()

    def git(self, *args):
        proc = subprocess.run(["git", "-C", str(self.root), *args],
                              text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def sha(self):
        return self.git("rev-parse", "HEAD")

    def write(self, path, content):
        f = self.root / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")

    def change(self, path, text):
        self.write(path, text)
        self.git("add", ".")
        self.git("commit", "-qm", "A5 synthetic mutation")
        self.head = self.sha()

    def test_new_a5_full_without_historical_a4_reacquisition(self):
        self.assertEqual(route.decision(self.root, "pull_request",
                                        self.head, self.base)[0], "fast")
        self.assertEqual(route.a5_decision(self.root, "pull_request",
                                           self.head, self.base)[0], "full")

    def test_a5_archive_is_separate_from_sealed_a4(self):
        self.assertEqual(route.A5_PREFIX,
                         "tests/fixtures/cpc6128/clk_04_a5_product_ram/")
        self.assertNotIn(route.A5_PREFIX, route.INPUTS)
        self.assertEqual(route.decision(self.root, "pull_request",
                                        self.head, self.base)[0], "fast")
        self.assertEqual(route.a5_decision(self.root, "pull_request",
                                           self.head, self.base)[0], "full")

    def test_new_child_of_historical_a4_still_forces_historical_full(self):
        before = self.sha()
        self.change("tests/fixtures/cpc6128/clk_04_a4_numeric/forgery.json",
                    "unapproved old archive extension")
        self.assertEqual(route.decision(self.root, "pull_request",
                                        self.head, before)[0], "full")
        self.assertEqual(route.a5_decision(self.root, "pull_request",
                                           self.head, before)[0], "fast")

    def test_a5_only_new_source_diff_after_first_merge(self):
        baseline = self.sha()
        self.change("tools/clk_04_a4_a5_product_ram.py", "modified A5 reader")
        self.assertEqual(route.decision(self.root, "pull_request",
                                        self.head, baseline)[0], "fast")
        self.assertEqual(route.a5_decision(self.root, "pull_request",
                                           self.head, baseline)[0], "full")

    def test_a5_candidate_only_change_forces_full_without_a4_reacquisition(self):
        baseline = self.sha()
        self.change("tools/clk_04_a4_numeric_lab.c", "C99 candidate change")
        self.assertEqual(route.decision(self.root, "pull_request",
                                        self.head, baseline)[0], "fast")
        self.assertEqual(route.a5_decision(self.root, "pull_request",
                                           self.head, baseline)[0], "full")

    def test_a5_candidate_header_change_also_forces_full(self):
        baseline = self.sha()
        self.change("tools/clk_04_a4_numeric_lab.h", "candidate ABI header change")
        self.assertEqual(route.decision(self.root, "pull_request",
                                        self.head, baseline)[0], "fast")
        self.assertEqual(route.a5_decision(self.root, "pull_request",
                                           self.head, baseline)[0], "full")

    def test_documentation_and_tests_only_are_fast_for_both(self):
        baseline = self.sha()
        self.change("docs/CLK-04-A6-real5-print-lab.md", "documentation change")
        self.assertEqual(route.decision(self.root, "pull_request",
                                        self.head, baseline)[0], "fast")
        self.assertEqual(route.a5_decision(self.root, "pull_request",
                                           self.head, baseline)[0], "fast")
        baseline = self.sha()
        self.change("tests/test_clk_04_a4_numeric_lab.c", "new host test")
        self.assertEqual(route.decision(self.root, "pull_request",
                                        self.head, baseline)[0], "fast")
        self.assertEqual(route.a5_decision(self.root, "pull_request",
                                           self.head, baseline)[0], "fast")

    def test_stale_cpc_head_or_raw_reuse_guard_cannot_be_dropped(self):
        source = (self.root / route.WORKFLOW).read_text()
        self.assertIn('test "$CAPTURE_HEAD" = "$EXPECTED_HEAD"', source)
        self.assertIn('data["head"] == sys.argv[3]', source)
        baseline = self.sha()
        self.change(route.WORKFLOW, source.replace(
            'test "$CAPTURE_HEAD" = "$EXPECTED_HEAD"',
            'test -n "$CAPTURE_HEAD"'))
        with self.assertRaisesRegex(
                route.RouteError, "A5_REPLAY_DEPENDENCY_SEAL_OR_CANDIDATE_GUARD_MISSING"):
            route.a5_decision(self.root, "pull_request", self.head, baseline)
        # The seal's own identity must also be checked (not only the job output).
        self.change(route.WORKFLOW, source.replace(
            'data["head"] == sys.argv[3]', 'bool(data["head"])'))
        with self.assertRaisesRegex(
                route.RouteError, "A5_REPLAY_DEPENDENCY_SEAL_OR_CANDIDATE_GUARD_MISSING"):
            route.a5_decision(self.root, "pull_request", self.head, baseline)

    def test_wrong_head_is_not_accepted_as_fresh_a5_evidence(self):
        with self.assertRaisesRegex(route.RouteError, "A5_HEAD_MISMATCH"):
            route.a5_decision(self.root, "pull_request", self.base, self.base)


    def test_changed_a4_historical_input_still_forces_full_a4(self):
        baseline = self.sha()
        self.change("tools/clk_04_a4_oracle.py", "changed A4")
        self.assertEqual(route.decision(self.root, "pull_request",
                                        self.head, baseline)[0], "full")
        self.assertEqual(route.a5_decision(self.root, "pull_request",
                                           self.head, baseline)[0], "full")

    def test_a5_cpc_bypass_and_identity_tampering_rejected(self):
        source = (self.root / route.WORKFLOW).read_text()
        self.change(route.WORKFLOW, source.replace(
            "if: needs.route.outputs.a5_mode == 'full'",
            "if: false"))
        with self.assertRaisesRegex(route.RouteError,
                                    "A5_ROM_HEAD_SEAL_OR_ACQUIRE_GUARD"):
            route.a5_decision(self.root, "pull_request", self.head, self.base)
        with self.assertRaisesRegex(route.RouteError, "A5_HEAD_MISMATCH"):
            route.a5_decision(self.root, "pull_request", self.base, self.base)

    def test_a5_route_test_invocation_cannot_be_silently_removed(self):
        source = (self.root / route.WORKFLOW).read_text()
        self.change(route.WORKFLOW, source.replace(
            "test_clk_04_a4_a5_fast_route.py", "absent_route_tests.py"))
        with self.assertRaisesRegex(route.RouteError,
                                    "A5_ROUTE_OUTPUT_OR_TESTS_MISSING"):
            route.a5_decision(self.root, "pull_request", self.head, self.base)

    def test_skipped_replay_and_missing_a5_sources_are_not_evidence(self):
        self.assertEqual(route.a5_decision(self.root, "workflow_dispatch",
                                           self.head)[0], "full")
        self.git("rm", "tools/clk_04_a4_a5_product_ram.py")
        self.git("commit", "-qm", "missing A5 reader")
        with self.assertRaisesRegex(route.RouteError, "INPUT_MISSING"):
            route.a5_decision(self.root, "pull_request", self.sha(), self.base)


if __name__ == "__main__":
    unittest.main()
