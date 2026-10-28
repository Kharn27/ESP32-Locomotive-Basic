#!/usr/bin/env python3
"""ARCH-HW4-U1-B: positive and negative regression checks of relocated tool.

The original partition checker remains byte-for-byte unchanged.
"""
import pathlib
import subprocess
import sys
import tempfile

CHECK = pathlib.Path(__file__).with_name("check_build.py")
BASE_CONFIG = ('CONFIG_IDF_TARGET="esp32"\n'
               'CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y\n'
               'CONFIG_PARTITION_TABLE_CUSTOM=y\n')
BASE_TABLE = ("nvs,data,nvs,0x9000,0x6000,\n"
              "phy_init,data,phy,0xf000,0x1000,\n"
              "factory,app,factory,0x10000,0x300000,\n")


def verify(label, config, table, size, success):
    with tempfile.TemporaryDirectory(prefix="u1b-partitions-") as d:
        root = pathlib.Path(d)
        (root / "sdkconfig").write_text(config, encoding="utf-8")
        (root / "partitions.csv").write_text(table, encoding="utf-8")
        (root / "firmware.bin").write_bytes(b"X" * size)
        run = subprocess.run(
            [sys.executable, str(CHECK), str(root / "sdkconfig"),
             str(root / "partitions.csv"), str(root / "firmware.bin")],
            capture_output=True, text=True, check=False)
        if (run.returncode == 0) != success:
            raise AssertionError(label + " unexpected result: " + run.stdout + run.stderr)
        print("U1-B PARTITIONS_" + label + "=PASS")


verify("VALID", BASE_CONFIG, BASE_TABLE, 1024, True)
verify("INVALID_TARGET", BASE_CONFIG.replace('"esp32"', '"esp32s3"'), BASE_TABLE, 1024, False)
verify("PSRAM", BASE_CONFIG + "CONFIG_SPIRAM=y\n", BASE_TABLE, 1024, False)
verify("WIFI", BASE_CONFIG + "CONFIG_ESP_WIFI_ENABLED=y\n", BASE_TABLE, 1024, False)
verify("OVERLAP", BASE_CONFIG, BASE_TABLE.replace("0xf000", "0x9000"), 1024, False)
verify("NO_FACTORY", BASE_CONFIG, BASE_TABLE.replace("app,factory", "data,foo"), 1024, False)
verify("APP_OVERFLOW", BASE_CONFIG, BASE_TABLE.replace("0x300000", "0x1000"), 0x1001, False)
