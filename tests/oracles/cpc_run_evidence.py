#!/usr/bin/env python3
"""J0.24-C6 integrity and semantic validator for real RUN + PRINT #8,B% evidence.

Two distinct channels may agree on one signed INT16 value. They are NEVER
byte-identical CPC screen output evidence. Negative tests do not create or
promote synthetic historical observations.
"""
import argparse
import configparser
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

from run_behavior_oracle import CASES, EXPECTED_FILES, PIN, ROM_SHA, ROOT, digest, integer

ALLOWED = {"MATCH_SEMANTIC", "DIFF", "UNSUPPORTED", "UNVERIFIED"}
# Pilotage-approved anchors: NEVER derive them from acquisition.json or
# manifest.json, which are themselves inputs to this verifier.
APPROVED_ACQUISITION_SHA256 = "2e39584df89089120f422a0c7cd3541ac5e0b9a4f24788007b31c9d3cc34b895"
APPROVED_GITHUB_RUN_ID = 40241824206
APPROVED_ARTIFACT_ID = 12615969513
PNG = b"\x89PNG\r\n\x1a\n"
KINDS = {
    "source.bas": "basic_source",
    "autocmd.json": "input_trace",
    "cap32.cfg": "cpc_config",
    "caprice.log": "acquisition_log",
    "printer.dat": "cpc_printer",
    "native.stdin.bin": "c99_stdin",
    "native.stdout.bin": "c99_stdout",
    "native.stderr.bin": "c99_stderr",
    "screen.png": "visual_png",
}


class Invalid(Exception):
    pass


def require(ok, what):
    if not ok:
        raise Invalid(what)


def read_json(path):
    return json.loads(path.read_bytes())


def chronology(source, commands):
    lines = source.decode("ascii").splitlines()
    return (commands == lines + ["RUN", "PRINT #8,B%",
             "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"])


def classification(cpc_bytes, native_bytes, rc, stderr):
    cpc, native = integer(cpc_bytes), integer(native_bytes)
    if rc != 0 or b"[cli:error]" in stderr:
        return "UNSUPPORTED", cpc, native
    if cpc is None or native is None:
        return "UNVERIFIED", cpc, native
    return ("MATCH_SEMANTIC" if cpc == native else "DIFF"), cpc, native


