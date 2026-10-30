#!/usr/bin/env python3
"""J1.20-A: genuinely run CPC6128/BASIC 1.1 ABS integer oracle.

No native ABS implementation. First acquisition is UNSEALED; external SHA
pins are separately added only after archive commit and independent CI logs.
"""
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
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/oracles'))
sys.path.insert(0,str(ROOT/'tools'))
import token_ram_oracle as cpc
import j1_18_a_ink_evidence as ink

CASES={
 'A00': '10 PRINT ABS(0)\n20 PRINT #8,ABS(0)\n30 END\n',
 'A01': '10 PRINT ABS(1)\n20 PRINT #8,ABS(1)\n30 END\n',
 'AN1': '10 PRINT ABS(-1)\n20 PRINT #8,ABS(-1)\n30 END\n',
 'V07': '10 A%=7\n20 PRINT ABS(A%)\n30 PRINT #8,ABS(A%)\n40 END\n',
 'VN7': '10 A%=-7\n20 PRINT ABS(A%)\n30 PRINT #8,ABS(A%)\n40 END\n',
 'VMAX': '10 A%=32767\n20 PRINT ABS(A%)\n30 PRINT #8,ABS(A%)\n40 END\n',
 'VNMAX': '10 A%=-32767\n20 PRINT ABS(A%)\n30 PRINT #8,ABS(A%)\n40 END\n',
 'VMIN': '10 A%=-32768\n20 PRINT ABS(A%)\n30 PRINT #8,ABS(A%)\n40 END\n',
 'B07': '10 A%=7\n20 B%=ABS(A%)\n30 PRINT B%\n40 PRINT #8,B%\n50 END\n',
 'BN7': '10 A%=-7\n20 B%=ABS(A%)\n30 PRINT B%\n40 PRINT #8,B%\n50 END\n',
 'BMIN': '10 A%=-32768\n20 B%=ABS(A%)\n30 PRINT B%\n40 PRINT #8,B%\n50 END\n',
 'IMIN': '10 PRINT ABS(-32768)\n20 PRINT #8,ABS(-32768)\n30 END\n',
 'L20': '10 REM CHECK LINE 20\n20 PRINT ABS(-32768)\n30 PRINT #8,ABS(-32768)\n40 END\n',
 'EMPTY': '10 PRINT ABS()\n20 PRINT #8,88\n30 END\n',
 'STRING': '10 PRINT ABS("X")\n20 PRINT #8,88\n30 END\n',
 'MULTI': '10 PRINT ABS(1,2)\n20 PRINT #8,88\n30 END\n',
}
SESSIONS=('original','repeat')
PHASE='J1.20-A'
DEST=ROOT/'tests/fixtures/cpc6128/j1_20_a_abs'
SOURCES=ROOT/'tests/oracles/inputs/j1_20_a'
GHCR=ink.GHCR
# To be inserted FROM FIRST REAL CI ACQUISITION LOGS after archived Git commit.
SEALED_MANIFEST=''
SEALED={}
ACQUISITION_HEAD=''
SCREEN_SENTINEL=b'@@ABS-SCREEN@@'
ERR_SENTINEL=b'@@ABS-ERR@@'
SETUP=['MODE 1','NEW']

class Invalid(ValueError): pass
def check(ok,why):
    if not ok: raise Invalid(why)
def read(p):
    check(p.is_file() and not p.is_symlink(),'MISSING_'+str(p))
    return p.read_bytes()
def sha(data): return hashlib.sha256(data).hexdigest()
def enc(x): return (json.dumps(x,sort_keys=True,indent=2)+'\n').encode('ascii')
def source(case):
    expected=CASES[case].encode('ascii')
    check(read(SOURCES/(case.lower()+'.bas'))==expected,'SOURCE_DRIFT_'+case)
    return expected
def rows(case):
    return [int(line.split(' ',1)[0]) for line in CASES[case].splitlines()]
def png_ok(raw):
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'): return False
    pos=8; found=False
    while pos+12<=len(raw):
        length=int.from_bytes(raw[pos:pos+4],'big')
        kind=raw[pos+4:pos+8]
        end=pos+12+length
        if end>len(raw): return False
        got=int.from_bytes(raw[end-4:end],'big')
        if zlib.crc32(raw[pos+4:end-4])&0xffffffff!=got: return False
        pos=end
        if kind==b'IEND':
            found=True;break
    return found and pos==len(raw)

def snapshot_program(snapshot):
    check(len(snapshot)==cpc.HEADER+cpc.RAM_BYTES,'SNA_SIZE')
    ram=memoryview(snapshot)[cpc.HEADER:]
    start=cpc.u16(ram,cpc.PROGRAM_BASE_PTR)+1
    end=cpc.u16(ram,cpc.PROGRAM_END_PTR)
    check(0x170<=start<end<=0x8000,'PROGRAM_POINTERS')
    data=bytes(ram[start:end])
    numbers,_=cpc.records(data)
    validated,region=cpc.extract_snapshot(snapshot,numbers)
    check(data==validated,'SNA_EXTRACTION')
    return data,region,numbers

