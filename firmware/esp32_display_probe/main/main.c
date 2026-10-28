/*
 * HW3 - independent native ESP-IDF LCD probe for classic ESP32 CYD.
 * No BASIC, Z80, ROM dumps, touch, SD, Wi-Fi or frame buffer.
 * SPDX-License-Identifier: MIT
 */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <inttypes.h>
#include <limits.h>

#include "driver/uart.h"
#include "esp_err.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "cpc_font.h"
#include "cpc_boot.h"
#include "cpc_video.h"
#include "cyd_ili9341.h"

#define HW3_W 320
#define HW3_NATIVE_W 240
#define HW3_NATIVE_H 320
#define HW3_H 240
#define HW3_CPC_Y 20
#define HW3_CPC_H 200
#define HW3_COLS 40
#define HW3_ROWS 25
#define HW3_TILE 8
#define HW3_BAND_BYTES CYD_LCD_DMA_BYTES
#define HW3_CURSOR_ROW 13
#define HW3_CURSOR_COL 0
#define HW3_CURSOR_MS 500 /* diagnostic only; disabled at boot */
#define HW3_MATRIX_HOLD_MS 2500
#define HW3_SOFTWARE_ROTATE_CW 12U
#define HW3_SOFTWARE_ROTATE_CCW 13U

/* CPC firmware defaults: INK 0=colour 1 (#000080), INK 1=colour 24 (#FFFF00).
 * Deterministic RGB565, sent high byte first to the ILI9341.
 */
#define HW3_BLUE_RGB565 0x0010U
#define HW3_YELLOW_RGB565 0xFFE0U

#ifndef HW3_SWAP_XY
#define HW3_SWAP_XY 1
#endif
#ifndef HW3_LCD_BGR
#define HW3_LCD_BGR 0
#endif
#ifndef HW3_MIRROR_X
#define HW3_MIRROR_X 0
#endif
#ifndef HW3_MIRROR_Y
#define HW3_MIRROR_Y 1
#endif

static const char *TAG = "HW3";
static uint8_t *s_dma_band; /* borrowed, never freed by the probe */
static uint8_t s_screen[HW3_ROWS][HW3_COLS];
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

static void build_boot_screen(void)
{
    memset(s_screen, ' ', sizeof(s_screen));
    /* Shared HW3 layout, unchanged original title in OFF probe variant. */
    for (unsigned i=0U;i<CPC_BOOT_LINES;++i) {
        CpcBootLine line;
        if (cpc_boot_line(i,false,&line))
            put_text((int)line.row,(int)line.column,line.text);
    }
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
        esp_err_t err = cyd_lcd_send(0, top, HW3_W, HW3_TILE);
        if (err != ESP_OK) {
            return err;
        }
    }
    return ESP_OK;
}

/* Cursor cell only: no full-screen refresh for a visibility change. */
static esp_err_t draw_cursor(bool visible)
{
    uint16_t color = visible ? HW3_YELLOW_RGB565 : HW3_BLUE_RGB565;
    for (int i = 0; i < HW3_TILE * HW3_TILE; ++i) {
        s_dma_band[2 * i] = (uint8_t)(color >> 8);
        s_dma_band[2 * i + 1] = (uint8_t)color;
    }
    int x = HW3_CURSOR_COL * HW3_TILE;
    int y = HW3_CPC_Y + HW3_CURSOR_ROW * HW3_TILE;
    if (cyd_lcd_current_orientation() == HW3_SOFTWARE_ROTATE_CW) {
        /* Portrait GRAM u=239-logical_y, v=logical_x. */
        int u = HW3_H - (y + HW3_TILE);
        int v = x;
        x = u; y = v;
    } else if (cyd_lcd_current_orientation() == HW3_SOFTWARE_ROTATE_CCW) {
        /* Portrait GRAM u=logical_y, v=319-logical_x. */
        int u = y;
        int v = HW3_W - (x + HW3_TILE);
        x = u; y = v;
    }
    return cyd_lcd_send(x, y, HW3_TILE, HW3_TILE);
}


/* Transport and orientation are now owned by the shared HW4-B component. */
static esp_err_t set_orientation_probe(unsigned index)
{
    return cyd_lcd_orientation(index, HW3_BLUE_RGB565);
}
static uint8_t s_hw4_pixels[CPC_VIDEO_BYTES];
static CpcVideo s_hw4_video;
static bool s_hw4_active;
/* The HW3 boot screen has its own cursor, distinct from the HW4 VRAM cursor.
 * PO reports the real CPC 6128 startup cursor as steady; default is fixed.
 * Optional UART 't' retains the prior 500 ms HW3 diagnostic experiment.
 */
