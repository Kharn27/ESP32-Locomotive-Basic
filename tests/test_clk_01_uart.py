"""CLK-01: synthetic parser fixtures only (never CPC/CYD measurements)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from clk_01_uart import Reject, analyze, corpus, format_report

SHA = "c8cec8b1b4d0cab553cdc8b97b751aef3dd1370d"
SCOPE = "RUN_slices_including_repaint_excluding_final_prompt"


def example():
    out = [
        "HW4-C2 START project=loco version=%s idf=v5.5.6 ON_DEVICE_UNVERIFIED" % SHA[:7],
        "HW4-DISP-PROFILE BOOT spi_request_hz=40000000 variant=SPI40 sha=" + SHA,
        "HW4-C3-B2-C1 LCD_METRICS stage=after_line flushes=1 bands=1",
    ]
    seq = 0
    for spec in corpus()["programs"]:
        source = Path(__file__).resolve().parent / "fixtures/cpc6128/clk_01_speed" / spec["file"]
        commands = ["NEW"] + source.read_text().splitlines()
        for _ in range(3):
            commands.extend(("!CLS", "RUN"))
        for cmd in commands:
            out.append("HW4-C2 UART_LINE length=%d hex=%s" %
                       (len(cmd), cmd.encode("ascii").hex()))
            if cmd != "RUN":
                continue
            seq += 1
            out += [
                "HW4-RUN-B RUN_START quantum=8 uart_poll_max=16 budget=none sha=" + SHA,
                "HW4-DISP-PROFILE RUN_DURATION run=%d core_us=%d scope=%s" %
                (seq, seq + 1000, SCOPE),
                "HW4-RUN-B RUN_TERMINAL state=5 quanta=3 steps=12 break_source=none "
                "stop_calls=0 latency_us=0 ignored_input_lines=0 overflow_input_lines=0 "
                "sha=" + SHA + " program_preserved=1",
                "HW4-C2 DEVICE_MEMORY stage=run_terminal heap8_free=200000 "
                "heap8_largest=110000 stack_margin_bytes=4000 dma_fault=0 "
                "dma_timeouts=0 lcd_error=ESP_OK",
                "HW4-DISP-PROFILE SUMMARY run=%d stage=run_terminal_after_prompt completed=2" % seq,
            ]
            for name in ("full25", "partial", "scroll_associated"):
                out.append("HW4-DISP-PROFILE CLASS run=%d stage=run_terminal_after_prompt "
                       "name=%s n=1 wall_us=100 render_pack_us=40 sem_wait_us=20" %
                       (seq, name))
    return "\n".join(out) + "\n"


class TestUart(unittest.TestCase):
    def setUp(self):
        self.log = example()
        self.manifest = corpus()

    def test_synthetic_valid(self):
        answer = analyze(self.log, SHA, self.manifest)
        self.assertEqual(len(answer["runs"]), 5)
        self.assertEqual(answer["runs"][0]["median_us"], 1002)
        self.assertEqual(answer["runs"][-1]["median_us"], 1014)
        csv_text, markdown = format_report(answer)
        self.assertEqual(len(csv_text.splitlines()), 6)
        self.assertIn("NOT_COMPARABLE", markdown)

    def test_falsifications(self):
        x = self.log
        mutants = {
            "missing_start": x.replace("RUN_START quantum=8", "NO_START quantum=8", 1),
            "missing_duration": x.replace("RUN_DURATION run=1", "NO_DURATION run=1", 1),
            "missing_terminal": x.replace("RUN_TERMINAL state=5", "NO_TERMINAL state=5", 1),
            "broken_run": x.replace("RUN_TERMINAL state=5", "RUN_TERMINAL state=4", 1),
            "invalid_sha": x.replace("sha=" + SHA, "sha=" + "a"*40, 1),
            "wrong_terminal_sha": x.replace("sha=" + SHA + " program_preserved",
                                             "sha=" + "a"*40 + " program_preserved", 1),
            "dirty_boot": x.replace("version=" + SHA[:7], "version=" + SHA[:7]+"-dirty"),
            "foreign_boot": x.replace("version=" + SHA[:7], "version=deadbee"),
            "reboot": x + "HW4-C2 START project=loco version=c8cec8b idf=v5.5.6\n",
            "wrong_idf": x.replace("idf=v5.5.6", "idf=v5.5.5"),
            "wrong_spi": x.replace("variant=SPI40", "variant=SPI20"),
            "bad_dma": x.replace("dma_fault=0", "dma_fault=2", 1),
            "bad_timeout": x.replace("dma_timeouts=0", "dma_timeouts=1", 1),
            "bad_lcd": x.replace("lcd_error=ESP_OK", "lcd_error=ESP_FAIL", 1),
            "no_memory": x.replace(" DEVICE_MEMORY stage=run_terminal",
                                   " MISSING_MEMORY stage=run_terminal", 1),
            "zero_stack": x.replace("stack_margin_bytes=4000", "stack_margin_bytes=0", 1),
            "no_lcd_metrics": x.replace(" LCD_METRICS ", " NO_LCD ", 1),
            "wrong_scope": x.replace(SCOPE, "CPU_BASIC_EXCLUSIVE", 1),
            "no_summary": x.replace(" SUMMARY run=1 ", " WRONG_SUMMARY run=1 ", 1),
            "no_class": x.replace(" CLASS run=1 stage=run_terminal_after_prompt name=partial",
                                  " LOST_CLASS run=1 stage=run_terminal_after_prompt name=partial", 1),
            "duplicate_field": x.replace("core_us=1001", "core_us=1001 core_us=1001", 1),
            "run_gap": x.replace("RUN_DURATION run=7", "RUN_DURATION run=9", 1),
            "uart_overflow": x.replace("overflow_input_lines=0", "overflow_input_lines=1", 1),
            "error": x + "Guru Meditation Error: Core 1 panic\n",
            "truncated": "\n".join(x.splitlines()[:-1]),
            "wrong_cls": x.replace("UART_LINE length=4 hex=21434c53", "UART_LINE length=4 hex=21434c54", 1),
            "tampered_source": x.replace("UART_LINE length=7 hex=31302041253d30", "UART_LINE length=7 hex=31302041253d31", 1),
            "extra_command": x + "HW4-C2 UART_LINE length=3 hex=52554e\n",
        }
        for name, bad in mutants.items():
            with self.subTest(name=name), self.assertRaises(Reject):
                analyze(bad, SHA, self.manifest)

    def test_bad_head_and_n(self):
        for sha in ("abc", "a" * 40, SHA + "0"):
            with self.subTest(sha=sha), self.assertRaises(Reject):
                analyze(self.log, sha, self.manifest)
        for count in (2, 4):
            with self.subTest(count=count), self.assertRaises(Reject):
                analyze(self.log, SHA, self.manifest, repetitions=count)


if __name__ == "__main__":
    unittest.main()
