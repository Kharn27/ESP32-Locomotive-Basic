#!/usr/bin/env python3
"""J1.1 fail-closed CPC signed token / B1 printer / live C99 differential audit.

CPC RAM bytes were collected in a separate BEFORE-native-change workflow.
J0.28 archives remain historical; their UNSUPPORTED classification is immutable.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from cpc_diff import validate_image
from j0_post_c1_audit import (AuditError, B1_UNSUPPORTED, POLICY,
    compare_presentation, current_capabilities, integrity,
    reject_if_invalid_policy, require)
from signed_print_permanent import APPROVED_PRINTER_BYTES

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/j1_negative_tokens"
SPECS = {
    "minus_one": (-1, 31,
       "2cb0acf88f9eab748a1c10247379993e6979a894e1784f201939e80710a3904c",
       "ae7f11f667659dc5b06ccd5fe3dfa418306bdbec70fdb3131e29a50a0809e3b9",
       bytes.fromhex("F5 0F")),
    "minus_twelve": (-12, 32,
       "6c72b0bf1fe2a77514a456985a9a3c275581966b31e823e8ef6f3cd9bfc468a5",
       "c96aa8c415fa3972378009fb2a6c5fad1245ef112dd2bb4eea2b333f37932cfd",
       bytes.fromhex("F5 19 0C")),
}
EXPECTED_RUN = 40405671305
EXPECTED_ARTIFACT = 12690008430
EXPECTED_DIGEST = ("sha256:4682bc14f04f6541af54d23246ccda4fd0594fb93d4a659df903e673b93ee35b")
EXPECTED_MANIFEST_SHA = "ce6ad0959d3c9a5dc6ea518dc77a75f1045e2c278b4776859e1f59d88b931961"
ROM_SHA = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
PIN = "8c778bf072a06fb7c23b9cccd179041db7f79a52"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_manifest(meta):
    require(meta.get("schema_version") == 1 and
            meta.get("phase") == "J1.1-CPC6128-ROM-BASIC-1.1" and
            meta.get("acquisition_run_id") == EXPECTED_RUN and
            meta.get("artifact_id") == EXPECTED_ARTIFACT and
            meta.get("artifact_digest") == EXPECTED_DIGEST and
            meta.get("original_acquisition_manifest_sha256") == EXPECTED_MANIFEST_SHA and
            meta.get("acquisition_commit") == "55c559c365cad6ff9a7d0fbc6a06aba2bf6540dc",
            "J1_PROVENANCE_CHANGED")
    require(meta.get("caprice32_commit") == PIN and
            meta.get("rom_cpc6128_sha256") == ROM_SHA and
            meta.get("machine") == "CPC6128" and
            meta.get("basic") == "1.1" and meta.get("ram_kb") == 128 and
            meta.get("no_rom_or_snapshot_export") is True and
            meta.get("historical_archives_modified") is False and
            meta.get("historical_list_run_promoted") is False,
            "J1_ROM_OR_ARCHIVE_PROVENANCE_CHANGED")
    require(set(meta.get("cases", {})) == set(SPECS), "J1_CASE_SET_CHANGED")
    for name, (_, size, digest, source_sha, operand) in SPECS.items():
        case = meta["cases"][name]
        require(case == {
            "source": f"tests/oracles/inputs/j027_b1/{name}.bas",
            "source_sha256": source_sha,
            "program_path": f"{name}/program.bin",
            "program_sha256": digest,
            "size_bytes": size,
            "assignment_operand_hex": operand.hex(" ").upper(),
            "native_at_acquisition": "UNSUPPORTED"}, name + ": J1_PROOF_CHANGED")


def verify_raw(name, raw):
    _, size, expected_sha, _, operand = SPECS[name]
    require(len(raw) == size and sha(raw) == expected_sha,
            name + ": CPC_RAW_SHA_MISMATCH")
    # The sign/operator occurs after the CPC variable and EQUAL token.
    require(raw[9:9 + len(operand)] == operand,
            name + ": CPC_UNARY_OPERATOR_CHANGED")
    validate_image(raw)


def process(executable, data, case):
    result = subprocess.run([str(executable)], input=data, capture_output=True,
                            timeout=25, check=False)
    require(result.returncode == 0 and b"[cli:error]" not in result.stderr,
            case + ": NATIVE_CLI_FAILED " +
            result.stderr[:160].decode("ascii", errors="replace"))
    return result


def live_case(name, cli, image_cli):
    value, _, _, source_sha, _ = SPECS[name]
    source = (ROOT / "tests/oracles/inputs/j027_b1" / (name + ".bas")).read_bytes()
    require(source == (f"10 B%={value}\n20 PRINT B%\n30 END\n").encode("ascii") and
            sha(source) == source_sha, name + ": SOURCE_CHANGED")
    cpc = (EVIDENCE / name / "program.bin").read_bytes()
    verify_raw(name, cpc)
    native_img = process(image_cli, source, name + "/IMAGE").stdout
    require(native_img == cpc, name + ": NATIVE_TOKEN_IMAGE_DIFFERENT")
    listed = process(cli, source + b"LIST\n:quit\n", name + "/LIST")
    require(listed.stdout == source and b"[cli] LIST\n" in listed.stderr,
            name + ": LIST_DIFFERENT")
    ran = process(cli, source + b"RUN\n:step 3\n:step\n:quit\n", name + "/RUN")
    require(b"[cli] RUNNING\n" in ran.stderr and
            b"[cli] STEPPED 3\n" in ran.stderr and
            b"[cli] END\n" in ran.stderr, name + ": RUN_NOT_TERMINATED")
    expected = str(value).encode("ascii") + b" "
    require(ran.stdout == expected + b"\n", name + ": C99_PRINT_HEX_DIFF")
    printer = (ROOT / "tests/fixtures/cpc6128/signed_print" /
               (name + "_printer") / "printer.dat").read_bytes()
    require(printer == APPROVED_PRINTER_BYTES[name],
            name + ": APPROVED_B2_PRINTER_CHANGED")
    require(compare_presentation(name, printer, ran.stdout, expected) ==
            "MATCH_PRESENTATION", name + ": PRESENTATION_MISMATCH")
    print(f"PASS J1.1 {name} CPC_SHA256={sha(cpc)} "
          f"NATIVE_IMAGE=MATCH_EXACT PRINT=MATCH_PRESENTATION "
          f"C99_STDOUT={ran.stdout.hex(' ').upper()} "
          f"CPC_PRINTER={printer.hex(' ').upper()} LIST=YES RUN=END",
          flush=True)


def self_test(meta):
    verify_manifest(copy.deepcopy(meta))
    for name in SPECS:
        data = (EVIDENCE / name / "program.bin").read_bytes()
        verify_raw(name, data)
        changed = bytearray(data)
        changed[9] ^= 1
        try:
            verify_raw(name, bytes(changed))
        except AuditError as exc:
            require(str(exc) == name + ": CPC_RAW_SHA_MISMATCH",
                    name + ": WRONG_NEGATIVE_CAUSE")
        else:
            raise AuditError(name + ": MUTATED_CPC_ACCEPTED")
    changed = copy.deepcopy(meta)
    changed["cases"]["minus_one"]["native_at_acquisition"] = "EXECUTABLE"
    try:
        verify_manifest(changed)
    except AuditError as exc:
        require(str(exc) == "minus_one: J1_PROOF_CHANGED",
                "WRONG_PROVENANCE_NEGATIVE_CAUSE")
    else:
        raise AuditError("FORGED_HISTORIC_PROMOTION_ACCEPTED")
    changed = copy.deepcopy(meta)
    changed["acquisition_run_id"] += 1
    try:
        verify_manifest(changed)
    except AuditError as exc:
        require(str(exc) == "J1_PROVENANCE_CHANGED",
                "WRONG_RUN_NEGATIVE_CAUSE")
    else:
        raise AuditError("FORGED_RUN_ID_ACCEPTED")
    altered = copy.deepcopy(POLICY)
    altered["historical"]["c_integer_add/RUN"] = "MATCH_EXACT"
    try:
        reject_if_invalid_policy(altered)
    except AuditError as exc:
        require(str(exc) == "c_integer_add/RUN: HISTORICAL_UNVERIFIED_PROMOTION_FORBIDDEN",
                "WRONG_HISTORICAL_NEGATIVE_CAUSE")
    else:
        raise AuditError("PROMOTED_J0_HISTORICAL_OPERATION")
    print("PASS J1.1 intact proof and five specific negative forgery guards", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--image-cli", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        current_capabilities()
        reject_if_invalid_policy(POLICY)
        integrity(ROOT / "tests/fixtures/cpc6128")
        meta = json.loads((EVIDENCE / "manifest.json").read_bytes())
        verify_manifest(meta)
        for name in SPECS:
            live_case(name, args.cli, args.image_cli)
        if args.self_test:
            self_test(meta)
        print("PASS J1.1 3 CURRENT EXECUTABLE / 1 CURRENT UNSUPPORTED / "
              "4 HISTORICALLY UNSUPPORTED / 18 UNVERIFIED", flush=True)
    except (AuditError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as err:
        print("J1.1 SIGNED AUDIT FAILED:", err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
