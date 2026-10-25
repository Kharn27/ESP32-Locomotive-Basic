#!/usr/bin/env python3
"""J0.24 differential harness: local C99 output is never a CPC oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

CLASSIFICATIONS = {"MATCH_EXACT", "MATCH_SEMANTIC", "DIFF", "UNSUPPORTED", "UNVERIFIED", "BLOCKED"}
OPERATIONS = {"LIST", "RUN", "TOKENS"}
NUMERIC_LINE = re.compile(rb"[ \t]*([+-]?[0-9]+)[ \t]*(?:\r\n|\n|\r)?\Z")


class HarnessError(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fixture_bytes(root, item):
    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
        raise HarnessError("reference requires a path")
    rel = Path(item["path"])
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise HarnessError(f"unsafe fixture path: {rel}")
    path = root / rel
    if not path.is_file():
        raise HarnessError(f"missing fixture: {rel}")
    data = path.read_bytes()
    digest = item.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise HarnessError(f"missing SHA-256: {rel}")
    if sha256(data) != digest:
        raise HarnessError(f"SHA-256 mismatch: {rel}")
    return data


def validate_image(data):
    """Validate CPC RAM-style line records, not AMSDOS saved-file bytes."""
    offset, prev = 0, 0
    while True:
        if len(data) - offset < 2:
            raise HarnessError("truncated token image")
        size = int.from_bytes(data[offset:offset + 2], "little")
        if size == 0:
            if offset + 2 != len(data):
                raise HarnessError("non-terminal CPC image sentinel")
            return
        if size < 5 or offset + size > len(data):
            raise HarnessError("invalid CPC record length")
        number = int.from_bytes(data[offset + 2:offset + 4], "little")
        if number <= prev or data[offset + size - 1] != 0:
            raise HarnessError("invalid CPC line number or terminator")
        offset += size
        prev = number


def capture_bytes(root, capture, operation):
    raw = fixture_bytes(root, capture)
    if capture.get("origin") != "cpc6128-rom-basic11":
        raise HarnessError("capture does not declare CPC ROM origin")
    if not capture.get("captured_at") or not capture.get("method"):
        raise HarnessError("capture missing date or acquisition method")
    if operation == "TOKENS":
        if capture.get("media") != "binary":
            raise HarnessError("token evidence must be binary")
        region = capture.get("program_region")
        if not isinstance(region, dict) or not all(k in region for k in
                ("offset", "length", "container", "header_bytes", "memory_layout")):
            raise HarnessError("token capture needs explicit region/layout/header")
        start, count = region["offset"], region["length"]
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(count, int) or isinstance(count, bool):
            raise HarnessError("token region bounds must be integers")
        if start < 0 or count < 2 or start + count > len(raw):
            raise HarnessError("token region lies outside capture")
        if region["memory_layout"] != "contiguous-cpc-ram-records" or \
           region["container"] not in ("raw-ram-export", "amsdos-file") or \
           region["header_bytes"] not in (0, 128):
            raise HarnessError("token region has undocumented layout")
        if region["container"] == "raw-ram-export" and region["header_bytes"] != 0:
            raise HarnessError("RAM export cannot have AMSDOS header")
        if region["container"] == "amsdos-file" and start < region["header_bytes"]:
            raise HarnessError("token slice overlaps AMSDOS header")
        data = raw[start:start + count]
        validate_image(data)
        return data
    if capture.get("media") != "bytes":
        raise HarnessError("console output must be exact captured bytes")
    prefix = bytes.fromhex(capture.get("protocol_prefix_hex", ""))
    suffix = bytes.fromhex(capture.get("protocol_suffix_hex", ""))
    if not raw.startswith(prefix) or (suffix and not raw.endswith(suffix)):
        raise HarnessError("capture protocol wrapper mismatch")
    return raw[len(prefix):len(raw) - len(suffix) if suffix else len(raw)]


def run_command(command, input_bytes):
    try:
        return subprocess.run([str(command)], input=input_bytes, capture_output=True,
                              timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f"local executable error: {exc}") from exc


def local_observation(source, operation, cli, image_cli):
    if operation == "TOKENS":
        result = run_command(image_cli, source)
        if result.returncode == 0:
            validate_image(result.stdout)
        return result
    if operation == "LIST":
        return run_command(cli, source + b"LIST\n:quit\n")
    return run_command(cli, source + b"RUN\n:step 100\n:quit\n")


def checked_local_result(result, case_id, operation):
    # Process-level failure is an infrastructure error even without an oracle.
    # Valid BASIC rejections are CLI protocol diagnostics with exit code zero.
    if result.returncode != 0:
        details = result.stderr[:180].decode("utf-8", errors="replace")
        raise HarnessError(f"{case_id}/{operation}: local process exited {result.returncode}: {details}")


def compare(actual, expected, mode):
    if actual == expected:
        return "MATCH_EXACT"
    if mode == "numeric-integer":
        left, right = NUMERIC_LINE.fullmatch(actual), NUMERIC_LINE.fullmatch(expected)
        if left and right and int(left.group(1)) == int(right.group(1)):
            return "MATCH_SEMANTIC"
    return "DIFF"


def read_manifest(root, path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise HarnessError("unknown manifest schema")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) < 8:
        raise HarnessError("need at least eight planned cases")
    seen = set()
    for case in cases:
        cid = case.get("id")
        if not isinstance(cid, str) or not re.fullmatch("[a-z0-9_-]+", cid) or cid in seen:
            raise HarnessError("invalid or duplicate case id")
        seen.add(cid)
        source = fixture_bytes(root, {"path": case.get("source"), "sha256": case.get("source_sha256")})
        if not source.endswith(b"\n") or b"\x00" in source or b"\r" in source:
            raise HarnessError(f"{cid}: source must be LF-terminated clean BASIC")
        ops = case.get("operations")
        if not isinstance(ops, list) or len(ops) != len(set(ops)) or not set(ops) <= OPERATIONS or not ops:
            raise HarnessError(f"{cid}: invalid operations")
        observations = case.get("observations")
        if not isinstance(observations, dict) or not set(observations) <= set(ops):
            raise HarnessError(f"{cid}: malformed observations")
        if observations:
            oracle = manifest.get("oracle")
            if not isinstance(oracle, dict) or not all(oracle.get(k) for k in
                ("name", "version", "model", "ram_kb", "basic_rom_version", "rom_sha256", "input_method", "capture_method")):
                raise HarnessError("observations require verified oracle identity and ROM hash")
            if not re.fullmatch(r"[0-9a-f]{64}", str(oracle["rom_sha256"])):
                raise HarnessError("oracle ROM SHA-256 invalid")
            if oracle["model"] != "CPC6128" or oracle["basic_rom_version"] != "1.1":
                raise HarnessError("oracle is not CPC 6128 BASIC 1.1")
        for op, obs in observations.items():
            if not isinstance(obs, dict) or obs.get("expected_classification") not in CLASSIFICATIONS:
                raise HarnessError(f"{cid}/{op}: missing expected classification")
            if obs["expected_classification"] in ("BLOCKED", "UNVERIFIED"):
                raise HarnessError(f"{cid}/{op}: observation must be independently verifiable")
            capture_bytes(root, obs, op)
    return manifest


def evaluate(root, manifest, cli, image_cli, ci):
    counts = {key: 0 for key in sorted(CLASSIFICATIONS)}
    proven = 0
    binary_token_cases = 0
    observed_case_ids = set()
    conflicts = []
    for case in manifest["cases"]:
        source = fixture_bytes(root, {"path": case["source"], "sha256": case["source_sha256"]})
        for op in case["operations"]:
            result = local_observation(source, op, cli, image_cli)
            checked_local_result(result, case["id"], op)
            observation = case["observations"].get(op)
            if observation is None:
                status = "BLOCKED" if manifest.get("oracle") is None else "UNVERIFIED"
            else:
                proven += 1
                observed_case_ids.add(case["id"])
                if op == "TOKENS":
                    binary_token_cases += 1
                expected = capture_bytes(root, observation, op)
                if result.returncode != 0 or (op != "TOKENS" and b"[cli:error]" in result.stderr):
                    status = "UNSUPPORTED"
                else:
                    mode = observation.get("comparison", "exact-bytes")
                    if mode not in ("exact-bytes", "numeric-integer"):
                        raise HarnessError("unknown comparison level")
                    status = compare(result.stdout, expected, mode)
                if status != observation["expected_classification"]:
                    conflicts.append(f"{case['id']}/{op}: recorded={observation['expected_classification']} observed={status}")
            counts[status] += 1
            print(f"{case['id']}/{op}: {status} local_rc={result.returncode}")
    print("SUMMARY " + " ".join(f"{name}={count}" for name, count in counts.items()))
    print(f"INDEPENDENT_OBSERVATIONS={proven} VERIFIED_CASES={len(observed_case_ids)} TOKEN_BINARIES={binary_token_cases}")
    for conflict in conflicts:
        print("NEEDS_REVIEW " + conflict, file=sys.stderr)
    if conflicts and ci:
        raise HarnessError("comparison changed without updated historical evidence/review")
    return len(observed_case_ids), binary_token_cases, conflicts


def self_test():
    try:
        checked_local_result(subprocess.CompletedProcess([], 1, b"", b"failed"), "test", "LIST")
    except HarnessError:
        pass
    else:
        raise HarnessError("local process failure was swallowed")
    assert compare(b"5\n", b" 5 \r\n", "numeric-integer") == "MATCH_SEMANTIC"
    assert compare(b"5\n", b" 5 \r\n", "exact-bytes") == "DIFF"
    assert compare(b"5\n", b"5\n", "exact-bytes") == "MATCH_EXACT"
    for image in (b"", b"\x00", b"\x00\x00\x00", b"\x05\x00\x0a\x00\x00\x00"):
        try:
            validate_image(image)
        except HarnessError:
            pass
        else:
            raise HarnessError("malformed record wrongly accepted")
    validate_image(b"\x05\x00\x0a\x00\x00\x00\x00")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cli", required=True, type=Path)
    parser.add_argument("--image-cli", required=True, type=Path)
    parser.add_argument("--ci", action="store_true", help="check hashes/invariants and freeze recorded results")
    parser.add_argument("--require-independent", action="store_true", help="gate for J0.24 acceptance")
    args = parser.parse_args()
    try:
        self_test()
        root = args.manifest.resolve().parent
        manifest = read_manifest(root, args.manifest)
        proven_cases, token_cases, conflicts = evaluate(root, manifest, args.cli.resolve(),
                                                        args.image_cli.resolve(), args.ci)
        if args.require_independent and (proven_cases < 8 or token_cases < 2 or conflicts):
            raise HarnessError("historical gate BLOCKED: need >=8 independent cases and >=2 binary token captures")
    except (HarnessError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"cpc_diff: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