static bool s_boot_cursor_enabled = true;
static bool s_boot_cursor_blink = false;
static unsigned s_hw4_mode = 2U;
static unsigned s_hw4_palette = 24U;
static bool s_hw4_cursor_visible = true;

static uint8_t hw4_glyph(void *ignored, uint8_t ch, unsigned y)
{
    (void)ignored;
    return hw3_glyph_row(ch, y);
}

static esp_err_t hw4_repaint(void)
{
    uint16_t row[HW3_W];
    for (unsigned top = 0; top < HW3_H; top += HW3_TILE) {
        for (unsigned dy = 0; dy < HW3_TILE; ++dy) {
            if (!cpc_video_render_row(&s_hw4_video, top + dy, row, HW3_W))
                return ESP_ERR_INVALID_STATE;
            for (unsigned x = 0; x < HW3_W; ++x) {
                size_t p = ((size_t)dy * HW3_W + x) * 2U;
                s_dma_band[p] = (uint8_t)(row[x] >> 8U);
                s_dma_band[p + 1U] = (uint8_t)row[x];
            }
        }
        esp_err_t err = cyd_lcd_send(0, (int)top, HW3_W, HW3_TILE);
        if (err != ESP_OK) return err;
    }
    (void)cpc_video_take_dirty(&s_hw4_video);
    return ESP_OK;
}

static esp_err_t hw4_scene(unsigned mode)
{
    esp_err_t err = set_orientation_probe(9U);
    if (err != ESP_OK) return err;
    if (!cpc_video_init(&s_hw4_video, s_hw4_pixels, sizeof(s_hw4_pixels),
                        (CpcMode)mode)) return ESP_ERR_INVALID_ARG;
    unsigned width = cpc_video_width(&s_hw4_video);
    unsigned colors = cpc_video_colors(&s_hw4_video);
    for (unsigned y = 0; y < 200U; ++y) {
        for (unsigned x = 0; x < width; ++x) {
            /* Palette swatch plus checker bars, exercising every logical pen. */
            unsigned pen = (y >= 80U && y < 144U) ? 1U :
                           (x / (width / colors) + y / 40U) % colors;
            if (!cpc_video_put(&s_hw4_video, x, y, pen)) return ESP_ERR_INVALID_ARG;
        }
    }
    (void)cpc_video_set_ink(&s_hw4_video, 1U, s_hw4_palette);
    const char *label = mode == 0U ? "MODE 0" : mode == 1U ? "MODE 1" : "MODE 2";
    (void)cpc_video_set_text_colors(&s_hw4_video, 1U, 0U);
    for (unsigned i = 0U; label[i] != 0; ++i)
        (void)cpc_video_put_cell(&s_hw4_video, i + 1U, 2U,
                                 (uint8_t)label[i], hw4_glyph, NULL);
    (void)cpc_video_cursor(&s_hw4_video, 1U, 5U, s_hw4_cursor_visible);
    s_hw4_active = true;
    ESP_LOGI(TAG, "HW4 MODE_READY mode=%u logical_width=%u colours=%u vram_bytes=%u case=9",
             mode, width, colors, (unsigned)sizeof(s_hw4_pixels));
    err = hw4_repaint();
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "HW4 MODE_DRAWN mode=%u TFT=320x240 viewport=0,20,320,200 border=20px cursor=%u",
                 mode, (unsigned)s_hw4_cursor_visible);
        log_device_memory("HW4_MODE_DRAWN");
    }
    return err;
}

/* A geometric test independent of BASIC, CPC characters or font layout.
 * It has full-panel perimeter and four DISTINCT corner colors. It can be
 * drawn within either legal address space without out-of-range rectangles.
 */
