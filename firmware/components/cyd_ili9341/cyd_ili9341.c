/* CYD transport extracted from HW3; BASIC/render independent. MIT. */
#include "cyd_ili9341.h"
#include <limits.h>
#include <stddef.h>
#include <string.h>
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_vendor.h"
#include "esp_lcd_ili9341.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#define LCD_HOST SPI2_HOST
#define LCD_MOSI GPIO_NUM_13
#define LCD_SCLK GPIO_NUM_14
#define LCD_CS GPIO_NUM_15
#define LCD_DC GPIO_NUM_2
#define LCD_BL GPIO_NUM_21
#define LCD_CLOCK_HZ (20 * 1000 * 1000)
#define LCD_W 320
#define LCD_NATIVE_W 240
#define LCD_NATIVE_H 320
#define LCD_H 240
#define LCD_TILE 8
#define LCD_SOFTWARE_ROTATE_CW 12U
#define LCD_SOFTWARE_ROTATE_CCW 13U
#ifndef LCD_BGR
#define LCD_BGR 0
#endif
static const char *TAG = "CYD_LCD";
static esp_lcd_panel_handle_t s_panel;
static esp_lcd_panel_io_handle_t s_io;
static SemaphoreHandle_t s_done;
static uint8_t *s_band;
static bool s_bus_owned, s_fault;
static unsigned s_active_case = UINT_MAX;
static int s_width = LCD_NATIVE_W, s_height = LCD_NATIVE_H;
static unsigned s_transfers, s_timeouts;
static esp_err_t s_last_error = ESP_OK;
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

uint8_t *cyd_lcd_band(void) { return (s_panel && !s_fault) ? s_band : NULL; }
esp_err_t cyd_lcd_send(int x, int y, int width, int height)
{
    if (!s_panel || !s_done || s_fault) return ESP_ERR_INVALID_STATE;
    if (x < 0 || y < 0 || width <= 0 || height <= 0 ||
        x > s_width || width > s_width - x ||
        y > s_height || height > s_height - y ||
        (size_t)width*(size_t)height > CYD_LCD_DMA_BYTES/2U)
        return ESP_ERR_INVALID_ARG;
    (void)xSemaphoreTake(s_done,0);
    esp_err_t err = esp_lcd_panel_draw_bitmap(s_panel,x,y,x+width,y+height,s_band);
    if (err == ESP_OK && xSemaphoreTake(s_done,pdMS_TO_TICKS(2000)) != pdTRUE) {
        err = ESP_ERR_TIMEOUT; ++s_timeouts;
    }
    if (err != ESP_OK) {
        s_fault = true; /* DMA/ISR ownership ambiguous: keep resources pinned. */
        (void)gpio_set_level(LCD_BL,0);
        ESP_LOGE(TAG,"HW4B DMA_FAIL err=%s buffer_retained=1",esp_err_to_name(err));
    } else ++s_transfers;
    s_last_error = err; return err;
}
/*
 * Clear all 240x320 native GRAM in portrait BEFORE applying a new MADCTL.
 * This covers the 80-pixel stale strip seen on physical CYD when a 320x240
 * logical bitmap was sent but the panel remained effectively in portrait.
 */
