#!/usr/bin/env python3
"""C6-B1 read-only GitHub M/B/H/MB/C evidence; NOT a memory gate.

No Xtensa/build/ELF/BIN consumption. A valid provenance snapshot NEVER
produces a PASS verdict for PR memory or integration readiness.
"""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "Kharn27/ESP32-Locomotive-Basic"
CONTRACT = "HW4-MEM-C6-B1/v1"
SHA = re.compile(r"[0-9a-f]{40}\Z")
HISTORY = {
    "evaluation": "HISTORICAL_UNCHANGED_NOT_REEVALUATED",
    "render_a_sealed": "HISTORICAL_FAILURE",
    "c3_sealed": "HISTORICAL_FAILURE",
    "a0_console_sealed": "HISTORICAL_DEBT",
    "root_cause": "ROOT_CAUSE_UNVERIFIED",
    "device": "ON_DEVICE_UNVERIFIED",
}


class EvidenceError(Exception):
    def __init__(self, code, detail=""):
        super().__init__(code + (": " + detail if detail else ""))
        self.code = code
        self.detail = detail


def need(condition, code):
    if not condition:
        raise EvidenceError(code)


def sha(value, code="INVALID_SHA"):
    need(isinstance(value, str) and SHA.fullmatch(value) is not None
         and value != "0" * 40, code)
    return value


def obj(value, code="API_RESPONSE_INVALID"):
    need(isinstance(value, dict), code)
    return value


def field(value, *path):
    for key in path:
        value = obj(value).get(key)
    return value


def date_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EvidenceError("API_REDIRECT_REFUSED")


class GitHubReadOnly:
    """Fixed-repository GET-only API; no mutation or redirect to arbitrary hosts."""

    def __init__(self, token=None, timeout=20):
        self.token = token
        self.timeout = timeout
        self.opener = urllib.request.build_opener(NoRedirect)

    def get(self, path):
        need(path.startswith("/") and "?" not in path and "//" not in path,
             "UNSAFE_API_PATH")
        url = "https://api.github.com/repos/" + REPO + path
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "hw4-mem-c6-b1-readonly"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                need(response.status == 200, "API_UNAVAILABLE")
                data = json.load(response)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                json.JSONDecodeError) as exc:
            # Do not leak token, response body, or request headers.
            status = getattr(exc, "code", "NETWORK")
            raise EvidenceError("API_UNAVAILABLE", "HTTP_" + str(status)) from None
        return obj(data)


def comparison(client, left, right):
    return client.get("/compare/" + sha(left) + "..." + sha(right))


def git_commit(client, commit_sha):
    return client.get("/git/commits/" + sha(commit_sha))


def capture_once(client, number):
    """Query live GitHub objects; feed their immutable data into pure validation."""
    need(isinstance(number, int) and not isinstance(number, bool) and number > 0,
         "PR_NUMBER_INVALID")
    branch = client.get("/branches/main")
    pull = client.get("/pulls/" + str(number))
    m = sha(field(branch, "commit", "sha"))
    b = sha(field(pull, "base", "sha"))
    h = sha(field(pull, "head", "sha"))
    mb_mh = comparison(client, m, h)
    mb_bh = comparison(client, b, h)
    g_mb = sha(field(mb_mh, "merge_base_commit", "sha"))
    g_bh = sha(field(mb_bh, "merge_base_commit", "sha"))
    graphs = {
        "base_main": comparison(client, b, m),
        "main_head": mb_mh,
        "base_head": mb_bh,
        "mb_main": comparison(client, g_mb, m),
        "mb_head": comparison(client, g_mb, h),
        "bh_base": comparison(client, g_bh, b),
        "bh_head": comparison(client, g_bh, h),
    }
    commits = {k: git_commit(client, v) for k, v in
               (("M", m), ("B", b), ("H", h), ("MB", g_mb), ("MB_BH", g_bh))}
    preview_sha = pull.get("merge_commit_sha")
    preview = {"sha": preview_sha, "commit": None, "tree": None,
               "availability": "ABSENT", "parent_main_graph": None}
    if preview_sha is not None:
        sha(preview_sha, "PREVIEW_SHA_INVALID")
        try:
            preview["commit"] = git_commit(client, preview_sha)
            tree_sha = sha(field(preview["commit"], "tree", "sha"),
                           "PREVIEW_TREE_INVALID")
            preview["tree"] = client.get("/git/trees/" + tree_sha)
            preview["availability"] = "PRESENT"
            # The GitHub test-merge ref can lag behind main. Verify its
            # first parent is an actual ancestor of the current M before
            # classifying it as STALE rather than a forged parent.
            parents = field(preview["commit"], "parents")
            if (isinstance(parents, list) and len(parents) == 2 and
                    isinstance(parents[0], dict) and
                    parents[0].get("sha") != m and
                    isinstance(parents[1], dict) and
                    parents[1].get("sha") == h):
                parent = sha(parents[0].get("sha"), "PREVIEW_PARENTS_INVALID")
                preview["parent_main_graph"] = comparison(client, parent, m)
        except EvidenceError as exc:
            if exc.code != "API_UNAVAILABLE":
                raise
            preview["commit"] = None
            preview["tree"] = None
            preview["availability"] = "UNAVAILABLE"
            preview["reason"] = "PREVIEW_API_UNAVAILABLE"
    return {
        "captured_at": date_utc(), "branch": branch, "pull": pull,
        "graphs": graphs, "commits": commits, "preview": preview,
    }


