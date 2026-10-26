#!/usr/bin/env python3
"""J0.27-B2: independently sealed, six-case CPC6128 INTEGER printer oracle.

Only approved PRINT #8 B1 runs are byte exact. Screen PNGs remain
VISUAL_OBSERVATION, never surrogate text streams. No generic PRINT rule.
"""
import copy
import json
import shutil
import tempfile
from pathlib import Path
from signed_print_oracle import VALUES, digest, parse_integer

# Approved anchors kept outside BOTH archived manifests (Pilotage J0.27-B2).
APPROVED_ORIGIN = {
    "repository": "Kharn27/ESP32-Locomotive-Basic",
    "merged_pr": 50,
    "merge_commit": "5699bb1a1476d26e78334983cf778554a01b8528",
    "run_id": 40360049336,
    "artifact_id": 12668440819,
    "artifact_name": "cpc6128-j027-b1-signed-print",
    "github_sha": "a39d6083ef70fa5faac69d8105c0c1c9a3fcab44",
    "acquisition_manifest_sha256": "069da38e3b000091e5cfb5d97b79edefb34eb26b5f097c60b500765a86e8c67d",
    "acquisition_manifest_size_bytes": 31222,
}
# These ARE exact oracle bytes only for the six approved PRINTER observations.
APPROVED_PRINTER_BYTES = {
    "zero": bytes.fromhex("20 30 20 0D 0A"),
    "five": bytes.fromhex("20 35 20 0D 0A"),
    "minus_one": bytes.fromhex("2D 31 20 0D 0A"),
    "minus_twelve": bytes.fromhex("2D 31 32 20 0D 0A"),
    "max_int16": bytes.fromhex("20 33 32 37 36 37 20 0D 0A"),
    "min_int16": bytes.fromhex("2D 33 32 37 36 38 20 0D 0A"),
}

def promotion_manifest():
    return {
        "schema_version": 1,
        "phase": "J0.27-B2",
        "acquisition_phase": "J0.27-B1",
        "oracle_scope": "SIX_APPROVED_INTEGER_PRINTER_STREAMS_ONLY",
        "screen_status": "VISUAL_OBSERVATION",
        "screen_text_bytes_extracted": False,
        "printer_screen_equivalent": False,
        "origin": copy.deepcopy(APPROVED_ORIGIN),
    }

def must(condition, reason):
    if not condition:
        from signed_print_evidence import Invalid
        raise Invalid(reason)

def check_exact(base):
    """Byte identity applies to the six printer.dat files and nothing else."""
    must(set(VALUES) == set(APPROVED_PRINTER_BYTES),
         "approval table differs from six historical BASIC inputs")
    for case, expected in APPROVED_PRINTER_BYTES.items():
        path = base / (case + "_printer") / "printer.dat"
        must(path.is_file() and not path.is_symlink(),
             case + ": approved CPC printer stream absent")
        observed = path.read_bytes()
        must(observed == expected,
             case + ": B1 printer exact oracle DIFF expected=" +
             expected.hex(" ").upper() + " observed=" +
             observed.hex(" ").upper())

def verify_permanent(base):
    from signed_print_evidence import verify
    must(base.is_dir() and not base.is_symlink(), "missing permanent B2 evidence")
    promotion, acquisition = base / "manifest.json", base / "acquisition.json"
    must(promotion.is_file() and not promotion.is_symlink(),
         "missing B2 promotion manifest")
    p = json.loads(promotion.read_bytes())
    must(p.get("screen_status") == "VISUAL_OBSERVATION" and
         p.get("screen_text_bytes_extracted") is False and
         p.get("printer_screen_equivalent") is False,
         "B2 screen observation promotion forbidden")
    must(p == promotion_manifest(), "unapproved B2 promotion metadata")
    must(acquisition.is_file() and not acquisition.is_symlink(),
         "approved original acquisition missing")
    original = acquisition.read_bytes()
    must(len(original) == APPROVED_ORIGIN["acquisition_manifest_size_bytes"] and
         digest(original) == APPROVED_ORIGIN["acquisition_manifest_sha256"],
         "approved original acquisition SHA/size mismatch")
    m = json.loads(original)
    must(m.get("github_run_id") == str(APPROVED_ORIGIN["run_id"]) and
         m.get("github_sha") == APPROVED_ORIGIN["github_sha"] and
         m.get("phase") == "J0.27-B1", "approved B1 run identity mismatch")

    # Reuse UNMODIFIED B1 validator: provenance, 12 independent sessions,
    # source, command chronology, PNG integrity, channel isolation, raw SHA,
    # sizes, exact file inventory. Stage acquisition under its original name.
    with tempfile.TemporaryDirectory(prefix="j027b2-check-") as temp:
        stage = Path(temp) / "b1"
        shutil.copytree(base, stage, symlinks=True)
        (stage / "manifest.json").write_bytes(original)
        (stage / "acquisition.json").unlink()
        verify(stage, require_six_prints=True)
    check_exact(base)
    print("PASS PERMANENT J0.27-B2 SEALED SIX-CASE PRINTER ORACLE", flush=True)

