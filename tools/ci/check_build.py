#!/usr/bin/env python3
"""J0.25: validate actual ESP-IDF sdkconfig and 4 MiB partition budget."""
import csv
import pathlib
import sys

if len(sys.argv) != 4:
    raise SystemExit("usage: check_build.py sdkconfig partitions.csv firmware.bin")
config_path, table_path, image_path = map(pathlib.Path, sys.argv[1:])
lines = set(config_path.read_text(encoding="utf-8").splitlines())
required = {
    'CONFIG_IDF_TARGET="esp32"',
    'CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y',
    'CONFIG_PARTITION_TABLE_CUSTOM=y',
}
missing = sorted(required - lines)
if missing:
    raise SystemExit("Bad sdkconfig: missing " + ", ".join(missing))
if any(line.startswith("CONFIG_SPIRAM") and line.endswith("=y")
       for line in lines):
    raise SystemExit("PSRAM/SPIRAM is incorrectly enabled")
if "CONFIG_BT_ENABLED=y" in lines:
    raise SystemExit("Bluetooth is incorrectly enabled")
if "CONFIG_ESP_WIFI_ENABLED=y" in lines:
    raise SystemExit("Wi-Fi is incorrectly enabled")
flash_capacity = 0x400000
regions = []
factory = None
with table_path.open(encoding="utf-8", newline="") as f:
    for row in csv.reader(l for l in f if l.strip() and not l.lstrip().startswith("#")):
        if len(row) < 5:
            raise SystemExit("Malformed partition row")
        name, kind, subtype, offset, length = (v.strip() for v in row[:5])
        lo, size = int(offset, 0), int(length, 0)
        hi = lo + size
        if size <= 0 or hi > flash_capacity:
            raise SystemExit("Partition exceeds 4 MiB: " + name)
        if any(lo < end and hi > begin for begin, end in regions):
            raise SystemExit("Overlapping partitions: " + name)
        regions.append((lo, hi))
        if kind == "app" and subtype == "factory":
            factory = (lo, size)
if factory is None:
    raise SystemExit("Factory app partition missing")
app_bytes = image_path.stat().st_size
if app_bytes > factory[1]:
    raise SystemExit(f"APP PARTITION OVERFLOW: {app_bytes} > {factory[1]}")
print("J0.25 VERIFIED: target=esp32 flash=4194304 no_psram=true")
print(f"APP_BIN_BYTES={app_bytes}")
print(f"APP_PARTITION_OFFSET={factory[0]}")
print(f"APP_PARTITION_BYTES={factory[1]}")
print(f"APP_PARTITION_FREE_BYTES={factory[1] - app_bytes}")
print("ON_DEVICE_UNVERIFIED")
