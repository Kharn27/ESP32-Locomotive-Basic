/* CYD transport extracted from HW3; BASIC/render independent. MIT. */
#include "cyd_ili9341.h"
#include "cyd_vscr_probe_policy.h"
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
/* A1-P1 diagnostics only: no active VSCR at boot. */
static bool s_vscr_active;
/* No persistent plan copy: 200-line VSA and other geometry are constants. */
static uint16_t s_vscr_tfa, s_vscr_offset;
static uint16_t s_vscr_params, s_vscr_marker_writes;
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

static esp_err_t vscr_latch(esp_err_t err)
{
    s_last_error=err;
    if(err!=ESP_OK) {
        s_fault=true;
        (void)gpio_set_level(LCD_BL,0);
        ESP_LOGE(TAG,"VSCR_P1_FAIL_STOP err=%s retry=0",esp_err_to_name(err));
    }
    return err;
}
static esp_err_t vscr_param(uint8_t cmd,const uint8_t *params,size_t n)
{
    if(!s_panel || !s_io || !s_done || s_fault) return ESP_ERR_INVALID_STATE;
    /* All callers execute in the sole CONSOLE task between completed DMA sends. */
    const esp_err_t err=esp_lcd_panel_io_tx_param(s_io,cmd,params,n);
    if(err==ESP_OK && s_vscr_params!=UINT16_MAX) ++s_vscr_params;
    return vscr_latch(err);
}
uint8_t *cyd_lcd_band(void)
{
    return (s_panel && !s_fault && !s_vscr_active) ? s_band : NULL;
}
esp_err_t cyd_lcd_send(int x, int y, int width, int height)
{
    if (!s_panel || !s_done || s_fault || s_vscr_active) return ESP_ERR_INVALID_STATE;
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
    if (s_panel == NULL || s_fault || s_vscr_active) return ESP_ERR_INVALID_STATE;
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


/* UART-only, bounded P1 diagnostic using the existing driver-owned DMA buffer.
 * The colour pattern codes every CPC row (binary column labels) and distinct
 * top/bottom margins. Its geometry is a HYPOTHESIS, not a controller verdict.
 */
esp_err_t cyd_lcd_vscr_probe_pattern(void)
{
    if(!s_panel || !s_band || s_fault || s_vscr_active ||
       s_active_case!=10U || s_width!=320 || s_height!=240)
        return ESP_ERR_INVALID_STATE;
    static const uint16_t stripes[4]={0xF800U,0x07E0U,0xFFE0U,0x07FFU};
    for(unsigned top=0U;top<240U;top+=8U) {
        for(unsigned dy=0U;dy<8U;++dy) {
            const unsigned y=top+dy;
            for(unsigned x=0U;x<320U;++x) {
                uint16_t rgb;
                if(y<20U) rgb=0x001FU;
                else if(y>=220U) rgb=0xF81FU;
                else {
                    const unsigned row=(y-20U)/8U;
                    rgb=stripes[row%4U];
                    if(x<8U) rgb=0x0000U;
                    if(x>=312U) rgb=0xFFFFU;
                    if(x>=24U && x<88U && ((row>>((x-24U)/8U))&1U))
                        rgb=0x0000U;
                }
                const size_t index=((size_t)dy*320U+x)*2U;
                s_band[index]=(uint8_t)(rgb>>8U);
                s_band[index+1U]=(uint8_t)rgb;
            }
        }
        const esp_err_t err=cyd_lcd_send(0,(int)top,320,8);
        if(err!=ESP_OK) return err;
    }
    return ESP_OK;
}
esp_err_t cyd_lcd_vscr_probe_begin(unsigned visible_start)
{
    CydVscrPlan plan;
    if(s_vscr_active || s_fault ||
       !cyd_vscr_plan(s_active_case,(unsigned)s_width,
                      (unsigned)s_height,visible_start,&plan))
        return ESP_ERR_INVALID_ARG;
    esp_err_t err=cyd_lcd_vscr_probe_pattern();
    if(err!=ESP_OK) return err;
    uint8_t def[6];
    cyd_vscr_def_bytes(&plan,def);
    err=vscr_param(0x33U,def,sizeof(def));
    if(err!=ESP_OK) return err;
    const uint8_t pos[2]={(uint8_t)(plan.tfa>>8U),(uint8_t)plan.tfa};
    err=vscr_param(0x37U,pos,sizeof(pos));
    if(err!=ESP_OK) return err;
    s_vscr_tfa=plan.tfa;
    s_vscr_offset=0U;
    s_vscr_active=true;
    return ESP_OK;
}
esp_err_t cyd_lcd_vscr_probe_shift(int direction,unsigned rows)
{
    uint16_t next;
    if(!s_vscr_active || s_fault ||
       !cyd_vscr_advance(s_vscr_offset,direction,rows,&next))
        return ESP_ERR_INVALID_ARG;
    const uint16_t vsp=(uint16_t)(s_vscr_tfa+next);
    const uint8_t pos[2]={(uint8_t)(vsp>>8U),(uint8_t)vsp};
    const esp_err_t err=vscr_param(0x37U,pos,sizeof(pos));
    if(err==ESP_OK) s_vscr_offset=next;
    return err;
}
esp_err_t cyd_lcd_vscr_probe_marker(void)
{
    if(!s_vscr_active || s_fault || !s_band) return ESP_ERR_INVALID_STATE;
    CydVscrPlan plan;
    if(!cyd_vscr_plan(10U,320U,240U,(unsigned)s_vscr_tfa-20U,&plan))
        return ESP_ERR_INVALID_STATE;
    const uint8_t column[4]={0U,96U,0U,223U};
    for(unsigned i=0U;i<128U;++i) {
        s_band[2U*i]=0xFFU;
        s_band[2U*i+1U]=0xFFU;
    }
    /* Eight independent raster writes to avoid crossing a circular boundary.
     * DMA buffer is not reused until the existing ISR completion semaphore.
     */
    for(unsigned y=208U;y<216U;++y) {
        uint16_t addr=0U;
        if(!cyd_vscr_address(&plan,s_vscr_offset,y,&addr))
            return ESP_ERR_INVALID_STATE;
        const uint8_t page[4]={(uint8_t)(addr>>8U),(uint8_t)addr,
                               (uint8_t)(addr>>8U),(uint8_t)addr};
        esp_err_t err=vscr_param(0x2AU,column,sizeof(column));
        if(err!=ESP_OK) return err;
        err=vscr_param(0x2BU,page,sizeof(page));
        if(err!=ESP_OK) return err;
        (void)xSemaphoreTake(s_done,0);
        err=esp_lcd_panel_io_tx_color(s_io,0x2CU,s_band,256U);
        if(err==ESP_OK && xSemaphoreTake(s_done,pdMS_TO_TICKS(2000))!=pdTRUE) {
            err=ESP_ERR_TIMEOUT; ++s_timeouts;
        }
        if(vscr_latch(err)!=ESP_OK) return err;
        ++s_transfers;
        if(s_vscr_marker_writes!=UINT16_MAX) ++s_vscr_marker_writes;
    }
    return ESP_OK;
}
esp_err_t cyd_lcd_vscr_probe_restore(void)
{
    if(!s_panel || s_fault) return ESP_ERR_INVALID_STATE;
    if(!s_vscr_active) return ESP_OK;
    /* Canonical default: zero scroll offset, VSCRDEF covering full 320 GRAM.
     * If any command fails, sticky fault + BL off; NEVER retry or repaint.
     */
    const uint8_t anchor[2]={(uint8_t)(s_vscr_tfa>>8U),
                              (uint8_t)s_vscr_tfa};
    const uint8_t full[6]={0U,0U,1U,64U,0U,0U};
    const uint8_t zero[2]={0U,0U};
    esp_err_t err=vscr_param(0x37U,anchor,sizeof(anchor));
    if(err!=ESP_OK) return err;
    err=vscr_param(0x33U,full,sizeof(full));
    if(err!=ESP_OK) return err;
    err=vscr_param(0x37U,zero,sizeof(zero));
    if(err!=ESP_OK) return err;
    s_vscr_active=false;
    s_vscr_offset=0U;
    return ESP_OK; /* CONSOLE must then repaint full logical 320x240. */
}
bool cyd_lcd_vscr_probe_is_active(void) { return s_vscr_active; }

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
    d->last_error=s_last_error;
    d->vscr_probe_active=s_vscr_active;
    d->vscr_param_commands=s_vscr_params;
    d->vscr_marker_writes=s_vscr_marker_writes;
    return true;
}
