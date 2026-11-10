#!/usr/bin/env python3
"""Synthetic, falsifiable route tests. No Caprice32 and no CPC proof claimed."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

S = importlib.util.spec_from_file_location(
    "clk_04_a4_fast_route", Path(__file__).resolve().parents[1] /
    "tools/ci/clk_04_a4_fast_route.py")
route = importlib.util.module_from_spec(S)
S.loader.exec_module(route)

BASE_WORKFLOW = '''name: A4
on:
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  host-negatives-and-c99:
    runs-on: ubuntu-24.04
  cpc-acquire:
    runs-on: ubuntu-24.04
    needs: host-negatives-and-c99
    container:
      image: ghcr.io/kharn27/caprice32@sha256:abc
    steps:
      - run: python3 tools/clk_04_a4_oracle.py --acquire --head "$EXPECTED_HEAD"
  sealed-replay:
    runs-on: ubuntu-24.04
    needs: cpc-acquire
    steps:
      - run: python3 tools/clk_04_a4_oracle.py --verify --seal "$EXTERNAL_SHA"
'''
NEW_WORKFLOW = (BASE_WORKFLOW
                .replace("    needs: host-negatives-and-c99\n",
                         "    needs: [host-negatives-and-c99, route]\n"
                         "    if: needs.route.outputs.mode == 'full'\n")
                .replace("  host-negatives-and-c99:\n",
                         "  route:\n    runs-on: ubuntu-24.04\n"
                         "  host-negatives-and-c99:\n"))


class Routes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.g("init", "-q", "-b", "main")
        self.g("config", "user.name", "CI synthetic")
        self.g("config", "user.email", "ci@example.invalid")
        for path in route.INPUTS:
            if path == "tests/oracles/caprice32":
                continue
            self.write(path + ("/corpus.json" if path.endswith("clk_04_a4_numeric") else ""),
                       "sealed data for " + path + "\n")
        self.write(route.WORKFLOW, BASE_WORKFLOW)
        self.write("tools/clk_04_a4_numeric_lab.c", "candidate original\n")
        self.write("tools/ci/opt3_routing.py", "OPT3 original\n")
        self.g("add", ".")
        (self.root / "tests/oracles/caprice32").mkdir(parents=True, exist_ok=True)
        self.g("update-index", "--add", "--cacheinfo",
               "160000," + "a" * 40 + ",tests/oracles/caprice32")
        self.g("commit", "-qm", "baseline")
        self.base = self.sha()
        self.write(route.WORKFLOW, NEW_WORKFLOW)
        self.g("add", ".")
        self.g("commit", "-qm", "new route-only workflow")
        self.head = self.sha()

    def g(self, *args):
        p = subprocess.run(["git", "-C", str(self.root), *args],
                           text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        if p.returncode:
            self.fail(p.stderr)
        return p.stdout.strip()

    def sha(self):
        return self.g("rev-parse", "HEAD")

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def change(self, path, content):
        self.write(path, content)
        self.g("add", ".")
        self.g("commit", "-qm", "change " + path)
        self.head = self.sha()

    def check(self, expected):
        mode, _, label = route.decision(self.root, "pull_request",
                                       self.head, self.base)
        self.assertEqual(mode, expected)
        self.assertIn("HEAD_EXACT" if expected == "full" else "FAST_HOST_ONLY", label)

    def test_workflow_route_only_upgrade_fast(self):
        self.check("fast")

    def test_opt3_only_is_fast(self):
        self.change("tools/ci/opt3_routing.py", "OPT3 changed\n")
        self.check("fast")

    def test_candidate_only_is_fast_no_cpc_proof(self):
        self.change("tools/clk_04_a4_numeric_lab.c", "candidate new\n")
        self.check("fast")

    def test_corpus_oracle_and_dependencies_must_acquire(self):
        for path in ("tests/fixtures/cpc6128/clk_04_a4_numeric/corpus.json",
                     "tools/clk_04_a4_oracle.py", "tools/clk_03_cpc_time.py",
                     "tools/clk_04_real5_oracle.py"):
            with self.subTest(path=path):
                original = (self.root / path).read_text()
                self.change(path, original + "significant modification\n")
                self.check("full")

    def test_submodule_pin_change_must_acquire(self):
        self.g("update-index", "--add", "--cacheinfo",
               "160000," + "b" * 40 + ",tests/oracles/caprice32")
        self.g("commit", "-qm", "changed caprice32 ROM gitlink")
        self.head = self.sha()
        self.check("full")

    def test_changed_cpc_protocol_must_acquire(self):
        self.change(route.WORKFLOW, NEW_WORKFLOW.replace(
            "--acquire --head", "--acquire --changed --head"))
        self.check("full")

    def test_changed_image_digest_must_acquire(self):
        self.change(route.WORKFLOW, NEW_WORKFLOW.replace("sha256:abc", "sha256:def"))
        self.check("full")

    def test_replay_interpretation_must_acquire(self):
        self.change(route.WORKFLOW, NEW_WORKFLOW.replace(
            "--verify --seal", "--verify --strict --seal"))
        self.check("full")

    def test_main_sync_without_oracle_input_is_fast(self):
        self.g("checkout", "-qb", "feature")
        self.change("tools/ci/opt3_routing.py", "only fast change\n")
        self.g("checkout", "main")
        self.change("core/other.c", "unrelated main work\n")
        new_base = self.sha()
        self.g("checkout", "feature")
        self.g("merge", "--no-edit", "main")
        head = self.sha()
        mode, _, _ = route.decision(self.root, "pull_request", head, new_base)
        self.assertEqual(mode, "fast")

    def test_manual_dispatch_is_always_full(self):
        mode, _, label = route.decision(self.root, "workflow_dispatch", self.head)
        self.assertEqual(mode, "full")
        self.assertEqual(label, "HEAD_EXACT_MANUAL_FULL")

    def test_missing_oracle_input_stops_not_fast(self):
        self.g("rm", "tools/clk_03_cpc_time.py")
        self.g("commit", "-qm", "removed dependency")
        with self.assertRaisesRegex(route.RouteError, "INPUT_MISSING"):
            route.decision(self.root, "pull_request", self.sha(), self.base)

    def test_forged_head_stops(self):
        with self.assertRaisesRegex(route.RouteError, "HEAD_MISMATCH"):
            route.decision(self.root, "pull_request", self.base, self.base)

    def test_unknown_base_stops(self):
        with self.assertRaisesRegex(route.RouteError, "GIT_OBJECT_UNAVAILABLE"):
            route.decision(self.root, "pull_request", self.head, "f" * 40)

    def test_unguarded_capture_stops(self):
        self.change(route.WORKFLOW, NEW_WORKFLOW.replace(
            "    if: needs.route.outputs.mode == 'full'\n", "    if: always()\n"))
        with self.assertRaisesRegex(route.RouteError, "CPC_GATE_CONDITION_CHANGED"):
            route.decision(self.root, "pull_request", self.head, self.base)

    def test_skipped_replay_bypass_stops(self):
        self.change(route.WORKFLOW, NEW_WORKFLOW.replace(
            "    needs: cpc-acquire\n", "    needs: cpc-acquire\n    if: false\n"))
        with self.assertRaisesRegex(route.RouteError, "REPLAY_GUARD_CHANGED"):
            route.decision(self.root, "pull_request", self.head, self.base)


if __name__ == "__main__":
    unittest.main()
