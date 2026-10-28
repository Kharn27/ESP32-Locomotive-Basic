#!/usr/bin/env python3
"""Reproduce three 320x240 CPC PPMs twice and require pinned byte hashes."""
import hashlib
from pathlib import Path
import subprocess
import sys

# HW4-EDIT-A-C1: updated only MODE0/MODE1 image digests after the deliberate
# reverse-video cursor change, acquired from exact SHA 4b4fc92896aa3c8e
# in CI-C99 40721623224. MODE2 OR_PAIR PPM digest is unchanged.
# All three 320x240 PPMs remain pinned and reproduced twice.
EXPECTED = (
    '55e44da158c152d5d835332e4710352778c910355712f96564e69b6bb0b31940',
    '17b8918a5289c2c98c47ab6f4fc7700d69df3f56953521468bbe481ee6b196e9',
    'e3befe375e2454a7aaa6dac1d2b01ffb719f078bab1e70da7b9e055e70d7a439',
)

def main():
    exe, prefix = sys.argv[1:]
    for repeat in range(2):
        subprocess.run([exe, prefix], check=True)
        observed = []
        for mode, target in enumerate(EXPECTED):
            image = Path(f'{prefix}-mode{mode}.ppm').read_bytes()
            assert image.startswith(b'P6\n320 240\n255\n')
            assert len(image) == len(b'P6\n320 240\n255\n') + 320*240*3
            result = hashlib.sha256(image).hexdigest()
            observed.append(result)
        # Fail closed, but report all three real image hashes for deliberate
        # re-sealing after C1's intended visual cursor inversion.
        assert tuple(observed) == EXPECTED, (repeat, tuple(observed), EXPECTED)
    print('HW4-A three-mode PPM deterministic sha256 PASS')

if __name__ == '__main__':
    main()
