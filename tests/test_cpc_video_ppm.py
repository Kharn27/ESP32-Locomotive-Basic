#!/usr/bin/env python3
"""Reproduce three 320x240 CPC PPMs twice and require pinned byte hashes."""
import hashlib
from pathlib import Path
import subprocess
import sys

EXPECTED = (
    '9df98bd1b71c1040d1859023deb14760d30b2c5bacdf7aa43de993c881596da5',
    '64e512a59a6f33e15c1cbeb6f0062dae958f33d08ec6040e31d27908d66f1641',
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
