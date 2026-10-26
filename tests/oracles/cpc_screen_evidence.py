#!/usr/bin/env python3
"""J0.24-C8: verify CPC LIST screen observation provenance and negative cases.

Pixels are NOT textual bytes. Even an authentic PNG is only visual evidence.
Permanent promotion requires independent hardcoded acquisition/run/artifact anchors.
"""
import argparse
import configparser
import copy
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import zlib

from list_screen_oracle import (CASES, PIN, ROM_SHA, AMSDOS_SHA, ROOT,
                                EXPECTED_FILES, PNG, CAPTURE_MACRO,
                                commands_for, digest)

# Set these ONLY after a genuine independently reviewed GitHub Actions
# acquisition has been promoted, NOT from the manifest under verification.
APPROVED_ACQUISITION_SHA256 = None
APPROVED_GITHUB_RUN_ID = None
APPROVED_ARTIFACT_ID = None


class Invalid(Exception):
    pass


def require(condition, msg):
    if not condition:
        raise Invalid(msg)


def read_json(path):
    return json.loads(path.read_bytes())


def check_png(raw):
    require(len(raw) > 1024 and raw.startswith(PNG), "bad PNG signature/size")
    pos, kinds, width_height = 8, [], None
    while pos < len(raw):
        require(pos + 12 <= len(raw), "truncated PNG chunk header")
        size = struct.unpack_from(">I", raw, pos)[0]
        kind = raw[pos + 4:pos + 8]
        end = pos + 12 + size
        require(end <= len(raw) and size < 16 * 1024 * 1024,
                "truncated/oversize PNG chunk")
        chunk = raw[pos + 4:pos + 8 + size]
        expected_crc = struct.unpack_from(">I", raw, pos + 8 + size)[0]
        require(zlib.crc32(chunk) & 0xffffffff == expected_crc,
                "PNG chunk CRC mismatch")
        if kind == b"IHDR":
            require(width_height is None and size == 13 and not kinds,
                    "PNG IHDR invalid")
            width_height = struct.unpack_from(">II", raw, pos + 8)
        kinds.append(kind)
        pos = end
        if kind == b"IEND":
            break
    require(pos == len(raw) and kinds.count(b"IEND") == 1 and
            b"IDAT" in kinds and width_height == (768, 540),
            "incomplete PNG or wrong CPC screenshot dimensions")


