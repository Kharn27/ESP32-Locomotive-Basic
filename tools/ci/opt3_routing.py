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
        "cpc-oracle-image.yml", "hw4-esc-oracle-r1.yml",
        "j1-2-a-boundaries.yml", "j1-3-a-subtraction.yml",
        "j1-4-a-multiplication.yml", "j1-5-a-division.yml",
        "j1-6-a-mod.yml", "j1-7-a-add-vars.yml",
        "j1-8-a-sub-vars.yml", "j1-9-a-binary-family.yml",
        "j1-10-a-if-then.yml", "j1-11-a-gosub-return.yml",
        "j1-12-a-for-next-integer.yml", "j1-12-b1-cpc-reacquire.yml",
        "j1-13-a-integer-relations.yml", "j1-14-a-if-inline-else.yml",
        "j1-15-a-string-scalar.yml", "j1-16-a-real5-scalar.yml",
        "j1-16-d-a-negative-store.yml", "j1-16-e-a-small-store.yml",
        "j1-17-c-a-pen-cpc.yml", "clk-01-acquisition.yml",
        "clk-03-acquisition.yml", "clk-04-real5-oracle.yml",
        "clk-04-a2-numeric-oracle.yml"),
    "HW4": ("hw4-c3-b1-scroll.yml", "hw4-c3-b2-scroll.yml",
            "hw4-diag-a.yml", "hw4-edit-p1.yml", "hw4-ready-a.yml",
            "hw4-scroll-opt-a0-memory.yml",
            "hw4-disp-profile-c3.yml", "hw4-disp-render-a.yml",
            "hw4-mem-c5-v2.yml", "hw4-mem-c6-b2-a-live.yml",
            "hw4-mem-c6-b2-b-xtensa.yml", "hw4-mem-c6-b2-d1-prelink.yml"),
    "XTENSA": ("ci-xtensa.yml",),
}
EXPECTED_ROUTES = {
    "hw4-esc-oracle-r1.yml": ("tests/oracles/hw4_esc_r1_capture.py",
        "tests/oracles/hw4_esc_r1_verify.py",
        "tests/fixtures/cpc6128/hw4_esc_r1/**",
        "docs/HW4-ESC-ORACLE-R1.md",
        ".github/workflows/hw4-esc-oracle-r1.yml"),
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
CLS_TOOL = "tools/j1_21_a_cls_oracle.py"
CLS_JOB = "cls-cpc-acquisition"
CLS_BRANCH = "oracle/j1-21-a-cls-cpc"
CLS_ARCHIVE = "tests/fixtures/cpc6128/j1_21_a_cls"
CLS_PERMANENT_STEP = """      - name: J1.21-A CLS 252 external SHA seals (permanent, no Caprice32)
        shell: bash
        run: |
          set -euo pipefail
          python3 tools/j1_21_a_cls_oracle.py --check-sources
          python3 tools/j1_21_a_cls_oracle.py \\
            --evidence tests/fixtures/cpc6128/j1_21_a_cls \\
            --permanent --self-test"""
PAPER_IMAGE = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
               "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")
PAPER_ROM = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
PAPER_CAPRICE = "8c778bf072a06fb7c23b9cccd179041db7f79a52"

# J1.22-A-C1: only this exact oracle may use the protected permanent CPC job.
J122_TOOL = "tools/j1_22_a_integer_logical_oracle.py"
J122_ZIP = "tests/fixtures/cpc6128/j1_22_a_integer_logical/original-run-41464839712.zip"
J122_ZIP_SHA256 = "60977e10abae836f6c59adc3f54b51829abc8a5e65e802efb289fcd0f053df3b"
J122_MANIFEST_SHA256 = "f77f770972ddf8f3710b43a36e43fd554a11edd9c98b099ac26497a514f49b92"
J122_ROM_SHA256 = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
J122_HEAD = "787af8a9159d573c3f6444248666001e3b159ce8"
J122_PERMANENT_STEP = """      - name: J1.22-A 48 authentic CPC sessions external SHA seals (permanent, no acquisition)
        shell: bash
        run: |
          set -euo pipefail
          python3 tools/j1_22_a_integer_logical_oracle.py --check-sources
          echo '60977e10abae836f6c59adc3f54b51829abc8a5e65e802efb289fcd0f053df3b  tests/fixtures/cpc6128/j1_22_a_integer_logical/original-run-41464839712.zip' | sha256sum --check --status
          mkdir -p "$RUNNER_TEMP/j122-permanent"
          unzip -q tests/fixtures/cpc6128/j1_22_a_integer_logical/original-run-41464839712.zip -d "$RUNNER_TEMP/j122-permanent"
          echo "f77f770972ddf8f3710b43a36e43fd554a11edd9c98b099ac26497a514f49b92  $RUNNER_TEMP/j122-permanent/archive/manifest.json" | sha256sum --check --status
          python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); assert m["acquisition_head"]=="787af8a9159d573c3f6444248666001e3b159ce8"; assert m["oracle"]["rom_sha256"]=="31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"' "$RUNNER_TEMP/j122-permanent/archive/manifest.json"
          python3 tools/j1_22_a_integer_logical_oracle.py --verify "$RUNNER_TEMP/j122-permanent/archive" --self-test"""

R1_WORKFLOW = "hw4-esc-oracle-r1.yml"
R1_MANIFEST = "tests/fixtures/cpc6128/hw4_esc_r1/manifest.json"
R1_VERIFIER = "tests/oracles/hw4_esc_r1_verify.py"
# Independent seal; not derived from mutable archive JSON.
R1_SEAL = "5eff0daedd5d41d37f05848c02913de3bf8aa4b47009a43a6986095d54b3e850"
R1_SEAL_COMMAND = ("echo '" + R1_SEAL + "  " + R1_MANIFEST +
                   "' | sha256sum --check --status")
R1_VERIFY_COMMAND = ("python3 " + R1_VERIFIER +
    " --evidence tests/fixtures/cpc6128/hw4_esc_r1"
    " --expected-manifest-sha256 " + R1_SEAL + " --self-test")
R1_SEALED_STEP = """      - name: Permanent R1 29 PNG archive and external manifest seal
        shell: bash
        run: |
          set -euo pipefail
          """ + R1_SEAL_COMMAND + """
          """ + R1_VERIFY_COMMAND + """
          echo 'R1_C1_PERMANENT_ORIGINALS_AND_EXTERNAL_SEAL_PASS'"""
R1_PERMANENT_STEP = """      - name: HW4-ESC-R1-C1 permanently sealed original manifest and 29 CPC PNGs
        shell: bash
        run: |
          set -euo pipefail
          """ + R1_SEAL_COMMAND + """
          """ + R1_VERIFY_COMMAND + """
          echo 'R1_C1_UNFILTERED_PERMANENT_ARCHIVE_PASS'"""



# Exact in-job command contract. Never accept a grep match in an acquisition job.
PAPER_PERMANENT_STEP = """      - name: J1.19-A PAPER 264 external seals (permanent, no Caprice32)
        shell: bash
        run: |
          set -euo pipefail
          python3 tools/j1_19_a_paper_oracle.py --check-sources
          python3 tools/j1_19_a_paper_oracle.py \\
            --evidence tests/fixtures/cpc6128/j1_19_a_paper \\
            --permanent --self-test"""
PAPER_ARCHIVE = "tests/fixtures/cpc6128/j1_19_a_paper"

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
# C3 enters the closed inventory; preserve exact triggering routes and reject
# missing/overbroad edits. A0 historical filters remain immutable.
HW4_C3 = "hw4-disp-profile-c3.yml"
HW4_C3_PATHS = (
    "firmware/components/cyd_ili9341/**",
    "firmware/esp32_display_probe/**",
    "video/hw4_disp_profile.*",
    "tools/ci/hw4_disp_spi_*.py",
    ".github/workflows/hw4-disp-profile-c3.yml",
)


HW4_RENDER_A = "hw4-disp-render-a.yml"
HW4_RENDER_A_PATHS = (
    "video/cpc_video.c",
    "CMakeLists.txt",
    "tests/*hw4_render_a*",
    "tools/ci/hw4_render_a_memory.py",
    "docs/HW4-DISP-RENDER-A.md",
    ".github/workflows/hw4-disp-render-a.yml",
)

# C5-C1: additive HW4 memory prototype; exact five PR paths, fail-closed.
HW4_MEM_C5 = "hw4-mem-c5-v2.yml"
HW4_MEM_C5_PATHS = (
    "tools/ci/hw4_mem_c5_*.py",
    "tools/ci/hw4_mem_c5_build.sh",
    "tests/test_hw4_mem_c5_v2.py",
    "docs/HW4-MEM-C5-v2.md",
    ".github/workflows/hw4-mem-c5-v2.yml",
)

# CLK-01 C1: exact, closed PR routing contract (Issue #308, PR #320).
CLK01_WORKFLOW = "clk-01-acquisition.yml"
CLK01_PATHS = (
    "tools/clk_01_*",
    "tests/test_clk_01_uart.py",
    "tests/fixtures/cpc6128/clk_01_speed/**",
    "docs/CLK-01*",
    ".github/workflows/clk-01-acquisition.yml",
)

# CLK-03-C2: exact five-route contract of the isolated CPC6128 TIME oracle.
# Do not share or widen this trigger with CLK-01 or unrelated source paths.
CLK03_WORKFLOW = "clk-03-acquisition.yml"
CLK03_PATHS = (
    ".github/workflows/clk-03-acquisition.yml",
    "tools/clk_03_*",
    "tests/test_clk_03_time.py",
    "tests/fixtures/cpc6128/clk_03_time/**",
    "docs/CLK-03*",
)

# CLK-04-A2: exactly five isolated triggers, CPC acquisition only.
CLK04_A2_WORKFLOW = "clk-04-a2-numeric-oracle.yml"
CLK04_A2_PATHS = (
    ".github/workflows/clk-04-a2-numeric-oracle.yml",
    "tools/clk_04_a2_*",
    "tests/test_clk_04_a2_numeric.py",
    "tests/fixtures/cpc6128/clk_04_a2_numeric/**",
    "docs/CLK-04-A2*",
)

# CLK-04-A1: exactly five isolated triggers, no production code.
CLK04_WORKFLOW = "clk-04-real5-oracle.yml"
CLK04_PATHS = (
    ".github/workflows/clk-04-real5-oracle.yml",
    "tools/clk_04_real5_*",
    "tests/test_clk_04_real5_oracle.py",
    "tests/fixtures/cpc6128/clk_04_real5/**",
    "docs/CLK-04-A1*",
)


# B2-A: strictly additive non-required read-only GitHub API lab, Issue #348.
C6_B2A_WORKFLOW = "hw4-mem-c6-b2-a-live.yml"
C6_B2A_PATHS = (
    ".github/workflows/hw4-mem-c6-b2-a-live.yml",
    "tools/ci/opt3_routing.py",
    "tools/ci/hw4_mem_c6_refs.py",
    "tests/test_hw4_mem_c6_refs.py",
    "tests/test_hw4_mem_c6_b2_a_live.py",
    "docs/HW4-MEM-C6-B2-A-live.md",
)


# C6-B2-B #351: eight-build #330 proof; additive, non-required.
C6_B2B_WORKFLOW = "hw4-mem-c6-b2-b-xtensa.yml"
C6_B2B_PATHS = (
    ".github/workflows/hw4-mem-c6-b2-b-xtensa.yml",
    "tools/ci/hw4_mem_c6_b2b.py",
    "tests/test_hw4_mem_c6_b2b.py",
    "docs/HW4-MEM-C6-B2-B.md",
    "tools/ci/opt3_routing.py",
)


