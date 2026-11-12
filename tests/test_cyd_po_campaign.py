#!/usr/bin/env python3
"""PO-AUTO-01 synthetic UART state machine and negative archive/provenance tests."""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import cyd_po_campaign as po

HEAD = "4a386ee82f6ca2c5bbf73cf17c794f5274b449e9"
VER = HEAD[:7]


def shot(id: str, seq: int, crc_bad=False, truncated=False,
         duplicate=False, wrong_head=False) -> bytes:
    data = bytes([0, 0])*320
    crc = zlib.crc32(data)
    b64 = base64.b64encode(data).decode("ascii")
    lines = [f"@CYDSHOT:1|BEGIN|id={id}|seq={seq}|w=320|h=240|pix=RGB565LE|orient=LCD10_UNVERIFIED|fw={VER}|sha={HEAD if not wrong_head else 'a'*40}\n"]
    for n in range(240):
        if truncated and n == 100:
            continue
        lines.append(f"@CYDSHOT:1|ROW|id={id}|n={n}|crc={crc:08X}|b64={b64}\n")
    global_crc = zlib.crc32(data * 240)
    if crc_bad:global_crc ^= 1
    lines.append(f"@CYDSHOT:1|DONE|id={id}|crc={global_crc:08X}\n")
    lines.append(f"HW4-SHOT-A CAPTURE_DONE trigger=PROMPT id={id} seq={seq} orientation=10 source=LOGICAL_RGB565LE version={VER} sha={HEAD} tft_equivalence=ON_DEVICE_UNVERIFIED\n")
    return "".join(lines).encode("ascii")


def boot(version=VER, idf="v5.5.6", sha=HEAD, omit_start=False) -> bytes:
    lines = []
    if not omit_start:
        lines += [f"HW4-C2 START project=loco_esp32_display_probe version={version} idf={idf} target=esp32 ON_DEVICE_UNVERIFIED\n"]
    lines += [f"HW4-DISP-PROFILE BOOT spi_request_hz=40000000 variant=SPI40 physical_gram_visible=UNVERIFIED sha={sha}\n",
              "HW4-C2 UART_READY port=0 baud=115200 input=raw CR_LF_CRLF=1\n",
              "HW4-C3-B2 INPUT_READY capacity=32 screen_row=12 policy=mode1_scroll\n"]
    return "".join(lines).encode("ascii")


class Device:
    def __init__(self, startup: bytes | None = None, *, fault: str | None = None):
        self.buffer = bytearray(boot() if startup is None else startup)
        self.writes = []
        self.fault = fault
        self.seq = 0
        self.last_command = None

    def write(self, data):
        assert data.endswith(b"\r")
        text = data[:-1].decode('ascii')
        self.writes.append(data)
        self.last_command = text
        echo = f"HW4-C2 UART_LINE length={len(text)} hex={data[:-1].hex()}\n"
        if self.fault == "echo_wrong":
            echo = "HW4-C2 UART_LINE length=4 hex=4c495354\n"
        if self.fault == "panic":
            self.buffer.extend(b"Guru Meditation Error\n")
        if self.fault == "reboot":
            self.buffer.extend(boot())
        if self.fault == "out_of_order":
            self.buffer.extend(b"HW4-C2 UART_LINE length=3 hex=4e4557\n")
        self.buffer.extend(echo.encode('ascii'))
        if text == "RUN":
            self.buffer.extend(f"HW4-RUN-B RUN_START quantum=8 uart_poll_max=8 budget=none sha={HEAD}\n".encode())
            if self.fault == "run_timeout":
                return len(data)
            if self.fault == "run_bad_terminal":
                state = '4'
            else:
                state = '5'
            self.buffer.extend(f"HW4-RUN-B RUN_TERMINAL state={state} quanta=5 steps=10 break_source=none stop_calls=0 ignored_input_lines=0 overflow_input_lines=0 sha={HEAD} program_preserved=1\n".encode())
        if text == "RUN" and self.fault != "run_timeout":
            self.buffer.extend(b"HW4-C2 DEVICE_MEMORY stage=run_terminal heap8_free=251220 heap8_largest=140000 heap8_min=240000 stack_margin_bytes=3360 dma_transfers=4 dma_timeouts=0 dma_fault=0 lcd_error=ESP_OK\n")
        policy = ('NEW_RETURN'  if text=='NEW' else 'LIST_RETURN' if text=='LIST' else
                  'RUN_RETURN' if text=='RUN' else 'DIRECT_UNKNOWN' if text=='!SHOT' else 'NUMBERED_STORED')
        self.buffer.extend(f"HW4-READY-A READY_POLICY transition={policy} emitted=1 row=12 col=0 source=CONSOLE\n".encode())
        self.buffer.extend(b"HW4-C3-B2 INPUT_READY capacity=32 screen_row=12 policy=mode1_scroll\n")
        if text == '!SHOT':
            self.seq += 1
            ident = f'CYD_12345678_{self.seq}'
            if self.fault == "shot_duplicate" and self.seq > 1:
                ident = 'CYD_12345678_1'
            self.buffer.extend(shot(ident, self.seq, crc_bad=self.fault=='shot_crc',
                                    truncated=self.fault=='shot_truncated',
                                    wrong_head=self.fault=='shot_sha'))
        return len(data)

    def read(self, size):
        n = min(size, len(self.buffer))
        part = self.buffer[:n]
        del self.buffer[:n]
        return bytes(part)

    def flush(self): pass


