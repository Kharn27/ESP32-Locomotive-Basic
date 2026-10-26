#!/usr/bin/env python3
"""Validate J0.27-A real CPC PRINT acquisitions, without conflating channels.

The permanent anchor must be approved after reviewing a REAL Actions artifact.
Both an intact temporary copy and every negative mutation are checked.
"""
import argparse
import configparser
import copy
import json
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile

from numeric_print_oracle import (AMSDOS_SHA, CAPTURE, FILES, MODES,
                                  PIN, ROM_SHA, ROOT, commands_for, digest, instrument)
from run_behavior_oracle import CASES
from cpc_screen_evidence import check_png

# Approved values are independent of the archived manifest and MUST be filled
# only following independent review of the acquired GitHub Actions artifact.
APPROVED_ACQUISITION_SHA256 = "f4e48600515a83d736fd5a61a94c5f53b8e6fb6537280d1a8e2332b561a7521d"
APPROVED_GITHUB_RUN_ID = 40341786914
APPROVED_ARTIFACT_ID = 12659112768

C6_PRINTER_SHA = {
    "c_integer_add": "427c73eb948406e2dee128c2e23ee2dfc00e26e35f6b776a7d7112a1e9996246",
    "d_self_reference": "a6b9d0e774e8414383a7154ccc19fb4da0057614ddd554ad96789ac8d5ede99e",
}
C6_PRINTER_RAW = {
    "c_integer_add": bytes.fromhex("20 35 20 0D 0A"),
    "d_self_reference": bytes.fromhex("20 32 20 0D 0A"),
}
SIGNED_PRINTER = re.compile(rb"( *)([+-]?[0-9]+)( *)(\r\n|\n|\r)\Z")
SIGNED_NATIVE = re.compile(rb"([+-]?[0-9]+)(\r\n|\n|\r)\Z")


