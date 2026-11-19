#!/usr/bin/env python3
"""CLK-04-A7: sealed A2 printer-byte crosscheck against unchanged A6 C99.

The two CPC sessions predate A7. Nothing here emulates the CPC, supplies an
expected PRINT text, or derives printer bytes from REAL5 / Decimal / Python.
Any invalid provenance or ambiguous address/PRINT alignment is a hard error.
"""
import argparse
import collections
import csv
import ctypes
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile

A2_HEAD = "a9355e507ad17531163c8d578cc3f451c63f5dad"
A6_MAIN = "902f3abeaf6fc9244236b397ddd1f278cf545b09"
A2_MANIFEST_SHA = "aaa77eed457f51d28e7eee7d06e17d2457cf3c5fb95ae6bfafabbe2db2202014"
A2_CORPUS_SHA = "9c36655e872f0a4d2af423f242c8185dfb7053fa418bf81e4ac608f1b5588d53"
A2_ZIPS = {
    "raw": "d0316f543834206166e1db46cd26a2d005e9b98be74df1bbb39f65bab66117b6",
    "seal": "3cb7ce6e99a192baff11626c218df8104219e0d75efb47735727d0f8e3c9af30",
    "comparison": "3c0ad4bf15abe91403c544653661b2cc8b9b4df87a8d51566743504cabbc0807",
}
A6_BLOBS = {"c": "fc54657476bca93ff846a2c284a4b87d7ffc0424",
            "h": "b6899e5185bf6d30e0831a71eb165ddf5bab624d"}
CAPRICE = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
ROM = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
IMAGE = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
         "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")
SESSIONS = ("original", "repeat")
FIELD_RE = re.compile(rb"(?: [0-9]+(?:\.[0-9]+E\+[0-9]{2})?|-1) \r\n\Z")
LINE_RE = re.compile(r"^\d+ PRINT #8,(.+)$")


class AuditError(ValueError):
    """A2 authenticity / parse failure; never interpreted as C99 mismatch."""


def need(condition, reason):
    if not condition:
        raise AuditError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_json(data, context):
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuditError("JSON_INVALID_" + context) from exc


def zip_verified(path, digest, max_bytes):
    raw = Path(path).read_bytes()
    need(sha(raw) == digest, "ZIP_SHA_DRIFT_" + str(path))
    need(len(raw) <= max_bytes, "ZIP_SIZE_LIMIT")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = z.namelist()
        need(len(names) == len(set(names)) and names, "ZIP_DUPLICATE_OR_EMPTY")
        for info in z.infolist():
            name = info.filename
            pure = PurePosixPath(name)
            need(not info.is_dir() and not name.startswith("/") and
                 "\\" not in name and ".." not in pure.parts and
                 name == str(pure) and info.file_size <= 200000,
                 "ZIP_UNSAFE_MEMBER")
        return z
    except (zipfile.BadZipFile, OSError) as exc:
        raise AuditError("ZIP_INVALID") from exc


def check_inventory(z, external_sha=A2_MANIFEST_SHA):
    """Also directly unit-tested with synthetic tampered zip (HOST_ONLY)."""
    need("manifest.json" in z.namelist(), "MANIFEST_MISSING")
    raw = z.read("manifest.json")
    need(sha(raw) == external_sha, "EXTERNAL_MANIFEST_SHA_DRIFT")
    obj = parse_json(raw, "MANIFEST")
    members = obj.get("files")
    need(isinstance(members, dict) and len(members) == 360,
         "INVENTORY_CARDINALITY")
    need(set(z.namelist()) == set(members) | {"manifest.json"},
         "INVENTORY_MEMBERSHIP")
    for name, desc in members.items():
        need(isinstance(desc, dict) and
             set(desc) == {"bytes", "sha256"}, "INVENTORY_ENTRY_SCHEMA")
        data = z.read(name)
        need(type(desc["bytes"]) is int and len(data) == desc["bytes"],
             "INVENTORY_SIZE:" + name)
        need(sha(data) == desc["sha256"], "INVENTORY_SHA:" + name)
    need(obj.get("schema") == 1 and obj.get("mission") == "CLK-04-A2" and
         obj.get("head") == A2_HEAD and obj.get("run_id") == "42653720557" and
         obj.get("caprice_commit") == CAPRICE and
         obj.get("rom_sha256") == ROM and obj.get("image") == IMAGE and
         obj.get("corpus_sha256") == A2_CORPUS_SHA and
         obj.get("rom_archived") is False and
         obj.get("snapshot_archived") is False and
         obj.get("observation_class") == "CPC6128_CAPRICE32_ROM_BACKED",
         "MANIFEST_PROVENANCE")
    return obj