static esp_err_t clear_native_gram(bool wide, uint16_t rgb)
{
    esp_err_t err = esp_lcd_panel_swap_xy(s_panel, false);
    if (err != ESP_OK) return err;
    err = esp_lcd_panel_mirror(s_panel, false, false);
    if (err != ESP_OK) return err;
    const int width = wide ? LCD_W : LCD_NATIVE_W;
    s_width = width;
    s_height = wide ? LCD_H : LCD_NATIVE_H;
    const int height = wide ? LCD_H : LCD_NATIVE_H;
    for (int i = 0; i < width * LCD_TILE; ++i) {
        s_band[2 * i] = (uint8_t)(rgb >> 8);
        s_band[2 * i + 1] = (uint8_t)rgb;
    }
    for (int top = 0; top < height; top += LCD_TILE) {
        err = cyd_lcd_send(0, top, width, LCD_TILE);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}

/* Index bits encode all eight hardware MADCTL combinations:
 * bit0=swap_xy, bit1=mirror_x, bit2=mirror_y.
 * swap=0 MUST use 240x320 coordinates; swap=1 uses 320x240.
 */
esp_err_t cyd_lcd_orientation(unsigned int idx, uint16_t rgb)
{
    if (s_panel == NULL || s_fault) return ESP_ERR_INVALID_STATE;
    if (idx > 13U) return ESP_ERR_INVALID_ARG;
    /* The first boot of case 9 looks correct on the physical CYD but
     * selecting 9 then b used to corrupt the image. This guard separates
     * ordinary redraws from explicit MADCTL state changes. It does not
     * claim that switching between different cases is safe.
     */
    if (s_active_case == idx) {
        ESP_LOGI(TAG, "HW3 ORIENTATION_REUSED case=%u MADCTL_UNCHANGED=1 CLEAR_SKIPPED=1", idx);
        return ESP_OK;
    }
    const bool native_wide = idx >= 8U && idx <= 11U;
    const bool software = idx == LCD_SOFTWARE_ROTATE_CW || idx == LCD_SOFTWARE_ROTATE_CCW;
    const bool swap = !native_wide && !software && (idx & 1U) != 0;
    const bool mirror_x = native_wide ? ((idx - 8U) & 1U) != 0
                                 : (!software && (idx & 2U) != 0);
    const bool mirror_y = native_wide ? ((idx - 8U) & 2U) != 0
                                 : (!software && (idx & 4U) != 0);
    const int width = (native_wide || swap) ? LCD_W : LCD_NATIVE_W;
    const int height = (native_wide || swap) ? LCD_H : LCD_NATIVE_H;
    ESP_LOGI(TAG, "HW3 ORIENTATION_CASE index=%u mode=%s swap_xy=%u mirror_x=%u mirror_y=%u geometry=%dx%d",
             idx, software ? "SOFTWARE_ROTATED" : native_wide ? "NATIVE_LANDSCAPE" : "MADCTL_MATRIX",
             (unsigned)swap, (unsigned)mirror_x, (unsigned)mirror_y, width, height);
    /* Full GRAM coverage in the addressing model under test. Note that
     * the 320x240-MV0 path is intentionally a separate hardware hypothesis.
     */
    esp_err_t err = clear_native_gram(native_wide,rgb);
    if (err != ESP_OK) return err;
    err = esp_lcd_panel_swap_xy(s_panel, swap);
    if (err != ESP_OK) return err;
    err = esp_lcd_panel_mirror(s_panel, mirror_x, mirror_y);
    if (err == ESP_OK) {
        s_active_case = idx;
        s_width = width;
        s_height = height;
        ESP_LOGI(TAG, "HW3 ORIENTATION_APPLIED case=%u MADCTL_UPDATED=1", idx);
    }
    return err;
}

esp_err_t cyd_lcd_init(void)
{
    if (s_panel || s_bus_owned || s_done || s_band || s_fault) return ESP_ERR_INVALID_STATE;
    /* Backlight remains OFF until a complete frame is sent successfully. */
    gpio_config_t bl = {
        .pin_bit_mask = 1ULL << LCD_BL,
        .mode = GPIO_MODE_OUTPUT,
    };
    esp_err_t err = gpio_config(&bl);
    if (err != ESP_OK) goto fail;
    err = gpio_set_level(LCD_BL, 0);
    if (err != ESP_OK) goto fail;

    s_band = heap_caps_malloc(CYD_LCD_DMA_BYTES,
                                  MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA);
    if (s_band == NULL) { err = ESP_ERR_NO_MEM; goto fail; }
    s_done = xSemaphoreCreateBinary();
    if (s_done == NULL) { err = ESP_ERR_NO_MEM; goto fail; }

    spi_bus_config_t bus_cfg = {
        .sclk_io_num = LCD_SCLK,
        .mosi_io_num = LCD_MOSI,
        .miso_io_num = -1,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = CYD_LCD_DMA_BYTES + 16,
    };
    err = spi_bus_initialize(LCD_HOST, &bus_cfg, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) goto fail;
    s_bus_owned = true;

    esp_lcd_panel_io_spi_config_t io_cfg = {
        .cs_gpio_num = LCD_CS,
        .dc_gpio_num = LCD_DC,
        .spi_mode = 0,
        .pclk_hz = LCD_CLOCK_HZ,
        .trans_queue_depth = 2,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
    };
    err = esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)LCD_HOST,
                                   &io_cfg, &s_io);
    if (err != ESP_OK) goto fail;

    esp_lcd_panel_io_callbacks_t cb = {
        .on_color_trans_done = on_color_done,
    };
    err = esp_lcd_panel_io_register_event_callbacks(s_io, &cb,
                                                      s_done);
    if (err != ESP_OK) goto fail;

    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = -1, /* LCD reset is wired to EN on common CYD. */
        .rgb_ele_order = LCD_BGR ? LCD_RGB_ELEMENT_ORDER_BGR
                                    : LCD_RGB_ELEMENT_ORDER_RGB,
        .data_endian = LCD_RGB_DATA_ENDIAN_BIG,
        .bits_per_pixel = 16,
    };
    err = esp_lcd_new_panel_ili9341(s_io, &panel_cfg, &s_panel);
    if (err != ESP_OK) goto fail;
    err = esp_lcd_panel_reset(s_panel);
    if (err != ESP_OK) goto fail;
    err = esp_lcd_panel_init(s_panel);
    if (err != ESP_OK) goto fail;
    /* MADCTL is configured by set_orientation AFTER the native clear. */
    err = esp_lcd_panel_disp_on_off(s_panel, true);
    if (err != ESP_OK) goto fail;
    s_last_error = ESP_OK;
    return ESP_OK;
fail:
    s_last_error = err;
    if (s_panel) { (void)esp_lcd_panel_del(s_panel); s_panel = NULL; }
    if (s_io) { (void)esp_lcd_panel_io_del(s_io); s_io = NULL; }
    if (s_bus_owned) { (void)spi_bus_free(LCD_HOST); s_bus_owned = false; }
    if (s_done) { vSemaphoreDelete(s_done); s_done = NULL; }
    if (s_band) { heap_caps_free(s_band); s_band = NULL; }
    (void)gpio_set_level(LCD_BL, 0);
    return err;
}

unsigned cyd_lcd_current_orientation(void) { return s_active_case; }
esp_err_t cyd_lcd_backlight(bool enabled)
{
    if (!s_panel || s_fault) return ESP_ERR_INVALID_STATE;
    esp_err_t err=gpio_set_level(LCD_BL,enabled?1:0);
    s_last_error=err; return err;
}
bool cyd_lcd_diagnostics(CydLcdDiagnostics *d)
{
    if (!d) return false;
    memset(d,0,sizeof(*d));
    d->initialized = s_panel != NULL; d->dma_fault=s_fault;
    d->orientation=s_active_case;
    d->width=(unsigned)s_width; d->height=(unsigned)s_height;
    d->transfer_count=s_transfers; d->timeout_count=s_timeouts;
    d->heap8_free=(unsigned)heap_caps_get_free_size(MALLOC_CAP_8BIT);
    d->heap8_largest=(unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
    d->heap8_min=(unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT);
    d->stack_margin_bytes=(unsigned)uxTaskGetStackHighWaterMark(NULL);
    d->last_error=s_last_error; return true;
}
