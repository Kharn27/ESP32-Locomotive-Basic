#!/usr/bin/env python3
"""Fail-closed verification of live GitHub PR refs and three local Git checkouts."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from hw4_a0_compare_memory import A0_SHA, checked_sha


def validate_pr(payload, repo, number, base_sha, head_sha):
    checked_sha(base_sha)
    checked_sha(head_sha)
    if base_sha == head_sha:
        raise ValueError("FAIL_CLOSED: identical PR base and HEAD")
    if payload.get("number") != number or payload.get("state") != "open":
        raise ValueError("FAIL_CLOSED: PR identity/state mismatch")
    base, head = payload.get("base", {}), payload.get("head", {})
    if base.get("ref") != "main" or base.get("repo", {}).get("full_name") != repo:
        raise ValueError("FAIL_CLOSED: unexpected PR target repo/ref")
    if base.get("sha") != base_sha or head.get("sha") != head_sha:
        raise ValueError("FAIL_CLOSED: stale/falsified PR base or HEAD against live API")


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def validate_git(a0_path, base_path, head_path, base_sha, head_sha):
    for path, expected in ((a0_path, A0_SHA), (base_path, base_sha), (head_path, head_sha)):
        if git(path, "rev-parse", "HEAD") != expected:
            raise ValueError(f"FAIL_CLOSED: checkout SHA mismatch at {path}")
        if git(path, "cat-file", "-t", expected) != "commit":
            raise ValueError(f"FAIL_CLOSED: checkout object not a commit: {expected}")
    # head checkout fetch-depth:0: both PR branches' ancestry visible.
    if git(head_path, "cat-file", "-t", base_sha) != "commit":
        raise ValueError("FAIL_CLOSED: PR base Git object unavailable")
    ancestor = git(head_path, "merge-base", base_sha, head_sha)
    checked_sha(ancestor)
    for candidate in (base_sha, head_sha):
        if git(head_path, "merge-base", "--is-ancestor", ancestor, candidate) != "":
            raise ValueError("FAIL_CLOSED: merge-base graph inconsistent")
    return ancestor


def main(argv=None):
    ap = argparse.ArgumentParser()
    for name in ("api-response", "repo", "pr-number", "base-sha", "head-sha",
                 "a0-path", "base-path", "head-path", "output"):
        ap.add_argument("--" + name, required=True)
    args = ap.parse_args(argv)
    output = Path(args.output)
    try:
        payload = json.loads(Path(args.api_response).read_text(encoding="utf-8"))
        validate_pr(payload, args.repo, int(args.pr_number), args.base_sha, args.head_sha)
        merge_base = validate_git(args.a0_path, args.base_path, args.head_path,
                                  args.base_sha, args.head_sha)
        result = {"status": "PROVENANCE_PASS", "a0": A0_SHA,
                  "base": args.base_sha, "head": args.head_sha,
                  "merge_base": merge_base, "pr_number": int(args.pr_number)}
        code = 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        result = {"status": "FAIL_CLOSED", "error": str(exc)}
        code = 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return code


if __name__ == "__main__":
    sys.exit(main())