def check_corpus(raw):
    need(sha(raw) == A2_CORPUS_SHA, "CORPUS_SHA_DRIFT")
    obj = parse_json(raw, "CORPUS")
    need(obj.get("schema") == 1 and obj.get("mission") == "CLK-04-A2" and
         obj.get("status") == "SEALED_INPUTS_NOT_OBSERVATIONS" and
         len(obj.get("cases", [])) == 11, "CORPUS_PROVENANCE")
    cases = obj["cases"]
    values = [i["value"] for case in cases for i in case["items"]]
    need(len(values) == len(set(values)) == 37 and
         sum(bool(i["arithmetic"]) for case in cases for i in case["items"]) == 14,
         "CORPUS_37_14")
    need([c["id"] for c in cases] ==
         ["D0_%02d" % n for n in range(1, 7)] +
         ["D1_%02d" % n for n in range(1, 4)] +
         ["D2_%02d" % n for n in range(1, 3)], "CORPUS_CASE_ORDER")
    for case in cases:
        for item in case["items"]:
            need(re.fullmatch(r"0|[1-9][0-9]*", item["value"]) is not None and
                 int(item["value"]) <= 4294967295, "CORPUS_INTEGER")
            expected_tier = ("D0" if int(item["value"]) <= 65536 else
                             "D1" if int(item["value"]) <= 2147483647 else "D2")
            need(case["tier"] == expected_tier, "CORPUS_TIER")
    return cases


def lines(raw, count):
    need(raw.endswith(b"\r\n") and b"\n" not in raw.replace(b"\r\n", b""),
         "PRINTER_CRLF")
    parts = [x + b"\r\n" for x in raw[:-2].split(b"\r\n")]
    need(len(parts) == count and all(FIELD_RE.fullmatch(x) for x in parts),
         "PRINTER_CARDINALITY_OR_SYNTAX")
    return parts


def check_decimal_metadata(raw, numeric_string):
    """Cross-check only historic report TEXT; never synthesize CPC expectations."""
    try:
        got = Decimal(raw[:-2].strip().decode("ascii"))
        previous = Decimal(numeric_string)
    except (InvalidOperation, ValueError, UnicodeDecodeError) as exc:
        raise AuditError("REPORT_NUMBER_INVALID") from exc
    need(got == previous, "REPORT_PRINTER_TEXT_DRIFT")


def check_window(z, base, expected_vars):
    st = parse_json(z.read(base + "/stop.json"), "STOP")
    window = z.read(base + "/window.bin")
    ptr = st["pointers"]
    start, end = ptr["scalar_start"], ptr["array_start"]
    need(ptr["program_end"] <= start < end <= ptr["array_end"] and
         st["ram_window_start"] == start and st["ram_window_end"] == end and
         len(window) == end - start and sha(window) == st["ram_window_sha256"],
         "STOP_WINDOW_POINTER_OR_SHA")
    entries = st.get("entries", {})
    need(set(entries) == {str(ord(v[0])) for v in expected_vars},
         "STOP_VARIABLE_SET")
    for key, e in entries.items():
        off = e["entry_offset"]
        need(type(off) is int and off >= 0 and off + 9 <= len(window) and
             e["address"] == start + off + 4 and
             e["name_byte"] == (int(key) | 0x80) and
             e["type_byte"] == 4 and
             window[off:off+2].hex(" ").upper() == e["link_hex"] and
             window[off+2] == e["name_byte"] and
             window[off+3] == e["type_byte"] and
             window[off+4:off+9].hex(" ").upper() == e["value_hex"],
             "STOP_RAM_ENTRY_OR_OFFSET:" + key)
    need(set(range(0, len(window), 9)) == {e["entry_offset"] for e in entries.values()}
         and len(window) == len(entries)*9, "STOP_RAM_LAYOUT")
    return entries


