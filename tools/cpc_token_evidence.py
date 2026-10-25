#!/usr/bin/env python3
"""Verify published J0.24-C3 program-only evidence; never consume a full SNA."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/oracles"))
import token_ram_oracle as oracle

ALLOWED = {"program.bin", "c99.bin", "cap32.cfg",
           "autocmd.json", "caprice.log", "list.png", "comparison.json"}
FORBIDDEN_SUFFIXES = {".sna", ".rom", ".dsk", ".cpr", ".zip", ".img"}
ROM = oracle.ROM_SHA

def require(ok, msg):
    if not ok:
        raise ValueError(msg)

def sha(buf):
    return hashlib.sha256(buf).hexdigest()

def compare(cpc, local):
    n = next((i for i, (x, y) in enumerate(zip(cpc,local)) if x != y),
             min(len(cpc),len(local)))
    same = cpc == local
    return same, None if same else {
        "first_offset": n,
        "cpc_byte": f"{cpc[n]:02x}" if n < len(cpc) else None,
        "c99_byte": f"{local[n]:02x}" if n < len(local) else None,
        "cpc_context_hex": cpc[max(0,n-8):n+9].hex(" "),
        "c99_context_hex": local[max(0,n-8):n+9].hex(" "),
        "hypothesis": "unresolved; no normalization or tokenizer modification",
    }

def validate(base, manifest):
    require(manifest.get("schema_version") == 1, "invalid manifest schema")
    identity = manifest["oracle"]
    require(identity["emulator"] == "Caprice32" and
            identity["commit"] == oracle.PIN and
            identity["rom_sha256"] == ROM and
            identity["model"] == "CPC6128" and
            identity["basic"] == "1.1" and identity["ram_kb"] == 128,
            "unverified oracle identity")
    require(manifest["snapshots_archived"] is False and
            manifest["rom_archived"] is False, "prohibited complete image")
    require(len(manifest["captures"]) == 2 and
            {c["case"] for c in manifest["captures"]} == set(oracle.CASES),
            "exactly two distinct cases required")
    present = {x.relative_to(base).as_posix() for x in base.rglob("*") if x.is_file()}
    expected = {"manifest.json"}
    for name, (source_rel, nums) in oracle.CASES.items():
        cap = next(c for c in manifest["captures"] if c["case"] == name)
        files = cap["files"]
        require(set(files) == ALLOWED, "unexpected case file inventory")
        require(cap["snapshot_taken_before_run"] is True and
                cap["list_requested"] is True, "LIST / before RUN not documented")
        src = (ROOT / "tests/fixtures/cpc6128" / source_rel).read_bytes()
        require(sha(src) == cap["source_sha256"], "source SHA mismatch")
        for key in files:
            f = base / name / key
            require(f.is_file() and not f.is_symlink() and
                    f.resolve().is_relative_to(base.resolve()),
                    "missing/unsafe evidence file")
            require(f.suffix not in FORBIDDEN_SUFFIXES, "forbidden memory export")
            d = f.read_bytes()
            require(len(d) == files[key]["size_bytes"] and
                    sha(d) == files[key]["sha256"], "file digest/size mismatch: "+key)
            expected.add(f"{name}/{key}")
        auto = json.loads((base/name/"autocmd.json").read_text())
        commands = auto["commands"]
        input_lines = src.decode("ascii").splitlines()
        require(commands[:len(input_lines)] == input_lines and
                commands[len(input_lines)] == "LIST" and
                not any(x == "RUN" for x in commands) and
                auto["snapshot_before_run"] is True and
                auto["source_sha256"] == sha(src),
                "input altered, LIST absent or RUN was sent")
        require(commands[-1].endswith("CAP32_EXIT") and
                "CAP32_SNAPSHOT" in commands[-1], "snapshot command missing")
        require("exit code: 0" in (base/name/"caprice.log").read_text(),
                "Caprice32 process did not succeed")
        require((base/name/"list.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"),
                "LIST visual evidence invalid")
        cpc = (base/name/"program.bin").read_bytes()
        local = (base/name/"c99.bin").read_bytes()
        cpc_lines, cpc_records = oracle.records(cpc)
        local_lines, _ = oracle.records(local)
        require(cpc_lines == nums and local_lines == nums, "wrong stored line numbers")
        region = cap["region"]
        require(region["start_address"] == region["base_pointer_value"]+1 and
                region["end_exclusive"] == region["start_address"]+len(cpc) and
                region["length"] == len(cpc) and
                region["snapshot_data_offset"] == 256 and
                region["snapshot_program_offset"] == 256+region["start_address"] and
                region["base_pointer_address"] == 0xAE64 and
                region["end_pointer_address"] == 0xAE66 and
                region["records"] == cpc_records and
                region["sentinel_offset"] == len(cpc)-2 and
                region["terminator_hex"] == "0000", "region bounds inconsistent")
        report = json.loads((base/name/"comparison.json").read_text())
        require(report == cap["comparison"], "comparison report differs from manifest")
        same, diff = compare(cpc,local)
        require(report["classification"] == ("MATCH_EXACT" if same else "DIFF") and
                report["first_difference"] == diff and
                report["cpc_sha256"] == sha(cpc) and
                report["c99_sha256"] == sha(local) and
                report["cpc_size"] == len(cpc) and
                report["c99_size"] == len(local), "comparison is not reproducible")
        print(name, "CPC", sha(cpc), report["classification"], flush=True)
    require(present == expected, "unexpected files, potentially a full SNA/ROM: "+
            str(sorted(present-expected)))
    print("PASS: 2 delimited ROM-backed program images; no complete SNA/ROM files")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    base = args.evidence.resolve()
    manifest = json.loads((base/"manifest.json").read_text())
    validate(base, manifest)
    if args.self_test:
        for field, value in [("snapshots_archived", True), ("rom_archived", True)]:
            malformed = copy.deepcopy(manifest)
            malformed[field] = value
            try:
                validate(base, malformed)
            except ValueError:
                pass
            else:
                raise ValueError("negative test not rejected: "+field)
        altered = copy.deepcopy(manifest)
        altered["captures"][0]["comparison"]["classification"] = "MATCH_EXACT" if (
            altered["captures"][0]["comparison"]["classification"] == "DIFF") else "DIFF"
        try:
            validate(base, altered)
        except ValueError:
            pass
        else:
            raise ValueError("fabricated classification accepted")
        print("PASS: prohibited images and fabricated classification rejected")

if __name__ == "__main__":
    try:
        main()
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print("TOKEN EVIDENCE INVALID:",exc,file=sys.stderr)
        sys.exit(1)