def check_head(head):
    check(bool(re.fullmatch('[a-f0-9]{40}',head)),'INVALID_HEAD')
    actual=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    check(head==actual,'EXPECTED_HEAD_MISMATCH')
    return head

def capture_one(cap,out,case,session,tmp):
    src=source(case)
    work=out/session/case
    lsnap=tmp/(case+'-'+session)
    lsnap.mkdir()
    initial=SETUP+src.decode('ascii').splitlines()
    list_commands=initial+['LIST','CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT CAP32_SNAPSHOT CAP32_EXIT']
    lt=ink.launch(cap,work/'list',lsnap,list_commands,False)
    snapshots=list(lsnap.glob('*.sna'))
    check(len(snapshots)==1,'SNA_MISSING_'+case+session)
    program,region,found=snapshot_program(read(snapshots[0]))
    (work/'program.bin').write_bytes(program)
    # Program result is printed both on-screen and to the CPC #8 printer
    # by the SOURCE itself. The post-RUN ERR/ERL probe is separate.
    # Screen extraction is performed AFTER the screenshot and ERR/ERL probe,
    # with COPYCHR$ (#0) from the CPC firmware, not desktop OCR.
    run_commands=initial+['RUN','CAP32_DELAY CAP32_DELAY CAP32_SCRNSHOT',
                          'PRINT #8,"@@ABS-ERR@@";ERR;",";ERL',
                          'PRINT #8,"@@ABS-SCREEN@@"',
                          'FOR YY=1 TO 25:FOR XX=1 TO 40:LOCATE XX,YY:PRINT #8,COPYCHR$(#0);:NEXT XX:PRINT #8:NEXT YY',
                          'CAP32_DELAY CAP32_EXIT']
    rt=ink.launch(cap,work/'run',tmp,run_commands,True)
    raw=read(work/'run/printer.dat')
    idx=raw.find(ERR_SENTINEL)
    check(idx>=0,'ERR_ERL_MARKER_MISSING_'+case+session)
    prefix=raw[:idx]
    tail=raw[idx+len(ERR_SENTINEL):]
    match=re.match(rb'\s*([0-9]+)\s*,\s*([0-9]+)\s*[\r\n]+',tail)
    check(match is not None,'ERR_ERL_NUMERIC_PROBE_'+case+session+repr(tail[:120]))
    err=int(match.group(1));erl=int(match.group(2))
    screen_pos=tail.find(SCREEN_SENTINEL,match.end())
    screen_text=tail[screen_pos+len(SCREEN_SENTINEL):] if screen_pos>=0 else b''
    lines=screen_text.splitlines()
    screen_class='TEXT_SCREEN_OBSERVED' if len(lines)==25 else 'DIAG_CPC_UNVERIFIED'
    case_class='INPUT_REJECTED' if found!=rows(case) else 'OBSERVED'
    rec={'case':case,'session':session,'source_sha256':sha(src),
         'line_numbers_requested':rows(case),'line_numbers_observed':found,
         'input_classification':case_class,'token_classification':
          'TOKEN_UNVERIFIED' if case_class!='OBSERVED' else 'OBSERVED',
         'program_sha256':sha(program),'program_hex':program.hex(' ').upper(),
         'region':region,'run_printer_sha256':sha(raw),
         'result_printer_hex':prefix.hex(' ').upper(),
         'err':err,'erl':erl,'list':lt,'run':rt,
         'list_image_sha256':sha(read(work/'list/screen.png')),
         'run_image_sha256':sha(read(work/'run/screen.png')),
         'screen_text_hex':screen_text.hex(' ').upper(),
         'screen_text_classification':screen_class,
         'screen_rows':len(lines),
         'diagnostic_classification':'DIAG_CPC_UNVERIFIED',
         'type_classification':'TYPE_UNVERIFIED',
         'setup_commands':SETUP,'list_commands':list_commands,
         'run_commands':run_commands,'printer_is_not_screen_evidence':True,
         'snapshot_before_run':True,'full_snapshot_archived':False}
    (work/'capture.json').write_bytes(enc(rec))
    print(PHASE,case,session,'INPUT',case_class,'RAM',program.hex(' ').upper(),
          'RESULT',prefix.hex(' ').upper(),'ERR',err,'ERL',erl,
          'SCREEN_ROWS',len(lines),flush=True)
    return rec

