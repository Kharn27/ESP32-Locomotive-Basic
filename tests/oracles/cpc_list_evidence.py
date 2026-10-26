#!/usr/bin/env python3
"""C7 integrity/origin oracle for authentic CPC LIST-to-printer observations.

Differential equivalence is strictly byte-level. A CPC printer is not the
CPC screen. A structurally valid DIFF is archivable (NOT a compatibility PASS).
"""
import argparse
import configparser
import copy
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

from list_printer_oracle import (CASES, PIN, ROM_SHA, AMSDOS_SHA, ROOT,
                                 EXPECTED_FILES, PNG, digest, difference, classify)

# Independently approved original acquisition identity. NEVER derived from the
# manifest or payload being verified (including coordinated SHA forgeries).
APPROVED_ACQUISITION_SHA256 = "932f9cdc72ddb529d2f3bfb4f28457f8217c18d561ad95947d38c5c73d27750e"
APPROVED_GITHUB_RUN_ID = 40284150801
APPROVED_ARTIFACT_ID = 12633570767
ALLOWED = {"MATCH_EXACT", "DIFF", "UNVERIFIED", "UNSUPPORTED"}


class Invalid(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def read_json(path):
    return json.loads(path.read_bytes())


def verify(base, permanent=False):
    require(base.is_dir(), "evidence directory missing")
    m = read_json(base / "manifest.json")
    require(m.get("schema_version") == 1 and m.get("phase") == "J0.24-C7",
            "C7 schema mismatch")
    require(m.get("screen_bytes_captured") is False and
            m.get("printer_screen_byte_equivalence") is False,
            "printer/screen conflation")
    o = m.get("oracle", {})
    require(o.get("name") == "Caprice32" and o.get("commit") == PIN and
            o.get("model") == "CPC6128" and o.get("ram_kb") == 128 and
            o.get("basic") == "1.1" and o.get("rom_sha256") == ROM_SHA and
            o.get("amsdos_sha256") == AMSDOS_SHA and
            o.get("rom_archived") is False and o.get("snapshot_archived") is False and
            "4.6.0" in o.get("version_output", ""),
            "Caprice32/ROM identity unapproved")
    run_id, sha = m.get("github_run_id"), m.get("github_sha")
    if permanent:
        require(type(APPROVED_GITHUB_RUN_ID) is int and
                type(APPROVED_ARTIFACT_ID) is int and
                isinstance(APPROVED_ACQUISITION_SHA256, str) and
                re.fullmatch(r"[0-9a-f]{64}", APPROVED_ACQUISITION_SHA256),
                "NO INDEPENDENT C7 APPROVAL ANCHORS")
        require(run_id == str(APPROVED_GITHUB_RUN_ID) and
                isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha),
                "unapproved permanent GitHub run identity")
        original = m.get("original_artifact", {})
        require(type(original.get("run_id")) is int and
                original["run_id"] == APPROVED_GITHUB_RUN_ID and
                type(original.get("artifact_id")) is int and
                original["artifact_id"] == APPROVED_ARTIFACT_ID and
                original.get("run_url") ==
                "https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/" +
                str(APPROVED_GITHUB_RUN_ID),
                "unapproved acquisition run or artifact")
        acq = (base / "acquisition.json").read_bytes()
        require(digest(acq) == APPROVED_ACQUISITION_SHA256 and
                original.get("acquisition_sha256") == APPROVED_ACQUISITION_SHA256,
                "C7 immutable acquisition digest mismatch")
        historical = read_json(base / "acquisition.json")
        copy_m = copy.deepcopy(m)
        copy_m.pop("original_artifact")
        require(historical == copy_m,
                "permanent manifest differs from original acquisition")
    else:
        require((run_id is None and sha is None) or
                (isinstance(run_id, str) and
                 re.fullmatch(r"[0-9]+", run_id) is not None and
                 isinstance(sha, str) and
                 re.fullmatch(r"[0-9a-f]{40}", sha) is not None),
                "malformed partial local GitHub identity")
    captures = m.get("captures")
    require(isinstance(captures, list) and len(captures) == 2 and
            {c.get("case") for c in captures} == set(CASES),
            "both independent CPC cases required")
    inventory = {"manifest.json"}
    if permanent:
        inventory.add("acquisition.json")
    result = {}
    for c in captures:
        case = c["case"]
        path, sha_source, cmd = CASES[case]
        work = base / case
        require(work.is_dir() and not work.is_symlink(),
                case + ": missing/untrusted case directory")
        source = (ROOT / path).read_bytes()
        require(digest(source) == sha_source and source.endswith(b"\n") and b"\r" not in source,
                case + ": historical source mismatched")
        commands = source.decode("ascii").splitlines() + [
            cmd, "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"]
        require(c.get("source_path") == path and
                c.get("source_sha256") == sha_source and
                c.get("commands") == commands and
                c.get("operation") == "LIST_PRINTER_PROBE" and
                c.get("list_command_cpc") == cmd and
                c.get("list_command_native") == "LIST" and
                c.get("selection_scope") ==
                "all stored historical lines, identical numbered range" and
                c.get("comparison") == "exact-bytes" and
                c.get("classification") in ALLOWED and
                c.get("cpc_channel") == "printer.dat: CPC direct LIST <range>,#8 (no RUN)" and
                c.get("native_channel") == "native.stdout.bin: C99 CLI LIST (no RUN)" and
                c.get("screen_channel") == "screen.png: visual only, NOT byte-exact text",
                case + ": operation, command, or evidence channels altered")
        require(set(c.get("files", {})) == set(EXPECTED_FILES),
                case + ": evidence descriptors incomplete")
        raw = {}
        for filename in EXPECTED_FILES:
            f = work / filename
            require(f.is_file() and not f.is_symlink() and
                    f.resolve().is_relative_to(base.resolve()),
                    case + ": missing/unsafe " + filename)
            data = f.read_bytes()
            meta = c["files"][filename]
            require(type(meta.get("size_bytes")) is int and
                    len(data) == meta["size_bytes"] and
                    meta.get("sha256") == digest(data),
                    case + ": modified raw " + filename)
            raw[filename] = data
            inventory.add(case + "/" + filename)
        require(raw["source.bas"] == source, case + ": source copy forged")
        trace = read_json(work / "autocmd.json")
        require(trace.get("source_path") == path and
                trace.get("source_sha256") == sha_source and
                trace.get("commands") == commands and
                trace.get("new_cpc_process") is True and
                trace.get("direct_list_to_printer") is True and
                trace.get("run_executed") is False and
                all("RUN" not in x for x in commands),
                case + ": source, direct LIST, or chronology mismatch")
        cfg = configparser.ConfigParser(interpolation=None)
        require(bool(cfg.read(work / "cap32.cfg")) and
                cfg.get("system", "model") == "2" and
                cfg.get("system", "ram_size") == "128" and
                cfg.get("system", "printer") == "1" and
                cfg.get("rom", "slot07") == "amsdos.rom" and
                cfg.get("file", "printer_file").endswith("/" + case + "/printer.dat") and
                cfg.get("file", "sdump_dir").endswith("/" + case),
                case + ": inconsistent CPC printer/ROM setup")
        require(c.get("cpc_returncode") == 0 and
                b"exit code: 0\n" in raw["caprice.log"] and
                re.fullmatch(r"screenshot_[0-9_]+\.png",
                             c.get("original_screen_name", "")) and
                c["original_screen_name"].encode() in raw["caprice.log"],
                case + ": authentic screenshot/Caprice log absent")
        png = raw["screen.png"]
        require(len(png) > 1024 and png.startswith(PNG) and
                png[12:16] == b"IHDR" and
                struct.unpack(">II", png[16:24]) == (768, 540),
                case + ": invalid PNG")
        require(raw["native.stdin.bin"] == source + b"LIST\n:quit\n",
                case + ": C99 execution not direct LIST of unchanged source")
        status = classify(raw["printer.dat"], raw["native.stdout.bin"],
                          c.get("native_returncode"), raw["native.stderr.bin"])
        delta = difference(raw["printer.dat"], raw["native.stdout.bin"])
        require(status == c.get("classification") and
                delta == c.get("first_difference"),
                case + ": fabricated classification or byte discrepancy")
        require(status != "MATCH_EXACT" or
                raw["printer.dat"] == raw["native.stdout.bin"],
                case + ": false exact-byte match")
        result[case] = {"status": status, "first_difference": delta,
                        "cpc": raw["printer.dat"], "native": raw["native.stdout.bin"]}
        print(case, status, "CPC printer", len(raw["printer.dat"]),
              "native stdout", len(raw["native.stdout.bin"]), "delta", delta)
    found = {f.relative_to(base).as_posix() for f in base.rglob("*") if f.is_file()}
    require(found == inventory, "missing or additional unclassified evidence")
    return result


