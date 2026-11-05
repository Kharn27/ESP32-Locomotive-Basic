#!/usr/bin/env python3
"""CLK-01 host CLI execution witness; not a CPC oracle and not a CYD run."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "tests/fixtures/cpc6128/clk_01_speed"
# Maximum per test is enough for END inside the LAST :step batch, never another step.
BATCHES = {"01_for": 13, "02_integer": 16, "03_gosub": 13,
           "04_print_fixed": 1, "05_print_scroll": 1}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cli", type=Path, required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    m = json.loads((BASE / "manifest.json").read_text())
    if set(BATCHES) != {p["id"] for p in m["programs"]}:
        raise RuntimeError("CORPUS_DRIFT")
    results = []
    for case in m["programs"]:
        source = (BASE / case["file"]).read_bytes()
        if hashlib.sha256(source).hexdigest() != case["sha256"]:
            raise RuntimeError("SOURCE_SHA_" + case["id"])
        input_bytes = (b"NEW\n" + source + b"RUN\n" +
                       b":step 100\n" * BATCHES[case["id"]] + b":quit\n")
        r = subprocess.run([str(args.cli.resolve())], input=input_bytes,
                           capture_output=True, timeout=50, check=False)
        stderr = r.stderr.decode("utf-8", "replace")
        output = r.stdout.decode("utf-8", "replace")
        actual = [x.strip() for x in output.splitlines()]
        if r.returncode != 0 or "[cli:error]" in stderr or \
           stderr.count("[cli] END\n") != 1 or \
           actual != case["expected_screen_lines"]:
            raise RuntimeError("HOST_RUNTIME_" + case["id"] +
                               " exit=" + str(r.returncode) +
                               " stdout=" + repr(output[-500:]) +
                               " stderr=" + repr(stderr[-800:]))
        results.append({"scenario": case["id"], "status": "HOST_VERIFIED",
                        "expected_lines": len(actual),
                        "stdout_sha256": hashlib.sha256(r.stdout).hexdigest()})
        print("CLK-01 HOST_VERIFIED", case["id"], len(actual), "screen lines")
    if args.output:
        args.output.write_text(json.dumps(results, indent=2) + "\n")
    print("CLK-01 HOST_VERIFIED 5/5 on Linux CLI; CYD ON_DEVICE_UNVERIFIED")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as err:
        print("CLK-01 NATIVE FAIL:", err, file=sys.stderr)
        sys.exit(2)
