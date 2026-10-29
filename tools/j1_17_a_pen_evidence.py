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
# External SHA-256 pins observed in genuine GitHub Actions run 40956293250,
# obtained from actual raw files before bot commit 0f8d7e42f5c4cdb79964910d7271702cd289beed.
# Independently cross-checked against the downloaded 113-file Actions archive.
SEALED = {
    "P00": {
        "original": {
            "program": "87f5845113b49034f9d7729a8bcedc1b1915bd462b9cf43528ecc53b44707c50",
            "list_png": "c0c67ddbb81a959c819abf27df34af767a4019c94803e8257aecedb915772587",
            "run_png": "978e3a40eaade43385b8777f41ef9336ec99594a1088c5d5c728311f32ddb12a",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "23b08601771c2d6e0f67b9b91a3e8e31ab9056bd8ee231fac2b61b6c9f33df6b",
            "run_log": "1077fc6b6d4b71b64e974d4962fccf6f619262f77104b270e3dced5f9d8d055f",
            "capture": "8c674a4ed1e68be4fd00b407265c9b0103a6dd16ee3531906edb7aca533b5c97"
        },
        "repeat": {
            "program": "87f5845113b49034f9d7729a8bcedc1b1915bd462b9cf43528ecc53b44707c50",
            "list_png": "221e6b289427babf76f612bd8e120fcb9d9cfda96f10aa64ca90e76e30d96c91",
            "run_png": "ad4a5623346b5d2d63f40138d8e5655f5b4c1a86c952d22acabe0c2cac12aabe",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "ed08b4c692daab49143c4bc9c583f9c1bd3cc559e6c40febefa828fcdd76e9e0",
            "run_log": "ed68e749414ecc4a9f6187704080f8a3898d7853fb1f4e5dbb2c308d71be7f6c",
            "capture": "1ef0c7380dbce2a3fec46e5cab48078f6d73b2823b66fca7625cad842a1caf73"
        }
    },
    "P01": {
        "original": {
            "program": "6b7daf5d4833ea36c6f44b82865831c3e520b63bd4703b039a59ce24ee3dab43",
            "list_png": "54753dd2168b4e3ec6bf6f35bb5d76fc27a6ede038331b8a2455017af93d5e8d",
            "run_png": "af5d5e29e6fedbd29ae1a5030529eebe55cc95474d9a3e183358883ae5569f66",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "59a5106125766cf419dbdeffe2f1394d533607b026f6f2dec1b5a809049ce695",
            "run_log": "bb52760270077c85c6d886921e8e62aaa4164d88a460d38aac099da7d7c00bb9",
            "capture": "be55da2a8b3156350e2cda3d1c640d83156f26d287d493a2e275481d04080634"
        },
        "repeat": {
            "program": "6b7daf5d4833ea36c6f44b82865831c3e520b63bd4703b039a59ce24ee3dab43",
            "list_png": "767623276a98d6ba9f9de88c2355652fe5cd5de46d54379eecf659a8130e2d67",
            "run_png": "acf2d82d63ed83bc135c7ec935ec27a1686dd262b0170f152af73f7dca8c1f97",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "10ea2a391f56a1fd5d7cd216907b5cab242a73098fe57eb40f65872e6dabc124",
            "run_log": "6714cb0f3333d60f7ce938144fe228d94cb84e8ceb96503af8ad351a5a2b70ca",
            "capture": "d0b553a78cfbd6cb50bd13f61cc64d6e2a24a0d300fd20bde46a16c8862c4024"
        }
    },
    "P02": {
        "original": {
            "program": "110927fbdefcaf25a5f57e3f0d3962a1389c1e606d822ee48b09551af08d4169",
            "list_png": "2aca5587c2437adb2db68be0eea12aeb79d6ca1a36eb2e99f09d965ac2e99068",
            "run_png": "dd1ef54ec69a7bb3cedbc17807693533d1dde59457f6ef3608f024f734429cec",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "e2477ba42e55ae3adea95cbada5dd83950fe441515e62a0e78757c24018f553b",
            "run_log": "9f93df77682f5da4e99bcb04846cd3d180dce725afc928cf1fba012fa9f30c46",
            "capture": "e72d31816c69e63307ca8cd02db80f5bc5a5badc26c746f7cb5e8c07fa465fe5"
        },
        "repeat": {
            "program": "110927fbdefcaf25a5f57e3f0d3962a1389c1e606d822ee48b09551af08d4169",
            "list_png": "2aca5587c2437adb2db68be0eea12aeb79d6ca1a36eb2e99f09d965ac2e99068",
            "run_png": "bb3492546743d02e2a2cfd9bd8fc262d884d58bb9c5128e27dfd867dcd62e6d5",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "637fdebaa5e33da47d4e0ff42bce09b89f498cd66c975380d78a78f8ac43e949",
            "run_log": "a5db517e23511f857befcfcd6e673b87826b247a12aba2fa24ef6506b927d1f1",
            "capture": "a85ba02c89ecaff05d394c770d1ae95047e9a64bdb84feac3cf2ce27507f1875"
        }
    },
    "P03": {
        "original": {
            "program": "a47bbd36c2229206a200a6fee7a9b5e454b2fda98267925c895469f019cf8337",
            "list_png": "946c32eafaa96d48f6c36b52b0764632c3f23dfb6419f57fd1385a35534eef9f",
            "run_png": "9283b96a42709090d582bb0c2fb18ee4c500ead805e5627ad761cdaa9ee887fc",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "2c42d627a5d0544beda76ece51b8cf8ec6a3521be899f296092d90f4462ae1ef",
            "run_log": "30879afe084d408b5e9398ecfe95ea00444ebde2783e204575fb06c858ddb00c",
            "capture": "5b9bb9a2550b10fdd791d0a6f149007157ffdd82158eab1a4c90200ffedb859b"
        },
        "repeat": {
            "program": "a47bbd36c2229206a200a6fee7a9b5e454b2fda98267925c895469f019cf8337",
            "list_png": "998e1d5c9c4161da82b4bb8afc8c7178b8e6fa36ed11e71296b26882e6efe988",
            "run_png": "43b1dba9d0ad2c891be309fb9a0e4f1565562c230688d611fd06995caf89bf3c",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "b2e2c1657615549dc8eb70439cce844ae5bffb231881f8cf977b7185b3fe83db",
            "run_log": "3f8abcd1d878579ff52f388b0d29e783662a8a8042a959c4159dfb9dbd16682b",
            "capture": "a9c0c44c7f3fc7f0ab73ac0ff5d39ee84d1b6caf8c3c2299037eb9bd67bb94ce"
        }
    },
    "P04": {
        "original": {
            "program": "d9bd6058b8220280305c40b6215767abba5c2e3064d0b782721b4f6a1e599b30",
            "list_png": "3480a2ea297731c1f14d647453d68059c55dac0996475dfd9de00bf19fe59d61",
            "run_png": "069304b5824afe1cf70b7551ef6742c0174ebc95ef086d12e81e882d3d95348a",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "b4122bbc77676b9cabf52b2c9ece8c9b3023eaeb5a3c123d1811fa9afba97c89",
            "run_log": "d6b2ac770e07208402fbaff43d837458ccefd4da2588b104c06e31110171251f",
            "capture": "c5e18fcd570cbb24e1a6f4dcddf60ca2bb275b1a60a5a620b9fb1228b2217635"
        },
        "repeat": {
            "program": "d9bd6058b8220280305c40b6215767abba5c2e3064d0b782721b4f6a1e599b30",
            "list_png": "3b8f6409f074e3bd63cf791b11b12bb9cbeb52abc27a46e7c864e2049e5668c1",
            "run_png": "d2f6b28717c7863163a7c28521986ad74264907d78635c62054a20cdfc24db93",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "bf8911dfe4ef02684d3741415995f7773967c5c4a50056ad4beb7bd24a8a7054",
            "run_log": "88125691928356b45d76e569f1de1d2d99c590e5b43ade98e93147eb72372595",
            "capture": "bd03441cf3ae854658a1552c01873d2d9a202d207c17622458517caf76dfaeb3"
        }
    },
    "P15": {
        "original": {
            "program": "5197e59e15403951eb8fa49a90dd5e6b8b96bceade3ad5fced1e0b52d82ba9f8",
            "list_png": "17cdc02acf52b54d90bf875b48e96ca5470f505758e61928fced73a68219c790",
            "run_png": "3d742bc104d26092f5dc75e41fb44db881768970ae7565470532ee14493e449a",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "faa865b99a745aa122ab17b2dda2ebeccbeca505a672b45ee8fa6e0a235f74ef",
            "run_log": "efa6a63e662b29dd4e973721335a3194459dad11ef8c08a0298da667daada585",
            "capture": "0d06bb3add2a32c201a78ef25a5e9f11ea190954c48a61f309e73f0fb235b576"
        },
        "repeat": {
            "program": "5197e59e15403951eb8fa49a90dd5e6b8b96bceade3ad5fced1e0b52d82ba9f8",
            "list_png": "2c5867d7b9df650fcd1c8f18507e5d541f35f9ca80b173d815baf090e8514297",
            "run_png": "177d1c324c435733d24e75dc44036dbfb5abdbf118ca9f2eb90b1d3d736f6bf1",
            "printer": "37945bf7b406cce0ad7c77718e3e66d128ac15f3f81d6f389d32c5f6aed664f9",
            "list_log": "937205ea6a520c3bdfea2bccb81aae99f3b074e63615a40c271a26f8939e1e87",
            "run_log": "e99f6b33791edfc0eea79e49e0175bf5cd25d587a726bab59e0f29c34918c6ba",
            "capture": "e3b5628ccb8ed6096b92eeb4dfd54cdf9ca2b602bd9a14aa1c0464c71ac7c8cd"
        }
    },
    "P16": {
        "original": {
            "program": "6085d672786943e7b97af882eeb500e291b7aed2231619f68b2b585ca9dd4c23",
            "list_png": "0826e5a48ec7ffc9fccc1c7406d9324b3b7066182630281376be272f874ab904",
            "run_png": "1b90bb118d32a6ee8f50d01baab62c3b2a1ac1fd6248125c7a2635de71ea5f44",
            "printer": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
            "list_log": "7a6c75e00cfd9af3fa0f8dc5b430b72b5fe9b6924f3edcacddd7f04754521b3a",
            "run_log": "6bb36466ed8e4131319795780760d1a1dc90bf8a8dd8bfa6186663c9f6807eb9",
            "capture": "bb546ff543c0c04786a19f5cbce4c480197b3355573effc6e64c1a424350378f"
        },
        "repeat": {
            "program": "6085d672786943e7b97af882eeb500e291b7aed2231619f68b2b585ca9dd4c23",
            "list_png": "bc84340ed1f16fb3670ada7d5f2cc22f4963c77c31569f78f7f3c4d0c5351328",
            "run_png": "a3f28258a529afcc077e65091baa747a77c3ffb417f396af4fd0e2708f1097c5",
            "printer": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
            "list_log": "a81e0bcacd70239eb045626ce1f8e51afba276402c07bb01b58cc77fecf66f25",
            "run_log": "0da7044e7577237a476354695881e22b4d210364da167769cdd2bc48f5ee42c7",
            "capture": "9c6919a32574bef000bdf49fb30f1e91cd785512269f65c08affb5b72afa1ac0"
        }
    },
    "PN1": {
        "original": {
            "program": "87fa456563ba4baad738b3813aeddf549c5d8d3c16798497c6b0bd569f1641a0",
            "list_png": "2fcff4fad35844c0c931dfcd9e33ef1c6f8ef5751ab8db0d5999a0859a24a566",
            "run_png": "8ab70bcf642151de75435d2580b840cec6e9438cd857647db25206205076b9d4",
            "printer": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
            "list_log": "02ad689881b0667eeac9c1fe81c3e2271efa6342fcf784a5f2d2d3b944c4e7fd",
            "run_log": "9bbc614b60774d192d3a2bc3aad51b3034cebc6297479b59029b2e319220c4bf",
            "capture": "181aa74c086429911a13ae9d91e12845daabed7309917a2032467312785045e5"
        },
        "repeat": {
            "program": "87fa456563ba4baad738b3813aeddf549c5d8d3c16798497c6b0bd569f1641a0",
            "list_png": "34ae492d9bc09d9d7b7820fc13224c693c6ad993b4d36e800796c1a7211f9616",
            "run_png": "c688575d35ae8bec9e99a45c1763ebad9b456b45b0f15ac6d0a4e6ae4a2f11a0",
            "printer": "cc37406bf184f74205d65161d51646bd67a9101c7aad0a5623bb3a6aca4e5272",
            "list_log": "6e2e235eb24d725f11c4026850509d5d331074126a134b8328446a3ad24ba776",
            "run_log": "1c0bb14c740ce8a56be872dfd5d78b6b8e3a3359387a095b86803701baeaa2a4",
            "capture": "0257302c97a74d13dcecf2232b30c92b7934c1cd607494ab2b1f781be088f959"
        }
    }
}
SEALED_MANIFEST = 'ce35e39b71958f7eb721b8ee6559547def403920393979f710b3fda690da5106'


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