def verify(base, permanent=False):
    require(base.is_dir(), "missing evidence directory")
    manifest = read_json(base / "manifest.json")
    require(manifest.get("schema_version") == 1 and manifest.get("phase") == "J0.24-C6",
            "incorrect C6 schema")
    require(manifest.get("screen_bytes_captured") is False and
            manifest.get("printer_screen_byte_equivalence") is False,
            "screen and printer channels must be distinct")
    oracle = manifest.get("oracle", {})
    require(oracle.get("name") == "Caprice32" and oracle.get("commit") == PIN and
            oracle.get("model") == "CPC6128" and oracle.get("ram_kb") == 128 and
            oracle.get("basic") == "1.1" and oracle.get("rom_sha256") == ROM_SHA and
            oracle.get("rom_archived") is False and oracle.get("snapshot_archived") is False and
            isinstance(oracle.get("amsdos_sha256"), str) and
            re.fullmatch("[0-9a-f]{64}", oracle["amsdos_sha256"]) and
            "4.6.0" in oracle.get("version_output", ""),
            "unverified emulator/ROM provenance")
    # Temporary acquisitions can originate from a machine without Actions.
    # Either both workflow fields are absent, or both must be well-formed.
    run_id, github_sha = manifest.get("github_run_id"), manifest.get("github_sha")
    if permanent:
        require(isinstance(run_id, str) and
                run_id == str(APPROVED_GITHUB_RUN_ID) and
                isinstance(github_sha, str) and
                re.fullmatch("[0-9a-f]{40}", github_sha) is not None,
                "permanent acquisition GitHub identity unapproved/missing")
    else:
        require((run_id is None and github_sha is None) or
                (isinstance(run_id, str) and
                 re.fullmatch("[0-9]+", run_id) is not None and
                 isinstance(github_sha, str) and
                 re.fullmatch("[0-9a-f]{40}", github_sha) is not None),
                "partial or malformed optional local GitHub identity")
    if permanent:
        original = manifest.get("original_artifact", {})
        require(type(original.get("run_id")) is int and
                original["run_id"] == APPROVED_GITHUB_RUN_ID and
                type(original.get("artifact_id")) is int and
                original["artifact_id"] == APPROVED_ARTIFACT_ID and
                original.get("run_url") ==
                "https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/" +
                str(APPROVED_GITHUB_RUN_ID),
                "unapproved permanent acquisition run/artifact identity")
        # This digest is a hard-coded historical acceptance anchor. Checking
        # ONLY manifest.original_artifact.acquisition_sha256 is forgeable.
        acquisition = (base / "acquisition.json").read_bytes()
        require(digest(acquisition) == APPROVED_ACQUISITION_SHA256 and
                original.get("acquisition_sha256") == APPROVED_ACQUISITION_SHA256,
                "approved acquisition SHA-256 anchor mismatch")
        before = json.loads(acquisition)
        expected = copy.deepcopy(manifest)
        expected.pop("original_artifact")
        require(before == expected, "permanent record differs from original acquisition")
    captures = manifest.get("captures")
    require(isinstance(captures, list) and len(captures) == 2 and
            {x.get("case") for x in captures} == set(CASES),
            "two independent numbered programs required")
    inventory = {"manifest.json"}
    if permanent:
        inventory.add("acquisition.json")
    results = {}
    for capture in captures:
        case = capture["case"]
        source_path, source_sha, hypothesis = CASES[case]
        work = base / case
        require(work.is_dir() and not work.is_symlink(), case + ": missing case directory")
        require(capture.get("source_path") == source_path and
                capture.get("source_sha256") == source_sha and
                capture.get("hypothesis_not_oracle") == hypothesis and
                capture.get("operation") == "RUN_NUMERIC_PROBE" and
                capture.get("comparison") == "strict-signed-integer" and
                capture.get("cpc_channel") == "printer.dat: direct-mode PRINT #8,B% after RUN" and
                capture.get("native_channel") == "native.stdout.bin: C99 PRINT during RUN" and
                capture.get("screen_channel") == "screen.png: visual only; NOT byte-exact text" and
                capture.get("classification") in ALLOWED,
                case + ": invalid or conflated comparison")
        descs = capture.get("files", {})
        require(set(descs) == set(EXPECTED_FILES) == set(KINDS),
                case + ": required source/screen/printer/CLI evidence absent or extra")
        raw = {}
        for name in EXPECTED_FILES:
            file = work / name
            require(file.is_file() and not file.is_symlink() and
                    file.resolve().is_relative_to(base.resolve()),
                    case + ": missing, unsafe, or symlinked " + name)
            data = file.read_bytes()
            desc = descs[name]
            require(type(desc.get("size_bytes")) is int and
                    len(data) == desc["size_bytes"] and
                    isinstance(desc.get("sha256"), str) and
                    re.fullmatch("[0-9a-f]{64}", desc["sha256"]) and
                    digest(data) == desc["sha256"],
                    case + ": modified " + name)
            raw[name] = data
            inventory.add(case + "/" + name)
        source = raw["source.bas"]
        require(digest(source) == source_sha and
                (ROOT / source_path).read_bytes() == source and
                source.endswith(b"\n") and b"\r" not in source,
                case + ": historical source altered")
        commands = read_json(work / "autocmd.json")
        require(commands.get("source_path") == source_path and
                commands.get("source_sha256") == source_sha and
                commands.get("new_cpc_process") is True and
                commands.get("probe_is_direct_after_run") is True and
                chronology(source, commands.get("commands")) and
                capture.get("commands") == commands["commands"],
                case + ": probe order or command injection trace changed")
        cfg = configparser.ConfigParser(interpolation=None)
        require(bool(cfg.read(work / "cap32.cfg")) and cfg.get("system", "model") == "2" and
                cfg.get("system", "ram_size") == "128" and
                cfg.get("system", "printer") == "1" and
                cfg.get("file", "printer_file").endswith("/" + case + "/printer.dat") and
                cfg.get("file", "sdump_dir").endswith("/" + case),
                case + ": CPC model/printer screenshot configuration inconsistent")
        require(capture.get("cpc_returncode") == 0 and
                b"exit code: 0\n" in raw["caprice.log"] and
                re.fullmatch(r"screenshot_[0-9_]+\.png", capture.get("original_screen_name", "")) and
                capture["original_screen_name"].encode() in raw["caprice.log"],
                case + ": Caprice32 run/screenshot cannot be attested")
        png = raw["screen.png"]
        require(len(png) > 1024 and png.startswith(PNG) and png[12:16] == b"IHDR" and
                struct.unpack(">II", png[16:24]) == (768, 540),
                case + ": PNG screenshot missing or malformed")
        require(raw["native.stdin.bin"] == source + b"RUN\n:step 100\n:quit\n",
                case + ": native CLI did not execute original source")
        status, cpc_number, native_number = classification(
            raw["printer.dat"], raw["native.stdout.bin"],
            capture.get("native_returncode"), raw["native.stderr.bin"])
        require(status == capture.get("classification") and
                cpc_number == capture.get("cpc_integer") and
                native_number == capture.get("native_integer"),
                case + ": false semantic classification/numeric value")
        results[case] = {"status": status, "cpc": cpc_number, "native": native_number}
    found = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}
    require(found == inventory, "absent/unclassified/extraneous evidence file")
    for case, result in results.items():
        print(case, result["status"], "CPC=", result["cpc"],
              "C99=", result["native"], "screen exactness=UNVERIFIED")
    return results


