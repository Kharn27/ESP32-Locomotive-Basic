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

    def test_rerun_one_hour_later_does_not_fake_runner_queue(self):
        run = trace()["runs"][-1]
        d = perf.analyze_run(run)
        # Original run 19:08 -> final job at 20:13 is HEAD latency.
        self.assertEqual(d["wall_seconds"], 3913)
        # Latest attempt 20:13 -> job starts 20:13:10: only 10 seconds.
        self.assertEqual(d["workflow_wait_seconds"], 10)
        self.assertEqual(d["workflow_wait_reference"], "last_attempt_run_started_at")
        self.assertEqual(d["job_queue_seconds"]["p95"], 8)

    def test_rerun_without_attempt_start_fails_conservatively(self):
        run = copy.deepcopy(trace()["runs"][-1])
        run["attempts"][-1]["metadata"].pop("run_started_at")
        d = perf.analyze_run(run)
        self.assertEqual(d["workflow_wait_seconds"], 8)
        self.assertEqual(d["workflow_wait_reference"],
                         "last_attempt_job_created_at_fallback")

    def test_stale_rerun_start_is_not_one_hour_runner_wait(self):
        run = copy.deepcopy(trace()["runs"][-1])
        run["attempts"][-1]["metadata"]["run_started_at"] = run["created_at"]
        d = perf.analyze_run(run)
        self.assertEqual(d["workflow_wait_seconds"], 8)
        self.assertEqual(d["workflow_wait_reference"],
                         "last_attempt_job_created_at_fallback")

    def test_missing_rerun_jobs_does_not_invent_queue(self):
        run = copy.deepcopy(trace()["runs"][-1])
        run["jobs"] = []
        run["attempts"][-1]["metadata"].pop("run_started_at")
        d = perf.analyze_run(run)
        self.assertIsNone(d["workflow_wait_seconds"])
        self.assertEqual(d["workflow_wait_reference"], "last_attempt_start_unknown")

    def test_frozen_real_head_and_family_percentiles(self):
        snapshot = json.loads((ROOT / "docs/CI-OPT3-PERF-REAL-20261030.json").read_text(encoding="utf-8"))
        self.assertEqual(len(snapshot["runs"]), 286)
        result = perf.summarize(snapshot["runs"], snapshot["cutoff"])
        self.assertEqual(len(result["heads"]), 41)
        self.assertEqual(result["all_terminal_raw"]["p95"], 265)  # 4.42 min
        self.assertEqual(result["all_terminal"]["n"], 39)
        self.assertEqual(result["all_terminal"]["max"], 265)
        self.assertEqual(result["successes"]["n"], 20)
        self.assertEqual(result["successes"]["max"], 265)
        self.assertEqual(result["by_family"]["HW4_MEMORY_A0"]["p95"], 263)

    def test_frozen_real_late_github_update_is_not_job_end(self):
        snapshot = json.loads((ROOT / "docs/CI-OPT3-PERF-REAL-20261030.json").read_text(encoding="utf-8"))
        run = next(r for r in snapshot["runs"] if r["id"] == 41099638924)
        self.assertEqual(perf.run_duration(run), 368)  # API update lag 105 s
        detail = perf.analyze_run(run)
        self.assertEqual(detail["wall_seconds"], 263)
        self.assertEqual(detail["completion_source"], "jobs")

    def test_frozen_real_report_matches_published_rounded_figures(self):
        snapshot = json.loads((ROOT / "docs/CI-OPT3-PERF-REAL-20261030.json").read_text(encoding="utf-8"))
        generated = perf.report(snapshot)
        published = (ROOT / "docs/CI-OPT3-PERF.md").read_text(encoding="utf-8")
        self.assertIn("| HEADs terminés TOUS, y compris incidents (raw) | 41 | 2.70 | 4.42 | 916.47 |", generated)
        self.assertIn("| HW4_MEMORY_A0 | 15 | 3.17 | 4.38 | 4.38 |", generated)
        for value in ("**4,42 min**", "**4,38 min**", "41099638924", "105 secondes"):
            self.assertIn(value, published)

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
