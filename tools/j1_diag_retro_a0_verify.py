#!/usr/bin/env python3
"""J1-DIAG-RETRO-A0: fail-closed inspection of preserved CPC screen witnesses.

Does NOT OCR screenshots, run Caprice32, or infer CPC codes from BEStatus.
Image descriptions are human transcriptions anchored to immutable sha256 PNGs.
Exit nonzero if anchors, original/repeat, numerics or native enum coverage drift.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "tests/diag_retro_a0_matrix.json"
# Independent post-observation anchors. Do not derive these from matrix JSON.
ANCHORS = {
    "GOSUB-MISSING": ("936c82670d51b34adbc91456e56bbf7eba7dfe92ffb411939369caabc3b5132e",
                      "Line does not exist in 10", 8, 10, True),
    "RETURN-10": ("6c48f33728a64fcc00daaf2388e20b6222609578edc5cfdd76e9816a8bbf8e83",
                  "Unexpected RETURN in 10", 3, 10, True),
    "RETURN-20": ("f217d197ebaa6a77a959765b7d0dff67fa072520f4ba9013fb74b45c2b53412c",
                  "Unexpected RETURN in 20", 3, 20, True),
    "NEXT-ORPHAN": ("c2608f8885239234d43a3c1dd653b73a29cc2364a0a7579967e7ce8a47da2700",
                    "Unexpected NEXT in 20", 1, 20, True),
    "NEXT-MISMATCH": ("7c85d54069bb37cc47af3c520522b3cf78232486877a44f6bc42c2757015f6d7",
                      "Unexpected NEXT in 30", 1, 30, True),
    "DIV-1-0": ("3ce555de3fbcadae08dc91bb16a8cbe21d4afa0abef8001cd7094119956c1ecd",
                 "Division by zero in 20", 11, 20, False),
    "DIV-0-0": ("c129009be2ce2bb02ac244d1ce27d6a2c3dfefcc40b7e000bfafd5661e3bae8e",
                 "Division by zero in 20", 11, 20, False),
}
ALLOWED_SOURCE_PREFIX = "tests/fixtures/cpc6128/"
IMAGE_HEADER = b"\x89PNG\r\n\x1a\n"


def require(condition, label):
    if not condition:
        raise ValueError(label)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def image_matches(raw, expected):
    return raw.startswith(IMAGE_HEADER) and digest(raw) == expected


def check_witness_metadata(w):
    require(w["id"] in ANCHORS, "UNEXPECTED_CPC_SCREEN_WITNESS")
    sha, wording, err, erl, paired = ANCHORS[w["id"]]
    require(w["provenance"] == "CPC_SCREEN_OBSERVED",
            "FABRICATED_SCREEN_PROVENANCE")
    require(w["evidence"] == "CPC_ROM_BACKED_ARCHIVE_PNG_REVIEW_2026_10_31",
            "UNAPPROVED_SCREEN_TRANSCRIPTION")
    require(w["run_png_sha256"] == sha, "SCREEN_HASH_ANCHOR_CHANGED")
    require(w["cpc_text"] == wording, "UNREVIEWED_WORDING_CHANGED")
    require(w["cpc_err"] == err and w["cpc_erl"] == erl,
            "UNREVIEWED_CPC_ERR_ERL_CHANGED")
    require(w["double_capture"] is paired, "CAPTURE_TOPOLOGY_CHANGED")
    require(w["cpc_ready"] == "Ready", "UNREVIEWED_READY_CHANGED")
    require(w["status"].startswith("BE_"), "WITNESS_STATUS_NOT_NATIVE")
    require(w["archive"].startswith(ALLOWED_SOURCE_PREFIX) and
            ".." not in w["archive"].split("/"), "ARCHIVE_PATH_INVALID")
    return sha


def actual_statuses(path, name, prefix):
    text = path.read_text(encoding="utf-8")
    pattern = r"typedef\s+enum\s*\{(.*?)\}\s*" + re.escape(name) + r"\s*;"
    match = re.search(pattern, text, re.S)
    require(match is not None, "MISSING_ENUM_" + name)
    values = re.findall(r"\b" + prefix + r"[A-Z0-9_]+\b", match.group(1))
    return set(values)


def verify_matrix(m):
    require(m["schema_version"] == 1 and m["mission"] ==
            "J1-DIAG-RETRO-A0", "UNKNOWN_MATRIX_SCHEMA")
    status_rows = m["status_inventory"]
    statuses = [r["status"] for r in status_rows]
    require(len(statuses) == len(set(statuses)), "DUPLICATE_STATUS_ROW")
    header = ROOT / "core/basic_executor.h"
    expected = actual_statuses(header, "BEStatus", "BE_") - {"BE_OK", "BE_END"}
    require(set(statuses) == expected, "BE_STATUS_INVENTORY_DRIFT")
    # Native, session, tokenizer, storage and LIST namespaces are disjoint:
    # enumerate all host statuses but never map them to ROM codes.
    outside = m["non_executor_status_inventory"]
    host_enums = (
        ("core/basic_session_runtime.h", "BSRStatus", "BSR_"),
        ("core/basic_session.h", "BSStatus", "BS_"),
        ("core/basic_tokenizer.h", "BTStatus", "BT_"),
        ("core/basic_program.h", "BPStatus", "BP_"),
        ("core/basic_listing.h", "BLStatus", "BL_"),
    )
    expected_non_be = set()
    for path, name, prefix in host_enums:
        expected_non_be |= {(name, s) for s in actual_statuses(
            ROOT / path, name, prefix)}
    found_non_be = [(r["layer"], r["status"]) for r in outside]
    require(len(found_non_be) == len(set(found_non_be)) and
            set(found_non_be) == expected_non_be,
            "NON_EXECUTOR_STATUS_INVENTORY_DRIFT")
    require(all(r["cpc_text"] is None and
                r["semantics"] in ("CONTROL_NOT_ERROR",
                                    "HOST_STATUS_NOT_CPC_CODE") and
                r["positive"] and r["negative"] for r in outside),
            "UNANCHORED_HOST_STATUS_CPC_MAPPING")
    rows = m["witnesses"]
    require(len(rows) == len(ANCHORS) and
            {w["id"] for w in rows} == set(ANCHORS),
            "WITNESS_INVENTORY_DRIFT")
    for row in status_rows + m["extra_paths"]:
        # Error/status names in C are *not* a ROM diagnostic license.
        require(row["cpc_text"] is None, "UNANCHORED_CPC_MESSAGE")
        require(row["negative"] and row["positive"] and row["gap"],
                "UNBOUNDED_MATRIX_ROW")
    for row in rows:
        check_witness_metadata(row)
    require(any(row["id"] == "NEXT-MISMATCH" and
                "FOR" in row["gap"] and "10" in row["gap"]
                for row in rows), "MISSING_FOR_NEXT_LOCUS_WARNING")
    return rows


def verify_archive(row):
    sha = check_witness_metadata(row)
    base = ROOT / row["archive"]
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    matches = [entry for entry in manifest["captures"]
               if entry["case"] == row["case"]]
    require(len(matches) == 1, "ARCHIVE_CASE_NOT_UNIQUE")
    case = matches[0]
    if row["double_capture"]:
        for side in ("original", "repeat"):
            info = case[side]["run"]
            img = (base / side / row["case"] / "run/run.png").read_bytes()
            require(image_matches(img, sha), "ARCHIVE_RUN_SCREEN_MUTATED")
            require(info["files"]["run.png"]["sha256"] == sha,
                    "ARCHIVE_MANIFEST_SCREEN_MUTATED")
            require(info["err_probe"] == row["cpc_err"] and
                    info["erl_probe"] == row["cpc_erl"],
                    "ARCHIVE_ERR_ERL_NUMERIC_DRIFT")
            printer = (base / side / row["case"] / "run/printer.dat").read_bytes()
            require(digest(printer) == info["files"]["printer.dat"]["sha256"],
                    "ARCHIVE_PRINTER_MUTATED")
        original = (base / "original" / row["case"] / "run/run.png").read_bytes()
        repeated = (base / "repeat" / row["case"] / "run/run.png").read_bytes()
        require(original == repeated, "CPC_SCREEN_ORIGINAL_REPEAT_DISAGREE")
    else:
        # J1.5-A has a single independent RUN process per case, not two
        # equivalent RUN screenshots. Its printer probes ERR and B%, NOT ERL.
        info = case["run"]
        img = (base / row["case"] / "run/run.png").read_bytes()
        require(image_matches(img, sha), "ARCHIVE_RUN_SCREEN_MUTATED")
        require(info["files"]["run.png"]["sha256"] == sha,
                "ARCHIVE_MANIFEST_SCREEN_MUTATED")
        require(info["err_probe"] == row["cpc_err"], "ARCHIVE_ERR_NUMERIC_DRIFT")
        printer = (base / row["case"] / "run/printer.dat").read_bytes()
        require(digest(printer) == info["files"]["printer.dat"]["sha256"],
                "ARCHIVE_PRINTER_MUTATED")
        # ERL=20 is a direct *screen* transcription; no ERL printer probe.
    return True


def self_test(m):
    rows = verify_matrix(m)
    # Mutation of a copied PNG byte must fail, as must every copied text
    # or numerical transcript. Canonical archive remains read-only.
    first = rows[0]
    p = ROOT / first["archive"] / "original" / first["case"] / "run/run.png"
    raw = p.read_bytes()
    assert image_matches(raw, ANCHORS[first["id"]][0])
    altered = bytearray(raw)
    altered[-1] ^= 1
    require(not image_matches(bytes(altered), ANCHORS[first["id"]][0]),
            "FALSE_NEGATIVE_SCREEN_CORRUPTION")
    for field, bad in (("cpc_text", "Unexpected NEXT in 10"),
                       ("cpc_err", 999), ("cpc_ready", "No ready"),
                       ("run_png_sha256", "0" * 64)):
        changed = dict(first, **{field: bad})
        try:
            check_witness_metadata(changed)
        except ValueError:
            pass
        else:
            raise ValueError("FALSE_NEGATIVE_TRANSCRIPT_CORRUPTION_" + field)
    return 5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    rows = verify_matrix(matrix)
    for row in rows:
        verify_archive(row)
    n = self_test(matrix) if args.self_test else 0
    print("J1-DIAG-RETRO-A0 PASS: {} BE statuses; {} host statuses; {} preserved PNG "
          "screen witnesses; {} original/repeat pairs; {} negative "
          "in-memory mutations. No CPC execution or new physical test."
          .format(len(matrix["status_inventory"]),
                  len(matrix["non_executor_status_inventory"]), len(rows),
                  sum(x["double_capture"] for x in rows), n))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, AssertionError) as exc:
        raise SystemExit("J1-DIAG-RETRO-A0 FAIL: " + str(exc))
