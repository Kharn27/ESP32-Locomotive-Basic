/*
 * HW3 - independent native ESP-IDF LCD probe for classic ESP32 CYD.
 * No BASIC, Z80, ROM dumps, touch, SD, Wi-Fi or frame buffer.
 * SPDX-License-Identifier: MIT
 */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <inttypes.h>

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_err.h"
#include "esp_heap_caps.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_ili9341.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "cpc_font.h"

#define HW3_LCD_HOST SPI2_HOST
#define HW3_LCD_MOSI GPIO_NUM_13
#define HW3_LCD_SCLK GPIO_NUM_14
#define HW3_LCD_CS GPIO_NUM_15
#define HW3_LCD_DC GPIO_NUM_2
#define HW3_LCD_BL GPIO_NUM_21
#define HW3_LCD_CLOCK_HZ (20 * 1000 * 1000)
#define HW3_W 320
#define HW3_H 240
#define HW3_CPC_Y 20
#define HW3_CPC_H 200
#define HW3_COLS 40
#define HW3_ROWS 25
#define HW3_TILE 8
#define HW3_BAND_BYTES (HW3_W * HW3_TILE * 2)
#define HW3_CURSOR_ROW 11
#define HW3_CURSOR_COL 0
#define HW3_CURSOR_MS 500

/* CPC firmware defaults: INK 0=colour 1 (#000080), INK 1=colour 24 (#FFFF00).
 * Deterministic RGB565, sent high byte first to the ILI9341.
 */
#define HW3_BLUE_RGB565 0x0010U
#define HW3_YELLOW_RGB565 0xFFE0U

#ifndef HW3_LCD_BGR
#define HW3_LCD_BGR 0
#endif
#ifndef HW3_MIRROR_X
#define HW3_MIRROR_X 1
#endif
#ifndef HW3_MIRROR_Y
#define HW3_MIRROR_Y 0
#endif

static const char *TAG = "HW3";
static esp_lcd_panel_handle_t s_panel;
static uint8_t *s_dma_band;
static SemaphoreHandle_t s_transfer_done;
static uint8_t s_screen[HW3_ROWS][HW3_COLS];

static bool IRAM_ATTR on_color_done(esp_lcd_panel_io_handle_t io,
                                    esp_lcd_panel_io_event_data_t *event,
                                    void *ctx)
{
    (void)io;
    (void)event;
    BaseType_t task_woken = pdFALSE;
    xSemaphoreGiveFromISR((SemaphoreHandle_t)ctx, &task_woken);
    return task_woken == pdTRUE;
}

static void log_device_memory(const char *phase)
{
    /* Espressif's FreeRTOS high-water mark is in bytes (not vanilla words). */
    ESP_LOGI(TAG, "HW3 DEVICE_MEMORY phase=%s heap8_free=%u heap8_largest=%u heap8_min=%u stack_margin_bytes=%u dma_buffer_bytes=%u text_grid_bytes=%u",
             phase,
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_8BIT),
             (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
             (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT),
             (unsigned)uxTaskGetStackHighWaterMark(NULL),
             (unsigned)HW3_BAND_BYTES,
             (unsigned)sizeof(s_screen));
}

static void put_text(int row, int column, const char *text)
{
    if (row < 0 || row >= HW3_ROWS || column < 0 || column >= HW3_COLS) {
        return;
    }
    while (*text != 0 && column < HW3_COLS) {
        s_screen[row][column++] = (uint8_t)*text++;
    }
}

static void put_centered(int row, const char *text)
{
    size_t len = strlen(text);
    int column = (len < HW3_COLS) ? (HW3_COLS - (int)len) / 2 : 0;
    put_text(row, column, text);
}