def expression_fields(items):
    """Describe source BASIC expression roles, not preformatted print text."""
    for item in items:
        v, n = item["variable"], int(item["value"])
        yield ("@" + v, "address", v, None)
        yield (v, "primary", v, n)
        a = item["arithmetic_variable"]
        if item["arithmetic"]:
            yield ("@" + a, "alternate_address", a, None)
            yield (a, "alternate", a, n)
            yield (v + "=" + a, "equality_probe", v, -1)
            yield ("(" + a + "+1)-" + a, "plus_probe", a, 1)
            yield (a + "-(" + a + "-1)", "minus_probe", a, 1)


def check_case(z, session, case, comparison):
    prefix = session + "/" + case["id"]
    raw = z.read(prefix + "/run/printer.dat")
    source = case["lines"]
    script_expr = [LINE_RE.fullmatch(row).group(1) for row in source
                   if LINE_RE.fullmatch(row)]
    fields = list(expression_fields(case["items"]))
    need(script_expr == [f[0] for f in fields] and
         case["printer_numeric_count"] == len(fields), "BASIC_PRINT_ORDER")
    printer = lines(raw, len(fields))
    # LIST canonicalizes long numeric literals to a 9-significant-digit
    # spelling; requiring byte-identical source would incorrectly reject A2.
    listed = z.read(prefix + "/list/printer.dat")
    need(listed.endswith(b"\r\n"), "BASIC_LIST_CRLF")
    rendered = listed[:-2].decode("ascii").split("\r\n")
    need(len(rendered) == len(source), "BASIC_LIST_COUNT")
    for given, observed in zip(source, rendered):
        if given == observed:
            continue
        match = re.fullmatch(r"(\d+ [A-Z]!=)([0-9]+)", given)
        need(match is not None and
             re.fullmatch(re.escape(match.group(1)) +
                          r"[0-9]\.[0-9]+E\+[0-9]{2}", observed) is not None,
             "BASIC_LIST_UNEXPECTED_CANONICALIZATION")
    commands = parse_json(z.read(prefix + "/run/autocmd.json"), "AUTOCMD")["commands"]
    need(commands[0:2] == ["MODE 1", "NEW"] and
         commands[2:2+len(source)] == source and
         commands[2+len(source)] == "RUN" and
         "CONT" in commands[3+len(source):], "AUTOCMD_PROGRAM_DRIFT")
    need(len(z.read(prefix + "/program.bin")) > 0 and
         len(z.read(prefix + "/stop_program.bin")) > 0, "PROGRAM_EMPTY")
    variables = {item["variable"] for item in case["items"]}
    variables.update(item["arithmetic_variable"] for item in case["items"]
                     if item["arithmetic"])
    entries = check_window(z, prefix, variables)
    output=[]
    start=0
    for (expr, role, var, n), rawline in zip(fields, printer):
        sample = comparison[(session, case["id"],
                             next(item["variable"] for item in case["items"]
                                  if var == item["variable"] or
                                  var == item["arithmetic_variable"]))]
        e = entries[str(ord(var[0]))]
        if role in ("address", "alternate_address"):
            need(rawline == (" %d \r\n" % e["address"]).encode("ascii"),
                 "PRINTER_ADDRESS_OR_ALIGNMENT")
            need(e["address"] == sample["address" if role == "address"
                                                else "arithmetic_address"],
                 "REPORT_ADDRESS_DRIFT")
        else:
            if role in ("primary", "alternate"):
                report_field = ("cpc_print" if role == "primary" else
                                "arithmetic_print")
                report_bytes = ("cpc_real5_hex" if role == "primary" else
                                "arithmetic_real5_hex")
                need(e["value_hex"] == sample[report_bytes],
                     "REPORT_REAL5_RAM_DRIFT")
                check_decimal_metadata(rawline, sample[report_field])
            else:
                meta = {"equality_probe": "cpc_equal", "plus_probe": "cpc_plus_step",
                        "minus_probe": "cpc_minus_step"}[role]
                check_decimal_metadata(rawline, sample[meta])
                need(Decimal(sample[meta]) == n, "PROBE_SEMANTICS_DRIFT")
        output.append({"session": session, "case": case["id"], "tier": case["tier"],
                       "value_requested": sample["value_requested"],
                       "variable": var, "role": role, "basic_expression": expr,
                       "printer_file": prefix + "/run/printer.dat",
                       "byte_offset": start, "byte_count": len(rawline),
                       "cpc_hex": rawline.hex().upper(),
                       "cpc_text": rawline[:-2].decode("ascii"),
                       "candidate_input": n})
        start += len(rawline)
    need(start == len(raw), "PRINTER_TRAILING_DATA")
    return output


