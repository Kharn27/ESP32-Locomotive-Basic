#!/usr/bin/env python3
"""C3: execute the real CMake selector; inspect unchanged DMA/fail-stop guards."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "firmware/esp32_display_probe"
SELECT = PROJECT / "spi_clock_select.cmake"

def cmake(profile, hz=None):
    cmd=["cmake", "-DLOCO_CYD_PROFILE="+profile]
    if hz is not None:
        cmd.append("-DCYD_LCD_SPI_HZ="+str(hz))
    cmd.extend(["-P",str(SELECT)])
    return subprocess.run(cmd,text=True,capture_output=True,check=False)

def test():
    positives=[
        ("CONSOLE",None,40000000),("CONSOLE",40000000,40000000),
        ("CONSOLE",20000000,20000000),("HW3",None,20000000),
        ("HW3",20000000,20000000),("BASIC_PROBE",None,20000000),
        ("BASIC_PROBE",20000000,20000000)
    ]
    negatives=[
        ("CONSOLE",0),("CONSOLE",-1),("CONSOLE",1),
        ("CONSOLE",10000000),("CONSOLE",30000000),
        ("CONSOLE",39999999),("CONSOLE",40000001),
        ("CONSOLE",55000000),("CONSOLE",80000000),
        ("CONSOLE","40MHz"),("CONSOLE","40000000U"),
        ("CONSOLE","020000000"),("CONSOLE","20000000;40000000"),
        ("HW3",40000000),("BASIC_PROBE",40000000)
    ]
    for profile,hz,expected in positives:
        r=cmake(profile,hz)
        assert r.returncode==0,(profile,hz,r.stderr)
        assert "REQUESTED_SPI_HZ="+str(expected) in r.stdout,r.stdout
        assert "ELECTRICAL_SPI_HZ=UNMEASURED" in r.stdout
    for profile,hz in negatives:
        r=cmake(profile,hz)
        assert r.returncode!=0,(profile,hz,r.stdout)
        assert "INVALID_SPI_HZ" in r.stderr or "CONSOLE_ONLY" in r.stderr,r.stderr
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
