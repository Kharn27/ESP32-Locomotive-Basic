#!/usr/bin/env python3
"""J1.18-A independent CRC-checked CPC RGB measurements, no palette assumptions.

A frozen glyph ROI is applied to baseline and RUN snapshots. Measurements
are pixels, not guesses based on INK indices or PRINT #8. Two chronological
captures in ONE emulator process test repaint without a second PRINT.
"""
import argparse
import hashlib
from pathlib import Path
import struct
import sys
import zlib

CASES = ('I00','I126','I106','I206','I318','I1526','I127',
         'I131','I1266','I1626','IN126','I132','I1N1')
SESSIONS = ('original','repeat')
WIDTH, HEIGHT = 768, 540
# Independently inspected first CPC acquisition: scaled glyph at LOCATE 1,15.
ROI = (64, 305, 190, 321)  # left,top,right,bottom (exclusive)

class Invalid(ValueError):
    pass

def need(ok, reason):
    if not ok:
        raise Invalid(reason)

def png_rgb(path):
    data = path.read_bytes()
    need(data[:8] == b'\x89PNG\r\n\x1a\n', 'PNG_SIGNATURE')
    pos, parts, palette, seen, width, height = 8, [], None, set(), 0, 0
    while pos+12 <= len(data):
        size=struct.unpack_from('>I',data,pos)[0]
        need(size <= 8*1024*1024 and pos+12+size <= len(data), 'PNG_CHUNK_LENGTH')
        kind=data[pos+4:pos+8]; value=data[pos+8:pos+8+size]
        actual=struct.unpack_from('>I',data,pos+8+size)[0]
        need(zlib.crc32(value,zlib.crc32(kind)) & 0xffffffff == actual,
             'PNG_CRC_'+kind.decode('latin1'))
        if kind == b'IHDR':
            need(pos == 8 and size == 13, 'PNG_IHDR_POSITION')
            width,height,depth,ctype,comp,filter_method,interlace=struct.unpack('>IIBBBBB',value)
            need((width,height,depth,ctype,comp,filter_method,interlace) ==
                 (WIDTH,HEIGHT,8,2,0,0,0), 'PNG_UNSUPPORTED_FORMAT')
        elif kind == b'IDAT':
            parts.append(value)
        elif kind == b'IEND':
            need(size==0 and pos+12 == len(data),'PNG_END_POSITION')
            seen.add(kind)
            break
        elif kind not in (b'gAMA',b'sRGB',b'pHYs',b'tEXt',b'tIME',b'iCCP',b'cHRM',b'bKGD',b'sBIT'):
            # Whitelist no ancillary unknowns, fail closed for source changes.
            raise Invalid('PNG_UNEXPECTED_CHUNK_'+kind.decode('latin1'))
        pos += 12+size
    need(b'IEND' in seen and width == WIDTH and height == HEIGHT and parts, 'PNG_STRUCTURE')
    raw=zlib.decompress(b''.join(parts))
    stride=width*3
    need(len(raw)==height*(1+stride),'PNG_DECOMPRESSED_SIZE')
    result=[]; previous=bytearray(stride); start=0
    for y in range(height):
        kind=raw[start]; start+=1
        need(kind in range(5), 'PNG_FILTER')
        cur=bytearray(raw[start:start+stride]); start+=stride
        for x in range(stride):
            a=cur[x-3] if x>=3 else 0
            b=previous[x]
            c=previous[x-3] if x>=3 else 0
            if kind==1: adj=a
            elif kind==2: adj=b
            elif kind==3: adj=(a+b)//2
            elif kind==4:
                p=a+b-c
                distances=(abs(p-a),abs(p-b),abs(p-c))
                adj=(a,b,c)[distances.index(min(distances))]
            else: adj=0
            cur[x]=(cur[x]+adj)&0xff
        result.append(cur)
        previous=cur
    return result


import json
import tempfile

