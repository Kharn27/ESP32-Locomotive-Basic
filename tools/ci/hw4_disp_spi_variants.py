#!/usr/bin/env python3
"""C3: compare the two real Xtensa image section tables and build identities."""
import argparse
import json
import hashlib
from pathlib import Path
import re

def sizes(path):
    found={}
    for line in path.read_text().splitlines():
        m=re.match(r"\s*(\.[A-Za-z0-9_.$-]+)\s+(\d+)\s+",line)
        if m: found[m.group(1)]=int(m.group(2))
    for name in (".dram0.data",".dram0.bss",".flash.text",".flash.rodata"):
        assert name in found,(path,name)
    assert any(x.startswith(".iram0.") for x in found),path
    def total(prefix):
        return sum(v for k,v in found.items() if k.startswith(prefix))
    return dict(dram=total(".dram0."),bss=found[".dram0.bss"],
                iram=total(".iram0."),
                text=total(".flash.text"),rodata=total(".flash.rodata"))

def main():
    ap=argparse.ArgumentParser()
    for variant in ("spi40","spi20"):
        for item in ("sections","cache","bin","commands"):
            ap.add_argument(f"--{variant}-{item}",type=Path,required=True)
    args=ap.parse_args()
    m={}; digest={}
    for variant,hz in (("spi40",40000000),("spi20",20000000)):
        section=getattr(args,variant+"_sections")
        cache=getattr(args,variant+"_cache").read_text()
        binary=getattr(args,variant+"_bin").read_bytes()
        commands=json.loads(getattr(args,variant+"_commands").read_text())
        lcd=[item for item in commands if
             item.get("file","").endswith("/cyd_ili9341.c")]
        assert len(lcd)==1,(variant,"LCD compile command missing or ambiguous")
        command=lcd[0].get("command","")
        if not command:
            command=" ".join(lcd[0].get("arguments",[]))
        assert "-DLCD_CLOCK_HZ="+str(hz)+"U" in command,(
            variant,"HAL compiler did not receive requested clock")
        assert "CYD_LCD_SPI_HZ:STRING="+str(hz) in cache,(variant,"SPI cache")
        assert "LOCO_CYD_PROFILE:STRING=CONSOLE" in cache,variant
        assert binary,(variant,"missing image")
        m[variant]=sizes(section)
        digest[variant]=hashlib.sha256(binary).hexdigest()
        assert m[variant]["dram"]<=54664,(variant,"DRAM limit",m[variant])
        assert m[variant]["iram"]==67331,(variant,"IRAM changed",m[variant])
    assert m["spi40"]["dram"]==m["spi20"]["dram"],("DRAM mismatch",m)
    assert m["spi40"]["iram"]==m["spi20"]["iram"],("IRAM mismatch",m)
    assert digest["spi40"]!=digest["spi20"],"SPI40 and SPI20 images unexpectedly identical"
    print("HW4-DISP-C3 TARGET_BUILD_VERIFIED=SPI40_AND_SPI20 "
          "HAL_COMPILE_CLOCKS_VERIFIED=40000000_AND_20000000 "
          "clock_scope=requested_not_measured")
    print("| Metric | CONSOLE SPI40 | CONSOLE SPI20 fallback |")
    print("|---|---:|---:|")
    for key in ("dram","bss","iram","text","rodata"):
        print(f"| {key} (bytes) | {m['spi40'][key]} | {m['spi20'][key]} |")
    print(f"| firmware SHA256 | \`{digest['spi40']}\` | \`{digest['spi20']}\` |")
    print("C3_EXCEPTION_MEMORY=WITHIN_54664 IRAM=67331 HISTORIC_A0_UNCHANGED")

if __name__=="__main__":
    main()