def mutate_expected(base, mutation, label, permanent):
    with tempfile.TemporaryDirectory(prefix="c7-negative-") as tmp:
        root = Path(tmp) / "proof"
        shutil.copytree(base, root)
        m = read_json(root / "manifest.json")
        mutation(root, m)
        (root / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
        try:
            verify(root, permanent)
        except (Invalid, OSError, ValueError, KeyError, TypeError):
            print("PASS: rejected", label)
        else:
            raise Invalid("NEGATIVE TEST ACCEPTED: " + label)


def self_test(base, permanent):
    first = "c_integer_add"
    def tamper(f):
        return lambda root, m: (root / first / f).write_bytes(
            (root / first / f).read_bytes() + b"X")
    for f in ("printer.dat", "screen.png", "native.stdout.bin", "source.bas"):
        mutate_expected(base, tamper(f), "tampered " + f, permanent)
    for f in ("printer.dat", "screen.png"):
        mutate_expected(base, lambda root, m, f=f: (root / first / f).unlink(),
                        "missing " + f, permanent)
    def fake_exact(root, m):
        next(c for c in m["captures"] if c["case"] == first)["classification"] = "MATCH_EXACT"
    # If the original is coincidentally exact, force a false exact claim by
    # changing a copied CPC byte and rehashing the descriptor too.
    def fake_exact_strict(root, m):
        c = next(c for c in m["captures"] if c["case"] == first)
        replacement = (root / first / "printer.dat").read_bytes() + b"X"
        (root / first / "printer.dat").write_bytes(replacement)
        c["files"]["printer.dat"] = {
            "sha256": digest(replacement), "size_bytes": len(replacement)}
        c["classification"] = "MATCH_EXACT"
        c["first_difference"] = difference(replacement,
                                           (root / first / "native.stdout.bin").read_bytes())
    mutate_expected(base, fake_exact_strict, "falsely labeled MATCH_EXACT", permanent)
    def wrong_trace(root, m):
        j = read_json(root / first / "autocmd.json")
        j["commands"].insert(-1, "RUN")
        f = root / first / "autocmd.json"
        f.write_text(json.dumps(j))
        c = next(c for c in m["captures"] if c["case"] == first)
        c["files"]["autocmd.json"] = {"sha256": digest(f.read_bytes()),
                                       "size_bytes": f.stat().st_size}
    mutate_expected(base, wrong_trace, "inserted RUN", permanent)
    def swapped(root, m):
        next(c for c in m["captures"] if c["case"] == first)["cpc_channel"] = (
            "native.stdout.bin: C99 CLI LIST (no RUN)")
    mutate_expected(base, swapped, "swapped provenance channel", permanent)
    with tempfile.TemporaryDirectory(prefix="c7-local-") as tmp:
        root = Path(tmp) / "proof"
        shutil.copytree(base, root)
        m = read_json(root / "manifest.json")
        m.pop("original_artifact", None)
        (root / "acquisition.json").unlink(missing_ok=True)
        m["github_run_id"], m["github_sha"] = None, None
        (root / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
        verify(root)
        print("PASS: valid local evidence without GitHub Actions identity")
    if permanent:
        with tempfile.TemporaryDirectory(prefix="c7-forged-") as tmp:
            root = Path(tmp) / "proof"
            shutil.copytree(base, root)
            m = read_json(root / "manifest.json")
            c = next(c for c in m["captures"] if c["case"] == first)
            new_raw = (root / first / "printer.dat").read_bytes() + b"X"
            (root / first / "printer.dat").write_bytes(new_raw)
            c["files"]["printer.dat"] = {"sha256": digest(new_raw),
                                           "size_bytes": len(new_raw)}
            c["classification"] = classify(new_raw,
                                           (root / first / "native.stdout.bin").read_bytes(),
                                           c["native_returncode"],
                                           (root / first / "native.stderr.bin").read_bytes())
            c["first_difference"] = difference(
                new_raw, (root / first / "native.stdout.bin").read_bytes())
            original = copy.deepcopy(m)
            original.pop("original_artifact")
            raw = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
            (root / "acquisition.json").write_bytes(raw)
            m["original_artifact"]["acquisition_sha256"] = digest(raw)
            (root / "manifest.json").write_text(
                json.dumps(m, indent=2, ensure_ascii=False) + "\n")
            require(digest(raw) != APPROVED_ACQUISITION_SHA256,
                    "forged acquisition did not change digest")
            try:
                verify(root, permanent=True)
            except Invalid as e:
                require("immutable acquisition digest mismatch" in str(e),
                        "forgery rejected for wrong reason: " + str(e))
            else:
                raise Invalid("coordinated archival forgery accepted")
            print("PASS: coordinated printer + all SHA + acquisition manifest forgery rejected")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", required=True, type=Path)
    p.add_argument("--permanent", action="store_true")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    try:
        base = a.evidence.resolve()
        verify(base, a.permanent)
        if a.self_test:
            self_test(base, a.permanent)
    except (Invalid, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        print("C7 EVIDENCE INVALID:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
