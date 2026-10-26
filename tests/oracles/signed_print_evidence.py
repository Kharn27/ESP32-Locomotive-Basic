#!/usr/bin/env python3
"""J0.27-B1: strict provenance and channel validation of 12 CPC PRINT observations.

There are deliberately NO approved CPC format bytes in this validator.
An observed CPC historical error is an *unreviewed screenshot*, never a
fabricated number or a byte-exact screen observation.
"""
import argparse
import configparser
import json
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile

from signed_print_oracle import (VALUES, SOURCE_ROOT, ROOT, SCREEN_FILES,
                                 PRINTER_FILES, INTEGER_LINE, commands_for,
                                 digest, parse_integer, variant)
from numeric_print_oracle import CAPTURE, PIN, ROM_SHA, AMSDOS_SHA
from cpc_screen_evidence import check_png

CASES = {case + "_" + channel
         for case in VALUES for channel in ("screen", "printer")}


class Invalid(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Invalid(reason)


def load(path):
    return json.loads(path.read_bytes())


def verify(base, require_six_prints=False):
    require(base.is_dir(), "missing J0.27-B1 directory")
    require((base / "manifest.json").is_file(), "missing manifest.json")
    m = load(base / "manifest.json")
    require(m.get("schema_version") == 1 and m.get("phase") == "J0.27-B1" and
            m.get("screen_bytes_extracted") is False and
            m.get("printer_screen_equivalent") is False,
            "invalid schema or screen/printer conflation")
    o = m.get("oracle", {})
    require(o.get("name") == "Caprice32" and o.get("commit") == PIN and
            o.get("model") == "CPC6128" and o.get("ram_kb") == 128 and
            o.get("basic") == "1.1" and
            "4.6.0" in o.get("version_output", "") and
            o.get("rom_sha256") == ROM_SHA and
            o.get("amsdos_sha256") == AMSDOS_SHA and
            o.get("rom_archived") is False and o.get("snapshot_archived") is False,
            "CPC provenance mismatch")
    runid, sha = m.get("github_run_id"), m.get("github_sha")
    require((runid is None and sha is None) or
            (isinstance(runid, str) and re.fullmatch(r"[0-9]+", runid) and
             isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)),
            "incomplete acquisition run provenance")
    captures = m.get("captures")
    require(isinstance(captures, list) and len(captures) == len(CASES) and
            {r.get("id") for r in captures} == CASES,
            "twelve unique CPC processes required")
    inventory = {"manifest.json"}
    outcomes = {}
    for entry in captures:
        id_ = entry["id"]
        case, mode = entry.get("case"), entry.get("mode")
        require(case in VALUES and mode in ("screen", "printer") and
                id_ == case + "_" + mode, id_ + ": invalid case/channel")
        value = VALUES[case]
        source_path = "tests/oracles/inputs/j027_b1/" + case + ".bas"
        original = (SOURCE_ROOT / (case + ".bas")).read_bytes()
        require(original == (f"10 B%={value}\n20 PRINT B%\n30 END\n").encode("ascii"),
                id_ + ": historical input corpus altered")
        expected = original if mode == "screen" else variant(original)
        require(entry.get("source_path") == source_path and
                entry.get("original_sha256") == digest(original) and
                entry.get("source_sha256") == digest(expected) and
                entry.get("hypothesis_integer") == value,
                id_ + ": source/case metadata invalid")
        require(entry.get("screen_status") == "VISUAL_OBSERVATION" and
                entry.get("screen_text_bytes_extracted") is False and
                entry.get("printer_screen_equivalent") is False,
                id_ + ": screen bytes wrongly equated to printer")
        require(entry.get("cpc_returncode") == 0, id_ + ": emulator exited abnormally")
        work = base / id_
        require(work.is_dir() and not work.is_symlink(),
                id_ + ": missing unsafe CPC session directory")
        printer_exists = (work / "printer.dat").is_file()
        files = list(SCREEN_FILES if mode == "screen" else PRINTER_FILES)
        if mode == "printer" and printer_exists:
            files.append("printer.dat")
        desc = entry.get("files", {})
        require(set(desc) == set(files), id_ + ": missing/extra evidence descriptor")
        contents = {}
        for name in files:
            p = work / name
            require(p.is_file() and not p.is_symlink(),
                    id_ + ": missing evidence file " + name)
            data = p.read_bytes()
            d = desc[name]
            require(type(d.get("size_bytes")) is int and
                    len(data) == d["size_bytes"] and
                    digest(data) == d.get("sha256"),
                    id_ + ": SHA/size mismatch " + name)
            if name == "screen.png":
                try:
                    check_png(data)
                except Exception as err:
                    raise Invalid(id_ + ": authentic PNG corrupt") from err
            contents[name] = data
            inventory.add(id_ + "/" + name)
        require(contents["original.bas"] == original and
                contents["source.bas"] == expected,
                id_ + ": BASIC original/instrumented text forged")
        trace = load(work / "autocmd.json")
        commands = commands_for(expected)
        require(trace.get("id") == id_ and
                trace.get("case") == case and trace.get("mode") == mode and
                trace.get("fresh_process") is True and
                trace.get("run_executed") is True and
                trace.get("direct_post_run_probe") is False and
                trace.get("original_sha256") == digest(original) and
                trace.get("source_sha256") == digest(expected) and
                trace.get("commands") == commands and
                entry.get("commands") == commands,
                id_ + ": BASIC command sequence/order invalid")
        cfg = configparser.ConfigParser(interpolation=None)
        require(bool(cfg.read(work / "cap32.cfg")) and
                cfg.get("system", "model") == "2" and
                cfg.get("system", "ram_size") == "128" and
                cfg.get("system", "printer") == ("1" if mode == "printer" else "0") and
                cfg.get("file", "printer_file").endswith(
                    "/" + id_ + ("/printer.dat" if mode == "printer"
                                 else "/unexpected-printer.dat")) and
                cfg.get("file", "sdump_dir").endswith("/" + id_),
                id_ + ": emulator channel or machine configuration invalid")
        argv = load(work / "command_argv.json")
        require(isinstance(argv, list) and len(argv) == 5 + 2 * len(commands) and
                argv[0:2] == ["xvfb-run", "-a"] and
                argv[3] == "-c" and
                argv[4].endswith("/" + id_ + "/cap32.cfg") and
                argv[5::2] == ["-a"] * len(commands) and
                argv[6::2] == commands,
                id_ + ": executable argv/command order forged")
        require(contents["caprice.log"].startswith(
                    ("$ " + shlex.join(argv) + "\nexit code: 0\n").encode()),
                id_ + ": executed Caprice32 command log incompatible")
        require(re.fullmatch(r"screenshot_[0-9_]+\.png",
                             entry.get("original_screenshot_name", "")) is not None and
                entry["original_screenshot_name"].encode() in contents["caprice.log"],
                id_ + ": screenshot chronology invalid")
        if mode == "screen":
            require(not printer_exists, id_ + ": printer data in screen session")
            require(contents["native.stdin.bin"] == original + b"RUN\n:step 100\n:quit\n",
                    id_ + ": native execution inputs invalid")
            native = parse_integer(contents["native.stdout.bin"])
            native_status = ("UNSUPPORTED" if b"[cli:error]" in contents["native.stderr.bin"]
                             or entry.get("native_returncode") != 0 else
                             "OBSERVED" if native is not None else "UNVERIFIED")
            require(entry.get("native_status") == native_status and
                    entry.get("native_observation") == native and
                    type(entry.get("native_returncode")) is int,
                    id_ + ": native output/UNSUPPORTED classification forged")
            require(entry.get("cpc_printer_status") == "VISUAL_OBSERVATION" and
                    entry.get("printer_observation") is None and
                    entry.get("printer_raw_hex") is None,
                    id_ + ": screen data promoted to printer")
            outcomes[id_] = {"screen": "VISUAL_OBSERVATION",
                             "native_status": native_status,
                             "native": native}
        else:
            require(entry.get("native_status") is None and
                    entry.get("native_observation") is None and
                    entry.get("native_returncode") is None,
                    id_ + ": printer session conflated with CLI")
            printer = contents.get("printer.dat")
            parsed = parse_integer(printer) if printer is not None else None
            status = ("PRINT_NUMERIC" if parsed is not None else
                      "NO_NUMERIC_PRINTER_OUTPUT_REVIEW_REQUIRED")
            require(entry.get("cpc_printer_status") == status and
                    entry.get("printer_observation") == parsed and
                    entry.get("printer_raw_hex") == (
                        printer.hex(" ").upper() if printer is not None else None),
                    id_ + ": printer bytes or derived observation falsified")
            # An unexpected CPC numeric value is not silently corrected to
            # the hypothesized integer; it is a documented discrepancy.
            # In a non-numeric/error case, screenshot review is mandatory.
            require(parsed is None or parsed["numeric_value"] == value,
                    id_ + ": CPC printed integer differs from BASIC assignment")
            outcomes[id_] = {"status": status,
                             "observation": parsed,
                             "raw_hex": entry["printer_raw_hex"]}
    present = {p.relative_to(base).as_posix()
               for p in base.rglob("*") if p.is_file()}
    require(present == inventory, "unexpected/missing evidence file inventory")
    for case, value in VALUES.items():
        printer, screen = outcomes[case + "_printer"], outcomes[case + "_screen"]
        if require_six_prints:
            # Structural validation deliberately allows an error screenshot.
            # The acceptance gate cannot silently pass an unreviewed CPC
            # error or missing printer stream as a successful observation.
            require(printer["status"] == "PRINT_NUMERIC",
                    case + ": missing numeric CPC proof; historical "
                    "screenshot diagnosis requires independent review")
        print(case, "hypothesis=", value,
              "printer=", printer["raw_hex"], "status=", printer["status"],
              "C99=", screen["native_status"], "screen=VISUAL_OBSERVATION",
              flush=True)
    return outcomes