def validate_compare(value, base, head):
    """Trust only GitHub's real compare response; reject inconsistent fixtures."""
    value = obj(value)
    need(sha(field(value, "base_commit", "sha")) == base,
         "COMPARE_BASE_MISMATCH")
    # GitHub compare REST has no head_commit property: the final commit in
    # its ahead-list is the requested head whenever ahead_by > 0.
    mb = sha(field(value, "merge_base_commit", "sha"), "MERGE_BASE_INVALID")
    ahead, behind, status = (value.get("ahead_by"), value.get("behind_by"),
                             value.get("status"))
    need(all(type(x) is int and x >= 0 for x in (ahead, behind)),
         "COMPARE_COUNTS_INVALID")
    expected = ("identical" if ahead == behind == 0 else
                "ahead" if ahead > 0 and behind == 0 else
                "behind" if behind > 0 and ahead == 0 else "diverged")
    need(status == expected, "COMPARE_STATUS_INVALID")
    if ahead > 0:
        commits = value.get("commits")
        need(isinstance(commits, list) and len(commits) > 0 and
             sha(field(commits[-1], "sha")) == head, "COMPARE_HEAD_MISMATCH")
    if behind == 0:
        need(mb == base, "MERGE_BASE_INCORRECT")
    if ahead == 0:
        need(mb == head, "MERGE_BASE_INCORRECT")
    return {"base": base, "head": head, "merge_base": mb,
            "ahead_by": ahead, "behind_by": behind, "status": status}


def validate_commit(value, expected):
    value = obj(value)
    need(sha(value.get("sha")) == expected, "COMMIT_SHA_MISMATCH")
    tree = sha(field(value, "tree", "sha"), "TREE_SHA_INVALID")
    parents = value.get("parents")
    need(isinstance(parents, list), "COMMIT_PARENTS_INVALID")
    for parent in parents:
        sha(field(parent, "sha"), "COMMIT_PARENTS_INVALID")
    return {"sha": expected, "tree": tree,
            "parents": [parent["sha"] for parent in parents]}


def verify_preview(raw, m, h):
    prev = obj(raw)
    status = prev.get("availability")
    if status == "ABSENT":
        need(prev.get("sha") is None and prev.get("commit") is None,
             "PREVIEW_ABSENCE_INCONSISTENT")
        return {"status": "UNVERIFIED", "reason": "PREVIEW_ABSENT",
                "sha": None, "tree": None, "parents": None}
    p_sha = sha(prev.get("sha"), "PREVIEW_SHA_INVALID")
    need(p_sha not in (m, h), "PREVIEW_SHA_REPLAY")
    if status == "UNAVAILABLE":
        need(prev.get("commit") is None and prev.get("tree") is None and
             prev.get("reason") == "PREVIEW_API_UNAVAILABLE",
             "PREVIEW_UNAVAILABLE_INCONSISTENT")
        return {"status": "UNVERIFIED", "reason": "PREVIEW_API_UNAVAILABLE",
                "sha": p_sha, "tree": None, "parents": None}
    need(status == "PRESENT", "PREVIEW_STATE_UNKNOWN")
    commit = validate_commit(prev.get("commit"), p_sha)
    tree = obj(prev.get("tree"))
    need(sha(tree.get("sha"), "PREVIEW_TREE_INVALID") == commit["tree"],
         "PREVIEW_TREE_MISMATCH")
    if commit["parents"] == [m, h]:
        need(prev.get("parent_main_graph") is None,
             "PREVIEW_UNEXPECTED_ANCESTRY_PROOF")
        return {"status": "VERIFIED", "reason": None,
                "sha": p_sha, "tree": commit["tree"],
                "parents": commit["parents"]}
    if (len(commit["parents"]) == 2 and commit["parents"][1] == h and
            commit["parents"][0] not in (m, h)):
        former_main = commit["parents"][0]
        proof = validate_compare(prev.get("parent_main_graph"), former_main, m)
        need(proof["merge_base"] == former_main and
             proof["behind_by"] == 0 and proof["ahead_by"] > 0,
             "PREVIEW_PARENTS_MISMATCH")
        return {"status": "UNVERIFIED", "reason": "PREVIEW_STALE_MAIN",
                "sha": p_sha, "tree": commit["tree"],
                "parents": commit["parents"],
                "former_main_ancestor_verified": former_main}
    raise EvidenceError("PREVIEW_PARENTS_MISMATCH")


