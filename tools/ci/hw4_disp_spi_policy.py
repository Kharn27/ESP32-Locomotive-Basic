#!/usr/bin/env python3
"""C3/B1-C2: execute real selector, preserved-cache rebuild and DMA guards."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "firmware/esp32_display_probe"
SELECT = PROJECT / "spi_clock_select.cmake"

def cmake(profile, hz=None, opt_in=None):
    cmd=["cmake", "-DLOCO_CYD_PROFILE="+profile]
    if hz is not None:
        cmd.append("-DCYD_LCD_SPI_HZ="+str(hz))
    if opt_in is not None:
        cmd.append("-DCYD_LCD_SPI20_OPT_IN="+str(opt_in))
    cmd.extend(["-P",str(SELECT)])
    return subprocess.run(cmd,text=True,capture_output=True,check=False)


def test_preserved_cache_build():
    """Legacy SPI20 cache -> SPI40 after a plain Build in the SAME directory.

    The legacy stub contains the historic if(NOT DEFINED) cache logic. The
    next Build loads the actual production selector without flags/fullclean.
    This is a compiled host-only clock-request probe, not ESP32 firmware.
    """
    legacy = """if(NOT DEFINED CYD_LCD_SPI_HZ)
  if(LOCO_CYD_PROFILE STREQUAL "CONSOLE")
    set(CYD_LCD_SPI_HZ 40000000)
  else()
    set(CYD_LCD_SPI_HZ 20000000)
  endif()
endif()
set(CYD_LCD_SPI_HZ "${CYD_LCD_SPI_HZ}" CACHE STRING "legacy")
"""
    def checked(*cmd):
        r=subprocess.run(cmd,text=True,capture_output=True,check=False)
        assert r.returncode==0,(cmd,r.stdout,r.stderr)
        return r.stdout
    def boot(build_dir,hz):
        output=checked(str(build_dir/"clock_request_probe"))
        assert f"spi_request_hz={hz} variant=SPI{hz//1000000}" in output,output
    with tempfile.TemporaryDirectory(prefix="loco-spi-cache-") as tmp:
        src=Path(tmp)
        build=src/"build"
        selector=src/"selector.cmake"
        selector.write_text(legacy)
        (src/"CMakeLists.txt").write_text("""cmake_minimum_required(VERSION 3.16)
set(LOCO_CYD_PROFILE CONSOLE CACHE STRING "profile")
include("${CMAKE_CURRENT_LIST_DIR}/selector.cmake")
project(spi_cache_probe C)
add_executable(clock_request_probe boot.c)
target_compile_definitions(clock_request_probe PRIVATE LCD_CLOCK_HZ=${CYD_LCD_SPI_HZ}U)
""")
        (src/"boot.c").write_text("""#include <stdio.h>
