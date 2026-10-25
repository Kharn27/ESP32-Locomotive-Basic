#!/usr/bin/env python3
"""Archive or verify independent CPC6128 evidence. No Caprice32/ROM needed."""
import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = Path('tests/fixtures/cpc6128/evidence')
ORACLE = '8c778bf072a06fb7c23b9cccd179041db7f79a52'
CASE_SHA = {'minimal': 'f1f6c19632305d30c3584b602eefa053010521d927eebc86ec86b5fdfad236d6',
            'witness': 'd0d15378eee3eb763390c1e0e592730e9260c0dcc6d7c832bcc7212d50e625b1'}
KINDS = {'screenshot': 'visual_png', 'printer.dat': 'cpc_printer',
         'native.stdout.bin': 'c99_stdout', 'source.bas': 'basic_source',
         'autocmd.json': 'input_trace', 'cap32.cfg': 'cpc_config',
         'caprice.log': 'acquisition_log', 'native.stderr.log': 'c99_stderr'}
FORBIDDEN = {'.rom', '.sna', '.dsk', '.cpr', '.img', '.iso', '.zip', '.tap', '.cdt'}
SOURCES = {'minimal': 'tests/oracles/inputs/minimal.bas',
           'witness': 'tests/fixtures/cpc6128/sources/c_integer_add.bas'}
HEX = re.compile('[0-9a-f]{64}\\Z')


class Invalid(Exception):
    pass


