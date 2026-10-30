/*
 * HW4-C2: real user-submitted native Locomotive BASIC via UART0 -> CPC TFT.
 * One app_main owns UART intake, BASIC session, CpcText, video and LCD DMA.
 * Native MODE1 scroll added in HW4-C3-B2; no Z80 or second SPI driver.
 */
#include "basic_session_runtime.h"
#include "hw4_pen_bridge.h"
#include "basic_variable_store.h"
#include "j1_15_c_string_arena.h"
#include "cpc_font.h"
#include "cpc_boot.h"
#include "cpc_text.h"
#include "cpc_uart_console.h"
#include "cpc_ready_policy.h"
#include "cpc_diag_policy.h"
#include "cpc_screen_nav.h"
#include "cpc_video.h"
#include "hw4_scroll_metrics.h"
#include "hw4_touch_t1.h"
#include "cyd_ili9341.h"
#include "uart_line.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_app_desc.h"
#include "esp_heap_caps.h"
#include "esp_idf_version.h"
#include "esp_cpu.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "sdkconfig.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum {
    PROGRAM_CAPACITY = 8192,
    VARIABLES_CAPACITY = J115C_VARIABLES_CAPACITY,
    STRING_SLOT_BYTES = J115C_STRING_SLOT_BYTES,
    STRING_ARENA_CAPACITY = J115C_STRING_ARENA_CAPACITY,
    TEMP_CAPACITY = 2048,
    OUTPUT_CAPACITY = 4096,
    LCD_WIDTH = 320,
    LCD_HEIGHT = 240,
    LCD_ROWS_PER_BAND = 8,
    CPC_ROWS = 25,
    RUN_STEP_BUDGET = 256,
    PEN_EVENT_CAPACITY = 3, /* A0 DRAM guard: 3 typed events, no heap/VRAM */
    ECHO_IDLE_MS = 20,
    TOUCH_POLL_MS = 20,
    ECHO_MAX_BYTES = UART_LINE_CAPACITY
};
/* Submit and RUN are strictly sequential in sole CONSOLE app_main.
 * Reuse static submission scratch for typed events: aligned C99 union,
 * unchanged 2048-byte tokenizer and 3-event execution capacities. */
typedef union {
    uint8_t temporary[TEMP_CAPACITY];
    BEVideoEvent events[PEN_EVENT_CAPACITY];
} BasicScratch;
typedef char HW4_PEN_SCRATCH_FITS[
    (sizeof(((BasicScratch *)0)->temporary) >=
     sizeof(((BasicScratch *)0)->events)) ? 1 : -1];
typedef struct {
    BasicProgram program;
    BasicVariableStore variables;
    BasicSessionRuntime runtime;
    uint8_t bytes[PROGRAM_CAPACITY];
    BasicVariableEntry entries[VARIABLES_CAPACITY];
    uint8_t string_arena[STRING_ARENA_CAPACITY]; /* s_basic-owned, no heap */
    BasicScratch scratch;
    uint8_t output[OUTPUT_CAPACITY];
    size_t written;
} BasicStorage;
typedef char J115C_BasicStorageArenaExtent[
    (sizeof(((BasicStorage *)0)->string_arena) ==
     (size_t)(VARIABLES_CAPACITY * STRING_SLOT_BYTES)) ? 1 : -1];
static BasicStorage s_basic;
static CpcVideo s_video;
static CpcText s_text;
static UartLine s_line;
static CpcUartEditor s_edit;
static CpcScreenNavigation s_nav;
static uint8_t s_vram[CPC_VIDEO_BYTES];
static size_t s_scroll_reported;
/* A0: CONSOLE-only class counters; a scroll-associated dirty flush may
 * also contain cursor, text or !CLS writes. Never label it scroll-exclusive. */
static Hw4ScrollMetrics s_scroll_metrics;
static Hw4TouchT1 s_touch; /* CONSOLE only; 0 heap, 0 extra tasks */
/* B2-C1 instrumentation: bounded histogram, never a second framebuffer. */
static struct {
    uint32_t flushes, bands, max_us, histogram[12];
    uint32_t idle_echo_batches, command_echo_batches, max_echo_batch;
    uint64_t repaint_us, spi_bytes;
} s_lcd_metrics;
static const uint32_t s_latency_bounds_us[12] = {
    500U, 1000U, 2000U, 4000U, 8000U, 16000U,
    32000U, 64000U, 128000U, 256000U, 512000U, UINT32_MAX
};
static uint32_t latency_quantile_upper(unsigned percent)
{
    uint32_t rank=(uint32_t)(((uint64_t)s_lcd_metrics.flushes*percent+99U)/100U);
    uint32_t seen=0U;
    if(rank==0U) return 0U;
    for(unsigned i=0U;i<12U;++i) {
        seen+=s_lcd_metrics.histogram[i];
        if(seen>=rank) return s_latency_bounds_us[i];
    }
    return UINT32_MAX;
}
static void echo_batch_record(unsigned size,bool command)
{
    if(size==0U) return;
    if(size>s_lcd_metrics.max_echo_batch)
        s_lcd_metrics.max_echo_batch=size;
    if(command) ++s_lcd_metrics.command_echo_batches;
    else ++s_lcd_metrics.idle_echo_batches;
}
static void lcd_metrics_report(const char *stage)
{
    printf("HW4-C3-B2-C1 LCD_METRICS stage=%s flushes=%u bands=%u "
           "spi_bytes=%llu scrolls=%u repaint_us_total=%llu "
           "repaint_p50_upper_us=%u repaint_p95_upper_us=%u repaint_max_us=%u "
           "echo_idle_batches=%u echo_command_batches=%u echo_batch_max=%u "
           "mode=histogram_upper_bounds\n",
           stage,(unsigned)s_lcd_metrics.flushes,(unsigned)s_lcd_metrics.bands,
           (unsigned long long)s_lcd_metrics.spi_bytes,
           (unsigned)s_text.scrolls,
           (unsigned long long)s_lcd_metrics.repaint_us,
           (unsigned)latency_quantile_upper(50U),
           (unsigned)latency_quantile_upper(95U),
           (unsigned)s_lcd_metrics.max_us,
           (unsigned)s_lcd_metrics.idle_echo_batches,
           (unsigned)s_lcd_metrics.command_echo_batches,
           (unsigned)s_lcd_metrics.max_echo_batch);
}


