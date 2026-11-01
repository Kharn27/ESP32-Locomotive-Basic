#!/usr/bin/env python3
"""CI-OPT3-PERF-A: read-only GitHub Actions latency audit (Python stdlib).

Only GET requests.  No CI triggers, PR mutations, or credentials in output.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

CUTOFF = "2026-10-29T18:51:11Z"
BASELINE_C99_IDS = (40921214206, 40919647970, 40918602480, 40918535166,
    40918505229, 40917684913, 40917057424, 40914948339, 40914655484,
    40914182587, 40911969432, 40911153325, 40910778520, 40910360975,
    40907439442, 40907202069, 40906854820, 40906633033, 40903964637,
    40902075537)
STABLE = frozenset(("basic-program.yml", "ci-cpc-permanent.yml",
                    "ci-arch.yml", "ci-opt3-routing.yml"))
ANOMALY_SECONDS = 3600  # Mark unusually long run(s) with zero job evidence.


def stamp(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def minutes(seconds):
    return "N/A" if seconds is None else f"{seconds / 60:.2f}"


def percentile(values, p):
    """Nearest-rank percentile: sorted[ceil(p*n)-1], p in (0, 1]."""
    if not values or not 0 < p <= 1:
        raise ValueError("non-empty values and 0<p<=1 required")
    ordered = sorted(values)
    return ordered[math.ceil(p * len(ordered)) - 1]


def stats(values):
    v = [x for x in values if x is not None]
    return {"n": len(v), "p50": percentile(v, .50) if v else None,
            "p95": percentile(v, .95) if v else None,
            "max": max(v) if v else None}


def family(path):
    name = (path or "").rsplit("/", 1)[-1]
    if name == "basic-program.yml":
        return "C99"
    if name == "ci-cpc-permanent.yml":
        return "CPC_PERMANENT"
    if name == "cpc-oracle.yml":
        return "CPC_INDEPENDENT"
    if name == "ci-arch.yml":
        return "ARCH"
    if name == "ci-opt3-routing.yml":
        return "ROUTER"
    if name == "ci-xtensa.yml":
        return "XTENSA"
    if name == "hw4-scroll-opt-a0-memory.yml":
        return "HW4_MEMORY_A0"
    if name.startswith("hw4-"):
        return "HW4_OTHER"
    if name.startswith("j1-") or name == "cpc-oracle-image.yml":
        return "CPC_ACQUISITION"
    return "OTHER"


def conclusion(run):
    return (run.get("conclusion") or
            ("IN_PROGRESS" if run.get("status") != "completed" else "UNKNOWN")).upper()


def run_duration(run):
    # run.updated_at is an API-update bound, NOT reliable job completion.
    start = stamp(run.get("created_at"))
    end = stamp(run.get("updated_at"))
    return end - start if start is not None and end is not None and end >= start else None


def analyze_run(run):
    jobs = run.get("jobs")  # absent => unknown, [] => confirmed empty API result
    start = stamp(run.get("created_at"))
    bounds = [stamp(j.get("completed_at")) for j in (jobs or [])]
    bounds = [v for v in bounds if v is not None]
    end = max(bounds) if bounds else stamp(run.get("updated_at"))
    wall = (end - start) if end is not None and start is not None and end >= start else None
    queue = []
    execution = []
    for job in jobs or []:
        a, b, c = (stamp(job.get(k)) for k in ("created_at", "started_at", "completed_at"))
        if a is not None and b is not None and b >= a:
            queue.append(b - a)
        if b is not None and c is not None and c >= b:
            execution.append(c - b)
    attempts = run.get("attempts", [])
    # Workflow wait is NOT the PR/HEAD elapsed time. Reruns retain the
    # original run.created_at, so it cannot anchor the final attempt's queue.
    # Use an explicitly dated final attempt; otherwise use its first scheduled
    # job as a conservative boundary (never infer an hour of runner queue).
    attempt_count = max(int(run.get("run_attempt") or 1), len(attempts))
    starts = [stamp(j.get("started_at")) for j in jobs or []]
    starts = [v for v in starts if v is not None]
    created = [stamp(j.get("created_at")) for j in jobs or []]
    created = [v for v in created if v is not None]
    first_created = min(created) if created else None
    attempt_start = start
    wait_reference = "run_created_at"
    if attempt_count > 1:
        meta = attempts[-1].get("metadata", {}) if attempts else {}
        explicit_start = stamp(meta.get("run_started_at"))
        # Only trust metadata for the current attempt when its number matches.
        meta_number = meta.get("run_attempt", meta.get("attempt"))
        if meta_number is None or int(meta_number) != attempt_count:
            explicit_start = None
        # Large pre-job gaps may reflect stale metadata or controller delays;
        # report only evidenced queue, never label them runner waiting.
        if (explicit_start is not None and first_created is not None and
                first_created - 120 <= explicit_start <= min(starts or [first_created])):
            attempt_start = explicit_start
            wait_reference = "last_attempt_run_started_at"
        elif first_created is not None:
            attempt_start = first_created
            wait_reference = "last_attempt_job_created_at_fallback"
        else:
            attempt_start = None
            wait_reference = "last_attempt_start_unknown"
    workflow_wait = (max(0, min(starts) - attempt_start)
                     if starts and attempt_start is not None else None)
    return dict(wall_seconds=wall, workflow_wait_seconds=workflow_wait,
                workflow_wait_reference=wait_reference,
                job_queue_seconds=stats(queue), job_execution_seconds=stats(execution),
                jobs_seen=None if jobs is None else len(jobs),
                attempt_count=attempt_count,
                conclusion=conclusion(run),
                anomalous_no_jobs=(jobs == [] and wall is not None and
                                   wall > ANOMALY_SECONDS),
                completion_source="jobs" if bounds else "run_updated_at_proxy")


def select_latest_heads(runs, limit):
    """Keep all workflows for newest N distinct SHA heads, never fastest runs.

    Selection uses the earliest real run created_at per SHA. A date-filtered
    API query must be exhaustive before selection: truncating a page of runs
    could quietly omit a slow workflow and understate HEAD wall latency.
    """
    if limit is None:
        return list(runs)
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("latest-heads must be positive")
    starts = {}
    for r in runs:
        if r.get("event") != "pull_request" or not r.get("head_sha"):
            continue
        created = stamp(r.get("created_at"))
        if created is None:
            continue
        sha = r["head_sha"]
        starts[sha] = min(starts.get(sha, created), created)
    chosen = set(sorted(starts, key=lambda sha: (starts[sha], sha),
                        reverse=True)[:limit])
    return [r for r in runs if r.get("head_sha") in chosen]


def _dedup_runs(runs):
    by_id = {}
    for r in runs:
        key = r.get("id")
        if not isinstance(key, int):
            raise ValueError("run id must be integer")
        if key in by_id:
            old = by_id[key]
            if old.get("head_sha") != r.get("head_sha"):
                raise ValueError("contradictory SHA for run id")
            if (r.get("run_attempt") or 1) > (old.get("run_attempt") or 1):
                by_id[key] = r
        else:
            by_id[key] = r
    return list(by_id.values())


def group_heads(runs, cutoff=CUTOFF):
    grouped = defaultdict(list)
    for r in _dedup_runs(runs):
        if r.get("event") != "pull_request" or not r.get("head_sha"):
            continue
        if stamp(r.get("created_at")) is None:
            continue
        if stamp(r["created_at"]) < stamp(cutoff):
            continue
        grouped[r["head_sha"]].append(r)
    heads = []
    for sha, members in grouped.items():
        prs = set()
        for r in members:
            prs.update(int(p["number"]) for p in r.get("pull_requests", []) if p.get("number"))
            prs.update(int(p) for p in r.get("resolved_prs", []))
        state = [conclusion(r) for r in members]
        names = {r.get("path", "").rsplit("/", 1)[-1] for r in members}
        absent = sorted(STABLE - names)
        start = min(stamp(r["created_at"]) for r in members)
        # Use job completions where available, run.updated_at proxy otherwise.
        details = [analyze_run(r) for r in members]
        ends = [start + 0]  # this HEAD is not complete unless ALL workflows complete
        for r, d in zip(members, details):
            s = stamp(r.get("created_at"))
            if s is not None and d["wall_seconds"] is not None:
                ends.append(s + d["wall_seconds"])
        terminal = all(r.get("status") == "completed" for r in members)
        if not terminal:
            verdict = "IN_PROGRESS"
        elif "FAILURE" in state or "TIMED_OUT" in state or "ACTION_REQUIRED" in state:
            verdict = "FAILURE"
        elif "CANCELLED" in state:
            verdict = "CANCELLED"
        elif "UNKNOWN" in state:
            verdict = "UNKNOWN"
        elif any(conclusion(r) == "SKIPPED" and r.get("path", "").rsplit("/", 1)[-1] in STABLE
                 for r in members):
            verdict = "SKIPPED"
        elif absent:
            verdict = "NOT_TRIGGERED"
        elif all(conclusion(r) in ("SUCCESS", "SKIPPED", "NEUTRAL") for r in members):
            verdict = "SUCCESS"  # optional skipped retained in per-workflow rows
        else:
            verdict = "UNKNOWN"
        abnormal = any(d["anomalous_no_jobs"] for d in details)
        heads.append(dict(sha=sha, prs=sorted(prs), run_count=len(members),
            start=start, wall_seconds=(max(ends) - start if terminal else None),
            verdict=verdict, missing_stable=absent, anomaly=abnormal,
            old_head=False, runs=members))
    # Same PR can appear on many HEADs. Never count them as independent PRs.
    by_pr = defaultdict(list)
    for h in heads:
        for p in h["prs"]:
            by_pr[p].append(h)
    for hs in by_pr.values():
        hs.sort(key=lambda h: (h["start"], h["sha"]))
        for h in hs[:-1]:
            h["old_head"] = True
            if h["verdict"] == "CANCELLED":
                h["old_head_cancelled"] = True
    return sorted(heads, key=lambda h: (h["start"], h["sha"]))


def summarize(runs, cutoff=CUTOFF):
    heads = group_heads(runs, cutoff)
    valid = [h["wall_seconds"] for h in heads if h["wall_seconds"] is not None and not h["anomaly"]]
    by_family = defaultdict(list)
    states = Counter()
    for h in heads:
        for r in h["runs"]:
            d = analyze_run(r)
            f = family(r.get("path"))
            states[(f, d["conclusion"])] += 1
            if d["wall_seconds"] is not None and not d["anomalous_no_jobs"] and r.get("status") == "completed":
                by_family[f].append(d["wall_seconds"])
    all_terminal_raw = [h["wall_seconds"] for h in heads if h["wall_seconds"] is not None]
    return dict(heads=heads, all_terminal=stats(valid), all_terminal_raw=stats(all_terminal_raw),
                successes=stats([h["wall_seconds"] for h in heads
                                 if h["verdict"] == "SUCCESS" and not h["anomaly"]]),
                by_family={f: stats(v) for f, v in sorted(by_family.items())},
                by_state={f"{k[0]}/{k[1]}": v for k, v in sorted(states.items())},
                verdicts=dict(Counter(h["verdict"] for h in heads)))


class GitHubReadOnly:
    def __init__(self, repo, token=None):
        self.root = "https://api.github.com/repos/" + repo
        self.token = token
        self.calls = 0

    def get(self, endpoint, params=None):
        url = self.root + endpoint
        if params:
            url += "?" + urllib.parse.urlencode(params)
        if not url.startswith("https://api.github.com/repos/"):
            raise ValueError("only GitHub repository GET allowed")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "ci-opt3-perf-audit/1",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                self.calls += 1
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Never print request headers or token.
            raise RuntimeError(f"GitHub GET {endpoint}: HTTP {exc.code}; rate limit/auth? ") from None

    def pages(self, endpoint, *, limit=30, params=None):
        if limit < 1:
            raise ValueError("pages limit must be >0")
        for page in range(1, limit + 1):
            p = dict(params or {}, per_page=100, page=page)
            obj = self.get(endpoint, p)
            items = obj if isinstance(obj, list) else obj.get("workflow_runs", obj.get("jobs", []))
            yield items
            if len(items) < 100:
                break


def fetch_live(client, *, max_pages, cutoff=CUTOFF, through=None, with_jobs=True,
               max_jobs_runs=None, with_pr_files=True, created=None,
               latest_heads=None):
    """Snapshot entire collected interval; never silently cap population."""
    found = []
    exhausted = False
    parameters = {"event": "pull_request"}
    if created is not None:
        parameters["created"] = created  # GitHub REST date-search range
    for i, page in enumerate(client.pages("/actions/runs", limit=max_pages,
                        params=parameters), 1):
        found.extend(page)
        if len(page) < 100:
            exhausted = True
            break
        # Pages are by creation date descending; ensure older C99 baseline coverage
        # by separately retrieving authoritative published run ids.
        if not created and page and all(stamp(r.get("created_at")) < stamp(cutoff) for r in page):
            exhausted = True  # All newer runs covered; don't need full historical history.
            break
    if not exhausted:
        raise RuntimeError(f"pagination incomplete after {max_pages} pages; increase --max-pages")
    sample = [r for r in found if stamp(r.get("created_at")) and
              stamp(r["created_at"]) >= stamp(cutoff) and
              (through is None or stamp(r["created_at"]) <= stamp(through))]
    sample = select_latest_heads(sample, latest_heads)
    missing_shas = sorted({r["head_sha"] for r in sample if not r.get("pull_requests")})
    pr_by_sha = {}
    for sha in missing_shas:
        prs = client.get("/commits/" + sha + "/pulls")
        pr_by_sha[sha] = [p["number"] for p in prs if p.get("number")]
    for r in sample:
        r["resolved_prs"] = pr_by_sha.get(r["head_sha"], []) if not r.get("pull_requests") else []
    if with_jobs:
        if max_jobs_runs is not None and len(sample) > max_jobs_runs:
            raise RuntimeError("job-run cap would bias the measured population")
        for r in sample:
            attempt_count = r.get("run_attempt") or 1
            hist = []
            for n in range(1, attempt_count + 1):
                try:
                    meta = client.get(f"/actions/runs/{r['id']}/attempts/{n}")
                    # Preserve attempt identity; run-level created_at belongs
                    # to the original run, not the re-run's runner queue.
                    meta["attempt"] = n
                except RuntimeError:
                    meta = {"attempt": n, "metadata_unavailable": True}
                    if n == attempt_count:
                        # run_started_at may refer to the latest attempt, but
                        # we do not trust it without attempt-scoped evidence.
                        meta.update(status=r.get("status"),
                                    conclusion=r.get("conclusion"))
                jobs = []
                for batch in client.pages(f"/actions/runs/{r['id']}/attempts/{n}/jobs", limit=10):
                    jobs.extend(batch)
                hist.append({"number": n, "metadata": meta,
                             "jobs": jobs})
            r["attempts"] = hist
            r["jobs"] = hist[-1]["jobs"]
    if with_pr_files:
        prs = sorted({p for r in sample for p in (
            r.get("resolved_prs", []) + [x["number"] for x in r.get("pull_requests", [])])})
        pr_info = {}
        for p in prs:
            info = client.get(f"/pulls/{p}")
            files = []
            for batch in client.pages(f"/pulls/{p}/files", limit=30):
                files.extend(x["filename"] for x in batch)
            pr_info[str(p)] = {"head_sha": info.get("head", {}).get("sha"), "files": files}
    else:
        pr_info = {}
    baseline = []
    for rid in BASELINE_C99_IDS:
        baseline.append(client.get(f"/actions/runs/{rid}"))
    return {"source": "LIVE_GITHUB_API", "cutoff": cutoff, "through": through,
            "complete_post_window": exhausted, "runs": sample,
            "baseline_c99_runs": baseline, "pr_info": pr_info,
            "metadata": {"calls": client.calls, "max_pages": max_pages,
                         "created_filter": created, "latest_heads": latest_heads}}


def diff_type(files):
    if files is None:
        return "UNKNOWN_REVISION"
    if all(x.startswith("docs/") or x.endswith(".md") for x in files):
        return "DOC_ONLY"
    if any(x.startswith("firmware/") or x.startswith("video/") or x.startswith("io/") for x in files):
        return "HW4_TARGET"
    if any(x.startswith("core/") for x in files):
        return "CORE"
    if any(x.startswith("tools/ci/") for x in files):
        return "CI_TOOLS"
    if any(x.startswith("tests/fixtures/cpc6128/") for x in files):
        return "CPC_ARCHIVE"
    return "OTHER"


def report(snapshot):
    if snapshot.get("source") not in ("LIVE_GITHUB_API", "TEST_SYNTHETIC"):
        raise ValueError("source missing; label fixture as TEST_SYNTHETIC")
    summary = summarize(snapshot["runs"], snapshot.get("cutoff", CUTOFF))
    heads = summary["heads"]
    repo = snapshot.get("repo", "Kharn27/ESP32-Locomotive-Basic")
    base = "https://github.com/" + repo
    pre = [r for r in snapshot.get("baseline_c99_runs", []) if r.get("path", "").endswith("basic-program.yml")]
    pre_stats = stats([run_duration(r) for r in pre if r.get("status") == "completed"])
    pr_info = snapshot.get("pr_info", {})
    typed = Counter()
    pr_groups = defaultdict(list)
    for h in heads:
        classes = {diff_type(pr_info[str(p)]["files"])
                   for p in h["prs"] if str(p) in pr_info and
                   pr_info[str(p)]["head_sha"] == h["sha"]}
        h["diff_class"] = next(iter(classes)) if len(classes) == 1 else "UNKNOWN_REVISION"
        typed[h["diff_class"]] += 1
        for p in h["prs"]:
            pr_groups[p].append(h)
    # PR cycle: first observed HEAD creation -> last HEAD verdict; NOT a merged-PR SLA.
    cycles = []
    for num, hs in pr_groups.items():
        hs.sort(key=lambda h: h["start"])
        last = hs[-1]
        if last["wall_seconds"] is not None:
            cycles.append((num, last["start"] + last["wall_seconds"] - hs[0]["start"], len(hs)))
    lines = ["# CI-OPT3-PERF-A — rapport de mesure reproductible",
        "", f"**Origine :** `{snapshot['source']}` ; **coupure UTC :** `{snapshot.get('cutoff', CUTOFF)}` ; **fin fenêtre :** `{snapshot.get('through') or 'non fixée'}`.",
        "", "**Percentiles :** nearest-rank `sorted[ceil(p*n)-1]` sur secondes entières ;"
        " durées en minutes, sans somme des workflows parallèles.",
        "", "**Date de verdict par run :** fin du dernier job de la dernière tentative si disponible ;"
        " à défaut, `updated_at` comme proxy explicitement signalé. Le HEAD finit au dernier verdict"
        " des couloirs en parallèle. `run.created_at` reste le départ du HEAD, y compris si rerun ;"
        " **l'attente du rerun** part de son propre `run_started_at` ou, en absence de preuve,"
        " du premier `job.created_at` de cette tentative (borne conservatrice).",
        "", "| Population | N | P50 min | P95 min | Max min |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, values in (("HEADs terminés TOUS, y compris incidents (raw)", summary["all_terminal_raw"]),
                         ("HEADs terminés hors anomalies no-jobs >1h (tous verdicts)", summary["all_terminal"]),
                         ("HEADs SUCCESS seulement (diagnostic, pas échantillon primaire)", summary["successes"]),
                         ("Baseline pré CI-OPT3 C99 uniquement (non comparable au global)", pre_stats)):
        lines.append(f"| {name} | {values['n']} | {minutes(values['p50'])} | {minutes(values['p95'])} | {minutes(values['max'])} |")
    lines += ["", "## Familles — runs terminés, tous verdicts hors anomalie no-jobs >1h",
              "", "| Famille | N runs | P50 min | P95 min | Max min |", "|---|---:|---:|---:|---:|"]
    for fam, values in sorted(summary["by_family"].items()):
        lines.append(f"| {fam} | {values['n']} | {minutes(values['p50'])} | {minutes(values['p95'])} | {minutes(values['max'])} |")
    lines += ["", "## Types de diff / comparabilité", "",
              "Classe déterminée par les fichiers de la PR **uniquement si son HEAD courant = SHA mesuré** ;"
              " sinon UNKNOWN_REVISION (pas de reconstruction inventée du diff historique).", "",
              "| Type | HEADs |", "|---|---:|"]
    for k, n in sorted(typed.items()):
        lines.append(f"| {k} | {n} |")
    lines += ["", "## Cycles de PR (révisions successives; des HEADs d'une même PR sont corrélés)", "",
              "| PR | HEADs observés | Cycle observé (min) |", "|---|---:|---:|"]
    for num, seconds, count in sorted(cycles):
        lines.append(f"| [#{num}]({base}/pull/{num}) | {count} | {minutes(seconds)} |")
    lines += ["", "## HEADs post-déploiement (sans sélection sur succès)",
        "", "| PR | SHA | Classe | Runs | Verdict | Dernier verdict (min) | Remplacé | Incident |",
        "|---|---|---|---:|---|---:|---|---|"]
    for h in heads:
        prs = ", ".join(f"[#{p}]({base}/pull/{p})" for p in h["prs"]) or "PR_NON_RESOLUE"
        sha = h["sha"]
        href = f"[{sha[:12]}]({base}/commit/{sha})"
        links = ", ".join(f"[{r['id']}]({base}/actions/runs/{r['id']})" for r in h["runs"][:2])
        lines.append(f"| {prs} | {href} | {h['diff_class']} | {h['run_count']} ([runs]({base}/actions?query={sha[:12]}), {links}) | {h['verdict']}"
                     f" | {minutes(h['wall_seconds'])} | {'OLD_HEAD_CANCELLED' if h.get('old_head_cancelled') else 'OLD_HEAD' if h['old_head'] else 'non/unknown'} | {'NO_JOBS_LONG' if h['anomaly'] else '—'} |")
    lines += ["", "## Attente jobs, tentatives, reruns et incident no-jobs", "",
              "| HEAD SHA | Run | Famille | Tentatives | Conclusion finale | Run (min) | Attente workflow (s) | Référence attente | Queue jobs P95 (s) | Exécution jobs P95 (s) | Jobs | Source fin |",
              "|---|---|---|---:|---|---:|---:|---|---:|---:|---:|---:|---|"]
    for h in heads:
        for r in h["runs"]:
            d = analyze_run(r)
            if (r.get("run_attempt", 1) > 1 or d["anomalous_no_jobs"] or
                family(r.get("path")) == "HW4_MEMORY_A0" or
                d["conclusion"] in ("FAILURE", "CANCELLED") or
                d["workflow_wait_seconds"] is not None and d["workflow_wait_seconds"] > 30):
                url = f"{base}/actions/runs/{r['id']}"
                lines.append(f"| `{h['sha'][:12]}` | [{r['id']}]({url}) | {family(r.get('path'))} | {d['attempt_count']} | {d['conclusion']} | {minutes(d['wall_seconds'])} | "
                             f"{d['workflow_wait_seconds'] if d['workflow_wait_seconds'] is not None else 'N/A'} | "
                             f"{d['workflow_wait_reference']} | "
                             f"{d['job_queue_seconds']['p95'] if d['job_queue_seconds']['n'] else 'N/A'} | "
                             f"{d['job_execution_seconds']['p95'] if d['job_execution_seconds']['n'] else 'N/A'} | "
                             f"{d['jobs_seen'] if d['jobs_seen'] is not None else 'UNKNOWN'} | {d['completion_source']} |")
    lines += ["", "## Répartition des conclusions par famille", "", "| Famille / état | N |", "|---|---:|"]
    for item, num in summary["by_state"].items():
        lines.append(f"| {item} | {num} |")
    lines += ["", "## Conclusion de preuve et contrôles historiques", "",
              "`PERF_NOT_YET_VERIFIED` : 20 HEADs observés ne garantissent ni 20 PR indépendantes ni"
              " 20 HEADs de même type de diff. Aucun gain global pré/post chiffré n'est établi :"
              " baseline pré-OPT3 C99 seule, versus mur PR post-OPT3 ; l'objectif indicatif"
              " P95 < 5 min n'est pas certifié par cette comparaison.", "",
              "Le contrôle HW4-A0 #190 compile base/HEAD, trois profils chacun (six images),"
              " distinct du budget physique CYD ; ne pas interpréter l'échec mémoire"
              " comme une défaillance Xtensa. L'incident `0d4214fdc4670dcdaa36f7704fe692b92d43d963`"
              " doit rester un échec avec jobs vides, jamais une compilation de 15 h 16."
              " Les acquisitions CPC historiques sont comptées à part de CPC_PERMANENT :"
              " un `SKIPPED` d'acquisition n'atteste aucune acquisition ROM.", "",
              "**Limites :** le run `updated_at` est un proxy d'achèvement si les jobs n'ont pas de `completed_at`."
              " Les `SKIPPED` et `NOT_TRIGGERED` ne sont jamais du succès ; les acquisitions CPC sont hors SLA PR ordinaire."
              " Les RUNS des HEADs remplacés et les verdicts négatifs restent présents."
              " L'association SHA→PR via commits peut être ambiguë, et la classe du diff d'une révision ancienne est `UNKNOWN_REVISION`."
              " Le contrôle de 20 HEADs distincts ne prouve pas 20 PR indépendantes ni une comparaison pré/post équitable.", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default="Kharn27/ESP32-Locomotive-Basic")
    ap.add_argument("--input", type=Path, help="offline JSON snapshot; synthetic must be labeled TEST_SYNTHETIC")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--snapshot-out", type=Path, help="save raw JSON run metadata WITHOUT any token")
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--created", help="GitHub REST created= date/range; bounds pagination")
    ap.add_argument("--latest-heads", type=int, help="newest N distinct SHA, all their runs")
    ap.add_argument("--no-jobs", action="store_true", help="faster but no queue/real completion proof")
    ap.add_argument("--no-pr-files", action="store_true", help="skip diff typing")
    ap.add_argument("--cutoff", default=CUTOFF)
    ap.add_argument("--through", help="freeze cohort by run creation UTC ISO-8601")
    args = ap.parse_args(argv)
    if args.input:
        snapshot = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        snapshot = fetch_live(GitHubReadOnly(args.repo, os.getenv("GITHUB_TOKEN")),
                              max_pages=args.max_pages, cutoff=args.cutoff, through=args.through,
                              with_jobs=not args.no_jobs, with_pr_files=not args.no_pr_files,
                              created=args.created, latest_heads=args.latest_heads)
    if args.input and args.latest_heads is not None:
        snapshot["runs"] = select_latest_heads(snapshot["runs"], args.latest_heads)
    snapshot["repo"] = args.repo
    output = report(snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    if args.snapshot_out:
        args.snapshot_out.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot_out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    s = summarize(snapshot["runs"], snapshot.get("cutoff", CUTOFF))
    print(f"HEADs={len(s['heads'])} verdicts={s['verdicts']} all_terminal={s['all_terminal']} calls={snapshot.get('metadata', {}).get('calls', 'offline')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
