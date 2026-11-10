"""C6-B1 synthetic fixtures only: no Xtensa images, no CPC or CYD tests."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "ci"))
import hw4_mem_c6_refs as c6

M = "a" * 40
B = "b" * 40
H = "c" * 40
C = "d" * 40
T = "9" * 40
REPO = c6.REPO
PR = 330


def commit(commit_sha, tree_sha=None, parents=None):
    return {"sha": commit_sha,
            "tree": {"sha": tree_sha or commit_sha.replace(commit_sha[0], "f")},
            "parents": [{"sha": item} for item in (parents or [])]}


def compare(base, head, merge_base, ahead, behind):
    status = ("identical" if ahead == behind == 0 else
              "ahead" if ahead > 0 and behind == 0 else
              "behind" if behind > 0 and ahead == 0 else "diverged")
    return {"base_commit": {"sha": base},
            "merge_base_commit": {"sha": merge_base},
            "status": status, "ahead_by": ahead, "behind_by": behind,
            "commits": [{"sha": head}] if ahead else []}


def good(m=M, b=B, h=H, preview=C, preview_state="PRESENT",
         former_main=None):
    # B is ancestor of M and H; M and H diverged after B.
    graphs = {
        "base_main": compare(b, m, b, 2, 0) if b != m else
                     compare(b, m, b, 0, 0),
        "main_head": compare(m, h, b, 2, 1) if b != m else
                     compare(m, h, m, 2, 0),
        "base_head": compare(b, h, b, 2, 0),
        "mb_main": compare(b, m, b, 2, 0) if b != m else
                   compare(m, m, m, 0, 0),
        "mb_head": compare(b, h, b, 2, 0) if b != m else
                   compare(m, h, m, 2, 0),
        "bh_base": compare(b, b, b, 0, 0),
        "bh_head": compare(b, h, b, 2, 0),
    }
    mb = b if b != m else m
    commits = {"M": commit(m, "1" * 40), "B": commit(b, "2" * 40),
               "H": commit(h, "3" * 40), "MB": commit(mb, "2" * 40),
               "MB_BH": commit(b, "2" * 40)}
    if b == m:
        commits["MB"] = commit(m, "1" * 40)
        commits["MB_BH"] = commit(b, "1" * 40)
        commits["B"] = commit(b, "1" * 40)
    pv = {"sha": preview, "commit": None, "tree": None,
          "availability": preview_state}
    if preview_state == "PRESENT":
        pv["commit"] = commit(preview, T, [former_main or m, h])
        pv["tree"] = {"sha": T, "tree": []}
        if former_main is not None:
            pv["parent_main_graph"] = compare(former_main, m, former_main, 1, 0)
    if preview_state == "UNAVAILABLE":
        pv["reason"] = "PREVIEW_API_UNAVAILABLE"
    if preview_state == "ABSENT":
        pv["sha"] = None
    return {"captured_at": "2026-11-09T12:00:01+00:00",
            "branch": {"name": "main", "commit": {"sha": m}},
            "pull": {"number": PR, "state": "open", "merged_at": None,
                     "draft": True, "mergeable": True,
                     "base": {"sha": b, "ref": "main",
                              "repo": {"full_name": REPO}},
                     "head": {"sha": h, "ref": "feat/c6-candidate",
                              "repo": {"full_name": REPO}},
                     "merge_commit_sha": None if preview_state == "ABSENT"
                     else preview},
            "graphs": graphs, "commits": commits, "preview": pv}


class FakeGithub:
    """Inject a complete capture as GET endpoint results (no actual network)."""

    def __init__(self, snapshot, failure=None):
        self.s = snapshot
        self.calls = []
        self.failure = failure

    def get(self, path):
        self.calls.append(path)
        if path == self.failure:
            raise c6.EvidenceError("API_UNAVAILABLE", "HTTP_503")
        if path == "/branches/main":
            return copy.deepcopy(self.s["branch"])
        if path == "/pulls/" + str(PR):
            return copy.deepcopy(self.s["pull"])
        if path.startswith("/compare/"):
            a, b = path[9:].split("...")
            candidates = list(self.s["graphs"].values())
            if self.s["preview"].get("parent_main_graph"):
                candidates.append(self.s["preview"]["parent_main_graph"])
            for graph in candidates:
                if graph["base_commit"]["sha"] == a and (
                    graph["commits"][-1]["sha"] if graph["commits"] else
                    graph["merge_base_commit"]["sha"]) == b:
                    return copy.deepcopy(graph)
        if path.startswith("/git/commits/"):
            wanted = path.rsplit("/", 1)[-1]
            for value in self.s["commits"].values():
                if value["sha"] == wanted:
                    return copy.deepcopy(value)
            if wanted == self.s["preview"]["sha"]:
                return copy.deepcopy(self.s["preview"]["commit"])
        if path.startswith("/git/trees/"):
            return copy.deepcopy(self.s["preview"]["tree"])
        raise AssertionError("unscripted GET " + path)


class RefValidation(unittest.TestCase):
    def ok(self, fixture=None):
        return c6.validate_snapshot(fixture if fixture is not None else good(), REPO, PR)

    def invalid(self, fixture, reason):
        with self.assertRaises(c6.EvidenceError) as ctx:
            self.ok(fixture)
        self.assertEqual(ctx.exception.code, reason)

    def test_positive_stale_base_and_valid_preview_not_ready(self):
        v = self.ok()
        self.assertEqual(v["M"], M)
        self.assertEqual(v["B"], B)
        self.assertEqual(v["H"], H)
        self.assertEqual(v["MB"], B)
        self.assertEqual(v["preview"]["parents"], [M, H])
        self.assertEqual(v["preview"]["tree"], T)
        self.assertEqual(v["PR_INCREMENTAL_VERDICT"], "UNVERIFIED")
        self.assertEqual(v["INTEGRATION_READINESS"], "BLOCKED_STALE_BASE")
        self.assertEqual(v["INTEGRATION_MEMORY_VERDICT"], "UNVERIFIED")
        self.assertEqual(v["historical"]["evaluation"],
                         "HISTORICAL_UNCHANGED_NOT_REEVALUATED")
        self.assertNotIn('"PASS"', json.dumps(v))

    def test_positive_current_base_still_not_ready(self):
        v = self.ok(good(m=B, b=B))
        self.assertEqual(v["INTEGRATION_READINESS"], "UNVERIFIED")
        self.assertEqual(v["PR_INCREMENTAL_VERDICT"], "UNVERIFIED")
        self.assertFalse(v["graph"]["stale_base"])

    def test_stale_preview_with_verified_former_main_is_not_integration_proof(self):
        former = "e" * 40
        s = good(former_main=former)
        v = self.ok(s)
        self.assertEqual(v["preview"]["status"], "UNVERIFIED")
        self.assertEqual(v["preview"]["reason"], "PREVIEW_STALE_MAIN")
        self.assertEqual(v["preview"]["parents"], [former, H])
        self.assertEqual(v["preview"]["former_main_ancestor_verified"], former)
        self.assertEqual(v["INTEGRATION_READINESS"], "BLOCKED_STALE_BASE")
        self.assertEqual(v["PR_INCREMENTAL_VERDICT"], "UNVERIFIED")
        self.assertEqual(v["INTEGRATION_MEMORY_VERDICT"], "UNVERIFIED")
        self.assertNotIn('"PASS"', json.dumps(v))

    def test_stale_preview_missing_or_forged_ancestry_proof_rejected(self):
        s = good(former_main="e" * 40)
        del s["preview"]["parent_main_graph"]
        self.invalid(s, "API_RESPONSE_INVALID")
        s = good(former_main="e" * 40)
        s["preview"]["parent_main_graph"] = compare("e" * 40, M, B, 2, 0)
        self.invalid(s, "MERGE_BASE_INCORRECT")
        s = good(former_main="e" * 40)
        s["preview"]["parent_main_graph"] = compare("e" * 40, M, "e" * 40, 1, 1)
        self.invalid(s, "PREVIEW_PARENTS_MISMATCH")

    def test_valid_preview_absent_or_unavailable(self):
        for mode, reason in (("ABSENT", "PREVIEW_ABSENT"),
                             ("UNAVAILABLE", "PREVIEW_API_UNAVAILABLE")):
            with self.subTest(mode=mode):
                v = self.ok(good(preview_state=mode))
                self.assertEqual(v["preview"]["reason"], reason)
                self.assertEqual(v["INTEGRATION_READINESS"], "BLOCKED_STALE_BASE")
                self.assertEqual(v["INTEGRATION_MEMORY_VERDICT"], "UNVERIFIED")
                self.assertIn("BLOCKED_STALE_BASE", v["blockers"])
                self.assertIn("XTENSA_BUILDS_NOT_EXECUTED", v["blockers"])

    def test_reject_short_zero_uppercase_missing_sha(self):
        for invalid in ("", "abc", "0" * 40, "A" * 40, None):
            s = good()
            s["pull"]["head"]["sha"] = invalid
            with self.subTest(invalid=invalid):
                self.invalid(s, "INVALID_SHA")

    def test_reject_other_repo_ref_and_number(self):
        cases = (("number", 331, "PR_NUMBER_MISMATCH"),
                 ("state", "closed", "PR_NOT_OPEN"))
        for name, value, error in cases:
            s = good(); s["pull"][name] = value
            self.invalid(s, error)
        for side in ("base", "head"):
            s = good(); s["pull"][side]["repo"]["full_name"] = "other/repo"
            self.invalid(s, "PR_BASE_REPOSITORY_OR_REF_INVALID" if side == "base"
                         else "PR_HEAD_REPOSITORY_OR_REF_INVALID")
        s = good(); s["pull"]["base"]["ref"] = "other"
        self.invalid(s, "PR_BASE_REPOSITORY_OR_REF_INVALID")
        s = good(); s["branch"]["name"] = "develop"
        self.invalid(s, "MAIN_REF_INVALID")
        with self.assertRaises(c6.EvidenceError) as ctx:
            c6.validate_snapshot(good(), "another/repo", PR)
        self.assertEqual(ctx.exception.code, "REPOSITORY_MISMATCH")

    def test_reject_head_equals_base_or_main(self):
        for value in (B, M):
            s = good(); s["pull"]["head"]["sha"] = value
            self.invalid(s, "PR_HEAD_EQUALS_BASE_OR_MAIN")

    def test_reject_merge_base_and_non_ancestor(self):
        s = good(); s["graphs"]["main_head"]["merge_base_commit"]["sha"] = "e" * 40
        # For a diverged comparison, a different merge-base must be caught by
        # the independent MB ancestry comparisons.
        with self.assertRaises(c6.EvidenceError):
            self.ok(s)
        s = good(); s["graphs"]["base_main"] = compare(B, M, "e" * 40, 2, 0)
        self.invalid(s, "MERGE_BASE_INCORRECT")
        s = good(); s["graphs"]["mb_head"] = compare(B, H, B, 1, 2)
        self.invalid(s, "MERGE_BASE_NOT_ANCESTOR")
        s = good(); s["graphs"]["bh_base"] = compare(B, B, "e" * 40, 0, 0)
        self.invalid(s, "MERGE_BASE_INCORRECT")

    def test_reject_counts_status_or_head_replay(self):
        s = good(); s["graphs"]["main_head"]["status"] = "ahead"
        self.invalid(s, "COMPARE_STATUS_INVALID")
        s = good(); s["graphs"]["main_head"]["behind_by"] = -1
        self.invalid(s, "COMPARE_COUNTS_INVALID")
        s = good(); s["graphs"]["main_head"]["commits"][-1]["sha"] = "e" * 40
        self.invalid(s, "COMPARE_HEAD_MISMATCH")
        s = good(); s["graphs"]["base_head"] = compare(B, H, B, 0, 1)
        self.invalid(s, "MERGE_BASE_INCORRECT")

    def test_reject_preview_parents_tree_commit_sha_and_state(self):
        for mutation, reason in (
            (lambda p: p["commit"].update(parents=[{"sha": H}, {"sha": M}]),
             "PREVIEW_PARENTS_MISMATCH"),
            (lambda p: p["tree"].update(sha="e" * 40),
             "PREVIEW_TREE_MISMATCH"),
            (lambda p: p["commit"].update(sha="e" * 40),
             "COMMIT_SHA_MISMATCH"),
            (lambda p: p.update(availability="UNKNOWN"),
             "PREVIEW_STATE_UNKNOWN"),
            (lambda p: p["commit"].update(parents=[{"sha": M}, {"sha": M}]),
             "PREVIEW_PARENTS_MISMATCH"),
        ):
            s = good(); mutation(s["preview"])
            with self.subTest(reason=reason):
                self.invalid(s, reason)

    def test_reject_commit_tree_incomplete_responses(self):
        s = good(); del s["commits"]["H"]["tree"]
        self.invalid(s, "API_RESPONSE_INVALID")
        s = good(); s["commits"]["M"]["sha"] = "e" * 40
        self.invalid(s, "COMMIT_SHA_MISMATCH")
        s = good(); del s["graphs"]["mb_main"]
        self.invalid(s, "API_RESPONSE_INVALID")
        s = good(); del s["pull"]["base"]["repo"]
        self.invalid(s, "API_RESPONSE_INVALID")
        s = good(); s["preview"]["availability"] = "ABSENT"
        self.invalid(s, "PREVIEW_ABSENCE_INCONSISTENT")

    def test_preview_id_altered_in_pr_but_not_immutable_commit_rejected(self):
        s = good(); s["pull"]["merge_commit_sha"] = "e" * 40
        self.invalid(s, "PR_PREVIEW_IDENTITY_MISMATCH")
        s = good(); s["pull"]["merge_commit_sha"] = None
        self.invalid(s, "PR_PREVIEW_IDENTITY_MISMATCH")
        s = good(); s["pull"]["merge_commit_sha"] = "abc"
        self.invalid(s, "PREVIEW_SHA_INVALID")

    def test_unknown_timestamp_or_unknown_mergeable_never_pass(self):
        for timestamp in (None, "", "yesterday", "2026-11-09T12:00:00"):
            s = good(); s["captured_at"] = timestamp
            with self.subTest(timestamp=timestamp):
                self.invalid(s, "CAPTURE_TIMESTAMP_INVALID")
        s = good(); s["pull"]["mergeable"] = True
        s["preview"]["commit"]["parents"] = [{"sha": H}, {"sha": M}]
        self.invalid(s, "PREVIEW_PARENTS_MISMATCH")
        s = good(); s["pull"]["mergeable"] = "arbitrary"
        v = self.ok(s)
        self.assertEqual(v["INTEGRATION_READINESS"], "BLOCKED_STALE_BASE")

    def test_preview_replay_and_unsupported_head_repo(self):
        s = good(preview=M)
        self.invalid(s, "PREVIEW_SHA_REPLAY")
        s = good(preview=H)
        self.invalid(s, "PREVIEW_SHA_REPLAY")
        s = good(); s["pull"]["head"]["ref"] = ""
        self.invalid(s, "PR_HEAD_REPOSITORY_OR_REF_INVALID")

    def test_snapshot_drift_main_base_head_and_preview(self):
        for change in ("M", "B", "H", "MB", "trees", "draft", "preview"):
            a = self.ok(); b = copy.deepcopy(a)
            if change == "preview":
                b["preview"]["sha"] = "e" * 40
            else:
                b[change] = "e" * 40
            with self.subTest(change=change), self.assertRaises(c6.EvidenceError) as ctx:
                c6.compare_snapshots(a, b)
            self.assertTrue(ctx.exception.code.startswith("SNAPSHOT_DRIFT"))


class RunnerAndIO(unittest.TestCase):
    def test_live_readonly_capture_two_passes(self):
        fake = FakeGithub(good())
        report, rc = c6.run(fake, PR)
        self.assertEqual(rc, 0)
        self.assertEqual(report["snapshot_status"], "PROVENANCE_VERIFIED")
        self.assertEqual(report["INTEGRATION_READINESS"], "BLOCKED_STALE_BASE")
        self.assertEqual(len(report["observations"]), 2)
        self.assertTrue(report["stable_double_capture"])
        self.assertEqual(fake.calls.count("/branches/main"), 2)
        self.assertFalse(any(not path.startswith(("/branches/", "/pulls/",
                                                       "/compare/", "/git/"))
                             for path in fake.calls))
        self.assertNotIn('"PASS"', json.dumps(report))

    def test_live_readonly_capture_stale_preview_negative(self):
        fake = FakeGithub(good(former_main="e" * 40))
        report, rc = c6.run(fake, PR)
        self.assertEqual(rc, 0)  # snapshot success, NOT integration success
        self.assertEqual(report["snapshot_status"], "PROVENANCE_VERIFIED")
        self.assertEqual(report["observations"][1]["preview"]["reason"],
                         "PREVIEW_STALE_MAIN")
        self.assertEqual(report["INTEGRATION_READINESS"], "BLOCKED_STALE_BASE")
        self.assertIn("PREVIEW_STALE_MAIN", report["blockers"])
        self.assertEqual(report["preview_reason"], "PREVIEW_STALE_MAIN")
        self.assertIn("/compare/" + "e" * 40 + "..." + M, fake.calls)
        self.assertEqual(fake.calls.count("/branches/main"), 2)

    def test_api_denied_is_invalid(self):
        fake = FakeGithub(good(), "/branches/main")
        report, rc = c6.run(fake, PR)
        self.assertEqual(rc, 2)
        self.assertEqual(report["reason"], "API_UNAVAILABLE")
        self.assertEqual(report["snapshot_status"], "MEASUREMENT_INVALID")

    def test_preview_api_unavailable_is_unverified(self):
        fake = FakeGithub(good(), "/git/commits/" + C)
        report, rc = c6.run(fake, PR)
        self.assertEqual(rc, 0)
        self.assertEqual(report["INTEGRATION_READINESS"], "BLOCKED_STALE_BASE")
        self.assertEqual(report["observations"][1]["preview"]["status"], "UNVERIFIED")

    def test_drift_at_second_live_read(self):
        a, b = good(), good(m="e" * 40)
        # Change only valid SHA/tree/graph between snapshots, not an invented PASS.
        with patch.object(c6, "capture_once", side_effect=[a, b]):
            report, rc = c6.run(None, PR)
        self.assertEqual(rc, 2)
        self.assertTrue(report["reason"].startswith("SNAPSHOT_DRIFT"))

    def test_unknown_and_missing_api_responses_fail_closed(self):
        s = good(); s["branch"] = {}
        with patch.object(c6, "capture_once", side_effect=[s, good()]):
            report, rc = c6.run(None, PR)
        self.assertEqual((rc, report["reason"]), (2, "MAIN_REF_INVALID"))
        s = good(); s["preview"]["availability"] = "UNKNOWN"
        with patch.object(c6, "capture_once", side_effect=[s, good()]):
            report, rc = c6.run(None, PR)
        self.assertEqual((rc, report["reason"]), (2, "PREVIEW_STATE_UNKNOWN"))

    def test_invalid_output_path_no_success(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "report.json"
            report, rc = c6.run(FakeGithub(good()), PR)
            c6.write_evidence(output, report)
            self.assertEqual(json.loads(output.read_text())["snapshot_status"],
                             "PROVENANCE_VERIFIED")
            with self.assertRaises(c6.EvidenceError) as ctx:
                c6.write_evidence(Path(d), report)
            self.assertEqual(ctx.exception.code, "OUTPUT_WRITE_FAILED")


if __name__ == "__main__":
    unittest.main()
