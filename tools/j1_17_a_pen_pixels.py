#!/usr/bin/env python3
"""Independent J1.17-A RGB evidence verification for pinned CPC MODE 1 screens.

Pure Python PNG decoder (RGB8 non-interlaced, PNG filters 0..4); does not use
OCR, palette assumptions beyond the explicitly programmed ink references, or
printer output as a pixel oracle. Does NOT infer visually invisible glyphs.
"""
import argparse
import hashlib
from pathlib import Path
import struct
import sys
import zlib

CASES = ('P00', 'P01', 'P02', 'P03', 'P04', 'P15', 'P16', 'PN1')
SESSIONS = ('original','repeat')
WIDTH, HEIGHT = 768, 540
# Independently inspected first CPC acquisition: scaled glyph at LOCATE 1,15.
ROI = (64, 305, 190, 321)  # left,top,right,bottom (exclusive)
# CPC reference controls INK1=26 white; INK2=6 red; INK3=18 green.
# P15 is empirically same green under these commands; no extrapolation to INK.
REFERENCES = {'P01': (255,255,255), 'P02': (255,0,0),
              'P03': (0,255,0), 'P15': (0,255,0)}
BLACK = ('P00','P04','P16','PN1')
# Constrained to observed eight witnesses; these are *not* a general CPC palette.
EXPECTED_FOREGROUND_PIXELS = 684

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

def inspect(path, case):
    rows=png_rgb(path)
    x0,y0,x1,y1=ROI
    pixels={}
    for y in range(y0,y1):
        for x in range(x0,x1):
            color=tuple(rows[y][x*3:x*3+3])
            pixels[color]=pixels.get(color,0)+1
    expected=REFERENCES.get(case)
    fg={c:n for c,n in pixels.items() if c != (0,0,0)}
    need((not fg if case in BLACK else
          fg == {expected:EXPECTED_FOREGROUND_PIXELS}),
         'UNEXPECTED_PIXEL_RGB_'+case+':'+str(fg))
    need(pixels.get((0,0,0),0) + sum(fg.values()) == (x1-x0)*(y1-y0),
         'PNG_MISSING_BLACK_BACKGROUND_'+case)
    return {'roi':ROI,'rgb':expected if expected else (0,0,0),
            'foreground_pixels':sum(fg.values()),
            'black_background_pixels':pixels.get((0,0,0),0),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'classification':('GLYPH_RGB_OBSERVED' if case in REFERENCES
                              else 'BLACK_ROI_ONLY_GLYPH_NOT_DEMONSTRABLE')}

def verify(root):
    check=[]
    for case in CASES:
        pair=[]
        for session in SESSIONS:
            path=root/session/case/'run/screen.png'
            need(path.is_file() and not path.is_symlink(), 'SCREENSHOT_MISSING_'+case+session)
            measured=inspect(path,case)
            pair.append(measured)
            print('J1.17-A PIXEL',case,session,'ROI',ROI,'RGB',measured['rgb'],
                  'FG',measured['foreground_pixels'],'SHA',measured['sha256'],flush=True)
        need(pair[0]['rgb']==pair[1]['rgb'] and
             pair[0]['foreground_pixels']==pair[1]['foreground_pixels'],
             'PAIRED_RGB_DISAGREEMENT_'+case)
        check.append(case)
    print('J1.17-A RGB_MEASURED',len(check)*2,'SCREENS / 8 CASES',
          'GLYPHS_VERIFIED=4 CASES BLACK_ONLY=4 CASES', flush=True)

def negatives(root):
    # Falsification must never alter or overwrite the permanent archive.
    candidate=root/'original/P02/run/screen.png'
    original=candidate.read_bytes()
    import tempfile
    with tempfile.TemporaryDirectory(prefix='j117-pen-pixel-neg-') as td:
        bad=Path(td)/'bad.png'
        changed=bytearray(original);changed[-20]^=1;bad.write_bytes(changed)
        try:
            inspect(bad,'P02')
        except Invalid as err:
            print('J1.17-A PIXEL_FALSIFICATION_REJECTED',err,flush=True)
        else:
            raise Invalid('PIXEL_MUTATION_ACCEPTED')
        bad.write_bytes(original)
        try:
            inspect(bad,'P03')
        except Invalid as err:
            print('J1.17-A WRONG_RGB_CONTROL_REJECTED',err,flush=True)
        else:
            raise Invalid('FORGED_RGB_CONTROL_ACCEPTED')
    need(candidate.read_bytes()==original,'PERMANENT_PNG_MUTATED')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--self-test',action='store_true')
    a=p.parse_args()
    try:
        verify(a.evidence)
        if a.self_test: negatives(a.evidence)
    except (Invalid,OSError,zlib.error,struct.error) as e:
        print('J1.17-A PIXEL FAIL',e,file=sys.stderr)
        sys.exit(1)
