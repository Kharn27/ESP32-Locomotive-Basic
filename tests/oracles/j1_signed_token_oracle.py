#!/usr/bin/env python3
"""J1.1 independent pre-RUN CPC6128/BASIC 1.1 negative INTEGER token acquisition.

Reuse the already reviewed J0.24 snapshot parser and acquisition machinery.
Only delimited BASIC program records are retained; full snapshots and ROM
images never leave their temporary directories. Historical fixtures untouched.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import token_ram_oracle as oracle

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    "minus_one": ("tests/oracles/inputs/j027_b1/minus_one.bas", [10, 20, 30]),
    "minus_twelve": ("tests/oracles/inputs/j027_b1/minus_twelve.bas", [10, 20, 30]),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caprice", type=Path, required=True)
    parser.add_argument("--image-cli", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cap, image_cli, out = (args.caprice.resolve(),
                           args.image_cli.resolve(), args.output.resolve())
    oracle.self_test()
    oracle.check(image_cli.is_file(), "missing native program-image CLI")
    oracle.check(subprocess.check_output(
        ["git", "-C", str(cap), "rev-parse", "HEAD"], text=True
    ).strip() == oracle.PIN, "Caprice32 revision differs from pinned J0 oracle")
    romdir = cap / "rom"
    oracle.check(oracle.sha((romdir / "cpc6128.rom").read_bytes()) == oracle.ROM_SHA,
                 "CPC6128 ROM sha256 differs from approved oracle")
    version = subprocess.check_output([str(cap / "cap32"), "--version"],
                                      cwd=cap, text=True).strip()
    out.mkdir(parents=True, exist_ok=True)
    oracle.check(not list(out.iterdir()), "refuse nonempty acquisition directory")
    captures = []
    for name, (path, numbers) in CASES.items():
        source = (ROOT / path).read_bytes()
        oracle.check(source == (
            f"10 B%={'-1' if name == 'minus_one' else '-12'}\n"
            "20 PRINT B%\n30 END\n").encode("ascii"),
            name + ": original B1 source changed")
        captures.append(oracle.acquire(cap, romdir, name, source,
                                       numbers, image_cli, out))
    manifest = {
        "schema_version": 1,
        "phase": "J1.1-original-CPC-token-evidence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "oracle": {"emulator": "Caprice32", "commit": oracle.PIN,
                   "version_output": version, "rom_sha256": oracle.ROM_SHA,
                   "model": "CPC6128", "basic": "1.1", "ram_kb": 128},
        "github_run_id": __import__("os").environ.get("GITHUB_RUN_ID"),
        "github_sha": __import__("os").environ.get("GITHUB_SHA"),
        "snapshots_archived": False,
        "rom_archived": False,
        "captures": captures
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("J1.1 CPC token acquisition COMPLETE: 2 fresh independent cases",
          flush=True)


if __name__ == "__main__":
    main()