def github_blob_sha(data):
    raw = ("blob %d\0" % len(data)).encode("ascii") + data
    return hashlib.sha1(raw).hexdigest()


class Candidate:
    def __init__(self, src, header, compiler, target_dir):
        files = {"c": Path(src), "h": Path(header)}
        for ext, path in files.items():
            need(github_blob_sha(path.read_bytes()) == A6_BLOBS[ext],
                 "A6_CANDIDATE_GIT_BLOB_DRIFT:" + ext)
        so = Path(target_dir) / "a6_print_a7_audit.so"
        cmd = [compiler, "-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic",
               "-O2", "-fPIC", "-shared", str(src), "-o", str(so)]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        need(proc.returncode == 0, "C99_COMPILE_FAILED:" + proc.stderr[:500])
        self.lib = ctypes.CDLL(str(so))
        func = self.lib.a4_print_candidate
        func.argtypes = [ctypes.c_int64, ctypes.POINTER(ctypes.c_uint8),
                         ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        func.restype = ctypes.c_int
        self.func = func

    def compare(self, value, observed):
        buf = (ctypes.c_uint8 * 32)(*([0xA5]*32))
        used = ctypes.c_size_t(12345)
        status = self.func(value, buf, len(buf), ctypes.byref(used))
        if status == 1:
            need(used.value == 12345 and bytes(buf) == b"\xa5"*32,
                 "C99_UNSUPPORTED_MUTATED_OUTPUT")
            return "C99_UNSUPPORTED", ""
        need(status == 0 and used.value <= 32 and
             bytes(buf)[used.value:] == b"\xa5"*(32-used.value),
             "C99_INVALID_OR_MUTATED_OUTPUT")
        got = bytes(buf)[:used.value]
        return ("C99_CANDIDATE_MATCH" if got == observed else
                "C99_CANDIDATE_MISMATCH"), got.hex().upper()


def check_seal(sealed):
    need(sealed.get("mission") == "CLK-04-A2" and
         sealed.get("head") == A2_HEAD and
         sealed.get("manifest_sha256") == A2_MANIFEST_SHA and
         sealed.get("origin") == "GitHub Actions acquisition job logs / output",
         "EXTERNAL_SEAL_DRIFT")


def check_sessions(manifest, cases):
    expected_cases = {case["id"] for case in cases}
    need(set(manifest.get("sessions", {})) == set(SESSIONS), "SESSION_SET")
    for name in SESSIONS:
        session = manifest["sessions"][name]
        need(set(session["cases"]) == expected_cases and
             session["boot"]["returncode"] == 0 and
             all(session["gate"][g]["returncode"] == 0
                 for g in ("short", "long")) and
             all(v["run"]["returncode"] == 0 and
                 v["list"]["returncode"] == 0
                 for v in session["cases"].values()), "SESSION_INCOMPLETE")
    need(manifest["sessions"]["original"]["boot"]["started_utc"] !=
         manifest["sessions"]["repeat"]["boot"]["started_utc"],
         "SESSIONS_NOT_DISTINCT")


def audit(raw_path, seal_path, comparison_path, corpus_path, source, header, cc):
    # ZIP SHA pins are GitHub Actions artifact API digest, not an internally
    # recomputed, self-certifying manifest.
    z = zip_verified(raw_path, A2_ZIPS["raw"], 2000000)
    s = zip_verified(seal_path, A2_ZIPS["seal"], 10000)
    c = zip_verified(comparison_path, A2_ZIPS["comparison"], 100000)
    need(s.namelist() == ["clk04-a2-external-seal.json"] and
         c.namelist() == ["clk04-a2-comparison.json"], "SEAL_OR_REPORT_MEMBERS")
    sealed = parse_json(s.read(s.namelist()[0]), "SEAL")
    check_seal(sealed)
    manifest = check_inventory(z)
    cases = check_corpus(Path(corpus_path).read_bytes())
    report = parse_json(c.read(c.namelist()[0]), "COMPARISON")
    need(report["mission"] == "CLK-04-A2" and report["head"] == A2_HEAD and
         report["seal"] == A2_MANIFEST_SHA and len(report["samples"]) == 74 and
         report["totals"] == {"CPC_SAMPLE_MATCH": 74,
                              "CPC_SAMPLE_MISMATCH": 0,
                              "INPUT_VALUE_UNVERIFIED": 0}, "REPORT_PROVENANCE")
    check_sessions(manifest, cases)
    sample_lookup = {}
    values_per_session = collections.defaultdict(set)
    for sample in report["samples"]:
        n = sample["value_requested"]
        need(sample["session"] in SESSIONS and sample["comparison"] == "CPC_SAMPLE_MATCH"
             and sample["input_identity"] in
             ("DECIMAL_LITERAL_ONLY", "SECOND_CPC_CONSTRUCTION_CONCORDANT"),
             "REPORT_SAMPLE_NOT_AUTHENTICATED")
        values_per_session[sample["session"]].add(n)
        for case in cases:
            for item in case["items"]:
                if item["value"] == n:
                    need(item["variable"] == sample["variable"] and
                         case["tier"] == sample["tier"], "REPORT_SOURCE_DRIFT")
                    key = (sample["session"], case["id"], item["variable"])
                    need(key not in sample_lookup, "REPORT_DUPLICATE")
                    sample_lookup[key] = sample
    need(all(len(values_per_session[session]) == 37 for session in SESSIONS) and
         len(sample_lookup) == 74, "REPORT_SAMPLE_COVERAGE")
    rows=[]
    for session in SESSIONS:
        for case in cases:
            rows += check_case(z, session, case, sample_lookup)
    with tempfile.TemporaryDirectory(prefix="clk04-a7-") as td:
        candidate = Candidate(source, header, cc, td)
        for row in rows:
            n = row.pop("candidate_input")
            if n is None:
                row["classification"] = "RAW_CPC_OBSERVED"
                row["candidate_hex"] = ""
            else:
                status, data = candidate.compare(n, bytes.fromhex(row["cpc_hex"]))
                row["classification"] = status
                row["candidate_hex"] = data
    totals = dict(collections.Counter(r["classification"] for r in rows))
    need(len(rows) == 288 and totals.get("RAW_CPC_OBSERVED") == 102 and
         sum(totals.get(x, 0) for x in
             ("C99_CANDIDATE_MATCH", "C99_CANDIDATE_MISMATCH", "C99_UNSUPPORTED")) == 186,
         "FIELD_COUNTS_DRIFT")
    return {"mission": "CLK-04-A7", "comparison_scope": "A2_TWO_HISTORIC_SESSIONS",
            "a2_head": A2_HEAD, "a6_base": A6_MAIN,
            "a2_manifest_sha256": A2_MANIFEST_SHA,
            "artifact_zip_sha256": A2_ZIPS,
            "candidate_git_blobs": A6_BLOBS, "totals": totals,
            "primary": dict(collections.Counter(r["classification"] for r in rows
                       if r["role"] == "primary")),
            "alternative": dict(collections.Counter(r["classification"] for r in rows
                           if r["role"] == "alternate")),
            "probes": dict(collections.Counter(r["classification"] for r in rows
                      if r["role"].endswith("_probe"))),
            "rows": rows}


def write_outputs(report, output):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "a7-a2-print-matrix.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    headers = ["session", "case", "tier", "value_requested", "variable", "role",
               "basic_expression", "printer_file", "byte_offset", "byte_count",
               "cpc_hex", "cpc_text", "classification", "candidate_hex"]
    with (out / "a7-a2-print-matrix.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=headers)
        writer.writeheader()
        writer.writerows(report["rows"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("raw", "seal", "comparison", "corpus", "source", "header", "output"):
        parser.add_argument("--"+key, required=True, type=Path)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args(argv)
    try:
        report = audit(args.raw, args.seal, args.comparison, args.corpus,
                       args.source, args.header, args.cc)
        write_outputs(report, args.output)
    except (AuditError, OSError, KeyError, TypeError, IndexError, AttributeError,
            subprocess.SubprocessError) as exc:
        print("A7_FAIL_CLOSED:" + str(exc), file=sys.stderr)
        return 2
    print("A7_A2_CPC_SOURCE_AUTHENTICATED A2_HEAD="+report["a2_head"])
    print("A7_A2_PRINTER_BYTE_EXACT_TOTALS="+json.dumps(report["totals"],sort_keys=True))
    print("A7_A2_PRIMARY="+json.dumps(report["primary"],sort_keys=True))
    print("A7_A2_CLASSIFICATION_NOT_CPC_GENERAL_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