static void diagnostic_band(int top, int width, int height, unsigned int idx)
{
    /* Label is always two decimal digits: 08, 09, 10, 11, etc. */
    const char label[8] = {'C', 'A', 'S', 'E', ' ',
                           (char)('0' + idx / 10U),
                           (char)('0' + idx % 10U), '\0'};
    const int label_x = (width - 7 * 8) / 2;
    const int label_y = 36;
    for (int by = 0; by < HW3_TILE; ++by) {
        const int y = top + by;
        for (int x = 0; x < width; ++x) {
            uint16_t rgb = HW3_BLUE_RGB565;
            if (x < 2 || x >= width - 2 || y < 2 || y >= height - 2) {
                rgb = HW3_YELLOW_RGB565;
            }
            if (x < 18 && y < 18) rgb = 0xF800U;               /* top-left red */
            if (x >= width - 18 && y < 18) rgb = 0x07E0U;      /* top-right green */
            if (x < 18 && y >= height - 18) rgb = 0xFFE0U;     /* bottom-left yellow */
            if (x >= width - 18 && y >= height - 18) rgb = 0xFFFFU; /* bottom-right white */
            if (y >= label_y && y < label_y + 8 &&
                x >= label_x && x < label_x + 7 * 8) {
                int col = (x - label_x) / 8;
                char ch = label[col];
                uint8_t pixels = hw3_glyph_row((uint8_t)ch, (unsigned)(y - label_y));
                if ((pixels & (0x80U >> ((x - label_x) % 8))) != 0) {
                    rgb = HW3_YELLOW_RGB565;
                }
            }
            const size_t at = ((size_t)by * (size_t)width + (size_t)x) * 2U;
            s_dma_band[at] = (uint8_t)(rgb >> 8);
            s_dma_band[at + 1] = (uint8_t)rgb;
        }
    }
}

static esp_err_t draw_diagnostic(unsigned int idx)
{
    /* HW3-C3: width must agree with set_orientation_probe() for EVERY case.
     * Before this fix idx=8 used 240x320 while MADCTL stayed in MV=0
     * with a 320x240 address window. That wrapped stale/corrupt pixels.
     */
    const bool native_wide = idx >= 8U && idx <= 11U;
    const bool landscape = native_wide || ((idx & 1U) != 0);
    const int width = landscape ? HW3_W : HW3_NATIVE_W;
    const int height = landscape ? HW3_H : HW3_NATIVE_H;
    ESP_LOGI(TAG, "HW3 DIAGNOSTIC_GEOMETRY case=%u width=%d height=%d", idx, width, height);
    for (int top = 0; top < height; top += HW3_TILE) {
        diagnostic_band(top, width, height, idx);
        esp_err_t err = cyd_lcd_send(0, top, width, HW3_TILE);
        if (err != ESP_OK) return err;
    }
    ESP_LOGI(TAG, "HW3 CALIBRATION_DRAWN case=%u corners=TL_RED,TR_GREEN,BL_YELLOW,BR_WHITE",
             idx);
    return ESP_OK;
}

/* The fallback never sets MV. A 240x8 DMA strip is written in native
 * portrait GRAM coordinates and filled by inverse-mapping to a logical
 * 320x240 landscape pixel. No 153600-byte framebuffer or malloc needed.
 *
 * Case 12: physical (u,v) -> logical (x=v,y=239-u).
 * Case 13: physical (u,v) -> logical (x=319-v,y=u).
 */
static uint16_t logical_boot_pixel(int x, int y)
{
    if (y < HW3_CPC_Y || y >= HW3_CPC_Y + HW3_CPC_H) {
        return HW3_BLUE_RGB565;
    }
    const int ly = y - HW3_CPC_Y;
    uint8_t ch = s_screen[ly / 8][x / 8];
    uint8_t row = hw3_glyph_row(ch, (unsigned)ly % 8U);
    return ((row & (0x80U >> (x % 8))) != 0) ?
           HW3_YELLOW_RGB565 : HW3_BLUE_RGB565;
}

static uint16_t logical_diag_pixel(int x, int y)
{
    if (x < 2 || x >= HW3_W - 2 || y < 2 || y >= HW3_H - 2) {
        return HW3_YELLOW_RGB565;
    }
    if (x < 18 && y < 18) return 0xF800U;
    if (x >= HW3_W - 18 && y < 18) return 0x07E0U;
    if (x < 18 && y >= HW3_H - 18) return HW3_YELLOW_RGB565;
    if (x >= HW3_W - 18 && y >= HW3_H - 18) return 0xFFFFU;
    if (y >= 38 && y < 46) {
        const char *label = cyd_lcd_current_orientation() == HW3_SOFTWARE_ROTATE_CW ? "ROT 12" : "ROT 13";
        const int start = (HW3_W - (int)strlen(label) * 8) / 2;
        if (x >= start && x < start + (int)strlen(label) * 8) {
            uint8_t bits = hw3_glyph_row((uint8_t)label[(x - start) / 8],
                                          (unsigned)(y - 38));
            if (bits & (0x80U >> ((x - start) % 8))) return HW3_YELLOW_RGB565;
        }
    }
    return HW3_BLUE_RGB565;
}