def verify(base, permanent=False):
    require(base.is_dir(), "screen evidence missing")
    m = read_json(base / "manifest.json")
    require(m.get("schema_version") == 1 and m.get("phase") == "J0.24-C8" and
            m.get("screen_text_bytes_extracted") is False and
            m.get("screen_printer_equivalence") is False,
            "screen classification/conflation invalid")
    o = m.get("oracle", {})
    require(o.get("name") == "Caprice32" and o.get("commit") == PIN and
            o.get("model") == "CPC6128" and o.get("ram_kb") == 128 and
            o.get("basic") == "1.1" and "4.6.0" in o.get("version_output", "") and
            o.get("rom_sha256") == ROM_SHA and
            o.get("amsdos_sha256") == AMSDOS_SHA and
            o.get("rom_archived") is False and
            o.get("snapshot_archived") is False,
            "emulator or ROM provenance invalid")
    runid, commit = m.get("github_run_id"), m.get("github_sha")
    if permanent:
        require(isinstance(APPROVED_ACQUISITION_SHA256, str) and
                re.fullmatch(r"[a-f0-9]{64}", APPROVED_ACQUISITION_SHA256) and
                type(APPROVED_GITHUB_RUN_ID) is int and
                type(APPROVED_ARTIFACT_ID) is int,
                "independent permanent approval anchors missing")
        require(runid == str(APPROVED_GITHUB_RUN_ID) and isinstance(commit, str) and
                re.fullmatch(r"[a-f0-9]{40}", commit),
                "unapproved GitHub acquisition identity")
        approval = m.get("original_artifact", {})
        require(approval == {
            "run_id": APPROVED_GITHUB_RUN_ID,
            "artifact_id": APPROVED_ARTIFACT_ID,
            "run_url": "https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/" +
                       str(APPROVED_GITHUB_RUN_ID),
            "acquisition_sha256": APPROVED_ACQUISITION_SHA256,
        }, "unapproved archive identity")
        raw = (base / "acquisition.json").read_bytes()
        require(digest(raw) == APPROVED_ACQUISITION_SHA256,
                "immutable original acquisition digest mismatch")
        original = read_json(base / "acquisition.json")
        clone = copy.deepcopy(m)
        clone.pop("original_artifact", None)
        require(clone == original, "permanent manifest is not original acquisition")
    else:
        require((runid is None and commit is None) or
                (isinstance(runid, str) and re.fullmatch(r"[0-9]+", runid) and
                 isinstance(commit, str) and re.fullmatch(r"[a-f0-9]{40}", commit)),
                "partial GitHub identity invalid")
    captures = m.get("captures")
    require(isinstance(captures, list) and len(captures) == len(CASES) and
            {c.get("case") for c in captures} == set(CASES),
            "both independently captured cases required")
    inventory = {"manifest.json", *({"acquisition.json"} if permanent else set())}
    for c in captures:
        name = c["case"]
        path, source_sha, list_cmd = CASES[name]
        work = base / name
        require(work.is_dir() and not work.is_symlink(),
                name + ": missing/unsafe capture directory")
        source = (ROOT / path).read_bytes()
        require(digest(source) == source_sha and b"\r" not in source and
                source.endswith(b"\n"), name + ": historical file altered")
        expected = commands_for(source, list_cmd)
        require(c.get("source_path") == path and
                c.get("source_sha256") == source_sha and
                c.get("commands") == expected and
                expected[-3:] == ["CLS", list_cmd, CAPTURE_MACRO] and
                c.get("operation") == "LIST_SCREEN_VISUAL" and
                c.get("list_command_cpc") == list_cmd and
                c.get("list_command_native") == "LIST" and
                c.get("selection_scope") ==
                "all historical lines match requested CPC range" and
                c.get("classification") == "VISUAL_OBSERVATION" and
                c.get("visual_review_status") == "PENDING_MANUAL_INSPECTION" and
                c.get("visual_review") is None and
                c.get("byte_exactness_claimed") is False and
                c.get("cpc_returncode") == 0 and
                c.get("native_returncode") == 0 and
                c.get("cpc_channel") ==
                "screen.png: original CPC DISPLAY PIXELS (no RUN, no printer)" and
                c.get("printer_channel") == "not acquired (disabled, no LIST #8)" and
                c.get("native_channel") ==
                "native.stdout.bin: original C99 CLI LIST bytes",
                name + ": channels, commands or classification forged")
        require(list_cmd in {"LIST 10-40", "LIST 10-30"} and
                not any(re.search(r"\bRUN\b|#\s*8\b", cmd, re.I)
                        for cmd in expected),
                name + ": RUN or LIST printer contamination")
        require(set(c.get("files", {})) == set(EXPECTED_FILES),
                name + ": missing or extra file descriptor")
        raws = {}
        for filename in EXPECTED_FILES:
            f = work / filename
            require(f.is_file() and not f.is_symlink() and
                    f.resolve().is_relative_to(base.resolve()),
                    name + ": missing/unsafe " + filename)
            data = f.read_bytes()
            meta = c["files"][filename]
            require(type(meta.get("size_bytes")) is int and
                    meta["size_bytes"] == len(data) and
                    meta.get("sha256") == digest(data),
                    name + ": SHA-256/size mismatch " + filename)
            raws[filename] = data
            inventory.add(name + "/" + filename)
        require(raws["source.bas"] == source,
                name + ": captured historical source mismatch")
        trace = json.loads(raws["autocmd.json"])
        require(trace == {
            "source_path": path, "source_sha256": source_sha,
            "commands": expected, "new_cpc_process": True,
            "direct_cls_before_list": True, "list_to_screen_only": True,
            "run_executed": False, "screen_text_bytes_extracted": False,
        }, name + ": command injection or false process provenance")
        cfg = configparser.ConfigParser(interpolation=None)
        with (work / "cap32.cfg").open(encoding="utf-8") as f:
            cfg.read_file(f)
        require(cfg.get("system", "model") == "2" and
                cfg.get("system", "ram_size") == "128" and
                cfg.get("system", "printer") == "0" and
                cfg.get("rom", "slot07") == "amsdos.rom" and
                cfg.get("file", "sdump_dir").endswith("/" + name) and
                cfg.get("file", "printer_file").endswith(
                    "/" + name + "/unexpected-printer.dat"),
                name + ": printer used or CPC configuration altered")
        require(not (work / "unexpected-printer.dat").exists(),
                name + ": unexpected printer output")
        require(b"exit code: 0\n" in raws["caprice.log"] and
                re.fullmatch(r"screenshot_[0-9_]+\.png",
                             c.get("original_screen_name", "")) and
                c["original_screen_name"].encode() in raws["caprice.log"],
                name + ": screenshot trace absent")
        check_png(raws["screen.png"])
        require(raws["native.stdin.bin"] == source + b"LIST\n:quit\n" and
                raws["native.stdout.bin"] and
                b"[cli:error]" not in raws["native.stderr.bin"],
                name + ": independent C99 LIST not demonstrated")
        require(b"\r\n" not in raws["native.stdout.bin"],
                name + ": native output was normalized to printer CRLF")
        print(f"{name}: CPC SCREEN={len(raws['screen.png'])} PNG bytes "
              f"sha256={digest(raws['screen.png'])} / "
              f"C99 LIST={len(raws['native.stdout.bin'])} bytes "
              "(VISUAL_OBSERVATION, no byte equivalence)")
    found = {p.relative_to(base).as_posix()
             for p in base.rglob("*") if p.is_file()}
    require(found == inventory, "unclassified or missing evidence files")
    return m