def acquire(cap,out,head):
    check(not out.exists(),'OUTPUT_EXISTS')
    version=ink.check_caprice(cap)
    out.mkdir(parents=True)
    manifest={'schema_version':1,'phase':PHASE,'acquisition_head':head,
              'run_id':os.environ.get('GITHUB_RUN_ID','LOCAL'),
              'oracle':{'caprice':cpc.PIN,'rom':cpc.ROM_SHA,
                        'ghcr':GHCR,'version':version,
                        'model':'CPC6128','basic':'1.1'},
              'native_changes':False,'full_snapshots_archived':False,'cases':{}}
    with tempfile.TemporaryDirectory(prefix='j120-abs-sna-') as tmp:
        t=Path(tmp)
        for case in CASES:
            observed={}
            for session in SESSIONS:
                observed[session]=capture_one(cap,out,case,session,t)
            check(observed['original']['program_hex']==observed['repeat']['program_hex'],
                  'INDEPENDENT_RAM_MISMATCH_'+case)
            check((observed['original']['err'],observed['original']['erl'],
                   observed['original']['result_printer_hex'])==
                  (observed['repeat']['err'],observed['repeat']['erl'],
                   observed['repeat']['result_printer_hex']),
                  'INDEPENDENT_RUN_MISMATCH_'+case)
            manifest['cases'][case]={s:sha(read(out/s/case/'capture.json'))
                                     for s in SESSIONS}
    (out/'manifest.json').write_bytes(enc(manifest))
    verify(out)
    print(PHASE,'FRESH_CPC_SESSIONS',2*len(CASES),'UNSEALED',head,flush=True)

def verify(out,permanent=False):
    m=json.loads(read(out/'manifest.json'))
    check(m['phase']==PHASE and m['schema_version']==1 and
          m['oracle']['caprice']==cpc.PIN and m['oracle']['rom']==cpc.ROM_SHA and
          m['oracle']['ghcr']==GHCR and m['native_changes'] is False and
          m['full_snapshots_archived'] is False and
          set(m['cases'])==set(CASES) and
          bool(re.fullmatch('[a-f0-9]{40}',m['acquisition_head'])),
          'MANIFEST_PROVENANCE')
    check(subprocess.run(['git','-C',str(ROOT),'merge-base','--is-ancestor',
                          m['acquisition_head'],'HEAD'],capture_output=True).returncode==0,
          'FALSE_ACQUISITION_HEAD')
    inventory={str(p.relative_to(out)):sha(read(p)) for p in out.rglob('*') if p.is_file()}
    check('manifest.json' in inventory,'MISSING_MANIFEST')
    if permanent:
        check(m['acquisition_head']==ACQUISITION_HEAD and
              sha(read(out/'manifest.json'))==SEALED_MANIFEST and
              bool(SEALED) and set(SEALED)==set(inventory)-{'manifest.json'},
              'EXTERNAL_MANIFEST_OR_INVENTORY')
        for key,digest in SEALED.items():
            check(inventory[key]==digest,'EXTERNAL_FILE_SHA_'+key)
    for case in CASES:
        pair=[]
        for session in SESSIONS:
            work=out/session/case
            recdata=read(work/'capture.json')
            d=json.loads(recdata)
            program=read(work/'program.bin')
            raw=read(work/'run/printer.dat')
            found,details=cpc.records(program)
            expected_class='OBSERVED' if found==rows(case) else 'INPUT_REJECTED'
            check(d['source_sha256']==sha(source(case)) and
                  d['program_sha256']==sha(program) and
                  d['program_hex']==program.hex(' ').upper() and
                  d['line_numbers_observed']==found and
                  d['line_numbers_requested']==rows(case) and
                  d['input_classification']==expected_class and
                  d['token_classification']==('OBSERVED' if expected_class=='OBSERVED' else 'TOKEN_UNVERIFIED') and
                  d['snapshot_before_run'] and not d['full_snapshot_archived'] and
                  d['setup_commands']==SETUP and d['case']==case and d['session']==session and
                  sha(recdata)==m['cases'][case][session],
                  'CASE_PROVENANCE_'+case+session)
            for kind in ('list','run'):
                png=read(work/kind/'screen.png')
                log=read(work/kind/'caprice.log')
                check(png_ok(png) and log.startswith(b'exit code: 0\n') and
                      d[kind]['screenshot_width']==int.from_bytes(png[16:20],'big') and
                      d[kind]['screenshot_height']==int.from_bytes(png[20:24],'big') and
                      sha(png)==d[kind+'_image_sha256'],
                      'PNG_CRC_OR_PROCESS_'+case+session+kind)
            check(sha(raw)==d['run_printer_sha256'] and
                  d['diagnostic_classification']=='DIAG_CPC_UNVERIFIED' and
                  d['type_classification']=='TYPE_UNVERIFIED',
                  'UNVERIFIED_CLAIM_OR_PRINTER_'+case+session)
            idx=raw.find(ERR_SENTINEL)
            check(idx>=0 and d['result_printer_hex']==raw[:idx].hex(' ').upper(),
                  'PRINTER_RESULT_'+case+session)
            match=re.match(rb'\s*([0-9]+)\s*,\s*([0-9]+)\s*[\r\n]+',
                           raw[idx+len(ERR_SENTINEL):])
            check(match is not None and
                  (int(match.group(1)),int(match.group(2)))==(d['err'],d['erl']),
                  'ERR_ERL_'+case+session)
            if expected_class!='OBSERVED':
                check(d['token_classification']=='TOKEN_UNVERIFIED','FALSE_TOKEN_CLAIM')
            pair.append(d)
        check(pair[0]['program_hex']==pair[1]['program_hex'] and
              (pair[0]['err'],pair[0]['erl'],pair[0]['result_printer_hex'])==
              (pair[1]['err'],pair[1]['erl'],pair[1]['result_printer_hex']),
              'INDEPENDENT_PAIR_'+case)
    print(PHASE,'VERIFIED',len(CASES)*2,
          'SESSIONS','EXTERNAL' if permanent else 'UNSEALED',flush=True)

