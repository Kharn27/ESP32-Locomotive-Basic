#!/usr/bin/env python3
"""Host-only FAKES to challenge CLK-06-A1 replay; NEVER CPC observations."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import clk_06_a1_oracle as oracle


@contextmanager
def source_root():
    original = oracle.ROOT
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "tests/fixtures/cpc6128/clk_06_a1_after_remain"
            dest.mkdir(parents=True)
            dest.joinpath("corpus.json").write_bytes(oracle.CORPUS.read_bytes())
            source_dir = dest / "sources"
            source_dir.mkdir()
            for file in (oracle.CORPUS.parent / "sources").glob("*.bas"):
                (source_dir/file.name).write_bytes(file.read_bytes())
            oracle.ROOT = root
            oracle.CORPUS = dest / "corpus.json"
            yield root
    finally:
        oracle.ROOT = original
        oracle.CORPUS = original / "tests/fixtures/cpc6128/clk_06_a1_after_remain/corpus.json"


class FakeRam:
    @staticmethod
    def records(raw):
        pos, numbers, records = 0, [], []
        while pos < len(raw)-2:
            length = int.from_bytes(raw[pos:pos+2], 'little')
            number = int.from_bytes(raw[pos+2:pos+4], 'little')
            assert length > 4
            numbers.append(number)
            records.append({'offset':pos, 'length':length})
            pos += length
        assert raw[pos:] == b'\x00\x00'
        return numbers, records


class FakeClk03:
    def ram_parser(self): return FakeRam
    def cfg_validate(self, cfg):
        assert cfg.read_text() == 'FAKE_CPC_CONFIG_FOR_TESTS_ONLY\n'
    def parse_numbers(self, raw, n):
        result = [int(x) for x in raw.split()]
        assert len(result) == n
        return result


def program_for(case):
    # Falsification fixture only: no emulator, never an oracle.
    result = bytearray()
    for line in case['lines']:
        num = int(line.split(' ',1)[0])
        body = b'X'
        for word, token in [('AFTER ',b'\x80'), ('REMAIN(0)',b'\xff\x13'),
                            ('GOSUB ',b'\x9f'), ('RETURN',b'\xc9')]:
            if word in line: body += token
        length = len(body)+5
        result += length.to_bytes(2,'little') + num.to_bytes(2,'little') + body + b'\x00'
    return bytes(result) + b'\x00\x00'


def png_chunk(kind, data):
    return (len(data).to_bytes(4,'big') + kind + data +
            (zlib.crc32(kind+data)&0xffffffff).to_bytes(4,'big'))


def fake_png():
    header = (320).to_bytes(4,'big')+(240).to_bytes(4,'big')+bytes([8,2,0,0,0])
    # 240 scanlines of 320 RGB black pixels: syntactically valid 320x240 PNG.
    rows = (b'\x00' + b'\x00'*960)*240
    return (b'\x89PNG\r\n\x1a\n'+png_chunk(b'IHDR',header)+
            png_chunk(b'tEXt', b'FAKE_ONLY\x00' + b'X'*1100)+
            png_chunk(b'IDAT',zlib.compress(rows)) + png_chunk(b'IEND',b''))


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.folder = Path(self.dir.name)/'synthetic-not-oracle'
        self.folder.mkdir()
        self.cases = oracle.source_cases()
        self.patcher = patch.object(oracle, 'clk03', return_value=FakeClk03())
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def file(self, name, data):
        path = self.folder/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data if isinstance(data,bytes) else data.encode())

    def new_manifest(self):
        shutil.rmtree(self.folder)
        self.folder.mkdir()
        meta = {'schema':1,'mission':'CLK-06-A1','status':'ACQUIRED_PENDING_SCREEN_REVIEW',
                'head':'a'*40,'corpus_sha256':oracle.CORPUS_SHA,
                'caprice_commit':oracle.CAP_SHA,'rom_sha256':oracle.ROM_SHA,
                'container_image':oracle.IMAGE,
                'caprice_binary_sha256':oracle.CAP_BINARY_SHA,
                'caprice_version':'Caprice32 v4.6.0-'+oracle.CAP_SHA+'\nFAKE_TEST_ONLY',
                'observation_class':'ROM_BACKED_CPC6128_RAW_PENDING_SCREEN_REVIEW',
                'rom_archived':False,'sna_archived':False,
                'session_names':['original','repeat'],'sessions':{},
                'run_id':'SYNTHETIC_TEST_ONLY'}
        start = datetime(2026,11,16,tzinfo=timezone.utc)
        counter=0
        def proc(directory, commands=None, printer=b'FAKE:NOT_ORACLE\r\n'):
            nonlocal counter
            directory.mkdir(parents=True,exist_ok=True)
            stamp = (start + timedelta(seconds=counter)).isoformat()
            counter += 1
            for name,data in [('screen.png',fake_png()),
                              ('cap32.cfg','FAKE_CPC_CONFIG_FOR_TESTS_ONLY\n'),
                              ('caprice.log','returncode=0\nFAKE_ONLY\n'),
                              ('printer.dat',printer)]:
                (directory/name).write_bytes(data if isinstance(data,bytes) else data.encode())
            if commands is not None:
                argv = ['xvfb-run','-a','/fake/cap32','-c',str(directory/'cap32.cfg')]
                for cmd in commands:
                    argv += ['-a',cmd.replace('CAP32_SNAPSHOT','\x0c\x0d')]
                (directory/'autocmd.json').write_bytes(oracle.canonical(
                    {'commands':commands,'argv':argv}))
            return {'returncode':0,'wall_seconds':2.0,
                    'started_utc':stamp,'ended_utc':stamp}
        for session in oracle.SESSIONS:
            group=self.folder/session
            info = {'cases':{}}
            info['boot']=proc(group/'boot')
            gate={}
            for kind, values in [('short',[100,140]),('long',[100,4400])]:
                gate[kind] = {**proc(group/('gate_'+kind),printer=(
                    str(values[0])+'\n'+str(values[1])+'\n').encode()),
                    'ticks':values,'delta_ticks':values[1]-values[0]}
            gate['delta_wall_seconds']=14.0
            gate['delta_ticks']=4220
            gate['ticks_per_wall_second']=301.428571
            info['gate']=gate
            for case in self.cases:
                ident=case['id']
                base=group/ident
                program=program_for(case)
                (base).mkdir(parents=True)
                (base/'program.bin').write_bytes(program)
                list_printer=('\r\n'.join(case['lines'])+'\r\n').encode()
                li=proc(base/'list',oracle.command_list(case),printer=list_printer)
                ru=proc(base/'run',oracle.command_run(case))
                info['cases'][ident]={
                    'question':case['question'],
                    'source_sha256':oracle.digest(oracle.source_bytes(case)),
                    'list':li,'run':ru,
                    'ram':oracle.ram_checked(program,case),
                    'region':{'fake':True},
                    'list_line_numbers':[int(x.split(' ',1)[0]) for x in case['lines']],
                    'run_printer_sha256':oracle.digest(b'FAKE:NOT_ORACLE\r\n'),
                    'screen_review':'UNVERIFIED',
                    'observation':'RAW_ACQUIRED_UNINTERPRETED'}
            meta['sessions'][session]=info
        meta['files']=oracle.inventory(self.folder)
        (self.folder/'manifest.json').write_bytes(oracle.canonical(meta))
        return meta

    def seal(self, meta):
        # A test can forge a new external seal; verifier must still catch
        # policy/provenance/structural damage in its replay rules.
        (self.folder/'manifest.json').write_bytes(oracle.canonical(meta))
        return oracle.digest((self.folder/'manifest.json').read_bytes())

    def test_exact_eight_independent_input_cases(self):
        self.assertEqual(len(self.cases),8)
        self.assertEqual(len({oracle.digest(oracle.source_bytes(c)) for c in self.cases}),8)
        self.assertTrue(all('EVERY ' not in '\n'.join(c['lines'])
                            and 'DI:' not in '\n'.join(c['lines'])
                            and 'EI:' not in '\n'.join(c['lines'])
                            for c in self.cases))

    def test_source_drift_rejected(self):
        with source_root():
            doc=json.loads(oracle.CORPUS.read_text())
            doc['cases'][0]['question']='FORGED'
            oracle.CORPUS.write_text(json.dumps(doc))
            with self.assertRaisesRegex(oracle.OracleError,'CORPUS_SHA_MISMATCH'):
                oracle.source_cases()

    def test_synthetic_replay_structure_and_two_sessions(self):
        meta=self.new_manifest()
        self.assertTrue(oracle.verify(self.folder, 'a'*40, self.seal(meta)))
        self.assertEqual(len(meta['sessions']['original']['cases']),8)
        self.assertEqual(len(meta['sessions']['repeat']['cases']),8)

    def test_reject_missing_external_seal_wrong_head_and_manifest(self):
        m=self.new_manifest()
        seal=self.seal(m)
        for head,sig,expected in [('a'*40,'','EXTERNAL_MANIFEST_SEAL_REQUIRED'),
                                  ('b'*40,seal,'MANIFEST_OR_HEAD_MISMATCH'),
                                  ('a'*40,'0'*64,'EXTERNAL_MANIFEST_SEAL_MISMATCH')]:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(oracle.OracleError,expected):
                    oracle.verify(self.folder,head,sig)

    def test_reject_wrong_rom_caprice_image_or_fake_claim(self):
        for key in ['rom_sha256','caprice_commit','container_image',
                    'caprice_binary_sha256','status','observation_class']:
            with self.subTest(key=key):
                m=self.new_manifest()
                m[key]='0'*64
                with self.assertRaises(oracle.OracleError):
                    oracle.verify(self.folder,'a'*40,self.seal(m))

    def test_reject_png_corruption_even_with_forged_inventory_and_seal(self):
        m=self.new_manifest()
        path=self.folder/'repeat/A08_BAD_ARGUMENT/run/screen.png'
        raw=bytearray(path.read_bytes())
        raw[-8]^=1
        path.write_bytes(raw)
        m['files']=oracle.inventory(self.folder)
        m['files'].pop('manifest.json', None)
        with self.assertRaisesRegex(oracle.OracleError,'PNG_'):
            oracle.verify(self.folder,'a'*40,self.seal(m))

    def test_reject_manifest_injected_evidence_or_file_drift(self):
        m=self.new_manifest()
        (self.folder/'original/A01_NEVER_ARMED/run/printer.dat').write_bytes(b'altered')
        with self.assertRaisesRegex(oracle.OracleError,'FILE_MISSING_MODIFIED_OR_INJECTED'):
            oracle.verify(self.folder,'a'*40,self.seal(m))
        m['files']=oracle.inventory(self.folder)
        m['files'].pop('manifest.json', None)
        with self.assertRaisesRegex(oracle.OracleError,'CPC_RUN_PRINTER_SHA_MISMATCH'):
            oracle.verify(self.folder,'a'*40,self.seal(m))

    def test_reject_reused_session_time_and_missing_case(self):
        m=self.new_manifest()
        m['sessions']['repeat']['boot']['started_utc']=(
            m['sessions']['original']['boot']['started_utc'])
        with self.assertRaisesRegex(oracle.OracleError,'PROCESS_NOT_INDEPENDENT'):
            oracle.verify(self.folder,'a'*40,self.seal(m))
        m=self.new_manifest()
        del m['sessions']['repeat']['cases']['A08_BAD_ARGUMENT']
        with self.assertRaisesRegex(oracle.OracleError,'CASE_COUNT_MISMATCH'):
            oracle.verify(self.folder,'a'*40,self.seal(m))

    def test_reject_commands_list_ram_and_unobserved_claim(self):
        for variant in ('commands','list','ram','claim'):
            with self.subTest(variant=variant):
                m=self.new_manifest()
                if variant=='commands':
                    path=self.folder/'original/A02_ARM_FIRE/run/autocmd.json'
                    obj=json.loads(path.read_text())
                    obj['commands'][3]='RUN FORGED'
                    path.write_bytes(oracle.canonical(obj))
                if variant=='list':
                    path=self.folder/'original/A01_NEVER_ARMED/list/printer.dat'
                    path.write_bytes(b'10 ONLY\n')
                if variant=='ram':
                    path=self.folder/'repeat/A02_ARM_FIRE/program.bin'
                    raw=bytearray(path.read_bytes());raw[8]^=1
                    path.write_bytes(raw)
                if variant=='claim':
                    m['sessions']['original']['cases']['A01_NEVER_ARMED']['screen_review']='OBSERVED'
                m['files']=oracle.inventory(self.folder)
                m['files'].pop('manifest.json', None)
                with self.assertRaises(oracle.OracleError):
                    oracle.verify(self.folder,'a'*40,self.seal(m))

    def test_archive_forbidden_full_rom_or_snapshot(self):
        m=self.new_manifest()
        (self.folder/'malice.sna').write_bytes(b'FAKE')
        with self.assertRaisesRegex(oracle.OracleError,'FORBIDDEN_SNAPSHOT_ARCHIVE'):
            oracle.verify(self.folder,'a'*40,self.seal(m))

    def test_acquisition_refuses_fake_head_before_creating_output(self):
        output=self.folder/'not-created'
        with patch.object(oracle.subprocess,'check_output',return_value='b'*40):
            with self.assertRaisesRegex(oracle.OracleError,'HEAD_NOT_CHECKED_OUT'):
                oracle.acquire(self.folder, output, 'a'*40)
        self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