def validate_snapshot(raw, repo, number):
    """Pure verifier: all input objects injectable; no network, no PASS metrics."""
    need(repo == REPO, "REPOSITORY_MISMATCH")
    need(type(number) is int and number > 0, "PR_NUMBER_INVALID")
    s = obj(raw)
    observed = s.get("captured_at")
    need(isinstance(observed, str), "CAPTURE_TIMESTAMP_INVALID")
    try:
        observed_date = dt.datetime.fromisoformat(observed)
    except ValueError:
        raise EvidenceError("CAPTURE_TIMESTAMP_INVALID") from None
    need(observed_date.tzinfo is not None and
         observed_date.utcoffset() is not None, "CAPTURE_TIMESTAMP_INVALID")
    branch, pull = obj(s.get("branch")), obj(s.get("pull"))
    need(branch.get("name") == "main", "MAIN_REF_INVALID")
    m = sha(field(branch, "commit", "sha"))
    need(pull.get("number") == number, "PR_NUMBER_MISMATCH")
    need(pull.get("state") == "open" and pull.get("merged_at") is None,
         "PR_NOT_OPEN")
    need(field(pull, "base", "ref") == "main" and
         field(pull, "base", "repo", "full_name") == REPO,
         "PR_BASE_REPOSITORY_OR_REF_INVALID")
    need(field(pull, "head", "repo", "full_name") == REPO and
         isinstance(field(pull, "head", "ref"), str) and
         bool(field(pull, "head", "ref")), "PR_HEAD_REPOSITORY_OR_REF_INVALID")
    b, h = sha(field(pull, "base", "sha")), sha(field(pull, "head", "sha"))
    need(b != h and m != h, "PR_HEAD_EQUALS_BASE_OR_MAIN")
    observed_preview = pull.get("merge_commit_sha")
    if observed_preview is not None:
        sha(observed_preview, "PREVIEW_SHA_INVALID")
    need(observed_preview == obj(s.get("preview")).get("sha"),
         "PR_PREVIEW_IDENTITY_MISMATCH")
    graphs = obj(s.get("graphs"))
    g_bm = validate_compare(graphs.get("base_main"), b, m)
    need(g_bm["behind_by"] == 0 and g_bm["merge_base"] == b,
         "BASE_NOT_ANCESTOR_OF_MAIN")
    g_mh = validate_compare(graphs.get("main_head"), m, h)
    g_bh = validate_compare(graphs.get("base_head"), b, h)
    need(g_mh["ahead_by"] > 0 and g_bh["ahead_by"] > 0,
         "HEAD_NOT_AHEAD_OF_BASE_AND_MAIN")
    mb, bh_mb = g_mh["merge_base"], g_bh["merge_base"]
    ancestor_pairs = (("mb_main", mb, m), ("mb_head", mb, h),
                      ("bh_base", bh_mb, b), ("bh_head", bh_mb, h))
    for key, origin, destination in ancestor_pairs:
        graph = validate_compare(graphs.get(key), origin, destination)
        need(graph["behind_by"] == 0 and graph["merge_base"] == origin,
             "MERGE_BASE_NOT_ANCESTOR")
    commits = obj(s.get("commits"))
    identities = {name: validate_commit(commits.get(name), value)
                  for name, value in (("M", m), ("B", b), ("H", h),
                                      ("MB", mb), ("MB_BH", bh_mb))}
    # A single immutable commit SHA cannot authenticate two different trees.
    by_sha = {}
    for item in identities.values():
        value = (item["tree"], tuple(item["parents"]))
        if item["sha"] in by_sha:
            need(by_sha[item["sha"]] == value, "DUPLICATE_COMMIT_INCONSISTENT")
        by_sha[item["sha"]] = value
    preview = verify_preview(s.get("preview"), m, h)
    stale = b != m
    blockers = ["BLOCKED_STALE_BASE"] if stale else []
    if preview["status"] != "VERIFIED":
        blockers.append(preview["reason"])
    return {
        "repo": REPO, "pr_number": number, "captured_at": observed,
        "M": m, "B": b, "H": h, "MB": mb, "MB_BH": bh_mb,
        "trees": {k: v["tree"] for k, v in identities.items()},
        "graph": {"base_main": g_bm, "main_head": g_mh,
                  "base_head": g_bh, "base_head_diverged": bh_mb != b,
                  "stale_base": stale},
        "preview": preview,
        "mergeable_ui_only": pull.get("mergeable"),
        "draft": pull.get("draft"),
        "head_branch": field(pull, "head", "ref"),
        "PR_INCREMENTAL_VERDICT": "UNVERIFIED",
        "INTEGRATION_MEMORY_VERDICT": "UNVERIFIED",
        "INTEGRATION_READINESS": ("BLOCKED_STALE_BASE" if stale else "UNVERIFIED"),
        "blockers": blockers + ["XTENSA_BUILDS_NOT_EXECUTED"],
        "historical": dict(HISTORY),
    }