def negatives(out,permanent=False):
    originals={str(p.relative_to(out)):sha(read(p)) for p in out.rglob('*') if p.is_file()}
    for kind in ('ram','list','run','printer','diagnostic','manifest','head','missing','pair','coordinated'):
        with tempfile.TemporaryDirectory(prefix='j120-falsification-') as tmp:
            clone=Path(tmp)/'clone'
            shutil.copytree(out,clone)
            work=clone/'original/A00'
            c=work/'capture.json'
            if kind in ('ram','coordinated'):
                p=work/'program.bin';v=bytearray(read(p));v[4]^=1;p.write_bytes(v)
                if kind=='coordinated':
                    d=json.loads(read(c));d['program_sha256']=sha(v);d['program_hex']=v.hex(' ').upper()
                    c.write_bytes(enc(d));m=json.loads(read(clone/'manifest.json'))
                    m['cases']['A00']['original']=sha(read(c))
                    (clone/'manifest.json').write_bytes(enc(m))
            elif kind in ('list','run'):
                p=work/kind/'screen.png';v=bytearray(read(p));v[-20]^=1;p.write_bytes(v)
            elif kind=='printer':
                p=work/'run/printer.dat';v=bytearray(read(p));v[0]^=1;p.write_bytes(v)
            elif kind=='diagnostic':
                d=json.loads(read(c));d['err']=999;c.write_bytes(enc(d))
            elif kind=='manifest':
                m=json.loads(read(clone/'manifest.json'));m['native_changes']=True
                (clone/'manifest.json').write_bytes(enc(m))
            elif kind=='head':
                m=json.loads(read(clone/'manifest.json'));m['acquisition_head']='0'*40
                (clone/'manifest.json').write_bytes(enc(m))
            elif kind=='missing':(work/'program.bin').unlink()
            elif kind=='pair':
                p=clone/'repeat/A00/program.bin';v=bytearray(read(p));v[4]^=1;p.write_bytes(v)
            try:verify(clone,permanent)
            except (Invalid,ValueError,KeyError,OSError,IndexError):
                print(PHASE,'FALSIFICATION_REJECTED',kind,flush=True)
            else:raise Invalid('FALSIFICATION_ACCEPTED_'+kind)
    for rel,digest in originals.items():
        check(sha(read(out/rel))==digest,'ARCHIVE_CHANGED_'+rel)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--check-sources',action='store_true')
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--permanent',action='store_true')
    p.add_argument('--expect-head')
    p.add_argument('--caprice',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--evidence',type=Path)
    a=p.parse_args()
    if a.expect_head:check_head(a.expect_head)
    if a.check_sources or a.self_test:
        for name in CASES:source(name)
        check(len(CASES)>=12 and len(SESSIONS)==2,'INSUFFICIENT_MATRIX')
        cpc.self_test()
        print(PHASE,'16_CASE_SOURCES_CHECKED',flush=True)
    if a.caprice:
        check(a.output is not None,'OUTPUT_REQUIRED')
        head=check_head(a.expect_head or subprocess.check_output(
            ['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip())
        acquire(a.caprice.resolve(),a.output.resolve(),head)
    if a.evidence:
        verify(a.evidence.resolve(),a.permanent)
        if a.self_test:negatives(a.evidence.resolve(),a.permanent)
    else:
        check(not a.permanent,'PERMANENT_REQUIRES_ARCHIVE')
    check(a.check_sources or a.self_test or a.caprice or a.evidence,'NO_ACTION')

if __name__=='__main__':
    try:main()
    except (Invalid,ValueError,OSError,subprocess.SubprocessError,KeyError,IndexError,UnicodeError) as exc:
        print(PHASE,'FAIL',str(exc),file=sys.stderr)
        sys.exit(1)