static void scroll_metrics_report(const char *stage)
{
    Hw4ScrollMetrics *m=&s_scroll_metrics;
    const unsigned seq=++m->report_seq;
    printf("HW4-SCROLL-A0 SAMPLE seq=%u stage=%s text_scrolls=%u "
           "resets=%u pending_up=%u pending_down=%u cpu_mhz=%u "
           "bytes_per_band=%u classes=cumulative schema=1\n",
           seq,stage,(unsigned)s_text.scrolls,(unsigned)m->resets,
           (unsigned)m->pending_up,(unsigned)m->pending_down,
           (unsigned)CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ,
           (unsigned)CYD_LCD_DMA_BYTES);
    for(unsigned type=0U;type<2U;++type) {
        const Hw4ScrollClass *v=&m->cls[type];
        printf("HW4-SCROLL-A0 CLASS seq=%u name=%s flushes=%u "
               "bands=%u spi_bytes=%llu us_total=%llu min_us=%u max_us=%u "
               "p50_upper_us=%u p95_upper_us=%u up=%u down=%u "
               "reset_tagged=%u hist=",
               seq,type ? "scroll_associated" : "ordinary",
               (unsigned)v->flushes,(unsigned)v->bands,
               (unsigned long long)v->spi_bytes,
               (unsigned long long)v->us_total,(unsigned)v->min_us,
               (unsigned)v->max_us,
               (unsigned)hw4_scroll_quantile_upper(v,50U),
               (unsigned)hw4_scroll_quantile_upper(v,95U),
               (unsigned)v->up,(unsigned)v->down,
               (unsigned)v->reset_tagged);
        for(unsigned i=0U;i<HW4_SCROLL_BINS;++i)
            printf("%s%u",i ? "," : "",(unsigned)v->hist[i]);
        printf("\n");
    }
}

/* All ASCII, including the eight legacy console patterns, now uses the
 * original HW3 shared font; no local glyph copies or visual fallbacks. */

static void memory_report(const char *stage)
{
    CydLcdDiagnostics d;
    if (!cyd_lcd_diagnostics(&d)) {
        printf("HW4-C2 MEMORY_FAIL stage=%s\n",stage);
        return;
    }
    printf("HW4-C2 DEVICE_MEMORY stage=%s heap8_free=%u "
           "heap8_largest=%u heap8_min=%u stack_margin_bytes=%u "
           "dma_transfers=%u dma_timeouts=%u dma_fault=%u lcd_error=%s\n",
           stage,d.heap8_free,d.heap8_largest,d.heap8_min,
           d.stack_margin_bytes,d.transfer_count,d.timeout_count,
           (unsigned)d.dma_fault,esp_err_to_name(d.last_error));
}
static bool fail(const char *phase,int code)
{
    printf("HW4-C2 FAIL phase=%s code=%d\n",phase,code);
    memory_report(phase);
    return false;
}
static bool render_band(unsigned top)
{
    uint8_t *const band=cyd_lcd_band(); /* unique driver-owned 5120 B */
    uint16_t scan[LCD_WIDTH];           /* 640 B transient stack row */
    if(band==NULL || top+LCD_ROWS_PER_BAND>LCD_HEIGHT)
        return fail("LCD_BAND_ACCESS",-1);
    for(unsigned dy=0;dy<LCD_ROWS_PER_BAND;++dy) {
        if(!cpc_video_render_row(&s_video,top+dy,scan,LCD_WIDTH))
            return fail("VIDEO_RENDER",(int)(top+dy));
        for(unsigned x=0;x<LCD_WIDTH;++x) {
            size_t n=((size_t)dy*LCD_WIDTH+x)*2U;
            band[n]=(uint8_t)(scan[x]>>8U);
            band[n+1U]=(uint8_t)scan[x];
        }
    }
    /* DMA sender blocks for completion; a single app_main owns the band. */
    esp_err_t e=cyd_lcd_send(0,(int)top,LCD_WIDTH,LCD_ROWS_PER_BAND);
    if(e!=ESP_OK) return fail("LCD_DMA",(int)e);
    return true;
}
static bool repaint_full(void)
{
    for(unsigned top=0;top<LCD_HEIGHT;top+=LCD_ROWS_PER_BAND)
        if(!render_band(top)) return false;
    (void)cpc_video_take_dirty(&s_video);
    return true;
}
/* /PENIRQ on classic CYD is GPIO36, active low; input-only, no
 * internal pull-up. Do not configure SPI, I2C or touch coordinates here.
 * BOOT is deliberately disarmed until 50 ms of stable released level. */
