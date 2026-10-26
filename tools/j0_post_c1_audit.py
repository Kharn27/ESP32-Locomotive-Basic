#!/usr/bin/env python3
"""J0.28: post-C1 J0 vertical-slice audit; NEVER an automatic phase gate.

Archived pre-C1 stdout is deliberately NOT compared to the new CLI output.
Only CPC printer *presentation*, excluding its CRLF terminator, is compared
with Linux stdout presentation, excluding LF. CPC screen pixels stay visual.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/oracles"))
from signed_print_evidence import Invalid as SignedInvalid  # noqa: E402
from signed_print_permanent import (  # noqa: E402
    APPROVED_PRINTER_BYTES, verify_permanent,
)
from j0_exit_audit import (  # noqa: E402
    AuditError, external_validators, inspect, require,
)
from cpc_diff import validate_image  # noqa: E402

# Exactly the executable subset of the J0 vertical slice. NOT six B1 runs.
EXECUTABLE = {
    "c_integer_add": ("sources/c_integer_add.bas", 5, 4),
    "d_self_reference": ("sources/d_self_reference.bas", 2, 4),
    "zero": ("../oracles/inputs/j027_b1/zero.bas", 0, 3),
    "five": ("../oracles/inputs/j027_b1/five.bas", 5, 3),
}
# This immutable J0 classification describes ARCHIVED observations, not the
# supported program inputs of later native engines.
B1_UNSUPPORTED = ("minus_one", "minus_twelve", "max_int16", "min_int16")
# J1.1 adds executable negatives; old archives MUST still say UNSUPPORTED.
CURRENT_B1_UNSUPPORTED = ("max_int16", "min_int16")


def current_capabilities():
    filename = ROOT / "tests/oracles/j1_native_capabilities.json"
    data = json.loads(filename.read_bytes())
    require(data.get("schema_version") == 1 and data.get("phase") == "J1.1",
            "CURRENT_CAPABILITY_SCHEMA_CHANGED")
    require(data.get("archived_B1_native_status") ==
            {name: "UNSUPPORTED" for name in B1_UNSUPPORTED},
            "ARCHIVED_B1_STATUS_REWRITTEN")
    require(data.get("current_native_B1") ==
            {"minus_one": "EXECUTABLE", "minus_twelve": "EXECUTABLE",
             "max_int16": "UNSUPPORTED", "min_int16": "UNSUPPORTED"},
            "CURRENT_B1_CAPABILITY_PROMOTION_FORBIDDEN")
    require(data.get("historical_LIST_RUN") == "UNVERIFIED" and
            data.get("presentation_comparison") == "MATCH_PRESENTATION" and
            data.get("screen_transport") == "VISUAL_OBSERVATION",
            "HISTORICAL_CHANNEL_PROMOTION_FORBIDDEN")
    return data
HISTORICAL_CASES = (
    "a_print_constants", "b_integer_scalar", "c_integer_add",
    "d_self_reference", "e_goto", "f_let_spacing",
    "f_constant_boundary", "f_mixed_case", "g_uninitialized",
)
# These are NEW audit conclusions, never rewrites of archived classifications.
POLICY = {
    "presentation": {name: "MATCH_PRESENTATION" for name in EXECUTABLE},
    "b1_non_executable": {name: "UNSUPPORTED" for name in B1_UNSUPPORTED},
    "historical": {name + "/" + operation: "UNVERIFIED"
                   for name in HISTORICAL_CASES
                   for operation in ("LIST", "RUN")},
}


def bytes_hex(data):
    return data.hex(" ").upper()


def reject_if_invalid_policy(policy):
    for key, value in POLICY["presentation"].items():
        require(policy.get("presentation", {}).get(key) == value,
                key + ": CROSS_TRANSPORT_CLASSIFICATION_FORBIDDEN")
    require(set(policy.get("presentation", {})) == set(EXECUTABLE),
            "PRESENTATION_SCOPE_EXCEEDED")
    for key, value in POLICY["b1_non_executable"].items():
        require(policy.get("b1_non_executable", {}).get(key) == value,
                key + ": B1_UNSUPPORTED_PROMOTION_FORBIDDEN")
    require(set(policy.get("b1_non_executable", {})) == set(B1_UNSUPPORTED),
            "B1_UNSUPPORTED_SET_CHANGED")
    for key, value in POLICY["historical"].items():
        require(policy.get("historical", {}).get(key) == value,
                key + ": HISTORICAL_UNVERIFIED_PROMOTION_FORBIDDEN")
    require(set(policy.get("historical", {})) == set(POLICY["historical"]),
            "HISTORICAL_18_OPERATION_SCOPE_CHANGED")


def compare_presentation(case, cpc, native, expected):
    """Validate channels BEFORE comparing numeric data. Never strip whitespace."""
    require(cpc.endswith(b"\r\n"), case + ": CPC_TRANSPORT_NOT_CRLF")
    require(native.endswith(b"\n") and not native.endswith(b"\r\n"),
            case + ": NATIVE_TRANSPORT_NOT_LF")
    cpc_body, native_body = cpc[:-2], native[:-1]
    require(cpc_body == expected, case + ": CPC_PRESENTATION_CHANGED")
    require(native_body == expected, case + ": NATIVE_PRESENTATION_MISMATCH")
    require(cpc_body == native_body, case + ": PRESENTATION_DIFF")
    require(cpc != native, case + ": CROSS_TRANSPORT_EXACT_FORBIDDEN")
    return "MATCH_PRESENTATION"


def command(binary, input_bytes, label):
    try:
        result = subprocess.run([str(binary)], input=input_bytes,
                                capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuditError(label + ": CLI_EXECUTION_FAILED: " + str(exc)) from exc
    require(result.returncode == 0 and b"[cli:error]" not in result.stderr,
            label + ": CLI_REJECTED_OR_FAILED " +
            result.stderr[:160].decode("ascii", errors="replace"))
    return result


def run_case(name, spec, cpc_root, cli, image_cli, printer):
    relative, value, steps = spec
    if name in ("zero", "five"):
        source = ROOT / "tests/oracles/inputs/j027_b1" / (name + ".bas")
        require(source.read_bytes() ==
                (f"10 B%={value}\n20 PRINT B%\n30 END\n").encode("ascii"),
                name + ": B1_INPUT_CHANGED")
    else:
        source = cpc_root / relative
        canonical = (
            b"10 A%=2\n20 B%=A%+3\n30 PRINT B%\n40 END\n"
            if name == "c_integer_add" else
            b"10 B%=1\n20 B%=B%+1\n30 PRINT B%\n40 END\n"
        )
        require(source.read_bytes() == canonical, name + ": C6_INPUT_CHANGED")
    source_bytes = source.read_bytes()
    # Tokenize and store through an ACTUAL C99 binary, not an in-memory fixture.
    image = command(image_cli, source_bytes, name + "/TOKENS").stdout
    try:
        validate_image(image)
    except Exception as exc:
        raise AuditError(name + ": C99_TOKEN_IMAGE_INVALID") from exc
    if name in ("c_integer_add", "d_self_reference"):
        require(image == (cpc_root / "token_ram" / name / "program.bin").read_bytes(),
                name + ": TOKEN_IMAGE_DIFF_FROM_CPC")
    # LIST and RUN are separate real processes; stdout has no host prompts.
    listed = command(cli, source_bytes + b"LIST\n:quit\n", name + "/LIST")
    require(listed.stdout == source_bytes and
            b"[cli] LIST\n" in listed.stderr,
            name + ": LIST_NOT_RESTORED")
    ran = command(cli, source_bytes +
                  (f"RUN\n:step {steps}\n:step\n:quit\n").encode("ascii"),
                  name + "/RUN")
    require((f"[cli] STEPPED {steps}\n").encode("ascii") in ran.stderr and
            b"[cli] END\n" in ran.stderr and
            b"[cli] RUNNING\n" in ran.stderr,
            name + ": RUN_DID_NOT_END")
    expected_body = b" " + str(value).encode("ascii") + b" "
    classification = compare_presentation(
        name, printer, ran.stdout, expected_body)
    print("PASS J0.28", name, "TOKENS=CHECKED LIST=CHECKED RUN=END",
          "VALUE=" + str(value), "CLASS=" + classification,
          "CPC_PRINTER=" + bytes_hex(printer),
          "C99_STDOUT=" + bytes_hex(ran.stdout),
          "TRANSPORT=CPC_CRLF_VS_C99_LF", flush=True)



def refuse_non_executable_b1(cli):
    """Exercise the four historical B1 programs; DO NOT promote them."""
    current_capabilities()
    for case in CURRENT_B1_UNSUPPORTED:
        value = {"minus_one": -1, "minus_twelve": -12,
                 "max_int16": 32767, "min_int16": -32768}[case]
        source = (ROOT / "tests/oracles/inputs/j027_b1" /
                  (case + ".bas")).read_bytes()
        require(source ==
                (f"10 B%={value}\n20 PRINT B%\n30 END\n").encode("ascii"),
                case + ": UNSUPPORTED_B1_SOURCE_CHANGED")
        try:
            result = subprocess.run([str(cli)],
                                    input=source + b"RUN\n:step 100\n:quit\n",
                                    capture_output=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AuditError(case + ": UNSUPPORTED_CLI_PROCESS_FAILED") from exc
        require(result.returncode == 0 and
                b"[cli:error]" in result.stderr and not result.stdout,
                case + ": UNSUPPORTED_B1_WAS_EXECUTED_OR_MISCLASSIFIED")
        print("PASS J0.28 B1_REMAINS_UNSUPPORTED", case, flush=True)


def integrity(cpc_root, independent=True):
    # C6/C7/C8 classification freezes, original C6 pre-C1 gap, 18 UNVERIFIED.
    print(inspect(cpc_root).splitlines()[0], flush=True)
    verify_permanent(cpc_root / "signed_print")
    if independent:
        # Reuse preexisting independent SHA/provenance validators, not a new
        # partially duplicated archivist.
        external_validators()
    b1 = json.loads((cpc_root / "signed_print/acquisition.json").read_bytes())
    screen = {item["case"]: item for item in b1["captures"]
              if item["mode"] == "screen"}
    require(set(screen) == set(APPROVED_PRINTER_BYTES),
            "B1_SCREEN_CAPTURE_SET_CHANGED")
    for name in B1_UNSUPPORTED:
        require(screen[name]["native_status"] == "UNSUPPORTED",
                name + ": ARCHIVED_B1_UNSUPPORTED_PROMOTED")
    for name in ("zero", "five"):
        require(screen[name]["native_status"] == "OBSERVED",
                name + ": ARCHIVED_B1_OBSERVATION_CHANGED")
    print("PASS SEALED CPC PROVENANCE 8 TOKENS / C6 C7 C8 / B2 SIX PRINTERS", flush=True)


def expect_error(name, function, expected):
    try:
        function()
    except (AuditError, SignedInvalid) as exc:
        require(str(exc) == expected,
                name + ": WRONG_REJECTION_CAUSE: " + str(exc))
        print("PASS EXPECTED_REJECTION", name, "cause=" + str(exc),
              flush=True)
    else:
        raise AuditError(name + ": FORGERY_ACCEPTED")


def negative_tests(cpc_root):
    with tempfile.TemporaryDirectory(prefix="j028-audit-") as directory:
        dest = Path(directory) / "cpc6128"
        shutil.copytree(cpc_root, dest, symlinks=True)
        # A full untouched archive copy MUST pass before any mutation.
        integrity(dest, independent=False)
        reject_if_invalid_policy(copy.deepcopy(POLICY))
        current_capabilities()
        print("PASS POSITIVE INTACT_TEMP_COPY", flush=True)

        for name, case, cpc, native, expected, reason in (
            ("missing_positive_leading", "five", b" 5 \r\n", b"5 \n", b" 5 ",
             "five: NATIVE_PRESENTATION_MISMATCH"),
            ("missing_positive_trailing", "five", b" 5 \r\n", b" 5\n", b" 5 ",
             "five: NATIVE_PRESENTATION_MISMATCH"),
            ("wrong_value", "five", b" 5 \r\n", b" 6 \n", b" 5 ",
             "five: NATIVE_PRESENTATION_MISMATCH"),
            ("wrong_sign", "five", b" 5 \r\n", b"-5 \n", b" 5 ",
             "five: NATIVE_PRESENTATION_MISMATCH"),
            ("cpc_crlf_conflated", "five", b" 5 \n", b" 5 \n", b" 5 ",
             "five: CPC_TRANSPORT_NOT_CRLF"),
            ("native_crlf_conflated", "five", b" 5 \r\n", b" 5 \r\n", b" 5 ",
             "five: NATIVE_TRANSPORT_NOT_LF"),
        ):
            expect_error(name,
                         lambda a=case, b=cpc, c=native, d=expected:
                         compare_presentation(a, b, c, d), reason)

        # Change signed B2 provenance on an already-proven-good disposable
        # archive. No permanent fixture nor its SHA is edited.
        wrapper = dest / "signed_print/manifest.json"
        document = json.loads(wrapper.read_bytes())
        document["origin"]["run_id"] += 1
        wrapper.write_text(json.dumps(document, indent=2) + "\n")
        expect_error("forged_provenance",
                     lambda: verify_permanent(dest / "signed_print"),
                     "unapproved B2 promotion metadata")

        promoted = copy.deepcopy(POLICY)
        promoted["presentation"]["five"] = "MATCH_EXACT"
        expect_error("false_cross_transport_exact",
                     lambda: reject_if_invalid_policy(promoted),
                     "five: CROSS_TRANSPORT_CLASSIFICATION_FORBIDDEN")
        promoted = copy.deepcopy(POLICY)
        promoted["b1_non_executable"]["minus_one"] = "MATCH_PRESENTATION"
        expect_error("promoted_unsupported",
                     lambda: reject_if_invalid_policy(promoted),
                     "minus_one: B1_UNSUPPORTED_PROMOTION_FORBIDDEN")
        promoted = copy.deepcopy(POLICY)
        promoted["historical"]["c_integer_add/RUN"] = "MATCH_EXACT"
        expect_error("promoted_unverified",
                     lambda: reject_if_invalid_policy(promoted),
                     "c_integer_add/RUN: HISTORICAL_UNVERIFIED_PROMOTION_FORBIDDEN")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", required=True, type=Path)
    parser.add_argument("--image-cli", required=True, type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        cli, image_cli = args.cli.resolve(), args.image_cli.resolve()
        require(cli.is_file() and image_cli.is_file(),
                "both real C99 executables required; build with CMake first")
        root = ROOT / "tests/fixtures/cpc6128"
        reject_if_invalid_policy(POLICY)
        current_capabilities()
        integrity(root)
        for name, spec in EXECUTABLE.items():
            cpc = ((root / "run_behavior" / name / "printer.dat").read_bytes()
                   if name in ("c_integer_add", "d_self_reference")
                   else (root / "signed_print" / (name + "_printer") /
                         "printer.dat").read_bytes())
            # B2 seal already validated; explicit linkage to its approved
            # independent byte table for 0 and 5.
            if name in APPROVED_PRINTER_BYTES:
                require(cpc == APPROVED_PRINTER_BYTES[name],
                        name + ": B2_APPROVED_PRINTER_BYTES_CHANGED")
            run_case(name, spec, root, cli, image_cli, cpc)
        refuse_non_executable_b1(cli)
        if args.self_test:
            negative_tests(root)
        print("PASS J0.28 FOUR EXECUTABLE CASES; 4 B1 UNSUPPORTED; "
              "18 HISTORICAL UNVERIFIED; NOT AN AUTOMATIC J0 GATE", flush=True)
    except (AuditError, SignedInvalid, OSError, ValueError, KeyError,
            TypeError, subprocess.TimeoutExpired) as exc:
        print("J0.28 AUDIT FAILED:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