static esp_err_t draw_software_rotated(bool boot, unsigned int idx)
{
    if (boot) build_boot_screen();
    for (int top = 0; top < HW3_NATIVE_H; top += HW3_TILE) {
        for (int by = 0; by < HW3_TILE; ++by) {
            const int v = top + by;
            for (int u = 0; u < HW3_NATIVE_W; ++u) {
                const int x = idx == HW3_SOFTWARE_ROTATE_CW ? v : HW3_W - 1 - v;
                const int y = idx == HW3_SOFTWARE_ROTATE_CW ? HW3_H - 1 - u : u;
                const uint16_t rgb = boot ? logical_boot_pixel(x,y)
                                          : logical_diag_pixel(x,y);
                const size_t at = ((size_t)by * HW3_NATIVE_W + (size_t)u) * 2U;
                s_dma_band[at] = (uint8_t)(rgb >> 8);
                s_dma_band[at + 1] = (uint8_t)rgb;
            }
        }
        esp_err_t err = cyd_lcd_send(0, top, HW3_NATIVE_W, HW3_TILE);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}

static esp_err_t show_case(unsigned int idx, bool boot, bool *is_boot)
{
    esp_err_t err = set_orientation_probe(idx);
    if (err != ESP_OK) return err;
    const bool native_wide = idx >= 8U && idx <= 11U;
    const bool software = idx == HW3_SOFTWARE_ROTATE_CW || idx == HW3_SOFTWARE_ROTATE_CCW;
    *is_boot = boot && (native_wide || software || ((idx & 1U) != 0));
    if (software) {
        err = draw_software_rotated(*is_boot, idx);
        if (err == ESP_OK) ESP_LOGI(TAG, "HW3 SOFTWARE_ROTATION_DRAWN case=%u boot=%u", idx,
                                    (unsigned)*is_boot);
        if (err == ESP_OK && *is_boot) err = draw_cursor(s_boot_cursor_enabled);
    } else if (*is_boot) {
        err = draw_boot_screen();
        if (err == ESP_OK) err = draw_cursor(s_boot_cursor_enabled);
    } else {
        if (boot) {
            ESP_LOGW(TAG, "HW3 PORTRAIT_CASE: CPC landscape boot requires width 320; drawing diagnostic");
        }
        err = draw_diagnostic(idx);
    }
    if (err == ESP_OK && *is_boot) ESP_LOGI(TAG, "HW3 BOOT_SCREEN_DRAWN case=%u", idx);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "HW3 FULL_REPAINT_PASS case=%u mode=%s", idx,
                 *is_boot ? "BOOT" : "MIRE");
    }
    return err;
}

static void print_uart_help(void)
{
    ESP_LOGI(TAG, "HW3 UART_CALIBRATION: m=8 MADCTL, n=6 fallback cases; 0..9,a,c,d,e=select case; b=boot; r=default; ?=help");
    ESP_LOGI(TAG, "HW3 ALT_CASES: 8=MV0 MX0 MY0, 9=MV0 MX1 MY0 (default candidate), a=MV0 MX0 MY1, c=MV0 MX1 MY1; d/e=software experiments");
    ESP_LOGI(TAG, "HW4 UART_VIDEO: v=next MODE0/1/2, p=next palette ink1 colour 0..26, z=cursor toggle BOTH BOOT/HW4, w=MODE2 OR/viewport, r=HW3 boot");
    ESP_LOGI(TAG, "HW3 BOOT_CURSOR_HELP: steady by default; t=toggle 500ms diagnostic blink on BOOT only");
    ESP_LOGI(TAG, "HW3 CASE_BITS: index 0..7=(swap_xy?1:0)+(mirror_x?2:0)+(mirror_y?4:0); 8..11=MV0 native 320x240 (mirror combinations)");
}

