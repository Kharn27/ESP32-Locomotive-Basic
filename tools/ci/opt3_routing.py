#!/usr/bin/env python3
"""CI-OPT3: fail-closed five-family GitHub Actions route audit (stdlib only).

A triggering workflow is not necessarily a completed job: historical CPC
acquisition jobs still enforce their branch/HEAD and ROM/GHCR guards.
"""
import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
FAMILIES = {
    "C99": ("basic-program.yml", "ci-arch.yml", "ci-opt3-routing.yml"),
    "CPC_PERMANENT": ("ci-cpc-permanent.yml", "cpc-oracle.yml"),
    "CPC_ACQUISITION": (
        "cpc-oracle-image.yml",
        "j1-2-a-boundaries.yml", "j1-3-a-subtraction.yml",
        "j1-4-a-multiplication.yml", "j1-5-a-division.yml",
        "j1-6-a-mod.yml", "j1-7-a-add-vars.yml",
        "j1-8-a-sub-vars.yml", "j1-9-a-binary-family.yml",
        "j1-10-a-if-then.yml", "j1-11-a-gosub-return.yml",
        "j1-12-a-for-next-integer.yml", "j1-12-b1-cpc-reacquire.yml",
        "j1-13-a-integer-relations.yml", "j1-14-a-if-inline-else.yml",
        "j1-15-a-string-scalar.yml", "j1-16-a-real5-scalar.yml",
        "j1-16-d-a-negative-store.yml", "j1-16-e-a-small-store.yml"),
    "HW4": ("hw4-c3-b1-scroll.yml", "hw4-c3-b2-scroll.yml",
            "hw4-diag-a.yml", "hw4-edit-p1.yml", "hw4-ready-a.yml"),
    "XTENSA": ("ci-xtensa.yml",),
}
EXPECTED_ROUTES = {
    "j1-6-a-mod.yml": ("tools/j1_6_mod_verify.py", "tests/fixtures/cpc6128/j1_integer_mod/**"),
    "j1-7-a-add-vars.yml": ("tools/j1_7_add_vars_verify.py", "tests/fixtures/cpc6128/j1_integer_add_vars/**"),
    "j1-8-a-sub-vars.yml": ("tools/j1_8_sub_vars_verify.py", "tests/fixtures/cpc6128/j1_integer_sub_vars/**"),
    "j1-9-a-binary-family.yml": ("tools/j1_9_binary_family_verify.py", "tests/fixtures/cpc6128/j1_integer_binary_family/**"),
    "j1-10-a-if-then.yml": ("tools/j1_10_if_then_verify.py", "tests/fixtures/cpc6128/j1_10_if_then/**"),
    "j1-11-a-gosub-return.yml": ("tools/j1_11_gosub_return_verify.py", "tests/fixtures/cpc6128/j1_11_gosub_return/**"),
    "j1-12-a-for-next-integer.yml": ("tools/j1_12_for_next_verify.py", "tests/fixtures/cpc6128/j1_12_for_next/**"),
    "j1-12-b1-cpc-reacquire.yml": ("tools/j1_12_for_next_verify.py", "tests/fixtures/cpc6128/j1_12_for_next/**"),
    "j1-13-a-integer-relations.yml": ("tools/j1_13_relational_if_verify.py", "tests/fixtures/cpc6128/j1_13_integer_relations/**"),
    "j1-14-a-if-inline-else.yml": ("tools/j1_14_if_inline_else_verify.py", "tests/fixtures/cpc6128/j1_14_if_inline_else/**"),
    "j1-15-a-string-scalar.yml": ("tools/j1_15_string_scalar_verify.py", "tests/fixtures/cpc6128/j1_15_string_scalar/**"),
    "j1-16-e-a-small-store.yml": ("tools/j1_16_e_a_store.py", "tests/fixtures/cpc6128/j1_16_e_a_small_store/**"),
}
HISTORICAL = {x for x in FAMILIES["CPC_ACQUISITION"] if x.startswith("j1-")}


class UnsafeRoute(ValueError):
    pass


def demand(yes, code):
    if not yes:
        raise UnsafeRoute(code)


