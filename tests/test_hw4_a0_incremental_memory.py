"""Positive and adversarial negative HW4-A0 fixtures; no Xtensa results are simulated."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "ci"))
import hw4_a0_compare_memory as m
import hw4_a0_provenance as p

A0, BASE, HEAD = m.A0_SHA, "1" * 40, "2" * 40


def section_text(dram=54864, bss=43792, iram=67331, missing=None, duplicate=None):
    entries = {
        ".dram0.data": dram - bss, ".dram0.bss": bss,
        ".iram0.vectors": 1027, ".iram0.text": iram - 1027,
        ".iram0.text_end": 1, ".flash.text": 165370,
        ".flash.rodata": 56228,
    }
    if missing:
        del entries[missing]
    lines = ["firmware.elf  :", "section size addr"]
    lines.extend(f"{k} {v} 1073414144" for k, v in entries.items())
    if duplicate:
        lines.append(f"{duplicate} {entries[duplicate]} 1073414144")
    lines.append(f"Total {sum(entries.values())}")
    return "\n".join(lines) + "\n"


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.files = {}
        for label in ("a0", "base", "head"):
            txt, binfile = self.path / (label + ".txt"), self.path / (label + ".bin")
            txt.write_text(section_text(), encoding="utf-8")
            binfile.write_bytes(b"ESP32" * 10)
            self.files[label] = (txt, binfile)

    def run_cli(self, overrides=None):
        argv = []
        for label in ("a0", "base", "head"):
            txt, binfile = self.files[label]
            argv += ["--" + label + "-size", str(txt), "--" + label + "-bin", str(binfile)]
        argv += ["--a0-sha", A0, "--base-sha", BASE, "--head-sha", HEAD,
                 "--profile", "CONSOLE", "--output-md", str(self.path / "report.md"),
                 "--output-json", str(self.path / "report.json")]
        for opt, val in (overrides or {}).items():
            argv[argv.index(opt) + 1] = val
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools/ci/hw4_a0_compare_memory.py"), *argv],
            text=True, capture_output=True,
        )
        return (proc, json.loads((self.path / "report.json").read_text()),
                (self.path / "report.md").read_text())

    def write_section(self, label="head", **kw):
        self.files[label][0].write_text(section_text(**kw), encoding="utf-8")

    def test_historical_debt_with_identical_incremental(self):
        self.write_section("a0", dram=53728, bss=42656)
        proc, report, md = self.run_cli()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(report["historical_base"]["status"], "HISTORICAL_DEBT")
        self.assertEqual(report["historical_head"]["status"], "HISTORICAL_DEBT")
        self.assertEqual(report["incremental"]["status"], "INCREMENTAL_PASS")
        self.assertIn("+1136", md)
        self.assertNotIn("**HISTORICAL_PASS**", md)

    def test_historical_iram_debt_with_incremental_pass(self):
        self.write_section("a0", iram=67330)
        proc, report, _ = self.run_cli()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(report["historical_head"]["status"], "HISTORICAL_DEBT")
        self.assertEqual(report["historical_head"]["iram"], "FAIL")

    def test_plus_256_dram_allowed(self):
        self.write_section(dram=55120, bss=44048)
        proc, report, _ = self.run_cli()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(report["incremental"]["dram_delta"], 256)

    def test_plus_257_dram_rejected_as_nonzero_exit(self):
        self.write_section(dram=55121, bss=44049)
        proc, report, _ = self.run_cli()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["incremental"]["status"], "INCREMENTAL_FAIL")

    def test_plus_one_iram_rejected_as_nonzero_exit(self):
        self.write_section(iram=67332)
        proc, report, _ = self.run_cli()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["incremental"]["status"], "INCREMENTAL_FAIL")

    def test_minus_one_iram_rejected_as_nonzero_exit(self):
        self.write_section(iram=67330)
        proc, report, _ = self.run_cli()
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["incremental"]["status"], "INCREMENTAL_FAIL")

    def test_three_profiles_positive(self):
        metrics = {**m.read_size(self.files["a0"][0]), **m.read_image(self.files["a0"][1])}
        for profile in m.PROFILES:
            with self.subTest(profile=profile):
                self.assertEqual(
                    m.evaluate(metrics, metrics, metrics, A0, BASE, HEAD, profile)
                    ["incremental"]["status"], "INCREMENTAL_PASS")

    def test_required_sections_missing_and_duplicate(self):
        for missing in m.REQUIRED:
            with self.subTest(missing=missing):
                self.write_section(missing=missing)
                proc, report, _ = self.run_cli()
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(report["status"], "FAIL_CLOSED")
        self.write_section(duplicate=".dram0.bss")
        proc, report, _ = self.run_cli()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("duplicate", report["error"])

    def test_wrong_sha_fails_closed(self):
        for opt, value in (("--a0-sha", "f" * 40), ("--base-sha", "0" * 40),
                           ("--head-sha", BASE), ("--head-sha", "f" * 39),
                           ("--base-sha", "ABC" + "1" * 37)):
            with self.subTest(opt=opt, value=value):
                proc, report, _ = self.run_cli({opt: value})
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(report["status"], "BASELINE_INVALID" if opt == "--a0-sha" else "FAIL_CLOSED")

    def test_invalid_a0_sections_are_baseline_invalid(self):
        self.files["a0"][0].write_text("")
        proc, report, _ = self.run_cli()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "BASELINE_INVALID")

    def test_empty_truncated_report_or_failed_image(self):
        self.files["head"][0].write_text("")
        self.assertEqual(self.run_cli()[0].returncode, 2)
        self.files["head"][0].write_text(section_text().replace("Total ", "Invalid "))
        self.assertEqual(self.run_cli()[0].returncode, 2)
        self.write_section()
        self.files["head"][1].write_bytes(b"")
        self.assertEqual(self.run_cli()[0].returncode, 2)
        self.files["head"][1].unlink()
        self.assertEqual(self.run_cli()[0].returncode, 2)

    def test_stale_live_pr_base_or_head_fails_closed(self):
        payload = {"number": 329, "state": "open",
                   "base": {"ref": "main", "repo": {"full_name": "Kharn27/ESP32-Locomotive-Basic"},
                            "sha": BASE}, "head": {"sha": HEAD}}
        p.validate_pr(payload, "Kharn27/ESP32-Locomotive-Basic", 329, BASE, HEAD)
        for field in ("base", "head", "state", "number"):
            bad = json.loads(json.dumps(payload))
            if field in ("base", "head"):
                bad[field]["sha"] = "f" * 40
            elif field == "state":
                bad["state"] = "closed"
            else:
                bad["number"] = 330
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "FAIL_CLOSED"):
                p.validate_pr(bad, "Kharn27/ESP32-Locomotive-Basic", 329, BASE, HEAD)

    def test_checkout_sha_or_git_object_falsification(self):
        with mock.patch.object(p, "git", side_effect=["f" * 40]):
            with self.assertRaisesRegex(ValueError, "FAIL_CLOSED"):
                p.validate_git("a0", "base", "head", BASE, HEAD)
        with mock.patch.object(p, "git", side_effect=[A0, "commit", BASE, "commit",
                                                       HEAD, "commit", "blob"]):
            with self.assertRaisesRegex(ValueError, "FAIL_CLOSED"):
                p.validate_git("a0", "base", "head", BASE, HEAD)


if __name__ == "__main__":
    unittest.main()
