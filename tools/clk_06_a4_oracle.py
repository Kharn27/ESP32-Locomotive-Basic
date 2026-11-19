#!/usr/bin/env python3
"""CLK-06-A4: independent CPC6128 EVERY channel-2/3 capture and sealed replay.

Acquisition is never an implementation of the CPC timer. Evidence comes only
from real Caprice32 processes with pinned ROM and original RAM snapshots.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/cpc6128/clk_06_a4_ch23/corpus.json"
CORPUS_SHA = "5ceeea333137910818326f79a7e37ff89f911c0af8a0df7a9e7f5ed2a00404e5"
CAP_SHA = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
CAP_BINARY_SHA = "5170b3fc68ab116e7698e6e68a742e324d0e9dbfd87eeb7b2090e13c639f73eb"
ROM_SHA = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
IMAGE = ("ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:"
         "7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c")
SESSIONS = ("original", "repeat")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
CASE_ID = re.compile(r"S0[1-4]_[A-Z0-9_]+\Z")
PROCESS_PARTS = ("list", "run")
FORBIDDEN_SUFFIXES = (".sna", ".rom", ".dsk", ".zip")


class OracleError(RuntimeError):
    pass


def need(value, reason):
    if not value:
        raise OracleError(reason)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> bytes:
    return path.read_bytes()


def canonical(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":")) + "\n").encode("ascii")


def clk03():
    # Read-only reuse. Never invoke its CLOCK-03 acquisition, corpus or seals.
    sys.path.insert(0, str(ROOT / "tools"))
    import clk_03_cpc_time
    return clk_03_cpc_time


def source_cases() -> list[dict]:
    raw = read(CORPUS)
    need(digest(raw) == CORPUS_SHA, "CORPUS_SHA_MISMATCH")
    data = json.loads(raw)
    need(data.get("schema") == 1 and data.get("mission") == "CLK-06-A4"
         and data.get("status") == "INPUT_ONLY_NOT_AN_ORACLE", "CORPUS_SCHEMA")
    cases = data.get("cases")
    need(isinstance(cases, list) and len(cases) == 4, "FOUR_CASES_REQUIRED")
    ids = []
    unique_sources = set()
    for case in cases:
        need(set(case) == {"id", "question", "run_delays", "lines"}, "CORPUS_FIELDS")
        ident, question, delays, lines = (case[k] for k in
                                           ("id", "question", "run_delays", "lines"))
        need(isinstance(ident, str) and CASE_ID.fullmatch(ident), "CASE_ID_BAD")
        need(isinstance(question, str) and bool(question.strip()), "CASE_QUESTION")
        need(type(delays) is int and 2 <= delays <= 20, "CAPTURE_DELAY_BOUNDS")
        need(isinstance(lines, list) and 2 <= len(lines) <= 22,
             "PROGRAM_LENGTH_BOUNDS")
        need(all(isinstance(line, str) and line.isascii()
                 and 0 < len(line) <= 92 and "\n" not in line and "\r" not in line
                 for line in lines), "PROGRAM_ASCII")
        numbers = [int(line.split(" ", 1)[0]) for line in lines]
        need(all(re.fullmatch(r"[1-9][0-9]* .+", line) for line in lines)
             and numbers == sorted(set(numbers)) and max(numbers) <= 65535,
             "PROGRAM_LINE_NUMBERS")
        need(lines[-1].endswith(" RETURN") or lines[-1].endswith(" END"),
             "FINITE_PROGRAM_END_REQUIRED")
        need(any("EVERY " in line for line in lines), "TIMER_PROBE_MISSING")
        need("FOR I%=" in "\n".join(lines), "BOUNDED_PROBE_EXPECTED")
        ids.append(ident)
        unique_sources.add(digest("\n".join(lines).encode("ascii")))
    for case in cases:
        source = CORPUS.parent / "sources" / (case["id"] + ".bas")
        need(source.is_file() and read(source) == source_bytes(case),
             "BASIC_SOURCE_FILE_DRIFT_" + case["id"])
    need(len(set(ids)) == len(ids) == len(unique_sources) == 4,
         "DUPLICATE_CASE_OR_PROGRAM")
    need(ids == ["S01_CH2_RECUR_RETURN", "S02_CH3_RECUR_RETURN",
                 "S03_CH23_COEXIST", "S04_CANCEL_CH3_KEEP_CH2"], "SCENARIO_MATRIX_DRIFT")
    return cases


def source_bytes(case: dict) -> bytes:
    return ("\n".join(case["lines"]) + "\n").encode("ascii")


def command_list(case: dict) -> list[str]:
    return ["MODE 1", "NEW", *case["lines"], "LIST",
            "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT",
            "LIST #8", "CAP32_DELAY CAP32_EXIT"]


def command_run(case: dict) -> list[str]:
    return ["MODE 1", "NEW", *case["lines"], "RUN",
            " ".join(["CAP32_DELAY"] * case["run_delays"])
            + " CAP32_SCRNSHOT CAP32_EXIT"]


def png_checked(path: Path) -> dict:
    raw = read(path)
    need(len(raw) > 1024 and raw.startswith(b"\x89PNG\r\n\x1a\n"), "PNG_MISSING_OR_SHORT")
    offset = 8
    width = height = None
    compressed = []
    kinds = []
    while offset < len(raw):
        need(offset + 12 <= len(raw), "PNG_TRUNCATED_CHUNK")
        length = int.from_bytes(raw[offset:offset+4], "big")
        kind = raw[offset+4:offset+8]
        end = offset + 12 + length
        need(length <= 1 << 25 and end <= len(raw), "PNG_BOUNDS")
        payload = raw[offset+8:end-4]
        declared = int.from_bytes(raw[end-4:end], "big")
        need(zlib.crc32(kind + payload) & 0xffffffff == declared, "PNG_CRC_MISMATCH")
        kinds.append(kind)
        if kind == b"IHDR":
            need(width is None and length == 13, "PNG_DUPLICATE_IHDR")
            width = int.from_bytes(payload[:4], "big")
            height = int.from_bytes(payload[4:8], "big")
        if kind == b"IDAT":
            compressed.append(payload)
        offset = end
        if kind == b"IEND":
            need(length == 0 and offset == len(raw), "PNG_TRAILING_DATA")
            break
    need(kinds and kinds[0] == b"IHDR" and kinds[-1] == b"IEND"
         and b"IDAT" in kinds and width is not None and
         width >= 320 and height >= 200, "PNG_INCOMPLETE_FRAME")
    try:
        expanded = zlib.decompress(b"".join(compressed))
    except zlib.error as exc:
        raise OracleError("PNG_IDAT_INVALID") from exc
    need(len(expanded) >= height, "PNG_IDAT_TOO_SHORT")
    return {"width": width, "height": height, "sha256": digest(raw),
            "file_bytes": len(raw), "decompressed_bytes": len(expanded)}


def list_printer_checked(raw: bytes, case: dict) -> list[int]:
    need(bool(raw), "LIST_PRINTER_EMPTY")
    # The actual LIST output, not a Python reconstruction, must enumerate
    # the original BASIC line numbers in order. No invented spacing/format.
    lines = raw.decode("latin-1").replace("\r", "").split("\n")
    numbered = []
    for row in lines:
        match = re.match(r"\s*([0-9]{1,5})\s+", row)
        if match:
            numbered.append(int(match.group(1)))
    expected = [int(line.split(" ", 1)[0]) for line in case["lines"]]
    need(numbered == expected, "CPC_LIST_LINES_MISMATCH")
    return numbered


def ram_checked(image: bytes, case: dict) -> dict:
    oracle = clk03().ram_parser()
    numbers, records = oracle.records(image)
    expected = [int(line.split(" ", 1)[0]) for line in case["lines"]]
    need(numbers == expected and len(records) == len(expected), "RAM_LINES_MISMATCH")
    # Token IDs are from the supplied CPC BASIC ROM listing, not a native
    # tokenizer. Only look for tokens in their corresponding acquired RAM line.
    signatures = (("EVERY ", b"\x9d"), ("AFTER ", b"\x80"), ("REMAIN(2)", b"\xff\x13"), ("REMAIN(3)", b"\xff\x13"),
                  ("GOSUB ", b"\x9f"), ("RETURN", b"\xc9"))
    seen = set()
    for source, rec in zip(case["lines"], records):
        payload = image[rec["offset"]+4:rec["offset"]+rec["length"]-1]
        for spelling, token in signatures:
            if spelling in source:
                # Token bytes are actual RAM snapshot contents, never created
                # by the oracle tool to stand in for a missing capture.
                need(token in payload, "CPC_RAM_TOKEN_MISSING_" + spelling.strip())
                seen.add(spelling)
    return {"line_numbers": numbers, "tokens_seen": sorted(seen),
            "sha256": digest(image)}


def inventory(folder: Path) -> dict:
    files = {}
    for item in sorted(folder.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(folder).as_posix()
        need(item.suffix.lower() not in FORBIDDEN_SUFFIXES, "FORBIDDEN_SNAPSHOT_ARCHIVE")
        need(not item.is_symlink() and ".." not in item.parts,
             "UNSAFE_EVIDENCE_PATH")
        files[rel] = {"bytes": item.stat().st_size, "sha256": digest(read(item))}
    return files


def freshness_metadata(meta: dict):
    need(meta.get("returncode") == 0 and type(meta.get("wall_seconds")) in (int, float)
         and meta["wall_seconds"] > 0, "EMULATOR_PROCESS_UNVERIFIED")
    for key in ("started_utc", "ended_utc"):
        need(isinstance(meta.get(key), str) and "+00:00" in meta[key],
             "EMULATOR_PROCESS_TIMESTAMPS")


def acquire(cap: Path, out: Path, head: str) -> None:
    cases = source_cases()
    need(bool(SHA40.fullmatch(head or "")), "INVALID_HEAD")
    actual = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                     text=True).strip()
    need(actual == head, "HEAD_NOT_CHECKED_OUT")
    need(not out.exists(), "NO_OVERWRITE")
    cap = cap.resolve()
    require_commit = subprocess.check_output(["git", "-C", str(cap), "rev-parse", "HEAD"],
                                             text=True).strip()
    need(require_commit == CAP_SHA, "CAPRICE_COMMIT_MISMATCH")
    need(digest(read(cap / "rom/cpc6128.rom")) == ROM_SHA,
         "ROM_SHA_MISMATCH")
    need((cap / "rom/amsdos.rom").is_file(), "AMSDOS_ROM_MISSING")
    executable = cap / "cap32"
    need(executable.is_file(), "CAPRICE_EXECUTABLE_MISSING")
    need(digest(read(executable)) == CAP_BINARY_SHA, "CAPRICE_BINARY_SHA_MISMATCH")
    version = subprocess.check_output([str(executable), "--version"],
                                      text=True).strip()
    need(version.startswith("Caprice32 v4.6.0-" + CAP_SHA), "CAPRICE_VERSION_MISMATCH")
    helper = clk03()
    out.mkdir(parents=True)
    manifest = {"schema": 1, "mission": "CLK-06-A4", "status": "ACQUISITION_PARTIAL",
                "head": head, "corpus_sha256": CORPUS_SHA, "caprice_commit": CAP_SHA,
                "rom_sha256": ROM_SHA, "container_image": IMAGE,
                "caprice_binary_sha256": digest(read(executable)),
                "caprice_version": version,
                "observation_class": "ROM_BACKED_CPC6128_RAW_PENDING_SCREEN_REVIEW",
                "rom_archived": False, "sna_archived": False,
                "session_names": list(SESSIONS), "sessions": {},
                "run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"), "files": {}}
    try:
        with tempfile.TemporaryDirectory(prefix="clk06-sna-") as temporary:
            snaps = Path(temporary)
            for session in SESSIONS:
                result = {"cases": {}}
                # Every original/repeat process starts a fresh CPC boot.
                result["boot"] = helper.run(cap, out / session / "boot",
                    ["CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT"], snaps)
                result["gate"] = helper.speed_gate(cap, out, session, snaps)
                for case in cases:
                    label = case["id"]
                    directory = out / session / label
                    before = set(snaps.glob("*.sna"))
                    listed = helper.run(cap, directory / "list", command_list(case), snaps)
                    created = set(snaps.glob("*.sna")) - before
                    need(len(created) == 1, "CPC_LIST_SNAPSHOT_MISSING")
                    try:
                        expected = [int(row.split(" ", 1)[0]) for row in case["lines"]]
                        program, region = helper.ram_parser().extract_snapshot(
                            read(next(iter(created))), expected)
                    finally:
                        for item in created:
                            item.unlink()
                    (directory / "program.bin").write_bytes(program)
                    ram = ram_checked(program, case)
                    listing = list_printer_checked(read(directory / "list/printer.dat"), case)
                    png_checked(directory / "list/screen.png")
                    executed = helper.run(cap, directory / "run", command_run(case), snaps)
                    png_checked(directory / "run/screen.png")
                    printer = directory / "run/printer.dat"
                    need(printer.is_file() and printer.stat().st_size > 0,
                         "CPC_RUN_PRINTER_MISSING")
                    # Printed bytes (including any CPC numeric representation)
                    # are raw observations. No expected outcome is built in.
                    result["cases"][label] = {
                        "question": case["question"], "source_sha256": digest(source_bytes(case)),
                        "list": listed, "run": executed, "ram": ram,
                        "region": region, "list_line_numbers": listing,
                        "run_printer_sha256": digest(read(printer)),
                        "screen_review": "UNVERIFIED",
                        "observation": "RAW_ACQUIRED_UNINTERPRETED"}
                manifest["sessions"][session] = result
        manifest["status"] = "ACQUIRED_PENDING_SCREEN_REVIEW"
    finally:
        manifest["files"] = inventory(out)
        (out / "manifest.json").write_bytes(canonical(manifest))
    need(manifest["status"] == "ACQUIRED_PENDING_SCREEN_REVIEW", "ACQUISITION_PARTIAL")
    print("CLK-06-A4 ROM_BACKED_RAW_CAPTURED; human screen review pending; HEAD=", head,
          "SHA256(manifest.json)=", digest(read(out / "manifest.json")), flush=True)


def verify(folder: Path, head: str, seal: str) -> bool:
    cases = source_cases()
    need(bool(SHA40.fullmatch(head or "")), "EXPECTED_HEAD_INVALID")
    need(bool(SHA64.fullmatch(seal or "")), "EXTERNAL_MANIFEST_SEAL_REQUIRED")
    raw_manifest = read(folder / "manifest.json")
    need(digest(raw_manifest) == seal, "EXTERNAL_MANIFEST_SEAL_MISMATCH")
    m = json.loads(raw_manifest)
    need(m.get("schema") == 1 and m.get("mission") == "CLK-06-A4" and
         m.get("status") == "ACQUIRED_PENDING_SCREEN_REVIEW" and
         m.get("head") == head, "MANIFEST_OR_HEAD_MISMATCH")
    need(m.get("corpus_sha256") == CORPUS_SHA and
         m.get("caprice_commit") == CAP_SHA and m.get("rom_sha256") == ROM_SHA
         and m.get("container_image") == IMAGE and
         m.get("caprice_binary_sha256") == CAP_BINARY_SHA and
         isinstance(m.get("caprice_version"), str) and
         m["caprice_version"].startswith("Caprice32 v4.6.0-" + CAP_SHA) and
         m.get("rom_archived") is False and m.get("sna_archived") is False and
         m.get("observation_class") == "ROM_BACKED_CPC6128_RAW_PENDING_SCREEN_REVIEW",
         "PROVENANCE_UNVERIFIED")
    need(m.get("session_names") == list(SESSIONS) and
         set(m.get("sessions", {})) == set(SESSIONS), "TWO_FRESH_SESSIONS_REQUIRED")
    current = inventory(folder)
    current.pop("manifest.json", None)
    need(m.get("files") == current and bool(current), "FILE_MISSING_MODIFIED_OR_INJECTED")
    need(not any(name.endswith((".rom", ".sna")) for name in current),
         "ROM_OR_SNAPSHOT_EXPORTED")
    helper = clk03()
    stamps = set()
    for session in SESSIONS:
        info = m["sessions"][session]
        need(set(info["cases"]) == {case["id"] for case in cases},
             "CASE_COUNT_MISMATCH")
        gate = info["gate"]
        need(255 <= gate["ticks_per_wall_second"] <= 345 and
             gate["delta_wall_seconds"] > 0.5 and gate["delta_ticks"] > 100,
             "CPC_SPEED_UNVERIFIED")
        for part, meta in (("boot", info["boot"]),
                           ("gate_short", gate["short"]),
                           ("gate_long", gate["long"])):
            base = folder / session / part
            freshness_metadata(meta)
            need(meta["started_utc"] not in stamps, "PROCESS_NOT_INDEPENDENT")
            stamps.add(meta["started_utc"])
            png_checked(base / "screen.png")
            helper.cfg_validate(base / "cap32.cfg")
            need(b"returncode=0\n" in read(base / "caprice.log"), "CAPRICE_PROCESS_LOG")
            if part.startswith("gate"):
                ints = helper.parse_numbers(read(base / "printer.dat"), 2)
                need(ints == meta["ticks"] and ints[1]-ints[0] == meta["delta_ticks"],
                     "SPEED_RAW_PRINTER_TICKS_MISMATCH")
        for case in cases:
            ident = case["id"]
            entry = info["cases"][ident]
            expected = [int(row.split(" ", 1)[0]) for row in case["lines"]]
            need(entry["question"] == case["question"] and
                 entry["source_sha256"] == digest(source_bytes(case)) and
                 entry["screen_review"] == "UNVERIFIED" and
                 entry["observation"] == "RAW_ACQUIRED_UNINTERPRETED",
                 "CASE_SOURCE_OR_CLAIM_TAMPERED")
            for part, commands in (("list", command_list(case)),
                                   ("run", command_run(case))):
                base = folder / session / ident / part
                meta = entry[part]
                freshness_metadata(meta)
                need(meta["started_utc"] not in stamps, "PROCESS_NOT_INDEPENDENT")
                stamps.add(meta["started_utc"])
                need(b"returncode=0\n" in read(base / "caprice.log"),
                     "CAPRICE_PROCESS_LOG")
                helper.cfg_validate(base / "cap32.cfg")
                png_checked(base / "screen.png")
                issued = json.loads(read(base / "autocmd.json"))
                need(issued.get("commands") == commands, "CPC_AUTOCMD_DRIFT")
                argv = issued.get("argv", [])
                need(isinstance(argv, list) and len(argv) == 5+2*len(commands),
                     "CPC_AUTOCMD_ARGV_BAD")
                need(argv[0] == "xvfb-run" and argv[1] == "-a"
                     and argv[3] == "-c", "CPC_AUTOCMD_PROGRAM_BAD")
                need([argv[j] for j in range(5, len(argv), 2)] == ["-a"]*len(commands),
                     "CPC_AUTOCMD_FLAGS_BAD")
                need([argv[j] for j in range(6, len(argv), 2)] == [
                    cmd.replace("CAP32_SNAPSHOT", "\x0c\x0d") for cmd in commands],
                     "CPC_AUTOCMD_INJECTION")
            directory = folder / session / ident
            ram = read(directory / "program.bin")
            facts = ram_checked(ram, case)
            need(entry["ram"] == facts and entry["ram"]["line_numbers"] == expected,
                 "CPC_RAM_REPLAY_DIFFERENCE")
            need(entry["list_line_numbers"] == list_printer_checked(
                     read(directory / "list/printer.dat"), case),
                 "CPC_LIST_REPLAY_DIFFERENCE")
            need(entry["run_printer_sha256"] == digest(read(directory / "run/printer.dat")),
                 "CPC_RUN_PRINTER_SHA_MISMATCH")
    return True


def self_test():
    cases = source_cases()
    need(len(cases) == 4 and sum("EVERY " in " ".join(c["lines"]) for c in cases) == 4,
         "SOURCE_SELF_TEST")
    need(len({digest(source_bytes(c)) for c in cases}) == 4, "SOURCE_DUPLICATE")
    try:
        list_printer_checked(b"10 PRINT #8,\"TEST\"\r\n", cases[0])
    except OracleError:
        pass
    else:
        raise OracleError("FALSE_ACCEPT_LIST")
    print("CLK-06-A4 SOURCE_SELF_TEST PASS; CPC ACQUISITION NOT EXECUTED")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    op = p.add_mutually_exclusive_group(required=True)
    op.add_argument("--self-test", action="store_true")
    op.add_argument("--check-sources", action="store_true")
    op.add_argument("--acquire", action="store_true")
    op.add_argument("--verify", type=Path)
    p.add_argument("--caprice", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--head")
    p.add_argument("--seal", help="external SHA-256 from acquisition job, not manifest")
    args = p.parse_args(argv)
    try:
        if args.self_test:
            self_test()
        elif args.check_sources:
            cases = source_cases()
            print("CLK-06-A4 CORPUS_SHA", CORPUS_SHA, "SCENARIOS", len(cases),
                  "NO_OBSERVATIONS_CLAIMED")
        elif args.acquire:
            need(args.caprice and args.output and args.head, "ACQUIRE_ARGS_REQUIRED")
            acquire(args.caprice, args.output, args.head)
        else:
            need(args.head and args.seal, "VERIFY_HEAD_AND_SEAL_REQUIRED")
            verify(args.verify, args.head, args.seal)
            print("CLK-06-A4 RAW_REPLAY_PASS; SCREENS_AND_SEMANTICS_PENDING_INSPECTION")
    except (OracleError, ValueError, OSError, subprocess.SubprocessError,
            json.JSONDecodeError) as exc:
        print("CLK-06-A4 UNVERIFIED:", str(exc), file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
