/*
 * HW4-C1: first real native Locomotive BASIC PRINT on ESP32 CYD TFT.
 * No duplicate BASIC engine, Z80, second LCD transport, REPL, SD or touch.
 * One FreeRTOS app_main owns both CPC video and all LCD DMA calls.
 */
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include "cpc_font.h"
#include "cpc_text.h"
#include "cpc_video.h"
#include "cyd_ili9341.h"
#include "esp_app_desc.h"
#include "esp_heap_caps.h"
#include "esp_idf_version.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum {
    PROGRAM_CAPACITY = 8192,
    VARIABLES_CAPACITY = 64,
    TEMP_CAPACITY = 2048,
    OUTPUT_CAPACITY = 4096,
    LCD_WIDTH = 320,
    LCD_HEIGHT = 240,
    LCD_ROWS_PER_BAND = 8,
    CPC_ROWS = 25
};

typedef struct {
    BasicProgram program;
    BasicVariableStore variables;
    BasicSessionRuntime runtime;
    uint8_t bytes[PROGRAM_CAPACITY];
    BasicVariableEntry entries[VARIABLES_CAPACITY];
    uint8_t temporary[TEMP_CAPACITY];
    uint8_t output[OUTPUT_CAPACITY];
    size_t written;
} BasicStorage;

static BasicStorage s_basic;
static CpcVideo s_video;
static CpcText s_text;
static uint8_t s_vram[CPC_VIDEO_BYTES];

/* Deliberately a diagnostic comparison, never an LCD/rendering source. */
static const uint8_t s_expected_print[] = {0x20U, 0x35U, 0x20U, 0x0aU};

static uint8_t glyph(void *context, uint8_t character, unsigned row)
{
    (void)context;
    return hw3_glyph_row(character, row);
}

static void memory_report(const char *stage)
{
    CydLcdDiagnostics d;
    if (!cyd_lcd_diagnostics(&d)) {
        printf("HW4-C1 MEMORY_FAIL stage=%s\n", stage);
        return;
    }
    printf("HW4-C1 DEVICE_MEMORY stage=%s heap8_free=%u "
           "heap8_largest=%u heap8_min=%u stack_margin_bytes=%u "
           "dma_transfers=%u dma_timeouts=%u dma_fault=%u lcd_error=%s\n",
           stage, d.heap8_free, d.heap8_largest, d.heap8_min,
           d.stack_margin_bytes, d.transfer_count, d.timeout_count,
           (unsigned)d.dma_fault, esp_err_to_name(d.last_error));
}

static bool failure(const char *phase, int code)
{
    printf("HW4-C1 FAIL phase=%s code=%d\n", phase, code);
    memory_report(phase);
    return false;
}

static bool render_band(unsigned top)
{
    uint8_t *const band = cyd_lcd_band(); /* owned by driver, 5120 bytes */
    uint16_t scan[LCD_WIDTH];             /* transient 640-byte stack row */
    if (band == NULL || top + LCD_ROWS_PER_BAND > LCD_HEIGHT)
        return failure("LCD_BAND_ACCESS", -1);

    for (unsigned dy = 0U; dy < LCD_ROWS_PER_BAND; ++dy) {
        if (!cpc_video_render_row(&s_video, top + dy, scan, LCD_WIDTH))
            return failure("VIDEO_RENDER", (int)(top + dy));
        for (unsigned x = 0U; x < LCD_WIDTH; ++x) {
            size_t offset = ((size_t)dy * LCD_WIDTH + x) * 2U;
            band[offset] = (uint8_t)(scan[x] >> 8U);
            band[offset + 1U] = (uint8_t)scan[x];
        }
    }

    /* cyd_lcd_send blocks until the DMA completion, or fails closed on timeout.
     * This is the ONLY invocation site; no other task touches the buffer.
     */
    esp_err_t error = cyd_lcd_send(0, (int)top, LCD_WIDTH, LCD_ROWS_PER_BAND);
    if (error != ESP_OK) {
        printf("HW4-C1 LCD_SEND_FAIL top=%u err=%s\n",
               top, esp_err_to_name(error));
        return failure("LCD_DMA", (int)error);
    }
    return true;
}

static bool repaint_full(void)
{
    for (unsigned top = 0U; top < LCD_HEIGHT; top += LCD_ROWS_PER_BAND)
        if (!render_band(top)) return false;
    (void)cpc_video_take_dirty(&s_video);
    return true;
}

static bool repaint_dirty(void)
{
    /* cpc_video_take_dirty covers the 25 logical 8px bands only.
     * Physical margins were painted in repaint_full().
     */
    uint32_t mask = cpc_video_take_dirty(&s_video);
    for (unsigned i = 0U; i < CPC_ROWS; ++i) {
        if ((mask & (UINT32_C(1) << i)) != 0U) {
            if (!render_band(CPC_VIDEO_VIEW_TOP + i * LCD_ROWS_PER_BAND))
                return false;
        }
    }
    return true;
}

static bool basic_submit(const char *source)
{
    size_t length = strlen(source);
    BSRResult r = bsr_submit(&s_basic.runtime,
                             (const uint8_t *)source, length,
                             s_basic.temporary, sizeof(s_basic.temporary),
                             s_basic.output, sizeof(s_basic.output),
                             &s_basic.written);
    if (r.status != BSR_OK || s_basic.written != 0U) {
        printf("HW4-C1 BASIC_SUBMIT_FAIL input=%s BSR=%d BS=%d BT=%d "
               "BP=%d BL=%d\n", source, (int)r.status,
               (int)r.session.status, (int)r.session.tokenizer_status,
               (int)r.session.program_status, (int)r.session.listing_status);
        return failure("BASIC_SUBMIT", (int)r.status);
    }
    return true;
}