class Tests(unittest.TestCase):
    def make(self, device=None, timeout=.07):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        (folder / 'screenshots').mkdir()
        return po.Session(device or Device(), folder, HEAD, None, timeout, timeout, timeout)

    def test_suite_and_plan(self):
        suite = po.load_suite('j1_25_b2_b3')
        self.assertEqual(len(suite['scenarios']), 6)
        self.assertEqual([x['group'] for x in suite['scenarios']], ['B2']*3+['B3']*3)
        for mode, count in (('all', 12), ('run', 6), ('none', 0)):
            plan = po.plan(suite, mode)
            self.assertEqual(sum(x['commands'].count('!SHOT') for x in plan), count)
        with self.assertRaises(po.Incomplete): po.load_suite('../wrong')

    def test_boot_attestation_rejects(self):
        for case, start in [('no_start',boot(omit_start=True)), ('bad_version',boot(version='deadbeef')),
                            ('bad_idf',boot(idf='v5.0')),('bad_sha',boot(sha='a'*40)),
                            ('reboot',boot()+boot())]:
            with self.subTest(case=case):
                sess = self.make(Device(startup=start))
                try:
                    if case == 'reboot':
                        sess.boot()
                        # The second boot is still pending; any extra command catches it.
                        with self.assertRaises(po.Incomplete):sess.submit('NEW','NEW_RETURN')
                    else:
                        with self.assertRaises(po.Incomplete): sess.boot()
                finally: sess.close()

    def test_uart_commands_and_rx_tx_exact(self):
        device = Device()
        sess = self.make(device)
        try:
            self.assertEqual(sess.boot(), VER)
            sess.submit('NEW','NEW_RETURN')
            sess.submit('10 DATA 1,2','NUMBERED_STORED')
            sess.submit('LIST','LIST_RETURN')
            sess.submit('RUN','RUN_RETURN', run=True)
            raw = (sess.folder / 'uart.raw.log').read_bytes()
            self.assertTrue(raw.startswith(boot()))
            self.assertIn(b'HW4-RUN-B RUN_TERMINAL',raw)
            self.assertNotIn(b'\nNEW\r',raw)
            self.assertEqual([bytes.fromhex(json.loads(line)['hex']) for line in
                (sess.folder / 'uart.tx.jsonl').read_text().splitlines()],device.writes)
            self.assertEqual(sess.tx_count, 4)
        finally:sess.close()

    def test_normal_12_crc_images_and_zip(self):
        device = Device()
        sess = self.make(device,timeout=3)
        try:
            sess.boot()
            for n in range(6):
                sess.submit('NEW','NEW_RETURN')
                sess.submit(f'{10+n} DATA 1','NUMBERED_STORED')
                sess.submit('LIST','LIST_RETURN')
                sess.capture('CASE'+str(n),'LIST')
                sess.submit('RUN','RUN_RETURN',run=True)
                sess.capture('CASE'+str(n),'RUN')
            self.assertEqual(len(sess.shots),12)
            self.assertEqual(sess.watcher.bad,0)
            self.assertEqual(len(list((sess.folder/'screenshots').glob('*.png'))),12)
            self.assertEqual([s['seq'] for s in sess.shots],list(range(1,13)))
        finally:sess.close()
        result={'status':'PO_REVIEW_PENDING','shots':sess.shots}
        zip_path=po.finalize(sess.folder,result)
        self.assertTrue(zip_path.is_file())
        self.assertIn('uart.raw.log',zipfile.ZipFile(zip_path).namelist())
        self.assertIn('SHA256SUMS',zipfile.ZipFile(zip_path).namelist())
        with self.assertRaises(FileExistsError):po.finalize(sess.folder,result)
        for row in (sess.folder/'SHA256SUMS').read_text().splitlines():
            digest,name=row.split('  ',1)
            self.assertEqual(digest,po.sha256(sess.folder / name))

    def test_fail_closed_negatives(self):
        for fault in ('echo_wrong','panic','out_of_order','reboot','run_timeout','run_bad_terminal',
                      'shot_crc','shot_truncated','shot_sha','shot_duplicate'):
            with self.subTest(fault=fault):
                sess=self.make(Device(fault=fault),timeout=.03)
                try:
                    sess.boot()
                    with self.assertRaises(po.Incomplete):
                        if fault in ('run_timeout','run_bad_terminal'):
                            sess.submit('RUN','RUN_RETURN',run=True)
                        elif fault in ('shot_crc','shot_truncated','shot_sha','shot_duplicate'):
                            sess.capture('CASE','LIST')
                            if fault == 'shot_duplicate':sess.capture('CASE','RUN')
                        else:sess.submit('NEW','NEW_RETURN')
                finally:sess.close()

    def test_memory_and_interruption(self):
        memory=b"HW4-C2 DEVICE_MEMORY stage=run_terminal heap8_free=251220 heap8_largest=13000 stack_margin_bytes=3360 dma_timeouts=1 dma_fault=0 lcd_error=ESP_OK\n"
        sess=self.make(Device(startup=boot()+memory))
        try:
            sess.boot()
            with self.assertRaisesRegex(po.Incomplete,'DEVICE_MEMORY_FAULT'):
                sess.next_line(time.monotonic()+.05)
        finally:sess.close()
        with tempfile.TemporaryDirectory() as root:
            dest=Path(root)
            a=po.make_folder(dest,'test',HEAD)
            with patch.object(po, 'datetime') as fake:
                fake.now.return_value.strftime.return_value='2026-11-12_10-10-10'
                b=po.make_folder(dest,'same',HEAD)
                with self.assertRaises(FileExistsError):po.make_folder(dest,'same',HEAD)
            self.assertNotEqual(a,b)
        sess=self.make(Device())
        try:
            sess.boot()
            with patch.object(sess.port, 'read', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):sess.submit('NEW','NEW_RETURN')
        finally:sess.close()


if __name__ == '__main__':
    unittest.main()