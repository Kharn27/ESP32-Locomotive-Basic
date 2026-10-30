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
        "j1-16-d-a-negative-store.yml", "j1-16-e-a-small-store.yml",
        "j1-17-c-a-pen-cpc.yml"),
    "HW4": ("hw4-c3-b1-scroll.yml", "hw4-c3-b2-scroll.yml",
            "hw4-diag-a.yml", "hw4-edit-p1.yml", "hw4-ready-a.yml",
            "hw4-scroll-opt-a0-memory.yml"),
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
    "j1-17-c-a-pen-cpc.yml": ("tools/j1_17_c_a_pen_oracle.py", "tests/fixtures/cpc6128/j1_17_c_a_pen/**"),
}
HISTORICAL = {x for x in FAMILIES["CPC_ACQUISITION"] if x.startswith("j1-")}
# J1.19-A C1: a specifically audited existing-workflow job, never a wildcard.
PAPER_TOOL = "tools/j1_19_a_paper_oracle.py"
PAPER_WORKFLOW = "ci-cpc-permanent.yml"
PAPER_BRANCH = "oracle/j1-19-a-paper-cpc"
PAPER_JOB = "paper-cpc-acquisition"
PAPER_IMAGE = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
               "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")
PAPER_ROM = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
PAPER_CAPRICE = "8c778bf072a06fb7c23b9cccd179041db7f79a52"

# Explicit HW4-SCROLL-OPT-A0 trigger contract from PR #168, not a generic
# "tools/**" or "docs/**" wildcard that would wake unrelated jobs.
HW4_A0 = "hw4-scroll-opt-a0-memory.yml"
HW4_A0_PATHS = (
    "video/hw4_scroll_metrics.*",
    "firmware/esp32_display_probe/main/hw4_c2_console.c",
    "firmware/esp32_display_probe/main/CMakeLists.txt",
    "tools/ci/hw4_a0_compare_memory.py",
    "tools/hw4_scroll_a0_uart.py",
    "tests/test_hw4_scroll_metrics_parser.py",
    "docs/HW4-SCROLL-OPT-A0-baseline.md",
    ".github/workflows/hw4-scroll-opt-a0-memory.yml",
)


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


def globmatch(path, pattern):
    # GitHub's '**/' matches zero or more complete directories. Python
    # fnmatchcase alone incorrectly misses the repository-root CMakeLists.
    return (fnmatch.fnmatchcase(path, pattern) or
            (pattern.startswith("**/") and
             fnmatch.fnmatchcase(path, pattern[3:])))


def triggered(paths, src):
    fs = filters(src)
    return fs is None or any(globmatch(p, f) for p in paths for f in fs)


def triggered_names(paths, sources):
    return {n for n, s in sources.items() if triggered(paths, s)}


def family_routes(paths, sources):
    found = triggered_names(paths, sources)
    return {family for family, names in FAMILIES.items()
            if found.intersection(names)}


def audit(sources):
    expected = [name for names in FAMILIES.values() for name in names]
    demand(len(expected) == 32 and len(set(expected)) == 32,
           "DUPLICATE_OR_MISSING_FAMILY")
    demand(set(sources) == set(expected), "UNKNOWN_OR_MISSING_WORKFLOW")
    a0_paths = filters(sources[HW4_A0])
    demand(a0_paths is not None and
           len(a0_paths) == len(HW4_A0_PATHS) and
           set(a0_paths) == set(HW4_A0_PATHS),
           "HW4_A0_FILTER_CONTRACT_MISMATCH")
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
    audit_paper_route(sources)
    ea = (ROOT / "tools/j1_16_e_a_store.py").read_text()
    da = (ROOT / "tools/j1_16_d_a_store.py").read_text()
    demand("SEALED_E_A_ARCHIVE_MISMATCH" in ea and
           "UNVERIFIED_SCALAR_RETAINED" in ea and
           "SEALED_D_A_ARCHIVE_MISMATCH" in da,
           "E_A_C1_OR_D_A_SEAL_LOST")


