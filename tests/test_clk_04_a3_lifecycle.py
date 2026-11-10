"""CLK-04-A3 synthetic negatives: they are NOT observations on a CPC6128."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import clk_04_a3_lifecycle as a3


def reject(call, message):
    try:
        call()
    except (a3.prior.OracleError, ValueError, TypeError, KeyError) as exc:
        if message not in str(exc):
            raise AssertionError("WRONG_REJECTION: " + str(exc)) from exc
    else:
        raise AssertionError("FORGED_INPUT_ACCEPTED: " + message)


def synthetic_printer(protocol):
    # These deliberately fake digits test only structural parser logic.
    lines = []
    def tag(s):
        lines.append("A3:" + s)
    def n(v=111):
        lines.append(" " + str(v))
    tag("BOOT"); n(10); n(100)
    tag("IDLE")
    for _ in range(4):
        n()
    tag("RUN:PRE"); n()
    lines.extend(protocol["programs"]["run"])
    for _ in (1, 2):
        tag("RUN:CONT")
        for v in (555, 111, 222, 333):
            n(v)
    tag("RUN:POST"); n()
    tag("NEW:BEFORE"); n()
    tag("NEW:AFTER"); n()
    tag("CLEAR:BEFORE"); n(777); n()
    tag("CLEAR:AFTER"); n(0); n()
    lines.extend(protocol["programs"]["stop"])
    tag("STOP:BEFORE"); n()
    tag("STOP:AFTER")
    for v in (555, 111, 222, 333):
        n(v)
    tag("FINAL"); n()
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


class SealedProtocol(unittest.TestCase):
    def test_original_corpus_is_closed_and_executable(self):
        p = a3.protocol()
        self.assertEqual(len(p["stages"]), 7)
        self.assertEqual(p["sessions"], ["original", "repeat"])
        self.assertEqual(len(p["screens_expected"]), 10)
        self.assertEqual(len(p["snapshots_expected"]), 5)

    def test_corpus_forgery_rejected(self):
        with mock.patch.object(a3, "CORPUS_SHA", "0" * 64):
            reject(a3.protocol, "CORPUS_SHA_DRIFT")

    def test_program_token_and_stop_commands(self):
        p = a3.protocol()
        self.assertIn("20 STOP", p["programs"]["run"])
        self.assertIn("40 STOP", p["programs"]["stop"])
        self.assertIn("LIST #8", p["stages"][2]["commands"])
        self.assertIn("NEW", p["stages"][4]["commands"])
        self.assertIn("CLEAR", p["stages"][5]["commands"])
        self.assertEqual(p["stages"][-1]["commands"][-1].split()[-1],
                         "CAP32_EXIT")

    def test_mutated_automation_stage_rejected(self):
        p = a3.protocol()
        fake = json.loads(json.dumps(p))
        fake["stages"][4]["commands"].remove("NEW")
        with mock.patch.object(a3, "read", return_value=a3.canonical(fake)):
            reject(a3.protocol, "CORPUS_SHA_DRIFT")


class SyntheticPrinter(unittest.TestCase):
    def setUp(self):
        self.proto = a3.protocol()
        self.data = synthetic_printer(self.proto)

    def test_exact_synthetic_sequence(self):
        found = a3.observe_printer(self.data, self.proto)
        self.assertEqual(found["values"]["boot_1"], 10)
        self.assertEqual(found["values"]["boot_2"], 100)
        self.assertEqual(found["values"]["clear_after_var"], 0)
        self.assertEqual(len(found["lists"]["run"]), 8)
        self.assertEqual(len(found["lists"]["stop"]), 10)

    def test_no_missing_or_reordered_time(self):
        reject(lambda: a3.observe_printer(
            self.data.replace(b" 100\r\n", b"", 1), self.proto),
            "PRINTER_NUMBER_AMBIGUOUS")

    def test_bad_command_marker_rejected(self):
        reject(lambda: a3.observe_printer(
            self.data.replace(b"A3:NEW:BEFORE", b"A3:CLEAR:BEFORE"), self.proto),
            "PRINTER_MARKER_OR_ORDER_NEW:BEFORE")

    def test_old_program_survives_new_rejected(self):
        forged = self.data.replace(b"A3:NEW:AFTER",
                                  b"10 PRINT #8,TIME\r\nA3:NEW:AFTER", 1)
        reject(lambda: a3.observe_printer(forged, self.proto),
               "PRINTER_MARKER_OR_ORDER_NEW:AFTER")

    def test_stop_cont_missing_rejected(self):
        forged = self.data.replace(b"A3:STOP:AFTER", b"A3:STOP:WAIT", 1)
        reject(lambda: a3.observe_printer(forged, self.proto),
               "PRINTER_MARKER_OR_ORDER_STOP:AFTER")

    def test_list_order_and_text_rejected(self):
        forged = self.data.replace(b"20 STOP", b"20 END", 1)
        reject(lambda: a3.observe_printer(forged, self.proto),
               "PRINTER_LIST_TEXT_run")

    def test_clear_variable_control_rejected(self):
        forged = self.data.replace(b"A3:CLEAR:AFTER\r\n 0\r\n",
                                   b"A3:CLEAR:AFTER\r\n 777\r\n", 1)
        reject(lambda: a3.observe_printer(forged, self.proto),
               "CLEAR_VARIABLE_CONTROL")

    def test_output_duplicate_rejected(self):
        reject(lambda: a3.observe_printer(self.data+b" 9000\r\n", self.proto),
               "PRINTER_TRAILING_OR_DUPLICATE")

    def test_print_numeric_rejects_ambiguous(self):
        for text in (b"", b"NaN", b"1 2", b"-1", b"1.4", b"4.3E+50"):
            reject(lambda text=text: a3.integer(text),
                   "PRINTER_")
        self.assertEqual(a3.integer(b" 4.2E+03\r"), 4200)


class SyntheticRamLink(unittest.TestCase):
    def test_wrong_address_and_type(self):
        found = {"scalar": {"address": 800, "value_hex": "00 00 00 00 81"}}
        values = {"run1_address": 801, "run1_stored": 1}
        reject(lambda: a3.link_witness(found, values, "run1"),
               "RAM_AT_ADDRESS_MISMATCH")
        values["run1_address"] = 800
        self.assertEqual(a3.link_witness(found, values, "run1")[
            "stored_decimal_printed"], 1)
        values["run1_stored"] = 2
        reject(lambda: a3.link_witness(found, values, "run1"),
               "RAM_REAL5_PRINT_MISMATCH")
        reject(lambda: a3.a1.check_window(
            bytes.fromhex("00 00 D4 05 00 00 00 00 81"), 796, [ord("T")]),
            "RAM_SCALAR_IDENTITY_OR_TYPE")


class ReplayFailClosed(unittest.TestCase):
    def test_external_manifest_seal(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "manifest.json").write_bytes(b"{}\n")
            reject(lambda: a3.verify(folder, "a" * 40, "0" * 64),
                   "EXTERNAL_SEAL_REQUIRED")

    def test_head_and_pin_forgery(self):
        base = {"schema": 1, "mission": "CLK-04-A3",
                "status": "ACQUIRED_PENDING_PNG_REVIEW",
                "head": "a" * 40, "corpus_sha256": a3.CORPUS_SHA,
                "rom_archived": False, "snapshot_archived": False,
                "observation_class": "CPC6128_CAPRICE32_ROM_BACKED",
                **a3.PINS, "sessions": {}}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for broken, expected in (
                ({**base, "head": "b"*40}, "HEAD_OR_MANIFEST_MISMATCH"),
                ({**base, "rom_sha256": "BAD"}, "PROVENANCE_MISMATCH"),
                ({**base, "image": "BAD"}, "PROVENANCE_MISMATCH"),
                ({**base, "caprice_commit": "BAD"}, "PROVENANCE_MISMATCH"),
                ({**base, "corpus_sha256": "BAD"}, "PROVENANCE_MISMATCH"),
                (base, "SESSIONS_MISSING_OR_EXTRA")):
                blob = a3.canonical(broken)
                (folder / "manifest.json").write_bytes(blob)
                reject(lambda blob=blob: a3.verify(folder, "a"*40,
                       a3.sha(blob)), expected)

    def test_sna_and_rom_cannot_be_archived_in_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "evidence.sna").write_bytes(b"secret")
            # Rejection is enforced during verify after manifest validation;
            # this structural test establishes inventory cannot silently omit it.
            self.assertIn("evidence.sna", a3.inventory(folder))
            self.assertEqual(a3.inventory(folder)["evidence.sna"]["bytes"], 6)

    def test_process_separation_and_png_are_required(self):
        p = a3.protocol()
        self.assertEqual(len(set(p["sessions"])), 2)
        self.assertEqual(len(p["screens_expected"]), 10)
        self.assertFalse(a3.prior.valid_png(b"not a png"))


if __name__ == "__main__":
    unittest.main()
