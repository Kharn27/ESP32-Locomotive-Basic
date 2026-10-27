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
#include "driver/uart.h"
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
#define HW3_NATIVE_W 240
#define HW3_NATIVE_H 320
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
static esp_lcd_panel_handle_t s_panel;
static uint8_t *s_dma_band;
static SemaphoreHandle_t s_transfer_done;
static uint8_t s_screen[HW3_ROWS][HW3_COLS];
static unsigned int s_active_case;

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
    int x = HW3_CURSOR_COL * HW3_TILE;
    int y = HW3_CPC_Y + HW3_CURSOR_ROW * HW3_TILE;
    if (s_active_case == HW3_SOFTWARE_ROTATE_CW) {
        /* Portrait GRAM u=239-logical_y, v=logical_x. */
        int u = HW3_H - (y + HW3_TILE);
        int v = x;
        x = u; y = v;
    } else if (s_active_case == HW3_SOFTWARE_ROTATE_CCW) {
        /* Portrait GRAM u=logical_y, v=319-logical_x. */
        int u = y;
        int v = HW3_W - (x + HW3_TILE);
        x = u; y = v;
    }
    return lcd_send(x, y, HW3_TILE, HW3_TILE);
}


/*
 * Clear all 240x320 native GRAM in portrait BEFORE applying a new MADCTL.
 * This covers the 80-pixel stale strip seen on physical CYD when a 320x240
 * logical bitmap was sent but the panel remained effectively in portrait.
 */