void app_main(void)
{
    /* HW3-C3: candidate MV=0 / MX=1 full 320x240. The real CYD photo
     * for case 8 + boot shows legible but mirrored text; independently
     * testing the X mirror is more evidence-driven than using the failed
     * software-rotation 12/13 path. PO must confirm orientation visually.
     */
    const unsigned int default_case = 9U;
    unsigned int selected_case = default_case;
    bool is_boot = false;
    ESP_LOGI(TAG, "HW3 START");
    ESP_LOGI(TAG, "HW3 BUILD_IDENT project=loco_esp32_display_probe target=esp32 idf=%s rgb_order=%s swap_xy=%d mirror_x=%d mirror_y=%d default_case=%u",
             esp_get_idf_version(), HW3_LCD_BGR ? "BGR" : "RGB",
             HW3_SWAP_XY, HW3_MIRROR_X, HW3_MIRROR_Y, default_case);
    esp_err_t err = cyd_lcd_init();
    if (err == ESP_OK) {
        s_dma_band = cyd_lcd_band();
        if (s_dma_band == NULL) err = ESP_ERR_INVALID_STATE;
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HW3 LCD_INIT_FAIL err=%s", esp_err_to_name(err));
        log_device_memory("LCD_INIT_FAIL");
        return;
    }
    ESP_LOGI(TAG, "HW3 LCD_INIT_PASS");
    log_device_memory("LCD_INIT_PASS");

    err = show_case(selected_case, true, &is_boot);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HW3 LCD_DRAW_FAIL err=%s", esp_err_to_name(err));
        log_device_memory("LCD_DRAW_FAIL");
        return;
    }
    err = cyd_lcd_backlight(true);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HW3 LCD_BACKLIGHT_FAIL err=%s", esp_err_to_name(err));
        return;
    }
    log_device_memory("BOOT_SCREEN_DRAWN");
    CydLcdDiagnostics lcd_diag;
    if (cyd_lcd_diagnostics(&lcd_diag))
        ESP_LOGI(TAG, "HW4B DRIVER init=%u fault=%u case=%u transfers=%u timeouts=%u",
                 (unsigned)lcd_diag.initialized, (unsigned)lcd_diag.dma_fault,
                 lcd_diag.orientation, lcd_diag.transfer_count, lcd_diag.timeout_count);
    ESP_LOGI(TAG, "HW3 BOOT_CURSOR_POLICY visible=%u blink=%u case=%u (blink experimental OFF by default)",
             (unsigned)s_boot_cursor_enabled, (unsigned)s_boot_cursor_blink, selected_case);

    /* Console still uses UART0 for ESP_LOGx, and UART driver gives us
     * single-character control from idf.py monitor (no keyboard dependency).
     */
    bool input_ready = uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0) == ESP_OK;
    if (!input_ready) ESP_LOGW(TAG, "HW3 UART_RX_UNAVAILABLE: boot cursor remains steady; UART controls unavailable");
    print_uart_help();

    TickType_t last_toggle = xTaskGetTickCount();
    bool cursor_visible = s_boot_cursor_enabled;
    for (;;) {
        uint8_t key = 0;
        int received = input_ready
            ? uart_read_bytes(UART_NUM_0, &key, 1, pdMS_TO_TICKS(30))
            : 0;
        if (!input_ready) vTaskDelay(pdMS_TO_TICKS(30));
        if (received == 1) {
            if (key == 'v' || key == 'V') {
                s_hw4_mode = (s_hw4_mode + 1U) % 3U;
                s_hw4_palette = 24U;
                s_hw4_cursor_visible = true;
                err = hw4_scene(s_hw4_mode);
                is_boot = false;
            } else if ((key == 'p' || key == 'P') && s_hw4_active) {
                s_hw4_palette = (s_hw4_palette + 1U) % 27U;
                (void)cpc_video_set_ink(&s_hw4_video, 1U, s_hw4_palette);
                ESP_LOGI(TAG, "HW4 PALETTE colour=%u ink=1", s_hw4_palette);
                err = hw4_repaint();
            } else if (key == 'z' || key == 'Z') {
                if (s_hw4_active) {
                    s_hw4_cursor_visible = !s_hw4_cursor_visible;
                    (void)cpc_video_cursor(&s_hw4_video, 1U, 5U, s_hw4_cursor_visible);
                    ESP_LOGI(TAG, "HW4 CURSOR visible=%u", (unsigned)s_hw4_cursor_visible);
                    err = hw4_repaint();
                } else if (is_boot) {
                    s_boot_cursor_enabled = !s_boot_cursor_enabled;
                    cursor_visible = s_boot_cursor_enabled;
                    err = draw_cursor(cursor_visible);
                    ESP_LOGI(TAG, "HW3 BOOT_CURSOR visible=%u blink=%u case=%u",
                             (unsigned)s_boot_cursor_enabled,
                             (unsigned)s_boot_cursor_blink, selected_case);
                } else {
                    ESP_LOGI(TAG, "HW3 BOOT_CURSOR_IGNORED reason=not_on_boot");
                }
            } else if ((key == 't' || key == 'T') && is_boot && !s_hw4_active) {
                s_boot_cursor_blink = !s_boot_cursor_blink;
                cursor_visible = s_boot_cursor_enabled;
                err = draw_cursor(cursor_visible);
                ESP_LOGI(TAG, "HW3 BOOT_CURSOR_BLINK enabled=%u interval_ms=%u (diagnostic only)",
                         (unsigned)s_boot_cursor_blink, (unsigned)HW3_CURSOR_MS);
            } else if ((key == 'w' || key == 'W') && s_hw4_active && s_hw4_mode == 2U) {
                CpcMode2Display next = s_hw4_video.mode2_display == CPC_MODE2_OR_PAIR
                     ? CPC_MODE2_VIEWPORT : CPC_MODE2_OR_PAIR;
                unsigned left = next == CPC_MODE2_VIEWPORT ? 320U : 0U;
                (void)cpc_video_mode2_display(&s_hw4_video, next, left);
                ESP_LOGI(TAG, "HW4 MODE2_VIEW display=%u left=%u", (unsigned)next, left);
                err = hw4_repaint();
            } else if (key == 'm' || key == 'M') {
                s_hw4_active = false;
                ESP_LOGI(TAG, "HW3 MATRIX_BEGIN count=8 hold_ms=%d", HW3_MATRIX_HOLD_MS);
                for (unsigned int idx = 0; idx < 8; ++idx) {
                    err = show_case(idx, false, &is_boot);
                    if (err != ESP_OK) break;
                    vTaskDelay(pdMS_TO_TICKS(HW3_MATRIX_HOLD_MS));
                }
                if (err == ESP_OK) err = show_case(selected_case, true, &is_boot);
                ESP_LOGI(TAG, "HW3 MATRIX_END restored_case=%u", selected_case);
            } else if (key == 'n' || key == 'N') {
                s_hw4_active = false;
                ESP_LOGI(TAG, "HW3 FALLBACK_MATRIX_BEGIN cases=8..13 hold_ms=%d", HW3_MATRIX_HOLD_MS);
                for (unsigned int idx = 8; idx <= HW3_SOFTWARE_ROTATE_CCW; ++idx) {
                    err = show_case(idx, false, &is_boot);
                    if (err != ESP_OK) break;
                    vTaskDelay(pdMS_TO_TICKS(HW3_MATRIX_HOLD_MS));
                }
                if (err == ESP_OK) err = show_case(selected_case, true, &is_boot);
                ESP_LOGI(TAG, "HW3 FALLBACK_MATRIX_END restored_case=%u", selected_case);
            } else if ((key >= '0' && key <= '9') || key == 'a' || key == 'c' ||
                       key == 'd' || key == 'e') {
                s_hw4_active = false;
                selected_case = (key >= '0' && key <= '9') ? (unsigned int)(key - '0')
                              : key == 'a' ? 10U : key == 'c' ? 11U
                              : key == 'd' ? 12U : 13U;
                err = show_case(selected_case, false, &is_boot);
            } else if (key == 'b' || key == 'B') {
                s_hw4_active = false;
                err = show_case(selected_case, true, &is_boot);
            } else if (key == 'r' || key == 'R') {
                s_hw4_active = false;
                selected_case = default_case;
                err = show_case(selected_case, true, &is_boot);
            } else if (key == '?') {
                print_uart_help();
            }
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "HW3 CALIBRATION_FAIL case=%u err=%s", selected_case, esp_err_to_name(err));
                log_device_memory("CALIBRATION_FAIL");
                return;
            }
            if (is_boot && key != 'z' && key != 'Z' && key != 't' && key != 'T')
                cursor_visible = s_boot_cursor_enabled;
            last_toggle = xTaskGetTickCount();
        }
        if (is_boot && s_boot_cursor_enabled && s_boot_cursor_blink &&
            (TickType_t)(xTaskGetTickCount() - last_toggle) >= pdMS_TO_TICKS(HW3_CURSOR_MS)) {
            cursor_visible = !cursor_visible;
            err = draw_cursor(cursor_visible);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "HW3 CURSOR_DRAW_FAIL err=%s", esp_err_to_name(err));
                log_device_memory("CURSOR_DRAW_FAIL");
                return;
            }
            last_toggle = xTaskGetTickCount();
        }
    }
}
