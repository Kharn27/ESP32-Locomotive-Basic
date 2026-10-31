#!/usr/bin/env python3
"""Fail-closed SHA/size/provenance verifier for independent R1 PNG originals."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

ROM = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
CAP = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
CASES = {"control_raw_esc", "E01", "E02", "E03", "E04", "E05", "E10", "E07_candidate"}
PNG = b"\x89PNG\r\n\x1a\n"


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(root):
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["schema"] == 1
    env = manifest["environment"]
    assert env["caprice_commit"] == CAP
    assert env["rom_sha256"] == ROM
    assert env["cpc_esc_enum"] == 130
    assert env["cpc_esc_scancode"] == "0x82"
    assert {s["case"] for s in manifest["sessions"]} == CASES
    count = 0
    for session in manifest["sessions"]:
        case = session["case"]
        folder = root / case
        events = json.loads((folder / "events.json").read_text())
        assert session["program"] == events["program"], "PROGRAM_MISMATCH"
        assert session["steps"] == events["steps"], "STEPS_MISMATCH"
        assert len(session["images"]) == len(events["checkpoint_labels"])
        assert session["capture_status"] == "PNG_ACQUIRED_NOT_YET_TRANSCRIBED"
        for filename, key in (("events.json", "events_sha256"),
                              ("cap32.cfg", "config_sha256"),
                              ("caprice.log", "log_sha256")):
            if digest(folder / filename) != session[key]:
                raise ValueError("R1_SHA_MISMATCH " + case + "/" + filename)
        for frame, label in zip(session["images"], events["checkpoint_labels"]):
            name = frame["original_png"]
            target = root / name
            if name.startswith("/") or ".." in Path(name).parts or target.parent != folder:
                raise ValueError("R1_BAD_IMAGE_PATH " + name)
            if frame["checkpoint"] != label:
                raise ValueError("R1_CHECKPOINT_MISMATCH " + name)
            if target.stat().st_size != frame["bytes"] or digest(target) != frame["sha256"]:
                raise ValueError("R1_SHA_MISMATCH " + name)
            if not target.read_bytes().startswith(PNG):
                raise ValueError("R1_NOT_PNG " + name)
            count += 1
    return count, manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    count, manifest = verify(a.evidence.resolve())
    if a.self_test:
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "mutated"
            shutil.copytree(a.evidence.resolve(), copy)
            first = copy / manifest["sessions"][0]["images"][0]["original_png"]
            raw = bytearray(first.read_bytes())
            raw[-1] ^= 1
            first.write_bytes(raw)
            try:
                verify(copy)
            except ValueError as exc:
                assert "R1_SHA_MISMATCH" in str(exc), str(exc)
                print("R1_MUTATED_PNG_REJECTED")
            else:
                raise AssertionError("R1_FALSE_PNG_ACCEPTED")
    print("R1_INDEPENDENT_PNG_SHA_VERIFIED", count, "CANDIDATE_ONLY_NO_CPC_VERDICT")


if __name__ == "__main__":
    main()