static uint64_t touch_now_ms(void)
{
    return (uint64_t)esp_timer_get_time()/UINT64_C(1000);
}
static bool touch_init(void)
{
    gpio_config_t pin={
        .pin_bit_mask=UINT64_C(1)<<GPIO_NUM_36,
        .mode=GPIO_MODE_INPUT,
        .pull_up_en=GPIO_PULLUP_DISABLE,
        .pull_down_en=GPIO_PULLDOWN_DISABLE,
        .intr_type=GPIO_INTR_DISABLE
    };
    esp_err_t e=gpio_config(&pin);
    if(e!=ESP_OK) return fail("TOUCH_GPIO36",(int)e);
    hw4_touch_t1_init(&s_touch,gpio_get_level(GPIO_NUM_36)==0,
                      touch_now_ms());
    printf("HW4-TOUCH-T1 BOOT_READY orientation=%u penirq_gpio=36 "
           "active_low=1 debounce_ms=50 long_ms=3000 armed=0\n",
           cyd_lcd_current_orientation());
    return true;
}
static bool touch_poll(void)
{
    uint64_t elapsed=0U;
    const uint64_t now=touch_now_ms();
    const Hw4TouchEvent event=hw4_touch_t1_step(
        &s_touch,gpio_get_level(GPIO_NUM_36)==0,now,&elapsed);
    if(event==HW4_TOUCH_PRESS) {
        printf("HW4-TOUCH-T1 PRESS at_ms=%llu\n",
               (unsigned long long)now);
    } else if(event==HW4_TOUCH_SHORT_ROTATE) {
        const unsigned old=cyd_lcd_current_orientation();
        if(old!=9U && old!=10U) return fail("TOUCH_ORIENTATION_STATE",(int)old);
        const unsigned target=old==9U ? 10U : 9U;
        /* Shared driver clears GRAM, applies both mirror bits, then the
         * unchanged CPC VRAM receives one COMPLETE repaint. No framebuffer
         * allocation and no mutation of BASIC, editor or dirty state. */
        esp_err_t e=cyd_lcd_orientation(target,
                                          cpc_video_palette_rgb565(1U));
        if(e!=ESP_OK) return fail("TOUCH_ORIENTATION",(int)e);
        if(!repaint_full()) return false; /* single DMA attempt per band */
        printf("HW4-TOUCH-T1 SHORT_ROTATE orientation=%u elapsed_ms=%llu "
               "program_preserved=1 repaint=full\n",
               target,(unsigned long long)elapsed);
    } else if(event==HW4_TOUCH_LONG_RESET) {
        /* A full firmware restart, NOT NEW, NVS erase or hardware EN reset.
         * The state machine emits LONG once; boot rearming needs release. */
        printf("HW4-TOUCH-T1 LONG_RESET elapsed_ms=%llu "
               "action=esp_restart orientation_before=%u\n",
               (unsigned long long)elapsed,cyd_lcd_current_orientation());
        fflush(stdout);
        esp_restart();
        return false; /* defensive: no second restart if platform returns */
    }
    return true;
}

static bool send_dirty_band(void *context, unsigned row)
{
    unsigned *sent=(unsigned *)context;
    if(row>=CPC_ROWS ||
       !render_band(CPC_VIDEO_VIEW_TOP+row*LCD_ROWS_PER_BAND))
        return false;
    ++(*sent);
    return true;
}
static bool repaint_dirty(void)
{
    hw4_scroll_observe_text(&s_scroll_metrics,(uint32_t)s_text.scrolls);
    if(s_video.dirty_bands!=0U) {
        unsigned sent=0U;
        uint32_t start=esp_cpu_get_cycle_count();
        /* Exactly ONE attempt. Real LCD errors latch s_fault, so preserve
         * remaining dirty bands and fail-stop. Never retry the driver. */
        bool ok=cpc_video_flush_dirty(&s_video,send_dirty_band,&sent);
        /* CPU cycles modulo UINT32 wrap; CYD uses a fixed CPU clock.
         * Avoid extra timer component and preserve HW3 OFF dependencies. */
        uint32_t elapsed=esp_cpu_get_cycle_count()-start;
        uint32_t us=elapsed/CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ;
        ++s_lcd_metrics.flushes;
        s_lcd_metrics.bands+=sent;
        s_lcd_metrics.spi_bytes+=(uint64_t)sent*CYD_LCD_DMA_BYTES;
        s_lcd_metrics.repaint_us+=(uint64_t)us;
        if(us>s_lcd_metrics.max_us) s_lcd_metrics.max_us=us;
        unsigned bin=0U;
        while(bin<11U && us>s_latency_bounds_us[bin]) ++bin;
        ++s_lcd_metrics.histogram[bin];
        if(ok) hw4_scroll_flush(&s_scroll_metrics,sent,us,
                                (uint64_t)sent*CYD_LCD_DMA_BYTES);
        if(!ok) {
            CydLcdDiagnostics d;
            bool got=cyd_lcd_diagnostics(&d);
            printf("HW4-C3-B2-C1 LCD_FAIL_STOP pending=0x%08x "
                   "sent=%u dma_fault=%u lcd_error=%s retry=0\n",
                   (unsigned)s_video.dirty_bands,sent,
                   got ? (unsigned)d.dma_fault : 1U,
                   got ? esp_err_to_name(d.last_error) : "UNKNOWN");
            return false;
        }
    }
    if(s_text.scrolls<s_scroll_reported) s_scroll_reported=0U; /* !CLS */
    if(s_text.scrolls>s_scroll_reported) {
        printf("HW4-C3-B2 SCREEN_SCROLL rows=%u total=%u "
               "policy=mode1_vram program_preserved=1\n",
               (unsigned)(s_text.scrolls-s_scroll_reported),
               (unsigned)s_text.scrolls);
        s_scroll_reported=s_text.scrolls;
    }
    return true;
}
static bool display_error(void); /* host-only diagnostics, below */
static void log_bytes(const char *kind,const uint8_t *data,size_t size)
{
    printf("HW4-C2 %s length=%u hex=",kind,(unsigned)size);
    for(size_t i=0U;i<size && i<32U;++i) printf("%02x",(unsigned)data[i]);
    if(size>32U) printf("...");
    printf("\n");
}
static bool display_bytes(const char *kind,const uint8_t *data,size_t size)
{
    size_t clipped_before=s_text.bytes_clipped;
    log_bytes(kind,data,size);
    if(!cpc_text_write(&s_text,data,size))
        return fail("TEXT_ADAPTER",-1);
    if(s_text.bytes_clipped>clipped_before)
        printf("HW4-C3-B2 SCREEN_OUTPUT_CLIPPED bytes=%u "
               "policy=unexpected_clip\n",
               (unsigned)(s_text.bytes_clipped-clipped_before));
    return true; /* final frame is flushed by prompt */
}
/* Preflight ALL typed events before changing ANY pixel or sink counter.
 * One original PRINT_BYTES log is retained, not fragments/escape codes. */