static void build_boot_screen(void)
{
    memset(s_screen, ' ', sizeof(s_screen));
    /* Reference: CPC 6128 v3 boot and BASIC ROM 1.1 strings. The vertical
     * placement is a visual approximation pending a real CPC photo.
     */
    put_centered(4, "Amstrad 128K Microcomputer (v3)");
    put_centered(5, "\x7f""1985 Amstrad Consumer Electronics plc");
    put_centered(6, "and Locomotive Software Ltd.");
    put_text(8, 1, "BASIC 1.1");
    put_text(10, 0, "Ready");
}

static esp_err_t lcd_send(int x, int y, int width, int height)
{
    esp_err_t err = esp_lcd_panel_draw_bitmap(s_panel, x, y, x + width,
                                              y + height, s_dma_band);
    if (err != ESP_OK) {
        return err;
    }
    return xSemaphoreTake(s_transfer_done, pdMS_TO_TICKS(2000)) == pdTRUE
               ? ESP_OK : ESP_ERR_TIMEOUT;
}

/* One 320x8 band in 16-bit RGB565, in wire byte order (MSB first). */
static void draw_band(int top)
{
    for (int by = 0; by < HW3_TILE; ++by) {
        const int y = top + by;
        const bool inside = y >= HW3_CPC_Y && y < HW3_CPC_Y + HW3_CPC_H;
        const int logical_y = y - HW3_CPC_Y;
        const unsigned int glyph_row = inside ? (unsigned int)(logical_y % 8) : 0U;
        for (int x = 0; x < HW3_W; ++x) {
            uint16_t color = HW3_BLUE_RGB565;
            if (inside) {
                uint8_t ch = s_screen[logical_y / 8][x / 8];
                uint8_t pixels = hw3_glyph_row(ch, glyph_row);
                if ((pixels & (0x80U >> (x % 8))) != 0U) {
                    color = HW3_YELLOW_RGB565;
                }
            }
            const size_t offset = ((size_t)by * HW3_W + (size_t)x) * 2U;
            s_dma_band[offset] = (uint8_t)(color >> 8);
            s_dma_band[offset + 1] = (uint8_t)color;
        }
    }
}

static esp_err_t draw_boot_screen(void)
{
    build_boot_screen();
    for (int top = 0; top < HW3_H; top += HW3_TILE) {
        draw_band(top);
        esp_err_t err = lcd_send(0, top, HW3_W, HW3_TILE);
        if (err != ESP_OK) {
            return err;
        }
    }
    return ESP_OK;
}

/* Cursor cell only: never re-send the 320x200 screen to blink. */
static esp_err_t draw_cursor(bool visible)
{
    uint16_t color = visible ? HW3_YELLOW_RGB565 : HW3_BLUE_RGB565;
    for (int i = 0; i < HW3_TILE * HW3_TILE; ++i) {
        s_dma_band[2 * i] = (uint8_t)(color >> 8);
        s_dma_band[2 * i + 1] = (uint8_t)color;
    }
    const int x = HW3_CURSOR_COL * HW3_TILE;
    const int y = HW3_CPC_Y + HW3_CURSOR_ROW * HW3_TILE;
    return lcd_send(x, y, HW3_TILE, HW3_TILE);
}