# D1 #354: nonrequired one-shot 2 B/H SPI40 pre-link evidence.
C6_D1_WORKFLOW = "hw4-mem-c6-b2-d1-prelink.yml"
C6_D1_PATHS = (
    ".github/workflows/hw4-mem-c6-b2-d1-prelink.yml",
    "tools/ci/hw4_mem_c6_b2_d1.py",
    "tests/test_hw4_mem_c6_b2_d1.py",
    "docs/HW4-MEM-C6-B2-D1.md",
    "tools/ci/opt3_routing.py",
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
    demand(len(FAMILIES) == 5 and len(expected) == 43 and
           len(set(expected)) == 43,
           "DUPLICATE_OR_MISSING_FAMILY")
    demand(CLK04_A2_WORKFLOW in FAMILIES["CPC_ACQUISITION"] and
           all(CLK04_A2_WORKFLOW not in ns for family,ns in FAMILIES.items()
               if family != "CPC_ACQUISITION"), "A2_WRONG_FAMILY")
    demand(HW4_MEM_C5 in FAMILIES["HW4"] and
           all(HW4_MEM_C5 not in names for family, names in
               FAMILIES.items() if family != "HW4"),
           "C5_WRONG_FAMILY")
    demand(set(sources) == set(expected), "UNKNOWN_OR_MISSING_WORKFLOW")
    a0_paths = filters(sources[HW4_A0])
    demand(a0_paths is not None and
           len(a0_paths) == len(HW4_A0_PATHS) and
           set(a0_paths) == set(HW4_A0_PATHS),
           "HW4_A0_FILTER_CONTRACT_MISMATCH")
    c3_paths = filters(sources[HW4_C3])
    demand(c3_paths is not None and
           len(c3_paths) == len(HW4_C3_PATHS) and
           set(c3_paths) == set(HW4_C3_PATHS),
           "HW4_C3_FILTER_CONTRACT_MISMATCH")
    render_paths = filters(sources[HW4_RENDER_A])
    demand(render_paths is not None and
           len(render_paths) == len(HW4_RENDER_A_PATHS) and
           set(render_paths) == set(HW4_RENDER_A_PATHS),
           "HW4_RENDER_A_FILTER_CONTRACT_MISMATCH")
    c5_src = sources[HW4_MEM_C5]
    c5_paths = filters(c5_src)
    demand(c5_paths is not None and
           len(c5_paths) == len(HW4_MEM_C5_PATHS) and
           set(c5_paths) == set(HW4_MEM_C5_PATHS),
           "C5_FILTER_CONTRACT_MISMATCH")
    demand(HW4_MEM_C5 in triggered_names(
           [".github/workflows/" + HW4_MEM_C5], sources),
           "C5_SELF_CHANGE_UNROUTED")
    # No new CI source such as push, schedule or workflow_run is authorized.
    c5_events = re.findall(r"(?m)^  ([a-z][\w-]*):",
                           c5_src.split("\npermissions:", 1)[0])
    demand(c5_events == ["pull_request", "workflow_dispatch"],
           "C5_EVENT_CONTRACT_MISMATCH")
    # Exact B2-A family, paths, trusted source, permissions, event and status.
    demand(C6_B2A_WORKFLOW in FAMILIES["HW4"] and
           all(C6_B2A_WORKFLOW not in names for f, names in FAMILIES.items()
               if f != "HW4"), "C6_B2A_WRONG_FAMILY")
    lab = sources[C6_B2A_WORKFLOW]
    lab_paths = filters(lab)
    demand(lab_paths is not None and len(lab_paths) == len(C6_B2A_PATHS)
           and set(lab_paths) == set(C6_B2A_PATHS),
           "C6_B2A_FILTER_CONTRACT_MISMATCH")
    lab_events = re.findall(r"(?m)^  ([a-z][\w-]*):",
                            lab.split("\npermissions:", 1)[0])
    demand(lab_events == ["pull_request", "workflow_dispatch"],
           "C6_B2A_EVENT_CONTRACT_MISMATCH")
    demand("permissions:\n  contents: read\n" in lab and
           "secrets." not in lab and not re.search(
               r"(?m)^\s+(?:contents|pull-requests|actions): write\s*$", lab),
           "C6_B2A_PERMISSIONS_MISMATCH")
    demand("ref: ${{ steps.pin.outputs.trusted_main_sha }}" in lab and
           "EXPECTED_MAIN: 0d5315be79262bb0355f8141a351937272f548fd" in lab and
           "persist-credentials: false" in lab and
           "live['head']['sha'] == os.environ['EVENT_HEAD']" in lab and
           "MAIN_DRIFT_AFTER_CLI" in lab and
           "cancel-in-progress: false" in lab,
           "C6_B2A_TRUST_SOURCE_MISMATCH")
    demand("needs: host-adversarial" in lab and
           "python3 -m py_compile" in lab and
           "-p 'test_hw4_mem_c6_refs.py' -v" in lab and
           "-p 'test_hw4_mem_c6_b2_a_live.py' -v" in lab,
           "C6_B2A_HOST_TESTS_MISSING")
    demand("actions/upload-artifact@v4" in lab and
           "if-no-files-found: error" in lab and "if: success()" in lab and
           "SHA256SUMS.txt" in lab and "--pr 330" in lab and
           "--pr 339" in lab and "continue-on-error:" not in lab and
           "|| true" not in lab, "C6_B2A_ARTIFACT_GUARD_MISSING")
    demand("PROVENANCE_ONLY" in lab and "NOT_MEMORY_GATE" in lab and
           "report['PR_INCREMENTAL_VERDICT'] == 'UNVERIFIED'" in lab and
           "report['INTEGRATION_MEMORY_VERDICT'] == 'UNVERIFIED'" in lab and
           "FALSE_READY" in lab, "C6_B2A_MEMORY_PASS_SPOOF")
    # B2-B must only touch its five exact paths; never become required.
    demand(C6_B2B_WORKFLOW in FAMILIES["HW4"] and
           all(C6_B2B_WORKFLOW not in names for f, names in FAMILIES.items()
               if f != "HW4"), "C6_B2B_WRONG_FAMILY")
    b2b = sources[C6_B2B_WORKFLOW]
    b2b_paths = filters(b2b)
    demand(b2b_paths is not None and len(b2b_paths) == len(C6_B2B_PATHS)
           and set(b2b_paths) == set(C6_B2B_PATHS),
           "C6_B2B_FILTER_CONTRACT_MISMATCH")
    b2b_events = re.findall(r"(?m)^  ([a-z][\w-]*):",
                            b2b.split("\npermissions:", 1)[0])
    demand(b2b_events == ["pull_request", "workflow_dispatch"],
           "C6_B2B_EVENT_CONTRACT_MISMATCH")
    demand("permissions:\n  contents: read\n  pull-requests: read\n  actions: read\n" in b2b
           and "pull_request_target:" not in b2b and "secrets." not in b2b
           and not re.search(r"(?m)^\s+(?:contents|pull-requests|actions): write\s*$", b2b),
           "C6_B2B_PERMISSIONS_MISMATCH")
    demand("needs: host-negatives" in b2b and
           "persist-credentials: false" in b2b and
           "fetch-depth: 0" in b2b and
           "EVENT_REPO" in b2b and
           "FORK_UNTRUSTED_STOP" in b2b and
           b2b.count("ref: $" + "{{ github.event.pull_request.head.sha || github.sha }}") == 2,
           "C6_B2B_CONTROLLER_SOURCE_MISMATCH")
    demand("LAB_BASE" in b2b and
           "6d3aae8a95b97e18174d758f35ef240740e9a861" in b2b and
           "4d261f2a76374ab99a4dd7415cae7a097330c46b" in b2b and
           "64b0087d5087903fee175c4f149c65a65bb43fe6" in b2b and
           "PR330_HEAD_MOVED_STOP" in b2b and
           "GITHUB_TOKEN" not in b2b and
           "github.token" in b2b,
           "C6_B2B_PROVENANCE_MISMATCH")
    demand("python3 -m unittest discover -s tests -p test_hw4_mem_c6_b2b.py -v"
           in b2b and "python3 -m py_compile" in b2b and
           "python3 tools/ci/hw4_mem_c6_b2b.py" in b2b and
           "8-XTENSA" in b2b and "NOT_REQUIRED" in b2b and
           "run-id: 42657443478" in b2b and
           "--reuse" in b2b and "Build only seven remaining" in b2b,
           "C6_B2B_EIGHT_BUILD_NOT_GUARDED")
    demand("if-no-files-found: error" in b2b and
           "actions/upload-artifact@v4" in b2b and
           "SHA256SUMS.txt" in b2b and
           "continue-on-error" not in b2b and
           "|| true" not in b2b,
           "C6_B2B_ARTIFACT_MISSING_OR_RC_MASKED")
    # D1 must never introduce a required memory gate or writable event.
    demand(C6_D1_WORKFLOW in FAMILIES["HW4"] and
           all(C6_D1_WORKFLOW not in names for f, names in FAMILIES.items()
               if f != "HW4"), "C6_D1_WRONG_FAMILY")
    d1 = sources[C6_D1_WORKFLOW]
    paths_d1 = filters(d1)
    demand(paths_d1 is not None and len(paths_d1) == len(C6_D1_PATHS)
           and set(paths_d1) == set(C6_D1_PATHS),
           "C6_D1_FILTER_CONTRACT_MISMATCH")
    d1_events = re.findall(r"(?m)^  ([a-z][\w-]*):",
                           d1.split("\npermissions:", 1)[0])
    demand(d1_events == ["pull_request", "workflow_dispatch"],
           "C6_D1_EVENTS_MISMATCH")
    demand("permissions:\n  contents: read\n  pull-requests: read\n  actions: read\n" in d1
           and "pull_request_target:" not in d1 and "secrets." not in d1
           and not re.search(r"(?m)^\s+(?:contents|pull-requests|actions): write\s*$", d1),
           "C6_D1_PERMISSIONS_MISMATCH")
    demand("group: hw4-mem-c6-b2-d1-one-shot-330" in d1 and
           "cancel-in-progress: false" in d1 and
           "fetch-depth: 0" in d1 and
           d1.count("persist-credentials: false") == 2 and
           d1.count("ref: $" + "{{ github.event.pull_request.head.sha || github.sha }}") == 2
           and "LAB_BASE" in d1 and
           "3d7f1dc914324a846ff92ba3a33ab9e03916b076" in d1,
           "C6_D1_CONTROLLER_TRUST_MISMATCH")
    demand("needs: host-negative-tests" in d1 and
           "-p test_hw4_mem_c6_b2_d1.py -v" in d1 and
           "python3 tools/ci/opt3_routing.py --self-test" in d1 and
           "42660089530" in d1 and
           "hw4-c6-b2-b-330-8build-42660089530-1" in d1 and
           "python3 tools/ci/hw4_mem_c6_b2_d1.py" in d1 and
           "GH_TOKEN: $" + "{{ github.token }}" in d1,
           "C6_D1_SOURCE_AND_OLD_ARTIFACT_MISMATCH")
    demand("if-no-files-found: error" in d1 and
           "if: always()" in d1 and
           "SHA256SUMS.txt" in d1 and
           "actions/upload-artifact@v4" in d1 and
           "continue-on-error" not in d1 and "|| true" not in d1 and
           "C6-D1 PRELINK_DIAGNOSTIC_ONLY NOT_REQUIRED" in d1,
           "C6_D1_MASKED_FAILURE_OR_NO_ARTIFACT")
    clk_paths = filters(sources[CLK01_WORKFLOW])
    demand(clk_paths is not None and
           len(clk_paths) == len(CLK01_PATHS) and
           set(clk_paths) == set(CLK01_PATHS),
           "CLK01_FILTER_CONTRACT_MISMATCH")
    demand(CLK01_WORKFLOW in triggered_names(
           [".github/workflows/" + CLK01_WORKFLOW], sources),
           "CLK01_SELF_CHANGE_UNROUTED")
    clk03_src = sources[CLK03_WORKFLOW]
    clk03_paths = filters(clk03_src)
    demand(clk03_paths is not None and
           len(clk03_paths) == len(CLK03_PATHS) and
           set(clk03_paths) == set(CLK03_PATHS),
           "CLK03_FILTER_CONTRACT_MISMATCH")
    # Restrict the isolated workflow to its two approved event sources.
    # The exact five paths above bind pull_request; workflow_dispatch is manual.
    events = re.findall(r"(?m)^  ([a-z][\w-]*):",
                        clk03_src.split("\npermissions:", 1)[0])
    demand(events == ["pull_request", "workflow_dispatch"],
           "CLK03_EVENT_CONTRACT_MISMATCH")
    demand(CLK03_WORKFLOW in triggered_names(
           [".github/workflows/" + CLK03_WORKFLOW], sources),
           "CLK03_SELF_CHANGE_UNROUTED")

    clk04_src = sources[CLK04_WORKFLOW]
    clk04_paths = filters(clk04_src)
    demand(clk04_paths is not None and
           len(clk04_paths) == len(CLK04_PATHS) and
           set(clk04_paths) == set(CLK04_PATHS),
           "CLK04_FILTER_CONTRACT_MISMATCH")
    clk04_events = re.findall(r"(?m)^  ([a-z][\w-]*):",
                             clk04_src.split("\npermissions:", 1)[0])
    demand(clk04_events == ["pull_request", "workflow_dispatch"],
           "CLK04_EVENT_CONTRACT_MISMATCH")
    demand(CLK04_WORKFLOW in triggered_names(
           [".github/workflows/" + CLK04_WORKFLOW], sources),
           "CLK04_SELF_CHANGE_UNROUTED")
    a2_src = sources[CLK04_A2_WORKFLOW]
    a2_paths = filters(a2_src)
    demand(a2_paths is not None and len(a2_paths) == len(CLK04_A2_PATHS)
           and set(a2_paths) == set(CLK04_A2_PATHS),
           "A2_FILTER_CONTRACT_MISMATCH")
    a2_events = re.findall(r"(?m)^  ([a-z][\w-]*):",
                           a2_src.split("\npermissions:", 1)[0])
    demand(a2_events == ["pull_request", "workflow_dispatch"],
           "A2_EVENT_CONTRACT_MISMATCH")
    demand(CLK04_A2_WORKFLOW in triggered_names(
           [".github/workflows/" + CLK04_A2_WORKFLOW], sources),
           "A2_SELF_CHANGE_UNROUTED")
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
    audit_paper_permanent(sources)
    audit_cls_route(sources)
    audit_cls_permanent(sources)
    audit_j122_permanent(sources)
    audit_r1_permanent(sources)
    ea = (ROOT / "tools/j1_16_e_a_store.py").read_text()
    da = (ROOT / "tools/j1_16_d_a_store.py").read_text()
    demand("SEALED_E_A_ARCHIVE_MISMATCH" in ea and
           "UNVERIFIED_SCALAR_RETAINED" in ea and
           "SEALED_D_A_ARCHIVE_MISMATCH" in da,
           "E_A_C1_OR_D_A_SEAL_LOST")




def r1_exact_step(job, expected, code):
    header = expected.split("\n", 1)[0]
    demand(job.count(header) == 1, code + "_MISSING")
    tail = job.split(header, 1)[1]
    boundary = re.search(r"(?m)^      - ", tail)
    actual = header + (tail[:boundary.start()] if boundary else tail)
    demand(actual.rstrip() == expected, code + "_ALTERED")


def audit_r1_permanent(sources):
    """A PR cannot bypass both independently pinned R1 checks."""
    workflow = sources[R1_WORKFLOW]
    required = EXPECTED_ROUTES[R1_WORKFLOW]
    actual = filters(workflow)
    demand(actual is not None and len(actual) == len(required)
           and set(actual) == set(required), "R1_MANDATORY_FILTER_SET_MISMATCH")
    demand("  push:\n    branches: [main]" in workflow,
           "R1_MAIN_PUSH_MISSING")
    marker = "\n  sealed-originals:\n"
    demand(workflow.count(marker) == 1, "R1_SEALED_JOB_MISSING")
    tail = workflow.split(marker, 1)[1]
    boundary = re.search(r"(?m)^  [A-Za-z][\w-]*:[ \t]*$", tail)
    job = tail[:boundary.start()] if boundary else tail
    prefix = job.split("\n    steps:", 1)[0]
    demand("    runs-on: ubuntu-24.04" in prefix
           and not re.search(r"(?m)^    (?:if|needs|continue-on-error):",
                             prefix),
           "R1_SEALED_JOB_CONDITIONAL")
    demand(job.count(R1_SEAL_COMMAND) == 1
           and job.count(R1_VERIFY_COMMAND) == 1,
           "R1_SEAL_COMMAND_MISSING")
    r1_exact_step(job, R1_SEALED_STEP, "R1_SEALED_STEP")
    demand("if: github.event_name == 'workflow_dispatch' && "
           "github.ref_name == 'oracle/hw4-esc-r1-cpc'" in workflow,
           "R1_UNREQUESTED_ACQUISITION")
    permanent = sources["ci-cpc-permanent.yml"]
    marker = "\n  sealed-evidence:\n"
    demand(permanent.count(marker) == 1, "R1_PERMANENT_JOB_MISSING")
    tail = permanent.split(marker, 1)[1]
    boundary = re.search(r"(?m)^  [A-Za-z][\w-]*:[ \t]*$", tail)
    job = tail[:boundary.start()] if boundary else tail
    demand(job.count(R1_SEAL_COMMAND) == 1
           and job.count(R1_VERIFY_COMMAND) == 1,
           "R1_PERMANENT_SEAL_MISSING")
    r1_exact_step(job, R1_PERMANENT_STEP, "R1_PERMANENT_STEP")


def r1_negative_tests(sources):
    """Only in-memory workflow mutations; original files never touched."""
    original = sources[R1_WORKFLOW]
    for required in EXPECTED_ROUTES[R1_WORKFLOW]:
        needle = "      - '" + required + "'\n"
        demand(needle in original, "R1_NEGATIVE_INERT_" + required)
        altered = {**sources, R1_WORKFLOW: original.replace(needle, "", 1)}
        try:
            audit_r1_permanent(altered)
        except UnsafeRoute as exc:
            demand(str(exc) == "R1_MANDATORY_FILTER_SET_MISMATCH",
                   "R1_FILTER_WRONG_REJECTION_" + required + ":" + str(exc))
        else:
            raise UnsafeRoute("R1_REMOVED_FILTER_ACCEPTED_" + required)
        print("CI-OPT3 R1_FILTER_REMOVAL_REJECTED", required)
    for label, workflow, before, after, expected in (
        ("SEALED_JOB_SKIPPED", R1_WORKFLOW,
         "  sealed-originals:\n    runs-on:",
         "  sealed-originals:\n    if: false\n    runs-on:",
         "R1_SEALED_JOB_CONDITIONAL"),
        ("R1_SEAL_CHANGED", R1_WORKFLOW, R1_SEAL_COMMAND,
         R1_SEAL_COMMAND.replace(R1_SEAL, "0" * 64),
         "R1_SEAL_COMMAND_MISSING"),
        ("PERMANENT_SEAL_CHANGED", "ci-cpc-permanent.yml",
         R1_SEAL_COMMAND, R1_SEAL_COMMAND.replace(R1_SEAL, "0" * 64),
         "R1_PERMANENT_SEAL_MISSING"),
        ("PERMANENT_STEP_REMOVED", "ci-cpc-permanent.yml",
         R1_PERMANENT_STEP + "\n", "",
         "R1_PERMANENT_SEAL_MISSING"),
    ):
        src = sources[workflow]
        demand(before in src, "R1_NEGATIVE_INERT_" + label)
        altered = {**sources, workflow: src.replace(before, after, 1)}
        try:
            audit_r1_permanent(altered)
        except UnsafeRoute as exc:
            demand(str(exc) == expected,
                   "R1_NEGATIVE_WRONG_REJECTION_" + label + ":" + str(exc))
        else:
            raise UnsafeRoute("R1_NEGATIVE_ACCEPTED_" + label)
        print("CI-OPT3 R1_SEAL_BYPASS_REJECTED", label)
    for proof in (R1_VERIFIER, R1_MANIFEST,
                  "tests/fixtures/cpc6128/hw4_esc_r1/E03/screenshot_fake.png"):
        demand(R1_WORKFLOW in triggered_names([proof], sources),
               "R1_EVIDENCE_CHANGE_NOT_ROUTED_" + proof)
        print("CI-OPT3 R1_EVIDENCE_PR_TRIGGER_VERIFIED", proof)


def audit_j122_permanent(sources):
    """Fail-closed single J1.22-A oracle in mandatory unfiltered permanent job."""
    audit_paper_permanent(sources)
    yml = sources[PAPER_WORKFLOW]
    marker = "\n  sealed-evidence:"
    demand(yml.count(marker) == 1, "J122_SEALED_JOB_MISSING")
    tail = yml.split(marker, 1)[1]
    end = re.search(r"(?m)^  [A-Za-z][\w-]*:[ \t]*$", tail)
    job = tail[:end.start()] if end else tail
    r1_exact_step(job, J122_PERMANENT_STEP, "J122_PERMANENT_STEP")
    for path in (J122_TOOL, J122_ZIP,
                 "tests/fixtures/cpc6128/j1_22_a_integer_logical/corpus.json"):
        demand(PAPER_WORKFLOW in triggered_names([path], sources),
               "J122_PERMANENT_UNROUTED_" + path)
    return True


def j122_permanent_negative_tests(sources):
    """Deterministically falsify only in-memory route strings; never relax old audits."""
    original = sources[PAPER_WORKFLOW]
    step = J122_PERMANENT_STEP
    demand(original.count(step) == 1, "J122_NEGATIVE_INERT")
    def mutate(old, new):
        demand(original.count(old) == 1, "J122_NEGATIVE_INERT")
        return original.replace(old, new, 1)
    cases = {
        "STEP_REMOVED": (mutate(step + "\n", ""), "J122_PERMANENT_STEP_MISSING"),
        "IF_FALSE": (mutate(step, step.replace("        shell: bash",
            "        if: false\\n        shell: bash")), "J122_PERMANENT_STEP_ALTERED"),
        "CONTINUE_ON_ERROR": (mutate(step, step.replace("        shell: bash",
            "        continue-on-error: true\\n        shell: bash")), "J122_PERMANENT_STEP_ALTERED"),
        "NO_SELF_TEST": (mutate(step, step.replace("--self-test", "")),
            "J122_PERMANENT_STEP_ALTERED"),
        "NO_CHECK_SOURCES": (mutate(step, step.replace("--check-sources", "")),
            "J122_PERMANENT_STEP_ALTERED"),
        "WRONG_ARCHIVE": (mutate(step, step.replace(J122_ZIP, "tests/fixtures/cpc6128/j1_19_a_paper/fake.zip")),
            "J122_PERMANENT_STEP_ALTERED"),
        "WRONG_ZIP_SHA": (mutate(step, step.replace(J122_ZIP_SHA256, "0" * 64)),
            "J122_PERMANENT_STEP_ALTERED"),
        "WRONG_MANIFEST_SHA": (mutate(step, step.replace(J122_MANIFEST_SHA256, "0" * 64)),
            "J122_PERMANENT_STEP_ALTERED"),
        "WRONG_ROM": (mutate(step, step.replace(J122_ROM_SHA256, "0" * 64)),
            "J122_PERMANENT_STEP_ALTERED"),
        "WRONG_HEAD": (mutate(step, step.replace(J122_HEAD, "0" * 40)),
            "J122_PERMANENT_STEP_ALTERED"),
        "WEAK_SHELL": (mutate(step, step.replace("set -euo pipefail", "set +e")),
            "J122_PERMANENT_STEP_ALTERED"),
        "FAKE_VERIFIER": (mutate(step, step.replace(J122_TOOL, "tools/j1_99_unknown_oracle.py")),
            "J122_PERMANENT_STEP_ALTERED"),
    }
    for label, (bad, expected) in cases.items():
        try:
            audit_j122_permanent({**sources, PAPER_WORKFLOW: bad})
        except UnsafeRoute as exc:
            demand(str(exc) == expected, "J122_WRONG_REJECTION_" + label + ":" + str(exc))
        else:
            raise UnsafeRoute("J122_ACCEPTED_TAMPERING_" + label)
        print("CI-OPT3 J122_PERMANENT_FALSIFICATION_REJECTED", label)
    demand(not HISTORICAL.intersection(triggered_names([J122_TOOL.replace("j1_22_a", "j1_99_unknown")], sources)),
           "J122_UNKNOWN_ORACLE_REGISTERED")
    print("CI-OPT3 J122_UNKNOWN_ORACLE_STILL_UNREGISTERED")


def audit_cls_permanent(sources):
    """The CLS SHA chain is mandatory on all PRs and main, not only branch CLS."""
    yml=sources[PAPER_WORKFLOW]
    # Existing PAPER audit enforces unfiltered PR/push, exact sealed-evidence shape.
    audit_paper_permanent(sources)
    marker="\n  sealed-evidence:"
    demand(yml.count(marker)==1,"CLS_SEALED_JOB_MISSING")
    tail=yml.split(marker,1)[1]
    boundary=re.search(r"(?m)^  [a-zA-Z][\w-]*:[ \t]*$",tail)
    job=tail[:boundary.start()] if boundary else tail
    header=CLS_PERMANENT_STEP.split("\n",1)[0]
    matches=list(re.finditer(r"(?m)^"+re.escape(header)+r"$",job))
    demand(len(matches)==1,"CLS_PERMANENT_STEP_MISSING")
    rest=job[matches[0].end():]
    next_step=re.search(r"(?m)^      - ",rest)
    actual=job[matches[0].start():
               matches[0].end()+next_step.start() if next_step else len(job)]
    demand(actual.rstrip()==CLS_PERMANENT_STEP,"CLS_PERMANENT_STEP_ALTERED")
    return True


def cls_permanent_negative_tests(sources):
    original=sources[PAPER_WORKFLOW]
    step=CLS_PERMANENT_STEP
    demand(original.count(step)==1,"CLS_PERMANENT_NEGATIVE_INERT")
    def mutate(a,b):
        demand(original.count(a)==1,"CLS_PERMANENT_NEGATIVE_INERT")
        return original.replace(a,b,1)
    failures={
       "REMOVED":(mutate(step+"\n",""),"CLS_PERMANENT_STEP_MISSING"),
       "NOT_PERMANENT":(mutate(step,step.replace("--permanent --self-test","--self-test")),
                        "CLS_PERMANENT_STEP_ALTERED"),
       "NO_SELF_TEST":(mutate(step,step.replace("--permanent --self-test","--permanent")),
                        "CLS_PERMANENT_STEP_ALTERED"),
       "WRONG_ARCHIVE":(mutate(step,step.replace(CLS_ARCHIVE,
                          "tests/fixtures/cpc6128/j1_19_a_paper")),
                        "CLS_PERMANENT_STEP_ALTERED"),
       "FAKE_ORACLE":(mutate(step,step.replace(CLS_TOOL,"tools/not_cls_oracle.py")),
                        "CLS_PERMANENT_STEP_ALTERED"),
       "SKIP_ON_FAILURE":(mutate(step,step.replace("        shell: bash",
                          "        continue-on-error: true\n        shell: bash")),
                        "CLS_PERMANENT_STEP_ALTERED"),
       "IF_FALSE":(mutate(step,step.replace("        shell: bash",
                          "        if: false\n        shell: bash")),
                        "CLS_PERMANENT_STEP_ALTERED"),
       "NO_STRICT_SHELL":(mutate(step,step.replace("set -euo pipefail","set +e")),
                        "CLS_PERMANENT_STEP_ALTERED"),
    }
    for name,(damaged,expected) in failures.items():
        try:
            audit_cls_permanent({**sources,PAPER_WORKFLOW:damaged})
        except UnsafeRoute as ex:
            demand(str(ex)==expected,"CLS_PERMANENT_WRONG_REJECTION_"+name+":"+str(ex))
        else:
            raise UnsafeRoute("CLS_PERMANENT_BYPASS_"+name)
        print("CI-OPT3 CLS_PERMANENT_FALSIFICATION_REJECTED",name,expected)


def audit_cls_route(sources):
    """J1.21-A must reach the genuine pinned GHCR job, never a dummy gate."""
    yml=sources[PAPER_WORKFLOW]
    marker="\n  "+CLS_JOB+":"
    demand(yml.count(marker)==1, "CLS_JOB_MISSING")
    header,job=yml.split(marker,1)
    guard=("if: (github.event_name == 'pull_request' && "
           "github.head_ref == '"+CLS_BRANCH+"' && "
           "github.event.pull_request.head.repo.full_name == github.repository) || "
           "(github.event_name == 'workflow_dispatch' && "
           "github.ref_name == '"+CLS_BRANCH+"')")
    demand(guard in job,"CLS_BRANCH_FORK_GUARD")
    demand("github.head_ref != '"+CLS_BRANCH+"'" in header and
           "cancel-in-progress:" in header,"CLS_ARCHIVE_CANCEL_RISK")
    demand("    permissions:\n      contents: write\n      packages: read" in job,
           "CLS_JOB_PERMISSIONS")
    demand("      image: "+PAPER_IMAGE in job,"CLS_GHCR_DIGEST")
    demand('test "$(git rev-parse HEAD)" = "$GITHUB_HEAD_SHA"' in job and
           "github.event.pull_request.head.sha || github.sha" in job and
           "submodules: recursive" in job,"CLS_HEAD_PIN")
    demand('test "$(git -C tests/oracles/caprice32 rev-parse HEAD)" = '+PAPER_CAPRICE in job and
           'test "$(cat /usr/local/share/loco-caprice32-source.sha)" = '+PAPER_CAPRICE in job and
           'test "$(sha256sum tests/oracles/caprice32/rom/cpc6128.rom | cut -d '+
           "' ' -f 1)\" = "+PAPER_ROM in job,"CLS_ROM_CAPRICE_PIN")
    demand("test -x /usr/local/bin/cap32" in job and
           "cp /usr/local/bin/cap32 tests/oracles/caprice32/cap32" in job,
           "CLS_GENUINE_EMULATOR")
    demand("git diff origin/main...HEAD --name-only" in job and
           "J1.21-A FORBIDDEN_DIFF_PATH" in job and
           "tests/fixtures/cpc6128/j1_18_" in job and
           "tools/j1_18_" in job,"CLS_FORBIDDEN_DIFF_GUARD")
    demand("python3 "+CLS_TOOL+" --check-sources" in job and
           "test_j1_21_a_cls_oracle.py" in job and
           "python3 "+CLS_TOOL+" --acquire tests/oracles/caprice32" in job and
           ' --output "$RUNNER_TEMP/j121-cls" --head "$GITHUB_HEAD_SHA"' in job and
           "python3 "+CLS_TOOL+' --evidence "$RUNNER_TEMP/j121-cls"' in job,
           "CLS_REAL_CAPTURE_LINK")
    demand("DEST="+CLS_ARCHIVE in job and
           "git ls-remote --exit-code origin refs/heads/"+CLS_BRANCH in job and
           'test "$REMOTE_HEAD" = "$GITHUB_HEAD_SHA"' in job and
           "git push origin HEAD:refs/heads/"+CLS_BRANCH in job,
           "CLS_ARCHIVE_ANTI_RACE")
    demand("ARCHIVE_PENDING_EXTERNAL_SEAL" in job and
           "--permanent --self-test" in job and
           "FRESH_REACQUISITION_RAM_LIST_ERR_ERL_ROI_MATCH_ARCHIVE" in job and
           "EXTERNALLY_SEALED_PASS" in job,
           "CLS_REACQUISITION_OR_SEAL_MISSING")
    demand("actions/upload-artifact@v4" in job and
           "j121-cls-origin-sha256.txt" in job and
           "j121-cls-manifest-sha256.txt" in job and
           "j121-cls-origin.txt" in job and
           "j121-cls-cpc-original-" in job,"CLS_ORIGINAL_ARTIFACT")
    return True


def cls_route_negative_tests(sources):
    """Mutate only in memory; prove branch/fork, proof and archive guards."""
    yml=sources[PAPER_WORKFLOW]
    job="\n  "+CLS_JOB+":"
    cases={
      "MISSING_JOB":(yml.split(job,1)[0],"CLS_JOB_MISSING"),
      "UNSAFE_BRANCH":(yml.replace("github.head_ref == '"+CLS_BRANCH+"'",
                                  "github.head_ref == 'main'"),"CLS_BRANCH_FORK_GUARD"),
      "FORK_ALLOW":(yml.replace("github.event.pull_request.head.repo.full_name == github.repository",
                                "github.event.pull_request.head.repo.full_name != github.repository"),
                     "PAPER_BRANCH_AND_FORK_GUARD"),
      "UNPINNED_IMAGE":(yml.replace(PAPER_IMAGE,"ubuntu:latest"),"PAPER_GHCR"),
      "CAPTURE_MISSING":(yml.replace(CLS_TOOL+" --acquire",
                                   "tools/unknown.py --acquire"),"CLS_REAL_CAPTURE_LINK"),
      "NO_ORIGIN_ARTIFACT":(yml.replace("j121-cls-origin-sha256.txt",
                                         "untrusted-origin.txt"),"CLS_ORIGINAL_ARTIFACT"),
      "NO_ANTIRACE":(yml.replace("git ls-remote --exit-code origin refs/heads/"+CLS_BRANCH,
                                  "git rev-parse HEAD"),"CLS_ARCHIVE_ANTI_RACE"),
      "SEAL_DISABLED":(yml.replace("FRESH_REACQUISITION_RAM_LIST_ERR_ERL_ROI_MATCH_ARCHIVE",
                                    "FRESH_UNVERIFIED"),"CLS_REACQUISITION_OR_SEAL_MISSING"),
    }
    for label,(damaged,expected) in cases.items():
        demand(damaged!=yml,"CLS_NEGATIVE_INERT_"+label)
        try:
            audit_paper_route({**sources,PAPER_WORKFLOW:damaged})
            audit_cls_route({**sources,PAPER_WORKFLOW:damaged})
        except UnsafeRoute as exc:
            # Older PAPER guards may reject a global alteration first.
            demand(str(exc)==expected or
                   (label=="FORK_ALLOW" and str(exc) in
                    ("PAPER_BRANCH_AND_FORK_GUARD","CLS_BRANCH_FORK_GUARD")) or
                   (label=="UNPINNED_IMAGE" and str(exc) in
                    ("PAPER_GHCR","CLS_GHCR_DIGEST")),
                   "CLS_NEGATIVE_WRONG_REASON_"+label+":"+str(exc))
        else:
            raise UnsafeRoute("CLS_NEGATIVE_BYPASS_"+label)
        print("CI-OPT3 CLS_FALSIFICATION_REJECTED",label,expected)


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



def audit_paper_permanent(sources):
    """Protect unfiltered PR/main events and an unconditional sealed-evidence step."""
    yml = sources[PAPER_WORKFLOW]
    on = re.findall(r"(?ms)^on:\n(.*?)(?=^[A-Za-z][\w-]*:|\Z)", yml)
    expected = ("  pull_request:\n  push:\n"
                "    branches: [main]\n  workflow_dispatch:")
    demand(len(on) == 1 and on[0].strip() == expected.strip(),
           "PAPER_PERMANENT_TRIGGER")
    demand(yml.count("\njobs:\n") == 1, "PAPER_PERMANENT_JOBS")
    matches = list(re.finditer(r"(?m)^  sealed-evidence:[ \t]*$", yml))
    demand(len(matches) == 1, "PAPER_SEALED_JOB_MISSING")
    tail = yml[matches[0].end():]
    next_job = re.search(r"(?m)^  [a-zA-Z][\w-]*:[ \t]*$", tail)
    job = tail[:next_job.start()] if next_job else tail
    head, separator, steps = job.partition("\n    steps:\n")
    demand(bool(separator) and
           re.search(r"(?m)^    runs-on: ubuntu-24\.04\s*$", head),
           "PAPER_SEALED_JOB_SHAPE")
    demand(not re.search(r"(?m)^    (?:if|needs|continue-on-error|strategy):",
                         head), "PAPER_SEALED_JOB_CONDITIONAL")
    header = PAPER_PERMANENT_STEP.split("\n", 1)[0]
    matches = list(re.finditer(r"(?m)^" + re.escape(header) + r"$", steps))
    demand(len(matches) == 1, "PAPER_PERMANENT_STEP_MISSING")
    following = steps[matches[0].end():]
    boundary = re.search(r"(?m)^      - ", following)
    actual = steps[matches[0].start():
                   matches[0].end() + boundary.start() if boundary else len(steps)]
    demand(actual.rstrip() == PAPER_PERMANENT_STEP,
           "PAPER_PERMANENT_STEP_ALTERED")
    return True


def paper_permanent_negative_tests(sources):
    """Mutate workflow strings only; negative controls never change tracked files."""
    original = sources[PAPER_WORKFLOW]

    def change(old, new):
        demand(original.count(old) == 1, "PAPER_GATE_NEGATIVE_INERT")
        return original.replace(old, new, 1)

    step = PAPER_PERMANENT_STEP
    moved = change(step + "\n", "")
    acquisition = "      - name: Acquire 24 independent PAPER cases plus direct and chronology checks from real CPC"
    demand(acquisition in moved, "PAPER_ACQUISITION_STEP_NOT_FOUND")
    moved = moved.replace(acquisition, step + "\n" + acquisition, 1)
    cases = {
        "STEP_REMOVED": (change(step + "\n", ""), "PAPER_PERMANENT_STEP_MISSING"),
        "ONLY_IN_SPECIALIZED_JOB": (moved, "PAPER_PERMANENT_STEP_MISSING"),
        "JOB_CONDITIONAL": (change("  sealed-evidence:\n    runs-on:",
                                   "  sealed-evidence:\n    if: false\n    runs-on:"),
                             "PAPER_SEALED_JOB_CONDITIONAL"),
        "JOB_DEPENDENCY": (change("  sealed-evidence:\n    runs-on:",
                                  "  sealed-evidence:\n    needs: paper-cpc-acquisition\n    runs-on:"),
                            "PAPER_SEALED_JOB_CONDITIONAL"),
        "STEP_IF_FALSE": (change(step, step.replace(
            "        shell: bash", "        if: false\n        shell: bash")),
            "PAPER_PERMANENT_STEP_ALTERED"),
        "STEP_CONTINUE_ON_ERROR": (change(step, step.replace(
            "        shell: bash", "        continue-on-error: true\n        shell: bash")),
            "PAPER_PERMANENT_STEP_ALTERED"),
        "SKIP_ARCHIVE": (change(step, step.replace(
            "          python3 tools/j1_19_a_paper_oracle.py --check-sources",
            "          if test -f tests/fixtures/cpc6128/j1_19_a_paper/manifest.json; then\n"
            "            python3 tools/j1_19_a_paper_oracle.py --check-sources\n"
            "          fi")), "PAPER_PERMANENT_STEP_ALTERED"),
        "SWALLOW_FAILURE": (change(step, step.replace(
            "--permanent --self-test", "--permanent --self-test || true")),
            "PAPER_PERMANENT_STEP_ALTERED"),
        "NO_CHECK_SOURCES": (change(step, step.replace(
            "          python3 tools/j1_19_a_paper_oracle.py --check-sources\n", "")),
            "PAPER_PERMANENT_STEP_ALTERED"),
        "NO_PERMANENT": (change(step, step.replace(
            "--permanent --self-test", "--self-test")), "PAPER_PERMANENT_STEP_ALTERED"),
        "NO_SELF_TEST": (change(step, step.replace(
            "--permanent --self-test", "--permanent")), "PAPER_PERMANENT_STEP_ALTERED"),
        "WRONG_ARCHIVE": (change(step, step.replace(
            PAPER_ARCHIVE, "tests/fixtures/cpc6128/j1_18_a_ink")),
            "PAPER_PERMANENT_STEP_ALTERED"),
        "UNKNOWN_ORACLE": (change(step, step.replace(
            PAPER_TOOL, "tools/unknown_oracle.py")), "PAPER_PERMANENT_STEP_ALTERED"),
        "PR_DOC_SKIP": (change("  pull_request:\n",
                               "  pull_request:\n    paths-ignore: ['docs/**']\n"),
                        "PAPER_PERMANENT_TRIGGER"),
        "PR_BRANCH_SKIP": (change("  pull_request:\n",
                                  "  pull_request:\n    branches: [oracle/j1-19-a-paper-cpc]\n"),
                           "PAPER_PERMANENT_TRIGGER"),
        "PUSH_MAIN_LOST": (change("    branches: [main]\n",
                                  "    branches: [oracle/j1-19-a-paper-cpc]\n"),
                           "PAPER_PERMANENT_TRIGGER"),
    }
    for label, (bad, reason) in cases.items():
        demand(bad != original, "PAPER_GATE_INERT_" + label)
        try:
            audit_paper_permanent({**sources, PAPER_WORKFLOW: bad})
        except UnsafeRoute as exc:
            demand(str(exc) == reason,
                   "PAPER_GATE_WRONG_REJECTION_" + label + ":" + str(exc))
        else:
            raise UnsafeRoute("PAPER_GATE_BYPASS_" + label)
        print("CI-OPT3 PAPER_PERMANENT_FALSIFICATION_REJECTED", label, reason)


def paper_archive_negative_tests():
    """Check real archive attacks using temporary copies; no Caprice32 acquisition."""
    import hashlib
    import importlib
    import json
    import os
    import shutil
    import tempfile
    from unittest.mock import patch

    sys.path.insert(0, str(ROOT / "tools"))
    oracle = importlib.import_module("j1_19_a_paper_oracle")
    archive = ROOT / PAPER_ARCHIVE
    demand(archive.is_dir(), "PAPER_NEGATIVE_ARCHIVE_ABSENT")
    demand(len(oracle.SEALED_FILE_SHA256) == 264,
           "PAPER_NEGATIVE_SEAL_COUNT")

    def must_fail(label, expected, path):
        try:
            oracle.verify(path, permanent=True)
        except oracle.Invalid as exc:
            demand(str(exc).startswith(expected),
                   "PAPER_ARCHIVE_WRONG_REJECTION_" + label + ":" + str(exc))
        else:
            raise UnsafeRoute("PAPER_ARCHIVE_BYPASS_" + label)
        print("CI-OPT3 PAPER_ARCHIVE_FALSIFICATION_REJECTED", label, expected)

    with tempfile.TemporaryDirectory(prefix="opt3-paper-") as temp:
        must_fail("ARCHIVE_ABSENT", "ARCHIVE_ABSENT", Path(temp) / "missing")
        # File hardlinks are read-only test inputs: unlink before every write.
        copy = Path(temp) / "copy"
        shutil.copytree(archive, copy, copy_function=os.link)
        manifest_file = copy / "manifest.json"
        original = manifest_file.read_bytes()
        manifest_file.unlink()
        manifest_file.write_bytes(original + b" ")
        must_fail("MANIFEST_ALTERED", "FALSE_SEALED_HEAD_OR_MANIFEST", copy)

        manifest = json.loads(original)
        manifest["acquisition_head"] = "0" * 40
        manifest_file.write_text(json.dumps(manifest))
        must_fail("FAKE_ACQUISITION_HEAD", "FALSE_HEAD_OR_ANCESTRY", copy)

        # Coordinated file+manifest changes cannot forge the external seal.
        name = sorted(oracle.SEALED_FILE_SHA256)[0]
        evidence_file = copy / name
        raw = evidence_file.read_bytes()
        evidence_file.unlink()
        corrupted = raw + b"\x00"
        evidence_file.write_bytes(corrupted)
        manifest["acquisition_head"] = oracle.SEALED_ACQUISITION_PARENT
        manifest["files"][name] = hashlib.sha256(corrupted).hexdigest()
        manifest_file.write_text(json.dumps(manifest))
        must_fail("COORDINATED_FILE_AND_MANIFEST",
                  "FALSE_SEALED_HEAD_OR_MANIFEST", copy)

    # Wrong independent digest, patched in memory only: source tool untouched.
    name = sorted(oracle.SEALED_FILE_SHA256)[0]
    with patch.dict(oracle.SEALED_FILE_SHA256, {name: "0" * 64}):
        must_fail("INCORRECT_EXTERNAL_SEAL", "EXTERNAL_SHA_" + name, archive)

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


def clk01_negative_tests(sources):
    """Attempt to bypass CLK-01 inventory, exact paths, or manual dispatch."""
    original = sources[CLK01_WORKFLOW]
    for required in CLK01_PATHS:
        needle = "      - '" + required + "'\n"
        demand(original.count(needle) == 1,
               "CLK01_NEGATIVE_INERT_" + required)
        changed = {**sources, CLK01_WORKFLOW: original.replace(needle, "", 1)}
        try:
            audit(changed)
        except UnsafeRoute as exc:
            demand(str(exc) == "CLK01_FILTER_CONTRACT_MISMATCH",
                   "CLK01_REMOVAL_WRONG_REJECTION_" + required + ":" + str(exc))
        else:
            raise UnsafeRoute("CLK01_REMOVED_FILTER_ACCEPTED_" + required)
        print("CI-OPT3 CLK01_FILTER_REMOVAL_REJECTED", required)

    cases = {
        "WORKFLOW_REMOVED": (
            {k: v for k, v in sources.items() if k != CLK01_WORKFLOW},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "WORKFLOW_RENAMED": (
            {**{k: v for k, v in sources.items() if k != CLK01_WORKFLOW},
             "clk-01-renamed.yml": original},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "OVERBROAD_TOOL": (
            {**sources, CLK01_WORKFLOW: original.replace(
                "'tools/clk_01_*'", "'tools/**'", 1)},
            "CLK01_FILTER_CONTRACT_MISMATCH"),
        "ROUTE_DIVERTED": (
            {**sources, CLK01_WORKFLOW: original.replace(
                "'tests/fixtures/cpc6128/clk_01_speed/**'",
                "'core/**'", 1)},
            "CLK01_FILTER_CONTRACT_MISMATCH"),
        "SELF_CHANGE_UNROUTED": (
            {**sources, CLK01_WORKFLOW: original.replace(
                "'.github/workflows/clk-01-acquisition.yml'",
                "'.github/workflows/ci-xtensa.yml'", 1)},
            "CLK01_FILTER_CONTRACT_MISMATCH"),
        "DUPLICATE_FILTER": (
            {**sources, CLK01_WORKFLOW: original.replace(
                "      - 'tools/clk_01_*'\n",
                "      - 'tools/clk_01_*'\n"
                "      - 'tools/clk_01_*'\n", 1)},
            "CLK01_FILTER_CONTRACT_MISMATCH"),
        "DISPATCH_REMOVED": (
            {**sources, CLK01_WORKFLOW: original.replace(
                "  workflow_dispatch:\n", "", 1)},
            "MANUAL_DISPATCH_REMOVED_" + CLK01_WORKFLOW),
    }
    for label, (altered, code) in cases.items():
        demand(altered != sources, "CLK01_NEGATIVE_INERT_" + label)
        try:
            audit(altered)
        except UnsafeRoute as exc:
            demand(str(exc) == code,
                   "CLK01_WRONG_REJECTION_" + label + ":" + str(exc))
        else:
            raise UnsafeRoute("CLK01_FALSIFICATION_ACCEPTED_" + label)
        print("CI-OPT3 CLK01_FALSIFICATION_REJECTED", label, code)

    # Verify each authorized filter activates the CPC acquisition family,
    # and unrelated changes cannot trigger this isolated workflow.
    examples = (
        "tools/clk_01_uart.py",
        "tests/test_clk_01_uart.py",
        "tests/fixtures/cpc6128/clk_01_speed/manifest.json",
        "docs/CLK-01-cpc-speed-baseline.md",
        ".github/workflows/clk-01-acquisition.yml",
    )
    for path in examples:
        demand(CLK01_WORKFLOW in triggered_names([path], sources),
               "CLK01_REQUIRED_PR_PATH_UNROUTED_" + path)
        demand("CPC_ACQUISITION" in family_routes([path], sources),
               "CLK01_WRONG_FAMILY_" + path)
        print("CI-OPT3 CLK01_PR_ROUTE_VERIFIED", path)
    for path in ("tools/other.py", "docs/README.md",
                 "firmware/esp32_display_probe/main/main.c",
                 "tools/ci/opt3_routing.py"):
        demand(CLK01_WORKFLOW not in triggered_names([path], sources),
               "CLK01_UNRELATED_PR_PATH_ROUTED_" + path)
        print("CI-OPT3 CLK01_UNRELATED_ROUTE_REJECTED", path)


def clk03_negative_tests(sources):
    """In-memory falsifications: keep CLK-03 in its own closed CPC family."""
    original = sources[CLK03_WORKFLOW]
    for required in CLK03_PATHS:
        needle = "      - '" + required + "'\n"
        demand(original.count(needle) == 1,
               "CLK03_NEGATIVE_INERT_" + required)
        mutated = {**sources, CLK03_WORKFLOW: original.replace(needle, "", 1)}
        try:
            audit(mutated)
        except UnsafeRoute as exc:
            demand(str(exc) == "CLK03_FILTER_CONTRACT_MISMATCH",
                   "CLK03_REMOVAL_WRONG_REJECTION_" + required + ":" + str(exc))
        else:
            raise UnsafeRoute("CLK03_REMOVED_FILTER_ACCEPTED_" + required)
        print("CI-OPT3 CLK03_FILTER_REMOVAL_REJECTED", required)

    cases = {
        "UNKNOWN_WORKFLOW": (
            {**sources, "clk-03-unregistered.yml": original},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "WORKFLOW_REMOVED": (
            {k: v for k, v in sources.items() if k != CLK03_WORKFLOW},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "WORKFLOW_RENAMED": (
            {**{k: v for k, v in sources.items() if k != CLK03_WORKFLOW},
             "clk-03-renamed.yml": original},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "OVERBROAD_TOOL": (
            {**sources, CLK03_WORKFLOW: original.replace(
                "'tools/clk_03_*'", "'tools/**'", 1)},
            "CLK03_FILTER_CONTRACT_MISMATCH"),
        "OVERBROAD_FIXTURE": (
            {**sources, CLK03_WORKFLOW: original.replace(
                "'tests/fixtures/cpc6128/clk_03_time/**'",
                "'tests/fixtures/**'", 1)},
            "CLK03_FILTER_CONTRACT_MISMATCH"),
        "OVERBROAD_DOC": (
            {**sources, CLK03_WORKFLOW: original.replace(
                "'docs/CLK-03*'", "'docs/**'", 1)},
            "CLK03_FILTER_CONTRACT_MISMATCH"),
        "DUPLICATE_PATH": (
            {**sources, CLK03_WORKFLOW: original.replace(
                "      - 'tools/clk_03_*'\n",
                "      - 'tools/clk_03_*'\n"
                "      - 'tools/clk_03_*'\n", 1)},
            "CLK03_FILTER_CONTRACT_MISMATCH"),
        "SELF_CHANGE_UNROUTED": (
            {**sources, CLK03_WORKFLOW: original.replace(
                "'.github/workflows/clk-03-acquisition.yml'",
                "'.github/workflows/ci-opt3-routing.yml'", 1)},
            "CLK03_FILTER_CONTRACT_MISMATCH"),
        "PR_TRIGGER_REMOVED": (
            {**sources, CLK03_WORKFLOW: original.replace(
                "  pull_request:\n", "", 1)},
            "PULL_REQUEST_MISSING"),
        "DISPATCH_TRIGGER_REMOVED": (
            {**sources, CLK03_WORKFLOW: original.replace(
                "  workflow_dispatch:\n", "", 1)},
            "CLK03_EVENT_CONTRACT_MISMATCH"),
        "PUSH_TRIGGER_ADDED": (
            {**sources, CLK03_WORKFLOW: original.replace(
                "  workflow_dispatch:\n",
                "  workflow_dispatch:\n  push:\n", 1)},
            "CLK03_EVENT_CONTRACT_MISMATCH"),
    }
    for label, (mutated, code) in cases.items():
        demand(mutated != sources, "CLK03_NEGATIVE_INERT_" + label)
        try:
            audit(mutated)
        except UnsafeRoute as exc:
            demand(str(exc) == code,
                   "CLK03_WRONG_REJECTION_" + label + ":" + str(exc))
        else:
            raise UnsafeRoute("CLK03_FALSIFICATION_ACCEPTED_" + label)
        print("CI-OPT3 CLK03_FALSIFICATION_REJECTED", label, code)

    examples = (
        ".github/workflows/clk-03-acquisition.yml",
        "tools/clk_03_cpc_time.py",
        "tests/test_clk_03_time.py",
        "tests/fixtures/cpc6128/clk_03_time/corpus.json",
        "docs/CLK-03-cpc-time-oracle.md",
    )
    for path in examples:
        demand(CLK03_WORKFLOW in triggered_names([path], sources),
               "CLK03_REQUIRED_PR_PATH_UNROUTED_" + path)
        demand("CPC_ACQUISITION" in family_routes([path], sources),
               "CLK03_WRONG_FAMILY_" + path)
        print("CI-OPT3 CLK03_PR_ROUTE_VERIFIED", path)
    for path in (
        "tools/clk_01_cpc.py", "tools/clk_030_cpc.py",
        "tools/ci/opt3_routing.py", "docs/CLK-04-roadmap.md",
        "docs/README.md", "core/basic_executor.c",
        "firmware/esp32_display_probe/main/main.c",
    ):
        demand(CLK03_WORKFLOW not in triggered_names([path], sources),
               "CLK03_UNRELATED_PR_PATH_ROUTED_" + path)
        print("CI-OPT3 CLK03_UNRELATED_ROUTE_REJECTED", path)


def c5_negative_tests(sources):
    """C5-C1: adversarial in-memory inventory, filters and HW4 family tests."""
    original = sources[HW4_MEM_C5]
    exact = filters(original)
    demand(exact is not None and len(exact) == 5 and
           len(set(exact)) == 5 and set(exact) == set(HW4_MEM_C5_PATHS),
           "C5_NEGATIVE_PRECONDITION")
    for required in HW4_MEM_C5_PATHS:
        needle = "      - '" + required + "'\n"
        demand(original.count(needle) == 1,
               "C5_NEGATIVE_INERT_" + required)
        broken = {**sources, HW4_MEM_C5: original.replace(needle, "", 1)}
        try:
            audit(broken)
        except UnsafeRoute as exc:
            demand(str(exc) == "C5_FILTER_CONTRACT_MISMATCH",
                   "C5_REMOVAL_WRONG_REJECTION_" + required + ":" + str(exc))
        else:
            raise UnsafeRoute("C5_REQUIRED_FILTER_REMOVAL_ACCEPTED_" + required)
        print("CI-OPT3 C5_REQUIRED_FILTER_REMOVAL_REJECTED", required)

    cases = {
        "UNKNOWN_WORKFLOW": (
            {**sources, "hw4-mem-c5-unlisted.yml": original},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "C5_REMOVED": (
            {k: v for k, v in sources.items() if k != HW4_MEM_C5},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "C5_RENAMED": (
            {**{k: v for k, v in sources.items() if k != HW4_MEM_C5},
             "hw4-mem-c5-renamed.yml": original},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "DUPLICATE_FILTER": (
            {**sources, HW4_MEM_C5: original.replace(
                "      - 'tools/ci/hw4_mem_c5_*.py'\n",
                "      - 'tools/ci/hw4_mem_c5_*.py'\n"
                "      - 'tools/ci/hw4_mem_c5_*.py'\n", 1)},
            "C5_FILTER_CONTRACT_MISMATCH"),
        "OVERBROAD_TOOL": (
            {**sources, HW4_MEM_C5: original.replace(
                "'tools/ci/hw4_mem_c5_*.py'", "'tools/**'", 1)},
            "C5_FILTER_CONTRACT_MISMATCH"),
        "OVERBROAD_TEST": (
            {**sources, HW4_MEM_C5: original.replace(
                "'tests/test_hw4_mem_c5_v2.py'", "'tests/**'", 1)},
            "C5_FILTER_CONTRACT_MISMATCH"),
        "OVERBROAD_DOC": (
            {**sources, HW4_MEM_C5: original.replace(
                "'docs/HW4-MEM-C5-v2.md'", "'docs/**'", 1)},
            "C5_FILTER_CONTRACT_MISMATCH"),
        "OVERBROAD_FIRMWARE": (
            {**sources, HW4_MEM_C5: original.replace(
                "'tools/ci/hw4_mem_c5_build.sh'", "'firmware/**'", 1)},
            "C5_FILTER_CONTRACT_MISMATCH"),
        "UNLISTED_FILTER_ADDED": (
            {**sources, HW4_MEM_C5: original.replace(
                "      - 'tools/ci/hw4_mem_c5_*.py'\n",
                "      - 'tools/ci/hw4_mem_c5_*.py'\n"
                "      - 'core/**'\n", 1)},
            "C5_FILTER_CONTRACT_MISMATCH"),
        "SELF_EDIT_REMOVED": (
            {**sources, HW4_MEM_C5: original.replace(
                "'.github/workflows/hw4-mem-c5-v2.yml'",
                "'.github/workflows/ci-opt3-routing.yml'", 1)},
            "C5_FILTER_CONTRACT_MISMATCH"),
        "PR_TRIGGER_REMOVED": (
            {**sources, HW4_MEM_C5: original.replace(
                "  pull_request:\n", "", 1)},
            "PULL_REQUEST_MISSING"),
        "DISPATCH_TRIGGER_REMOVED": (
            {**sources, HW4_MEM_C5: original.replace(
                "  workflow_dispatch:\n", "", 1)},
            "C5_EVENT_CONTRACT_MISMATCH"),
        "UNAUTHORIZED_PUSH_ADDED": (
            {**sources, HW4_MEM_C5: original.replace(
                "  workflow_dispatch:\n",
                "  workflow_dispatch:\n  push:\n", 1)},
            "C5_EVENT_CONTRACT_MISMATCH"),
    }
    for label, (mutated, expected_error) in cases.items():
        demand(mutated != sources, "C5_NEGATIVE_INERT_" + label)
        try:
            audit(mutated)
        except UnsafeRoute as exc:
            demand(str(exc) == expected_error,
                   "C5_WRONG_REJECTION_" + label + ":" + str(exc))
        else:
            raise UnsafeRoute("C5_FALSIFICATION_ACCEPTED_" + label)
        print("CI-OPT3 C5_FALSIFICATION_REJECTED", label, expected_error)

    # A misclassified HW4 workflow must fail even if the count stays 38.
    original_hw4 = FAMILIES["HW4"]
    original_xtensa = FAMILIES["XTENSA"]
    try:
        FAMILIES["HW4"] = tuple(n for n in original_hw4 if n != HW4_MEM_C5)
        FAMILIES["XTENSA"] = original_xtensa + (HW4_MEM_C5,)
        try:
            audit(sources)
        except UnsafeRoute as exc:
            demand(str(exc) == "C5_WRONG_FAMILY",
                   "C5_FAMILY_WRONG_REJECTION_" + str(exc))
        else:
            raise UnsafeRoute("C5_WRONG_FAMILY_ACCEPTED")
    finally:
        FAMILIES["HW4"] = original_hw4
        FAMILIES["XTENSA"] = original_xtensa
    print("CI-OPT3 C5_WRONG_FAMILY_REJECTED")

    required_examples = (
        "tools/ci/hw4_mem_c5_v2.py",
        "tools/ci/hw4_mem_c5_build.sh",
        "tests/test_hw4_mem_c5_v2.py",
        "docs/HW4-MEM-C5-v2.md",
        ".github/workflows/hw4-mem-c5-v2.yml",
    )
    for path in required_examples:
        demand(HW4_MEM_C5 in triggered_names([path], sources),
               "C5_REQUIRED_PR_PATH_UNROUTED_" + path)
        demand("HW4" in family_routes([path], sources),
               "C5_REQUIRED_PATH_WRONG_FAMILY_" + path)
        print("CI-OPT3 C5_PR_ROUTE_VERIFIED", path)
    for path in (
        "core/basic_executor.c",
        "firmware/esp32_display_probe/main/main.c",
        "tools/ci/opt3_routing.py",
        "tools/j1_19_a_paper_oracle.py",
        "tests/fixtures/cpc6128/j1_21_a_cls/archive.json",
        "tests/oracles/hw4_esc_r1_verify.py",
        "docs/CLK-03-cpc-time-oracle.md",
        "docs/ROADMAP_GATES.md",
    ):
        demand(HW4_MEM_C5 not in triggered_names([path], sources),
               "C5_UNRELATED_PR_PATH_ROUTED_" + path)
        print("CI-OPT3 C5_UNRELATED_ROUTE_REJECTED", path)


def clk04_negative_tests(sources):
    """Isolated A1 routing: reject mutation/renaming/widening of any trigger."""
    original = sources[CLK04_WORKFLOW]
    for required in CLK04_PATHS:
        needle = "      - '" + required + "'\n"
        demand(original.count(needle) == 1, "CLK04_NEGATIVE_INERT_" + required)
        changed = {**sources, CLK04_WORKFLOW: original.replace(needle, "", 1)}
        try:
            audit(changed)
        except UnsafeRoute as exc:
            demand(str(exc) == "CLK04_FILTER_CONTRACT_MISMATCH",
                   "CLK04_REMOVAL_WRONG_REJECTION_" + required + ":" + str(exc))
        else:
            raise UnsafeRoute("CLK04_REMOVED_FILTER_ACCEPTED_" + required)
        print("CI-OPT3 CLK04_FILTER_REMOVAL_REJECTED", required)

    cases = {
        "WORKFLOW_REMOVED": (
            {k:v for k,v in sources.items() if k != CLK04_WORKFLOW},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "WORKFLOW_RENAMED": (
            {**{k:v for k,v in sources.items() if k != CLK04_WORKFLOW},
             "clk-04-unregistered.yml": original},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "UNKNOWN_WORKFLOW": (
            {**sources, "clk-04-unknown.yml": original},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "OVERBROAD_TOOL": (
            {**sources, CLK04_WORKFLOW:original.replace(
             "'tools/clk_04_real5_*'", "'tools/**'", 1)},
            "CLK04_FILTER_CONTRACT_MISMATCH"),
        "OVERBROAD_DOC": (
            {**sources, CLK04_WORKFLOW:original.replace(
             "'docs/CLK-04-A1*'", "'docs/**'", 1)},
            "CLK04_FILTER_CONTRACT_MISMATCH"),
        "OVERBROAD_FIXTURE": (
            {**sources, CLK04_WORKFLOW:original.replace(
             "'tests/fixtures/cpc6128/clk_04_real5/**'", "'tests/fixtures/**'", 1)},
            "CLK04_FILTER_CONTRACT_MISMATCH"),
        "DUPLICATE_FILTER": (
            {**sources, CLK04_WORKFLOW:original.replace(
             "      - 'tools/clk_04_real5_*'\n",
             "      - 'tools/clk_04_real5_*'\n"
             "      - 'tools/clk_04_real5_*'\n", 1)},
            "CLK04_FILTER_CONTRACT_MISMATCH"),
        "PR_REMOVED": (
            {**sources, CLK04_WORKFLOW:original.replace("  pull_request:\n","",1)},
            "PULL_REQUEST_MISSING"),
        "DISPATCH_REMOVED": (
            {**sources, CLK04_WORKFLOW:original.replace("  workflow_dispatch:\n","",1)},
            "CLK04_EVENT_CONTRACT_MISMATCH"),
        "PUSH_ADDED": (
            {**sources, CLK04_WORKFLOW:original.replace(
             "  workflow_dispatch:\n", "  workflow_dispatch:\n  push:\n",1)},
            "CLK04_EVENT_CONTRACT_MISMATCH"),
    }
    for label,(mutant,code) in cases.items():
        demand(mutant != sources, "CLK04_NEGATIVE_INERT_" + label)
        try:
            audit(mutant)
        except UnsafeRoute as exc:
            demand(str(exc) == code,
                   "CLK04_WRONG_REJECTION_" + label + ":" + str(exc))
        else:
            raise UnsafeRoute("CLK04_FALSIFICATION_ACCEPTED_" + label)
        print("CI-OPT3 CLK04_FALSIFICATION_REJECTED", label, code)

    for path in (
        ".github/workflows/clk-04-real5-oracle.yml",
        "tools/clk_04_real5_oracle.py",
        "tests/test_clk_04_real5_oracle.py",
        "tests/fixtures/cpc6128/clk_04_real5/corpus.json",
        "docs/CLK-04-A1-real5-time-oracle.md",
    ):
        demand(CLK04_WORKFLOW in triggered_names([path], sources),
               "CLK04_REQUIRED_PATH_UNROUTED_" + path)
        print("CI-OPT3 CLK04_PR_ROUTE_VERIFIED", path)
    for path in ("tools/clk_03_cpc_time.py", "core/basic_executor.c",
                 "docs/CLK-04-roadmap.md", "firmware/foo.c", "tests/test_other.py"):
        demand(CLK04_WORKFLOW not in triggered_names([path], sources),
               "CLK04_UNRELATED_PATH_TRIGGERED_" + path)
        print("CI-OPT3 CLK04_UNRELATED_ROUTE_REJECTED", path)


def c6_b2a_negative_tests(sources):
    """B2-A in-memory falsifications only. Existing gates untouched."""
    original = sources[C6_B2A_WORKFLOW]
    for path in C6_B2A_PATHS:
        needle = "      - '" + path + "'\n"
        demand(original.count(needle) == 1, "C6_B2A_NEGATIVE_INERT_" + path)
        changed = {**sources, C6_B2A_WORKFLOW: original.replace(needle, "", 1)}
        try:
            audit(changed)
        except UnsafeRoute as exc:
            demand(str(exc) == "C6_B2A_FILTER_CONTRACT_MISMATCH",
                   "C6_B2A_NEGATIVE_WRONG_REASON_" + path + ":" + str(exc))
        else:
            raise UnsafeRoute("C6_B2A_REMOVED_FILTER_ACCEPTED_" + path)
        print("CI-OPT3 C6_B2A_FILTER_REMOVAL_REJECTED", path)
    mutations = (
        ("UNKNOWN_WORKFLOW", {**sources, "unlisted.yml": original},
         "UNKNOWN_OR_MISSING_WORKFLOW"),
        ("DUPLICATE_FILTER", {**sources, C6_B2A_WORKFLOW: original.replace(
            "      - 'tools/ci/opt3_routing.py'\n",
            "      - 'tools/ci/opt3_routing.py'\n" * 2, 1)},
         "C6_B2A_FILTER_CONTRACT_MISMATCH"),
        ("BROAD_FILTER", {**sources, C6_B2A_WORKFLOW: original.replace(
            "'docs/HW4-MEM-C6-B2-A-live.md'", "'docs/**'", 1)},
         "C6_B2A_FILTER_CONTRACT_MISMATCH"),
        ("UNSAFE_EVENT", {**sources, C6_B2A_WORKFLOW: original.replace(
            "  workflow_dispatch:\n", "  push:\n    branches: [main]\n  workflow_dispatch:\n", 1)},
         "C6_B2A_EVENT_CONTRACT_MISMATCH"),
        ("PR_TARGET", {**sources, C6_B2A_WORKFLOW: original.replace(
            "  pull_request:\n", "  pull_request_target:\n", 1)},
         "PULL_REQUEST_MISSING"),
        ("WRITE_TOKEN", {**sources, C6_B2A_WORKFLOW: original.replace(
            "  contents: read", "  contents: write", 1)},
         "C6_B2A_PERMISSIONS_MISMATCH"),
        ("WRONG_SOURCE", {**sources, C6_B2A_WORKFLOW: original.replace(
            "ref: ${{ steps.pin.outputs.trusted_main_sha }}",
            "ref: ${{ github.sha }}", 1)},
         "C6_B2A_TRUST_SOURCE_MISMATCH"),
        ("FALSE_HEAD", {**sources, C6_B2A_WORKFLOW: original.replace(
            "live['head']['sha'] == os.environ['EVENT_HEAD']",
            "live['head']['sha'] != os.environ['EVENT_HEAD']", 1)},
         "C6_B2A_TRUST_SOURCE_MISMATCH"),
        ("HOST_TEST_REMOVED", {**sources, C6_B2A_WORKFLOW: original.replace(
            "-p 'test_hw4_mem_c6_refs.py' -v", "-p 'unknown.py' -v", 1)},
         "C6_B2A_HOST_TESTS_MISSING"),
        ("NO_ARTIFACT", {**sources, C6_B2A_WORKFLOW: original.replace(
            "if-no-files-found: error", "if-no-files-found: ignore", 1)},
         "C6_B2A_ARTIFACT_GUARD_MISSING"),
        ("MASKED_FAILURE", {**sources, C6_B2A_WORKFLOW: original.replace(
            "          set -euo pipefail",
            "          continue-on-error: true\n          set -euo pipefail", 1)},
         "C6_B2A_ARTIFACT_GUARD_MISSING"),
        ("FALSE_MEMORY_PASS", {**sources, C6_B2A_WORKFLOW: original.replace(
            "report['PR_INCREMENTAL_VERDICT'] == 'UNVERIFIED'",
            "report['PR_INCREMENTAL_VERDICT'] == 'PASS'", 1)},
         "C6_B2A_MEMORY_PASS_SPOOF"),
    )
    for label, changed, expected in mutations:
        demand(changed != sources, "C6_B2A_NEGATIVE_INERT_" + label)
        try:
            audit(changed)
        except UnsafeRoute as exc:
            demand(str(exc) == expected,
                   "C6_B2A_WRONG_REJECTION_" + label + ":" + str(exc))
        else:
            raise UnsafeRoute("C6_B2A_FALSIFICATION_ACCEPTED_" + label)
        print("CI-OPT3 C6_B2A_FALSIFICATION_REJECTED", label, expected)
    original_hw4, original_xtensa = FAMILIES["HW4"], FAMILIES["XTENSA"]
    try:
        FAMILIES["HW4"] = tuple(x for x in original_hw4 if x != C6_B2A_WORKFLOW)
        FAMILIES["XTENSA"] = original_xtensa + (C6_B2A_WORKFLOW,)
        try:
            audit(sources)
        except UnsafeRoute as exc:
            demand(str(exc) == "C6_B2A_WRONG_FAMILY",
                   "C6_B2A_WRONG_FAMILY_REASON_" + str(exc))
        else:
            raise UnsafeRoute("C6_B2A_WRONG_FAMILY_ACCEPTED")
    finally:
        FAMILIES["HW4"], FAMILIES["XTENSA"] = original_hw4, original_xtensa
    print("CI-OPT3 C6_B2A_WRONG_FAMILY_REJECTED")


def c6_b2b_negative_tests(sources):
    """Only mutate ephemeral workflow strings, never the old source files."""
    original = sources[C6_B2B_WORKFLOW]
    for path in C6_B2B_PATHS:
        needle = "      - '" + path + "'\n"
        demand(original.count(needle) == 1, "C6_B2B_NEGATIVE_INERT_"+path)
        broken = {**sources, C6_B2B_WORKFLOW: original.replace(needle, "", 1)}
        try:
            audit(broken)
        except UnsafeRoute as exc:
            demand(str(exc) == "C6_B2B_FILTER_CONTRACT_MISMATCH",
                   "C6_B2B_WRONG_REJECTION_"+path+":"+str(exc))
        else:
            raise UnsafeRoute("C6_B2B_MISSING_FILTER_ACCEPTED_"+path)
        print("CI-OPT3 C6_B2B_FILTER_REMOVAL_REJECTED", path)
    cases = [
        ("UNKNOWN_WORKFLOW", {**sources, "extra-xtensa.yml": original},
         "UNKNOWN_OR_MISSING_WORKFLOW"),
        ("DUPLICATE_PATH", {**sources, C6_B2B_WORKFLOW: original.replace(
         "      - 'tools/ci/opt3_routing.py'\n",
         "      - 'tools/ci/opt3_routing.py'\n"*2, 1)},
         "C6_B2B_FILTER_CONTRACT_MISMATCH"),
        ("OVERBROAD_PATH", {**sources, C6_B2B_WORKFLOW: original.replace(
         "'docs/HW4-MEM-C6-B2-B.md'", "'docs/**'", 1)},
         "C6_B2B_FILTER_CONTRACT_MISMATCH"),
        ("WRONG_EVENT", {**sources, C6_B2B_WORKFLOW: original.replace(
         "  workflow_dispatch:\n", "  push:\n    branches: [main]\n  workflow_dispatch:\n", 1)},
         "C6_B2B_EVENT_CONTRACT_MISMATCH"),
        ("PR_TARGET", {**sources, C6_B2B_WORKFLOW: original.replace(
         "  pull_request:\n", "  pull_request_target:\n", 1)},
         "PULL_REQUEST_MISSING"),
        ("WRITE_TOKEN", {**sources, C6_B2B_WORKFLOW: original.replace(
         "  contents: read", "  contents: write", 1)},
         "C6_B2B_PERMISSIONS_MISMATCH"),
        ("WRONG_HEAD", {**sources, C6_B2B_WORKFLOW: original.replace(
         "ref: $" + "{{ github.event.pull_request.head.sha || github.sha }}",
         "ref: $" + "{{ github.sha }}", 1)},
         "C6_B2B_CONTROLLER_SOURCE_MISMATCH"),
        ("MISSING_TEST", {**sources, C6_B2B_WORKFLOW: original.replace(
         "test_hw4_mem_c6_b2b.py -v", "test_missing.py -v", 1)},
         "C6_B2B_EIGHT_BUILD_NOT_GUARDED"),
        ("NO_ARTIFACT", {**sources, C6_B2B_WORKFLOW: original.replace(
         "if-no-files-found: error", "if-no-files-found: ignore", 1)},
         "C6_B2B_ARTIFACT_MISSING_OR_RC_MASKED"),
        ("HIDDEN_RC", {**sources, C6_B2B_WORKFLOW: original.replace(
         "          set -euo pipefail", "          continue-on-error: true\n          set -euo pipefail", 1)},
         "C6_B2B_ARTIFACT_MISSING_OR_RC_MASKED"),
        ("FAKE_MAIN", {**sources, C6_B2B_WORKFLOW: original.replace(
         "6d3aae8a95b97e18174d758f35ef240740e9a861", "0"*40)},
         "C6_B2B_PROVENANCE_MISMATCH"),
    ]
    for label, changed, expected in cases:
        demand(changed != sources,"C6_B2B_NEGATIVE_INERT_"+label)
        try:
            audit(changed)
        except UnsafeRoute as exc:
            demand(str(exc) == expected,
                   "C6_B2B_NEGATIVE_WRONG_REASON_"+label+":"+str(exc))
        else:
            raise UnsafeRoute("C6_B2B_FALSIFICATION_ACCEPTED_"+label)
        print("CI-OPT3 C6_B2B_FALSIFICATION_REJECTED", label, expected)
    hw4, xtensa = FAMILIES["HW4"], FAMILIES["XTENSA"]
    try:
        FAMILIES["HW4"] = tuple(n for n in hw4 if n != C6_B2B_WORKFLOW)
        FAMILIES["XTENSA"] = xtensa + (C6_B2B_WORKFLOW,)
        try:
            audit(sources)
        except UnsafeRoute as exc:
            demand(str(exc) == "C6_B2B_WRONG_FAMILY",
                   "C6_B2B_FAMILY_NEGATIVE_WRONG_REASON_"+str(exc))
        else:
            raise UnsafeRoute("C6_B2B_FAMILY_SPOOF_ACCEPTED")
    finally:
        FAMILIES["HW4"], FAMILIES["XTENSA"] = hw4, xtensa
    print("CI-OPT3 C6_B2B_WRONG_FAMILY_REJECTED")


def clk04_a2_negative_tests(sources):
    """A2: in-memory adversarial workflow inventory and exactly five PR filters."""
    original = sources[CLK04_A2_WORKFLOW]
    for required in CLK04_A2_PATHS:
        needle = "      - '" + required + "'\n"
        demand(original.count(needle)==1,"A2_NEGATIVE_INERT_"+required)
        broken={**sources, CLK04_A2_WORKFLOW:original.replace(needle,"",1)}
        try:
            audit(broken)
        except UnsafeRoute as exc:
            demand(str(exc)=="A2_FILTER_CONTRACT_MISMATCH",
                   "A2_REMOVAL_WRONG_REASON_"+str(exc))
        else:
            raise UnsafeRoute("A2_REMOVAL_ACCEPTED_"+required)
        print("CI-OPT3 A2_REQUIRED_FILTER_REMOVAL_REJECTED",required)

    changes={
        "WORKFLOW_DELETED":(
            {k:v for k,v in sources.items() if k!=CLK04_A2_WORKFLOW},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "WORKFLOW_RENAMED":(
            {**{k:v for k,v in sources.items() if k!=CLK04_A2_WORKFLOW},
             "clk-04-a2-unregistered.yml":original},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "WORKFLOW_UNLISTED":(
            {**sources, "unknown-a2.yml":original},
            "UNKNOWN_OR_MISSING_WORKFLOW"),
        "DUPLICATE_FILTER":(
            {**sources, CLK04_A2_WORKFLOW:original.replace(
                "      - 'tools/clk_04_a2_*'\n",
                "      - 'tools/clk_04_a2_*'\n"
                "      - 'tools/clk_04_a2_*'\n",1)},
            "A2_FILTER_CONTRACT_MISMATCH"),
        "TOOL_TOO_BROAD":(
            {**sources, CLK04_A2_WORKFLOW:original.replace(
                "'tools/clk_04_a2_*'","'tools/**'",1)},
            "A2_FILTER_CONTRACT_MISMATCH"),
        "FIXTURE_TOO_BROAD":(
            {**sources, CLK04_A2_WORKFLOW:original.replace(
                "'tests/fixtures/cpc6128/clk_04_a2_numeric/**'",
                "'tests/fixtures/**'",1)},
            "A2_FILTER_CONTRACT_MISMATCH"),
        "DOC_TOO_BROAD":(
            {**sources, CLK04_A2_WORKFLOW:original.replace(
                "'docs/CLK-04-A2*'","'docs/**'",1)},
            "A2_FILTER_CONTRACT_MISMATCH"),
        "PR_REMOVED":(
            {**sources, CLK04_A2_WORKFLOW:original.replace(
                "  pull_request:\n","",1)},
            "PULL_REQUEST_MISSING"),
        "DISPATCH_REMOVED":(
            {**sources, CLK04_A2_WORKFLOW:original.replace(
                "  workflow_dispatch:\n","",1)},
            "A2_EVENT_CONTRACT_MISMATCH"),
        "PUSH_ADDED":(
            {**sources, CLK04_A2_WORKFLOW:original.replace(
                "  workflow_dispatch:\n","  workflow_dispatch:\n  push:\n",1)},
            "A2_EVENT_CONTRACT_MISMATCH"),
    }
    for label,(mutant,code) in changes.items():
        demand(mutant!=sources,"A2_NEGATIVE_INERT_"+label)
        try:
            audit(mutant)
        except UnsafeRoute as exc:
            demand(str(exc)==code,"A2_WRONG_REJECTION_"+label+":"+str(exc))
        else:
            raise UnsafeRoute("A2_FALSIFICATION_ACCEPTED_"+label)
        print("CI-OPT3 A2_FALSIFICATION_REJECTED",label,code)

    orig_cpc=FAMILIES["CPC_ACQUISITION"]
    orig_xtensa=FAMILIES["XTENSA"]
    try:
        FAMILIES["CPC_ACQUISITION"]=tuple(
            x for x in orig_cpc if x!=CLK04_A2_WORKFLOW)
        FAMILIES["XTENSA"]=orig_xtensa+(CLK04_A2_WORKFLOW,)
        try:
            audit(sources)
        except UnsafeRoute as exc:
            demand(str(exc)=="A2_WRONG_FAMILY",
                   "A2_WRONG_FAMILY_REJECTION_"+str(exc))
        else:
            raise UnsafeRoute("A2_MISCLASSIFIED_ACCEPTED")
    finally:
        FAMILIES["CPC_ACQUISITION"]=orig_cpc
        FAMILIES["XTENSA"]=orig_xtensa
    print("CI-OPT3 A2_WRONG_FAMILY_REJECTED")

    for path in (
        ".github/workflows/clk-04-a2-numeric-oracle.yml",
        "tools/clk_04_a2_numeric.py",
        "tests/test_clk_04_a2_numeric.py",
        "tests/fixtures/cpc6128/clk_04_a2_numeric/corpus.json",
        "docs/CLK-04-A2-numeric-real5.md"):
        demand(CLK04_A2_WORKFLOW in triggered_names([path],sources),
               "A2_REQUIRED_ROUTE_MISSING_"+path)
        demand("CPC_ACQUISITION" in family_routes([path],sources),
               "A2_WRONG_FAMILY_ROUTE_"+path)
        print("CI-OPT3 A2_PR_ROUTE_VERIFIED",path)
    for path in ("tools/clk_04_real5_oracle.py", "core/basic_executor.c",
                 "firmware/esp32_display_probe/main/main.c",
                 "docs/CLK-04-A1-real5-time-oracle.md",
                 "tools/ci/hw4_mem_c6_refs.py"):
        demand(CLK04_A2_WORKFLOW not in triggered_names([path],sources),
               "A2_UNRELATED_ROUTE_"+path)


def c6_d1_negative_tests(sources):
    """Only falsify in-memory workflow text; never alter historical gates."""
    original = sources[C6_D1_WORKFLOW]
    for path in C6_D1_PATHS:
        needle = "      - '" + path + "'\n"
        demand(original.count(needle) == 1, "C6_D1_NEGATIVE_INERT_PATH")
        broken = {**sources, C6_D1_WORKFLOW: original.replace(needle, "", 1)}
        try:
            audit(broken)
        except UnsafeRoute as exc:
            demand(str(exc) == "C6_D1_FILTER_CONTRACT_MISMATCH",
                   "C6_D1_WRONG_PATH_REASON:" + str(exc))
        else:
            raise UnsafeRoute("C6_D1_MISSING_PATH_ACCEPTED")
        print("CI-OPT3 C6_D1_PATH_REMOVAL_REJECTED", path)
    mutations = (
        ("UNKNOWN_WORKFLOW", {**sources, "extra-prelink.yml": original},
         "UNKNOWN_OR_MISSING_WORKFLOW"),
        ("DUPLICATE_PATH", {**sources, C6_D1_WORKFLOW: original.replace(
             "      - 'tools/ci/opt3_routing.py'\n",
             "      - 'tools/ci/opt3_routing.py'\n"*2,1)},
         "C6_D1_FILTER_CONTRACT_MISMATCH"),
        ("WIDE_PATH", {**sources, C6_D1_WORKFLOW: original.replace(
             "'docs/HW4-MEM-C6-B2-D1.md'", "'docs/**'",1)},
         "C6_D1_FILTER_CONTRACT_MISMATCH"),
        ("PUSH_EVENT", {**sources, C6_D1_WORKFLOW: original.replace(
             "  workflow_dispatch:\n",
             "  push:\n    branches: [main]\n  workflow_dispatch:\n",1)},
         "C6_D1_EVENTS_MISMATCH"),
        ("PR_TARGET", {**sources, C6_D1_WORKFLOW: original.replace(
             "  pull_request:\n", "  pull_request_target:\n",1)},
         "PULL_REQUEST_MISSING"),
        ("WRITE_TOKEN", {**sources, C6_D1_WORKFLOW: original.replace(
             "  contents: read", "  contents: write",1)},
         "C6_D1_PERMISSIONS_MISMATCH"),
        ("BAD_HEAD", {**sources, C6_D1_WORKFLOW: original.replace(
             "ref: $"+"{{ github.event.pull_request.head.sha || github.sha }}",
             "ref: $"+"{{ github.sha }}",1)},
         "C6_D1_CONTROLLER_TRUST_MISMATCH"),
        ("BAD_CONCURRENCY", {**sources, C6_D1_WORKFLOW: original.replace(
             "cancel-in-progress: false", "cancel-in-progress: true",1)},
         "C6_D1_CONTROLLER_TRUST_MISMATCH"),
        ("MISSING_TEST", {**sources, C6_D1_WORKFLOW: original.replace(
             "-p test_hw4_mem_c6_b2_d1.py -v",
             "-p test_not_there.py -v",1)},
         "C6_D1_SOURCE_AND_OLD_ARTIFACT_MISMATCH"),
        ("OLD_ARTIFACT_SPOOF", {**sources, C6_D1_WORKFLOW: original.replace(
             "42660089530", "12345678900",1)},
         "C6_D1_SOURCE_AND_OLD_ARTIFACT_MISMATCH"),
        ("NO_EVIDENCE", {**sources, C6_D1_WORKFLOW: original.replace(
             "if-no-files-found: error", "if-no-files-found: ignore",1)},
         "C6_D1_MASKED_FAILURE_OR_NO_ARTIFACT"),
        ("MASKED_RC", {**sources, C6_D1_WORKFLOW: original.replace(
             "          set -euo pipefail",
             "          continue-on-error: true\n          set -euo pipefail",1)},
         "C6_D1_MASKED_FAILURE_OR_NO_ARTIFACT"),
    )
    for label, changed, expected in mutations:
        demand(changed != sources, "C6_D1_NEGATIVE_INERT:"+label)
        try:
            audit(changed)
        except UnsafeRoute as exc:
            demand(str(exc) == expected,
                   "C6_D1_WRONG_REJECTION_"+label+":"+str(exc))
        else:
            raise UnsafeRoute("C6_D1_FALSIFICATION_ACCEPTED_"+label)
        print("CI-OPT3 C6_D1_NEGATIVE_REJECTED", label, expected)
    hw4, xtensa = FAMILIES["HW4"], FAMILIES["XTENSA"]
    try:
        FAMILIES["HW4"] = tuple(x for x in hw4 if x != C6_D1_WORKFLOW)
        FAMILIES["XTENSA"] = xtensa + (C6_D1_WORKFLOW,)
        try:
            audit(sources)
        except UnsafeRoute as exc:
            demand(str(exc) == "C6_D1_WRONG_FAMILY",
                   "C6_D1_WRONG_FAMILY_REASON:"+str(exc))
        else:
            raise UnsafeRoute("C6_D1_WRONG_FAMILY_ACCEPTED")
    finally:
        FAMILIES["HW4"], FAMILIES["XTENSA"] = hw4, xtensa
    print("CI-OPT3 C6_D1_WRONG_FAMILY_REJECTED")


def negative_tests(sources):
    c6_d1_negative_tests(sources)
    c6_b2b_negative_tests(sources)
    c6_b2a_negative_tests(sources)
    clk04_a2_negative_tests(sources)
    clk04_negative_tests(sources)
    c5_negative_tests(sources)
    clk03_negative_tests(sources)
    clk01_negative_tests(sources)
    r1_negative_tests(sources)
    cls_route_negative_tests(sources)
    cls_permanent_negative_tests(sources)
    j122_permanent_negative_tests(sources)
    paper_negative_tests(sources)
    paper_permanent_negative_tests(sources)
    paper_archive_negative_tests()
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
    c3_missing_filter = sources[HW4_C3].replace(
        "      - 'tools/ci/hw4_disp_spi_*.py'\n", "")
    demand(c3_missing_filter != sources[HW4_C3],
           "C3_FILTER_NEGATIVE_INERT")
    altered = {
        "C3_FILTER_REMOVED": ({**sources, HW4_C3: c3_missing_filter},
                              "HW4_C3_FILTER_CONTRACT_MISMATCH"),
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
            elif path == CLS_TOOL:
                audit_cls_route(sources)
                demand(PAPER_WORKFLOW in triggered_names([path], sources),
                       "CLS_WORKFLOW_UNROUTED")
            elif path == J122_TOOL:
                audit_j122_permanent(sources)
                demand(PAPER_WORKFLOW in triggered_names([path], sources),
                       "J122_WORKFLOW_UNROUTED")
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
    print("CI-OPT3 ROUTE_GATE_PASS WORKFLOWS=43 FAMILIES=5")


if __name__ == "__main__":
    try:
        main()
    except (UnsafeRoute, OSError, subprocess.CalledProcessError) as e:
        print("CI-OPT3 FAIL", e, file=sys.stderr)
        sys.exit(1)
