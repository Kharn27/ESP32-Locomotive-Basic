#!/usr/bin/env python3
"""J1.22-A: CPC6128 INTEGER logical-expression acquisition and sealed verifier.

A source program or a host calculation is NEVER an oracle measurement. An
independent original Actions artifact must supply immutable external seals
before --verify is allowed to succeed. --acquire only runs pinned CPC ROM.
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
DIR = ROOT / 'tests/fixtures/cpc6128/j1_22_a_integer_logical'
BASE = '1d5edc630390bfb109d6596693ec63c8d8588a28'
PHASE = 'J1.22-A'
ROM = '31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562'
CAPRICE = '8c778bf072a06fb7c23b9cccd179041db7f79a52'
GHCR = ('ghcr.io/kharn27/esp32-locomotive-basic-caprice32@sha256:'
        '7c2ac82df92a2df5c7305cc0bd70dc95124249fb46b2d893449f3d48395ced8c')
CORPUS_SHA256 = 'b6be133ea38a6be5a1cb87fea4d77352fa1ac7a814eed1c115feaf8bb30b7d4e'
SESSIONS = ('original', 'repeat')
FILESET = ('program.bin', 'capture.json', 'list/caprice.log',
           'list/screen.png', 'list/printer.dat', 'run/caprice.log',
           'run/screen.png', 'run/printer.dat')
ERR_TAG = b'@@J122ERR@@'
# IMPORTANT: Never fill these using the candidate archive or a host prediction.
# Copy and audit independently from the ORIGINAL GH Actions artifact.
EXTERNAL_MANIFEST_SHA256 = None
EXTERNAL_ACQUISITION_HEAD = None
EXTERNAL_FILE_SHA256 = {}  # exact relative path -> SHA256, from external artifact

class Invalid(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise Invalid(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    require(path.is_file() and not path.is_symlink(), 'MISSING_OR_SYMLINK_' + str(path))
    return path.read_bytes()

def encoding(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')

def corpus():
    raw = read(DIR / 'corpus.json')
    require(digest(raw) == CORPUS_SHA256, 'CORPUS_PIN_MISMATCH')
    obj = json.loads(raw)
    require(obj.get('schema') == 1 and obj.get('phase') == PHASE and
            obj.get('base_sha') == BASE, 'CORPUS_SCHEMA')
    cases = obj.get('cases')
    require(isinstance(cases, dict) and 20 <= len(cases) <= 24, 'CORPUS_COUNT')
    require(all(re.fullmatch(r'[A-Z][A-Z0-9_]+', c) for c in cases), 'CASE_IDS')
    return cases

def check_sources():
    cases = corpus()
    paths = {p.name for p in (DIR / 'sources').glob('*')}
    require(paths == {c.lower() + '.bas' for c in cases}, 'SOURCES_INVENTORY')
    families = [v['family'] for v in cases.values()]
    for op in ('AND', 'OR', 'XOR', 'NOT'):
        require(families.count(op) >= 2, 'OPERATOR_COVERAGE_' + op)
    require(families.count('PRECEDENCE') >= 4 and
            families.count('PARENTHESES') >= 2 and
            families.count('RELATION_IF') >= 2 and
            families.count('DIAGNOSTIC') >= 2, 'MATRIX_COVERAGE')
    for c, entry in cases.items():
        data = read(DIR / 'sources' / (c.lower() + '.bas'))
        require(data == ('\n'.join(entry['lines']) + '\n').encode('ascii') and
                digest(data) == entry['source_sha256'] and
                entry['evidence_status'] == 'UNVERIFIED', 'SOURCE_CHANGED_' + c)
        require(entry['lines'][0].startswith('10 ') and
                entry['lines'][-1].startswith(('20 END', '30 END')), 'LINE_FORM_' + c)
        require(entry['expression'] in entry['lines'][0], 'EXPRESSION_DRIFT_' + c)
    return cases

def repo_head():
    return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                   text=True).strip()

def check_head(head):
    require(bool(re.fullmatch('[0-9a-f]{40}', head or '')), 'HEAD_FORMAT')
    require(repo_head() == head, 'HEAD_MISMATCH')
    require(subprocess.run(['git', '-C', str(ROOT), 'merge-base',
                            '--is-ancestor', BASE, head], capture_output=True).returncode == 0,
            'BASE_NOT_ANCESTOR')

def head_is_ancestor(head):
    return bool(re.fullmatch('[0-9a-f]{40}', head or '')) and subprocess.run(
        ['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', head, 'HEAD'],
        capture_output=True).returncode == 0

def oracle_modules():
    sys.path.insert(0, str(ROOT / 'tools'))
    sys.path.insert(0, str(ROOT / 'tests/oracles'))
    import j1_18_a_ink_evidence as ink
    import token_ram_oracle as cpc
    require(cpc.PIN == CAPRICE and cpc.ROM_SHA == ROM and ink.GHCR == GHCR,
            'EMULATOR_PIN_DRIFT')
    return ink, cpc

def commands(case, entry, stage):
    prefix = ['MODE 1', 'NEW'] + entry['lines']
    if stage == 'list':
        return prefix + ['LIST', 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT',
                         'LIST #8', 'CAP32_DELAY CAP32_EXIT']
    require(stage == 'run', 'BAD_STAGE')
    return prefix + ['RUN', 'CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                     'PRINT #8,"@@J122ERR@@";ERR;",";ERL', 'LIST #8',
                     'CAP32_DELAY CAP32_EXIT']

def parse_output(raw):
    require(raw.count(ERR_TAG) == 1, 'ERR_TAG_MISSING_OR_DUPLICATE')
    result, tail = raw.split(ERR_TAG)
    m = re.match(rb'\s*(\d+)\s*,\s*(\d+)\s*[\r\n]+', tail)
    require(m is not None, 'ERR_ERL_UNREADABLE')
    err, erl = int(m.group(1)), int(m.group(2))
    listed = tail[m.end():]
    require(bool(listed), 'POST_RUN_LIST_MISSING')
    return result, err, erl, listed

def token_bytes(program, cpc, entry):
    nums, rows = cpc.records(program)
    require(nums == [int(x.split(' ', 1)[0]) for x in entry['lines']], 'RAM_LINE_NUMBERS')
    first = rows[0]
    body = program[first['offset'] + 4:first['offset'] + first['length'] - 1]
    # Static ROM tokens are *structural checks*, not evidence of evaluation.
    token = {'AND': 0xfa, 'OR': 0xfc, 'XOR': 0xfd, 'NOT': 0xfe}
    operators = [op for op in token if re.search(r'\b' + op + r'\b', entry['lines'][0])]
    require(all(bytes([token[op]]) in body for op in operators), 'RAM_OPCODE_MISSING')
    return nums, rows, body.hex(' ').upper()

def acquire(cap, out, head):
    cases = check_sources()
    check_head(head)
    require(not out.exists(), 'DESTINATION_EXISTS')
    ink, cpc = oracle_modules()
    version = ink.check_caprice(cap)
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='j122-caprice-sna-') as td:
        for session in SESSIONS:
            for case, entry in cases.items():
                target = out / session / case
                snap = Path(td) / (session + '-' + case)
                snap.mkdir()
                lc, rc = commands(case, entry, 'list'), commands(case, entry, 'run')
                lm = ink.launch(cap, target / 'list', snap, lc, True)
                snapshots = list(snap.glob('*.sna'))
                require(len(snapshots) == 1, 'SNA_COUNT_' + case)
                program, region = cpc.extract_snapshot(
                    read(snapshots[0]), [int(x.split(' ', 1)[0]) for x in entry['lines']])
                nums, rows, body = token_bytes(program, cpc, entry)
                (target / 'program.bin').write_bytes(program)
                rm = ink.launch(cap, target / 'run', Path(td), rc, True)
                list_raw = read(target / 'list/printer.dat')
                result, err, erl, post_list = parse_output(read(target / 'run/printer.dat'))
                require(list_raw and list_raw == post_list, 'LIST_CHANGED_OR_MISSING_' + case)
                capture = {'phase': PHASE, 'case': case, 'session': session,
                           'source_sha256': entry['source_sha256'], 'ram_hex': program.hex(' ').upper(),
                           'region': region, 'numbers': nums, 'expression_record_hex': body,
                           'list_hex': list_raw.hex().upper(), 'result_hex': result.hex().upper(),
                           'err': err, 'erl': erl,
                           'commands': {'list': lc, 'run': rc},
                           'processes': {'list': lm, 'run': rm},
                           'screen_diagnostic': 'UNVERIFIED_PENDING_HUMAN_TRANSCRIPTION',
                           'semantics': 'CPC_OBSERVATION_NOT_HOST_PREDICTION'}
                (target / 'capture.json').write_bytes(encoding(capture))
                print(PHASE, session, case, 'RAM', digest(program),
                      'RESULT_HEX', capture['result_hex'], 'ERR', err, 'ERL', erl, flush=True)
    expected = {f'{s}/{c}/{p}' for s in SESSIONS for c in cases for p in FILESET}
    manifest = {'schema': 1, 'phase': PHASE, 'base_sha': BASE, 'acquisition_head': head,
                'run_id': os.environ.get('GITHUB_RUN_ID', 'LOCAL'),
                'oracle': {'rom_sha256': ROM, 'caprice_commit': CAPRICE,
                           'ghcr': GHCR, 'version': version, 'model': 'CPC6128', 'basic': '1.1'},
                'cases': list(cases), 'sessions': list(SESSIONS),
                'files': {p: digest(read(out / p)) for p in sorted(expected)},
                'external_seals': 'PENDING_EXTERNAL_ORIGINAL_ACTIONS_ARTIFACT',
                'snapshots_archived': False, 'native_changes': False}
    (out / 'manifest.json').write_bytes(encoding(manifest))
    verify(out, permanent=False)
    print(PHASE, 'FRESH_ACQUISITION_UNSEALED', len(cases)*2,
          'MANIFEST_SHA256', digest(read(out/'manifest.json')), flush=True)
    for p in sorted(expected):
        print('EXTERNAL_SHA256', p, digest(read(out/p)), flush=True)

def verify(out, permanent=True):
    cases = check_sources()
    raw_manifest = read(out / 'manifest.json')
    m = json.loads(raw_manifest)
    require(m.get('schema') == 1 and m.get('phase') == PHASE and
            m.get('base_sha') == BASE and m.get('cases') == list(cases) and
            m.get('sessions') == list(SESSIONS) and
            m.get('snapshots_archived') is False and m.get('native_changes') is False and
            m.get('external_seals') == 'PENDING_EXTERNAL_ORIGINAL_ACTIONS_ARTIFACT' and
            m.get('oracle',{}).get('rom_sha256') == ROM and
            m.get('oracle',{}).get('caprice_commit') == CAPRICE and
            m.get('oracle',{}).get('ghcr') == GHCR and
            m.get('oracle',{}).get('model') == 'CPC6128' and
            m.get('oracle',{}).get('basic') == '1.1', 'PROVENANCE_MISMATCH')
    require(head_is_ancestor(m.get('acquisition_head')), 'FAKE_HEAD')
    paths = {f'{s}/{c}/{f}' for s in SESSIONS for c in cases for f in FILESET}
    actual = {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()}
    require(actual == paths | {'manifest.json'} and set(m.get('files',{})) == paths,
            'ARCHIVE_INVENTORY')
    if permanent:
        require(bool(re.fullmatch(r'[a-f0-9]{64}', EXTERNAL_MANIFEST_SHA256 or '')) and
                m['acquisition_head'] == EXTERNAL_ACQUISITION_HEAD and
                digest(raw_manifest) == EXTERNAL_MANIFEST_SHA256 and
                set(EXTERNAL_FILE_SHA256) == paths, 'EXTERNAL_SEALS_MISSING_OR_INVALID')
    for p in sorted(paths):
        contents = read(out / p)
        require(len(contents) > 0 and digest(contents) == m['files'][p], 'FILE_HASH_' + p)
        if permanent:
            require(digest(contents) == EXTERNAL_FILE_SHA256[p], 'EXTERNAL_FILE_HASH_' + p)
    _, cpc = oracle_modules()
    results = {}
    for session in SESSIONS:
        for case, entry in cases.items():
            base = out / session / case
            cap = json.loads(read(base / 'capture.json'))
            program = read(base / 'program.bin')
            nums, rows, body = token_bytes(program, cpc, entry)
            before = read(base / 'list/printer.dat')
            result, err, erl, after = parse_output(read(base / 'run/printer.dat'))
            require(before == after and before == bytes.fromhex(cap['list_hex']) and
                    result == bytes.fromhex(cap['result_hex']) and
                    cap['err'] == err and cap['erl'] == erl and
                    cap['ram_hex'] == program.hex(' ').upper() and
                    cap['numbers'] == nums and cap['expression_record_hex'] == body and
                    cap['source_sha256'] == entry['source_sha256'] and
                    cap['phase'] == PHASE and cap['case'] == case and
                    cap['session'] == session and
                    cap['commands'] == {t:commands(case,entry,t) for t in ('list','run')},
                    'CAPTURE_MISMATCH_' + case + session)
            for stage in ('list', 'run'):
                process = cap['processes'][stage]
                require(process['commands'] == commands(case,entry,stage) and
                        process['started_utc'] != process['finished_utc'] and
                        read(base / stage / 'caprice.log').startswith(b'exit code: 0\n'),
                        'PROCESS_NOT_PROVEN_' + case + session + stage)
                png = read(base / stage / 'screen.png')
                require(png[:8] == b'\x89PNG\r\n\x1a\n' and png[12:16] == b'IHDR' and
                        process['screenshot_width'] == int.from_bytes(png[16:20], 'big') and
                        process['screenshot_height'] == int.from_bytes(png[20:24], 'big'),
                        'SCREEN_INVALID_' + case + session + stage)
            results[case,session] = (program, before, result, err, erl,
                                     cap['processes']['list']['started_utc'],
                                     cap['processes']['run']['started_utc'])
    for case in cases:
        a,b = results[case,'original'], results[case,'repeat']
        require(a[:5] == b[:5] and a[5] != b[5] and a[6] != b[6],
                'INDEPENDENT_REPEAT_NOT_PROVEN_' + case)
    return {'cases': len(cases), 'sessions': len(cases)*2,
            'status': 'EXTERNALLY_SEALED' if permanent else 'UNSEALED_NOT_AN_ORACLE'}

def falsifications(out):
    """Run only against a verified externally sealed archive; never edit it."""
    verify(out, permanent=True)
    case = next(iter(corpus()))
    mutations = ('ram', 'printer', 'list', 'capture', 'png', 'log',
                 'missing_file', 'rom', 'head', 'repeat', 'coordinated_rehash')
    for kind in mutations:
        with tempfile.TemporaryDirectory(prefix='j122-negative-') as tmp:
            copy = Path(tmp) / 'archive'
            shutil.copytree(out, copy)
            victim = copy/'original'/case
            file = {'ram':'program.bin', 'printer':'run/printer.dat',
                    'list':'list/printer.dat', 'capture':'capture.json',
                    'png':'run/screen.png', 'log':'run/caprice.log',
                    'missing_file':'program.bin', 'repeat':'program.bin',
                    'coordinated_rehash':'program.bin'}.get(kind)
            if kind in ('rom','head'):
                m = json.loads(read(copy/'manifest.json'))
                if kind == 'rom': m['oracle']['rom_sha256'] = '0'*64
                else: m['acquisition_head'] = '0'*40
                (copy/'manifest.json').write_bytes(encoding(m))
            elif kind == 'repeat':
                data = read(copy/'repeat'/case/file)
                (victim/file).write_bytes(data + b'X')
            elif kind == 'missing_file': (victim/file).unlink()
            else:
                original = read(victim/file)
                (victim/file).write_bytes(original + b'X')
                if kind == 'coordinated_rehash':
                    m = json.loads(read(copy/'manifest.json'))
                    key = 'original/'+case+'/'+file
                    m['files'][key] = digest(read(victim/file))
                    (copy/'manifest.json').write_bytes(encoding(m))
            try: verify(copy, permanent=True)
            except (Invalid, ValueError, KeyError, IndexError, UnicodeError):
                print(PHASE, 'FALSIFICATION_REJECTED', kind, flush=True)
            else: raise Invalid('FALSIFICATION_ACCEPTED_' + kind)
    return len(mutations)

def self_test():
    check_sources()
    with tempfile.TemporaryDirectory(prefix='j122-empty-') as td:
        for path in (Path(td), Path(td)/'missing'):
            try: verify(path, permanent=True)
            except Invalid: pass
            else: raise Invalid('EMPTY_ARCHIVE_FALSE_PASS')
        partial = Path(td)/'partial'
        partial.mkdir()
        (partial/'manifest.json').write_bytes(b'{}\n')
        try: verify(partial, permanent=True)
        except Invalid: pass
        else: raise Invalid('PARTIAL_ARCHIVE_FALSE_PASS')
    require(EXTERNAL_MANIFEST_SHA256 is None or bool(re.fullmatch(
            r'[a-f0-9]{64}', EXTERNAL_MANIFEST_SHA256)), 'PARTIAL_SEAL')
    print(PHASE, 'OFFLINE_CONTRACT_PASS', len(corpus()), 'CASES',
          'NEGATIVE_SYNTHETIC', 3, 'CPC_OBSERVATIONS', 0, flush=True)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check-sources', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--acquire', type=Path)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--head')
    ap.add_argument('--verify', nargs='?', const=str(DIR), type=Path)
    ap.add_argument('--verify-unsealed', type=Path,
                    help='diagnostic only; NEVER an oracle PASS')
    args = ap.parse_args()
    require(any((args.check_sources,args.self_test,args.acquire,args.verify,
                 args.verify_unsealed)), 'OPERATION_REQUIRED')
    if args.check_sources: check_sources(); print(PHASE, 'SOURCES_PASS')
    if args.acquire:
        require(args.output is not None and args.verify is None, 'ACQUIRE_ARGS')
        acquire(args.acquire.resolve(),args.output.resolve(),args.head or repo_head())
    if args.verify_unsealed:
        print(PHASE, 'UNSEALED', verify(args.verify_unsealed.resolve(), False))
    if args.verify:
        print(PHASE, 'SEALED', verify(args.verify.resolve(), True))
        if args.self_test:
            print(PHASE, 'REAL_NEGATIVES_REJECTED', falsifications(args.verify.resolve()))
    elif args.self_test: self_test()

if __name__ == '__main__':
    try: main()
    except (Invalid, OSError, subprocess.SubprocessError, ValueError, KeyError,
            IndexError, UnicodeError, ImportError) as e:
        print(PHASE, 'FAIL', str(e), file=sys.stderr)
        sys.exit(1)
