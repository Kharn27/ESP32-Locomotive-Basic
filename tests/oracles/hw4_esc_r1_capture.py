#!/usr/bin/env python3
"""Caprice32 ESC keyboard oracle candidate acquisition (never an oracle verdict)."""
import argparse
import configparser
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

PIN = '8c778bf072a06fb7c23b9cccd179041db7f79a52'
ROM_SHA = '31c3668c67bea027dab698ece233c9434d9324f9ba7dac84db58f400b6689562'
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
# Each case is an independent cold-boot ROM session.
CASES = {
    'control_raw_esc': (['10 PRINT "A":GOTO 10'], ['shot:running', 'raw', 'shot:raw_host_byte', 'cpc', 'shot:cpc_first', 'cpc', 'shot:cpc_second']),
    'E01': (['10 GOTO 10'], ['shot:running', 'cpc', 'shot:paused', 'shot:pause_persistent']),
    'E02': (['10 GOTO 10'], ['cpc', 'shot:paused', 'text:x', 'shot:after_x', 'cpc', 'cpc', 'shot:after_break']),
    'E03': (['10 GOTO 10'], ['shot:running', 'cpc', 'shot:after_first', 'cpc', 'shot:after_second']),
    'E04': (['10 GOTO 10'], ['cpc', 'cpc', 'shot:break', 'text:CONT\n', 'shot:after_CONT', 'cpc', 'cpc', 'shot:break_after_CONT']),
    'E05': (['10 PRINT "A":GOTO 20', '20 PRINT "B":GOTO 10'], ['shot:running', 'cpc', 'shot:paused', 'shot:pause_persistent', 'cpc', 'shot:break']),
    'E10': ([], ['shot:boot', 'text:CONT\n', 'shot:without_context']),
    'E07_candidate': (['10 A%=A%+1:LOCATE 1,1:PRINT A%;:GOTO 10'], ['shot:running', 'cpc', 'shot:paused', 'cpc', 'shot:break', 'text:PRINT A%\n', 'shot:variable', 'text:CONT\n', 'shot:after_CONT', 'cpc', 'cpc', 'shot:after_second_break']),
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def enum_value(text, key, end_type):
    match = re.search(r'typedef\s+enum\s*\{([^{}]*)\}\s*' + re.escape(end_type) + r'\s*;', text, re.S)
    if match is None:
        raise RuntimeError('enum not found: ' + end_type)
    entries = [x.strip() for x in match.group(1).split(',')]
    names = [x.split('=')[0].strip() for x in entries]
    if names.count(key) != 1:
        raise RuntimeError('key not unique: ' + key)
    return names.index(key)


def make_tail(events, cpc_esc):
    # Caprice32's StringToEvents: BEL + enum index -> CPC key via SDL map;
    # raw ASCII ESC 0x1B does NOT use the BEL escape prefix.
    tokens = []
    checkpoints = []
    for action in events:
        if action == 'cpc':
            tokens.append('\x07' + chr(cpc_esc))
        elif action == 'raw':
            tokens.append('\x1b')
        elif action.startswith('text:'):
            tokens.append(action[5:])
        elif action.startswith('shot:'):
            tokens.append('CAP32_DELAY' * 2 + 'CAP32_SCRNSHOT' + 'CAP32_DELAY' * 2)
            checkpoints.append(action[5:])
        else:
            raise RuntimeError('bad action: ' + action)
    tokens.append('CAP32_EXIT')
    return ''.join(tokens), checkpoints


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--caprice', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--case', action='append', choices=CASES)
    args = p.parse_args()
    cap = args.caprice.resolve()
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError('output must not exist; stale captures forbidden')
    output.mkdir(parents=True)
    def command(*argv):
        return subprocess.check_output(argv, text=True, stderr=subprocess.STDOUT).strip()
    commit = command('git', '-C', str(cap), 'rev-parse', 'HEAD')
    if commit != PIN:
        raise RuntimeError('Caprice SHA mismatch: ' + commit)
    rom = cap / 'rom' / 'cpc6128.rom'
    if not rom.is_file() or len(rom.read_bytes()) != 32768 or sha256(rom) != ROM_SHA:
        raise RuntimeError('ROM missing, incorrect size or SHA')
    exe = cap / 'cap32'
    if not exe.is_file():
        raise RuntimeError('Caprice executable missing')
    header = (cap / 'src/keyboard.h').read_text()
    mapping = (cap / 'src/keyboard.cpp').read_text()
    argcode = (cap / 'src/argparse.cpp').read_text()
    cpc_esc = enum_value(header, 'CPC_ESC', 'CPC_KEYS')
    if not 0 < cpc_esc < 256 or not re.search(r'0x82\s*,\s*// CPC_ESC', mapping):
        raise RuntimeError('CPC_ESC hardware scancode guard failed')
    if not re.search(r'\{\s*CPC_ESC\s*,\s*SDLK_ESCAPE\s*\}', mapping):
        raise RuntimeError('CPC_ESC SDL mapping guard failed')
    if 'if (c == \'\\a\')' not in mapping or 'SDLkeysFromChars[c]' not in mapping:
        raise RuntimeError('BEL injection path not independently checked')
    if 'replaceCap32Keys(optarg)' not in argcode:
        raise RuntimeError('autocmd key replacement changed')
    version = command(str(exe), '--version')
    cfgsrc = cap / 'cap32.cfg'
    manifest = {'schema': 1, 'acquisition_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'CANDIDATE_NOT_VISUALLY_VERIFIED',
                'environment': {'caprice_commit': commit, 'caprice_version': version,
                                'rom_sha256': sha256(rom), 'model': 'CPC6128',
                                'keyboard': 'original English', 'cpc_esc_enum': cpc_esc,
                                'cpc_esc_scancode': '0x82',
                                'input_proof': 'BEL+CPC_ESC enum -> SDL_ESCAPE -> CPC matrix',
                                'negative_control': 'raw 0x1B without BEL prefix'},
                'sessions': []}
    env = dict(os.environ, SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='x11')
    for name in args.case or CASES:
        program, steps = CASES[name]
        work = output / name
        work.mkdir()
        cfg = configparser.ConfigParser(interpolation=None)
        if not cfg.read(cfgsrc):
            raise RuntimeError('cap32.cfg unavailable')
        cfg['system'].update(model='2', ram_size='128', speed='4', auto_pause='0',
                             printer='0', mf2='0', keyboard='0', boot_time='42', limit_speed='1')
        cfg['control']['kbd_layout'] = '0'
        cfg['sound']['enabled'] = '0'
        cfg['video'].update(scr_style='1', scr_window='1', scr_scale='2')
        cfg['file']['sdump_dir'] = str(work)
        cfg['rom']['rom_path'] = str(cap / 'rom')
        cfg['rom']['slot07'] = 'amsdos.rom' if (cap / 'rom/amsdos.rom').is_file() else ''
        cfg['rom']['rom_mf2'] = ''
        cfg['system']['resources_path'] = str(cap / 'resources')
        with (work / 'cap32.cfg').open('w') as f:
            cfg.write(f, space_around_delimiters=False)
        tail, checkpoints = make_tail(steps, cpc_esc)
        # Each -a automatically appends ENTER. The tail is ONE -a to avoid
        # injected ENTER between checkpoint screenshots and CPC ESC events.
        argv = ['xvfb-run', '-a', str(exe), '-c', str(work / 'cap32.cfg')]
        for line in program:
            argv += ['-a', line]
        if name != 'E10':
            argv += ['-a', 'RUN']
        argv += ['-a', tail]
        steps_json = {'program': program, 'steps': steps, 'tail_hex': tail.encode().hex(),
                      'checkpoint_labels': checkpoints, 'command_provenance':
                      'Caprice32 argv -a, macro BEL+CPC_ESC enum; no host UART'}
        (work / 'events.json').write_text(json.dumps(steps_json, indent=2) + '\n')
        try:
            result = subprocess.run(argv, cwd=cap, env=env, capture_output=True, timeout=240)
        except subprocess.TimeoutExpired as exc:
            (work / 'caprice.log').write_bytes((exc.stdout or b'') + b'\nTIMEOUT\n' + (exc.stderr or b''))
            raise RuntimeError(f'{name} timed out') from exc
        (work / 'caprice.log').write_bytes(b'returncode=' + str(result.returncode).encode() +
                                          b'\n[stdout]\n' + result.stdout + b'\n[stderr]\n' + result.stderr)
        pngs = sorted(work.glob('screenshot_*.png'))
        print(f'{name}: rc={result.returncode}; pngs={len(pngs)}/{len(checkpoints)}', flush=True)
        if result.returncode != 0 or len(pngs) != len(checkpoints):
            print((work / 'caprice.log').read_text(errors='replace')[-5000:], file=sys.stderr)
            raise RuntimeError(f'{name}: missing or overlapping PNG capture')
        entries = []
        for label, png in zip(checkpoints, pngs):
            if not png.read_bytes().startswith(PNG_MAGIC) or png.stat().st_size < 1024:
                raise RuntimeError(f'{name}: invalid PNG {png}')
            entries.append({'checkpoint': label, 'original_png': str(png.relative_to(output)),
                            'sha256': sha256(png), 'bytes': png.stat().st_size})
        manifest['sessions'].append({'case': name, 'program': program, 'steps': steps,
                    'capture_status': 'PNG_ACQUIRED_NOT_YET_TRANSCRIBED',
                    'images': entries, 'log_sha256': sha256(work / 'caprice.log'),
                    'events_sha256': sha256(work / 'events.json'),
                    'config_sha256': sha256(work / 'cap32.cfg')})
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('R1 acquisition candidates complete: independent screenshot bytes, NO CPC ORACLE VERDICT', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('HW4-ESC-R1 CAPTURE FAILURE:', exc, file=sys.stderr)
        raise SystemExit(1)
