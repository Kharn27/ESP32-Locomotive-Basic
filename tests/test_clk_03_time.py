"""CLK-03 verifier falsifications. Fixtures are SYNTHETIC, never CPC evidence."""
import configparser
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("clk_03_cpc_time", ROOT / "tools/clk_03_cpc_time.py")
clk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clk)

class FailClosedTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="clk03-fake-negative-only-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.cases = clk.source_cases()
        # Isolated structural fake: never use this as a substitute for the
        # production ROM-backed token_ram_oracle.extract_snapshot().
        def fake_records(data):
            pos = 0
            numbers, records = [], []
            while pos + 2 <= len(data):
                size = int.from_bytes(data[pos:pos+2], "little")
                if size == 0:
                    if pos+2 != len(data):
                        raise ValueError("BAD_FAKE_RECORDS")
                    return numbers, records
                n = int.from_bytes(data[pos+2:pos+4], "little")
                numbers.append(n)
                records.append({"offset": pos, "length": size, "line": n})
                pos += size
            raise ValueError("BAD_FAKE_RECORDS")
        patch = mock.patch.object(clk, "ram_parser", return_value=SimpleNamespace(records=fake_records))
        patch.start()
        self.addCleanup(patch.stop)
        self.counter = 0
        self.manifest = {"schema": 1, "mission": "CLK-03", "status": "ACQUIRED_PENDING_SCREEN_REVIEW",
             "head": "a" * 40, "corpus_sha256": clk.SOURCE_SHA,
             "caprice_commit": clk.CAP_SHA, "rom_sha256": clk.ROM_SHA,
             "image": clk.IMAGE, "rom_archived": False, "snapshot_archived": False,
             "observation_class": "CPC6128_CAPRICE32_ROM_BACKED", "sessions": {}, "files": {}}
        self.build()

    def process(self, folder, cmds, printer=None):
        folder.mkdir(parents=True)
        (folder / "cap32.cfg").write_text("[system]\nmodel=2\nram_size=128\nspeed=4\n"
             "limit_speed=1\nprinter=1\nauto_pause=0\n[sound]\nenabled=0\n"
             "[file]\nprinter_file=" + str(folder / "printer.dat") + "\n")
        (folder / "autocmd.json").write_bytes(clk.canonical({"commands": cmds, "argv": []}))
        (folder / "caprice.log").write_text("returncode=0\n")
        # Deliberately synthetic PNG header + padding; never archived or committed.
        png = bytearray(b"\x89PNG\r\n\x1a\n" + b"\0" * 2040)
        png[16:20] = (768).to_bytes(4, "big")
        png[20:24] = (540).to_bytes(4, "big")
        (folder / "screen.png").write_bytes(png)
        if printer is not None:
            (folder / "printer.dat").write_bytes(printer)
        self.counter += 1
        return {"started_utc": (datetime(2026, 11, 6, tzinfo=timezone.utc) +
                        timedelta(seconds=self.counter)).isoformat(),
                "ended_utc": "fake-test-only", "wall_seconds": 1.0,
                "returncode": 0}

    def build(self):
        for session in clk.SESSIONS:
            prefix = self.path / session
            boot = self.process(prefix / "boot", ["CAP32_SCRNSHOT"])
            short = self.process(prefix / "gate_short", ["PRINT #8,TIME"], b"1\r\n300\r\n")
            long = self.process(prefix / "gate_long", ["PRINT #8,TIME"], b"2\r\n1505\r\n")
            short["ticks"] = [1,300]
            short["delta_ticks"] = 299
            short["wall_seconds"] = 1.0
            long["ticks"] = [2,1505]
            long["delta_ticks"] = 1503
            long["wall_seconds"] = 5.0
            gate = {"short":short,"long":long,"delta_ticks":1204,
                    "delta_wall_seconds":4.0,"ticks_per_wall_second":301.0}
            captures = {}
            for c in self.cases:
                name = c["id"]
                p = prefix / name
                kind = c["kind"]
                if kind == "program":
                    listcmd = ["MODE 1", "NEW", *c["lines"], "LIST",
                               "CAP32_SNAPSHOT", "LIST #8"]
                    l = self.process(p / "list", listcmd, b"LIST RAW\r\n")
                    output = b"1\r\n" * c["printer_numeric_count"]
                    run = self.process(p / "run", [*c["lines"], "RUN"], output)
                    recs = []
                    for line in c["lines"]:
                        n = int(line.split(" ", 1)[0])
                        body = b"\xff\x46" if "TIME" in line else b"\x97"
                        raw = (5 + len(body)).to_bytes(2, "little") + n.to_bytes(2,"little") + body + b"\0"
                        recs.append(raw)
                    raw = b"".join(recs) + b"\0\0"
                    (p / "program.bin").write_bytes(raw)
                    captures[name] = {"kind": kind, "list": l, "run": run,
                         "line_numbers": [int(s.split(" ",1)[0]) for s in c["lines"]],
                         "program_sha256": clk.sha(raw),
                         "list_hex": (b"LIST RAW\r\n").hex(),
                         "numbers": [1] * c["printer_numeric_count"]}
                else:
                    printer = (b"1\r\n" * c["printer_numeric_count"] if kind=="direct" else None)
                    meta = self.process(p / "direct", [*c["commands"], "CAP32_EXIT"], printer)
                    captures[name] = {"kind": kind, "direct": meta,
                         "numbers": [1] * c["printer_numeric_count"],
                         "diagnostic_text": "UNVERIFIED_SCREEN_INSPECTION" if kind.endswith("diagnostic") else None}
            self.manifest["sessions"][session] = {"boot": boot, "gate": gate, "cases":captures}
        self.reseal()

    def reseal(self):
        self.manifest["files"] = clk.inventory(self.path)
        self.manifest["files"].pop("manifest.json",None)
        (self.path / "manifest.json").write_bytes(clk.canonical(self.manifest))
        self.seal = clk.sha(clk.read(self.path / "manifest.json"))

    def verify(self):
        return clk.check_capture(self.path, self.manifest, "a" * 40, self.seal)

    def fail(self, fragment):
        with self.assertRaisesRegex(clk.OracleError, fragment):
            self.verify()

    def test_00_synthetic_structure_only(self):
        self.assertTrue(self.verify())  # Synthetic structure. Not a CPC capture.

    def test_01_missing_file(self):
        (self.path / "original/D01_DIRECT/direct/screen.png").unlink()
        self.fail("FILE_MISSING_OR_MODIFIED")

    def test_02_tampered_file(self):
        with (self.path / "original/D01_DIRECT/direct/printer.dat").open("ab") as out:
            out.write(b"extra")
        self.fail("FILE_MISSING_OR_MODIFIED")

    def test_03_wrong_sha(self):
        self.seal = "f" * 64
        self.fail("EXTERNAL_SEAL_REQUIRED")

    def test_04_wrong_head(self):
        self.manifest["head"] = "b" * 40
        self.reseal()
        self.fail("HEAD_SEAL_MISMATCH")

    def test_05_fake_session_same_start(self):
        self.manifest["sessions"]["repeat"]["boot"]["started_utc"] = (
            self.manifest["sessions"]["original"]["boot"]["started_utc"])
        self.reseal()
        self.fail("FAKE_SESSION_SAME_START")

    def test_06_bad_clock(self):
        self.manifest["sessions"]["original"]["gate"]["ticks_per_wall_second"] = 4.0
        self.reseal()
        self.fail("EMULATOR_SPEED_UNVERIFIED")

    def test_07_bad_config(self):
        p = self.path / "original/D01_DIRECT/direct/cap32.cfg"
        p.write_text(p.read_text().replace("speed=4", "speed=32"))
        self.reseal()
        self.fail("CFG_BAD_speed")

    def test_08_screen_printer_divergence(self):
        p = self.path / "repeat/P02_RAPID/run/printer.dat"
        p.write_bytes(b"1 2\r\n")
        self.reseal()
        self.fail("TIME_AMBIGUOUS")

    def test_09_missing_session(self):
        self.manifest["sessions"].pop("repeat")
        self.reseal()
        self.fail("SESSIONS_MISSING")

    def test_10_wrong_rom(self):
        self.manifest["rom_sha256"] = "0" * 64
        self.reseal()
        self.fail("PROVENANCE_UNVERIFIED")

    def test_11_wrong_source(self):
        self.manifest["corpus_sha256"] = "f" * 64
        self.reseal()
        self.fail("PROVENANCE_UNVERIFIED")

    def test_12_wrong_argv(self):
        p = self.path / "original/P02_RAPID/list/autocmd.json"
        auto = json.loads(p.read_text())
        auto["commands"] = ["RUN"]
        p.write_bytes(clk.canonical(auto))
        self.reseal()
        self.fail("LIST_OR_SNAPSHOT_NOT_CAPTURED")

if __name__ == "__main__":
    unittest.main()