def audit_paper_route(sources):
    """Check the real job, exact branch, GHCR/ROM/HEAD and publishing safeguards."""
    yml = sources[PAPER_WORKFLOW]
    marker = "\n  " + PAPER_JOB + ":"
    demand(yml.count(marker) == 1, "PAPER_JOB_MISSING")
    header, job = yml.split(marker, 1)
    demand("github.head_ref != '" + PAPER_BRANCH + "'" in header and
           "cancel-in-progress: " in header, "PAPER_ARCHIVE_CANCEL_RISK")
    guard = ("if: (github.event_name == 'pull_request' && "
             "github.head_ref == 'oracle/j1-19-a-paper-cpc' && "
             "github.event.pull_request.head.repo.full_name == github.repository) || "
             "(github.event_name == 'workflow_dispatch' && "
             "github.ref_name == 'oracle/j1-19-a-paper-cpc')")
    demand(guard in job, "PAPER_BRANCH_AND_FORK_GUARD")
    demand("    permissions:\n      contents: write\n      packages: read" in job,
           "PAPER_PERMISSIONS")
    demand("      image: " + PAPER_IMAGE in job, "PAPER_GHCR")
    demand('test "$(git -C tests/oracles/caprice32 rev-parse HEAD)" = ' + PAPER_CAPRICE in job and
           'test "$(cat /usr/local/share/loco-caprice32-source.sha)" = ' + PAPER_CAPRICE in job,
           "PAPER_CAPRICE_PIN")
    demand('test "$(sha256sum tests/oracles/caprice32/rom/cpc6128.rom | cut -d ' +
           "' ' -f 1)\" = " + PAPER_ROM in job, "PAPER_ROM_PIN")
    demand('test "$(git rev-parse HEAD)" = "$GITHUB_HEAD_SHA"' in job and
           "github.event.pull_request.head.sha || github.sha" in job and
           "submodules: recursive" in job and
           "test -x /usr/local/bin/cap32" in job and
           "cp /usr/local/bin/cap32 tests/oracles/caprice32/cap32" in job,
           "PAPER_HEAD_OR_BIN")
    demand("git diff origin/main...HEAD --name-only" in job and
           "J1.19-A FORBIDDEN_DIFF_PATH" in job and
           "tests/fixtures/cpc6128/j1_18_" in job,
           "PAPER_SCOPE_GUARD")
    demand("python3 " + PAPER_TOOL + " --acquire tests/oracles/caprice32" in job and
           '--head "$GITHUB_HEAD_SHA"' in job and
           "python3 " + PAPER_TOOL + ' --evidence "$RUNNER_TEMP/j119-paper"' in job,
           "PAPER_TOOL_JOB_LINK")
    demand("git ls-remote --exit-code origin refs/heads/" + PAPER_BRANCH in job and
           'test "$REMOTE_HEAD" = "$GITHUB_HEAD_SHA"' in job and
           "git push origin HEAD:refs/heads/" + PAPER_BRANCH in job and
           "ARCHIVE_PENDING_EXTERNAL_SEAL" in job and
           "--permanent --self-test" in job and
           "EXTERNALLY_SEALED_PASS" in job,
           "PAPER_ARCHIVE_SEAL_GUARD")
    demand("actions/upload-artifact@v4" in job and
           "j119-paper-origin-sha256.txt" in job and
           "j119-paper-origin.txt" in job,
           "PAPER_ORIGINAL_ARTIFACT")
    return True


def paper_negative_tests(sources):
    """Mutate the in-memory workflow only; every weakened contract must fail."""
    original = sources[PAPER_WORKFLOW]
    cases = {
        "MISSING_JOB": (original.split("\n  " + PAPER_JOB + ":", 1)[0],
                        "PAPER_JOB_MISSING"),
        "WIDE_BRANCH": (original.replace(
            "github.head_ref == '" + PAPER_BRANCH + "'",
            "github.head_ref != 'other'"), "PAPER_BRANCH_AND_FORK_GUARD"),
        "FORK_ALLOWED": (original.replace(
            "github.event.pull_request.head.repo.full_name == github.repository",
            "github.event.pull_request.head.repo.full_name != github.repository"),
            "PAPER_BRANCH_AND_FORK_GUARD"),
        "FAKE_HEAD": (original.replace(
            'test "$(git rev-parse HEAD)" = "$GITHUB_HEAD_SHA"',
            'test "$(git rev-parse HEAD)" != "$GITHUB_HEAD_SHA"'), "PAPER_HEAD_OR_BIN"),
        "IMAGE_UNPINNED": (original.replace(PAPER_IMAGE, "ubuntu:latest"),
                            "PAPER_GHCR"),
        "ROM_UNPINNED": (original.replace(PAPER_ROM, "0"*64),
                          "PAPER_ROM_PIN"),
        "CAPRICE_UNPINNED": (original.replace(PAPER_CAPRICE, "0"*40),
                              "PAPER_CAPRICE_PIN"),
        "LINK_MISSING": (original.replace(PAPER_TOOL + " --acquire",
                                           "tools/unknown.py --acquire"),
                         "PAPER_TOOL_JOB_LINK"),
        "WEAK_PERMISSIONS": (original.replace("      contents: write",
                                                "      contents: read"),
                              "PAPER_PERMISSIONS"),
        "NO_REMOTE_LEASE": (original.replace(
            'test "$REMOTE_HEAD" = "$GITHUB_HEAD_SHA"',
            'test "$REMOTE_HEAD" != "$GITHUB_HEAD_SHA"'),
                             "PAPER_ARCHIVE_SEAL_GUARD"),
        "CANCEL_ARCHIVE": (original.replace(
            "github.head_ref != '" + PAPER_BRANCH + "'",
            "github.head_ref == '" + PAPER_BRANCH + "'"),
                           "PAPER_ARCHIVE_CANCEL_RISK"),
        "NO_SHA_ARTIFACT": (original.replace(
            "j119-paper-origin-sha256.txt", "not-original.txt"),
                            "PAPER_ORIGINAL_ARTIFACT"),
    }
    for label, (bad, reason) in cases.items():
        demand(bad != original, "PAPER_NEGATIVE_INERT_" + label)
        try:
            audit_paper_route({**sources, PAPER_WORKFLOW: bad})
        except UnsafeRoute as exc:
            demand(str(exc) == reason,
                   "PAPER_NEGATIVE_WRONG_REASON_" + label + ":" + str(exc))
        else:
            raise UnsafeRoute("PAPER_NEGATIVE_ACCEPTED_" + label)
        print("CI-OPT3 PAPER_FALSIFICATION_REJECTED", label, reason)


