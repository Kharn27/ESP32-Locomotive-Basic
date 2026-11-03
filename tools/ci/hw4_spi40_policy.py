#!/usr/bin/env python3
"""HW4-SPI40: execute real CMake selection and guard the shared LCD transport.

Policy only; no synthetic test is an electrical SPI measurement or CYD proof.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROJECT = ROOT / "firmware/esp32_display_probe"
SELECT = PROJECT / "spi_clock_select.cmake"


def configure(profile, hz=None):
    cmd = ["cmake", "-DLOCO_CYD_PROFILE=" + profile]
    if hz is not None:
        cmd.append("-DCYD_LCD_SPI_HZ=" + str(hz))
    cmd += ["-P", str(SELECT)]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def positive(profile, hz, expected):
    result = configure(profile, hz)
    assert result.returncode == 0, (profile, hz, result.stderr)
    assert "REQUESTED_SPI_HZ=" + str(expected) in result.stdout, result.stdout
    assert "EFFECTIVE_SPI_HZ=UNMEASURED" in result.stdout
    return 1


def negative(profile, hz):
    result = configure(profile, hz)
    assert result.returncode != 0, (profile, hz, result.stdout)
    assert ("HW4-SPI40 INVALID_REQUEST" in result.stderr
            or "HW4-SPI40 CONSOLE_ONLY" in result.stderr), result.stderr
    return 1


def policy_source():
    lcd = (ROOT / "firmware/components/cyd_ili9341/cyd_ili9341.c").read_text()
    hdr = (ROOT / "firmware/components/cyd_ili9341/include/cyd_ili9341.h").read_text()
    cmake = (ROOT / "firmware/components/cyd_ili9341/CMakeLists.txt").read_text()
    console = (PROJECT / "main/hw4_c2_console.c").read_text()
    root = (PROJECT / "CMakeLists.txt").read_text()
    required = (
        '#define LCD_HOST SPI2_HOST', '#define LCD_MOSI GPIO_NUM_13',
        '#define LCD_SCLK GPIO_NUM_14', '#define LCD_CS GPIO_NUM_15',
        '#define LCD_DC GPIO_NUM_2', '#define LCD_BL GPIO_NUM_21',
        '#define LCD_TILE 8', 'CYD_LCD_DMA_BYTES + 16',
        'heap_caps_malloc(CYD_LCD_DMA_BYTES', 'MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA',
        'esp_lcd_panel_draw_bitmap(', 'xSemaphoreTake(s_done',
        's_fault = true;', '(void)gpio_set_level(LCD_BL,0);',
        '.pclk_hz = LCD_CLOCK_HZ', '.trans_queue_depth = 2',
        '.spi_mode = 0', 'cyd_lcd_requested_spi_hz(void)',
    )
    for item in required:
        assert item in lcd, "HAL transport invariant changed: " + item
    assert '#define CYD_LCD_DMA_BYTES 5120U' in hdr
    assert lcd.count("esp_lcd_panel_draw_bitmap(") == 1
    assert lcd.count("spi_bus_initialize(") == 1
    assert lcd.count("xSemaphoreTake(s_done") == 2
    assert not re.search(r'VSCR|55000000|80000000|spi_device_polling_transmit', lcd)
    assert "LCD_CLOCK_HZ != 20000000U && LCD_CLOCK_HZ != 40000000U" in lcd
    assert 'target_compile_definitions(${COMPONENT_LIB} PRIVATE LCD_CLOCK_HZ=${CYD_LCD_SPI_HZ}U)' in cmake
    assert 'include("${CMAKE_CURRENT_LIST_DIR}/spi_clock_select.cmake")' in root
    assert 'HW4-SPI40 BOOT requested_spi_hz=' in console
    assert 'effective_spi_hz=UNMEASURED' in console
    assert 'HW4-SPI40 RUN_DURATION' in console
    assert 'HW4-SPI40 FULL25_COUNT' in console
    assert 'cpc_video_flush_dirty(&s_video,send_dirty_band,&sent)' in console
    assert 'if(!ok)' in console and 'retry=0' in console
    assert 'RUN_QUANTUM = 8' in console
    return 1


def main():
    positives = sum([
        positive("CONSOLE", None, 20000000),
        positive("CONSOLE", 20000000, 20000000),
        positive("CONSOLE", 40000000, 40000000),
        positive("HW3", None, 20000000),
        positive("HW3", 20000000, 20000000),
        positive("BASIC_PROBE", None, 20000000),
        positive("BASIC_PROBE", 20000000, 20000000),
    ])
    negatives = sum(negative("CONSOLE", v) for v in (
        0, 1, 10000000, 19999999, 30000000, 40000001,
        55000000, 80000000, -1, "40000000U", "40MHz",
        "020000000", "20000000;40000000"
    ))
    negatives += negative("HW3", 40000000)
    negatives += negative("BASIC_PROBE", 40000000)
    guards = policy_source()
    print(f"HW4-SPI40 HOST_POLICY=PASS positives={positives} "
          f"negatives={negatives} transport_guards={guards} "
          "electrical=UNMEASURED")


if __name__ == "__main__":
    main()