def filters(yaml_text):
    """Parse the exact, simple pull_request.paths structure used in this repo.

    Return None for an unfiltered PR trigger. Fail closed on negated filters.
    """
    m = re.search(r"(?m)^  pull_request:.*$", yaml_text)
    demand(m is not None, "PULL_REQUEST_MISSING")
    enabled, paths = False, []
    for line in yaml_text[m.end():].splitlines():
        if line and not line.startswith(" "):
            break
        if re.match(r"^  \w[\w-]*:", line):
            break
        if re.match(r"^    paths:\s*$", line):
            enabled = True
            continue
        if enabled and re.match(r"^    \S", line):
            break
        if enabled:
            v = re.match(r"^      -\s+(.*?)\s*$", line)
            if v:
                pat = v.group(1).strip("'\"")
                demand(pat and not pat.startswith("!"),
                       "UNSUPPORTED_NEGATED_FILTER")
                paths.append(pat)
    return paths if enabled else None


def triggered(paths, src):
    fs = filters(src)
    return fs is None or any(fnmatch.fnmatchcase(p, f) for p in paths for f in fs)


def triggered_names(paths, sources):
    return {n for n, s in sources.items() if triggered(paths, s)}


def family_routes(paths, sources):
    found = triggered_names(paths, sources)
    return {family for family, names in FAMILIES.items()
            if found.intersection(names)}


def audit(sources):
    expected = [name for names in FAMILIES.values() for name in names]
    demand(len(expected) == 30 and len(set(expected)) == 30,
           "DUPLICATE_OR_MISSING_FAMILY")
    demand(set(sources) == set(expected), "UNKNOWN_OR_MISSING_WORKFLOW")
    for name, src in sources.items():
        demand(re.search(r"(?m)^  workflow_dispatch:", src),
               "MANUAL_DISPATCH_REMOVED_" + name)
        fs = filters(src)
        if name in HISTORICAL:
            demand(fs is not None and len(fs) > 0,
                   "HISTORICAL_PR_UNFILTERED_" + name)
            demand(".github/workflows/" + name in fs,
                   "HISTORICAL_SELF_CHANGE_UNROUTED_" + name)
            demand("docs/ROADMAP_GATES.md" not in fs,
                   "ROADMAP_ONLY_WAKES_CPC_" + name)
        if name in EXPECTED_ROUTES:
            for required in EXPECTED_ROUTES[name]:
                demand(required in fs, "CAPTURE_ROUTE_MISSING_" + name)
            pre = src.split("\njobs:", 1)[0]
            demand("github.sha" not in pre,
                   "ACQUISITION_CONCURRENCY_SHA_" + name)
            demand("cancel-in-progress: false" in pre,
                   "ARCHIVE_PUBLISHING_CANCELLED_" + name)
    for name in ("basic-program.yml", "ci-arch.yml",
                 "ci-cpc-permanent.yml", "ci-opt3-routing.yml"):
        demand(filters(sources[name]) is None,
               "STABLE_REQUIRED_GATE_FILTERED_" + name)
        demand(re.search(r"(?m)^  push:", sources[name]),
               "MAIN_PUSH_LOST_" + name)
    xtensa = filters(sources["ci-xtensa.yml"])
    demand(xtensa is not None and "core/**" in xtensa and
           "firmware/**" in xtensa and "tools/ci/**" in xtensa,
           "XTENSA_TARGET_INPUT_LOST")
    permanent = sources["ci-cpc-permanent.yml"]
    demand("tools/j1_16_e_a_store.py --evidence" in permanent and
           "tools/j1_16_d_a_store.py --evidence" in permanent and
           "--permanent --self-test" in permanent,
           "SEALED_STORES_PERMANENT_LOST")
    ea = (ROOT / "tools/j1_16_e_a_store.py").read_text()
    da = (ROOT / "tools/j1_16_d_a_store.py").read_text()
    demand("SEALED_E_A_ARCHIVE_MISMATCH" in ea and
           "UNVERIFIED_SCALAR_RETAINED" in ea and
           "SEALED_D_A_ARCHIVE_MISMATCH" in da,
           "E_A_C1_OR_D_A_SEAL_LOST")


