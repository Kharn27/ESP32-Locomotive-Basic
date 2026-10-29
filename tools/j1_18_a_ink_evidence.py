#!/usr/bin/env python3
"""J1.18-A CPC6128 INK oracle, no C99/firmware implementation.

The Caprice32 processes are genuinely independent; SNA files are transient.
Permanent SHA pins are added outside the archive AFTER the first CPC acquisition.
Unsealed archives and static-ROM predictions never become CPC_ORACLE_VERIFIED.
"""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests/oracles'))
import token_ram_oracle as cpc
from signed_print_oracle import parse_integer

PHASE = 'J1.18-A'
SOURCES = ROOT / 'tests/oracles/inputs/j1_18_a'
CASES = {
    'I00': '0,0', 'I126': '1,26', 'I106': '1,6',
    'I206': '2,6', 'I318': '3,18', 'I1526': '15,26',
    'I127': '1,27', 'I131': '1,31', 'I1266': '1,26,6',
    'I1626': '16,26', 'IN126': '-1,26',
    'I132': '1,32', 'I1N1': '1,-1'
}
SESSIONS = ('original', 'repeat')
LINES = [10, 20, 30, 40]
GHCR = 'ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c'
# I00 starts on red ink-0 so its black-background change is observable.
# All other cases begin black background, white foreground, MODE 1.
def setup(case):
    return ['MODE 1', 'INK 0,' + ('6' if case == 'I00' else '0'),
            'INK 1,26', 'INK 2,6', 'INK 3,18',
            'PAPER 0', 'PEN 1', 'CLS', 'NEW']
# Caprice screenshot filenames are wall-clock-second based. Space the two
# within-process captures by enough real execution time to prevent overwrite.
CHRONO_DELAY = ' '.join(['CAP32_DELAY'] * 96)
CHRONO = ['MODE 1', 'INK 0,0', 'INK 1,26', 'INK 2,6', 'INK 3,18',
          'PAPER 0', 'PEN 1', 'CLS', 'NEW']
# Extract independently from the FIRST authentic GitHub acquisition and pin
# its actual archive byte hashes here. Never derive these from manifest.json.
# Historic J1.17-A pins are *not* INK evidence. INK SHA are separate.
# Acquired external SHA-256 pins MUST be filled in only after a real
# Caprice32 Actions acquisition has archived its independently produced files.
# Never generate these pins from a suspect archive being verified.
SEALED = {}
SEALED_MANIFEST = ''
SEALED_CHRONO = {}



class Invalid(ValueError):
    pass


def require(test, code):
    if not test:
        raise Invalid(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink(), 'MISSING_OR_SYMLINK_' + str(path))
    return path.read_bytes()


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, indent=2) + '\n').encode('ascii')


def source(case):
    require(case in CASES, 'UNKNOWN_CASE')
    expected = (f'10 INK {CASES[case]}\n20 LOCATE 1,15\n'
                '30 PRINT "J118INK"\n40 END\n').encode('ascii')
    require(read(SOURCES / (case.lower() + '.bas')) == expected,
            'SOURCE_DRIFT_' + case)
    return expected


def check_head(expected):
    require(bool(re.fullmatch(r'[0-9a-f]{40}', expected)), 'INVALID_EXPECTED_HEAD')
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                   text=True).strip()
    require(head == expected, 'EXPECTED_HEAD_MISMATCH expected=' + expected + ' actual=' + head)
    return head


def check_caprice(cap):
    require(subprocess.check_output(['git', '-C', str(cap), 'rev-parse', 'HEAD'],
                                    text=True).strip() == cpc.PIN, 'CAPRICE_PIN_MISMATCH')
    require(sha(read(cap / 'rom/cpc6128.rom')) == cpc.ROM_SHA, 'ROM_SHA_MISMATCH')
    require((cap / 'cap32').is_file(), 'CAPRICE_EXECUTABLE_MISSING')
    return subprocess.check_output([str(cap / 'cap32'), '--version'],
                                   cwd=cap, text=True).strip()


