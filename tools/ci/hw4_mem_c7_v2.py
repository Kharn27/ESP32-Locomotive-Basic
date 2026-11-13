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
    require(sections["iram"] > 0 and sections["dram"] > 0 and
            sections["bss"] > 0 and sections["dram"] >= sections["bss"],
            "invalid sections or BSS")
    require(meta.get("sdkconfig_sha256") == digest(data["sdkconfig"]),
            "sdkconfig digest incorrect")
    return {"iram": sections["iram"], "dram": sections["dram"], "bss": sections["bss"],
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


def judge(base, head):
    delta = {k: head[k] - base[k] for k in ("iram", "dram", "bss")}
    return {"status": "INCREMENTAL_PASS" if all(v <= 0 for v in delta.values())
            else "INCREMENTAL_FAIL", **delta}


def evaluate(memory, provenance):
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
    r = {
        "contract": VERSION, "provenance": provenance, "anchors": ANCHORS,
        "render_a": {"historical": {label: status_hist(memory[label]["spi40"],
                                                       "RENDER_A", "spi40")
                                    for label in ("base", "head")},
                     "incremental": judge(base40, head40)},
        "spi_c3": {"historical": {label: {v: status_hist(memory[label][v], "B3", v)
                                             for v in CLOCKS}
                                  for label in ("base", "head")},
                   "incremental": {v: judge(memory["base"][v], memory["head"][v])
                                   for v in CLOCKS},
                   "variants": {"status": "SPI_VARIANTS_PARITY_UNVERIFIED"}},
        "measured": {label: {v: {k: m[k] for k in
                      ("iram", "dram", "bss", "flash_text", "flash_rodata", "bin_sha256")}
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
        if (a["iram"], a["dram"]) != (b["iram"], b["dram"]):
            faults.append(label + " SPI40/SPI20 IRAM/DRAM disparity")
        if a["bin_sha256"] == b["bin_sha256"]:
            faults.append(label + " SPI40/SPI20 identical BIN")
        if a["sdkconfig"] != b["sdkconfig"]:
            faults.append(label + " SPI40/SPI20 SDKCONFIG differs")
    for v in CLOCKS:
        for label in ("base", "head"):
            d = memory[label][v]["dram"]
            if not 0 <= d - 54168 <= 696 or d > 54864:
                faults.append(label + " " + v + " C3 DRAM cap/B3-cost exceeded")
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
              "HISTORICAL_FAILURE=TRUE (+220 IRAM)" if (
                  report["render_a"]["historical"]["head"]["delta_iram"] == 220 and
                  all(report["spi_c3"]["historical"]["head"][v]["delta_iram"] == 220
                      for v in CLOCKS)) else "HISTORICAL_FAILURE=UNEXPECTED",
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
        require(all(initial.get(k) == latest.get(k)
                    for k in ("number", "state", "base", "head")),
                "GitHub PR changed during real Xtensa builds")
        base, head = verify_provenance(p, latest, args.repo,
                                       args.pr_number, args.base_checkout,
                                       args.head_checkout)
        validate_pr(initial, args.repo, args.pr_number, base, head)
        memory = {label: {variant: build_metrics(args.root, label, variant, sha,
                                                  p[label + "_tree"])
                          for variant in CLOCKS}
                  for label, sha in (("base", base), ("head", head))}
        report = evaluate(memory, p)
        if (report["render_a"]["historical"]["head"]["delta_iram"] != 220 or
            any(report["spi_c3"]["historical"]["head"][v]["delta_iram"] != 220
                for v in CLOCKS)):
            raise ValueError("historical +220 IRAM witness invalid")
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