def mutation_test(base, alter, label, permanent):
    with tempfile.TemporaryDirectory(prefix="c8-negative-") as tmp:
        target = Path(tmp) / "capture"
        shutil.copytree(base, target)
        m = read_json(target / "manifest.json")
        alter(target, m)
        (target / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
        try:
            verify(target, permanent)
        except (Invalid, OSError, ValueError, TypeError, KeyError, UnicodeError):
            print("PASS rejected:", label)
        else:
            raise Invalid("NEGATIVE CASE ACCEPTED: " + label)


def self_test(base, permanent):
    name = "c_integer_add"
    def modify_bytes(file):
        def op(root, m):
            f = root / name / file
            f.write_bytes(f.read_bytes() + b"X")
        return op
    mutation_test(base, modify_bytes("screen.png"), "tampered screen PNG", permanent)
    mutation_test(base, lambda r, m: (r / name / "screen.png").unlink(),
                  "absent screen", permanent)
    mutation_test(base, modify_bytes("source.bas"), "changed historic line", permanent)

    def modify_trace(cmd):
        def op(root, m):
            f = root / name / "autocmd.json"
            trace = read_json(f)
            trace["commands"].insert(-1, cmd)
            f.write_text(json.dumps(trace), encoding="utf-8")
            c = next(c for c in m["captures"] if c["case"] == name)
            data = f.read_bytes()
            c["files"]["autocmd.json"] = {
                "sha256": digest(data), "size_bytes": len(data)}
        return op
    mutation_test(base, modify_trace("RUN"), "injected RUN with rehash", permanent)
    mutation_test(base, modify_trace("LIST 10-40,#8"),
                  "printer LIST with rehash", permanent)

    def swap_channel(root, m):
        next(c for c in m["captures"] if c["case"] == name)["cpc_channel"] = (
            "native.stdout.bin: C99 CLI LIST bytes")
    mutation_test(base, swap_channel, "CPC/C99 printer/screen confusion", permanent)

    with tempfile.TemporaryDirectory(prefix="c8-local-") as tmp:
        target = Path(tmp) / "capture"
        shutil.copytree(base, target)
        m = read_json(target / "manifest.json")
        m.pop("original_artifact", None)
        (target / "acquisition.json").unlink(missing_ok=True)
        m["github_run_id"], m["github_sha"] = None, None
        (target / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
        verify(target, False)
        print("PASS: offline local evidence without GitHub Actions identity")

    if permanent:
        def coordinated(root, m):
            f = root / name / "screen.png"
            raw = f.read_bytes()
            # Valid CRC-preserving alteration of screenshot pixels/metadata:
            # a forged original can adjust all hashes and both manifests.
            altered = raw + b"X"
            f.write_bytes(altered)
            c = next(c for c in m["captures"] if c["case"] == name)
            c["files"]["screen.png"] = {
                "sha256": digest(altered), "size_bytes": len(altered)}
            new_acq = copy.deepcopy(m)
            new_acq.pop("original_artifact", None)
            acq = (json.dumps(new_acq, indent=2, ensure_ascii=False) + "\n").encode()
            (root / "acquisition.json").write_bytes(acq)
            m["original_artifact"]["acquisition_sha256"] = digest(acq)
        mutation_test(base, coordinated, "coordinated proof+manifest forgery",
                      True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--permanent", action="store_true")
    p.add_argument("--self-test", action="store_true")
    opts = p.parse_args()
    verify(opts.evidence.resolve(), opts.permanent)
    if opts.self_test:
        self_test(opts.evidence.resolve(), opts.permanent)
    print("C8 PROVENANCE VERIFIED (not SCREEN TEXT BYTE EQUIVALENCE)")


if __name__ == "__main__":
    try:
        main()
    except (Invalid, ValueError, OSError, KeyError, TypeError) as exc:
        print("C8 EVIDENCE REJECTED:", exc, file=sys.stderr)
        sys.exit(1)
