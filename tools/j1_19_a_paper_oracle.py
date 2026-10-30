#!/usr/bin/env python3
"""J1.19-A: independent CPC6128 PAPER acquisition/verification; no native PAPER.

IMPORTANT: Until actual Caprice32 observations and OUT-OF-ARCHIVE SHA pins
exist, --permanent deliberately refuses ALL archives. No simulated CPC facts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'tests/oracles/inputs/j1_19_a'
PHASE = 'J1.19-A'
SESSIONS = ('original', 'repeat')
BASIC = {
    'P00': '0', 'P01': '1', 'P02': '2', 'P03': '3',
    'P04': '4', 'P15': '15', 'P16': '16', 'PN1': '-1',
}
SCENARIOS = {
    'SPRINT': ('10 PAPER 2', '20 LOCATE 1,15', '30 PRINT "J119TEST"', '40 END'),
    'SCHANGE': ('10 PAPER 0', '20 LOCATE 1,15', '30 PRINT "J119OLD"',
                '40 PAPER 2', '50 LOCATE 1,16', '60 PRINT "J119NEW"', '70 END'),
    'SCLS': ('10 PAPER 3', '20 CLS', '30 LOCATE 1,15', '40 PRINT "J119TEST"', '50 END'),
    'SINK': ('10 INK 2,6', '20 PEN 1', '30 PAPER 2', '40 LOCATE 1,15',
             '50 PRINT "J119TEST"', '60 END'),
}
CASES = tuple(BASIC) + tuple(SCENARIOS)
GHCR = ('ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:'
        '7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c')
ROM_SHA256 = '31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562'
CAPRICE_COMMIT = '8c778bf072a06fb7c23b9cccd179041db7f79a52'
# SEALED VALUES MUST COME FROM AN INDEPENDENT REAL ACTIONS ACQUISITION,
# fixed outside manifest, checked against the original external artifact.
# Never compute these from the current directory being verified.
SEALED_MANIFEST_SHA256 = None
SEALED_ACQUISITION_PARENT = None
SEALED_FILE_SHA256 = {}
PRINT_LABEL = 'J119TEST'
SETUP = ('MODE 1', 'INK 0,0', 'INK 1,26', 'INK 2,6', 'INK 3,18',
         'PAPER 0', 'PEN 1', 'CLS', 'NEW')
PNG_PATHS = ('list/screen.png', 'baseline/screen.png', 'run/screen.png')
CASE_FILES = ('program.bin', 'capture.json', 'list/screen.png', 'list/caprice.log',
              'list/printer.dat', 'baseline/screen.png', 'baseline/caprice.log',
              'run/screen.png', 'run/caprice.log', 'run/printer.dat')
CHRON_FILES = ('capture.json', 'caprice.log', 'screen_0.png', 'screen_1.png')
DIRECT_CASES = {'D16':'PAPER 16', 'DN1':'PAPER -1'}
DIRECT_FILES = ('capture.json', 'caprice.log', 'screen.png', 'printer.dat')
ROI = (64, 305, 190, 321)  # prior INK oracle glyph location; still empirical here
ROI_SECOND_ROW = (64, 321, 190, 337)  # separate evidence for text printed after PAPER change
ROI_BLANK = (210, 180, 260, 200)  # screen area away from controlled glyph (CLS/background)


class Invalid(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise Invalid(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode('ascii')


def source(case):
    return (SOURCES / (case + '.bas')).read_bytes()


def expected_source(case):
    if case in BASIC:
        lines = (f'10 REM J119-{case}', f'20 PAPER {BASIC[case]}',
                 '30 LOCATE 1,15', f'40 PRINT "{PRINT_LABEL}"', '50 END')
    else:
        lines = SCENARIOS[case]
    return ('\n'.join(lines) + '\n').encode('ascii')


def check_sources():
    need(set(p.name for p in SOURCES.glob('*.bas')) == {x + '.bas' for x in CASES},
         'SOURCE_INVENTORY')
    for case in CASES:
        need(source(case) == expected_source(case), 'SOURCE_CHANGED_' + case)
    return True


def require_git_head(head):
    need(re.fullmatch(r'[0-9a-f]{40}', head) is not None, 'HEAD_SYNTAX')
    actual = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    need(actual == head, 'FALSE_HEAD')
    return head


def is_ancestor(head):
    return subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor',
                           head, 'HEAD'], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def prior_tools():
    """Only acquisition/verification imports prior unmodified, pinned CPC readers."""
    sys.path.insert(0, str(ROOT / 'tools'))
    import j1_18_a_ink_evidence as ink  # original ROM acquisition primitives
    import j1_18_a_ink_pixels as pixels  # independently CRC-checked PNG decoder
    return ink, pixels


def file_map():
    paths = {}
    for session in SESSIONS:
        for case in CASES:
            for name in CASE_FILES:
                rel = f'{session}/{case}/{name}'
                paths[rel] = None
        for name in CHRON_FILES:
            paths[f'{session}/chronology/{name}'] = None
        for case in DIRECT_CASES:
            for name in DIRECT_FILES:
                paths[f'{session}/direct/{case}/{name}'] = None
    return paths


def histogram(rows, roi):
    x0,y0,x1,y1 = roi
    need(len(rows) >= y1 and 0 <= x0 < x1 <= 768 and 0 <= y0 < y1 <= 540, 'ROI_RANGE')
    colors = {}
    for y in range(y0, y1):
        for x in range(x0, x1):
            rgb = ','.join(str(v) for v in rows[y][x*3:x*3+3])
            colors[rgb] = colors.get(rgb, 0) + 1
    need(sum(colors.values()) == (x1-x0)*(y1-y0), 'ROI_COUNT')
    return colors


def capture_case(cap, out, session, case, tmp, ink, pixels):
    work = out/session/case
    raw_lines = source(case).decode('ascii').splitlines()
    _, _, _, _ = session, case, ink, pixels
    lsnap = tmp / (session + '-' + case)
    lsnap.mkdir()
    # Pre-RUN genuine ROM LIST screenshot + snapshot + independent printer LIST.
    cl = list(SETUP) + raw_lines + ['LIST',
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT',
        'LIST #8', 'CAP32_DELAY CAP32_EXIT']
    lt = ink.launch(cap, work/'list', lsnap, cl, True)
    snaps = list(lsnap.glob('*.sna'))
    need(len(snaps) == 1, 'PRE_RUN_SNA_' + case)
    prog,region = ink.cpc.extract_snapshot(snaps[0].read_bytes(),
                  [int(x.split(' ',1)[0]) for x in raw_lines])
    nums, records = ink.cpc.records(prog)
    need(len(records) == len(raw_lines), 'RAM_RECORD_COUNT_' + case)
    (work/'program.bin').write_bytes(prog)
    list_raw = (work/'list/printer.dat').read_bytes()
    need(bool(list_raw), 'LIST_PRINTER_EMPTY_' + case)
    # Baseline text control in a new emulator process; no PAPER case executed.
    baseline = list(SETUP) + ['LOCATE 1,15', f'PRINT "{PRINT_LABEL}"',
                              'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT']
    bt = ink.launch(cap, work/'baseline', tmp, baseline, False)
    # RUN error screenshot is captured *before* ERR/ERL printer reads.
    cr = list(SETUP) + raw_lines + ['RUN',
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
        'PRINT #8,ERR', 'PRINT #8,ERL', 'CAP32_DELAY CAP32_EXIT']
    rt = ink.launch(cap, work/'run', tmp, cr, True)
    printer = (work/'run/printer.dat').read_bytes()
    parsed = [ink.parse_integer(v) for v in printer.splitlines(keepends=True)]
    need(len(parsed) == 2 and all(v is not None for v in parsed), 'ERR_ERL_CAPTURE_' + case)
    err,erl = (v['numeric_value'] for v in parsed)
    # Runtime observed statuses only. No textual error is inferred from ERR/ERL.
    visual = {}
    for name in PNG_PATHS:
        rows = pixels.png_rgb(work/name)
        visual[name] = {'sha256': digest((work/name).read_bytes()),
                        'roi': list(ROI), 'rgb_histogram': histogram(rows, ROI),
                        'blank_roi':list(ROI_BLANK),'blank_rgb_histogram':histogram(rows,ROI_BLANK)}
    row_hex = {str(n): prog[r['offset']:r['offset']+r['length']].hex(' ').upper()
               for n,r in zip(nums,records)}
    d = {'case':case,'session':session,'phase':PHASE,'source_sha256':digest(source(case)),
         'program_sha256':digest(prog),'program_hex':prog.hex(' ').upper(),
         'lines':nums,'ram_lines_hex':row_hex,'region':region,
         'setup':list(SETUP),'commands':{'list':cl,'baseline':baseline,'run':cr},
         'metadata':{'list':lt,'baseline':bt,'run':rt},
         'err':err,'erl':erl,'printer_hex':printer.hex(),
         'list_printer_hex':list_raw.hex(),
         'diagnostic_text':'DIAG_CPC_UNVERIFIED',
         'visual':visual,'visual_classification':'VISUAL_UNVERIFIED',
         'source_kind':'CPC6128_CAPRICE32_REAL_ACQUISITION'}
    (work/'capture.json').write_bytes(canonical(d))
    return d


def capture_chronology(cap, out, session, tmp, ink, pixels):
    """Extra in-process two-frame chronology, 2 fresh sessions, not a substitute for 12 cases."""
    dest = out/session/'chronology'
    cmds = list(SETUP) + ['LOCATE 1,15','PRINT "J119OLD"',
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
        'PAPER 2', 'LOCATE 1,16','PRINT "J119NEW"',
        ink.CHRONO_DELAY + ' CAP32_SCRNSHOT CAP32_EXIT']
    meta = ink.launch(cap,dest,tmp,cmds,False,shots=2)
    observations = {}
    for n in (0,1):
        img = dest/f'screen_{n}.png'
        observations[str(n)] = {'sha256':digest(img.read_bytes()),
                                  'roi':list(ROI),
                                  'rgb_histogram':histogram(pixels.png_rgb(img),ROI),
                                  'second_roi':list(ROI_SECOND_ROW),
                                  'second_rgb_histogram':histogram(pixels.png_rgb(img),ROI_SECOND_ROW)}
    (dest/'capture.json').write_bytes(canonical({'session':session,'commands':cmds,
        'phase':PHASE,'caprice':meta,'visual':observations,
        'visual_classification':'VISUAL_UNVERIFIED',
        'intervening_print':True,'source_kind':'CPC6128_CAPRICE32_REAL_ACQUISITION'}))



def capture_direct(cap, out, session, case, tmp, ink, pixels):
    """Supplementary direct-mode candidate, not a numbered-program oracle."""
    dest = out/session/'direct'/case
    cmds = list(SETUP) + [DIRECT_CASES[case],
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
        'PRINT #8,ERR', 'PRINT #8,ERL', 'CAP32_DELAY CAP32_EXIT']
    metadata = ink.launch(cap,dest,tmp,cmds,True)
    raw = (dest/'printer.dat').read_bytes()
    values = [ink.parse_integer(x) for x in raw.splitlines(keepends=True)]
    need(len(values)==2 and all(x is not None for x in values), 'DIRECT_ERR_ERL_'+case)
    img=dest/'screen.png'
    (dest/'capture.json').write_bytes(canonical({
        'session':session,'case':case,'phase':PHASE,'statement':DIRECT_CASES[case],
        'commands':cmds,'caprice':metadata,'source_kind':'CPC6128_CAPRICE32_REAL_ACQUISITION',
        'err':values[0]['numeric_value'],'erl':values[1]['numeric_value'],
        'printer_hex':raw.hex(),'diagnostic_text':'DIAG_CPC_UNVERIFIED',
        'visual':{'sha256':digest(img.read_bytes()),'roi':list(ROI),
                  'rgb_histogram':histogram(pixels.png_rgb(img),ROI),
                                  'second_roi':list(ROI_SECOND_ROW),
                                  'second_rgb_histogram':histogram(pixels.png_rgb(img),ROI_SECOND_ROW)}}))


def acquire(cap, output, head):
    need(not output.exists(), 'OUTPUT_ALREADY_EXISTS')
    require_git_head(head)
    check_sources()
    ink,pixels = prior_tools()
    version = ink.check_caprice(cap)
    need(ink.cpc.ROM_SHA == ROM_SHA256 and ink.cpc.PIN == CAPRICE_COMMIT,
         'ORACLE_ROM_OR_CAPRICE_DRIFT')
    # Temporary inputs never archived: only program.bin from real CPC SNA.
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='j119-paper-sna-') as tmp:
        for session in SESSIONS:
            for case in CASES:
                d=capture_case(cap,output,session,case,Path(tmp),ink,pixels)
                print(PHASE,case,session,'RAM',d['ram_lines_hex'],'ERR',d['err'],
                      'ERL',d['erl'],flush=True)
            capture_chronology(cap,output,session,Path(tmp),ink,pixels)
            for case in DIRECT_CASES:
                capture_direct(cap,output,session,case,Path(tmp),ink,pixels)
    hashes = {name:digest((output/name).read_bytes()) for name in file_map()}
    m = {'schema_version':1,'phase':PHASE,'acquisition_head':head,
         'origin':'CAPRICE32_REAL_ONLY',
         'run_id':os.environ.get('GITHUB_RUN_ID','LOCAL'),
         'oracle':{'rom_sha256':ROM_SHA256,'caprice_commit':CAPRICE_COMMIT,
                   'ghcr':GHCR,'model':'CPC6128','basic':'1.1','version':version},
         'cases':list(CASES),'sessions':list(SESSIONS),'files':hashes,
         'diagnostic_text':'DIAG_CPC_UNVERIFIED',
         'visual_classification':'VISUAL_UNVERIFIED',
         'full_snapshots_archived':False,'native_changes':False}
    (output/'manifest.json').write_bytes(canonical(m))
    verify(output, permanent=False)
    print(PHASE,'FRESH_ACQUISITION_UNSEALED',len(CASES)*2, 'sessions',flush=True)


def verify(root, permanent=False):
    need((root/'manifest.json').is_file(), 'ARCHIVE_ABSENT')
    m = json.loads((root/'manifest.json').read_bytes())
    need(m.get('schema_version') == 1 and m.get('phase') == PHASE and
         m.get('origin') == 'CAPRICE32_REAL_ONLY' and
         m.get('cases') == list(CASES) and m.get('sessions') == list(SESSIONS) and
         m.get('full_snapshots_archived') is False and m.get('native_changes') is False and
         m.get('oracle',{}).get('rom_sha256') == ROM_SHA256 and
         m.get('oracle',{}).get('caprice_commit') == CAPRICE_COMMIT and
         m.get('oracle',{}).get('ghcr') == GHCR, 'MANIFEST_PROVENANCE')
    head=m.get('acquisition_head','')
    need(re.fullmatch(r'[0-9a-f]{40}',head) is not None and is_ancestor(head),
         'FALSE_HEAD_OR_ANCESTRY')
    expected=set(file_map())
    seen={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    need(seen == expected | {'manifest.json'}, 'FILE_INVENTORY')
    need(set(m.get('files',{})) == expected, 'MANIFEST_FILES')
    if permanent:
        need(bool(re.fullmatch(r'[a-f0-9]{64}',SEALED_MANIFEST_SHA256 or '')) and
             bool(re.fullmatch(r'[a-f0-9]{40}',SEALED_ACQUISITION_PARENT or '')) and
             bool(SEALED_FILE_SHA256) and set(SEALED_FILE_SHA256) == expected,
             'EXTERNAL_SEAL_NOT_ACQUIRED')
        need(head == SEALED_ACQUISITION_PARENT and
             digest((root/'manifest.json').read_bytes()) == SEALED_MANIFEST_SHA256,
             'FALSE_SEALED_HEAD_OR_MANIFEST')
    for name in sorted(expected):
        raw=(root/name).read_bytes()
        need(digest(raw) == m['files'][name], 'SHA_'+name)
        if permanent:
            need(digest(raw)==SEALED_FILE_SHA256[name], 'EXTERNAL_SHA_'+name)
    ink,pixels=prior_tools()
    records={}
    directs={}
    chronologies={}
    for session in SESSIONS:
        for case in CASES:
            base=root/session/case
            d=json.loads((base/'capture.json').read_bytes())
            need(d.get('case')==case and d.get('session')==session and
                 d.get('phase')==PHASE and d.get('setup')==list(SETUP) and
                 d.get('source_kind')=='CPC6128_CAPRICE32_REAL_ACQUISITION' and
                 d.get('source_sha256')==digest(source(case)) and
                 d.get('commands',{}).get('list') == list(SETUP)+source(case).decode('ascii').splitlines()+['LIST', 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT', 'LIST #8','CAP32_DELAY CAP32_EXIT'] and
                 d.get('commands',{}).get('run') == list(SETUP)+source(case).decode('ascii').splitlines()+['RUN','CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT','PRINT #8,ERR','PRINT #8,ERL','CAP32_DELAY CAP32_EXIT'] and
                 d.get('diagnostic_text')=='DIAG_CPC_UNVERIFIED',
                 'CAPTURE_PROVENANCE_'+case+session)
            raw=(base/'program.bin').read_bytes()
            nums,rows=ink.cpc.records(raw)
            need(d.get('program_sha256')==digest(raw) and
                 d.get('program_hex')==raw.hex(' ').upper() and
                 d.get('lines')==nums and
                 d.get('ram_lines_hex') == {str(n):raw[r['offset']:r['offset']+r['length']].hex(' ').upper()
                              for n,r in zip(nums,rows)} and
                 nums==[int(line.split(' ',1)[0]) for line in source(case).decode().splitlines()],
                 'RAM_OR_LIST_'+case+session)
            for png_name in PNG_PATHS:
                png=base/png_name
                pic=pixels.png_rgb(png)
                need(d['visual'][png_name]['sha256']==digest(png.read_bytes()) and
                     d['visual'][png_name]['rgb_histogram']==histogram(pic,ROI) and
                     d['visual'][png_name]['blank_rgb_histogram']==histogram(pic,ROI_BLANK),
                     'PNG_CRC_OR_ROI_'+case+session+png_name)
            expect_printer=(base/'run/printer.dat').read_bytes()
            parsed=[ink.parse_integer(v) for v in expect_printer.splitlines(keepends=True)]
            need(len(parsed)==2 and all(v is not None for v in parsed) and
                 d.get('printer_hex')==expect_printer.hex() and
                 (d['err'],d['erl']) == tuple(v['numeric_value'] for v in parsed) and
                 d.get('list_printer_hex')==(base/'list/printer.dat').read_bytes().hex(),
                 'ERR_ERL_OR_LIST_'+case+session)
            records[(case,session)]=d
        for case in DIRECT_CASES:
            direct=root/session/'direct'/case
            d=json.loads((direct/'capture.json').read_bytes())
            raw=(direct/'printer.dat').read_bytes()
            parsed=[ink.parse_integer(x) for x in raw.splitlines(keepends=True)]
            need(len(parsed)==2 and all(x is not None for x in parsed) and
                 d.get('session')==session and d.get('statement')==DIRECT_CASES[case] and
                 d.get('commands')==list(SETUP)+[DIRECT_CASES[case],
                 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                 'PRINT #8,ERR','PRINT #8,ERL','CAP32_DELAY CAP32_EXIT'] and
                 d.get('source_kind')=='CPC6128_CAPRICE32_REAL_ACQUISITION' and
                 d.get('printer_hex')==raw.hex() and
                 (d.get('err'),d.get('erl'))==tuple(x['numeric_value'] for x in parsed) and
                 d.get('diagnostic_text')=='DIAG_CPC_UNVERIFIED', 'DIRECT_PROVENANCE_'+case)
            directs[(case,session)]=d
            png=direct/'screen.png'
            need(d['visual']['sha256']==digest(png.read_bytes()) and
                 d['visual']['rgb_histogram']==histogram(pixels.png_rgb(png),ROI),
                 'DIRECT_PNG_CRC_OR_ROI_'+case)
        chronology=root/session/'chronology'
        ch=json.loads((chronology/'capture.json').read_bytes())
        chronologies[session]=ch
        need(ch.get('phase')==PHASE and ch.get('session')==session and
             ch.get('source_kind')=='CPC6128_CAPRICE32_REAL_ACQUISITION' and
             ch.get('intervening_print') is True, 'CHRONO_PROVENANCE')
        for n in (0,1):
            p=chronology/f'screen_{n}.png'
            need(ch['visual'][str(n)]['sha256']==digest(p.read_bytes()) and
                 ch['visual'][str(n)]['rgb_histogram']==histogram(pixels.png_rgb(p),ROI) and
                 ch['visual'][str(n)]['second_rgb_histogram']==histogram(pixels.png_rgb(p),ROI_SECOND_ROW),
                 'CHRONO_PNG_CRC_OR_ROI')
    for case in CASES:
        a,b=(records[(case,s)] for s in SESSIONS)
        need(a['program_hex']==b['program_hex'] and
             (a['err'],a['erl'])==(b['err'],b['erl']) and
             a['list_printer_hex']==b['list_printer_hex'] and
             a['metadata']['list']['started_utc'] != b['metadata']['list']['started_utc'] and
             a['metadata']['run']['started_utc'] != b['metadata']['run']['started_utc'],
             'INDEPENDENT_MISMATCH_'+case)
        for name in ('run/screen.png','baseline/screen.png'):
            need(a['visual'][name]['rgb_histogram'] == b['visual'][name]['rgb_histogram'] and
                 a['visual'][name]['blank_rgb_histogram'] == b['visual'][name]['blank_rgb_histogram'],
                 'INDEPENDENT_RGB_MISMATCH_'+case+name)
    for case in DIRECT_CASES:
        a,b=(directs[(case,s)] for s in SESSIONS)
        need((a['err'],a['erl'])==(b['err'],b['erl']) and
             a['visual']['rgb_histogram']==b['visual']['rgb_histogram'],
             'INDEPENDENT_DIRECT_MISMATCH_'+case)
    for n in ('0','1'):
        need(chronologies['original']['visual'][n]['rgb_histogram'] ==
             chronologies['repeat']['visual'][n]['rgb_histogram'] and
             chronologies['original']['visual'][n]['second_rgb_histogram'] ==
             chronologies['repeat']['visual'][n]['second_rgb_histogram'],
             'INDEPENDENT_CHRONO_RGB_MISMATCH_'+n)
    return {'source':'CPC6128_CAPRICE32_REAL_ONLY','cases':len(CASES),
            'sessions':len(CASES)*2,'seal':'EXTERNAL_SEALED' if permanent else 'UNSEALED'}


def self_test():
    """Negative controls are deliberately synthetic and NEVER an oracle PASS."""
    import unittest
    class ContractTests(unittest.TestCase):
        def test_inventory(self):
            self.assertEqual(len(CASES),12)
            self.assertEqual(len(file_map()),12*2*len(CASE_FILES)+2*len(CHRON_FILES)+2*len(DIRECT_CASES)*len(DIRECT_FILES))
            self.assertTrue(check_sources())
        def test_no_archive(self):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(Invalid,'ARCHIVE_ABSENT'):
                    verify(Path(tmp),permanent=True)
        def test_no_auto_seal(self):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'manifest.json';p.write_text('{}')
                with self.assertRaisesRegex(Invalid,'MANIFEST_PROVENANCE'):
                    verify(Path(tmp),permanent=True)
        def test_false_head(self):
            with self.assertRaisesRegex(Invalid,'HEAD_SYNTAX'):
                require_git_head('abcdef')
        def test_corrupt_source(self):
            self.assertEqual(expected_source('P16').splitlines()[1],b'20 PAPER 16')
            self.assertEqual(expected_source('PN1').splitlines()[1],b'20 PAPER -1')
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests)
    results=unittest.TextTestRunner(verbosity=1).run(suite)
    need(results.wasSuccessful(), 'OFFLINE_SELF_TEST_FAILURE')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-sources', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--acquire',type=Path, help='pinned Caprice32 directory (contains cap32, cfg, ROM)')
    parser.add_argument('--output',type=Path,help='new archive destination, must not exist')
    parser.add_argument('--head', help='full exact checkout commit SHA')
    parser.add_argument('--evidence',type=Path)
    parser.add_argument('--permanent',action='store_true')
    args=parser.parse_args()
    need(any((args.check_sources,args.self_test,args.acquire,args.evidence)), 'NO_OPERATION')
    if args.check_sources or args.self_test or args.acquire:
        check_sources()
    if args.self_test:
        self_test()
    if args.acquire:
        need(args.output is not None and args.head is not None and not args.evidence, 'ACQUIRE_ARGS')
        acquire(args.acquire.resolve(),args.output.resolve(),args.head)
    if args.evidence:
        result=verify(args.evidence.resolve(),args.permanent)
        print('J1.19-A ARCHIVE_VERIFIED',result)
    else:
        need(not args.permanent,'PERMANENT_WITHOUT_ARCHIVE')

if __name__=='__main__':
    try:
        main()
    except (Invalid,OSError,ValueError,KeyError,IndexError,subprocess.SubprocessError,
            UnicodeError,json.JSONDecodeError,ImportError) as error:
        print('J1.19-A FAIL',error,file=sys.stderr)
        sys.exit(1)