class Invalid(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Invalid(reason)


def load(path):
    return json.loads(path.read_bytes())


def signed(raw, pattern):
    m = pattern.fullmatch(raw)
    return None if m is None else int(m.group(2 if pattern is SIGNED_PRINTER else 1))


def c6_direct(case):
    path = ROOT / "tests/fixtures/cpc6128/run_behavior" / case / "printer.dat"
    require(path.is_file(), case + ": approved C6 direct printer reference missing")
    raw = path.read_bytes()
    require(digest(raw) == C6_PRINTER_SHA[case] and raw == C6_PRINTER_RAW[case],
            case + ": approved C6 direct printer bytes modified")
    return raw


def verify(base, permanent=False):
    require(base.is_dir(), "missing evidence directory")
    require((base / "manifest.json").is_file(), "mandatory manifest missing")
    m = load(base / "manifest.json")
    require(m.get("schema_version") == 1 and m.get("phase") == "J0.27-A",
            "J0.27-A schema invalid")
    require(m.get("screen_bytes_extracted") is False and
            m.get("printer_screen_equivalent") is False,
            "screen/printer conflated")
    o = m.get("oracle", {})
    require(o.get("name") == "Caprice32" and o.get("commit") == PIN and
            o.get("model") == "CPC6128" and o.get("ram_kb") == 128 and
            o.get("basic") == "1.1" and "4.6.0" in o.get("version_output", "") and
            o.get("rom_sha256") == ROM_SHA and o.get("amsdos_sha256") == AMSDOS_SHA and
            o.get("rom_archived") is False and o.get("snapshot_archived") is False,
            "CPC ROM/emulator provenance invalid")
    runid, sha = m.get("github_run_id"), m.get("github_sha")
    if permanent:
        require(type(APPROVED_GITHUB_RUN_ID) is int and
                type(APPROVED_ARTIFACT_ID) is int and
                isinstance(APPROVED_ACQUISITION_SHA256, str) and
                re.fullmatch(r"[0-9a-f]{64}", APPROVED_ACQUISITION_SHA256),
                "independent approval anchor absent")
        require(runid == str(APPROVED_GITHUB_RUN_ID) and
                isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha),
                "unapproved acquisition run or SHA")
        approved = m.get("original_artifact", {})
        require(approved.get("run_id") == APPROVED_GITHUB_RUN_ID and
                approved.get("artifact_id") == APPROVED_ARTIFACT_ID and
                approved.get("acquisition_sha256") == APPROVED_ACQUISITION_SHA256,
                "unapproved artifact/manifest anchor")
        require((base / "acquisition.json").is_file(), "approved acquisition missing")
        raw_acquisition = (base / "acquisition.json").read_bytes()
        require(digest(raw_acquisition) == APPROVED_ACQUISITION_SHA256,
                "approved acquisition SHA-256 mismatch")
        canonical = copy.deepcopy(m)
        canonical.pop("original_artifact")
        require(json.loads(raw_acquisition) == canonical,
                "archive differs from independently approved acquisition")
    else:
        require((runid is None and sha is None) or
                (isinstance(runid, str) and re.fullmatch(r"[0-9]+", runid) and
                 isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)),
                "incomplete acquisition identity")
    captures = m.get("captures")
    require(isinstance(captures, list) and len(captures) == 4 and
            {c.get("id") for c in captures} ==
            {case + "_" + mode for case in CASES for mode in MODES},
            "four distinct screen/printer acquisitions required")
    expected_inventory = {"manifest.json"}
    if permanent:
        expected_inventory.add("acquisition.json")
    observations = {}
    for entry in captures:
        id_ = entry["id"]
        case, mode = entry.get("case"), entry.get("mode")
        require(case in CASES and mode in MODES and
                id_ == case + "_" + mode, id_ + ": invalid case/channel")
        original_path, original_sha, integer = CASES[case]
        historical = (ROOT / original_path).read_bytes()
        require(digest(historical) == original_sha,
                id_ + ": historical source anchor missing/modified")
        expected_source = historical if mode == "screen" else instrument(historical)
        require(entry.get("source_path") == original_path and
                entry.get("original_source_sha256") == original_sha and
                entry.get("source_sha256") == digest(expected_source) and
                entry.get("numeric_hypothesis") == integer,
                id_ + ": source identity/hypothesis changed")
        require(entry.get("cpc_returncode") == 0 and
                entry.get("screen_classification") == "VISUAL_OBSERVATION" and
                entry.get("screen_bytes_extracted") is False and
                entry.get("printer_screen_equivalent") is False and
                entry.get("printer_channel") == (
                    "programmed PRINT #8 during RUN" if mode == "printer"
                    else "disabled; no printer output") and
                entry.get("native_channel") == (
                    "C99 stdout during RUN" if mode == "screen"
                    else "not executed in printer session") and
                entry.get("native_returncode") == (0 if mode == "screen" else None),
                id_ + ": channel or return-code falsified")
        work = base / id_
        require(work.is_dir() and not work.is_symlink(), id_ + ": missing case directory")
        desc = entry.get("files", {})
        require(set(desc) == set(FILES[mode]), id_ + ": mandatory file inventory invalid")
        raw = {}
        for name in FILES[mode]:
            path = work / name
            require(path.is_file() and not path.is_symlink(),
                    id_ + ": missing file " + name)
            content = path.read_bytes()
            # Distinct evidence/format errors before general hash errors.
            if name == "printer.dat":
                require(SIGNED_PRINTER.fullmatch(content) is not None,
                        id_ + ": invalid programmed printer bytes")
            if name == "screen.png":
                try:
                    check_png(content)
                except Invalid:
                    raise
                except Exception as err:
                    raise Invalid(id_ + ": invalid original screenshot PNG") from err
            d = desc[name]
            require(type(d.get("size_bytes")) is int and len(content) == d["size_bytes"] and
                    digest(content) == d.get("sha256"),
                    id_ + ": sha/size mismatch " + name)
            raw[name] = content
            expected_inventory.add(id_ + "/" + name)
        require(raw["source.bas"] == expected_source,
                id_ + ": source bytes differ from original/instrumented identity")
        trace = load(work / "autocmd.json")
        expected_commands = commands_for(expected_source)
        require(trace.get("commands") == expected_commands and
                entry.get("commands") == expected_commands and
                trace.get("channel") == mode and trace.get("case") == case and
                trace.get("source_sha256") == digest(expected_source) and
                trace.get("original_source_sha256") == original_sha and
                trace.get("new_cpc_process") is True and
                trace.get("programmed_print") is True and
                trace.get("run_executed") is True and
                trace.get("direct_probe_after_run") is False,
                id_ + ": command chronology/mode invalid")
        cfg = configparser.ConfigParser(interpolation=None)
        require(bool(cfg.read(work / "cap32.cfg")) and
                cfg.get("system", "model") == "2" and
                cfg.get("system", "ram_size") == "128" and
                cfg.get("system", "printer") == ("1" if mode == "printer" else "0") and
                cfg.get("file", "printer_file").endswith(
                    "/" + id_ + ("/printer.dat" if mode == "printer"
                                 else "/unexpected-printer.dat")) and
                cfg.get("file", "sdump_dir").endswith("/" + id_),
                id_ + ": CPC config/channel invalid")
        argv = load(work / "command_argv.json")
        require(isinstance(argv, list) and len(argv) == 5 + 2 * len(expected_commands) and
                argv[0:2] == ["xvfb-run", "-a"] and
                argv[3] == "-c" and
                argv[4].endswith("/" + id_ + "/cap32.cfg") and
                argv[5::2] == ["-a"] * len(expected_commands) and
                argv[6::2] == expected_commands,
                id_ + ": executable argv/order changed")
        expected_log = ("$ " + shlex.join(argv) + "\nexit code: 0\n").encode()
        require(raw["caprice.log"].startswith(expected_log),
                id_ + ": command execution log does not match argv")
        require(re.fullmatch(r"screenshot_[0-9_]+\.png",
                             entry.get("original_screen_name", "")) and
                entry["original_screen_name"].encode() in raw["caprice.log"],
                id_ + ": screenshot chronology unverified")
        if mode == "screen":
            require(raw["native.stdin.bin"] == historical + b"RUN\n:step 100\n:quit\n",
                    id_ + ": native original/RUN chronology altered")
            require(signed(raw["native.stdout.bin"], SIGNED_NATIVE) == integer and
                    b"[cli:error]" not in raw["native.stderr.bin"],
                    id_ + ": native value/output unsupported or changed")
            observations[case + "_native"] = raw["native.stdout.bin"]
        else:
            value = signed(raw["printer.dat"], SIGNED_PRINTER)
            require(value == integer,
                    id_ + ": CPC programmed numeric result differs from witness")
            observations[case + "_printer"] = raw["printer.dat"]
    found = {p.relative_to(base).as_posix()
             for p in base.rglob("*") if p.is_file()}
    require(found == expected_inventory, "extra or unclassified evidence files")
    for case in CASES:
        program = observations[case + "_printer"]
        direct = c6_direct(case)
        native = observations[case + "_native"]
        compare = "MATCH_EXACT" if program == direct else "DIFF"
        print(case, "CPC printer(programmed)=", program.hex(" ").upper(),
              "CPC printer(direct C6)=", direct.hex(" ").upper(),
              "same-channel=", compare,
              "C99 stdout=", native.hex(" ").upper(),
              "CPC-versus-CLI=MATCH_SEMANTIC; screen=VISUAL_OBSERVATION",
              flush=True)
        # The approved C/D printer-to-printer oracle is a hard acceptance
        # gate for BOTH fresh and permanent acquisitions. Numeric parsing
        # and valid provenance alone must never authorize a formatting DIFF.
        require(program == direct,
                f"{case}: CPC printer programmed/direct DIFF "
                f"expected={direct.hex(' ').upper()} "
                f"observed={program.hex(' ').upper()}")
    return observations


