#!/usr/bin/env python3
"""HW4-MEM-C7 v2: additive, fail-closed, PR-anchored memory comparison.

Not a replacement for RENDER-A, SPI-C3 or A0 historical required checks.
Return codes: 0 = valid incremental/parity evidence, 1 = regression/parity
failure, 2 = invalid/missing/provenance evidence. Historical failures are
reported independently and NEVER promoted by return code 0.
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

from hw4_a0_compare_memory import checked_sha, read_size
from hw4_a0_provenance import validate_pr
from verify_esp_app_version import boot_version

VERSION = "HW4-MEM-C7/v2"
A0 = "5799c774a3a5b3d453c17012a2328b379bd587bd"
RENDER_A = "21e95a7197413923bb5976067a0419bc729c20c1"
B3 = "989ec54989537a31c3a9be8074f1ce7c47708f17"
IMAGE = "espressif/idf@sha256:bf72fe7a15c22849a9a94147301165a545fb8905d97c176cf748e3e4614cac84"
ANCHORS = {"A0": A0, "RENDER_A": RENDER_A, "B3": B3}
EXPECTED = {"A0": {"iram": 67331, "dram": 53728},
            "RENDER_A": {"iram": 67331, "dram": 54864},
            "B3": {"iram": 67331, "dram": 54168}}
FILES = ("sections.txt", "firmware.elf", "firmware.bin", "CMakeCache.txt",
         "compile_commands.json", "sdkconfig", "idf-version.txt",
         "gcc-version.txt", "ld-version.txt")
CLOCKS = {"spi40": 40000000, "spi20": 20000000}

# C7-C1 #388: closed Git-object ledger of the *only* approved growth.
# Later #387 HEAD must be an ancestor-preserving integration of main and
# have the same exact base-to-head patch as the original reviewed B1.
ESC_B1_REPO = "Kharn27/ESP32-Locomotive-Basic"
ESC_B1_PR = 387
ESC_B1_ISSUE = 385
ESC_B1_BRANCH = "feat/hw4-esc-break-b1-console"
ESC_B1_SOURCE_BASE = "3f84b119c404b95f72eab3b7dd6f3034bfc7c959"
ESC_B1_SOURCE_HEAD = "010e2d1d14941e4e09c097c8599b5cf4d0527f2f"
ESC_B1_PATHS = frozenset({
    "CMakeLists.txt",
    "docs/HW4-ESC-BREAK-B1-cyd.md",
    "firmware/esp32_display_probe/main/CMakeLists.txt",
    "firmware/esp32_display_probe/main/hw4_c2_console.c",
    "integration/hw4_cpc_escape_contract.c",
    "integration/hw4_cpc_escape_contract.h",
    "integration/hw4_run_scheduler.c",
    "integration/hw4_run_scheduler.h",
    "tests/test_hw4_cpc_escape_contract.c",
    "tests/test_hw4_run_break_b.c",
})
# B1-C7-C2 #385: immutable PO-host runner; CI-only changes are a closed
# path list, never a blanket tools/** exemption. The PO-tested firmware commit
# remains an ancestor; its runner blob must survive byte-for-byte.
ESC_B1_PO_HEAD = "5e44ca338e91283484b2ac41c46a7fcc3b2b0a10"
ESC_B1_HOST_BLOBS = {
    # Physical PO campaign 17/11: immutable original host script
    "tools/hw4_esc_b1_po_auto.py": "c14f2772dee0ba1b303098b4d97c18d717e12736",
}
ESC_B1_C1_HEAD = "8d2aa707598a0f3f82c0b4bfcd6467879c9238bc"
ESC_B1_VISUAL_HOST_BLOBS = {
    # B1-PO-VISUAL-C1: runner at the PO-tested C1 commit
    "tools/hw4_esc_b1_po_auto.py": "f26a2dcd39e299f745be7ce339f9eab2d77458a2",
}
ESC_B1_COUNTER_HOST_BLOBS = {
    # B1-PO-VISUAL-C2: opt-in monotonic counter runner at the live PR HEAD
    "tools/hw4_esc_b1_po_auto.py": "6bbbca0f144f44bcb46dda8f23177104801b9fda",
}
ESC_B1_CI_PATHS = frozenset({
    "tools/ci/hw4_mem_c7_v2.py",
    "tests/test_hw4_mem_c7.py",
})
ESC_B1_LIMIT = {"iram": 0, "dram": 40, "bss": 40}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def require(ok, what):
    if not ok:
        raise ValueError("MEASUREMENT_INVALID: " + what)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(value, dict), "JSON object expected at " + str(path))
    return value


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args],
                                   text=True, stderr=subprocess.PIPE).strip()


def stable_pr_identity(live):
    """Pin mutable PR refs, not volatile GitHub repository snapshots.

    GitHub includes repo counters/timestamps inside base/head; those may change
    while the five real builds run, without a PR ref/branch/owner transition.
    The branch, source repository, SHA and PR state still fail closed.
    """
    require(isinstance(live, dict), "GitHub PR payload missing")
    parts = [live.get("number"), live.get("state"), live.get("draft"),
             live.get("merged")]
    for side in ("base", "head"):
        ref = live.get(side)
        require(isinstance(ref, dict), "GitHub PR " + side + " missing")
        repo = ref.get("repo")
        require(isinstance(repo, dict), "GitHub PR " + side + " repository missing")
        sha, branch, owner = ref.get("sha"), ref.get("ref"), repo.get("full_name")
        checked_sha(sha)
        require(isinstance(branch, str) and bool(branch) and
                isinstance(owner, str) and bool(owner),
                "GitHub PR " + side + " identity incomplete")
        parts.extend((sha, branch, owner))
    return tuple(parts)


def verify_provenance(provenance, live, repo, pr_number, base_checkout, head_checkout):
    require(provenance.get("status") == "PROVENANCE_PASS", "missing successful Git provenance")
    require(provenance.get("repo") == repo and provenance.get("pr_number") == pr_number,
            "PR identity mismatch")
    base, head = provenance.get("base_sha"), provenance.get("head_sha")
    checked_sha(base)
    checked_sha(head)
    require(base != head, "same base and head")
    require(provenance.get("anchors") == ANCHORS, "immutable historical anchors substituted")
    require(provenance.get("historical_bytes") == EXPECTED,
            "historical reference measurements substituted")
    validate_pr(live, repo, pr_number, base, head)
    mb = checked_sha(provenance.get("merge_base", ""))
    # Provenance producer verifies the actual Git graph; compare to the frozen
    # output and require real source trees for both inputs.
    for label in ("base", "head"):
        checked_sha(provenance.get(label + "_tree", ""))
    require(provenance.get("policy_main") == base and mb == base and
            provenance.get("diverged_from_base") is False,
            "PR diverged from live main; STOP")
    require(provenance.get("ancestry_verified") is True and mb != head,
            "merge-base graph or ancestry check missing")
    # Re-check Git objects and the actual merge-base independently of the
    # provenance producer. JSON-only evidence is never authoritative.
    for label, folder, sha in (("base", base_checkout, base),
                               ("head", head_checkout, head)):
        require(git(folder, "rev-parse", "HEAD") == sha, "checkout SHA changed: " + label)
        require(git(folder, "cat-file", "-t", sha) == "commit",
                "commit object not found: " + label)
        require(git(folder, "rev-parse", "HEAD^{tree}") ==
                provenance[label + "_tree"], "checkout tree changed: " + label)
    require(git(head_checkout, "merge-base", base, head) == mb,
            "merge-base substituted")
    for sha in (base, head):
        rc = subprocess.run(["git", "-C", str(head_checkout), "merge-base",
                             "--is-ancestor", mb, sha], capture_output=True)
        require(rc.returncode == 0, "corrupted Git graph")
    return base, head


def authorize_esc_b1(provenance, live, repo, pr_number, head_checkout):
    """Allocate ONLY after GitHub PR and original B1 Git patch are verified.

    verify_provenance() must have already proven the live API response,
    current main/head checkouts, SHA/tree integrity and merge-base.
    """
    if pr_number != ESC_B1_PR:
        return None
    require(repo == ESC_B1_REPO and provenance.get("repo") == repo and
            provenance.get("pr_number") == ESC_B1_PR,
            "ESC allocation wrong repository or PR")
    require(live.get("number") == ESC_B1_PR and live.get("state") == "open" and
            live.get("head", {}).get("sha") == provenance.get("head_sha") and
            live.get("base", {}).get("sha") == provenance.get("base_sha"),
            "ESC allocation stale or falsified live PR")
    require(live.get("head", {}).get("repo", {}).get("full_name") == repo and
            live.get("head", {}).get("ref") == ESC_B1_BRANCH and
            live.get("base", {}).get("repo", {}).get("full_name") == repo and
            live.get("base", {}).get("ref") == "main",
            "ESC allocation fork or unapproved PR branch")
    require("#385" in live.get("title", "") or
            "Refs #385" in (live.get("body") or ""),
            "ESC allocation original issue missing")
    base, head = provenance["base_sha"], provenance["head_sha"]
    checked_sha(base)
    checked_sha(head)
    require(base != head, "ESC allocation empty PR diff")
    for original in (ESC_B1_SOURCE_BASE, ESC_B1_SOURCE_HEAD, ESC_B1_PO_HEAD,
                     ESC_B1_C1_HEAD):
        require(git(head_checkout, "cat-file", "-t", original) == "commit",
                "ESC approved original/PO commit missing")
    for before, after in ((ESC_B1_SOURCE_BASE, ESC_B1_SOURCE_HEAD),
                          (ESC_B1_SOURCE_HEAD, ESC_B1_PO_HEAD),
                          (ESC_B1_PO_HEAD, ESC_B1_C1_HEAD),
                           (ESC_B1_C1_HEAD, head)):
        rc = subprocess.run(["git", "-C", str(head_checkout), "merge-base",
                             "--is-ancestor", before, after],
                            capture_output=True)
        require(rc.returncode == 0,
                "ESC original B1/PO commit is not in the real Git ancestry")

    original_paths = frozenset(git(head_checkout, "diff", "--name-only",
                                   "--no-renames", ESC_B1_SOURCE_BASE,
                                   ESC_B1_SOURCE_HEAD).splitlines())
    current_paths = frozenset(git(head_checkout, "diff", "--name-only",
                                  "--no-renames", base, head).splitlines())
    expected = ESC_B1_PATHS | frozenset(ESC_B1_HOST_BLOBS) | ESC_B1_CI_PATHS
    require(original_paths == ESC_B1_PATHS and current_paths == expected,
            "ESC B1/host/CI closed file diff mismatch")

    # Compare precisely the ten source-file patches, excluding only explicitly
    # inventoried host-only files. The old B1 patch must remain byte-identical.
    opts = ("diff", "--binary", "--no-ext-diff", "--no-renames")
    b1_paths = tuple(sorted(ESC_B1_PATHS))
    original = git(head_checkout, *opts, ESC_B1_SOURCE_BASE,
                   ESC_B1_SOURCE_HEAD, "--", *b1_paths)
    current = git(head_checkout, *opts, base, head, "--", *b1_paths)
    require(original and current == original, "ESC B1 approved patch changed")
    for path in b1_paths:
        source = git(head_checkout, "ls-tree", ESC_B1_SOURCE_HEAD, "--", path)
        actual = git(head_checkout, "ls-tree", head, "--", path)
        require(source.startswith("100644 blob ") and actual == source,
                "ESC B1 source blob/mode changed: " + path)

    # Three sealed Git-object identities: PO original, C1 and current C2.
    require(set(ESC_B1_VISUAL_HOST_BLOBS) == set(ESC_B1_HOST_BLOBS) ==
            set(ESC_B1_COUNTER_HOST_BLOBS),
            "ESC runner inventory differs")
    for path, historical_sha in ESC_B1_HOST_BLOBS.items():
        original_entry = "100644 blob " + historical_sha + "\t" + path
        visual_entry = ("100644 blob " + ESC_B1_VISUAL_HOST_BLOBS[path] +
                        "\t" + path)
        require(not git(head_checkout, "ls-tree", base, "--", path),
                "ESC PO host runner unexpectedly exists in main: " + path)
        require(git(head_checkout, "ls-tree", ESC_B1_PO_HEAD, "--", path) ==
                original_entry, "ESC PO historical host runner blob/mode changed: " + path)
        counter_entry = ("100644 blob " + ESC_B1_COUNTER_HOST_BLOBS[path] +
                         "\t" + path)
        require(git(head_checkout, "ls-tree", ESC_B1_C1_HEAD, "--", path) ==
                visual_entry, "ESC C1 historical host runner blob/mode changed: " + path)
        require(git(head_checkout, "ls-tree", head, "--", path) == counter_entry,
                "ESC C2 counter host runner blob/mode changed: " + path)

    # The two C7 policy/test files are the *only* permitted extra changes.
    # Both must be real modifications of existing 100644 blobs on main.
    for path in sorted(ESC_B1_CI_PATHS):
        before = git(head_checkout, "ls-tree", base, "--", path)
        after = git(head_checkout, "ls-tree", head, "--", path)
        require(before.startswith("100644 blob ") and
                after.startswith("100644 blob ") and before != after,
                "ESC C7-only policy/test blob invalid: " + path)
    return {"status": "AUTHORIZED_ESC_B1_DRAM_BSS_40",
            "issue": ESC_B1_ISSUE, "pr_number": ESC_B1_PR,
            "source_base": ESC_B1_SOURCE_BASE,
            "source_head": ESC_B1_SOURCE_HEAD,
            "po_source_head": ESC_B1_PO_HEAD,
            "host_blobs": dict(ESC_B1_HOST_BLOBS),
            "visual_host_blobs": dict(ESC_B1_VISUAL_HOST_BLOBS),
            "c1_source_head": ESC_B1_C1_HEAD,
            "counter_host_blobs": dict(ESC_B1_COUNTER_HOST_BLOBS),
            "ci_paths": sorted(ESC_B1_CI_PATHS),
            "patch_sha256": digest(original.encode("utf-8")),
            "limit": dict(ESC_B1_LIMIT)}


def checked_binary(path, expected_sha, prefix):
    data = path.read_bytes()
    require(data, "missing " + str(path))
    require(digest(data) == expected_sha, "digest mismatch for " + str(path))
    if path.name == "firmware.elf":
        require(len(data) >= 52 and data[:6] == b"\x7fELF\x01\x01" and
                struct.unpack_from("<H", data, 18)[0] == 94,
                "not a 32-bit Xtensa ELF")
    if path.name == "firmware.bin":
        require(boot_version(data, "loco_esp32_display_probe").startswith(prefix[:7]),
                "firmware BIN embedded app SHA differs from Git checkout")
    return data


def hal_clock(commands, hz):
    require(isinstance(commands, list), "compile commands must be list")
    hal = [c for c in commands if c.get("file", "").endswith("/cyd_ili9341.c")]
    require(len(hal) == 1, "HAL command missing/ambiguous")
    c = hal[0]
    argv = c.get("arguments") or c.get("command", "").split()
    require(isinstance(argv, list) and "-DLCD_CLOCK_HZ=" + str(hz) + "U" in argv,
            "HAL compiled for wrong or missing LCD_CLOCK_HZ")


def build_metrics(root, label, variant, sha, tree):
    folder = root / label / variant
    meta = read_json(folder / "source.json")
    require(meta.get("source_sha") == sha and meta.get("source_tree") == tree,
            "artifact source SHA/tree mismatch: " + label + "/" + variant)
    require(meta.get("source_label") == label and meta.get("variant") == variant,
            "artifact label mismatch")
    hz = CLOCKS[variant]
    require(meta.get("clock_hz") == hz and meta.get("profile") == "CONSOLE",
            "profile/clock differs")
    require(meta.get("container_image") == IMAGE, "Docker image digest mismatch")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", meta.get("docker_image_id", "")) is not None,
            "Docker image ID missing")
    require(meta.get("app_source_sha") == sha, "app SHA provenance mismatch")
    declared = meta.get("digests")
    require(isinstance(declared, dict) and set(declared) == set(FILES),
            "incomplete artifact digests")
    data = {}
    for fname in FILES:
        expected = declared.get(fname)
        require(isinstance(expected, str) and SHA256.fullmatch(expected),
                "invalid artifact digest: " + fname)
        data[fname] = checked_binary(folder / fname, expected, sha)
    idf = data["idf-version.txt"].decode().strip()
    gcc = data["gcc-version.txt"].decode().strip().splitlines()[0]
    ld = data["ld-version.txt"].decode().strip().splitlines()[0]
    require(idf == "ESP-IDF v5.5.6", "ESP-IDF version differs")
    require("14.2.0" in gcc and "2.43.1" in ld, "GCC/ld versions differ")
    cache = data["CMakeCache.txt"].decode()
    require(re.search(r"^LOCO_CYD_PROFILE:STRING=CONSOLE$", cache, re.M) is not None,
            "LOCO_CYD_PROFILE incorrect")
    require(re.search(r"^CYD_LCD_SPI_HZ:STRING=" + str(hz) + r"$", cache, re.M) is not None,
            "CYD_LCD_SPI_HZ incorrect")
    hal_clock(json.loads(data["compile_commands.json"]), hz)
    require(re.search(r"^CYD_LCD_SPI20_OPT_IN:BOOL=" +
                      ("OFF" if variant == "spi40" else "ON") + r"$",
                      cache, re.M) is not None, "explicit SPI20 opt-in cache mismatch")
    sections = read_size(folder / "sections.txt")
    data_sections = re.findall(
        r"^\s*\.dram0\.data\s+(\d+)\s+(?:0x[0-9A-Fa-f]+|\d+)\s*$",
        data["sections.txt"].decode("utf-8"), re.M)
    require(len(data_sections) == 1 and int(data_sections[0]) > 0,
            "missing/ambiguous .dram0.data section")
    require(sections["iram"] > 0 and sections["dram"] > 0 and
            sections["bss"] > 0 and sections["dram"] >= sections["bss"],
            "invalid sections or BSS")
    require(meta.get("sdkconfig_sha256") == digest(data["sdkconfig"]),
            "sdkconfig digest incorrect")
    return {"iram": sections["iram"], "dram": sections["dram"], "bss": sections["bss"],
            "dram_data": int(data_sections[0]),
            "flash_text": sections["flash_text"], "flash_rodata": sections["flash_rodata"],
            "bin_sha256": digest(data["firmware.bin"]), "sdkconfig": digest(data["sdkconfig"]),
            "gcc": gcc, "ld": ld, "idf": idf, "docker_image_id": meta["docker_image_id"],
            "elf_sha256": digest(data["firmware.elf"])}


def status_hist(memory, anchor, variant):
    limit = EXPECTED[anchor]
    bad = memory["iram"] > limit["iram"] or memory["dram"] > (
        54864 if anchor == "B3" else limit["dram"])
    if anchor == "B3":
        cost = memory["dram"] - limit["dram"]
        bad = bad or not 0 <= cost <= 696 or memory["iram"] != 67331
    return {"status": "HISTORICAL_FAILURE" if bad else "HISTORICAL_PASS",
            "anchor_sha": ANCHORS[anchor], "anchor_iram": limit["iram"],
            "anchor_dram": limit["dram"], "delta_iram": memory["iram"] - limit["iram"],
            "delta_dram": memory["dram"] - limit["dram"],
            "variant": variant}


def judge(base, head, limit=None):
    limits = limit if limit is not None else {"iram": 0, "dram": 0, "bss": 0}
    require(set(limits) == {"iram", "dram", "bss"} and
            all(type(limits[k]) is int and
                0 <= limits[k] <= ESC_B1_LIMIT[k] for k in limits),
            "invalid RAM allocation ledger")
    delta = {k: head[k] - base[k] for k in ("iram", "dram", "bss")}
    return {"status": "INCREMENTAL_PASS" if all(
                delta[k] <= limits[k] for k in delta)
            else "INCREMENTAL_FAIL", **delta}


def evaluate(memory, provenance, allocation=None):
    if allocation is not None:
        require(allocation.get("status") == "AUTHORIZED_ESC_B1_DRAM_BSS_40" and
                allocation.get("pr_number") == ESC_B1_PR and
                allocation.get("issue") == ESC_B1_ISSUE and
                allocation.get("source_base") == ESC_B1_SOURCE_BASE and
                allocation.get("source_head") == ESC_B1_SOURCE_HEAD and
                allocation.get("po_source_head") == ESC_B1_PO_HEAD and
                allocation.get("host_blobs") == ESC_B1_HOST_BLOBS and
                allocation.get("visual_host_blobs") == ESC_B1_VISUAL_HOST_BLOBS and
                allocation.get("c1_source_head") == ESC_B1_C1_HEAD and
                allocation.get("counter_host_blobs") == ESC_B1_COUNTER_HOST_BLOBS and
                allocation.get("ci_paths") == sorted(ESC_B1_CI_PATHS) and
                allocation.get("limit") == ESC_B1_LIMIT,
                "ESC B1 allocation ledger changed")
    base40, head40 = memory["base"]["spi40"], memory["head"]["spi40"]
    require(len({m["docker_image_id"] for label in memory for m in memory[label].values()}) == 1,
            "Docker image ID differs across real builds")
    require(len({(m["gcc"], m["ld"], m["idf"]) for label in memory
                 for m in memory[label].values()}) == 1,
            "toolchain differs across real builds")
    # A configuration drift between input pair invalidates all deltas.
    for variant in CLOCKS:
        b, h = memory["base"][variant], memory["head"][variant]
        require((b["sdkconfig"], b["gcc"], b["ld"], b["idf"], b["docker_image_id"]) ==
                (h["sdkconfig"], h["gcc"], h["ld"], h["idf"], h["docker_image_id"]),
                "base/head build settings or toolchain differ: " + variant)
    limit = allocation["limit"] if allocation is not None else None
    r = {
        "contract": VERSION, "provenance": provenance, "anchors": ANCHORS,
        "allocation": allocation or {"status": "NO_ALLOCATION", "limit": {"iram": 0, "dram": 0, "bss": 0}},
        "historical_c3_dram_cap": 54864, "historical_b3_dram_cost_cap": 696,
        "render_a": {"historical": {label: status_hist(memory[label]["spi40"],
                                                       "RENDER_A", "spi40")
                                    for label in ("base", "head")},
                     "incremental": judge(base40, head40, limit)},
        "spi_c3": {"historical": {label: {v: status_hist(memory[label][v], "B3", v)
                                             for v in CLOCKS}
                                  for label in ("base", "head")},
                   "incremental": {v: judge(memory["base"][v], memory["head"][v], limit)
                                   for v in CLOCKS},
                   "variants": {"status": "SPI_VARIANTS_PARITY_UNVERIFIED"}},
        "measured": {label: {v: {k: m[k] for k in
                      ("iram", "dram", "bss", "dram_data", "flash_text", "flash_rodata", "bin_sha256")}
                      for v, m in variants.items()} for label, variants in memory.items()}
    }
    # Mandatory historical debt is visible, never converted to PASS by v2's
    # independent incremental success. An anchor measuring true PASS is allowed.
    hist = [r["render_a"]["historical"][l]["status"] for l in ("base", "head")]
    hist += [r["spi_c3"]["historical"][l][v]["status"]
             for l in ("base", "head") for v in CLOCKS]
    r["historical_debt"] = "HISTORICAL_DEBT" if "HISTORICAL_FAILURE" in hist else "NONE"
    faults = []
    for label in ("base", "head"):
        a, b = memory[label]["spi40"], memory[label]["spi20"]
        if (a["iram"], a["dram"], a["bss"], a["dram_data"]) != (
                b["iram"], b["dram"], b["bss"], b["dram_data"]):
            faults.append(label + " SPI40/SPI20 IRAM/DRAM/BSS/data disparity")
        if a["bin_sha256"] == b["bin_sha256"]:
            faults.append(label + " SPI40/SPI20 identical BIN")
        if a["sdkconfig"] != b["sdkconfig"]:
            faults.append(label + " SPI40/SPI20 SDKCONFIG differs")
    # 54864 and B3 696 are historical failures via status_hist(), not a
    # perpetual current-main ceiling after the approved ESC B1 integration.
    if allocation is not None:
        for v in CLOCKS:
            b, h = memory["base"][v], memory["head"][v]
            if h["dram_data"] != b["dram_data"]:
                faults.append(v + " ESC allocation changed .dram0.data")
            if h["dram"] - b["dram"] != h["bss"] - b["bss"]:
                faults.append(v + " ESC allocation growth outside BSS")
    r["spi_c3"]["variants"] = {
        "status": "SPI_VARIANTS_PARITY_FAIL" if faults else "SPI_VARIANTS_PARITY_PASS",
        "faults": faults}
    inc = [r["render_a"]["incremental"]["status"]]
    inc.extend(r["spi_c3"]["incremental"][v]["status"] for v in CLOCKS)
    r["status"] = ("INCREMENTAL_FAIL" if "INCREMENTAL_FAIL" in inc or faults
                   else "INCREMENTAL_PASS")
    return r


def markdown(report):
    if report.get("status") == "MEASUREMENT_INVALID":
        return "# HW4-MEM-C7 v2 — MEASUREMENT_INVALID\n\n" + report["error"] + "\n"
    p = report["provenance"]
    lines = ["# HW4-MEM-C7 — authoritative incremental gate",
             "", "PR #" + str(p["pr_number"]) + " GitHub real base " + p["base_sha"] +
             " → HEAD " + p["head_sha"], "Merge-base: " + p["merge_base"],
             "Historical debt: **" + report["historical_debt"] + "**",
             "Allocation: **" + report["allocation"]["status"] + "** " +
             str(report["allocation"]["limit"]) +
             " (issue #385 / PR #387 only; not inherited by later PRs)",
             "Historical references retained: C3 DRAM 54864 B / B3 cost <=696 B",
             "", "| Channel | Base IRAM / DRAM / BSS | HEAD IRAM / DRAM / BSS | Incremental |",
             "|---|---|---|---|"]
    for variant in CLOCKS:
        b, h = report["measured"]["base"][variant], report["measured"]["head"][variant]
        inc = report["spi_c3"]["incremental"][variant]
        lines.append("| " + variant + " | " + " / ".join(str(b[k]) for k in ("iram", "dram", "bss")) +
                     " | " + " / ".join(str(h[k]) for k in ("iram", "dram", "bss")) +
                     " | " + inc["status"] + " |")
    lines += ["", "RENDER_A_HISTORICAL base=" + report["render_a"]["historical"]["base"]["status"] +
              " head=" + report["render_a"]["historical"]["head"]["status"] +
              " ; RENDER-A incremental=" + report["render_a"]["incremental"]["status"],
              "C3_HISTORICAL head SPI40=" + report["spi_c3"]["historical"]["head"]["spi40"]["status"] +
              " SPI20=" + report["spi_c3"]["historical"]["head"]["spi20"]["status"],
              "SPI_VARIANTS_PARITY=" + report["spi_c3"]["variants"]["status"],
              ("HISTORICAL_FAILURE=TRUE" if report["historical_debt"] == "HISTORICAL_DEBT"
                  else "HISTORICAL_FAILURE=FALSE") + " (+" +
                  str(report["render_a"]["historical"]["head"]["delta_iram"]) +
                  " IRAM); C3_SPI20_DELTA=+" +
                  str(report["spi_c3"]["historical"]["head"]["spi20"]["delta_iram"]),
              "INCREMENTAL_PASS" if report["status"] == "INCREMENTAL_PASS"
                  else "INCREMENTAL_FAIL",
              "C7_CONTRACT=" + report["status"],
              "", "Old RENDER-A and SPI-C3 historical comparators must be replayed with their original nonzero return codes.",
              "ROOT_CAUSE_UNVERIFIED. Only PR-incremental and provenance gates can pass this workflow."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--provenance", type=Path, required=True)
    ap.add_argument("--live-pr", type=Path, required=True)
    ap.add_argument("--live-pr-start", type=Path, required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr-number", required=True, type=int)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--base-checkout", type=Path, required=True)
    ap.add_argument("--head-checkout", type=Path, required=True)
    args = ap.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        p = read_json(args.provenance)
        initial, latest = read_json(args.live_pr_start), read_json(args.live_pr)
        require(stable_pr_identity(initial) == stable_pr_identity(latest),
                "GitHub PR identity changed during real Xtensa builds")
        base, head = verify_provenance(p, latest, args.repo,
                                       args.pr_number, args.base_checkout,
                                       args.head_checkout)
        validate_pr(initial, args.repo, args.pr_number, base, head)
        memory = {label: {variant: build_metrics(args.root, label, variant, sha,
                                                  p[label + "_tree"])
                          for variant in CLOCKS}
                  for label, sha in (("base", base), ("head", head))}
        allocation = authorize_esc_b1(p, latest, args.repo,
                                       args.pr_number, args.head_checkout)
        report = evaluate(memory, p, allocation)
        # Historical verdict remains independently measured, even if future code
        # reductions genuinely close the old debt; never force old failure to PASS.
        rc = 0 if report["status"] == "INCREMENTAL_PASS" else 1
    except (OSError, ValueError, KeyError, TypeError, IndexError, UnicodeError,
            subprocess.CalledProcessError,
            json.JSONDecodeError) as exc:
        report = {"contract": VERSION, "status": "MEASUREMENT_INVALID",
                  "historical_debt": "UNVERIFIED",
                  "spi_variants_parity": "SPI_VARIANTS_PARITY_UNVERIFIED",
                  "error": str(exc)}
        rc = 2
    (args.output / "verdict.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    text = markdown(report)
    (args.output / "verdict.md").write_text(text)
    print(text)
    print("C7_EXIT_CODE=" + str(rc))
    return rc


if __name__ == "__main__":
    sys.exit(main())