def compare_snapshots(first, second):
    """Only timestamp may vary; live refs, topology and candidate must be stable."""
    keys = ("repo", "pr_number", "M", "B", "H", "MB", "MB_BH", "trees",
            "graph", "preview", "mergeable_ui_only", "draft", "head_branch")
    changed = [k for k in keys if first[k] != second[k]]
    need(not changed, "SNAPSHOT_DRIFT:" + ",".join(changed))
    return True


def run(client, number):
    evidence = {"contract": CONTRACT, "repo": REPO, "pr_number": number,
                "snapshot_status": "MEASUREMENT_INVALID",
                "PR_INCREMENTAL_VERDICT": "MEASUREMENT_INVALID",
                "INTEGRATION_READINESS": "MEASUREMENT_INVALID",
                "INTEGRATION_MEMORY_VERDICT": "UNVERIFIED",
                "historical": dict(HISTORY), "observations": [],
                "reason": "NOT_STARTED"}
    try:
        for _ in range(2):
            raw = capture_once(client, number)
            verified = validate_snapshot(raw, REPO, number)
            # Store validated, minimal representations; not unauthenticated JSON claims.
            evidence["observations"].append(verified)
        first, second = evidence["observations"]
        compare_snapshots(first, second)
        evidence.update({"snapshot_status": "PROVENANCE_VERIFIED",
                         "blockers": second["blockers"],
                         "preview_reason": second["preview"]["reason"],
                         "PR_INCREMENTAL_VERDICT": "UNVERIFIED",
                         "INTEGRATION_READINESS": second["INTEGRATION_READINESS"],
                         "INTEGRATION_MEMORY_VERDICT": "UNVERIFIED",
                         "reason": "XTENSA_BUILDS_NOT_EXECUTED",
                         "stable_double_capture": True,
                         "historical": dict(HISTORY)})
        return evidence, 0  # Provenance only; NEVER memory PASS
    except (TypeError, KeyError, IndexError) as exc:
        evidence["reason"] = "API_RESPONSE_INVALID"
        evidence["detail"] = type(exc).__name__
        evidence["stable_double_capture"] = False
        return evidence, 2
    except EvidenceError as exc:
        evidence["reason"] = exc.code
        evidence["detail"] = exc.detail
        evidence["stable_double_capture"] = False
        return evidence, 2


def write_evidence(path, evidence):
    """No success if output cannot be written. Atomic replace avoids partial files."""
    dest = Path(path)
    temporary = dest.with_name(dest.name + ".tmp")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(dest)
    except OSError as exc:
        raise EvidenceError("OUTPUT_WRITE_FAILED", type(exc).__name__) from None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pr", type=int, required=True, help="real OPEN GitHub PR number")
    ap.add_argument("--output", required=True, help="JSON evidence path")
    args = ap.parse_args(argv)
    client = GitHubReadOnly(token=os.environ.get("GH_TOKEN") or
                            os.environ.get("GITHUB_TOKEN"))
    report, rc = run(client, args.pr)
    try:
        write_evidence(args.output, report)
    except EvidenceError as exc:
        print("C6_B1_MEASUREMENT_INVALID " + exc.code, file=sys.stderr)
        return 2
    print("C6_B1_SNAPSHOT=" + report["snapshot_status"] +
          " PR_INCREMENTAL_VERDICT=" + report["PR_INCREMENTAL_VERDICT"] +
          " INTEGRATION_READINESS=" + report["INTEGRATION_READINESS"] +
          " INTEGRATION_MEMORY=" + report["INTEGRATION_MEMORY_VERDICT"] +
          " REASON=" + report["reason"] +
          " BLOCKERS=" + ",".join(report.get("blockers", [])) +
          " PREVIEW_REASON=" + str(report.get("preview_reason")) +
          " OUTPUT=" + args.output)
    return rc


if __name__ == "__main__":
    sys.exit(main())