def self_test(base, permanent):
    # Every mutation starts from a pristine copy which has passed the FULL
    # validator; an unrelated initial error cannot yield a false positive.
    cases = [
        ("printer_forgery", "c_integer_add_printer: CPC programmed numeric result differs from witness"),
        ("printer_hash", "c_integer_add_printer: sha/size mismatch printer.dat"),
        ("command_order", "c_integer_add_screen: command chronology/mode invalid"),
        ("missing_screen", "d_self_reference_screen: missing file screen.png"),
        ("channel_conflation", "screen/printer conflated"),
        ("source_forgery", "c_integer_add_screen: source bytes differ from original/instrumented identity"),
        ("printer_leading_space",
         "c_integer_add: CPC printer programmed/direct DIFF "
         "expected=20 35 20 0D 0A observed=35 20 0D 0A"),
        ("printer_crlf",
         "d_self_reference: CPC printer programmed/direct DIFF "
         "expected=20 32 20 0D 0A observed=20 32 20 0A"),
    ]
    with tempfile.TemporaryDirectory() as td:
        for name, reason in cases:
            dest = Path(td) / name
            shutil.copytree(base, dest)
            # The original archive passed permanent validation. In the COPY
            # remove only the external approval wrapper so each mutation
            # reaches its precise evidence check instead of the outer anchor.
            if permanent:
                original = (dest / "acquisition.json").read_bytes()
                (dest / "manifest.json").write_bytes(original)
                (dest / "acquisition.json").unlink()
            verify(dest, permanent=False)
            manifest = load(dest / "manifest.json")
            entries = {c["id"]: c for c in manifest["captures"]}
            screen = entries["c_integer_add_screen"]
            printer = entries["c_integer_add_printer"]
            if name in ("printer_forgery", "printer_hash"):
                path = dest / "c_integer_add_printer/printer.dat"
                changed = b" 0 \r\n"
                path.write_bytes(changed)
                if name == "printer_forgery":
                    printer["files"]["printer.dat"] = {
                        "sha256": digest(changed), "size_bytes": len(changed)}
            elif name == "command_order":
                screen["commands"][-2:] = list(reversed(screen["commands"][-2:]))
            elif name == "missing_screen":
                (dest / "d_self_reference_screen/screen.png").unlink()
            elif name == "channel_conflation":
                manifest["printer_screen_equivalent"] = True
            elif name == "source_forgery":
                p = dest / "c_integer_add_screen/source.bas"
                changed = p.read_bytes().replace(b"30 PRINT B%", b"30 PRINT A%")
                p.write_bytes(changed)
                screen["files"]["source.bas"] = {
                    "sha256": digest(changed), "size_bytes": len(changed)}
            elif name in ("printer_leading_space", "printer_crlf"):
                # Keep the signed integer and legitimate printer grammar.
                # Recompute the descriptor to bypass hash/size rejection:
                # ONLY the byte-exact C6 acceptance gate may reject this.
                target = ("c_integer_add_printer" if name == "printer_leading_space"
                          else "d_self_reference_printer")
                expected = C6_PRINTER_RAW["c_integer_add" if name == "printer_leading_space"
                                          else "d_self_reference"]
                changed = (b"35 20 0D 0A" if name == "printer_leading_space"
                           else b"20 32 20 0A")
                # Hex literals above are bytes, not their ASCII spellings.
                changed = bytes.fromhex(changed.decode("ascii"))
                require(changed != expected, name + ": no presentation mutation")
                p = dest / target / "printer.dat"
                require(p.read_bytes() == expected, name + ": pristine byte mismatch")
                p.write_bytes(changed)
                entries[target]["files"]["printer.dat"] = {
                    "sha256": digest(changed), "size_bytes": len(changed)}
            (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            try:
                verify(dest, permanent=False)
            except Invalid as e:
                require(str(e) == reason,
                        name + ": WRONG REJECTION CAUSE " + str(e) + " != " + reason)
                print("PASS EXPECTED_REJECTION", name, "cause=", str(e))
            else:
                raise Invalid(name + ": FORGERY NOT REJECTED")



def archival_self_test(base):
    """Independently pinned permanent approval must reject forged wrappers."""
    cases = (
        ("artifact_id", "unapproved artifact/manifest anchor"),
        ("acquisition_sha", "approved acquisition SHA-256 mismatch"),
        ("missing_acquisition", "approved acquisition missing"),
    )
    with tempfile.TemporaryDirectory() as td:
        for name, reason in cases:
            dest = Path(td) / name
            shutil.copytree(base, dest)
            verify(dest, permanent=True)  # Mandatory clean positive check.
            manifest = dest / "manifest.json"
            acquisition = dest / "acquisition.json"
            if name == "artifact_id":
                data = load(manifest)
                data["original_artifact"]["artifact_id"] += 1
                manifest.write_text(json.dumps(data, indent=2) + "\n")
            elif name == "acquisition_sha":
                acquisition.write_bytes(acquisition.read_bytes().replace(
                    b'"phase": "J0.27-A"', b'"phase": "J0.27-X"'))
            else:
                acquisition.unlink()
            try:
                verify(dest, permanent=True)
            except Invalid as err:
                require(str(err) == reason,
                        name + ": WRONG REJECTION CAUSE " + str(err))
                print("PASS EXPECTED_ARCHIVAL_REJECTION", name,
                      "cause=", str(err), flush=True)
            else:
                raise Invalid(name + ": FORGED PERMANENT ARCHIVE ACCEPTED")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--permanent", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    verify(args.evidence.resolve(), args.permanent)
    print("PASS POSITIVE INTACT EVIDENCE")
    if args.self_test:
        self_test(args.evidence.resolve(), args.permanent)
        if args.permanent:
            archival_self_test(args.evidence.resolve())


if __name__ == "__main__":
    try:
        main()
    except (Invalid, OSError, ValueError, KeyError, TypeError,
            configparser.Error, json.JSONDecodeError) as e:
        print("J0.27-A VALIDATION FAILED:", e, file=sys.stderr)
        sys.exit(1)
