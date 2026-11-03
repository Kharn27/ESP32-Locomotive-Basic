#!/usr/bin/env python3
"""Auditor for a real A1-C0 UART log. It cannot validate TFT appearance."""
import argparse
import json
import math
import re
from pathlib import Path

FIELDS = re.compile(r'([A-Za-z0-9_]+)=([^\s]+)')


def fields(line):
    return dict(FIELDS.findall(line))


def quantiles(values):
    if not values:
        return None
    a = sorted(values)
    return {'count': len(a), 'min': a[0], 'p50': a[math.ceil(.5 * len(a))-1],
            'p95': a[math.ceil(.95 * len(a))-1], 'max': a[-1],
            'total': sum(a)}


def audit(lines, sha=None, min_runs=3):
    active = 'OFF'
    started = None
    samples = {'OFF': [], 'ON': []}
    full = {'OFF': [], 'ON': []}
    runs = {'OFF': [], 'ON': []}
    heads = set()
    config = None
    memory = []
    for line in lines:
        if 'HW4-C2 START ' in line and 'idf=v5.5.6' not in line:
            raise ValueError('expected ESP-IDF v5.5.6')
        if 'HW4-A1-C0 DMA_CONFIG ' in line:
            config = fields(line)
        if 'HW4-A1-C0 CONTROL ' in line:
            active = fields(line).get('mode')
            if active not in samples:
                raise ValueError('unknown mode')
        if 'HW4-A1-C0 STATS ' in line:
            heads.add(fields(line).get('boot_sha', ''))
        if 'HW4-C2 DEVICE_MEMORY ' in line:
            item = fields(line)
            if item.get('stage') in ('after_line','run_terminal','interactive_ready'):
                memory.append(item)
                if item.get('dma_fault') != '0' or item.get('dma_timeouts') != '0':
                    raise ValueError('LCD DMA fault')
                if int(item.get('stack_margin_bytes', '0')) <= 0:
                    raise ValueError('stack exhaustion')
        if 'HW4-A1-C0 REPAINT_SAMPLE ' in line:
            v = fields(line)
            mode = v['mode']
            if mode not in samples or mode != active or v['success'] != '1':
                raise ValueError('bad mode or incomplete repaint')
            dirty = int(v['logical_dirty_bands'])
            done = int(v['logical_completed'])
            physical = int(v['physical_dma_transfers'])
            byte_count = int(v['spi_pixel_bytes'])
            if not 0 < dirty <= 25 or done != dirty or byte_count != dirty*5120:
                raise ValueError('dirty or bytes mismatch')
            batch = v['path'] == 'BATCH16'
            if batch and not (mode == 'ON' and dirty == 25 and physical == 13):
                raise ValueError('out-of-scope batching')
            if not batch and (v['path'] != 'LEGACY8' or physical != dirty):
                raise ValueError('legacy DMA accounting')
            micros = int(v['repaint_us'])
            samples[mode].append(micros)
            if dirty == 25:
                full[mode].append(micros)
                if physical != (13 if batch else 25):
                    raise ValueError('full repaint physical count')
        if 'HW4-A1-C0 RUN_CLOCK ' in line:
            v = fields(line)
            tick = int(v['timestamp_us'])
            if v['edge'] == 'start':
                if started is not None or v['mode'] != active:
                    raise ValueError('nested RUN or mode change')
                started = (v['mode'],tick)
            elif v['edge'] == 'end':
                if started is None or v['mode'] != started[0] or tick < started[1]:
                    raise ValueError('unpaired RUN clock')
                runs[v['mode']].append(tick-started[1])
                started = None
            else:
                raise ValueError('invalid RUN edge')
        if 'HW4-C3-B2-C1 LCD_FAIL_STOP ' in line or 'HW4B DMA_FAIL ' in line:
            raise ValueError('LCD fail-stop')
    if started:
        raise ValueError('unfinished RUN')
    if (config is None or config.get('unique_buffer') != '1'
            or config.get('allocated_bytes') != '10240'
            or config.get('spi_hz') != '20000000'
            or config.get('cpu_mhz') != '160'
            or config.get('mode') != 'OFF'):
        raise ValueError('DMA/clock/default mode mismatch')
    if len(heads) != 1 or not re.fullmatch(r'[0-9a-f]{40}', next(iter(heads))):
        raise ValueError('missing full HEAD evidence')
    head = next(iter(heads))
    if sha is not None and head != sha:
        raise ValueError('flashed SHA mismatch')
    if not memory:
        raise ValueError('missing memory data')
    if min_runs and (any(len(runs[m]) < min_runs for m in runs)
                     or any(not full[m] for m in full)):
        raise ValueError('need >=3 RUN per mode and full25 witnesses')
    return {'head': head, 'default': 'OFF',
            'repaint_all_us': {k: quantiles(v) for k,v in samples.items()},
            'repaint_full25_us': {k: quantiles(v) for k,v in full.items()},
            'run_end_to_end_us': {k: quantiles(v) for k,v in runs.items()},
            'last_memory': memory[-1],
            'visual_quality': 'PO_UNVERIFIED',
            'acceptance': 'PILOTAGE_DECIDES'}


def self_test():
    head = 'a'*40
    lines = [
        'HW4-C2 START idf=v5.5.6',
        'HW4-A1-C0 DMA_CONFIG unique_buffer=1 allocated_bytes=10240 mode=OFF spi_hz=20000000 cpu_mhz=160',
        'HW4-A1-C0 STATS mode=OFF boot_sha=' + head,
        'HW4-C2 DEVICE_MEMORY stage=after_line dma_fault=0 dma_timeouts=0 stack_margin_bytes=4500'
    ]
    for mode, n in (('OFF',25),('ON',13)):
        if mode == 'ON':
            lines.append('HW4-A1-C0 CONTROL mode=ON')
        for i in range(3):
            begin = (1 if mode=='OFF' else 2)*1000000+i*10000
            lines.extend([
                f'HW4-A1-C0 RUN_CLOCK edge=start mode={mode} timestamp_us={begin}',
                f'HW4-A1-C0 REPAINT_SAMPLE mode={mode} path={"BATCH16" if n==13 else "LEGACY8"} logical_dirty_bands=25 logical_completed=25 physical_dma_transfers={n} spi_pixel_bytes=128000 repaint_us={60000+i} text_scrolls_total=1 success=1',
                f'HW4-A1-C0 RUN_CLOCK edge=end mode={mode} timestamp_us={begin+100000}',
            ])
    result = audit(lines, sha=head)
    assert result['repaint_full25_us']['ON']['count'] == 3
    for needle,replacement in (
        ('physical_dma_transfers=13','physical_dma_transfers=12'),
        ('spi_pixel_bytes=128000','spi_pixel_bytes=127999'),
        ('logical_completed=25','logical_completed=24'),
        ('success=1','success=0'),
    ):
        bad = [line.replace(needle,replacement) for line in lines]
        try:
            audit(bad,sha=head)
        except ValueError:
            continue
        raise AssertionError('invalid UART escaped: '+replacement)
    print('HW4-A1-C0 AUDITOR synthetic_positive=PASS negatives=4/4 PASS NO_CYD')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('uart',type=Path,nargs='?')
    ap.add_argument('--expect-sha')
    ap.add_argument('--out',type=Path)
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        self_test()
    elif args.uart:
        result=audit(args.uart.read_text(errors='replace').splitlines(),
                     sha=args.expect_sha)
        output=json.dumps(result,indent=2,ensure_ascii=False)
        if args.out:
            args.out.write_text(output+'\n')
        print(output)
    else:
        ap.error('UART capture required or --self-test')