def self_test(base):
    """Every forgery begins with a complete copy passing ALL validation."""
    cases = (
        ("lost_minus_sign",
         "minus_twelve_printer: CPC printed integer differs from BASIC assignment"),
        ("changed_digit",
         "five_printer: CPC printed integer differs from BASIC assignment"),
        ("missing_png", "zero_screen: missing evidence file screen.png"),
        ("command_order", "zero_screen: BASIC command sequence/order invalid"),
        ("forged_sha", "five_printer: SHA/size mismatch source.bas"),
        ("screen_as_printer", "zero_screen: screen bytes wrongly equated to printer"),
    )
    with tempfile.TemporaryDirectory() as td:
        for name, reason in cases:
            dest = Path(td) / name
            shutil.copytree(base, dest)
            verify(dest)
            m = load(dest / "manifest.json")
            records = {c["id"]: c for c in m["captures"]}
            if name in ("lost_minus_sign", "changed_digit"):
                target = "minus_twelve_printer" if name == "lost_minus_sign" else "five_printer"
                p = dest / target / "printer.dat"
                require(p.is_file(), name + ": authentic CPC printer evidence required")
                old = p.read_bytes()
                require(INTEGER_LINE.fullmatch(old) is not None,
                        name + ": authentic CPC numeric record required")
                parts = INTEGER_LINE.fullmatch(old).groups()
                if name == "lost_minus_sign":
                    require(parts[1] == b"-", name + ": negative sign absent in genuine CPC record")
                    altered = parts[0] + parts[2] + parts[3] + parts[4]
                else:
                    digit = parts[2]
                    modified = b"9" if digit != b"9" else b"8"
                    altered = parts[0] + parts[1] + modified + parts[3] + parts[4]
                p.write_bytes(altered)
                # A hash-only failure must NOT satisfy the mutation.
                records[target]["files"]["printer.dat"] = {
                    "sha256": digest(altered), "size_bytes": len(altered)}
                records[target]["printer_observation"] = parse_integer(altered)
                records[target]["printer_raw_hex"] = altered.hex(" ").upper()
            elif name == "missing_png":
                (dest / "zero_screen/screen.png").unlink()
            elif name == "command_order":
                records["zero_screen"]["commands"][-2:] = list(
                    reversed(records["zero_screen"]["commands"][-2:]))
            elif name == "forged_sha":
                records["five_printer"]["files"]["source.bas"]["sha256"] = "0" * 64
            elif name == "screen_as_printer":
                records["zero_screen"]["printer_screen_equivalent"] = True
            (dest / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
            try:
                verify(dest)
            except Invalid as err:
                require(str(err) == reason,
                        name + ": WRONG CAUSE " + str(err) + " != " + reason)
                print("PASS EXPECTED_REJECTION", name, "cause=", str(err),
                      flush=True)
            else:
                raise Invalid(name + ": forged evidence unexpectedly accepted")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", required=True, type=Path)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--permanent", action="store_true",
                   help="validate Pilotage-approved J0.27-B2 sealed archive")
    p.add_argument("--require-six-prints", action="store_true",
                   help="fail closed if any of the six CPC values lacks raw printer proof")
    args = p.parse_args()
    base = args.evidence.resolve()
    if args.permanent:
        from signed_print_permanent import verify_permanent, self_test_permanent
        verify_permanent(base)
        if args.self_test:
            self_test_permanent(base)
        return
    verify(base, require_six_prints=args.require_six_prints)
    print("PASS POSITIVE INTACT B1 EVIDENCE", flush=True)
    if args.self_test:
        self_test(base)


if __name__ == "__main__":
    try:
        main()
    except (Invalid, OSError, ValueError, KeyError, TypeError,
            configparser.Error, json.JSONDecodeError) as err:
        print("J0.27-B1 VALIDATION FAILED:", err, file=sys.stderr)
        sys.exit(1)
