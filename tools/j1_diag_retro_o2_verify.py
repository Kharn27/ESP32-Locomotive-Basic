#!/usr/bin/env python3
"""J1-DIAG-RETRO-O2: independent ROM-backed GOTO / IF acquisition and archive guard.

Never generates screen wording, ERR/ERL, ROM bytes or synthetic CPC evidence.
Reviewing two real PNGs by eye is a separate, mandatory human step.
Only new O2 paths; existing A0/J1.10/J1.11 archives stay read-only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_diag_goto_if_missing"
SOURCES = EVIDENCE / "sources"
CASES = {
    "GOTO_MISSING": (10, "10 GOTO 999\n20 PRINT \"NEVER\"\n"),
    "IF_TAKEN_MISSING": (20, "10 A%=1\n20 IF A% THEN 999\n30 PRINT \"NEVER\"\n"),
    "IF_UNTAKEN_MISSING": (20, "10 A%=0\n20 IF A% THEN 999\n30 PRINT \"AFTER\"\n"),
    "GOSUB_CONTROL": (10, "10 GOSUB 999\n20 PRINT \"NEVER\"\n"),
    "GOTO_RENUMBERED": (370, "370 GOTO 999\n400 PRINT \"NEVER\"\n"),
    "IF_TAKEN_RENUMBERED": (520, "510 A%=1\n520 IF A% THEN 999\n530 PRINT \"NEVER\"\n"),
}
PIN = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
ROM_SHA = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
GHCR_PIN = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
            "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")
PNG = b"\x89PNG\r\n\x1a\n"
FORBIDDEN_SUFFIX = {".rom", ".sna", ".dsk"}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_file(case):
    return SOURCES / (case.lower() + ".bas")


def source_bytes(case):
    at, expected = CASES[case]
    actual = source_file(case).read_bytes()
    require(actual == expected.encode("ascii"), case + ": SOURCE_DRIFT")
    lines = [int(line.split(b" ", 1)[0]) for line in actual.splitlines()]
    require(lines == sorted(set(lines)) and at in lines, case + ": BAD_LINE_NUMBERS")
    return actual


def check_sources():
    require({p.name for p in SOURCES.glob("*.bas")} ==
            {source_file(case).name for case in CASES}, "O2_SOURCE_INVENTORY_CHANGED")
    for case in CASES:
        source_bytes(case)
    print("O2_SOURCES=PASS CASES=%u CPC_ORACLE_UNVERIFIED" % len(CASES))


def files_in(folder):
    return {p.relative_to(folder).as_posix():
            {"sha256": sha(p.read_bytes()), "size_bytes": p.stat().st_size}
            for p in sorted(folder.rglob("*")) if p.is_file()}


def inspect_files(folder, inventory):
    require(isinstance(inventory, dict), "INVALID_INVENTORY")
    actual = files_in(folder)
    require(set(actual) == set(inventory), "EVIDENCE_INVENTORY_CHANGED")
    for rel, metadata in actual.items():
        require(inventory[rel] == metadata, "EVIDENCE_SHA_OR_SIZE_CHANGED " + rel)
        require(not Path(rel).is_absolute() and ".." not in Path(rel).parts,
                "UNSAFE_EVIDENCE_PATH")
        require(Path(rel).suffix.lower() not in FORBIDDEN_SUFFIX,
                "ROM_OR_FULL_SNAPSHOT_ARCHIVED")
    return actual


def capture_one(cap, phase, case, source, numbers, image_cli):
    # Reuse the repository's genuine LIST + temporary pre-RUN SNA acquisition.
    # The SNA is deleted by the existing helper; only bounded BASIC RAM is saved.
    sys.path.insert(0, str(ROOT / "tests/oracles"))
    import token_ram_oracle
    from j1_11_gosub_return_oracle import run_observation
    pre = token_ram_oracle.acquire(cap, cap / "rom", case, source,
                                   numbers, image_cli, phase)
    work = phase / case
    (work / "original.bas").write_bytes(source)
    # Separate real Caprice32 process from LIST/SNA; PNG captured before ERR/ERL.
    run = run_observation(cap, work, source)
    require(run["returncode"] == 0 and run["screen_png_present"],
            case + ": RUN_PNG_MISSING")
    saved = files_in(work)
    for rel in saved:
        require(Path(rel).suffix.lower() not in FORBIDDEN_SUFFIX,
                "FORBIDDEN_BINARY_ARCHIVE")
    return {"pre_run": pre, "run": run, "all_files_sha256": saved}


def acquire(cap, image_cli, out):
    check_sources()
    require(not out.exists(), "REFUSE_OVERWRITE_EVIDENCE")
    require(cap.is_dir() and (cap / "cap32").is_file() and
            (cap / "cap32.cfg").is_file(), "PINNED_CAPRICE32_UNAVAILABLE")
    require((cap / "rom/cpc6128.rom").is_file(), "AUTHENTIC_ROM_UNAVAILABLE")
    require(sha((cap / "rom/cpc6128.rom").read_bytes()) == ROM_SHA,
            "CPC6128_ROM_SHA_MISMATCH")
    actual = subprocess.check_output(["git", "-C", str(cap),
                                      "rev-parse", "HEAD"], text=True).strip()
    require(actual == PIN, "CAPRICE32_SOURCE_PIN_MISMATCH")
    checkout = subprocess.check_output(["git", "-C", str(ROOT),
                                        "rev-parse", "HEAD"], text=True).strip()
    require(re.fullmatch(r"[a-f0-9]{40}", checkout), "CHECKOUT_SHA_MISSING")
    claimed = os.getenv("GITHUB_HEAD_SHA")
    require(not claimed or claimed == checkout, "CHECKOUT_SHA_MISMATCH")
    require(image_cli.is_file(), "C99_IMAGE_CLI_MISSING")
    version = subprocess.check_output([str(cap / "cap32"), "--version"],
                                      cwd=cap, text=True)
    # No output directory is created before all identity checks succeed.
    out.mkdir(parents=True)
    cases = {}
    for case in CASES:
        source = source_bytes(case)
        nums = [int(line.split(b" ", 1)[0]) for line in source.splitlines()]
        captures = {}
        for phase in ("original", "repeat"):
            (out / phase).mkdir(exist_ok=True)
            captures[phase] = capture_one(cap, out / phase, case,
                                          source, nums, image_cli)
        cases[case] = {"source_sha256": sha(source), "line_numbers": nums,
                       "fault_line_in_source": CASES[case][0],
                       **captures}
    manifest = {
        "schema_version": 1, "phase": "J1-DIAG-RETRO-O2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "checkout_sha": checkout, "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "rom_archived": False, "full_sna_archived": False,
        "native_mapping_authorized": False, "reviewed_screen_text": False,
        "oracle": {"emulator": "Caprice32", "commit": PIN,
                   "rom_sha256": ROM_SHA, "model": "CPC6128",
                   "basic": "1.1", "version_output": version,
                   "ghcr_image": GHCR_PIN},
        "cases": cases
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("O2_CAPTURED_RAW=PASS REVIEW_PENDING=1 CHECKOUT="+checkout)
    verify(out)


def cpc_record_lines(raw):
    # Native CPC BASIC pre-RUN RAM: bounded, length-prefixed records + 0000.
    cursor, numbers = 0, []
    while cursor < len(raw) - 2:
        require(len(raw) - cursor >= 6, "TRUNCATED_CPC_RAM_RECORD")
        length = raw[cursor] | (raw[cursor+1] << 8)
        require(5 <= length <= len(raw) - cursor - 2,
                "CPC_RAM_RECORD_LENGTH_INVALID")
        line = raw[cursor+2] | (raw[cursor+3] << 8)
        require(1 <= line <= 65535 and
                (not numbers or line > numbers[-1]) and
                raw[cursor+length-1] == 0,
                "CPC_RAM_LINE_OR_TERMINATOR_INVALID")
        numbers.append(line)
        cursor += length
    require(raw[cursor:] == b"\x00\x00", "CPC_RAM_SENTINEL_CHANGED")
    return numbers


def printer_probes(raw):
    # Parse only what the separate CPC printer actually wrote, not BEStatus.
    rows = raw.splitlines(keepends=True)
    if len(rows) != 2:
        return (None, None)
    values = []
    for row in rows:
        match = re.fullmatch(rb" *([+-]?[0-9]+) *(?:\r\n|\r|\n)", row)
        if match is None:
            return (None, None)
        values.append(int(match.group(1)))
    return (values[0], values[1])


def review_one(review, case, png_hash):
    """Check authenticity metadata, then classify observed *post-RUN* output.

    A faithfully transcribed CPC anomaly is valid evidence even when behavior
    differs. That case is REVIEWED/DIFF, never silently PASS or unreviewed.
    Metadata cannot independently prove that pixels were read: Pilotage must
    still inspect both original screenshots and their transcriptions.
    """
    require(isinstance(review, dict) and review.get("case") == case and
            review.get("provenance") == "CPC_SCREEN_HUMAN_VISUAL" and
            review.get("reviewed_original_and_repeat") is True and
            isinstance(review.get("reviewer"), str) and
            len(review["reviewer"].strip()) >= 2,
            "SCREEN_REVIEW_PROVENANCE_INCOMPLETE_" + case)
    require(set(review) == {"case", "provenance", "reviewed_original_and_repeat",
                            "reviewer", "original", "repeat"},
            "SCREEN_REVIEW_UNKNOWN_FIELDS_" + case)
    observed = []
    for phase in ("original", "repeat"):
        item = review.get(phase)
        require(isinstance(item, dict) and
                set(item) == {"png_sha256", "post_run_output_lines", "ready_count"},
                "SCREEN_REVIEW_UNKNOWN_PHASE_FIELDS_" + case)
        require(item.get("png_sha256") == png_hash,
                "SCREEN_REVIEW_PHASE_HASH_INVALID_" + case + "_" + phase)
        lines = item.get("post_run_output_lines")
        require(isinstance(lines, list) and len(lines) <= 25 and
                all(isinstance(line, str) and len(line) <= 160 and
                    not any(c in line for c in "\r\n\x00")
                    for line in lines),
                "SCREEN_REVIEW_POST_RUN_TRANSCRIPT_INVALID_" + case)
        ready = item.get("ready_count")
        require(type(ready) is int and 0 <= ready <= 25,
                "SCREEN_REVIEW_READY_COUNT_INVALID_" + case)
        observed.append((lines, ready))
    require(observed[0] == observed[1],
            "SCREEN_REVIEW_ORIGINAL_REPEAT_TRANSCRIPT_DIFF_" + case)
    lines, ready = observed[0]
    # Do not assume the wording of the GOTO / IF CPC error. Only check the
    # semantic witness (missing destination, locus and post-RUN output).
    reasons = []
    if ready != 1:
        reasons.append("READY_COUNT_%d" % ready)
    if any("NEVER" in line for line in lines):
        reasons.append("FORBIDDEN_PRINT_EXECUTED")
    if case == "IF_UNTAKEN_MISSING":
        if lines != ["AFTER"]:
            reasons.append("EXPECTED_AFTER_ONLY")
    else:
        expected_line = CASES[case][0]
        # Screen wording is empirical, not inferred from GOSUB/A0 or BEStatus.
        # An alternate authentic wording remains recorded, with a DIFF flag.
        if len(lines) != 1:
            reasons.append("EXPECTED_SINGLE_ERROR_LINE")
        if len(lines) == 1:
            match = re.search(r"(?:^|\s)in ([0-9]+)$", lines[0])
            if match is None or int(match.group(1)) != expected_line:
                reasons.append("ERROR_LOCUS_UNVERIFIED_OR_DIFFERENT")
    return {"status": "BEHAVIOR_PASS" if not reasons else "BEHAVIOR_DIFF",
            "reasons": reasons, "post_run_output_lines": list(lines),
            "ready_count": ready}


def verify(root):
    manifest_path = root / "manifest.json"
    require(manifest_path.is_file(), "CPC_CAPTURE_MISSING")
    data = json.loads(manifest_path.read_text())
    require(data.get("schema_version") == 1 and
            data.get("phase") == "J1-DIAG-RETRO-O2" and
            data.get("rom_archived") is False and
            data.get("full_sna_archived") is False and
            data.get("native_mapping_authorized") is False and
            data.get("oracle", {}).get("rom_sha256") == ROM_SHA and
            data["oracle"].get("commit") == PIN and
            data["oracle"].get("ghcr_image") == GHCR_PIN and
            re.fullmatch(r"[0-9a-f]{40}", data.get("checkout_sha", "")),
            "O2_PROVENANCE_UNTRUSTED")
    require(set(data.get("cases", {})) == set(CASES), "O2_CASE_INVENTORY_CHANGED")
    recorded = data["cases"]
    review_path = root / "screen_review.json"
    reviews = json.loads(review_path.read_text()) if review_path.exists() else {}
    require(isinstance(reviews, dict) and
            set(reviews).issubset(set(CASES)), "UNKNOWN_SCREEN_REVIEW")
    complete = 0
    divergent = 0
    for case, obj in recorded.items():
        source = source_bytes(case)
        expected_lines = [int(line.split(b" ", 1)[0])
                          for line in source.splitlines()]
        require(obj.get("source_sha256") == sha(source) and
                obj.get("fault_line_in_source") == CASES[case][0] and
                obj.get("line_numbers") == expected_lines,
                "O2_SOURCE_PROVENANCE_CHANGED_"+case)
        ram, printer, png = [], [], []
        probes = []
        for phase in ("original", "repeat"):
            part = root / phase / case
            require(part.is_dir(), "MISSING_FRESH_SESSION_"+phase+"_"+case)
            inspect_files(part, obj[phase]["all_files_sha256"])
            pre, run = obj[phase]["pre_run"], obj[phase]["run"]
            require(pre.get("snapshot_taken_before_run") is True and
                    pre.get("list_requested") is True and
                    pre.get("source_sha256") == sha(source) and
                    run.get("fresh_cpc_run_process") is True and
                    run.get("returncode") == 0 and
                    run.get("screen_png_present") is True and
                    json.loads((part / "run/autocmd.json").read_text()).get(
                        "screenshot_before_post_run_probes") is True,
                    "O2_CAPTURE_SEQUENCE_INVALID_"+case)
            require((part / "original.bas").read_bytes() == source,
                    "O2_ORIGINAL_SOURCE_MODIFIED_"+case)
            p = part / "run/run.png"
            require(p.read_bytes().startswith(PNG) and len(p.read_bytes()) > 32,
                    "O2_RUN_PNG_INVALID_"+case)
            require((part / "list.png").read_bytes().startswith(PNG),
                    "O2_LIST_PNG_INVALID_"+case)
            commands = json.loads((part / "run/autocmd.json").read_text())["commands"]
            require(commands[:len(source.splitlines())] ==
                    source.decode("ascii").splitlines() and
                    commands[len(source.splitlines())] == "RUN" and
                    commands.index("PRINT #8,ERR") > commands.index("CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT") and
                    commands.index("PRINT #8,ERL") > commands.index("PRINT #8,ERR"),
                    "O2_SCREEN_PRINTER_ORDER_INVALID_"+case)
            ram.append((part / "program.bin").read_bytes())
            printer_path = part / "run/printer.dat"
            # Probe not produced by Caprice32 => UNVERIFIED; never fabricate it.
            printer.append(printer_path.read_bytes() if printer_path.is_file() else b"")
            png.append(sha(p.read_bytes()))
            probes.append((run.get("err_probe"), run.get("erl_probe")))
        require(ram[0] == ram[1], "O2_CPC_RAM_ORIGINAL_REPEAT_DIFFER_"+case)
        require(cpc_record_lines(ram[0]) == expected_lines,
                "O2_CPC_RAM_NOT_THE_SOURCE_LINES_"+case)
        require(printer[0] == printer[1] and probes[0] == probes[1],
                "O2_PRINTER_ORIGINAL_REPEAT_DIFFER_"+case)
        for index, phase in enumerate(("original", "repeat")):
            run = obj[phase]["run"]
            raw = printer[index]
            require(probes[index] == printer_probes(raw) and
                    run.get("printer_raw_hex") == raw.hex(" ").upper(),
                    "O2_PROBES_NOT_GENUINE_PRINTER_BYTES_"+case)
        require(png[0] == png[1], "O2_PNG_ORIGINAL_REPEAT_DIFFER_"+case)
        outcome = None
        if case in reviews:
            outcome = review_one(reviews[case], case, png[0])
            complete += 1
            if outcome["status"] == "BEHAVIOR_DIFF":
                divergent += 1
        print("O2_CASE=%s RAW_PAIRS=PASS SCREEN_REVIEW=%s BEHAVIOR=%s "
              "REASONS=%s READY=%s RUN_OUTPUT=%s ERR=%s ERL=%s" %
              (case, "REVIEWED" if outcome else "UNVERIFIED",
               outcome["status"] if outcome else "UNVERIFIED",
               ",".join(outcome["reasons"]) if outcome else "UNVERIFIED",
               outcome["ready_count"] if outcome else "UNVERIFIED",
               json.dumps(outcome["post_run_output_lines"]) if outcome else "UNVERIFIED",
               probes[0][0] if probes[0][0] is not None else "UNVERIFIED",
               probes[0][1] if probes[0][1] is not None else "UNVERIFIED"))
    require(set(root.iterdir()) -
            {root/"original", root/"repeat", root/"manifest.json",
             root/"screen_review.json"} == set(),
            "O2_UNEXPECTED_ARCHIVE_PATH")
    # Validation of structured metadata never auto-approves an oracle. The
    # independent human + Pilotage still own the screen pixel verification.
    verdict = ("O2_EVIDENCE_READY_FOR_PILOTAGE_REVIEW" if
               complete == len(CASES) and divergent == 0 else
               "O2_REVIEWED_WITH_BEHAVIOR_DIFF" if divergent else
               "CPC_ORACLE_UNVERIFIED")
    print("O2_RAW_ARCHIVE=PASS SCREEN_REVIEWED=%u/%u BEHAVIOR_DIFF=%u %s" %
          (complete, len(CASES), divergent, verdict))
    return complete


def self_test():
    # Fake bytes below are ephemeral test cases, NOT CPC screenshots/oracles.
    check_sources()
    base_phase = {"png_sha256": "a"*64,
                  "post_run_output_lines": ["TEST_ERROR in 10"],
                  "ready_count": 1}
    base = {"case": "GOTO_MISSING",
            "provenance": "CPC_SCREEN_HUMAN_VISUAL",
            "reviewed_original_and_repeat": True,
            "reviewer": "in-memory test only",
            "original": dict(base_phase), "repeat": dict(base_phase)}
    require(review_one(base, "GOTO_MISSING", "a"*64)["status"] ==
            "BEHAVIOR_PASS", "VALID_REVIEW_STRUCTURE_REJECTED")
    def with_phase(key, value, phase="original"):
        return {**base, phase: {**base[phase], key: value}}
    metadata_mutants = [
        {**base, "original": {**base_phase, "png_sha256": "b"*64}},
        {**base, "reviewed_original_and_repeat": False},
        {**base, "provenance": "HOST_INFERRED"},
        {**base, "reviewer": ""},
        with_phase("post_run_output_lines", "not an array"),
        with_phase("ready_count", -1),
        with_phase("post_run_output_lines", ["different in 10"]),
        with_phase("ready_count", 2),
        {**base, "forbidden_print_absent": False},
        with_phase("forbidden_print_absent", False),
    ]
    for index, mutant in enumerate(metadata_mutants):
        try:
            review_one(mutant, "GOTO_MISSING", "a"*64)
        except ValueError:
            continue
        raise AssertionError("NEGATIVE_REVIEW_METADATA_ACCEPTED_%u" % index)
    # Crucial Pilotage review gate: genuine anomalous observations must be
    # retained but classified DIFF, never BEHAVIOR_PASS.
    def both(lines, ready=1, case="GOTO_MISSING"):
        return {**base, "case": case,
                "original": {**base_phase, "post_run_output_lines": lines,
                             "ready_count": ready},
                "repeat": {**base_phase, "post_run_output_lines": lines,
                           "ready_count": ready}}
    behavior_mutants = [
        both(["TEST_ERROR in 10"], 0),
        both(["TEST_ERROR in 10", "NEVER"]),
        both([], case="IF_UNTAKEN_MISSING"),
        both(["NEVER"], case="IF_UNTAKEN_MISSING"),
        both(["TEST_ERROR in 999"]),
        both(["ERROR_WITHOUT_LINE_NUMBER"]),
    ]
    for index, mutant in enumerate(behavior_mutants):
        observed = review_one(mutant, mutant["case"], "a"*64)
        require(observed["status"] == "BEHAVIOR_DIFF" and
                bool(observed["reasons"]),
                "NEGATIVE_BEHAVIOR_PROMOTED_%u" % index)
    require(review_one(both(["AFTER"], case="IF_UNTAKEN_MISSING"),
                       "IF_UNTAKEN_MISSING", "a"*64)["status"] ==
            "BEHAVIOR_PASS", "IF_UNTAKEN_AFTER_REJECTED")
    # Synthetically built parser input, never archived as CPC evidence.
    test_record = bytes.fromhex("06 00 0a 00 0e 00 00 00")
    require(cpc_record_lines(test_record) == [10], "CPC_RAM_PARSER_FIXTURE")
    require(printer_probes(b" 12\r\n -7\r\n") == (12, -7),
            "PRINTER_PARSER_FIXTURE")
    ram_mutants = [
        bytes.fromhex("06 00 0a 00 0e 00 00"),
        bytes.fromhex("06 00 0a 00 0e 00 00 01"),
        bytes.fromhex("06 00 0a 00 0e 01 00 00"),
        bytes.fromhex("06 00 00 00 0e 00 00 00"),
        bytes.fromhex("07 00 0a 00 0e 00 00 00")
    ]
    for index, mutant in enumerate(ram_mutants):
        try:
            cpc_record_lines(mutant)
        except ValueError:
            continue
        raise AssertionError("NEGATIVE_RAM_MUTANT_NOT_REJECTED_%u" % index)
    require(not (SOURCES / "manifest.json").exists(),
            "SOURCE_DIR_MUST_NOT_IMPERSONATE_ORACLE")
    print("O2_NEGATIVE_METADATA=10/10 REJECTED "
          "O2_NEGATIVE_BEHAVIOR=6/6 DIFF "
          "O2_NEGATIVE_RAM=5/5 REJECTED "
          "NO_GENERATED_CPC_EVIDENCE")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check-sources", action="store_true")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--acquire", action="store_true")
    p.add_argument("--verify", type=Path)
    p.add_argument("--caprice", type=Path)
    p.add_argument("--image-cli", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.acquire:
        require(args.caprice is not None and args.image_cli is not None and
                args.output is not None, "CAPRICE_IMAGE_CLI_OUTPUT_REQUIRED")
        acquire(args.caprice.resolve(), args.image_cli.resolve(),
                args.output.resolve())
    elif args.verify is not None:
        check_sources()
        verify(args.verify.resolve())
    elif not (args.check_sources or args.self_test):
        p.error("select --check-sources, --self-test, --acquire or --verify")
    elif args.check_sources:
        check_sources()
    if args.self_test:
        self_test()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, IndexError, subprocess.CalledProcessError) as error:
        print("J1-DIAG-RETRO-O2 FAIL:", error, file=sys.stderr)
        sys.exit(1)