def must(ok, message):
    if not ok:
        raise Invalid(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def get(root, name, desc):
    must(isinstance(desc, dict) and isinstance(desc.get('path'), str), 'missing file descriptor')
    raw = desc['path']; p = PurePosixPath(raw)
    must('\\' not in raw and not p.is_absolute() and raw == str(p)
         and '..' not in p.parts and all(not s.startswith('.') for s in p.parts), 'unsafe path: '+raw)
    must(p.parent == PurePosixPath(BASE.as_posix())/'caprice32'/name, 'path outside case: '+raw)
    must(p.suffix.lower() not in FORBIDDEN, 'forbidden ROM/snapshot/media: '+raw)
    f = root/p
    must(f.is_file() and not f.is_symlink() and f.resolve().is_relative_to(root.resolve()), 'file absent or symlink: '+raw)
    b = f.read_bytes()
    must(type(desc.get('size_bytes')) is int and len(b) == desc['size_bytes']
         and isinstance(desc.get('sha256'), str) and HEX.fullmatch(desc['sha256'])
         and sha(b) == desc['sha256'], 'size/SHA mismatch: '+raw)
    return b


def verify(root, j):
    must(j['schema_version'] == 1 and len(j['cases']) == 2, 'invalid archive schema')
    o = j['oracle']; must(o['commit'] == ORACLE and o['version'] == '4.6.0' and
                        o['model'] == 'CPC6128' and o['ram_kb'] == 128 and
                        o['rom_files_committed'] is False and o['keyboard'] == 'English', 'wrong oracle configuration')
    for k in ('system_rom_sha256', 'amsdos_rom_sha256'):
        must(isinstance(o[k], str) and HEX.fullmatch(o[k]), 'missing ROM fingerprint')
    origin = j['original_artifact']
    must(origin['artifact_id'] == 12604041942 and origin['run_id'] == 40207538056
         and HEX.fullmatch(origin['original_manifest_sha256']), 'invalid acquisition provenance')
    must(j['historical_acceptance_gate_closed'] is False and
         j['token_binary_captures'] == 0, 'unsupported historical gate claim')
    seen = set()
    for case in j['cases']:
        name=case['id']
        must(name in CASE_SHA and name not in seen, 'unknown/repeated case')
        seen.add(name)
        cmp = case['comparison']
        must(cmp['status'] == 'MATCH_SEMANTIC' and
             cmp['oracle_number'] == 5 and cmp['native_number'] == 5 and
             cmp['format_exactness_claimed'] is False, 'false exact comparison')
        must(case['printer_screen_byte_equivalence'] is False and
             case['screen_bytes_captured'] is False, 'printer/screenshot wrongly equated')
        records=case['files']
        must(set(records) == set(KINDS), 'missing/extra evidence files')
        buffers={}
        for key, kind in KINDS.items():
            d=records[key]
            must(d['kind'] == kind, 'wrong evidence channel: '+key)
            must(PurePosixPath(d['path']).name == (key if key!='screenshot' else d['path'].split('/')[-1]),
                 'unexpected filename')
            buffers[key]=get(root,name,d)
        png=buffers['screenshot']
        must(png.startswith(b'\x89PNG\r\n\x1a\n') and png[12:16] == b'IHDR'
             and struct.unpack('>II',png[16:24]) == (768,540)
             and sha(png) == CASE_SHA[name], 'screenshot is not the selected historical PNG')
        must(buffers['printer.dat'] == b' 5 \r\n' and buffers['native.stdout.bin'] == b'5\n',
             'raw printer/C99 channels changed')
        source=buffers['source.bas']
        must(sha(source) == case['source_sha256'] and
             (root/SOURCES[name]).read_bytes() == source, 'source mismatch')
        commands=json.loads(buffers['autocmd.json'])
        lines=source.decode('ascii').splitlines()
        must(commands['source_sha256'] == sha(source) and
             commands['commands'][:len(lines)] == lines and
             commands['commands'][len(lines)] == 'RUN' and
             commands['commands'] == case['commands'], 'command trace mismatch')
        must('exit code: 0' in buffers['caprice.log'].decode('utf-8') and
             PurePosixPath(records['screenshot']['path']).name in buffers['caprice.log'].decode('utf-8'),
             'acquisition log does not confirm screenshot')
        print(name, 'archived PNG verified', sha(png), 'MATCH_SEMANTIC only')
    must(seen == set(CASE_SHA), 'expected both cases')
    print('PASS: two historical PNGs, distinct printer/C99 streams, independent J0.24 gate still BLOCKED')


def archive(root, downloaded):
    target = root/BASE
    must(not (target/'manifest.json').exists(), 'permanent archive already exists; refuse overwrite')
    upstream_path=downloaded/'manifest.json'
    upbytes=upstream_path.read_bytes()
    must(sha(upbytes) == 'd5f1aa9b3b8129d25db5511af164db9a32a6cad6232127ae3fc30b5429ab9d55',
         'not the Pilotage-approved acquisition manifest')
    up=json.loads(upbytes)
    must(up['oracle']['commit']==ORACLE and up['oracle']['model']=='CPC6128' and
         up['oracle']['ram_kb']==128 and len(up['captures'])==2, 'wrong oracle archive')
    cases=[]
    for item in up['captures']:
        name=item['case']; must(name in CASE_SHA, 'unexpected case')
        source=(root/SOURCES[name]).read_bytes()
        must(sha(source)==item['source_sha256'], 'original BASIC source modified')
        files={}
        input_files=item['files']
        for key,kind in KINDS.items():
            if key=='source.bas':
                original=source
                filename='source.bas'
            else:
                matches=[(p,d) for p,d in input_files.items() if
                         p.startswith(name+'/') and
                         (p.endswith('.png') if key=='screenshot' else p.endswith('/'+key))]
                must(len(matches)==1, 'missing/duplicate '+key)
                member,info=matches[0]
                original=(downloaded/member).read_bytes()
                must(sha(original)==info['sha256'] and len(original)==info['size_bytes'], 'upstream file SHA changed: '+member)
                filename=Path(member).name
            if key=='screenshot':
                must(sha(original)==CASE_SHA[name], 'wrong screenshot sha: '+name)
            path=target/'caprice32'/name/filename
            path.parent.mkdir(parents=True,exist_ok=True)
            must(not path.exists(),'refuse overwrite: '+str(path))
            path.write_bytes(original)
            files[key]={'path':str(path.relative_to(root)), 'size_bytes':len(original),
                        'sha256':sha(original),'kind':kind}
        cmp=item['comparison']
        must(cmp['status']=='MATCH_SEMANTIC' and cmp['format_exactness_claimed'] is False, 'upstream mismatch')
        cases.append({'id':name,'source_upstream_path':SOURCES[name],
                      'source_sha256':sha(source),
                      'commands':json.loads((target/'caprice32'/name/'autocmd.json').read_text())['commands'],
                      'comparison':cmp,
                      'printer_screen_byte_equivalence':False,
                      'screen_bytes_captured':False,
                      'files':files})
    j={'schema_version':1,'purpose':'immutable ROM-backed evidence, not J0.24 historical acceptance',
       'original_artifact':{'run_id':40207538056,'artifact_id':12604041942,
         'run_url':'https://github.com/Kharn27/ESP32-Locomotive-Basic/actions/runs/40207538056',
         'original_manifest_sha256':sha(upbytes), 'acquired_at':up['generated_at']},
       'oracle':{'name':'Caprice32','version':'4.6.0','commit':ORACLE,
         'model':'CPC6128','ram_kb':128,'keyboard':'English',
         'system_rom_sha256':up['oracle']['rom_sha256'],
         'amsdos_rom_sha256':up['oracle']['amsdos_rom_sha256'],
         'rom_files_committed':False},
       'historical_acceptance_gate_closed':False,'token_binary_captures':0,'cases':cases}
    target.mkdir(parents=True, exist_ok=True)
    (target/'manifest.json').write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n')
    verify(root,j)


def self_test(root, original):
    for case in ('path', 'ROM', 'channel', 'fake-match', 'tamper'):
        j=copy.deepcopy(original); first=j['cases'][0]
        if case=='path': first['files']['screenshot']['path']='../../outside.png'
        if case=='ROM': first['files']['screenshot']['path']='tests/fixtures/cpc6128/evidence/caprice32/minimal/system.rom'
        if case=='channel': first['files']['printer.dat']['kind']='visual_png'
        if case=='fake-match': first['comparison']['status']='MATCH_EXACT'
        if case=='tamper': first['files']['screenshot']['sha256']='0'*64
        try: verify(root,j)
        except (Invalid, OSError): continue
        raise Invalid('self-test failed, unsafe proof accepted: '+case)
    print('PASS: 5 negative security/integrity cases refused')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,help='unpacked original GitHub Actions artifact')
    p.add_argument('--self-test',action='store_true')
    args=p.parse_args()
    if args.archive: archive(ROOT,args.archive.resolve())
    else: verify(ROOT,json.loads((ROOT/BASE/'manifest.json').read_text()))
    if args.self_test: self_test(ROOT,json.loads((ROOT/BASE/'manifest.json').read_text()))


if __name__ == '__main__':
    try: main()
    except (Invalid,OSError,KeyError,ValueError,TypeError,UnicodeError) as exc:
        print('CPC EVIDENCE INVALID:',exc,file=sys.stderr);sys.exit(1)
