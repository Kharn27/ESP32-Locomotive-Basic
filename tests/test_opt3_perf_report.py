"""Offline, synthetic-only regression tests for CI-OPT3-PERF-A."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/ci/opt3_perf_report.py"
spec = importlib.util.spec_from_file_location("opt3_perf_report", SCRIPT)
perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf)
FIXTURE = ROOT / "tests/fixtures/opt3_perf_synthetic_TEST.json"


def trace():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class LatencyTests(unittest.TestCase):
    def test_nearest_rank_even_and_boundary(self):
        self.assertEqual(perf.percentile([4, 3, 1, 2], .50), 2)
        self.assertEqual(perf.percentile(list(range(1, 21)), .95), 19)
        self.assertEqual(perf.percentile([1, 100], .95), 100)

    def test_invalid_percentiles(self):
        for values, p in (([], .5), ([1], 0), ([1], 1.01)):
            with self.assertRaises(ValueError):
                perf.percentile(values, p)

    def test_parallel_wall_not_sum(self):
        h = perf.group_heads(trace()["runs"])[0]
        self.assertEqual(h["wall_seconds"], 120)
        self.assertEqual(h["verdict"], "SUCCESS")

    def test_job_queue_vs_execution(self):
        d = perf.analyze_run(trace()["runs"][0])
        self.assertEqual(d["workflow_wait_seconds"], 15)
        self.assertEqual(d["job_queue_seconds"]["p95"], 10)
        self.assertEqual(d["job_execution_seconds"]["p95"], 105)
        self.assertEqual(d["completion_source"], "jobs")

    def test_old_head_cancelled(self):
        runs = trace()["runs"]
        newest = copy.deepcopy(runs[0:4])
        for r in newest:
            r["head_sha"] = "ffff000000000000000000000000000000000005"
            r["id"] += 2000
            r["created_at"] = "2026-10-29T19:06:00Z"
            r["updated_at"] = "2026-10-29T19:09:00Z"
            r["jobs"] = []
        hs = perf.group_heads(runs + newest)
        cancelled = next(h for h in hs if h["sha"].startswith("bbbb"))
        self.assertTrue(cancelled["old_head_cancelled"])
        self.assertEqual(cancelled["verdict"], "CANCELLED")

    def test_failure_not_success(self):
        h = perf.group_heads(trace()["runs"])[2]
        self.assertEqual(h["verdict"], "FAILURE")
        self.assertIn("ci-opt3-routing.yml", h["missing_stable"])

    def test_failure_full_gate(self):
        t = trace()["runs"]
        a = copy.deepcopy(t[0:4])
        a[0]["conclusion"] = "failure"
        self.assertEqual(perf.group_heads(a)[0]["verdict"], "FAILURE")

    def test_skipped_stable_not_pass(self):
        a = copy.deepcopy(trace()["runs"][0:4])
        a[0]["conclusion"] = "skipped"
        self.assertEqual(perf.group_heads(a)[0]["verdict"], "SKIPPED")

    def test_optional_skipped_not_counted_as_pass_workflow(self):
        a = copy.deepcopy(trace()["runs"][0:4])
        opt = copy.deepcopy(a[0]); opt["id"] = 112
        opt["path"] = ".github/workflows/j1-12-b1-cpc-reacquire.yml"
        opt["conclusion"] = "skipped"
        a.append(opt)
        s = perf.summarize(a)
        self.assertEqual(s["heads"][0]["verdict"], "SUCCESS")
        self.assertEqual(s["by_state"]["CPC_ACQUISITION/SKIPPED"], 1)

    def test_missing_run_not_triggered(self):
        a = copy.deepcopy(trace()["runs"][0:3])
        self.assertEqual(perf.group_heads(a)[0]["verdict"], "NOT_TRIGGERED")

    def test_no_jobs_and_anomaly(self):
        run = copy.deepcopy(trace()["runs"][0]); run["jobs"] = []
        run["updated_at"] = "2026-10-29T21:00:01Z"
        d = perf.analyze_run(run)
        self.assertTrue(d["anomalous_no_jobs"])
        self.assertEqual(d["completion_source"], "run_updated_at_proxy")
        self.assertIsNone(d["workflow_wait_seconds"])

    def test_reruns_preserved(self):
        d = perf.analyze_run(trace()["runs"][-1])
        self.assertEqual(d["attempt_count"], 2)
        self.assertEqual(d["conclusion"], "SUCCESS")
        self.assertEqual(trace()["runs"][-1]["attempts"][0]["metadata"]["conclusion"], "failure")

    def test_dedup_by_run_id(self):
        t = trace()["runs"][0:4]
        self.assertEqual(len(perf.group_heads(t + [copy.deepcopy(t[0])])[0]["runs"]), 4)

    def test_contradictory_sha_rejected(self):
        t = trace()["runs"][0:4]
        altered = copy.deepcopy(t[0]); altered["head_sha"] = "e" * 40
        with self.assertRaisesRegex(ValueError, "contradictory SHA"):
            perf.group_heads(t + [altered])

    def test_diff_class_historic_unknown(self):
        self.assertEqual(perf.diff_type(None), "UNKNOWN_REVISION")
        self.assertEqual(perf.diff_type(["docs/readme.md"]), "DOC_ONLY")
        self.assertEqual(perf.diff_type(["firmware/cyd.c"]), "HW4_TARGET")
        self.assertEqual(perf.diff_type(["tools/ci/file.py"]), "CI_TOOLS")

    def test_family_separates_oracle_acquisition(self):
        self.assertEqual(perf.family(".github/workflows/j1-12-b1-cpc-reacquire.yml"), "CPC_ACQUISITION")
        self.assertEqual(perf.family(".github/workflows/ci-cpc-permanent.yml"), "CPC_PERMANENT")

    def test_inprogress_not_measured_as_terminal(self):
        a = copy.deepcopy(trace()["runs"][0:4]); a[0]["status"] = "queued"; a[0]["conclusion"] = None
        h = perf.group_heads(a)[0]
        self.assertEqual(h["verdict"], "IN_PROGRESS")
        self.assertIsNone(h["wall_seconds"])

    def test_report_uses_test_label(self):
        text = perf.report(trace())
        self.assertIn("TEST_SYNTHETIC", text)
        self.assertIn("NOT_TRIGGERED", text)
        self.assertIn("PERF_NOT_YET_VERIFIED", text)

    def test_real_source_not_claimed_by_test(self):
        t = trace(); t["source"] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "source"):
            perf.report(t)

    def test_baseline_not_equated_to_global(self):
        text = perf.report(trace())
        self.assertIn("Baseline pré CI-OPT3 C99 uniquement", text)
        self.assertIn("Aucun gain global", text)


if __name__ == "__main__":
    unittest.main()
