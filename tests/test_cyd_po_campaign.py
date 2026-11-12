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
from unittest.mock import patch, Mock
import contextlib
import types
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

    def test_c1_en_only_pulse_and_failure_release(self):
        class Pins:
            is_open = True
            def __init__(self):
                self.trace = []
                self._dtr = self._rts = False
                self.fail = False
            @property
            def dtr(self): return self._dtr
            @dtr.setter
            def dtr(self, value):
                self.trace.append(('DTR', value))
                self._dtr = value
            @property
            def rts(self): return self._rts
            @rts.setter
            def rts(self, value):
                self.trace.append(('RTS', value))
                self._rts = value
                if self.fail and value: raise OSError('RTS_FAIL')
        p = Pins()
        with patch.object(po.time, 'sleep') as delay:
            po.auto_reset(p)
        delay.assert_called_once_with(.10)
        self.assertEqual(p.trace, [('DTR',False), ('RTS',False), ('RTS',True),
                                   ('RTS',False), ('DTR',False)])
        self.assertFalse(p.dtr or p.rts)
        p.is_open = False
        with self.assertRaisesRegex(po.Incomplete, 'RESET_REQUIRES_OPEN_UART'):
            po.auto_reset(p, 0)
        p.is_open = True
        p.fail = True
        with self.assertRaisesRegex(OSError, 'RTS_FAIL'):
            po.auto_reset(p, 0)
        self.assertFalse(p.dtr or p.rts)
        self.assertEqual(p.trace[-2:], [('RTS',False), ('DTR',False)])

    class C1Device(Device):
        def __init__(self, *, manual=False, no_boot=False, sha=HEAD,
                     fail_open=False, interrupt=False):
            super().__init__(startup=b'')
            self.is_open = False
            self.trace = []
            self._rts = self._dtr = False
            self.manual = manual
            self.no_boot = no_boot
            self.sha = sha
            self.fail_open = fail_open
            self.interrupt = interrupt
            self.pulses = self.reads = 0
        @property
        def dtr(self): return self._dtr
        @dtr.setter
        def dtr(self, value):
            self.trace.append(('DTR', value)); self._dtr = value
        @property
        def rts(self): return self._rts
        @rts.setter
        def rts(self, value):
            old = self._rts
            self.trace.append(('RTS', value)); self._rts = value
            if old and not value and self.is_open:
                self.pulses += 1
                if not self.no_boot and not self._dtr:
                    self.buffer.extend(boot(sha=self.sha))
        def __enter__(self):
            if self.fail_open: raise OSError('USB busy')
            self.is_open = True
            self.trace.append(('OPEN', True))
            return self
        def __exit__(self, *args): self.is_open = False
        def open(self): self.is_open = True
        def read(self, size):
            self.reads += 1
            if self.manual and self.reads == 2 and not self.no_boot:
                self.buffer.extend(boot(sha=self.sha))
            return super().read(size)
        def write(self, data):
            if self.interrupt: raise KeyboardInterrupt
            return super().write(data)

    def c1_run(self, device, *, manual=False, shots='none', flash=False, dry=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output = Path(tmp.name)/'campaigns'
        out, err = io.StringIO(), io.StringIO()
        factory = Mock(return_value=device)
        args = ['--suite','j1_25_b2_b3', '--shots',shots,
                '--output-root',str(output), '--boot-timeout','.03',
                '--command-timeout','.2','--shot-timeout','3']
        if manual: args.append('--manual-reset')
        if dry: args.append('--dry-run')
        else: args += ['--port','/dev/ttyUSB0',
                      '--flash' if flash else '--existing-firmware']
        def idf(folder, head, port, progress=None):
            for stage in ('BUILD','FLASH'):
                if progress:
                    progress(stage,'START',f'HEAD={head} port={port}')
                    progress(stage,'OK','simulated test')
            return {'binary_version': VER, 'profile': 'CONSOLE'}
        with patch.object(po,'identity',return_value=HEAD), \
             patch.object(po,'collision_guard'), \
             patch.object(po,'run_idf',side_effect=idf) as build, \
             patch.dict(sys.modules,{'serial':types.SimpleNamespace(Serial=factory)}), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = po.main(args)
        if dry:
            self.assertFalse(output.exists())
            factory.assert_not_called()
            build.assert_not_called()
            return code, None, [], out.getvalue()+err.getvalue()
        dirs = list(output.glob('CYD_*'))
        self.assertEqual(len(dirs),1)
        folder = dirs[0]
        rows = [json.loads(x) for x in
                (folder/'host-events.jsonl').read_text().splitlines()]
        self.assertEqual([x['sequence'] for x in rows],list(range(1,len(rows)+1)))
        factory.assert_called_once()
        if flash: build.assert_called_once()
        else: build.assert_not_called()
        return code,folder,rows,out.getvalue()+err.getvalue()

    def test_c1_six_cases_progress_boot_order_and_archive(self):
        d = self.C1Device()
        rc,folder,rows,out = self.c1_run(d)
        self.assertEqual(rc,0)
        self.assertEqual(d.pulses,1)
        self.assertFalse(d.dtr or d.rts)
        events = [(x['step'],x['state']) for x in rows]
        self.assertLess(events.index(('UART','OPEN')),events.index(('RESET','AUTO_START')))
        self.assertLess(events.index(('RESET','AUTO_DONE')),events.index(('BOOT','WAIT')))
        self.assertLess(events.index(('BOOT','VERIFIED')),events.index(('SCENARIO 1/6','START')))
        for n in range(1,7):
            stages = [x['state'] for x in rows if x['step']==f'SCENARIO {n}/6']
            self.assertEqual(stages,['START','NEW','BASIC_LOADED','LIST START',
                                     'LIST END','RUN START','RUN TERMINAL','END PASS'])
        self.assertIn('[SCENARIO 6/6] END PASS',out)
        self.assertIn('6/6 scenarios 0/0 PNG',out)
        self.assertEqual(json.loads((folder/'results.json').read_text())['status'],
                         'PO_REVIEW_PENDING')
        self.assertTrue((folder/'uart.raw.log').read_bytes().startswith(boot()))
        with zipfile.ZipFile(folder/(folder.name+'.zip')) as z:
            for name in ('host-events.jsonl','uart.raw.log','uart.tx.jsonl'):
                self.assertEqual(z.read(name),(folder/name).read_bytes())
            self.assertIn('"step": "SUMMARY"',z.read('host-events.jsonl').decode())
        for row in (folder/'SHA256SUMS').read_text().splitlines():
            digest,name=row.split('  ',1)
            self.assertEqual(digest,po.sha256(folder/name))

    def test_c1_twelve_crc_shot_progress_and_flash_phase(self):
        d = self.C1Device()
        rc,folder,rows,out = self.c1_run(d, shots='all', flash=True)
        self.assertEqual(rc,0)
        self.assertEqual(len([x for x in rows if x['step']=='SHOT' and
                              x['state']=='CRC_OK']),12)
        self.assertEqual(len(list((folder/'screenshots').glob('*.png'))),12)
        self.assertIn('12/12 PNG',out)
        for step in ('BUILD','FLASH'):
            self.assertEqual([x['state'] for x in rows if x['step']==step],
                             ['START','OK'])

    def test_c1_manual_port_error_wrong_sha_no_boot_interrupt(self):
        manual = self.C1Device(manual=True)
        rc,folder,rows,_ = self.c1_run(manual,manual=True)
        self.assertEqual(rc,0)
        self.assertEqual(manual.pulses,0)
        self.assertFalse(any(k=='RTS' and v for k,v in manual.trace))
        self.assertIn(('RESET','MANUAL_WAIT'),[(x['step'],x['state']) for x in rows])
        for label,dev in (('port',self.C1Device(fail_open=True)),
                          ('sha',self.C1Device(sha='a'*40)),
                          ('boot',self.C1Device(no_boot=True)),
                          ('ctrlc',self.C1Device(interrupt=True))):
            with self.subTest(label=label):
                code,f,ev,text = self.c1_run(dev)
                self.assertEqual(code,2)
                self.assertEqual(json.loads((f/'results.json').read_text())['status'],
                                 'INCOMPLETE')
                self.assertIn('[SUMMARY]',text)
                with zipfile.ZipFile(f/(f.name+'.zip')) as z:
                    self.assertIn('host-events.jsonl',z.namelist())
                    self.assertEqual(z.read('host-events.jsonl'),
                                     (f/'host-events.jsonl').read_bytes())
                if label=='boot':
                    self.assertIn('--manual-reset',text)
                    self.assertEqual(dev.pulses,1)
                    self.assertIn(('BOOT','FAIL'),[(x['step'],x['state']) for x in ev])
                if label=='port': self.assertEqual(dev.pulses,0)
                if label=='ctrlc': self.assertIn('END FAIL',text)

    def test_c1_dry_run_no_port_reset_archive(self):
        d = self.C1Device()
        rc,_,_,out = self.c1_run(d,dry=True)
        self.assertEqual(rc,0)
        self.assertEqual(d.trace,[])
        self.assertIn('"classification": "NOT_VERIFIED"',out)

    def test_c1_idf_failure_progress_prevents_flash(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=[]
            with patch.object(po.subprocess,'run',
                              return_value=types.SimpleNamespace(
                                  returncode=0,stdout='ESP-IDF v4.4',stderr='')):
                with self.assertRaisesRegex(po.Incomplete,'WRONG_HOST_IDF_VERSION'):
                    po.run_idf(Path(tmp),HEAD,'/dev/ttyUSB0',
                               progress=lambda *x: rows.append(x))
            self.assertEqual([x[:2] for x in rows],
                             [('BUILD','START'),('BUILD','FAIL')])
            self.assertFalse((Path(tmp)/'flash.log').exists())


if __name__ == '__main__':
    unittest.main()