#!/usr/bin/env python3
"""J0.26 evidence exit audit. Integrity controls, NEVER an automatic J0->J1 gate.

Pure stdlib; original immutable provenance is checked again by existing
C2/C3-C8 validators. No screen pixel-to-text or hardware validation is inferred.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    "a_print_constants", "b_integer_scalar", "c_integer_add",
    "d_self_reference", "e_goto", "f_let_spacing",
    "f_constant_boundary", "f_mixed_case", "g_uninitialized",
)
TOKEN_CASES = set(CASES) - {"f_constant_boundary"}
RUN_CASES = {"c_integer_add": 5, "d_self_reference": 2}
LIST_CASES = {"c_integer_add": (42, 38), "f_mixed_case": (46, 43)}


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def raw_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_case_map(base, dirname, expected, classification, op):
    manifest = load(base / dirname / "manifest.json")
    captures = manifest.get("captures")
    require(isinstance(captures, list) and
            {c.get("case") for c in captures} == set(expected) and
            len(captures) == len(expected),
            f"{dirname}: missing, duplicate or unexpected case")
    for capture in captures:
        cid = capture["case"]
        require(capture.get("classification") == classification and
                capture.get("operation") == op,
                f"{dirname}/{cid}: classification or operation drift")
        require(capture.get("cpc_channel", "").startswith(
                    "screen.png:" if dirname == "list_screen" else "printer.dat:") and
                capture.get("native_channel", "").startswith("native.stdout.bin:"),
                f"{dirname}/{cid}: CPC/native channel confusion")
        files = capture.get("files", {})
        required = {"screen.png", "native.stdout.bin", "source.bas"}
        if dirname != "list_screen":
            required.add("printer.dat")
        require(required <= set(files), f"{dirname}/{cid}: missing file manifest")
        for filename in required:
            require((base / dirname / cid / filename).is_file(),
                    f"{dirname}/{cid}: missing {filename}")
        if dirname == "list_screen":
            require("printer.dat" not in files and
                    not (base / dirname / cid / "printer.dat").exists() and
                    capture.get("byte_exactness_claimed") is False and
                    capture.get("printer_channel", "").startswith("not acquired"),
                    f"{dirname}/{cid}: pixels treated as printer/text bytes")
        else:
            require(capture.get("screen_channel", "").startswith("screen.png: visual only"),
                    f"{dirname}/{cid}: screen bytes incorrectly claimed")
    return manifest, {c["case"]: c for c in captures}


def c6_format_gap(cpc_bytes, native_bytes, value, case_id):
    """Assert C6 *archived* cross-channel numeric formatting divergence.

    This compares CPC post-RUN PRINT #8,B% with the C99 RUN stdout,
    NOT identical historical commands or CPC screen text bytes.
    The historical observation stays MATCH_SEMANTIC regardless.
    """
    number = str(value).encode("ascii")
    require(cpc_bytes == b" " + number + b" \r\n",
            f"{case_id}: CPC C6 post-RUN printer numeric format changed")
    require(native_bytes == number + b"\n",
            f"{case_id}: C99 C6 RUN stdout numeric format changed")
    # Normalize line endings only; CPC spaces still survive and must be reported.
    newline_only = cpc_bytes.replace(b"\r\n", b"\n")
    require(newline_only != native_bytes and
            newline_only.strip() == native_bytes.strip(),
            f"{case_id}: expected leading/trailing numeric spaces gap disappeared")
    return ("C6_FORMAT_GAP_OBSERVED "
            f"case={case_id} CPC_PRINTER_POST_RUN={cpc_bytes.hex(' ')} "
            f"C99_STDOUT_DURING_RUN={native_bytes.hex(' ')} "
            "CRLF_TO_LF_INSUFFICIENT=YES NUMERIC_SPACES=LEADING_AND_TRAILING "
            "HISTORICAL_CLASSIFICATION=MATCH_SEMANTIC "
            "SCREEN_TEXT_BYTES=NOT_AUTOMATICALLY_VERIFIABLE")


def inspect(base):
    """Verify actual manifests and payloads, not an audit-specific copied claim."""
    master = load(base / "manifest.json")
    cases = master.get("cases")
    require(master.get("schema_version") == 1 and
            isinstance(cases, list) and len(cases) == len(CASES) and
            {case.get("id") for case in cases} == set(CASES),
            "historical nine-case corpus changed")
    token_seen = set()
    probe_seen = set()
    printer_seen = set()
    for case in cases:
        cid = case["id"]
        operations = case.get("operations", [])
        observations = case.get("observations", {})
        expected_ops = {"LIST", "RUN"}
        if cid in TOKEN_CASES:
            expected_ops.add("TOKENS")
        if cid in RUN_CASES:
            expected_ops.add("RUN_NUMERIC_PROBE")
        if cid in LIST_CASES:
            expected_ops.add("LIST_PRINTER_PROBE")
        require(isinstance(operations, list) and len(operations) == len(expected_ops)
                and set(operations) == expected_ops,
                f"{cid}: one of 18 historical LIST/RUN operations removed/changed")
        require(isinstance(observations, dict) and
                "LIST" not in observations and "RUN" not in observations and
                set(observations) == expected_ops - {"LIST", "RUN"},
                f"{cid}: UNVERIFIED operation promoted or observation lost")
        source = base / case["source"]
        require(source.is_file() and raw_sha(source) == case["source_sha256"],
                f"{cid}: source missing or SHA-256 mismatch")
        for op, expected_class, expected_media, seen in (
            ("TOKENS", "MATCH_EXACT", "binary", token_seen),
            ("RUN_NUMERIC_PROBE", "MATCH_SEMANTIC", "printer-probe", probe_seen),
            ("LIST_PRINTER_PROBE", "DIFF", "printer-list", printer_seen),
        ):
            if op not in observations:
                continue
            observation = observations[op]
            require(observation.get("expected_classification") == expected_class and
                    observation.get("media") == expected_media,
                    f"{cid}/{op}: forged classification or media")
            filename = base / observation["path"]
            require(filename.is_file() and raw_sha(filename) == observation["sha256"],
                    f"{cid}/{op}: missing/modified archived evidence")
            seen.add(cid)
            if op == "TOKENS":
                require(observation.get("origin") == "cpc6128-rom-basic11",
                        f"{cid}: not CPC RAM provenance")
                c99 = base / "token_ram" / cid / "c99.bin"
                require(c99.is_file() and filename.read_bytes() == c99.read_bytes(),
                        f"{cid}: CPC/C99 token image mismatch")
    require(token_seen == TOKEN_CASES and probe_seen == set(RUN_CASES)
            and printer_seen == set(LIST_CASES),
            "insufficient 8 TOKENS / 2 RUN probes / 2 LIST printer captures")
    token_archive = load(base / "token_ram" / "manifest.json")
    master_by_id = {case["id"]: case for case in cases}
    require(token_archive.get("phase") == "J0.24-C5" and
            {c.get("id") for c in token_archive.get("cases", [])} == TOKEN_CASES and
            len(token_archive["cases"]) == 8,
            "C3/C4/C5 eight-case manifest changed")
    for c in token_archive["cases"]:
        cid = c["id"]
        # source_path is repository-relative provenance, not relative to ROOT
        # or to the parent directories of a potentially temporary corpus copy.
        # Resolve it through the corresponding source of THIS corpus instance.
        source_record = master_by_id[cid]
        require(c.get("source_path") ==
                "tests/fixtures/cpc6128/" + source_record["source"] and
                c.get("source_sha256") == source_record["source_sha256"],
                f"token archive case {cid}: source provenance drift")
        source = base / source_record["source"]
        require(c.get("comparison") == "MATCH_EXACT" and source.is_file()
                and raw_sha(source) == c["source_sha256"],
                f"token archive case {cid} incomplete")
    run, run_captures = archive_case_map(
        base, "run_behavior", RUN_CASES, "MATCH_SEMANTIC", "RUN_NUMERIC_PROBE")
    format_gaps = []
    require(run.get("screen_bytes_captured") is False and
            run.get("printer_screen_byte_equivalence") is False,
            "RUN screen/printer equivalence invented")
    for cid, expected in RUN_CASES.items():
        c = run_captures[cid]
        require(c.get("cpc_integer") == c.get("native_integer") == expected and
                c.get("comparison") == "strict-signed-integer",
                f"{cid}: post-RUN semantic probe drift")
        format_gaps.append(c6_format_gap(
            (base / "run_behavior" / cid / "printer.dat").read_bytes(),
            (base / "run_behavior" / cid / "native.stdout.bin").read_bytes(),
            expected, cid))
    printer, listings = archive_case_map(
        base, "list_printer", LIST_CASES, "DIFF", "LIST_PRINTER_PROBE")
    require(printer.get("screen_bytes_captured") is False and
            printer.get("printer_screen_byte_equivalence") is False,
            "LIST printer treated as screen text")
    for cid, sizes in LIST_CASES.items():
        capture = listings[cid]
        cpc = (base / "list_printer" / cid / "printer.dat").read_bytes()
        native = (base / "list_printer" / cid / "native.stdout.bin").read_bytes()
        require(capture.get("comparison") == "exact-bytes" and
                (len(cpc), len(native)) == sizes and
                b"\r\n" in cpc and b"\r" not in native and
                cpc.replace(b"\r\n", b"\n") == native and cpc != native,
                f"{cid}: C7 DIFF is no longer solely CRLF/LF")
    screen, screens = archive_case_map(
        base, "list_screen", LIST_CASES, "VISUAL_OBSERVATION", "LIST_SCREEN_VISUAL")
    require(screen.get("screen_text_bytes_extracted") is False and
            screen.get("screen_printer_equivalence") is False,
            "screen pixels promoted to textual byte oracle")
    for cid, capture in screens.items():
        require(capture.get("byte_exactness_claimed") is False and
                capture.get("visual_review_status") is not None,
                f"{cid}: visual-only classification changed")
    return ("PASS 9 cases / 18 historical LIST+RUN UNVERIFIED / "
            "8 TOKENS MATCH_EXACT / 2 RUN_NUMERIC_PROBE MATCH_SEMANTIC / "
            "2 LIST_PRINTER_PROBE DIFF / 2 LIST_SCREEN_VISUAL VISUAL_OBSERVATION"
            + "\n" + "\n".join(format_gaps))


def external_validators():
    """Approved validators contain provenance anchors independent of manifest input."""
    checks = [
        ["tools/cpc_evidence.py"],
        ["tools/cpc_token_evidence.py", "--permanent"],
        ["tests/oracles/cpc_run_evidence.py", "--evidence",
         "tests/fixtures/cpc6128/run_behavior", "--permanent"],
        ["tests/oracles/cpc_list_evidence.py", "--evidence",
         "tests/fixtures/cpc6128/list_printer", "--permanent"],
        ["tests/oracles/cpc_screen_evidence.py", "--evidence",
         "tests/fixtures/cpc6128/list_screen", "--permanent"],
    ]
    for cmd in checks:
        result = subprocess.run([sys.executable, str(ROOT / cmd[0]), *cmd[1:]],
                                cwd=ROOT, text=True, capture_output=True, timeout=90)
        require(result.returncode == 0,
                f"existing validator {cmd[0]} failed: {result.stderr.strip()}")
        print("PASS EXISTING_VALIDATOR", cmd[0])


def negative_tests(base):
    """Falsify only a corpus that already passes, and require exact failure causes."""
    with tempfile.TemporaryDirectory(prefix="j026-audit-") as temp:
        copied = Path(temp) / "cpc6128"
        shutil.copytree(base, copied)

        # Mandatory positive control: an UNMODIFIED temporary copy must pass the
        # same inspect() used by the negative tests, or no mutation can count.
        print("PASS POSITIVE INTACT_TEMP_COPY", inspect(copied).splitlines()[0])

        def mutate_json(path, change):
            p = copied / path
            doc = load(p)
            change(doc)
            p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        scenarios = [
            ("lost-token", lambda: (
                copied / "token_ram/b_integer_scalar/program.bin").unlink(),
             "b_integer_scalar/TOKENS: missing/modified archived evidence"),
            ("promoted-LIST", lambda: mutate_json("manifest.json",
                lambda m: m["cases"][0]["observations"].update(
                    {"LIST": {"expected_classification": "MATCH_EXACT"}})),
             "a_print_constants: UNVERIFIED operation promoted or observation lost"),
            ("lost-RUN", lambda: mutate_json("manifest.json",
                lambda m: m["cases"][0]["operations"].remove("RUN")),
             "a_print_constants: one of 18 historical LIST/RUN operations removed/changed"),
            ("forged-TOKENS", lambda: mutate_json("manifest.json",
                lambda m: m["cases"][0]["observations"]["TOKENS"].update(
                    {"expected_classification": "MATCH_SEMANTIC"})),
             "a_print_constants/TOKENS: forged classification or media"),
            ("printer-classification", lambda: mutate_json("list_printer/manifest.json",
                lambda m: m["captures"][0].update({"classification": "MATCH_EXACT"})),
             "list_printer/c_integer_add: classification or operation drift"),
            ("screen-channel", lambda: mutate_json("list_screen/manifest.json",
                lambda m: m["captures"][0].update(
                    {"cpc_channel": "native.stdout.bin: invented text"})),
             "list_screen/c_integer_add: CPC/native channel confusion"),
            ("screen-promotion", lambda: mutate_json("list_screen/manifest.json",
                lambda m: m.update({"screen_text_bytes_extracted": True})),
             "screen pixels promoted to textual byte oracle"),
            ("printer-byte-swap", lambda: (
                copied / "list_printer/c_integer_add/printer.dat").write_bytes(
                    (copied / "list_printer/c_integer_add/native.stdout.bin").read_bytes()),
             "c_integer_add: C7 DIFF is no longer solely CRLF/LF"),
            ("c6-cpc-numeric-spaces-removed", lambda: (
                copied / "run_behavior/c_integer_add/printer.dat").write_bytes(b"5\r\n"),
             "c_integer_add: CPC C6 post-RUN printer numeric format changed"),
            ("c6-native-numeric-spaces-added", lambda: (
                copied / "run_behavior/d_self_reference/native.stdout.bin").write_bytes(b" 2 \n"),
             "d_self_reference: C99 C6 RUN stdout numeric format changed"),
        ]
        for name, mutation, expected_reason in scenarios:
            # Each mutation starts from a fresh, proven-good temporary copy.
            shutil.rmtree(copied)
            shutil.copytree(base, copied)
            try:
                inspect(copied)
            except Exception as error:
                raise AuditError(
                    f"{name}: unmodified recopy failed before mutation: {error}"
                ) from error
            mutation()
            try:
                inspect(copied)
            except AuditError as error:
                require(str(error) == expected_reason,
                        f"{name}: WRONG_REJECTION_CAUSE: "
                        f"expected {expected_reason!r}, got {str(error)!r}")
                print(f"PASS EXPECTED_REJECTION {name} cause={error}")
            else:
                raise AuditError(f"{name}: mutation did not cause rejection")
            # OSError/KeyError/etc. are NOT accepted as expected rejections.

    # Direct signature tests: archive SHA checks cannot satisfy these.
    bad_signatures = [
        ("missing-both-spaces", b"5\r\n", b"5\n", 5,
         "CPC C6 post-RUN printer numeric format changed"),
        ("missing-trailing-space", b" 5\r\n", b"5\n", 5,
         "CPC C6 post-RUN printer numeric format changed"),
        ("native-space-added", b" 5 \r\n", b" 5 \n", 5,
         "C99 C6 RUN stdout numeric format changed"),
        ("wrong-value", b" 2 \r\n", b"2\n", 5,
         "CPC C6 post-RUN printer numeric format changed"),
    ]
    for name, cpc_bytes, native_bytes, value, expected_suffix in bad_signatures:
        try:
            c6_format_gap(cpc_bytes, native_bytes, value, name)
        except AuditError as error:
            require(str(error) == f"{name}: {expected_suffix}",
                    f"{name}: WRONG_C6_REJECTION_CAUSE: {error}")
            print(f"PASS EXPECTED_C6_REJECTION {name} cause={error}")
        else:
            raise AuditError(f"{name}: C6 numeric format mutation was accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        base = ROOT / "tests/fixtures/cpc6128"
        print(inspect(base))
        external_validators()
        if args.self_test:
            negative_tests(base)
        print("MANUAL_EVIDENCE J0.25-HW1: PO serial transcript, no independent raw acquisition")
        print("NOT_AUTOMATICALLY_VERIFIABLE C8 pixel text reading; CPC screen byte equivalence")
        print("NOT_AUTOMATICALLY_VERIFIABLE J0 gate decision; J0.24 and J0 remain OPEN")
    except (AuditError, OSError, KeyError, TypeError, ValueError,
            subprocess.TimeoutExpired) as error:
        print("J0.26 AUDIT FAILED:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