static esp_err_t clear_native_gram(bool wide)
{
    esp_err_t err = esp_lcd_panel_swap_xy(s_panel, false);
    if (err != ESP_OK) return err;
    err = esp_lcd_panel_mirror(s_panel, false, false);
    if (err != ESP_OK) return err;
    const int width = wide ? HW3_W : HW3_NATIVE_W;
    const int height = wide ? HW3_H : HW3_NATIVE_H;
    for (int i = 0; i < width * HW3_TILE; ++i) {
        s_dma_band[2 * i] = (uint8_t)(HW3_BLUE_RGB565 >> 8);
        s_dma_band[2 * i + 1] = (uint8_t)HW3_BLUE_RGB565;
    }
    for (int top = 0; top < height; top += HW3_TILE) {
        err = lcd_send(0, top, width, HW3_TILE);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}

/* Index bits encode all eight hardware MADCTL combinations:
 * bit0=swap_xy, bit1=mirror_x, bit2=mirror_y.
 * swap=0 MUST use 240x320 coordinates; swap=1 uses 320x240.
 */
static esp_err_t set_orientation(unsigned int idx)
{
    const bool native_wide = idx >= 8U && idx <= 11U;
    const bool software = idx == HW3_SOFTWARE_ROTATE_CW || idx == HW3_SOFTWARE_ROTATE_CCW;
    const bool swap = !native_wide && !software && (idx & 1U) != 0;
    const bool mirror_x = native_wide ? ((idx - 8U) & 1U) != 0
                                 : (!software && (idx & 2U) != 0);
    const bool mirror_y = native_wide ? ((idx - 8U) & 2U) != 0
                                 : (!software && (idx & 4U) != 0);
    const int width = (native_wide || swap) ? HW3_W : HW3_NATIVE_W;
    const int height = (native_wide || swap) ? HW3_H : HW3_NATIVE_H;
    ESP_LOGI(TAG, "HW3 ORIENTATION_CASE index=%u mode=%s swap_xy=%u mirror_x=%u mirror_y=%u geometry=%dx%d",
             idx, software ? "SOFTWARE_ROTATED" : native_wide ? "NATIVE_LANDSCAPE" : "MADCTL_MATRIX",
             (unsigned)swap, (unsigned)mirror_x, (unsigned)mirror_y, width, height);
    /* Full GRAM coverage in the addressing model under test. Note that
     * the 320x240-MV0 path is intentionally a separate hardware hypothesis.
     */
    esp_err_t err = clear_native_gram(native_wide);
    if (err != ESP_OK) return err;
    err = esp_lcd_panel_swap_xy(s_panel, swap);
    if (err != ESP_OK) return err;
    err = esp_lcd_panel_mirror(s_panel, mirror_x, mirror_y);
    if (err == ESP_OK) s_active_case = idx;
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
    /* HW3-C3: width must agree with set_orientation() for EVERY case.
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
        esp_err_t err = lcd_send(0, top, width, HW3_TILE);
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
        const char *label = s_active_case == HW3_SOFTWARE_ROTATE_CW ? "ROT 12" : "ROT 13";
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
        esp_err_t err = lcd_send(0, top, HW3_NATIVE_W, HW3_TILE);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}

static esp_err_t show_case(unsigned int idx, bool boot, bool *is_boot)
{
    esp_err_t err = set_orientation(idx);
    if (err != ESP_OK) return err;
    const bool native_wide = idx >= 8U && idx <= 11U;
    const bool software = idx == HW3_SOFTWARE_ROTATE_CW || idx == HW3_SOFTWARE_ROTATE_CCW;
    *is_boot = boot && (native_wide || software || ((idx & 1U) != 0));
    if (software) {
        err = draw_software_rotated(*is_boot, idx);
        if (err == ESP_OK) ESP_LOGI(TAG, "HW3 SOFTWARE_ROTATION_DRAWN case=%u boot=%u", idx,
                                    (unsigned)*is_boot);
        if (err == ESP_OK && *is_boot) err = draw_cursor(true);
    } else if (*is_boot) {
        err = draw_boot_screen();
        if (err == ESP_OK) err = draw_cursor(true);
    } else {
        if (boot) {
            ESP_LOGW(TAG, "HW3 PORTRAIT_CASE: CPC landscape boot requires width 320; drawing diagnostic");
        }
        err = draw_diagnostic(idx);
    }
    if (err == ESP_OK && *is_boot) ESP_LOGI(TAG, "HW3 BOOT_SCREEN_DRAWN case=%u", idx);
    return err;
}

static void print_uart_help(void)
{
    ESP_LOGI(TAG, "HW3 UART_CALIBRATION: m=8 MADCTL, n=6 fallback cases; 0..9,a,c,d,e=select case; b=boot; r=default; ?=help");
    ESP_LOGI(TAG, "HW3 ALT_CASES: 8=MV0 MX0 MY0, 9=MV0 MX1 MY0 (default candidate), a=MV0 MX0 MY1, c=MV0 MX1 MY1; d/e=software experiments");
    ESP_LOGI(TAG, "HW3 CASE_BITS: index 0..7=(swap_xy?1:0)+(mirror_x?2:0)+(mirror_y?4:0); 8..11=MV0 native 320x240 (mirror combinations)");
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
    /* MADCTL is configured by set_orientation AFTER the native clear. */
    return esp_lcd_panel_disp_on_off(s_panel, true);
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
    esp_err_t err = lcd_initialize();
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
    err = gpio_set_level(HW3_LCD_BL, 1);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HW3 LCD_BACKLIGHT_FAIL err=%s", esp_err_to_name(err));
        return;
    }
    log_device_memory("BOOT_SCREEN_DRAWN");
    ESP_LOGI(TAG, "HW3 CURSOR_BLINK_ACTIVE when_boot_visible=%u", (unsigned)is_boot);

    /* Console still uses UART0 for ESP_LOGx, and UART driver gives us
     * single-character control from idf.py monitor (no keyboard dependency).
     */
    bool input_ready = uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0) == ESP_OK;
    if (!input_ready) ESP_LOGW(TAG, "HW3 UART_RX_UNAVAILABLE: boot and blinking remain active");
    print_uart_help();

    TickType_t last_toggle = xTaskGetTickCount();
    bool cursor_visible = true;
    for (;;) {
        uint8_t key = 0;
        int received = input_ready
            ? uart_read_bytes(UART_NUM_0, &key, 1, pdMS_TO_TICKS(30))
            : 0;
        if (!input_ready) vTaskDelay(pdMS_TO_TICKS(30));
        if (received == 1) {
            if (key == 'm' || key == 'M') {
                ESP_LOGI(TAG, "HW3 MATRIX_BEGIN count=8 hold_ms=%d", HW3_MATRIX_HOLD_MS);
                for (unsigned int idx = 0; idx < 8; ++idx) {
                    err = show_case(idx, false, &is_boot);
                    if (err != ESP_OK) break;
                    vTaskDelay(pdMS_TO_TICKS(HW3_MATRIX_HOLD_MS));
                }
                if (err == ESP_OK) err = show_case(selected_case, true, &is_boot);
                ESP_LOGI(TAG, "HW3 MATRIX_END restored_case=%u", selected_case);
            } else if (key == 'n' || key == 'N') {
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
                selected_case = (key >= '0' && key <= '9') ? (unsigned int)(key - '0')
                              : key == 'a' ? 10U : key == 'c' ? 11U
                              : key == 'd' ? 12U : 13U;
                err = show_case(selected_case, false, &is_boot);
            } else if (key == 'b' || key == 'B') {
                err = show_case(selected_case, true, &is_boot);
            } else if (key == 'r' || key == 'R') {
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
            cursor_visible = true;
            last_toggle = xTaskGetTickCount();
        }
        if (is_boot && (TickType_t)(xTaskGetTickCount() - last_toggle) >= pdMS_TO_TICKS(HW3_CURSOR_MS)) {
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
