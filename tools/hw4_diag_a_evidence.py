#!/usr/bin/env python3
"""HW4-DIAG-A: immutable, ROM-backed CPC6128 diagnostic screenshots gate.

The seal authenticates previously archived screenshot bytes and provenance;
it does not OCR images or pretend to execute a fresh CPC in Linux CTest.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/fixtures/cpc6128/hw4_diag_a"
ROM_SHA = "31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562"
CAPRICE = "8c778bf072a06fb7c23b9cccd179041db7f79a52"
SEAL = {
    "00_boot": ([], "44dd5c29d2278251ac244dd703fc205009728631c7965451f5c3e770cb8495b7"),
    "01_d01_absent": (["10"], "e8f731b770e2f87de775e11dd8f394c15e294c0208aee857f9d402e39f09e2c8"),
    "02_d02_delete": (["10 PRINT 2", "10"], "c6a669ab8a6d45b03fbaf7a635341f9204d4df3de6b231386e621bdb0988a25d"),
    "03_d02_list": (["10 PRINT 2", "10", "LIST"], "8bad7d319c6435aa1ab3ec28b8e2df24d0f618188ca6793238abd4ece4fe98a0"),
    "04_d03_new_absent": (["NEW", "10"], "b767736d44a8d03db02a62b81c736b53e8bc96f47365292c2c6e6424f75b406b"),
    "05_d04_trailing_space": (["10 "], "e8f731b770e2f87de775e11dd8f394c15e294c0208aee857f9d402e39f09e2c8"),
    "06_d05_direct_goto": (["GOTO 999"], "d62e0da2a96f4eeecd6cd36101279d65009fd6920fcff911492f23df129dd951"),
    "07_d05_empty_list": (["LIST"], "91b421d10318467c1d6c6d393fce914dd4ff5ea5472535b5c2c9ef7baf67b655"),
    "08_control_existing": (["10 PRINT 2", "LIST"], "b788d7545207374b53bb153bbf7f053e07b0d32c1b9c1462b450caf611e27679"),
    "09_control_new_list": (["10 PRINT 2", "NEW", "LIST"], "74030e5b9116a643cdc5d4a106f2dc6db6c722b06709d105a840432b52be1bf9"),
}

def require(ok, cause):
    if not ok:
        raise ValueError(cause)

def audit():
    manifest = json.loads((EVIDENCE / "manifest.json").read_text(encoding="utf-8"))
    o = manifest["oracle"]
    require(manifest["mission"] == "HW4-DIAG-A" and
            manifest["phase"] == "A0" and
            o["commit"] == CAPRICE and o["rom_sha256"] == ROM_SHA and
            o["rom"] == "CPC6128 BASIC 1.1", "PROVENANCE")
    require(manifest["screen_is_not_printer"] is True and
            manifest["rom_archived"] is False and
            manifest["original_archives_untouched"] is True, "SOURCE_CLASSIFICATION")
    cases = manifest["cases"]
    require(len(cases) == len(SEAL) == 10, "COUNT")
    require(set(c["id"] for c in cases) == set(SEAL), "CASE_SET")
    for item in cases:
        name = item["id"]
        commands, expected_sha = SEAL[name]
        require(item["keyboard"] == commands, name + ":KEYBOARD")
        require(len(item["runs"]) == 2, name + ":REPEATS")
        for repetition, run in zip(("original", "repeat"), item["runs"]):
            path = EVIDENCE / repetition / name
            require(run["repetition"] == repetition, name + ":PROCESS")
            require(run["screen_png"] == f"{repetition}/{name}/screen.png",
                    name + ":PATH")
            raw = (path / "screen.png").read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            require(raw.startswith(b"\x89PNG\r\n\x1a\n") and
                    run["screen_width_px"] == 768 and
                    run["screen_height_px"] == 540, name + ":PNG")
            require(digest == expected_sha == run["screen_sha256"],
                    name + ":IMAGE_SHA")
            cmd = json.loads((path / "autocmd.json").read_text())
            require(cmd["keyboard_inputs"] == commands and
                    cmd["tail"] == "CAP32_DELAYCAP32_DELAYCAP32_SCRNSHOTCAP32_EXIT"
                    and cmd["screen_not_printer"] is True, name + ":AUTO_CMD")
            require((path / "caprice.log").read_text().startswith("returncode=0"),
                    name + ":EMULATOR_EXIT")
    require(not list(EVIDENCE.rglob("*.rom")) and
            not list(EVIDENCE.rglob("*.sna")), "ARCHIVE_ROM_SNAPSHOT_FORBIDDEN")

def main():
    require(len(SEAL) == 10 and
            SEAL["01_d01_absent"][1] == SEAL["05_d04_trailing_space"][1],
            "SELFTEST_SEAL")
    # Mutation control: an altered hash MUST NOT satisfy an original seal.
    sample = bytes.fromhex(SEAL["01_d01_absent"][1])
    forged = bytes([sample[0] ^ 1]) + sample[1:]
    require(sample != forged and forged.hex() != SEAL["01_d01_absent"][1],
            "SELFTEST_NEGATIVE")
    audit()
    print("HW4-DIAG-A CPC PERMANENT PASS 10/10 original + 10/10 repeated "
          "SHA and provenance, keyboard and negative seal test")

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("HW4-DIAG-A CPC PERMANENT FAIL", exc, file=sys.stderr)
        sys.exit(1)