int main(void) {
  printf("spi_request_hz=%u variant=SPI%u\\n",
         LCD_CLOCK_HZ, LCD_CLOCK_HZ/1000000U);
  return 0;
}
""")
        checked("cmake","-S",str(src),"-B",str(build),
                "-DCYD_LCD_SPI_HZ=20000000")
        checked("cmake","--build",str(build))
        boot(build,20000000)  # RED: inherited SPI20 build
        cache=build/"CMakeCache.txt"
        assert "CYD_LCD_SPI_HZ:STRING=20000000" in cache.read_text()
        selector.write_text(SELECT.read_text())  # branch switch
        checked("cmake","--build",str(build))     # no -D, no cache deletion
        boot(build,40000000)  # GREEN: standard CONSOLE SPI40
        assert "CYD_LCD_SPI_HZ:STRING=40000000" in cache.read_text()
        assert "CYD_LCD_SPI20_OPT_IN:BOOL=OFF" in cache.read_text()
        checked("cmake","-S",str(src),"-B",str(build),
                "-DCYD_LCD_SPI20_OPT_IN=ON")
        checked("cmake","--build",str(build))
        boot(build,20000000)  # explicitly requested fallback
        checked("cmake","--build",str(build))
        boot(build,20000000)  # persisted opt-in
        checked("cmake","-S",str(src),"-B",str(build),
                "-DCYD_LCD_SPI20_OPT_IN=OFF")
        checked("cmake","--build",str(build))
        boot(build,40000000)  # default restored
    print("HW4-DISP-C3 HOST_PRESERVED_CACHE=RED_SPI20_GREEN_SPI40 "
          "SAME_BUILD=PASS EXPLICIT_SPI20_OPT_IN=PASS")

def test():
    positives=[
        ("CONSOLE",None,None,40000000),
        ("CONSOLE",40000000,None,40000000),
        ("CONSOLE",20000000,None,40000000), # stale old cache != opt-in
        ("CONSOLE",20000000,"ON",20000000),
        ("CONSOLE",None,"ON",20000000),
        ("HW3",None,None,20000000),
        ("HW3",20000000,None,20000000),
        ("BASIC_PROBE",None,None,20000000),
        ("BASIC_PROBE",20000000,None,20000000)
    ]
    negatives=[
        ("CONSOLE",0,None),("CONSOLE",-1,None),("CONSOLE",1,None),
        ("CONSOLE",10000000,None),("CONSOLE",30000000,None),
        ("CONSOLE",39999999,None),("CONSOLE",40000001,None),
        ("CONSOLE",55000000,None),("CONSOLE",80000000,None),
        ("CONSOLE","40MHz",None),("CONSOLE","40000000U",None),
        ("CONSOLE","020000000",None),("CONSOLE","20000000;40000000",None),
        ("CONSOLE",55000000,"ON"),
        ("HW3",40000000,None),("BASIC_PROBE",40000000,None),
        ("HW3",None,"ON"),("BASIC_PROBE",None,"ON"),
        ("CONSOLE",None,"YES"),("CONSOLE",None,"INVALID")
    ]
    for profile,hz,opt,expected in positives:
        r=cmake(profile,hz,opt)
        assert r.returncode==0,(profile,hz,opt,r.stderr)
        assert "REQUESTED_SPI_HZ="+str(expected) in r.stdout,r.stdout
        assert "ELECTRICAL_SPI_HZ=UNMEASURED" in r.stdout
    for profile,hz,opt in negatives:
        r=cmake(profile,hz,opt)
        assert r.returncode!=0,(profile,hz,opt,r.stdout)
        assert ("INVALID_SPI_HZ" in r.stderr or
                "CONSOLE_ONLY" in r.stderr or
                "INVALID_SPI20_OPT_IN" in r.stderr),r.stderr
    test_preserved_cache_build()
    lcd=(ROOT/"firmware/components/cyd_ili9341/cyd_ili9341.c").read_text()
    hdr=(ROOT/"firmware/components/cyd_ili9341/include/cyd_ili9341.h").read_text()
    component=(ROOT/"firmware/components/cyd_ili9341/CMakeLists.txt").read_text()
    root=(PROJECT/"CMakeLists.txt").read_text()
    console=(PROJECT/"main/hw4_c2_console.c").read_text()
    guards=(
        "#define LCD_HOST SPI2_HOST","#define LCD_MOSI GPIO_NUM_13",
        "#define LCD_SCLK GPIO_NUM_14","#define LCD_CS GPIO_NUM_15",
        "#define LCD_DC GPIO_NUM_2","#define LCD_BL GPIO_NUM_21",
        "#define LCD_TILE 8","CYD_LCD_DMA_BYTES + 16",
        "heap_caps_malloc(CYD_LCD_DMA_BYTES","MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA",
        ".pclk_hz = LCD_CLOCK_HZ",".trans_queue_depth = 2",".spi_mode = 0",
        "s_fault = true;","(void)gpio_set_level(LCD_BL,0);",
        "cyd_lcd_requested_spi_hz(void)",
        "LCD_CLOCK_HZ != 20000000U && LCD_CLOCK_HZ != 40000000U",
    )
    for invariant in guards:
        assert invariant in lcd,"HAL guard lost: "+invariant
    assert lcd.count("esp_lcd_panel_draw_bitmap(")==1
    assert lcd.count("spi_bus_initialize(")==1
    assert lcd.count("xSemaphoreTake(s_done")==2
    assert "#define CYD_LCD_DMA_BYTES 5120U" in hdr
    assert "unsigned cyd_lcd_requested_spi_hz(void);" in hdr
    assert "LCD_CLOCK_HZ=\${CYD_LCD_SPI_HZ}U".replace("\\$","$") in component
    assert 'include("\${CMAKE_CURRENT_LIST_DIR}/spi_clock_select.cmake")'.replace("\\$","$") in root
    assert 'HW4-DISP-PROFILE BOOT spi_request_hz=%u ' in console
    assert 'electrical_spi_hz=UNMEASURED' in console
    assert 'cpc_video_flush_dirty(&s_video,send_dirty_band,&sent)' in console
    assert 'RUN_QUANTUM = 8' in console
    assert 'retry=0' in console
    assert "VSCR" not in lcd and "55000000" not in lcd
    print(f"HW4-DISP-C3 HOST_POLICY=PASS positive={len(positives)} "
          f"negative={len(negatives)} transport_guards=PASS "
          "electrical_spi_hz=UNMEASURED")

if __name__=="__main__":
    test()
