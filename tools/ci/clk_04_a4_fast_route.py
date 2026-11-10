#!/usr/bin/env python3
"""CI-A4-FAST: classify A4 PR inputs using Git objects, not PR path heuristics.

No cached CPC evidence is consumed or re-labelled here. A FAST job proves host
checks only. FULL retains the historical HEAD-bound RAW + independent seal.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

# Existing CPC acquisition/replay inputs. The C99 candidate is deliberately not
# an acquisition input: editing it triggers host tests, not new CPC observations.
INPUTS = (
    "tests/fixtures/cpc6128/clk_04_a4_numeric",  # entire sealed source set
    "tools/clk_04_a4_oracle.py",                   # generator, capture and replay
    "tools/clk_03_cpc_time.py",                    # CPC and speed-gate helper
    "tools/clk_04_real5_oracle.py",                # REAL5 RAM helper
    "tests/oracles/caprice32",                    # gitlink pins ROM and emulator
)
WORKFLOW = ".github/workflows/clk-04-a4-numeric-pipeline.yml"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class RouteError(ValueError):
    pass


def demand(condition, code):
    if not condition:
        raise RouteError(code)


def git(root, *args):
    proc = subprocess.run(["git", "-C", str(root), *args],
                          check=False, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    demand(proc.returncode == 0, "GIT_OBJECT_UNAVAILABLE")
    return proc.stdout


def job(text, name):
    marker = "  " + name + ":\n"
    demand(text.count("\n" + marker) == 1, "WORKFLOW_JOB_MISSING_" + name)
    tail = text.split("\n" + marker, 1)[1]
    end = re.search(r"(?m)^  [a-zA-Z][\w-]*:\s*$", tail)
    return tail[:end.start()] if end else tail


def check_wiring(text):
    """No change to the routing guard may silently disable mandatory full."""
    router = job(text, "route")
    host = job(text, "host-negatives-and-c99")
    cpc = job(text, "cpc-acquire")
    replay = job(text, "sealed-replay")
    demand(re.search(r"(?m)^    (?:if|needs):", router) is None and
           "python3 tools/ci/clk_04_a4_fast_route.py" in router,
           "ROUTE_JOB_CONDITIONAL_OR_MISSING")
    demand(re.search(r"(?m)^    (?:if|needs):", host) is None,
           "HOST_JOB_CONDITIONAL")
    demand(re.search(r"(?m)^    needs: \[host-negatives-and-c99, route\]$", cpc)
           is not None, "CPC_GATE_DEPENDENCIES_CHANGED")
    demand(re.search(r"(?m)^    if: needs\.route\.outputs\.mode == 'full'$", cpc)
           is not None, "CPC_GATE_CONDITION_CHANGED")
    demand(re.search(r"(?m)^    needs: cpc-acquire$", replay) is not None,
           "REPLAY_DEPENDENCY_CHANGED")
    demand(re.search(r"(?m)^    if:", replay) is None,
           "REPLAY_GUARD_CHANGED")
    demand("  workflow_dispatch:" in text and
           "python3 tools/clk_04_a4_oracle.py --acquire" in cpc and
           "python3 tools/clk_04_a4_oracle.py --verify" in replay and
           '--seal "$EXTERNAL_SHA"' in replay,
           "COMPLETE_CPC_CHAIN_MISSING")


def acquisition_jobs(text):
    """Normalize *only* top-level routing properties; never acquisition body."""
    outputs = []
    for name in ("cpc-acquire", "sealed-replay"):
        section = job(text, name)
        # A guard can vary without changing the actual measurement program.
        # The HEAD guard is independently checked by check_wiring above.
        filtered = [line for line in section.splitlines()
                    if not re.match(r"^    (?:needs|if):", line)]
        outputs.append("\n".join(filtered).rstrip())
    return outputs


def tree_objects(root, rev, prefix):
    """Return Git modes and object IDs; detect removed paths and gitlink changes."""
    raw = git(root, "ls-tree", "-r", "-z", rev, "--", prefix)
    # Git does not recurse into a gitlink; request its directory entry.
    if not raw and prefix == "tests/oracles/caprice32":
        raw = git(root, "ls-tree", "-z", rev, "--", prefix)
    out = {}
    for entry in filter(None, raw.split(b"\x00")):
        meta, path = entry.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        key = path.decode("utf-8")
        demand(mode in ("100644", "100755", "160000") and
               kind in ("blob", "commit"), "INPUT_GIT_TYPE_INVALID")
        out[key] = (mode, kind, oid)
    demand(bool(out), "INPUT_MISSING_" + prefix)
    return out


def fingerprint(root, rev):
    entries = {}
    for prefix in INPUTS:
        for path, data in tree_objects(root, rev, prefix).items():
            demand(path not in entries, "DUPLICATE_INPUT_PATH")
            entries[path] = data
    wf = git(root, "show", rev + ":" + WORKFLOW).decode("utf-8")
    payload = {"schema": 1, "git_inputs": entries,
               "acquisition_replay_job_bodies": acquisition_jobs(wf)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def decision(root, event, head, base=""):
    demand(SHA40.fullmatch(head) is not None, "HEAD_SHA_INVALID")
    actual = git(root, "rev-parse", "HEAD").decode().strip()
    demand(actual == head, "HEAD_MISMATCH")
    head_workflow = git(root, "show", head + ":" + WORKFLOW).decode("utf-8")
    check_wiring(head_workflow)
    head_fingerprint = fingerprint(root, head)
    if event == "workflow_dispatch":
        return "full", head_fingerprint, "HEAD_EXACT_MANUAL_FULL"
    demand(event == "pull_request", "EVENT_NOT_ALLOWED")
    demand(SHA40.fullmatch(base) is not None, "BASE_SHA_INVALID")
    common = git(root, "merge-base", base, head).decode().strip()
    demand(SHA40.fullmatch(common) is not None, "MERGE_BASE_INVALID")
    old_fingerprint = fingerprint(root, common)
    if head_fingerprint != old_fingerprint:
        return "full", head_fingerprint, "HEAD_EXACT_INPUT_CHANGED"
    return "fast", head_fingerprint, "FAST_HOST_ONLY_NO_CPC_EVIDENCE_REUSE"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, choices=["pull_request", "workflow_dispatch"])
    parser.add_argument("--head", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    mode, input_sha, provenance = decision(Path.cwd(), args.event, args.head, args.base)
    with args.output.open("a", encoding="ascii") as out:
        for k, value in (("mode", mode), ("inputs_sha256", input_sha),
                         ("provenance", provenance)):
            out.write(k + "=" + value + "\n")
    print("CI_A4_FAST_ROUTE=" + mode.upper(), "ORACLE_INPUT_SHA256=" + input_sha,
          "EVIDENCE_PROVENANCE=" + provenance)
    if mode == "fast":
        print("CI_A4_FAST_NO_CPC_RUN_NO_CPC_PROOF_FOR_THIS_HEAD; "
              "cpc-acquire and sealed-replay will be SKIPPED, not SUCCESS")


if __name__ == "__main__":
    try:
        main()
    except RouteError as exc:
        raise SystemExit("CI_A4_FAST_FAIL_CLOSED:" + str(exc)) from exc