def histogram(path, roi=ROI):
    rows=png_rgb(path)
    x0,y0,x1,y1=roi
    need(0 <= x0 < x1 <= WIDTH and 0 <= y0 < y1 <= HEIGHT, 'ROI_OUTSIDE_IMAGE')
    colors={}
    for y in range(y0,y1):
        for x in range(x0,x1):
            v=tuple(rows[y][x*3:x*3+3])
            colors[v]=colors.get(v,0)+1
    need(sum(colors.values())==(x1-x0)*(y1-y0),'ROI_PIXEL_COUNT')
    need(len(colors)<=256,'ROI_TOO_MANY_UNEXPECTED_COLORS')
    return {'roi':list(roi),
            'pixels':{','.join(map(str,k)):v for k,v in sorted(colors.items())},
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def glyph_mask(path, baseline=(0,0,0)):
    rows=png_rgb(path)
    x0,y0,x1,y1=ROI
    return {(x,y) for y in range(y0,y1) for x in range(x0,x1)
            if tuple(rows[y][x*3:x*3+3])!=baseline}

def inspect(root):
    report={'phase':'J1.18-A','roi':list(ROI),'cases':{},'chronology':{}}
    for case in CASES:
        sessions={}
        for sess in SESSIONS:
            item=root/sess/case
            baseline=histogram(item/'baseline/screen.png')
            run=histogram(item/'run/screen.png')
            sessions[sess]={'baseline':baseline,'run':run}
            print('J1.18-A PIXEL',case,sess,
                  'BASE',baseline['pixels'],'RUN',run['pixels'],flush=True)
        same_run=sessions['original']['run']['pixels']==sessions['repeat']['run']['pixels']
        same_baseline=sessions['original']['baseline']['pixels']==sessions['repeat']['baseline']['pixels']
        report['cases'][case]={'sessions':sessions,
           'classification':('RGB_OBSERVED' if same_run and same_baseline
                             else 'VISUAL_UNVERIFIED'),
           'pair_equal':same_run,'controls_equal':same_baseline,
           'temporal_classification':('TEMPORAL_UNVERIFIED' if case=='I1266'
                                       else 'NOT_APPLICABLE')}
    for sess in SESSIONS:
        p=root/sess/'chronology'
        before=histogram(p/'screen_0.png')
        after=histogram(p/'screen_1.png')
        report['chronology'][sess]={'before':before,'after':after,
                                    'no_new_print':True}
        print('J1.18-A CHRONO_RGB',sess,
              'BEFORE',before['pixels'],'AFTER',after['pixels'],flush=True)
    # Same chronology across two new emulator processes, not a PNG-only
    # attempt to prove retroactive recoloring if temporal frames disagree.
    a=report['chronology']['original']
    b=report['chronology']['repeat']
    same=a['before']['pixels']==b['before']['pixels'] and a['after']['pixels']==b['after']['pixels']
    altered=a['before']['pixels']!=a['after']['pixels']
    report['chronology_classification']=(
        'TWO_FRAME_RGB_CHANGE_OBSERVED' if same and altered else 'VISUAL_UNVERIFIED')
    print('J1.18-A TWO_FRAME_CHRONOLOGY',report['chronology_classification'],
          'BOTH_SESSIONS_CONCORDANT',same,'CHANGED',altered,flush=True)
    return report

def negatives(root):
    src=root/'original/I106/run/screen.png'
    data=src.read_bytes()
    with tempfile.TemporaryDirectory(prefix='j118-pixel-forgery-') as temp:
        changed=bytearray(data); changed[-20]^=1
        p=Path(temp)/'tampered.png'
        p.write_bytes(changed)
        try: histogram(p)
        except (Invalid,zlib.error,struct.error) as e:
            print('J1.18-A PNG_CRC_FALSIFICATION_REJECTED',str(e),flush=True)
        else: raise Invalid('FORGED_PNG_ACCEPTED')
        try: histogram(src,(WIDTH+1,0,WIDTH+2,1))
        except (Invalid,IndexError) as e:
            print('J1.18-A ROI_FALSIFICATION_REJECTED',str(e),flush=True)
        else: raise Invalid('FORGED_ROI_ACCEPTED')
    need(src.read_bytes()==data,'ORIGINAL_PNG_CHANGED')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--report',type=Path)
    p.add_argument('--self-test',action='store_true')
    args=p.parse_args()
    try:
        findings=inspect(args.evidence)
        if args.report:
            args.report.write_text(json.dumps(findings,sort_keys=True,indent=2)+'\n')
        if args.self_test: negatives(args.evidence)
    except (Invalid,OSError,zlib.error,struct.error,IndexError) as err:
        print('J1.18-A PIXEL FAIL',err,file=sys.stderr)
        sys.exit(1)