def launch(cap, dest, snadir, commands, printer, shots=1):
    dest.mkdir(parents=True, exist_ok=False)
    cfg = configparser.ConfigParser(interpolation=None)
    require(bool(cfg.read(cap / 'cap32.cfg')), 'CAPRICE_CONFIG_MISSING')
    cfg['system'].update(model='2', ram_size='128', speed='4', auto_pause='0',
                         printer='1' if printer else '0', mf2='0', keyboard='0',
                         boot_time='42', limit_speed='0', resources_path=str(cap / 'resources'))
    cfg['control']['kbd_layout'] = '0'
    cfg['sound']['enabled'] = '0'
    cfg['video'].update(scr_style='1', scr_window='1')
    cfg['file']['printer_file'] = str(dest / 'printer.dat')
    cfg['file']['snap_path'] = str(snadir)
    cfg['file']['sdump_dir'] = str(dest)
    cfg['rom']['rom_path'] = str(cap / 'rom')
    cfg['rom']['slot07'] = 'amsdos.rom'
    cfg['rom']['rom_mf2'] = ''
    config = dest / 'cap32.cfg'
    with config.open('w', encoding='utf-8') as f:
        cfg.write(f, space_around_delimiters=False)
    argv = ['xvfb-run', '-a', str(cap / 'cap32'), '-c', str(config)]
    for command in commands:
        argv.extend(['-a', command.replace('CAP32_SNAPSHOT', '\x0c\x0d')])
    start = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(argv, cwd=cap,
                            env=dict(os.environ, SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='x11'),
                            capture_output=True, timeout=90, check=False)
    stop = datetime.now(timezone.utc).isoformat()
    (dest / 'caprice.log').write_bytes(b'exit code: ' + str(result.returncode).encode()
                                      + b'\n' + result.stdout + b'\n[stderr]\n' + result.stderr)
    config.unlink()
    require(result.returncode == 0, 'CAPRICE_EXECUTION_ERROR_' + repr(result.stderr[-400:]))
    pics = list(dest.glob('screenshot_*.png'))
    require(len(pics) == shots and all(read(p).startswith(b'\x89PNG\r\n\x1a\n')
                                       for p in pics), 'PNG_COUNT_OR_SIGNATURE_INVALID')
    pics = sorted(pics)
    for i, src in enumerate(pics):
        src.rename(dest / ('screen.png' if shots == 1 else f'screen_{i}.png'))
    data = read(dest / ('screen.png' if shots == 1 else 'screen_0.png'))
    require(len(data) >= 80 and data[12:16] == b'IHDR', 'PNG_MISSING_IHDR')
    w = int.from_bytes(data[16:20], 'big')
    h = int.from_bytes(data[20:24], 'big')
    require(300 <= w <= 2000 and 200 <= h <= 1500, 'PNG_UNEXPECTED_DIMENSIONS')
    return {'started_utc': start, 'finished_utc': stop,
            'commands': commands, 'screenshot_width': w, 'screenshot_height': h}


