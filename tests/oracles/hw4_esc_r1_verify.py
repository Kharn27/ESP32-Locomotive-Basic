#!/usr/bin/env python3
"""Fail-closed R1 archive verifier. The immutable manifest seal is external.

A fresh Caprice32 acquisition is only a candidate; the original archive must
be checked with --expected-manifest-sha256 from an independently pinned CI step.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

ROM = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
CAP = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
CASES = {"control_raw_esc", "E01", "E02", "E03", "E04", "E05",
         "E10", "E07_candidate"}
PNG = b"\x89PNG\r\n\x1a\n"
ORIGINAL_COUNT = 29


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root, expected_manifest_sha256=None):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "R1_ARCHIVE_MISSING")
    manifest_file = root / "manifest.json"
    require(manifest_file.is_file() and not manifest_file.is_symlink(),
            "R1_MANIFEST_MISSING")
    if expected_manifest_sha256 is not None:
        require(bool(re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256)),
                "R1_SEAL_INVALID")
        require(digest(manifest_file) == expected_manifest_sha256,
                "R1_EXTERNAL_MANIFEST_SEAL_MISMATCH")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    require(manifest["schema"] == 1, "R1_SCHEMA_MISMATCH")
    env = manifest["environment"]
    require(env["caprice_commit"] == CAP and env["rom_sha256"] == ROM,
            "R1_PROVENANCE_MISMATCH")
    require(env["cpc_esc_enum"] == 130 and env["cpc_esc_scancode"] == "0x82",
            "R1_ESC_KEY_MISMATCH")
    sessions = manifest["sessions"]
    require(len(sessions) == len(CASES) and
            {s["case"] for s in sessions} == CASES, "R1_SESSIONS_MISMATCH")
    expected_files = {"manifest.json"}
    count = 0
    for session in sessions:
        case = session["case"]
        folder = root / case
        require(folder.is_dir() and not folder.is_symlink(),
                "R1_SESSION_MISSING " + case)
        events_path = folder / "events.json"
        events = json.loads(events_path.read_text(encoding="utf-8"))
        require(session["program"] == events["program"], "R1_PROGRAM_MISMATCH")
        require(session["steps"] == events["steps"], "R1_STEPS_MISMATCH")
        require(len(session["images"]) == len(events["checkpoint_labels"]),
                "R1_CHECKPOINT_COUNT_MISMATCH")
        require(session["capture_status"] == "PNG_ACQUIRED_NOT_YET_TRANSCRIBED",
                "R1_STATUS_MISMATCH")
        for filename, key in (("events.json", "events_sha256"),
                              ("cap32.cfg", "config_sha256"),
                              ("caprice.log", "log_sha256")):
            rel = case + "/" + filename
            target = folder / filename
            require(target.is_file() and not target.is_symlink() and
                    digest(target) == session[key],
                    "R1_SHA_MISMATCH " + rel)
            expected_files.add(rel)
        for frame, label in zip(session["images"], events["checkpoint_labels"]):
            name = frame["original_png"]
            target = root / name
            require(not name.startswith("/") and ".." not in Path(name).parts
                    and target.parent == folder and
                    re.fullmatch(r"screenshot_[0-9]{8}_[0-9]{6}\.png",
                                 target.name) is not None,
                    "R1_BAD_IMAGE_PATH " + name)
            require(name not in expected_files, "R1_DUPLICATE_PNG " + name)
            require(frame["checkpoint"] == label,
                    "R1_CHECKPOINT_MISMATCH " + name)
            require(target.is_file() and not target.is_symlink() and
                    target.stat().st_size == frame["bytes"] and
                    digest(target) == frame["sha256"],
                    "R1_SHA_MISMATCH " + name)
            require(target.read_bytes().startswith(PNG),
                    "R1_NOT_PNG " + name)
            expected_files.add(name)
            count += 1
    require(count == ORIGINAL_COUNT, "R1_ORIGINAL_COUNT_MISMATCH")
    # Do not silently ignore undeclared, missing or extra archive content.
    actual_files = {p.relative_to(root).as_posix()
                    for p in root.rglob("*") if p.is_file() or p.is_symlink()}
    require(actual_files == expected_files, "R1_ARCHIVE_FILE_SET_MISMATCH")
    actual_dirs = {p.relative_to(root).as_posix()
                   for p in root.rglob("*") if p.is_dir()}
    require(actual_dirs == CASES, "R1_ARCHIVE_DIR_SET_MISMATCH")
    return count, manifest


def assert_rejected(root, expected_sha, label, mutation, message):
    with tempfile.TemporaryDirectory() as directory:
        copy = Path(directory) / "mutated"
        shutil.copytree(root, copy)
        mutation(copy)
        try:
            verify(copy, expected_sha)
        except ValueError as exc:
            require(message in str(exc),
                    "R1_NEGATIVE_WRONG_FAILURE " + label + " " + str(exc))
            print(label)
        else:
            raise ValueError("R1_FALSE_ARCHIVE_ACCEPTED " + label)


def self_test(root, seal, manifest):
    name = manifest["sessions"][0]["images"][0]["original_png"]

    def corrupt_png(folder):
        target = folder / name
        data = bytearray(target.read_bytes())
        data[-1] ^= 1
        target.write_bytes(data)

    assert_rejected(root, seal, "R1_MUTATED_PNG_REJECTED",
                    corrupt_png, "R1_SHA_MISMATCH")

    def corrupt_both(folder):
        corrupt_png(folder)
        mf = folder / "manifest.json"
        data = json.loads(mf.read_text(encoding="utf-8"))
        data["sessions"][0]["images"][0]["sha256"] = digest(folder / name)
        mf.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # This test requires an external seal: no circular self-signed verdict.
    if seal is not None:
        assert_rejected(root, seal, "R1_COORDINATED_PNG_MANIFEST_REJECTED",
                        corrupt_both, "R1_EXTERNAL_MANIFEST_SEAL_MISMATCH")
        def corrupt_manifest(folder):
            mf = folder / "manifest.json"
            mf.write_bytes(mf.read_bytes() + b"\n")
        assert_rejected(root, seal, "R1_MANIFEST_ONLY_REJECTED",
                        corrupt_manifest, "R1_EXTERNAL_MANIFEST_SEAL_MISMATCH")

    def remove_png(folder):
        (folder / name).unlink()
    assert_rejected(root, seal, "R1_MISSING_PNG_REJECTED",
                    remove_png, "R1_SHA_MISMATCH")

    def add_png(folder):
        (folder / "E01" / "unknown.png").write_bytes(PNG + b"extra")
    assert_rejected(root, seal, "R1_EXTRA_FILE_REJECTED",
                    add_png, "R1_ARCHIVE_FILE_SET_MISMATCH")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--self-test", action="store_true")
    a = parser.parse_args()
    count, manifest = verify(a.evidence, a.expected_manifest_sha256)
    if a.self_test:
        self_test(a.evidence, a.expected_manifest_sha256, manifest)
    print("R1_INDEPENDENT_PNG_SHA_VERIFIED", count,
          "EXTERNAL_SEAL_VERIFIED" if a.expected_manifest_sha256
          else "CANDIDATE_ONLY_NO_CPC_VERDICT")


if __name__ == "__main__":
    main()
