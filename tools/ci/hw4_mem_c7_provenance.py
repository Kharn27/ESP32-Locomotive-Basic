#!/usr/bin/env python3
"""C5: authoritative live GitHub PR refs + real Git checkouts and merge-base.

Must run on trusted CI: pr-live.json is retrieved directly from GitHub API,
not supplied by a candidate's repository. A second fetch is mandatory after
the builds; comparator also matches the output against that fresh response.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from hw4_a0_compare_memory import checked_sha
from hw4_a0_provenance import validate_pr
from hw4_mem_c7_v2 import A0, RENDER_A, B3, ANCHORS, EXPECTED

# Live main SHA determines the valid incremental base, not a frozen old branch.


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args],
                                   text=True, stderr=subprocess.PIPE).strip()


def checked_git(live, repo, number, base_dir, head_dir, expected_base):
    base_sha = checked_sha(live["base"]["sha"])
    head_sha = checked_sha(live["head"]["sha"])
    validate_pr(live, repo, number, base_sha, head_sha)
    if base_sha != expected_base:
        raise ValueError("FAIL_CLOSED: live main/PR base drift")
    for label, folder, sha in (("base", base_dir, base_sha), ("head", head_dir, head_sha)):
        if git(folder, "rev-parse", "HEAD") != sha:
            raise ValueError("FAIL_CLOSED: wrong checkout " + label)
        if git(folder, "cat-file", "-t", sha) != "commit":
            raise ValueError("FAIL_CLOSED: source not a Git commit " + label)
    if git(head_dir, "cat-file", "-t", base_sha) != "commit":
        raise ValueError("FAIL_CLOSED: base not present in full HEAD history")
    mb = checked_sha(git(head_dir, "merge-base", base_sha, head_sha))
    # A diverged PR may exist: report the true merge base, do not synthesize
    # a merged tree or silently replace the real base with merge-base.
    for sha in (base_sha, head_sha):
        rc = subprocess.run(["git", "-C", str(head_dir), "merge-base",
                             "--is-ancestor", mb, sha], capture_output=True)
        if rc.returncode:
            raise ValueError("FAIL_CLOSED: corrupted Git ancestry")
    if mb != base_sha:
        raise ValueError("FAIL_CLOSED: PR diverged from current main; STOP")
    return {"status": "PROVENANCE_PASS", "repo": repo, "pr_number": number,
            "base_sha": base_sha, "head_sha": head_sha,
            "base_tree": checked_sha(git(base_dir, "rev-parse", "HEAD^{tree}")),
            "head_tree": checked_sha(git(head_dir, "rev-parse", "HEAD^{tree}")),
            "merge_base": mb, "ancestry_verified": True,
            "diverged_from_base": False,
            "anchors": ANCHORS, "historical_bytes": EXPECTED,
            "policy_main": base_sha}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-pr", required=True, type=Path)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr-number", required=True, type=int)
    ap.add_argument("--base-dir", required=True, type=Path)
    ap.add_argument("--head-dir", required=True, type=Path)
    ap.add_argument("--expected-base", required=True)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        live = json.loads(args.live_pr.read_text())
        report = checked_git(live, args.repo, args.pr_number, args.base_dir,
                             args.head_dir, args.expected_base)
        rc = 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError,
            json.JSONDecodeError, TypeError) as exc:
        report = {"status": "MEASUREMENT_INVALID", "error": str(exc)}
        rc = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return rc


if __name__ == "__main__":
    sys.exit(main())
