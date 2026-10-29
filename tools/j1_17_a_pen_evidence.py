#!/usr/bin/env python3
"""J1.17-A CPC6128 PEN oracle, no C99/firmware implementation.

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

PHASE = 'J1.17-A'
SOURCES = ROOT / 'tests/oracles/inputs/j1_17_a'
CASES = {'P00': '0', 'P01': '1', 'P02': '2', 'P03': '3',
         'P04': '4', 'P15': '15', 'P16': '16', 'PN1': '-1'}
SESSIONS = ('original', 'repeat')
LINES = [10, 20, 30, 40]
GHCR = 'ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c'
SETUP = ['MODE 1', 'INK 0,0', 'INK 1,26', 'INK 2,6', 'INK 3,18',
         'PAPER 0', 'PEN 1', 'CLS', 'NEW']
# Extract independently from the FIRST authentic GitHub acquisition and pin
# its actual archive byte hashes here. Never derive these from manifest.json.
# The permanent verifier fails CLOSED until all 16 entries are pinned.
SEALED = {}
SEALED_MANIFEST = ''  # SHA256 of first archived manifest, pinned outside archive


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
    expected = (f'10 PEN {CASES[case]}\n20 LOCATE 1,15\n'
                '30 PRINT "J117PEN"\n40 END\n').encode('ascii')
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


def launch(cap, dest, snadir, commands, printer):
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
    require(len(pics) == 1 and read(pics[0]).startswith(b'\x89PNG\r\n\x1a\n'),
            'PNG_MISSING_OR_INVALID')
    png = dest / 'screen.png'
    pics[0].rename(png)
    data = read(png)
    require(len(data) >= 80 and data[12:16] == b'IHDR', 'PNG_MISSING_IHDR')
    w = int.from_bytes(data[16:20], 'big')
    h = int.from_bytes(data[20:24], 'big')
    require(300 <= w <= 2000 and 200 <= h <= 1500, 'PNG_UNEXPECTED_DIMENSIONS')
    return {'started_utc': start, 'finished_utc': stop,
            'commands': commands, 'screenshot_width': w, 'screenshot_height': h}


def capture_one(cap, out, case, session, tmp):
    src = source(case)
    work = out / session / case
    # LIST and RUN are separate fresh CPC processes; input programs are identical.
    ldir, rdir = work / 'list', work / 'run'
    lsnap = tmp / (case + '_' + session)
    lsnap.mkdir()
    raw_lines = src.decode('ascii').splitlines()
    list_commands = SETUP + raw_lines + [
        'LIST', 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT']
    lt = launch(cap, ldir, lsnap, list_commands, False)
    snapshots = list(lsnap.glob('*.sna'))
    require(len(snapshots) == 1, 'LIST_SNAPSHOT_MISSING')
    program, region = cpc.extract_snapshot(read(snapshots[0]), LINES)
    # No SNA retained, no fabricated token stream. &BB is only a ROM hypothesis
    # until it is observed as the first opcode in BOTH real RAM captures.
    nums, rows = cpc.records(program)
    first = program[rows[0]['offset']:rows[0]['offset'] + rows[0]['length']]
    require(first[4] == 0xBB, 'CPC_PEN_TOKEN_NOT_BB')
    (work / 'program.bin').write_bytes(program)
    # Capturing after RUN and before the ERR/ERL probes avoids probe text on screen.
    run_commands = SETUP + raw_lines + ['RUN',
        'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
        'PRINT #8,ERR', 'PRINT #8,ERL', 'CAP32_DELAY CAP32_EXIT']
    rt = launch(cap, rdir, tmp, run_commands, True)
    raw = read(rdir / 'printer.dat')
    require(0 < len(raw) <= 256, 'MISSING_OR_OVERSIZE_ERR_ERL_PRINTER')
    parts = [parse_integer(line) for line in raw.splitlines(keepends=True)]
    require(len(parts) == 2 and all(p is not None for p in parts),
            'ERR_ERL_PRINTER_NOT_TWO_NUMBERS')
    err, erl = (p['numeric_value'] for p in parts)
    require(isinstance(err, int) and isinstance(erl, int), 'ERR_ERL_NON_INTEGER')
    # No assumption about error number (particularly PEN 16 / -1).
    # No pixel interpretation unless a future externally checked ROI/ink map exists.
    rec = {
        'case': case, 'session': session, 'source_sha256': sha(src),
        'program_sha256': sha(program), 'program_hex': program.hex(' ').upper(),
        'pen_record_hex': first.hex(' ').upper(), 'pen_opcode_observed': first[4],
        'region': region, 'line_numbers': nums, 'setup_mode': 1,
        'inks': {'0': 0, '1': 26, '2': 6, '3': 18}, 'paper': 0,
        'print_location': {'column': 1, 'row': 15, 'text': 'J117PEN'},
        'list': lt, 'run': rt,
        'err': err, 'erl': erl, 'run_kind': 'ERROR' if err != 0 else 'NO_ERROR',
        'printer_sha256': sha(raw),
        'list_png_sha256': sha(read(ldir / 'screen.png')),
        'run_png_sha256': sha(read(rdir / 'screen.png')),
        'list_log_sha256': sha(read(ldir / 'caprice.log')),
        'run_log_sha256': sha(read(rdir / 'caprice.log')),
        'visual_classification': 'VISUAL_UNVERIFIED',
        'visual_reason': 'pixel RGB/ink identity and PRINT glyph ROI not independently calibrated',
        'screen_is_not_token_evidence': True,
        'printer_is_not_color_evidence': True,
    }
    (work / 'capture.json').write_bytes(encoded(rec))
    return rec


def acquire(cap, out, head):
    require(not out.exists(), 'EVIDENCE_OUTPUT_EXISTS')
    version = check_caprice(cap)
    out.mkdir(parents=True)
    manifest = {'schema_version': 1, 'phase': PHASE, 'acquisition_head': head,
                'run_id': os.environ.get('GITHUB_RUN_ID', 'LOCAL'),
                'oracle': {'caprice': cpc.PIN, 'rom': cpc.ROM_SHA,
                           'ghcr': GHCR, 'version': version, 'model': 'CPC6128',
                           'basic': '1.1'},
                'full_snapshots_archived': False, 'native_changes': False,
                'cases': {}, 'visual_classification': 'VISUAL_UNVERIFIED'}
    with tempfile.TemporaryDirectory(prefix='j117-pen-sna-') as temp:
        t = Path(temp)
        for case in CASES:
            seen = {}
            for session in SESSIONS:
                seen[session] = capture_one(cap, out, case, session, t)
                print('J1.17-A', case, session, 'PEN_RECORD',
                      seen[session]['pen_record_hex'], 'ERR', seen[session]['err'],
                      'ERL', seen[session]['erl'], flush=True)
            require(seen['original']['program_hex'] == seen['repeat']['program_hex'],
                    'INDEPENDENT_RAM_MISMATCH_' + case)
            require((seen['original']['err'], seen['original']['erl']) ==
                    (seen['repeat']['err'], seen['repeat']['erl']),
                    'INDEPENDENT_EXECUTION_MISMATCH_' + case)
            manifest['cases'][case] = {s: sha(read(out / s / case / 'capture.json'))
                                       for s in SESSIONS}
    (out / 'manifest.json').write_bytes(encoded(manifest))
    verify(out)
    print('J1.17-A CPC_ACQUIRED', len(CASES) * len(SESSIONS),
          'INDEPENDENT_CASE_SESSIONS HEAD', head, flush=True)


def verify(out, permanent=False):
    m = json.loads(read(out / 'manifest.json'))
    require(m['phase'] == PHASE and m['schema_version'] == 1 and
            bool(re.fullmatch(r'[0-9a-f]{40}', m['acquisition_head'])) and
            m['oracle']['caprice'] == cpc.PIN and
            m['oracle']['rom'] == cpc.ROM_SHA and m['oracle']['ghcr'] == GHCR and
            m['oracle']['model'] == 'CPC6128' and m['oracle']['basic'] == '1.1' and
            m['native_changes'] is False and m['full_snapshots_archived'] is False and
            m['visual_classification'] == 'VISUAL_UNVERIFIED' and
            set(m['cases']) == set(CASES), 'MANIFEST_PROVENANCE_INVALID')
    # A forged but syntactically well-formed HEAD must not pass a live checkout.
    ancestry = subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor',
                               m['acquisition_head'], 'HEAD'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    require(ancestry.returncode == 0, 'FALSE_OR_UNREACHABLE_ACQUISITION_HEAD')
    if permanent:
        require(bool(re.fullmatch(r'[0-9a-f]{64}', SEALED_MANIFEST)) and
                sha(read(out / 'manifest.json')) == SEALED_MANIFEST,
                'EXTERNAL_MANIFEST_SEAL_MISMATCH')
        require(set(SEALED) == set(CASES) and all(
            set(SEALED[c]) == set(SESSIONS) for c in CASES), 'EXTERNAL_PEN_SEAL_NOT_ESTABLISHED')
    prog_set = {}
    for case in CASES:
        results = []
        for session in SESSIONS:
            work = out / session / case
            source(case)
            files = {'program': read(work / 'program.bin'),
                     'list_png': read(work / 'list/screen.png'),
                     'run_png': read(work / 'run/screen.png'),
                     'printer': read(work / 'run/printer.dat'),
                     'list_log': read(work / 'list/caprice.log'),
                     'run_log': read(work / 'run/caprice.log'),
                     'capture': read(work / 'capture.json')}
            require(sha(files['capture']) == m['cases'][case][session],
                    'INTERNAL_CAPTURE_HASH_' + case + session)
            if permanent:
                require(all(sha(files[name]) == SEALED[case][session][name]
                            for name in files),
                        'EXTERNAL_PEN_SEAL_MISMATCH_' + case + session)
            d = json.loads(files['capture'])
            require(d['case'] == case and d['session'] == session and
                    d['source_sha256'] == sha(source(case)) and
                    d['program_sha256'] == sha(files['program']) and
                    d['program_hex'] == files['program'].hex(' ').upper() and
                    d['line_numbers'] == LINES and d['setup_mode'] == 1 and
                    d['inks'] == {'0': 0, '1': 26, '2': 6, '3': 18} and d['paper'] == 0 and
                    d['print_location'] == {'column': 1, 'row': 15, 'text': 'J117PEN'} and
                    d['visual_classification'] == 'VISUAL_UNVERIFIED' and
                    d['screen_is_not_token_evidence'] is True and
                    d['printer_is_not_color_evidence'] is True,
                    'CAPTURE_PROVENANCE_' + case + session)
            numbers, rows = cpc.records(files['program'])
            first = files['program'][0:rows[0]['length']]
            require(numbers == LINES and first[4] == 0xbb and
                    d['pen_opcode_observed'] == 0xbb and
                    d['pen_record_hex'] == first.hex(' ').upper(),
                    'TOKEN_OR_VALUE_RAM_MISMATCH_' + case + session)
            require(d['region']['length'] == len(files['program']) and
                    d['region']['line_numbers'] == LINES and
                    d['region']['end_exclusive'] - d['region']['start_address'] == len(files['program']) and
                    d['region']['bank'] == 'physical bank 0, Gate Array RAM config 0',
                    'RAM_REGION_BOUNDS_' + case + session)
            for label, raw, field in [('list', files['list_png'], 'list_png_sha256'),
                                      ('run', files['run_png'], 'run_png_sha256')]:
                require(raw.startswith(b'\x89PNG\r\n\x1a\n') and
                        raw[12:16] == b'IHDR' and sha(raw) == d[field] and
                        int.from_bytes(raw[16:20], 'big') == d[label]['screenshot_width'] and
                        int.from_bytes(raw[20:24], 'big') == d[label]['screenshot_height'],
                        'SCREENSHOT_INVALID_' + case + session)
            for label in ('list', 'run'):
                cmds = d[label]['commands']
                suffix = (["LIST", "CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT"]
                          if label == 'list' else
                          ['RUN', 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                           'PRINT #8,ERR', 'PRINT #8,ERL', 'CAP32_DELAY CAP32_EXIT'])
                require(cmds == SETUP + source(case).decode('ascii').splitlines() + suffix,
                        'COMMANDS_CHRONOLOGY_' + case + session + label)
                require(sha(files[label + '_log']) == d[label + '_log_sha256'] and
                        files[label + '_log'].startswith(b'exit code: 0\n'),
                        'CAPRICE_LOG_CORRUPTION_' + case + session + label)
            lines = [parse_integer(line) for line in files['printer'].splitlines(keepends=True)]
            require(len(lines) == 2 and all(x is not None for x in lines) and
                    [x['numeric_value'] for x in lines] == [d['err'], d['erl']] and
                    sha(files['printer']) == d['printer_sha256'] and
                    d['run_kind'] == ('ERROR' if d['err'] else 'NO_ERROR'),
                    'RUN_ERR_ERL_MISMATCH_' + case + session)
            results.append(d)
        require(results[0]['program_hex'] == results[1]['program_hex'] and
                (results[0]['err'], results[0]['erl']) ==
                (results[1]['err'], results[1]['erl']),
                'INDEPENDENT_PAIR_MISMATCH_' + case)
        prog_set[case] = results[0]['pen_record_hex']
    require(len(set(prog_set.values())) == len(CASES),
            'CASE_VALUE_ALIAS_OR_RAM_REUSE')
    print('J1.17-A VERIFIED', len(CASES) * len(SESSIONS),
          'sessions; seal=' + ('EXTERNAL' if permanent else 'UNSEALED'),
          'VISUAL_UNVERIFIED', flush=True)


def negatives(out, permanent=False):
    # On unsealed acquisitions only single-axis fraud can be rejected.
    # Coordinated changes require the external, post-acquisition immutable pins.
    experiments = ['token', 'value', 'capture', 'internal_sha', 'fake_pair', 'head']
    if permanent:
        experiments.append('coordinated')
    untouched = {str(p.relative_to(out)): sha(read(p)) for p in out.rglob('*') if p.is_file()}
    for kind in experiments:
        with tempfile.TemporaryDirectory(prefix='j117-forgery-') as temp:
            work = Path(temp) / 'clone'
            shutil.copytree(out, work)
            item = work / 'original/P04'
            capture = item / 'capture.json'
            record = json.loads(read(capture))
            if kind in ('token', 'value'):
                raw = bytearray(read(item / 'program.bin'))
                if kind == 'token':
                    raw[4] ^= 1
                else:
                    raw[6] ^= 1  # C99 never involved; raw CPC RAM mutation
                (item / 'program.bin').write_bytes(raw)
            elif kind == 'capture':
                raw = bytearray(read(item / 'run/screen.png'))
                raw[-1] ^= 1
                (item / 'run/screen.png').write_bytes(raw)
            elif kind == 'internal_sha':
                record['run_png_sha256'] = '0' * 64
                capture.write_bytes(encoded(record))
            elif kind == 'fake_pair':
                fake = work / 'repeat/P04/capture.json'
                fake.write_bytes(read(capture))
                m = json.loads(read(work / 'manifest.json'))
                m['cases']['P04']['repeat'] = sha(read(fake))
                (work / 'manifest.json').write_bytes(encoded(m))
            elif kind == 'head':
                m = json.loads(read(work / 'manifest.json'))
                m['acquisition_head'] = '0' * 40
                (work / 'manifest.json').write_bytes(encoded(m))
            elif kind == 'coordinated':
                raw = bytearray(read(item / 'program.bin'))
                raw[6] ^= 1
                (item / 'program.bin').write_bytes(raw)
                record['program_sha256'] = sha(raw)
                record['program_hex'] = raw.hex(' ').upper()
                record['pen_record_hex'] = raw[:int.from_bytes(raw[:2], 'little')].hex(' ').upper()
                capture.write_bytes(encoded(record))
                m = json.loads(read(work / 'manifest.json'))
                m['cases']['P04']['original'] = sha(read(capture))
                (work / 'manifest.json').write_bytes(encoded(m))
            else:
                raise Invalid('UNKNOWN_FALSIFICATION')
            try:
                verify(work, permanent)
            except (Invalid, ValueError, KeyError, IndexError) as ex:
                print('J1.17-A FALSIFICATION_REJECTED', kind, str(ex)[:130], flush=True)
            else:
                raise Invalid('FALSIFICATION_ACCEPTED_' + kind)
    for name, original in untouched.items():
        require(sha(read(out / name)) == original, 'ORIGINAL_ARCHIVE_CHANGED_' + name)
    print('J1.17-A ORIGINAL_ARCHIVE_INTACT', len(untouched), flush=True)


def unit():
    for case in CASES:
        source(case)
    cpc.self_test()
    require(len(CASES) == 8 and len(SESSIONS) == 2, 'CASE_MATRIX_CHANGED')
    try:
        check_head('0' * 40)
    except Invalid as ex:
        require(str(ex).startswith('EXPECTED_HEAD_MISMATCH'), 'FALSE_HEAD_NOT_REJECTED')
    else:
        raise Invalid('FALSE_HEAD_ACCEPTED')
    print('J1.17-A SOURCE_MATRIX_AND_FALSE_HEAD_TESTED')


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
        print('J1.17-A FAIL', err, file=sys.stderr)
        sys.exit(1)