static bool display_print_events(size_t event_count)
{
    Hw4PenStatus validation=hw4_pen_preflight(&s_text,s_basic.output,
                            s_basic.written,s_basic.scratch.events,event_count);
    if(validation!=HW4_PEN_OK) {
        printf("HW4-PEN-A VIDEO_REJECT category=%s status=%d printed=0 event_applied=0 print_applied=0\n",
               validation==HW4_PEN_SET_INK_UNSUPPORTED ?
               "SET_INK_UNSUPPORTED" : "PEN_PREFLIGHT", (int)validation);
        (void)bsr_stop(&s_basic.runtime);
        return display_error();
    }
    if(s_basic.written>0U)
        log_bytes("PRINT_BYTES",s_basic.output,s_basic.written);
    const size_t clipped_before=s_text.bytes_clipped;
    Hw4PenStatus replay=hw4_pen_replay(&s_text,s_basic.output,
                             s_basic.written,s_basic.scratch.events,event_count);
    if(replay!=HW4_PEN_OK) {
        printf("HW4-PEN-A VIDEO_REPLAY_FAILURE status=%d\n",(int)replay);
        return fail("PEN_REPLAY",(int)replay);
    }
    for(size_t i=0U;i<event_count;++i) {
        uint8_t mapped=0U;
        if(hw4_pen_pixel_index(&s_video,s_basic.scratch.events[i].pen,&mapped)
           !=HW4_PEN_OK) return fail("PEN_CONTEXT_CHANGED",-1);
        printf("HW4-PEN-A VIDEO_EVENT type=SET_TEXT_PEN logical=%u "
               "pixel=%u print_offset=%u order=%u/%u "
               "renderer=MODE1\n",
               (unsigned)s_basic.scratch.events[i].pen,(unsigned)mapped,
               (unsigned)s_basic.scratch.events[i].print_offset,
               (unsigned)(i+1U),(unsigned)event_count);
    }
    if(s_text.bytes_clipped>clipped_before)
        printf("HW4-C3-B2 SCREEN_OUTPUT_CLIPPED bytes=%u "
               "policy=unexpected_clip\n",
               (unsigned)(s_text.bytes_clipped-clipped_before));
    return true;
}
static bool display_error(void)
{
    /* The UART reject, RUN step and budget errors are host-only; no ROM
     * diagnosis can be inferred from their internal numeric statuses. */
    printf("HW4-DIAG-A DIAG_POLICY origin=runtime_or_uart "
           "category=HOST_GENERIC message=ERROR\n");
    if(!cpc_diag_policy_write(&s_text,CPC_DIAG_HOST_GENERIC))
        return fail("ERROR_TEXT",-1);
    return true;
}
static bool apply_ready_policy(CpcReadyTransition transition)
{
    bool emitted=false;
    if(!cpc_ready_policy_apply(&s_text,transition,&emitted))
        return fail("READY_TEXT",-1);
    printf("HW4-READY-A READY_POLICY transition=%s emitted=%u "
           "row=%u col=%u source=CONSOLE\n",
           cpc_ready_transition_name(transition),(unsigned)emitted,
           (unsigned)s_text.row,(unsigned)s_text.column);
    return true;
}
static bool prompt(void)
{
    bool cleared=false;
    if(!cpc_uart_console_prompt(&s_text,&cleared))
        return fail("CONSOLE_PROMPT",-1);
    if(cleared) return fail("UNEXPECTED_AUTO_CLEAR",-1);
    if(!cpc_uart_console_edit_begin(&s_text,&s_edit))
        return fail("EDIT_BEGIN",-1);
    cpc_screen_nav_init(&s_nav);
    if(!repaint_dirty()) return false;
    printf("HW4-C3-B2 INPUT_READY capacity=%u screen_row=%u "
           "policy=mode1_scroll\n",UART_LINE_CAPACITY,s_text.row);
    return true;
}
static bool basic_submit(const uint8_t *source,size_t length,
                         bool *had_diagnostic)
{
    s_basic.written=0U;
    BSRResult r=bsr_submit(&s_basic.runtime,source,length,
                          s_basic.scratch.temporary,sizeof(s_basic.scratch.temporary),
                          s_basic.output,sizeof(s_basic.output),
                          &s_basic.written);
    printf("HW4-C2 BASIC_SUBMIT status=%d bs=%d bt=%d bp=%d bl=%d "
           "source_bytes=%u output_bytes=%u state=%u\n",
           (int)r.status,(int)r.session.status,(int)r.session.tokenizer_status,
           (int)r.session.program_status,(int)r.session.listing_status,
           (unsigned)length,(unsigned)s_basic.written,
           (unsigned)s_basic.runtime.state);
    if(had_diagnostic!=NULL) *had_diagnostic=(r.status!=BSR_OK);
    if(r.status!=BSR_OK) {
        printf("HW4-C2 BASIC_SUBMIT_FAIL status=%d (no program mutation)\n",
               (int)r.status);
        /* Text is a CPC presentation mapping; Ready stays the independent
         * HW4-READY-A BASIC_DIAGNOSTIC transition in execute_line(). */
        CpcDiagCategory category=cpc_diag_policy_select(source,length,r);
        printf("HW4-DIAG-A DIAG_POLICY origin=submit category=%s "
               "status=%d session=%d message=%s source_bytes=%u\n",
               cpc_diag_policy_category(category),(int)r.status,
               (int)r.session.status,cpc_diag_policy_message(category),
               (unsigned)length);
        if(!cpc_diag_policy_write(&s_text,category))
            return fail("DIAG_TEXT",-1);
        return true;
    }
    if(s_basic.written>0U && !display_bytes("LIST_BYTES",s_basic.output,
                                          s_basic.written)) return false;
    return true;
}
static bool basic_run(void)
{
    unsigned steps=0U;
    printf("HW4-C2 BSR_RUN state=%u budget=%u\n",
           (unsigned)s_basic.runtime.state,RUN_STEP_BUDGET);
    for(steps=0U;steps<RUN_STEP_BUDGET;++steps) {
        size_t event_count=0U;
        s_basic.written=0U;
        BSRResult r=bsr_step_events(&s_basic.runtime,s_basic.output,
                             sizeof(s_basic.output),&s_basic.written,
                             s_basic.scratch.events,PEN_EVENT_CAPACITY,&event_count);
        if(r.status==BSR_END) {
            printf("HW4-C2 BSR_END status=BE_END steps=%u\n",steps);
            return true;
        }
        if(r.status!=BSR_OK || r.executor_status!=BE_OK) {
            const char *pen_diag=r.executor_status==BE_INVALID_PEN ?
                "INVALID_PEN" : r.executor_status==BE_UNSUPPORTED ?
                "UNSUPPORTED_UNVERIFIED" : r.executor_status==BE_NO_EVENT_SPACE ?
                "EVENT_CAPACITY" : "HOST_GENERIC";
            printf("HW4-C2 BSR_STEP_FAIL BSR=%d BE=%d step=%u\n",
                   (int)r.status,(int)r.executor_status,steps);
            printf("HW4-PEN-A STEP_DIAG category=%s events_applied=0 "
                   "print_applied=0 origin=HOST_NOT_CPC_ERR\n",pen_diag);
            (void)bsr_stop(&s_basic.runtime);
            return display_error();
        }
        if(event_count!=0U) {
            if(!display_print_events(event_count)) return false;
        } else if(s_basic.written>0U &&
                  !display_bytes("PRINT_BYTES",s_basic.output,s_basic.written))
            return false;
    }
    (void)bsr_stop(&s_basic.runtime);
    printf("HW4-C2 BSR_STEP_BUDGET_EXCEEDED limit=%u "
           "runtime_stopped=1\n",RUN_STEP_BUDGET);
    return display_error();
}
static bool is_command(const uint8_t *source,size_t n,const char *word)
{
    size_t i;
    for(i=0U;i<n && word[i]!='\0';++i) {
        uint8_t c=source[i];
        if(c>='a' && c<='z') c=(uint8_t)(c-'a'+'A');
        if(c!=(uint8_t)word[i]) return false;
    }
    return i==n && word[i]=='\0';
}
static bool diagnostic_demo(void)
{
    static const char *const source[]={
        "NEW", "10 A%=2", "20 B%=A%+3", "30 PRINT B%", "40 END", "RUN"
    };
    printf("HW4-C2 DEMO_START scenario=HW4-C1 via_actual_bsr\n");
    for(size_t i=0U;i<sizeof(source)/sizeof(source[0]);++i) {
        if(!basic_submit((const uint8_t *)source[i],strlen(source[i]),NULL))
            return false;
    }
    return basic_run();
}
static bool execute_line(void)
{
    const uint8_t *source=s_line.data;
    size_t length=s_line.length;
    printf("HW4-C2 UART_LINE length=%u hex=",(unsigned)length);
    for(size_t i=0U;i<length && i<32U;++i)
        printf("%02x",(unsigned)source[i]);
    if(length>32U) printf("...");
    printf("\n");
    if(!cpc_uart_console_end_line(&s_text))
        return fail("INPUT_EOL",-1);
    CpcReadyTransition transition=CPC_READY_UNCHARACTERIZED_DIRECT;
    if(is_command(source,length,"!CLS")) {
        printf("HW4-C2 DIAGNOSTIC_SCREEN_CLEAR source=!CLS "
               "program_preserved=1\n");
        hw4_scroll_observe_text(&s_scroll_metrics,(uint32_t)s_text.scrolls);
        if(!hw4_pen_console_clear(&s_text)) return false;
        hw4_scroll_clear(&s_scroll_metrics,(uint32_t)s_text.scrolls);
        s_scroll_reported=0U;
        transition=CPC_READY_HOST_CLS; /* screen-only, no CPC equivalent */
    } else if(is_command(source,length,"!DEMO")) {
        if(!diagnostic_demo()) return false;
        transition=CPC_READY_HOST_DEMO; /* retain existing host behavior */
    } else {
        size_t a=0U,b=length;
        while(a<b && source[a]==' ') ++a;
        while(b>a && source[b-1U]==' ') --b;
        const bool run=is_command(source+a,b-a,"RUN");
        const bool list=is_command(source+a,b-a,"LIST");
        const bool new_program=is_command(source+a,b-a,"NEW");
        const bool numbered=(a<b && source[a]>='0' && source[a]<='9');
        bool had_diagnostic=false;
        if(!basic_submit(source,length,&had_diagnostic)) return false;
        if(had_diagnostic) {
            transition=CPC_READY_BASIC_DIAGNOSTIC;
        } else {
            if(run && s_basic.runtime.state==BSR_RUNNING)
                if(!basic_run()) return false;
            transition=run ? CPC_READY_RUN_RETURN :
                       list ? CPC_READY_LIST_RETURN :
                       new_program ? CPC_READY_NEW_RETURN :
                       a==b ? CPC_READY_EMPTY_ENTER :
                       numbered ? CPC_READY_NUMBERED_STORED :
                       CPC_READY_UNCHARACTERIZED_DIRECT;
        }
    }
    /* A prompt is always available, but Ready depends on the transition.
     * Boot Ready remains painted solely by cpc_boot_console(). */
    return apply_ready_policy(transition) && prompt();
}
static bool uart_init(void)
{
    uart_config_t config={
        .baud_rate=115200,
        .data_bits=UART_DATA_8_BITS,
        .parity=UART_PARITY_DISABLE,
        .stop_bits=UART_STOP_BITS_1,
        .flow_ctrl=UART_HW_FLOWCTRL_DISABLE,
        .source_clk=UART_SCLK_DEFAULT
    };
    esp_err_t e=uart_param_config(UART_NUM_0,&config);
    if(e!=ESP_OK) return fail("UART_CONFIG",(int)e);
    e=uart_driver_install(UART_NUM_0,512,0,0,NULL,0);
    if(e==ESP_ERR_INVALID_STATE && uart_is_driver_installed(UART_NUM_0))
        e=ESP_OK;
    if(e!=ESP_OK) return fail("UART_DRIVER",(int)e);
    printf("HW4-C2 UART_READY port=0 baud=115200 input=raw "
           "CR_LF_CRLF=1 BS=08_7f LEFT=1b5b44 RIGHT=1b5b43 DELETE=1b5b337e UP=1b5b41 DOWN=1b5b42 RETURN_EDIT=ENTER_OR_HOME\n");
    return true;
}
void app_main(void)
{
    const esp_app_desc_t *desc=esp_app_get_description();
    printf("HW4-C2 START project=%s version=%s idf=%s "
           "target=esp32 ON_DEVICE_UNVERIFIED\n",
           desc->project_name,desc->version,esp_get_idf_version());
    memory_report("before_lcd");
    esp_err_t e=cyd_lcd_init();
    if(e!=ESP_OK) { (void)fail("LCD_INIT",(int)e); return; }
    printf("HW4-C2 LCD_INIT_PASS dma_bytes=%u\n",CYD_LCD_DMA_BYTES);
    e=cyd_lcd_orientation(10U,cpc_video_palette_rgb565(1U));
    if(e!=ESP_OK) { (void)fail("LCD_ORIENTATION",(int)e); return; }
    printf("HW4-C2 ORIENTATION_PASS case=%u\n",
           cyd_lcd_current_orientation());
    if(!cpc_video_init(&s_video,s_vram,sizeof(s_vram),CPC_MODE_1) ||
       !cpc_video_set_ink(&s_video,0U,1U) ||
       !cpc_video_set_ink(&s_video,1U,24U) ||
       !cpc_video_set_ink(&s_video,2U,6U) ||
       !cpc_video_set_ink(&s_video,3U,18U) ||
       !cpc_video_set_border(&s_video,1U) ||
       !cpc_video_set_text_colors(&s_video,1U,0U) ||
       !cpc_text_init(&s_text,&s_video,hw3_glyph_callback,NULL)) {
        (void)fail("VIDEO_INIT",-1); return;
    }
    printf("HW4-C2 VIDEO_READY mode=1 logical=320x200 "
           "cols=40 rows=25 vram_bytes=%u ink_fg=24 ink_bg=1\n",
           CPC_VIDEO_BYTES);
    printf("HW4-PEN-A INK_CONTEXT mode=1 paper=0 "
           "ink0=1_blue ink1=24_yellow ink2=6_red ink3=18_green "
           "pen4=background_only pen15=green_witness_only "
           "events_capacity=%u\n",PEN_EVENT_CAPACITY);
    /* Startup in existing MODE1 VRAM: no second renderer or splash delay. */
    if(!cpc_boot_console(&s_text,true)) {
        (void)fail("BOOT_LAYOUT",-1); return;
    }
    printf("HW4-C3-A BOOT_READY heading=ESP32_CYD input_col=0 input_row=12\n");
    if(!repaint_full()) return;
    if(bp_init(&s_basic.program,s_basic.bytes,sizeof(s_basic.bytes))!=BP_OK ||
       j115c_init_store(&s_basic.variables,s_basic.entries,
                         VARIABLES_CAPACITY,s_basic.string_arena,
                         sizeof(s_basic.string_arena))!=BVS_OK ||
       bsr_init_with_store(&s_basic.runtime,&s_basic.program,
                            &s_basic.variables).status!=BSR_OK) {
        (void)fail("BASIC_INIT",-1); return;
    }
    printf("J1.15-C BASIC_ARENA_READY entries=%u slot_bytes=%u arena_bytes=%u "
           "allocation=static\n", VARIABLES_CAPACITY,STRING_SLOT_BYTES,
           STRING_ARENA_CAPACITY);
    uart_line_init(&s_line);
    if(!uart_init()) return;
    e=cyd_lcd_backlight(true);
    if(e!=ESP_OK) { (void)fail("BACKLIGHT",(int)e); return; }
    memory_report("interactive_ready");
    printf("HW4-C2 HELP submit_4_numbered_lines_then_RUN "
           "LIST_NEW=real_BSR !DEMO=HW4-C1 !CLS=screen_only\n");
    if(!prompt()) return;
    if(!touch_init()) return;
    unsigned echo_pending=0U;
    printf("HW4-C3-B2-C1 ECHO_POLICY idle_ms=%u batch_max=%u "
           "command_flush=1 dma_fail_stop=1\n",ECHO_IDLE_MS,ECHO_MAX_BYTES);
    for(;;) {
        if(!touch_poll()) return;
        uint8_t ch=0U;
        int got=uart_read_bytes(UART_NUM_0,&ch,1U,
                                pdMS_TO_TICKS(echo_pending ? ECHO_IDLE_MS : TOUCH_POLL_MS));
        if(got<0) { (void)fail("UART_READ",got); return; }
        if(got==0) {
            /* Echo within one idle interval. Fast paste coalesces into
             * one repaint at CR or at the bounded 120-event limit. */
            if(echo_pending) {
                if(!repaint_dirty()) return;
                echo_batch_record(echo_pending,false);
                echo_pending=0U;
            }
            continue;
        }
        UartLineEvent event=uart_line_feed_screen(&s_line,ch);
        if(event==UART_LINE_E1_START_EDIT) {
            /* The router already inserted ch into empty E3. Rebase to the
             * physical E1 cursor BEFORE rendering; never feed ch again. */
            const unsigned row=s_video.cursor_row, col=s_video.cursor_column;
            if(!cpc_screen_nav_start_edit(&s_nav,&s_text,&s_edit,&s_line)) {
                (void)fail("SCREEN_NAV_START_EDIT",-1); return;
            }
            printf("HW4-EDIT-B1-B-C1 E1_START_EDIT row=%u col=%u "
                   "source_bytes=%u first_hex=%02x source=NEW_E3 "
                   "e2_copied=0\n",
                   row,col,(unsigned)s_line.length,(unsigned)ch);
            ++echo_pending;
        } else if(event==UART_LINE_APPEND || event==UART_LINE_DELETE ||
           event==UART_LINE_DELETE_FORWARD ||
           event==UART_LINE_LEFT || event==UART_LINE_RIGHT) {
            const bool inserted=event==UART_LINE_APPEND;
            const bool erased=event==UART_LINE_DELETE ||
                              event==UART_LINE_DELETE_FORWARD;
            const size_t changed=inserted ? s_line.cursor_pos-1U :
                                 erased ? s_line.cursor_pos : s_line.length;
            if(event==UART_LINE_DELETE_FORWARD)
                printf("HW4-EDIT-A UART_EDIT sequence_hex=1b5b337e action=delete_under "
                       "cursor=%u length=%u\n",
                       (unsigned)s_line.cursor_pos,(unsigned)s_line.length);
            else if(event==UART_LINE_DELETE)
                printf("HW4-EDIT-A UART_EDIT key_hex=%02x action=backspace "
                       "cursor=%u length=%u\n",
                       (unsigned)ch,(unsigned)s_line.cursor_pos,
                       (unsigned)s_line.length);
            else if(event==UART_LINE_LEFT || event==UART_LINE_RIGHT)
                printf("HW4-EDIT-A UART_EDIT sequence_hex=%s action=%s "
                       "cursor=%u length=%u\n",
                       event==UART_LINE_LEFT ? "1b5b44" : "1b5b43",
                       event==UART_LINE_LEFT ? "left" : "right",
                       (unsigned)s_line.cursor_pos,(unsigned)s_line.length);
            if(!cpc_uart_console_edit(&s_text,&s_edit,&s_line,changed)) {
                (void)fail("EDIT_SYNC",-1); return;
            }
            ++echo_pending;
        } else if(event==UART_LINE_NAV_BLOCKED) {
            /* The consumed final CSI byte identifies the direction. No E1
             * movement, screen write, E3 edit, BASIC submit or repaint. */
            printf("HW4-EDIT-B1-B NAV_BLOCKED direction=%s "
                   "reason=E3_NONEMPTY source_bytes=%u\n",
                   ch==(uint8_t)'A' ? "UP" : "DOWN",
                   (unsigned)s_line.length);
            /* Optional terminal bell only: one UART0 BEL per refusal, not
             * a claim that this CYD has a working physical sound device. */
            const char bell='\a';
            if(uart_write_bytes(UART_NUM_0,&bell,1U)!=1)
                printf("HW4-EDIT-B1-B BEL_UNAVAILABLE transport=UART0\n");
        } else if(event==UART_LINE_NAV_LEFT || event==UART_LINE_NAV_RIGHT ||
                  event==UART_LINE_NAV_UP || event==UART_LINE_NAV_DOWN) {
            const char *direction=event==UART_LINE_NAV_LEFT ? "LEFT" :
                                  event==UART_LINE_NAV_RIGHT ? "RIGHT" :
                                  event==UART_LINE_NAV_UP ? "UP" : "DOWN";
            const unsigned edge_row=s_video.cursor_row;
            if(!cpc_screen_nav_move(&s_nav,&s_text,&s_edit,&s_line,event)) {
                (void)fail("SCREEN_NAV",-1); return;
            }
            if(event==UART_LINE_NAV_UP && edge_row==0U)
                hw4_scroll_nav(&s_scroll_metrics,-1);
            if(event==UART_LINE_NAV_DOWN && edge_row==24U)
                hw4_scroll_nav(&s_scroll_metrics,1);
            printf("HW4-EDIT-B1-A NAV direction=%s row=%u col=%u "
                   "focus=SCREEN anchor_valid=%u step_policy=ONE_ROW\n",
                   direction,(unsigned)s_video.cursor_row,
                   (unsigned)s_video.cursor_column,
                   (unsigned)s_nav.anchor_valid);
            ++echo_pending;
        } else if(event==UART_LINE_RETURN_EDIT) {
            if(!cpc_screen_nav_resume(&s_nav,&s_text,&s_edit,&s_line)) {
                (void)fail("SCREEN_NAV_RESUME",-1); return;
            }
            printf("HW4-EDIT-B1-A RETURN_EDIT row=%u col=%u "
                   "source_bytes=%u source_preserved=1 policy=E1_NEXT_ROW_CR\n",
                   (unsigned)s_video.cursor_row,
                   (unsigned)s_video.cursor_column,
                   (unsigned)s_line.length);
            ++echo_pending;
        } else if(event==UART_LINE_RETURN_HOME) {
            if(!cpc_screen_nav_home(&s_nav,&s_text,&s_edit,&s_line)) {
                (void)fail("SCREEN_NAV_HOME",-1); return;
            }
            printf("HW4-EDIT-B1-A RETURN_HOME row=%u col=%u "
                   "source_bytes=%u source_preserved=1\n",
                   (unsigned)s_video.cursor_row,
                   (unsigned)s_video.cursor_column,
                   (unsigned)s_line.length);
            ++echo_pending;
        } else if(event==UART_LINE_OVERFLOW) {
            printf("HW4-C2 INPUT_OVERFLOW max_bytes=%u "
                   "policy=reject_entire_line\n",UART_LINE_CAPACITY);
        } else if(event==UART_LINE_READY) {
            /* Input LF + program output + optional Ready + prompt are fully
             * composed BEFORE exactly one repaint_dirty(). */
            echo_batch_record(echo_pending,true);
            echo_pending=0U;
            if(!execute_line()) return;
            uart_line_ack(&s_line);
            memory_report("after_line");
            lcd_metrics_report("after_line");
            scroll_metrics_report("after_line");
        } else if(event==UART_LINE_REJECTED) {
            echo_batch_record(echo_pending,true);
            echo_pending=0U;
            printf("HW4-C2 UART_LINE_REJECTED reason=%s "
                   "program_preserved=1\n",
                   s_line.rejected_ansi_incomplete ?
                       "incomplete_ansi" : "overflow");
            if(!cpc_uart_console_end_line(&s_text) ||
               !display_error() || !apply_ready_policy(CPC_READY_HOST_REJECTED) ||
               !prompt()) return;
            uart_line_ack(&s_line);
            lcd_metrics_report("after_rejected");
            scroll_metrics_report("after_rejected");
        }
        if(echo_pending>=ECHO_MAX_BYTES) {
            if(!repaint_dirty()) return;
            echo_batch_record(echo_pending,false);
            echo_pending=0U;
        }
        /* NONE/IGNORED: CRLF pair, empty erase, non-ASCII or controls. */
    }
}