def negative_tests(sources):
    paper_negative_tests(sources)
    essential = {"C99", "CPC_PERMANENT"}
    scenarios = {
        "DOC_ONLY": (["docs/ROADMAP_GATES.md"], essential,
                     {"CPC_ACQUISITION", "HW4", "XTENSA"}),
        "CORE": (["core/basic_executor.c"], essential | {"XTENSA"}, set()),
        "HW4": (["video/cpc_video.c"], essential | {"XTENSA", "HW4"}, set()),
        "FIRMWARE": (["firmware/esp32_display_probe/main/hw4_c2_console.c"],
                     essential | {"XTENSA", "HW4"}, {"CPC_ACQUISITION"}),
        "HW4_A0_METRICS": (["video/hw4_scroll_metrics.c"],
                          essential | {"XTENSA", "HW4"}, {"CPC_ACQUISITION"}),
        "HW4_A0_MEMORY_TOOL": (["tools/ci/hw4_a0_compare_memory.py"],
                              essential | {"XTENSA", "HW4"}, {"CPC_ACQUISITION"}),
        "HW4_A0_UART_TOOL": (["tools/hw4_scroll_a0_uart.py"],
                            essential | {"HW4"}, {"CPC_ACQUISITION", "XTENSA"}),
        "HW4_A0_PARSER_TEST": (["tests/test_hw4_scroll_metrics_parser.py"],
                              essential | {"HW4"}, {"CPC_ACQUISITION", "XTENSA"}),
        "HW4_A0_BASELINE_DOC": (["docs/HW4-SCROLL-OPT-A0-baseline.md"],
                               essential | {"HW4"}, {"CPC_ACQUISITION", "XTENSA"}),
        "HW4_A0_SELF_EDIT": ([".github/workflows/hw4-scroll-opt-a0-memory.yml"],
                            essential | {"HW4"}, {"CPC_ACQUISITION", "XTENSA"}),
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
    # Mutate only in-memory copies: prove inventory and the exact A0 filters
    # are fail-closed without touching historical oracle files or YAML.
    missing_filter = sources[HW4_A0].replace(
        "      - 'tools/ci/hw4_a0_compare_memory.py'\n", "")
    demand(missing_filter != sources[HW4_A0], "A0_FILTER_NEGATIVE_INERT")
    altered = {
        "UNKNOWN_WORKFLOW": ({**sources, "unknown-extra.yml": sources[HW4_A0]},
                             "UNKNOWN_OR_MISSING_WORKFLOW"),
        "REMOVED_A0": ({k: v for k, v in sources.items() if k != HW4_A0},
                       "UNKNOWN_OR_MISSING_WORKFLOW"),
        "RENAMED_A0": ({**{k: v for k, v in sources.items() if k != HW4_A0},
                        "renamed-a0.yml": sources[HW4_A0]},
                       "UNKNOWN_OR_MISSING_WORKFLOW"),
        "A0_FILTER_REMOVED": ({**sources, HW4_A0: missing_filter},
                              "HW4_A0_FILTER_CONTRACT_MISMATCH"),
    }
    for label, (broken, code) in altered.items():
        try:
            audit(broken)
        except UnsafeRoute as exc:
            demand(str(exc) == code, "INVENTORY_NEGATIVE_WRONG_REASON_" + label)
        else:
            raise UnsafeRoute("INVENTORY_NEGATIVE_ACCEPTED_" + label)
        print("CI-OPT3 INVENTORY_FALSIFICATION_REJECTED", label, code)


def check_diff(base, sources):
    paths = subprocess.check_output(
        ["git", "-C", str(ROOT), "diff", "--name-only", base + "...HEAD"],
        text=True).splitlines()
    demand(bool(paths), "PR_DIFF_EMPTY")
    for path in paths:
        if re.fullmatch(r"(?:tools|tests/oracles)/j1_[\w]+_oracle\.py", path):
            if path == PAPER_TOOL:
                audit_paper_route(sources)
                demand(PAPER_WORKFLOW in triggered_names([path], sources),
                       "PAPER_WORKFLOW_UNROUTED")
            else:
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
    print("CI-OPT3 ROUTE_GATE_PASS WORKFLOWS=32 FAMILIES=5")


if __name__ == "__main__":
    try:
        main()
    except (UnsafeRoute, OSError, subprocess.CalledProcessError) as e:
        print("CI-OPT3 FAIL", e, file=sys.stderr)
        sys.exit(1)