def negative_tests(sources):
    essential = {"C99", "CPC_PERMANENT"}
    scenarios = {
        "DOC_ONLY": (["docs/ROADMAP_GATES.md"], essential,
                     {"CPC_ACQUISITION", "HW4", "XTENSA"}),
        "CORE": (["core/basic_executor.c"], essential | {"XTENSA"}, set()),
        "HW4": (["video/cpc_video.c"], essential | {"XTENSA", "HW4"}, set()),
        "FIRMWARE": (["firmware/esp32_display_probe/main/hw4_c2_console.c"],
                     essential | {"XTENSA"}, set()),
        "ORACLE_TOOL": (["tools/j1_16_e_a_store.py"],
                        essential | {"CPC_ACQUISITION"}, {"XTENSA"}),
        "ARCHIVE_TAMPER": ([
            "tests/fixtures/cpc6128/j1_16_e_a_small_store/original/R_ONE/window.bin"],
            essential | {"CPC_ACQUISITION"}, {"XTENSA"}),
        "SCRIPT_PLUS_ARCHIVE": ([
            "tools/j1_16_e_a_store.py",
            "tests/fixtures/cpc6128/j1_16_e_a_small_store/repeat/R_NEG_ONE/window.bin"],
            essential | {"CPC_ACQUISITION"}, {"XTENSA"}),
        "BUILD": (["CMakeLists.txt"], essential | {"XTENSA", "HW4"}, set()),
        "TARGET_CI": (["tools/ci/opt3_routing.py"],
                      essential | {"XTENSA"}, set()),
    }
    for label, (paths, require, forbid) in scenarios.items():
        got = family_routes(paths, sources)
        demand(require.issubset(got) and not got.intersection(forbid),
               "NEGATIVE_ROUTING_" + label)
        print("CI-OPT3 ROUTING_CASE_PASS", label, ",".join(sorted(got)))
    demand("j1-16-e-a-small-store.yml" in triggered_names(
           ["tools/j1_16_e_a_store.py"], sources), "EA_ORACLE_NOT_ROUTED")
    demand("j1-16-d-a-negative-store.yml" in triggered_names(
           ["tools/j1_16_d_a_store.py"], sources), "DA_ORACLE_NOT_ROUTED")
    demand(not HISTORICAL.intersection(triggered_names(
           ["tools/j1_99_unknown_oracle.py"], sources)),
           "UNREGISTERED_ORACLE_FALSELY_ACQUIRED")
    print("CI-OPT3 UNREGISTERED_ORACLE_NOT_PROMOTED")


def check_diff(base, sources):
    paths = subprocess.check_output(
        ["git", "-C", str(ROOT), "diff", "--name-only", base + "...HEAD"],
        text=True).splitlines()
    demand(bool(paths), "PR_DIFF_EMPTY")
    for path in paths:
        if re.fullmatch(r"(?:tools|tests/oracles)/j1_[\w]+_oracle\.py", path):
            demand(bool(HISTORICAL.intersection(triggered_names([path], sources))),
                   "UNREGISTERED_NEW_ORACLE_" + path)
    print("CI-OPT3 PR_DIFF_PATHS", len(paths),
          "FAMILIES", ",".join(sorted(family_routes(paths, sources))))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--base-sha")
    p.add_argument("--expect-head")
    a = p.parse_args()
    if a.expect_head:
        demand(re.fullmatch(r"[0-9a-f]{40}", a.expect_head),
               "EXPECTED_HEAD_MALFORMED")
        actual = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True).strip()
        demand(actual == a.expect_head,
               "OPT3_HEAD_MISMATCH expected=" + a.expect_head +
               " actual=" + actual)
    sources = {p.name: p.read_text() for p in WORKFLOWS.glob("*.yml")}
    audit(sources)
    if a.self_test:
        negative_tests(sources)
    if a.base_sha:
        demand(re.fullmatch(r"[0-9a-f]{40}", a.base_sha), "BAD_BASE_SHA")
        check_diff(a.base_sha, sources)
    print("CI-OPT3 ROUTE_GATE_PASS WORKFLOWS=30 FAMILIES=5")


if __name__ == "__main__":
    try:
        main()
    except (UnsafeRoute, OSError, subprocess.CalledProcessError) as e:
        print("CI-OPT3 FAIL", e, file=sys.stderr)
        sys.exit(1)