def capture_one(cap, out, case, session, tmp):
    src = source(case)
    work = out / session / case
    ldir, rdir, bdir = work / 'list', work / 'run', work / 'baseline'
    lsnap = tmp / (case + '_' + session)
    lsnap.mkdir()
    raw_lines = src.decode('ascii').splitlines()
    cmd_list = setup(case) + raw_lines + [
        'LIST', 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT']
    lt = launch(cap, ldir, lsnap, cmd_list, False)
    snapshots = list(lsnap.glob('*.sna'))
    require(len(snapshots) == 1, 'LIST_SNAPSHOT_MISSING')
    program, region = cpc.extract_snapshot(read(snapshots[0]), LINES)
    nums, rows = cpc.records(program)
    first = program[rows[0]['offset']:rows[0]['offset'] + rows[0]['length']]
    require(first[4] == 0xa2, 'CPC_INK_OPCODE_NOT_A2')
    (work / 'program.bin').write_bytes(program)

    # A genuine baseline glyph before INK; does not infer any RGB from #8.
    cmd_baseline = setup(case) + ['LOCATE 1,15', 'PRINT "J118INK"',
                                 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT']
    bt = launch(cap, bdir, tmp, cmd_baseline, False)
    cmd_run = setup(case) + raw_lines + ['RUN',
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
        'PRINT #8,ERR', 'PRINT #8,ERL', 'CAP32_DELAY CAP32_EXIT']
    rt = launch(cap, rdir, tmp, cmd_run, True)
    raw = read(rdir / 'printer.dat')
    require(0 < len(raw) <= 256, 'ERR_ERL_PRINTER_MISSING')
    parsed = [parse_integer(row) for row in raw.splitlines(keepends=True)]
    require(len(parsed) == 2 and all(p is not None for p in parsed),
            'ERR_ERL_NOT_TWO_NUMBERS')
    err, erl = (p['numeric_value'] for p in parsed)
    rec = {
        'case':case, 'session':session, 'source_sha256':sha(src),
        'program_sha256':sha(program), 'program_hex':program.hex(' ').upper(),
        'ink_record_hex':first.hex(' ').upper(), 'ink_opcode_observed':first[4],
        'region':region, 'line_numbers':nums, 'setup_mode':1,
        'setup_commands':setup(case), 'paper':0, 'pen':1,
        'print_location': {'column':1,'row':15,'text':'J118INK'},
        'list':lt, 'baseline':bt, 'run':rt, 'err':err,'erl':erl,
        'run_kind':'ERROR' if err else 'NO_ERROR',
        'printer_sha256':sha(raw),
        'list_png_sha256':sha(read(ldir/'screen.png')),
        'baseline_png_sha256':sha(read(bdir/'screen.png')),
        'run_png_sha256':sha(read(rdir/'screen.png')),
        'list_log_sha256':sha(read(ldir/'caprice.log')),
        'baseline_log_sha256':sha(read(bdir/'caprice.log')),
        'run_log_sha256':sha(read(rdir/'caprice.log')),
        'visual_classification':'VISUAL_UNVERIFIED',
        'temporal_classification':('TEMPORAL_UNVERIFIED' if case == 'I1266' else 'NOT_APPLICABLE'),
        'screen_is_not_token_evidence':True,'printer_is_not_color_evidence':True,
    }
    (work/'capture.json').write_bytes(encoded(rec))
    return rec


def capture_chronology(cap, out, session, tmp):
    # Same physical Caprice32 process: initial red text, then INK 1,26.
    # No PRINT between two screenshots. Two separate processes for original/repeat.
    dest = out/session/'chronology'
    cmds = CHRONO + ['INK 1,6', 'LOCATE 1,15', 'PRINT "J118INK"',
                    'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                    'INK 1,26',
                    CHRONO_DELAY + ' CAP32_SCRNSHOT CAP32_EXIT']
    chron = launch(cap,dest,tmp,cmds,False,shots=2)
    r = {'session':session,'commands':cmds,'caprice':chron,
         'before_sha256':sha(read(dest/'screen_0.png')),
         'after_sha256':sha(read(dest/'screen_1.png')),
         'no_intervening_print':True,'visual_classification':'VISUAL_UNVERIFIED'}
    (dest/'capture.json').write_bytes(encoded(r))
    return r


def acquire(cap, out, head):
    require(not out.exists(), 'EVIDENCE_OUTPUT_EXISTS')
    version = check_caprice(cap)
    out.mkdir(parents=True)
    manifest = {'schema_version':1,'phase':PHASE,'acquisition_head':head,
                'run_id':os.environ.get('GITHUB_RUN_ID','LOCAL'),
                'oracle':{'caprice':cpc.PIN,'rom':cpc.ROM_SHA,'ghcr':GHCR,
                          'version':version,'model':'CPC6128','basic':'1.1'},
                'full_snapshots_archived':False,'native_changes':False,
                'cases':{}, 'chronology':{},
                'visual_classification':'VISUAL_UNVERIFIED',
                'temporal_classification':'TEMPORAL_UNVERIFIED'}
    with tempfile.TemporaryDirectory(prefix='j118-ink-sna-') as tmp:
        t=Path(tmp)
        for case in CASES:
            seen={}
            for session in SESSIONS:
                seen[session]=capture_one(cap,out,case,session,t)
                print(PHASE,case,session,'RECORD',seen[session]['ink_record_hex'],
                      'ERR',seen[session]['err'],'ERL',seen[session]['erl'],flush=True)
            require(seen['original']['program_hex']==seen['repeat']['program_hex'],
                    'INDEINKDENT_RAM_MISMATCH_'+case)
            require((seen['original']['err'],seen['original']['erl'])==
                    (seen['repeat']['err'],seen['repeat']['erl']),
                    'INDEINKDENT_ERR_ERL_MISMATCH_'+case)
            manifest['cases'][case]={x:sha(read(out/x/case/'capture.json'))
                                      for x in SESSIONS}
        for session in SESSIONS:
            chron=capture_chronology(cap,out,session,t)
            manifest['chronology'][session]=sha(read(out/session/'chronology/capture.json'))
            print(PHASE,'CHRONOLOGY',session,chron['before_sha256'],
                  chron['after_sha256'],flush=True)
    (out/'manifest.json').write_bytes(encoded(manifest))
    verify(out)
    print(PHASE,'CPC_ACQUIRED',len(CASES)*2,
          'CASE_SESSIONS_PLUS_2_CHRONOLOGY HEAD',head,flush=True)


def verify(out, permanent=False):
    m=json.loads(read(out/'manifest.json'))
    require(m['phase']==PHASE and m['schema_version']==1 and
            bool(re.fullmatch(r'[0-9a-f]{40}',m['acquisition_head'])) and
            m['oracle']['caprice']==cpc.PIN and m['oracle']['rom']==cpc.ROM_SHA and
            m['oracle']['ghcr']==GHCR and m['oracle']['model']=='CPC6128' and
            m['native_changes'] is False and m['full_snapshots_archived'] is False and
            m['visual_classification']=='VISUAL_UNVERIFIED' and
            m['temporal_classification']=='TEMPORAL_UNVERIFIED' and
            set(m['cases'])==set(CASES) and set(m['chronology'])==set(SESSIONS),
            'MANIFEST_PROVENANCE')
    anc=subprocess.run(['git','-C',str(ROOT),'merge-base','--is-ancestor',
                        m['acquisition_head'],'HEAD'],stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
    require(anc.returncode==0,'FALSE_OR_UNREACHABLE_ACQUISITION_HEAD')
    if permanent:
        require(bool(re.fullmatch(r'[a-f0-9]{64}',SEALED_MANIFEST)) and
                sha(read(out/'manifest.json'))==SEALED_MANIFEST,
                'EXTERNAL_MANIFEST_SEAL')
        require(bool(SEALED) and set(SEALED)=={str(p.relative_to(out))
            for p in out.rglob('*') if p.is_file() and p.name != 'manifest.json'},
            'EXTERNAL_ARCHIVE_FILE_INVENTORY')
        for name,expected in SEALED.items():
            require(sha(read(out/name))==expected,'EXTERNAL_SHA_'+name)
    records={}
    for case in CASES:
        seen=[]
        for session in SESSIONS:
            work=out/session/case
            files={
                'program':read(work/'program.bin'),
                'capture':read(work/'capture.json'),
                'printer':read(work/'run/printer.dat'),
                'list_png':read(work/'list/screen.png'),
                'run_png':read(work/'run/screen.png'),
                'baseline_png':read(work/'baseline/screen.png'),
                'list_log':read(work/'list/caprice.log'),
                'run_log':read(work/'run/caprice.log'),
                'baseline_log':read(work/'baseline/caprice.log')}
            d=json.loads(files['capture'])
            require(sha(files['capture'])==m['cases'][case][session] and
                    d['source_sha256']==sha(source(case)) and
                    d['program_sha256']==sha(files['program']) and
                    d['program_hex']==files['program'].hex(' ').upper() and
                    d['case']==case and d['session']==session and
                    d['line_numbers']==LINES and d['setup_commands']==setup(case) and
                    d['paper']==0 and d['pen']==1 and d['setup_mode']==1 and
                    d['print_location']=={'column':1,'row':15,'text':'J118INK'} and
                    d['screen_is_not_token_evidence'] and
                    d['printer_is_not_color_evidence'] and
                    d['visual_classification']=='VISUAL_UNVERIFIED',
                    'CAPTURE_PROVENANCE_'+case+session)
            numbers,rows=cpc.records(files['program'])
            first=files['program'][:rows[0]['length']]
            require(numbers==LINES and first[4]==0xa2 and
                    d['ink_opcode_observed']==0xa2 and
                    d['ink_record_hex']==first.hex(' ').upper() and
                    d['region']['length']==len(files['program']) and
                    d['region']['line_numbers']==LINES,
                    'RAM_TOKEN_OR_VALUE_'+case+session)
            for label in ('list','baseline','run'):
                png=files[label+'_png']
                require(png.startswith(b'\x89PNG\r\n\x1a\n') and
                        png[12:16]==b'IHDR' and sha(png)==d[label+'_png_sha256'] and
                        d[label]['screenshot_width']==int.from_bytes(png[16:20],'big') and
                        d[label]['screenshot_height']==int.from_bytes(png[20:24],'big'),
                        'PNG_HASH_AND_FORMAT_'+case+session+label)
                require(sha(files[label+'_log'])==d[label+'_log_sha256'] and
                        files[label+'_log'].startswith(b'exit code: 0\n'),
                        'CAPRICE_LOG_'+case+session+label)
            lines=[parse_integer(z) for z in files['printer'].splitlines(keepends=True)]
            require(len(lines)==2 and all(z is not None for z in lines) and
                    [z['numeric_value'] for z in lines]==[d['err'],d['erl']] and
                    d['run_kind']==('ERROR' if d['err'] else 'NO_ERROR') and
                    sha(files['printer'])==d['printer_sha256'],
                    'ERR_ERL_'+case+session)
            require(d['list']['commands']==setup(case)+source(case).decode('ascii').splitlines()+
                    ['LIST','CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT'] and
                    d['baseline']['commands']==setup(case)+['LOCATE 1,15','PRINT "J118INK"',
                    'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_EXIT'] and
                    d['run']['commands']==setup(case)+source(case).decode('ascii').splitlines()+
                    ['RUN','CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                     'PRINT #8,ERR','PRINT #8,ERL','CAP32_DELAY CAP32_EXIT'],
                    'COMMAND_CHRONOLOGY_'+case+session)
            seen.append(d)
        require(seen[0]['program_hex']==seen[1]['program_hex'] and
                (seen[0]['err'],seen[0]['erl'])==(seen[1]['err'],seen[1]['erl']),
                'PAIR_RAM_ERR_ERL_'+case)
        records[case]=seen[0]['ink_record_hex']
    require(len(set(records.values()))==len(CASES),
            'SOURCE_TOKEN_RECORD_REUSED')
    chrono_cmds=CHRONO+['INK 1,6','LOCATE 1,15','PRINT "J118INK"',
                        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT','INK 1,26',
                        CHRONO_DELAY + ' CAP32_SCRNSHOT CAP32_EXIT']
    for session in SESSIONS:
        dest=out/session/'chronology'
        rec=json.loads(read(dest/'capture.json'))
        require(m['chronology'][session]==sha(read(dest/'capture.json')) and
                rec['session']==session and rec['commands']==chrono_cmds and
                rec['no_intervening_print'] is True and
                rec['visual_classification']=='VISUAL_UNVERIFIED' and
                rec['before_sha256']==sha(read(dest/'screen_0.png')) and
                rec['after_sha256']==sha(read(dest/'screen_1.png')) and
                read(dest/'caprice.log').startswith(b'exit code: 0\n'),
                'CHRONOLOGY_SOURCE_AND_SHA_'+session)
    print(PHASE,'VERIFIED',len(CASES)*2,'sessions',
          'EXTERNAL' if permanent else 'UNSEALED',flush=True)


def negatives(out, permanent=False):
    variants=['token','value','capture','internal_sha','pair','head','missing','png_roi']
    if permanent:variants.append('coordinated')
    untouched={str(p.relative_to(out)):sha(read(p)) for p in out.rglob('*') if p.is_file()}
    for variant in variants:
        with tempfile.TemporaryDirectory(prefix='j118-ink-fraud-') as tmp:
            clone=Path(tmp)/'clone'
            shutil.copytree(out,clone)
            item=clone/'original/I126'
            rec_path=item/'capture.json'
            rec=json.loads(read(rec_path))
            if variant in ('token','value','coordinated'):
                b=bytearray(read(item/'program.bin'))
                b[4 if variant=='token' else 8]^=1
                (item/'program.bin').write_bytes(b)
                if variant=='coordinated':
                    rec['program_sha256']=sha(b)
                    rec['program_hex']=b.hex(' ').upper()
                    rec['ink_record_hex']=b[:int.from_bytes(b[:2],'little')].hex(' ').upper()
                    rec_path.write_bytes(encoded(rec))
                    man=json.loads(read(clone/'manifest.json'))
                    man['cases']['I126']['original']=sha(read(rec_path))
                    (clone/'manifest.json').write_bytes(encoded(man))
            elif variant=='capture':
                b=bytearray(read(item/'run/screen.png'));b[-1]^=1
                (item/'run/screen.png').write_bytes(b)
            elif variant=='internal_sha':
                rec['run_png_sha256']='0'*64;rec_path.write_bytes(encoded(rec))
            elif variant=='pair':
                other=clone/'repeat/I126/capture.json'
                other.write_bytes(read(rec_path))
                man=json.loads(read(clone/'manifest.json'))
                man['cases']['I126']['repeat']=sha(read(other))
                (clone/'manifest.json').write_bytes(encoded(man))
            elif variant=='head':
                man=json.loads(read(clone/'manifest.json'))
                man['acquisition_head']='0'*40
                (clone/'manifest.json').write_bytes(encoded(man))
            elif variant=='missing':
                (item/'run/printer.dat').unlink()
            elif variant=='png_roi':
                b=bytearray(read(item/'baseline/screen.png'));b[-20]^=1
                (item/'baseline/screen.png').write_bytes(b)
            try: verify(clone,permanent)
            except (Invalid,ValueError,KeyError,IndexError,OSError) as ex:
                print(PHASE,'FALSIFICATION_REJECTED',variant,str(ex)[:100],flush=True)
            else:raise Invalid('FALSIFICATION_ACCEPTED_'+variant)
    for rel,digest in untouched.items():
        require(sha(read(out/rel))==digest,'ARCHIVE_MUTATED_'+rel)
    print(PHASE,'ARCHIVE_INTACT',len(untouched),flush=True)


def unit():
    for case in CASES:source(case)
    cpc.self_test()
    require(len(CASES)==13 and len(SESSIONS)==2,'MATRIX_DRIFT')
    try:check_head('0'*40)
    except Invalid as ex:
        require('EXPECTED_HEAD_MISMATCH' in str(ex),'FALSE_HEAD_NOT_REJECTED')
    else:raise Invalid('FALSE_HEAD_ACCEPTED')
    print(PHASE,'SOURCE_MATRIX_FALSE_HEAD_PASS')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check-sources', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--permanent', action='store_true')
    p.add_argument('--expect-head')
    p.add_argument('--caprice', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--evidence', type=Path)
    a = p.parse_args()
    if a.expect_head:
        check_head(a.expect_head)
    if a.check_sources or a.self_test:
        unit()
    if a.caprice:
        require(a.output is not None and a.evidence is None, 'ACQUIRE_ARGUMENTS')
        head = check_head(a.expect_head or subprocess.check_output(
            ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip())
        acquire(a.caprice.resolve(), a.output.resolve(), head)
    if a.evidence:
        verify(a.evidence.resolve(), a.permanent)
        if a.self_test:
            negatives(a.evidence.resolve(), a.permanent)
    else:
        require(not a.permanent, 'PERMANENT_REQUIRES_EVIDENCE')
    require(a.check_sources or a.self_test or a.caprice or a.evidence,
            'NO_OPERATION_SELECTED')


if __name__ == '__main__':
    try:
        main()
    except (Invalid, OSError, subprocess.SubprocessError, UnicodeError,
            KeyError, IndexError, json.JSONDecodeError) as err:
        print('J1.18-A FAIL', err, file=sys.stderr)
        sys.exit(1)
