#!/usr/bin/env python3
"""C8-A: read-only audit of pinned C6/B2-B and C6/D1 Xtensa ZIP evidence.

No compilation, link, ELF modification or simulated memory measurement.
"""
import argparse
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import re
import struct
from zipfile import ZipFile

ZIP_SEALS = {
    'b2b': ('29b8f28c7fcaadd808c3f0ce339ea2a3c18331154a1da08f9116c6ac2c067777',
            '0d5011d103cde1ea6429a4d4edbad8ba6a72aefab02cba1b71c6c242dd014c0b', 134),
    'd1': ('c12bf46013d91cb7ba0389388fa9523a460623944b44e2b8bb2c8c828f61fadc',
           'c70a6095a9b9622881a868ee40c80c8fd5653360e6083075940a365bcafe311a', 228),
}

def verify_archive(path, key):
    zip_sha, manifest_sha, count = ZIP_SEALS[key]
    assert sha256(path.read_bytes()).hexdigest() == zip_sha, 'ZIP SHA256 mismatch'
    z = ZipFile(path)
    manifest = z.read('SHA256SUMS.txt')
    assert sha256(manifest).hexdigest() == manifest_sha, 'manifest SHA256 mismatch'
    entries = manifest.decode('utf8').splitlines()
    assert len(entries) == count, 'manifest count drift'
    for entry in entries:
        m = re.fullmatch(r'([0-9a-f]{64})  \\./(.+)', entry)
        assert m and sha256(z.read(m[2])).hexdigest() == m[1], 'member hash drift: ' + entry
    print('C8_ARCHIVE_INTEGRITY=PASS label=%s verified=%d zip=%s' % (key, count, zip_sha))
    return z

def parse_map(z, label, variant):
    lines = z.read('%s/%s/firmware.map' % (label,variant)).decode('utf8').splitlines()
    begin = next(i for i, s in enumerate(lines) if s.startswith('.iram0.text '))
    end = next(i for i in range(begin+1, len(lines)) if lines[i].startswith('.dram0.data '))
    extent = int(lines[begin].split()[-1], 16)
    items = defaultdict(lambda: defaultdict(int))
    section = ''
    fill = 0
    for line in lines[begin+1:end]:
        m = re.match(r'^\\s*(\\.[\\w.$-]+)\\s*0x[0-9a-f]+\\s+0x([0-9a-f]+)\\s+(.+\\.a\\([^)]+\\))\\s*$', line)
        if m:
            section, size, obj = m.groups()
        else:
            m = re.match(r'^\\s*0x[0-9a-f]+\\s+0x([0-9a-f]+)\\s+(.+\\.a\\([^)]+\\))\\s*$', line)
            if m:
                size, obj = m.groups()
            else:
                header = re.match(r'^\\s*(\\.[\\w.$-]+)\\s*$', line)
                if header:
                    section = header[1]
                pad = re.match(r'^\\s*\\*fill\\*\\s+0x[0-9a-f]+\\s+0x([0-9a-f]+)', line)
                if pad:
                    fill += int(pad[1],16)
                continue
        items[obj]['literal' if 'literal' in section else 'code'] += int(size,16)
    assert sum(sum(t.values()) for t in items.values()) + fill == extent
    return extent, items, fill

def allocated_sections(data):
    assert data[:6] == b'\\x7fELF\\x01\\x01', 'not ELF32 little-endian'
    offset = struct.unpack_from('<I', data, 32)[0]
    size, count, index = struct.unpack_from('<HHH', data, 46)
    hdr = [struct.unpack_from('<10I', data, offset+i*size) for i in range(count)]
    shstr = hdr[index]
    strings = data[shstr[4]:shstr[4]+shstr[5]]
    result = {}
    for sh in hdr:
        at=sh[0]
        name=strings[at:strings.find(b'\\0', at)].decode('utf8')
        if sh[2] & 2:
            result[name] = (sh[5], b'' if sh[1]==8 else data[sh[4]:sh[4]+sh[5]])
    return result

def audit(b2b, d1):
    for variant in ('spi40','spi20'):
        base, bo, bf = parse_map(b2b, 'base', variant)
        head, ho, hf = parse_map(b2b, 'head', variant)
        assert (base, head, hf-bf) == (66303,66523,4), (base,head,hf-bf)
        changes=[]
        for obj in set(bo)|set(ho):
            code=ho[obj]['code']-bo[obj]['code']
            lit=ho[obj]['literal']-bo[obj]['literal']
            if code or lit:
                assert obj.startswith('esp-idf/'), 'application IRAM contribution changed: '+obj
                changes.append((obj,code,lit))
        assert len(changes) == 16 and sum(x[1] for x in changes) == 88
        assert sum(x[2] for x in changes) == 128
        print('C8_REAL_MAP=PASS freq=%s iram_text=%s_to_%s code=+88 literals=+128 fill=+4 iram_total=67331_to_67551 changed_idf_objects=16' % (variant,base,head))
    before={x[len('base/prelink/'):] for x in d1.namelist() if x.startswith('base/prelink/') and x.endswith('.obj')}
    assert len(before)==18
    different=[]
    for name in sorted(before):
        a=allocated_sections(d1.read('base/prelink/'+name))
        b=allocated_sections(d1.read('head/prelink/'+name))
        if a != b:
            different.append(name)
    assert different == ['loco_core/basic_executor.c.obj', 'loco_core/basic_session_runtime.c.obj'], different
    print('C8_REAL_PRELINK=PASS allocated_identical_idf_rtos_hal_log=16/16 modified_core_objects=2 root_cause=UNVERIFIED')
    print('C8_SAFE_PATCH_ATTRIBUTION=BLOCKED no directly changed application IRAM section')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--b2b',required=True,type=Path)
    p.add_argument('--d1',required=True,type=Path)
    a=p.parse_args()
    audit(verify_archive(a.b2b,'b2b'), verify_archive(a.d1,'d1'))

if __name__=='__main__':
    main()