static esp_err_t lcd_initialize(void)
{
    /* Backlight remains OFF until a complete frame is sent successfully. */
    gpio_config_t bl = {
        .pin_bit_mask = 1ULL << HW3_LCD_BL,
        .mode = GPIO_MODE_OUTPUT,
    };
    esp_err_t err = gpio_config(&bl);
    if (err != ESP_OK) return err;
    err = gpio_set_level(HW3_LCD_BL, 0);
    if (err != ESP_OK) return err;

    s_dma_band = heap_caps_malloc(HW3_BAND_BYTES,
                                  MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA);
    if (s_dma_band == NULL) return ESP_ERR_NO_MEM;
    s_transfer_done = xSemaphoreCreateBinary();
    if (s_transfer_done == NULL) return ESP_ERR_NO_MEM;

    spi_bus_config_t bus_cfg = {
        .sclk_io_num = HW3_LCD_SCLK,
        .mosi_io_num = HW3_LCD_MOSI,
        .miso_io_num = -1,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = HW3_BAND_BYTES + 16,
    };
    err = spi_bus_initialize(HW3_LCD_HOST, &bus_cfg, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) return err;

    esp_lcd_panel_io_spi_config_t io_cfg = {
        .cs_gpio_num = HW3_LCD_CS,
        .dc_gpio_num = HW3_LCD_DC,
        .spi_mode = 0,
        .pclk_hz = HW3_LCD_CLOCK_HZ,
        .trans_queue_depth = 2,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
    };
    esp_lcd_panel_io_handle_t panel_io = NULL;
    err = esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)HW3_LCD_HOST,
                                   &io_cfg, &panel_io);
    if (err != ESP_OK) return err;

    esp_lcd_panel_io_callbacks_t cb = {
        .on_color_trans_done = on_color_done,
    };
    err = esp_lcd_panel_io_register_event_callbacks(panel_io, &cb,
                                                      s_transfer_done);
    if (err != ESP_OK) return err;

    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = -1, /* LCD reset is wired to EN on common CYD. */
        .rgb_ele_order = HW3_LCD_BGR ? LCD_RGB_ELEMENT_ORDER_BGR
                                    : LCD_RGB_ELEMENT_ORDER_RGB,
        .data_endian = LCD_RGB_DATA_ENDIAN_BIG,
        .bits_per_pixel = 16,
    };
    err = esp_lcd_new_panel_ili9341(panel_io, &panel_cfg, &s_panel);
    if (err != ESP_OK) return err;
    err = esp_lcd_panel_reset(s_panel);
    if (err != ESP_OK) return err;
    err = esp_lcd_panel_init(s_panel);
    if (err != ESP_OK) return err;
    err = esp_lcd_panel_swap_xy(s_panel, true);
    if (err != ESP_OK) return err;
    err = esp_lcd_panel_mirror(s_panel, HW3_MIRROR_X, HW3_MIRROR_Y);
    if (err != ESP_OK) return err;
    return esp_lcd_panel_disp_on_off(s_panel, true);
}

void app_main(void)
{
    ESP_LOGI(TAG, "HW3 START");
    ESP_LOGI(TAG, "HW3 BUILD_IDENT project=loco_esp32_display_probe target=esp32 idf=%s rgb_order=%s mirror_x=%d mirror_y=%d",
             esp_get_idf_version(), HW3_LCD_BGR ? "BGR" : "RGB",
             HW3_MIRROR_X, HW3_MIRROR_Y);

    esp_err_t err = lcd_initialize();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HW3 LCD_INIT_FAIL err=%s", esp_err_to_name(err));
        log_device_memory("LCD_INIT_FAIL");
        return;
    }
    ESP_LOGI(TAG, "HW3 LCD_INIT_PASS");
    log_device_memory("LCD_INIT_PASS");

    err = draw_boot_screen();
    if (err == ESP_OK) {
        err = draw_cursor(true);
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HW3 LCD_DRAW_FAIL err=%s", esp_err_to_name(err));
        log_device_memory("LCD_DRAW_FAIL");
        return;
    }
    err = gpio_set_level(HW3_LCD_BL, 1);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HW3 LCD_BACKLIGHT_FAIL err=%s", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "HW3 BOOT_SCREEN_DRAWN");
    log_device_memory("BOOT_SCREEN_DRAWN");
    ESP_LOGI(TAG, "HW3 CURSOR_BLINK_ACTIVE");

    bool cursor_visible = true;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(HW3_CURSOR_MS));
        cursor_visible = !cursor_visible;
        err = draw_cursor(cursor_visible);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "HW3 CURSOR_DRAW_FAIL err=%s", esp_err_to_name(err));
            log_device_memory("CURSOR_DRAW_FAIL");
            return;
        }
    }
}