def self_test_permanent(base):
    """Each mutation starts from a FULL independently validated B2 copy.

    Formatting tests temporarily lift only the OUTER acquisition seal in a
    disposable copy. Mutated file SHA/size and derived observation are
    recalculated: the exact oracle, not a trivial stale hash, must reject.
    """
    formatting = {
        "minus_sign_removed": ("minus_twelve", "31 32 20 0D 0A"),
        "leading_space_negative": ("minus_one", "20 2D 31 20 0D 0A"),
        "trailing_space_removed": ("five", "20 35 0D 0A"),
        "crlf_to_lf": ("zero", "20 30 20 0A"),
        "different_digit": ("max_int16", "20 33 32 37 36 38 20 0D 0A"),
    }
    from signed_print_evidence import Invalid, verify
    with tempfile.TemporaryDirectory(prefix="j027b2-negative-") as td:
        for name, (case, raw_hex) in formatting.items():
            dest = Path(td) / name
            shutil.copytree(base, dest)
            verify_permanent(dest)
            original_manifest = (dest / "acquisition.json").read_bytes()
            (dest / "manifest.json").write_bytes(original_manifest)
            (dest / "acquisition.json").unlink()
            verify(dest, require_six_prints=True)  # valid initial unsealed B1
            m = json.loads(original_manifest)
            entry = next(x for x in m["captures"]
                         if x["id"] == case + "_printer")
            path = dest / (case + "_printer") / "printer.dat"
            expected = path.read_bytes()
            must(expected == APPROVED_PRINTER_BYTES[case],
                 name + ": original printer bytes not approved")
            changed = bytes.fromhex(raw_hex)
            must(changed != expected, name + ": ineffective mutation")
            path.write_bytes(changed)
            entry["files"]["printer.dat"] = {
                "size_bytes": len(changed), "sha256": digest(changed)}
            entry["printer_raw_hex"] = changed.hex(" ").upper()
            entry["printer_observation"] = parse_integer(changed)
            (dest / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
            must(path.stat().st_size == entry["files"]["printer.dat"]["size_bytes"] and
                 digest(path.read_bytes()) == entry["files"]["printer.dat"]["sha256"],
                 name + ": stale forged descriptor")
            reason = (case + ": B1 printer exact oracle DIFF expected=" +
                      expected.hex(" ").upper() + " observed=" +
                      changed.hex(" ").upper())
            try:
                # Byte oracle tested first because changing a digit/sign also
                # deliberately changes the semantic value in the B1 validator.
                check_exact(dest)
            except Invalid as exc:
                must(str(exc) == reason,
                     name + ": wrong rejection: " + str(exc))
                print("PASS EXPECTED_FORMAT_REJECTION", name, flush=True)
            else:
                must(False, name + ": forged formatting accepted")

        archives = {
            "missing_screen_png": "minus_one_screen: missing evidence file screen.png",
            "extra_unapproved_file": "unexpected/missing evidence file inventory",
            "original_sha_forged": "approved original acquisition SHA/size mismatch",
            "artifact_id_forged": "unapproved B2 promotion metadata",
            "screen_promoted_to_bytes": "B2 screen observation promotion forbidden",
            "acquisition_missing": "approved original acquisition missing",
        }
        for name, reason in archives.items():
            dest = Path(td) / name
            shutil.copytree(base, dest)
            verify_permanent(dest)
            if name == "missing_screen_png":
                (dest / "minus_one_screen" / "screen.png").unlink()
            elif name == "extra_unapproved_file":
                (dest / "unapproved.bin").write_bytes(b"unexpected")
            elif name == "original_sha_forged":
                path = dest / "acquisition.json"
                path.write_bytes(path.read_bytes() + b"\n")
            elif name == "acquisition_missing":
                (dest / "acquisition.json").unlink()
            else:
                path = dest / "manifest.json"
                wrapper = json.loads(path.read_bytes())
                if name == "artifact_id_forged":
                    wrapper["origin"]["artifact_id"] += 1
                else:
                    wrapper["screen_text_bytes_extracted"] = True
                path.write_text(json.dumps(wrapper, indent=2) + "\n")
            try:
                verify_permanent(dest)
            except Invalid as exc:
                must(str(exc) == reason,
                     name + ": wrong rejection: " + str(exc) + " != " + reason)
                print("PASS EXPECTED_ARCHIVE_REJECTION", name, flush=True)
            else:
                must(False, name + ": forged archive accepted")