static bool basic_run(void)
{
    static const char *const program[] = {
        "10 A%=2", "20 B%=A%+3", "30 PRINT B%", "40 END"
    };
    if (bp_init(&s_basic.program, s_basic.bytes, sizeof(s_basic.bytes)) != BP_OK)
        return failure("BP_INIT", -1);
    if (bvs_init(&s_basic.variables, s_basic.entries, VARIABLES_CAPACITY) != BVS_OK)
        return failure("BVS_INIT", -1);
    BSRResult init = bsr_init_with_store(&s_basic.runtime, &s_basic.program,
                                         &s_basic.variables);
    if (init.status != BSR_OK) return failure("BSR_INIT", (int)init.status);

    for (size_t i = 0U; i < sizeof(program) / sizeof(program[0]); ++i)
        if (!basic_submit(program[i])) return false;
    if (!basic_submit("RUN")) return false;
    printf("HW4-C1 BSR_RUN state=%u lines=4\n",
           (unsigned)s_basic.runtime.state);

    size_t print_count = 0U;
    unsigned steps = 0U;
    for (;;) {
        /* Each call executes one real tokenized BASIC line, no copied result. */
        BSRResult r = bsr_step(&s_basic.runtime, s_basic.output,
                               sizeof(s_basic.output), &s_basic.written);
        if (r.status == BSR_END) {
            if (steps != 4U || print_count != sizeof(s_expected_print) ||
                s_text.bytes_received != print_count ||
                s_text.glyphs_drawn != 3U ||
                s_text.row != 1U || s_text.column != 0U)
                return failure("BSR_END_INTEGRITY", (int)steps);
            printf("HW4-C1 BSR_END status=BE_END steps=%u "
                   "display_bytes=%zu input_fnv1a=%08lx\n",
                   steps, s_text.bytes_received,
                   (unsigned long)s_text.input_fnv1a);
            return true;
        }
        if (r.status != BSR_OK || r.executor_status != BE_OK)
        {
            printf("HW4-C1 BASIC_STEP_FAIL BSR=%d BE=%d step=%u\n",
                   (int)r.status, (int)r.executor_status, steps);
            return failure("BSR_STEP", (int)r.status);
        }
        ++steps;
        if (steps > 4U) return failure("BSR_EXCESS_STEPS", (int)steps);
        if (s_basic.written == 0U) continue;
        if (print_count != 0U ||
            s_basic.written != sizeof(s_expected_print) ||
            memcmp(s_basic.output, s_expected_print, sizeof(s_expected_print)) != 0)
            return failure("PRINT_MISMATCH", (int)s_basic.written);

        /* UART records the actual bytes, not an independently generated 5. */
        printf("HW4-C1 PRINT_BYTES length=%zu hex=", s_basic.written);
        for (size_t i = 0U; i < s_basic.written; ++i)
            printf("%02x", (unsigned)s_basic.output[i]);
        printf("\n");
        if (!cpc_text_write(&s_text, s_basic.output, s_basic.written))
            return failure("TEXT_ADAPTER", -1);
        print_count += s_basic.written;
        if (!repaint_dirty()) return false;
        printf("HW4-C1 TFT_PRINT_PASS bytes=%zu case=9 mode=1 "
               "columns=40 rows=25\n", s_text.bytes_received);
    }
}

void app_main(void)
{
    const esp_app_desc_t *desc = esp_app_get_description();
    printf("HW4-C1 START project=%s version=%s idf=%s target=esp32 "
           "ON_DEVICE_UNVERIFIED\n", desc->project_name,
           desc->version, esp_get_idf_version());
    memory_report("before_lcd");
    esp_err_t err = cyd_lcd_init();
    if (err != ESP_OK) {
        (void)failure("LCD_INIT", (int)err);
        return;
    }
    printf("HW4-C1 LCD_INIT_PASS dma_bytes=%u\n", CYD_LCD_DMA_BYTES);
    err = cyd_lcd_orientation(9U, cpc_video_palette_rgb565(1U));
    if (err != ESP_OK) {
        (void)failure("LCD_ORIENTATION", (int)err);
        return;
    }
    printf("HW4-C1 ORIENTATION_PASS case=%u\n",
           cyd_lcd_current_orientation());
    if (!cpc_video_init(&s_video, s_vram, sizeof(s_vram), CPC_MODE_1) ||
        !cpc_video_set_ink(&s_video, 0U, 1U) ||
        !cpc_video_set_ink(&s_video, 1U, 24U) ||
        !cpc_video_set_border(&s_video, 1U) ||
        !cpc_video_set_text_colors(&s_video, 1U, 0U) ||
        !cpc_text_init(&s_text, &s_video, glyph, NULL)) {
        (void)failure("VIDEO_INIT", -1);
        return;
    }
    printf("HW4-C1 VIDEO_READY mode=1 logical=320x200 cols=40 rows=25 "
           "vram_bytes=%u foreground_ink=24 background_ink=1\n",
           CPC_VIDEO_BYTES);
    if (!repaint_full()) return;
    memory_report("display_initialized");
    if (!basic_run()) return;
    err = cyd_lcd_backlight(true);
    if (err != ESP_OK) {
        (void)failure("BACKLIGHT", (int)err);
        return;
    }
    memory_report("complete");
    printf("HW4-C1 ON_DEVICE_TEST_PASS_CANDIDATE "
           "photo_and_uart_required=1\n");
}