def require_accepted_behavior(results):
    """Acceptance policy, intentionally separate from structural verification.

    DIFF/UNVERIFIED/UNSUPPORTED are legitimate *observations* which should
    remain archivable, but are not successes of the reproducibility gate.
    """
    require(set(results) == set(CASES), "C6 behavior gate: missing/extra case")
    for case, (_, _, approved) in CASES.items():
        result = results[case]
        require(result["status"] == "MATCH_SEMANTIC" and
                result["cpc"] == approved and result["native"] == approved,
                f"C6 behavior gate: {case} expected CPC/C99={approved} "
                f"MATCH_SEMANTIC, got {result}")


def should_reject(base, mutate, label, permanent):
    with tempfile.TemporaryDirectory(prefix="c6-negative-") as tmp:
        copied = Path(tmp) / "evidence"
        shutil.copytree(base, copied)
        manifest = read_json(copied / "manifest.json")
        mutate(copied, manifest)
        (copied / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        try:
            verify(copied, permanent)
        except (Invalid, OSError, ValueError, KeyError, TypeError):
            return
        raise Invalid("negative test unexpectedly accepted: " + label)


def self_test(base, permanent):
    require(integer(b" 5 \r\n") == 5 and integer(b"-32768\n") == -32768 and
            integer(b"32767\n") == 32767 and integer(b"32768\n") is None and
            integer(b"5\n6\n") is None and integer(b"answer:5\n") is None and
            integer(b"5") is None and integer(b" 2X\n") is None,
            "numeric grammar too permissive")
    first = "c_integer_add"

    def file_tamper(name):
        def mutate(copied, manifest):
            target = copied / first / name
            target.write_bytes(target.read_bytes() + b"x")
        return mutate

    for name in ("printer.dat", "source.bas", "screen.png", "native.stdout.bin",
                 "native.stderr.bin"):
        should_reject(base, file_tamper(name), "raw tamper " + name, permanent)

    def missing(name):
        return lambda copied, manifest: (copied / first / name).unlink()
    for name in ("screen.png", "printer.dat"):
        should_reject(base, missing(name), "missing " + name, permanent)

    def corrupt_trace(copied, manifest):
        trace = copied / first / "autocmd.json"
        j = read_json(trace)
        i = j["commands"].index("RUN")
        j["commands"][i], j["commands"][i+1] = j["commands"][i+1], j["commands"][i]
        trace.write_text(json.dumps(j))
        manifest["captures"][0]["files"]["autocmd.json"] = {
            "sha256": digest(trace.read_bytes()), "size_bytes": trace.stat().st_size}
    should_reject(base, corrupt_trace, "printer before RUN", permanent)

    def fake_exact(copied, manifest):
        manifest["captures"][0]["classification"] = "MATCH_EXACT"
    should_reject(base, fake_exact, "false exact classification", permanent)

    def fake_value(copied, manifest):
        manifest["captures"][0]["cpc_integer"] = 123
    should_reject(base, fake_value, "forged CPC value", permanent)

    def fake_native(copied, manifest):
        manifest["captures"][0]["native_integer"] = 123
    should_reject(base, fake_native, "forged C99 value", permanent)

    def swapped_channel(copied, manifest):
        manifest["captures"][0]["cpc_channel"] = "native.stdout.bin: C99 PRINT during RUN"
    should_reject(base, swapped_channel, "screen/printer/native channel confusion", permanent)

    def broken_source(copied, manifest):
        manifest["captures"][0]["source_sha256"] = "0"*64
    should_reject(base, broken_source, "source SHA altered", permanent)
    print("PASS: strict integer grammar and 13 negative integrity/chronology/channel tests")

    # Reproduction from a developer machine has no GitHub Actions variables.
    # Use authentic historical bytes, but drop the permanent provenance wrapper
    # to model the output produced by run_behavior_oracle.py on that machine.
    def local_copy(destination):
        # Always use the permanently approved baseline, NOT the just-acquired
        # data under validation. The self-test must pass even if a fresh RUN
        # legitimately reports DIFF/UNVERIFIED/UNSUPPORTED (diagnostic mode).
        trusted_baseline = ROOT / "tests/fixtures/cpc6128/run_behavior"
        require(trusted_baseline.is_dir(), "missing trusted baseline for C6 negative tests")
        shutil.copytree(trusted_baseline, destination)
        j = read_json(destination / "manifest.json")
        j.pop("original_artifact", None)
        (destination / "acquisition.json").unlink(missing_ok=True)
        j["github_run_id"] = None
        j["github_sha"] = None
        (destination / "manifest.json").write_text(json.dumps(j, indent=2) + "\n")
        return j

    with tempfile.TemporaryDirectory(prefix="c6-local-proof-") as tmp:
        local = Path(tmp) / "evidence"
        local_copy(local)
        observed = verify(local, permanent=False)
        require_accepted_behavior(observed)
        cmd = [sys.executable, str(Path(__file__).resolve()), "--evidence",
               str(local), "--require-accepted-behavior"]
        positive = subprocess.run(cmd, capture_output=True, timeout=20, check=False)
        require(positive.returncode == 0, "valid no-Actions local acquisition rejected")
        print("PASS: valid local acquisition without GITHUB_RUN_ID/GITHUB_SHA")

    # Every mutation below retains internal integrity (all relevant file
    # hashes and the semantic classification are recomputed). A regression
    # must remain structurally archivable yet fail the *actual CLI* CI gate.
    regressions = {
        "DIFF": (b" 6 \r\n", b"5\n", b"", "DIFF"),
        "UNVERIFIED": (b"?\r\n", b"5\n", b"", "UNVERIFIED"),
        "UNSUPPORTED": (b" 5 \r\n", b"5\n", b"[cli:error] deliberate test\n", "UNSUPPORTED"),
        "WRONG_MATCH": (b" 6 \r\n", b"6\n", b"", "MATCH_SEMANTIC"),
    }
    for label, (printer, stdout, stderr, result_status) in regressions.items():
        with tempfile.TemporaryDirectory(prefix="c6-gate-negative-") as tmp:
            local = Path(tmp) / "evidence"
            j = local_copy(local)
            c = next(item for item in j["captures"] if item["case"] == first)
            for name, data in (("printer.dat", printer), ("native.stdout.bin", stdout),
                               ("native.stderr.bin", stderr)):
                target = local / first / name
                target.write_bytes(data)
                c["files"][name] = {"size_bytes": len(data), "sha256": digest(data)}
            c["classification"], c["cpc_integer"], c["native_integer"] = classification(
                printer, stdout, c["native_returncode"], stderr)
            require(c["classification"] == result_status,
                    "negative test classified incorrectly: " + label)
            (local / "manifest.json").write_text(json.dumps(j, indent=2) + "\n")
            observed = verify(local, permanent=False)  # real, structurally valid diagnostic
            require(observed[first]["status"] == result_status,
                    "regression fixture not structurally accepted: " + label)
            if label == "DIFF":
                # The structural CLI must accept diagnostic evidence;
                # only the separately invoked behavioral acceptance gate fails.
                # Do not recursively invoke --self-test from self_test().
                structural = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()),
                     "--evidence", str(local)],
                    capture_output=True, timeout=20, check=False)
                require(structural.returncode == 0,
                        "structural CLI wrongly rejected a verified DIFF")
                print("PASS: structurally valid DIFF remains archivable")
            test = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                   "--evidence", str(local), "--require-accepted-behavior"],
                                  capture_output=True, timeout=20, check=False)
            require(test.returncode != 0 and
                    b"C6 behavior gate:" in test.stderr,
                    "CI gate did not reject " + label)
            print("PASS: CI behavioral gate rejects", label, "with nonzero exit")

    # Missing C or D must fail the process-level gate, not merely omit output.
    with tempfile.TemporaryDirectory(prefix="c6-missing-case-") as tmp:
        local = Path(tmp) / "evidence"
        j = local_copy(local)
        j["captures"] = [c for c in j["captures"] if c["case"] != first]
        shutil.rmtree(local / first)
        (local / "manifest.json").write_text(json.dumps(j, indent=2) + "\n")
        missing_result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--evidence",
             str(local), "--require-accepted-behavior"],
            capture_output=True, timeout=20, check=False)
        require(missing_result.returncode != 0 and
                b"two independent numbered programs required" in missing_result.stderr,
                "CI gate accepted acquisition with missing case")
        print("PASS: CI behavioral gate rejects missing C case with nonzero exit")

    if permanent:
        with tempfile.TemporaryDirectory(prefix="c6-coordinated-forgery-") as tmp:
            forged = Path(tmp) / "evidence"
            shutil.copytree(base, forged)
            j = read_json(forged / "manifest.json")
            c = next(item for item in j["captures"] if item["case"] == first)
            forged_printer = b"+5\n"  # same numeric value, different CPC raw bytes
            (forged / first / "printer.dat").write_bytes(forged_printer)
            c["files"]["printer.dat"] = {
                "sha256": digest(forged_printer), "size_bytes": len(forged_printer)}
            original = copy.deepcopy(j)
            original.pop("original_artifact")
            acquisition = (json.dumps(original, indent=2, ensure_ascii=False) + "\n").encode()
            (forged / "acquisition.json").write_bytes(acquisition)
            j["original_artifact"]["acquisition_sha256"] = digest(acquisition)
            (forged / "manifest.json").write_text(
                json.dumps(j, indent=2, ensure_ascii=False) + "\n")
            require(digest(acquisition) != APPROVED_ACQUISITION_SHA256 and
                    read_json(forged / "acquisition.json") == original and
                    j["original_artifact"]["acquisition_sha256"] == digest(acquisition),
                    "coordinated forgery test was not fully rehashed")
            try:
                verify(forged, permanent=True)
            except Invalid as exc:
                require("approved acquisition SHA-256 anchor mismatch" in str(exc),
                        "forgery rejected for unrelated reason: " + str(exc))
            else:
                raise Invalid("coordinated historical forgery accepted!")
            print("PASS: coordinated raw printer+both manifests+all SHA-256 "
                  "rejected by immutable approved acquisition anchor")



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--permanent", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--require-accepted-behavior", action="store_true",
                        help="nonzero exit unless both fresh C/D probes are CPC/C99=5/2 MATCH_SEMANTIC")
    args = parser.parse_args()
    try:
        base = args.evidence.resolve()
        results = verify(base, args.permanent)
        if args.require_accepted_behavior:
            require_accepted_behavior(results)
            print("PASS: C6 behavioral acceptance gate C=5 D=2 MATCH_SEMANTIC")
        if args.self_test:
            self_test(base, args.permanent)
    except (Invalid, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("C6 EVIDENCE INVALID:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
