/*
 * HW4-C2: real user-submitted native Locomotive BASIC via UART0 -> CPC TFT.
 * One app_main owns UART intake, BASIC session, CpcText, video and LCD DMA.
 * Not a CPC boot, scrolling screen, Z80 interpreter or second SPI driver.
 */
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include "cpc_font.h"
#include "cpc_boot.h"
#include "cpc_text.h"
#include "cpc_uart_console.h"
#include "cpc_video.h"
#include "cyd_ili9341.h"
#include "uart_line.h"
#include "driver/uart.h"
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
    CPC_ROWS = 25,
    RUN_STEP_BUDGET = 256
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
static UartLine s_line;
static uint8_t s_vram[CPC_VIDEO_BYTES];
static unsigned s_screen_pages;

/* Extend the existing ORIGINAL HW3 font for visible serial syntax.
 * Missing glyphs remain an explicitly provisional display limitation. */
static uint8_t glyph(void *context, uint8_t character, unsigned row)
{
    static const uint8_t percent[8]={0x62,0x64,0x08,0x10,0x20,0x4c,0x8c,0};
    static const uint8_t equal[8]={0,0x7e,0,0x7e,0,0,0,0};
    static const uint8_t plus[8]={0,0x10,0x10,0x7c,0x10,0x10,0,0};
    static const uint8_t minus[8]={0,0,0,0x7c,0,0,0,0};
    static const uint8_t prompt[8]={0x40,0x20,0x10,0x08,0x10,0x20,0x40,0};
    static const uint8_t quote[8]={0x48,0x48,0x48,0,0,0,0,0};
    static const uint8_t colon[8]={0,0x30,0x30,0,0x30,0x30,0,0};
    static const uint8_t slash[8]={0x04,0x08,0x08,0x10,0x20,0x20,0x40,0};
    (void)context;
    if (row >= 8U) return 0U;
    switch(character) {
    case '%': return percent[row];
    case '=': return equal[row];
    case '+': return plus[row];
    case '-': return minus[row];
    case '>': return prompt[row];
    case '"': return quote[row];
    case ':': return colon[row];
    case '/': return slash[row];
    default: return hw3_glyph_row(character, row);
    }
}

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
static bool repaint_dirty(void)
{
    uint32_t mask=cpc_video_take_dirty(&s_video);
    for(unsigned i=0;i<CPC_ROWS;++i)
        if((mask & (UINT32_C(1)<<i))!=0U &&
           !render_band(CPC_VIDEO_VIEW_TOP+i*LCD_ROWS_PER_BAND))
            return false;
    return true;
}
static bool display_bytes(const char *kind,const uint8_t *data,size_t size)
{
    size_t clipped_before=s_text.bytes_clipped;
    printf("HW4-C2 %s length=%u hex=",kind,(unsigned)size);
    for(size_t i=0U;i<size && i<32U;++i) printf("%02x",(unsigned)data[i]);
    if(size>32U) printf("..."); /* bounded log, never invented bytes */
    printf("\n");
    if(!cpc_text_write(&s_text,data,size))
        return fail("TEXT_ADAPTER",-1);
    if(s_text.bytes_clipped>clipped_before)
        printf("HW4-C2 SCREEN_FULL_OUTPUT_CLIPPED bytes=%u "
               "policy=next_prompt_paginates\n",
               (unsigned)(s_text.bytes_clipped-clipped_before));
    return repaint_dirty();
}
static bool display_error(void)
{
    static const uint8_t notice[]="ERROR\n"; /* host diagnostic, not CPC ERR */
    if(!cpc_text_write(&s_text,notice,sizeof(notice)-1U))
        return fail("ERROR_TEXT",-1);
    return repaint_dirty();
}
static bool prompt(void)
{
    bool cleared=false;
    if(!cpc_uart_console_prompt(&s_text,&cleared))
        return fail("CONSOLE_PROMPT",-1);
    if(cleared) {
        ++s_screen_pages;
        printf("HW4-C2 SCREEN_PAGE_RESET count=%u "
               "reason=no_room_for_120_byte_input program_preserved=1\n",
               s_screen_pages);
    }
    if(!repaint_dirty()) return false;
    printf("HW4-C2 INPUT_READY capacity=%u screen_row=%u "
           "policy=auto_page_non_cpc\n",UART_LINE_CAPACITY,s_text.row);
    return true;
}
static bool basic_submit(const uint8_t *source,size_t length)
{
    s_basic.written=0U;
    BSRResult r=bsr_submit(&s_basic.runtime,source,length,
                          s_basic.temporary,sizeof(s_basic.temporary),
                          s_basic.output,sizeof(s_basic.output),
                          &s_basic.written);
    printf("HW4-C2 BASIC_SUBMIT status=%d bs=%d bt=%d bp=%d bl=%d "
           "source_bytes=%u output_bytes=%u state=%u\n",
           (int)r.status,(int)r.session.status,(int)r.session.tokenizer_status,
           (int)r.session.program_status,(int)r.session.listing_status,
           (unsigned)length,(unsigned)s_basic.written,
           (unsigned)s_basic.runtime.state);
    if(r.status!=BSR_OK) {
        printf("HW4-C2 BASIC_SUBMIT_FAIL status=%d (no program mutation)\n",
               (int)r.status);
        return display_error(); /* recoverable BASIC diagnostic */
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
        s_basic.written=0U;
        BSRResult r=bsr_step(&s_basic.runtime,s_basic.output,
                             sizeof(s_basic.output),&s_basic.written);
        if(r.status==BSR_END) {
            printf("HW4-C2 BSR_END status=BE_END steps=%u\n",steps);
            return true;
        }
        if(r.status!=BSR_OK || r.executor_status!=BE_OK) {
            printf("HW4-C2 BSR_STEP_FAIL BSR=%d BE=%d step=%u\n",
                   (int)r.status,(int)r.executor_status,steps);
            (void)bsr_stop(&s_basic.runtime);
            return display_error();
        }
        if(s_basic.written>0U &&
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
        if(!basic_submit((const uint8_t *)source[i],strlen(source[i])))
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
    if(!cpc_uart_console_end_line(&s_text) || !repaint_dirty())
        return fail("INPUT_EOL",-1);
    if(is_command(source,length,"!CLS")) {
        printf("HW4-C2 DIAGNOSTIC_SCREEN_CLEAR source=!CLS "
               "program_preserved=1\n");
        if(!cpc_uart_console_clear(&s_text) || !repaint_dirty()) return false;
    } else if(is_command(source,length,"!DEMO")) {
        if(!diagnostic_demo()) return false;
    } else {
        size_t a=0U,b=length;
        while(a<b && source[a]==' ') ++a;
        while(b>a && source[b-1U]==' ') --b;
        const bool run=is_command(source+a,b-a,"RUN");
        if(!basic_submit(source,length)) return false;
        if(run && s_basic.runtime.state==BSR_RUNNING)
            if(!basic_run()) return false;
    }
    return prompt();
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
           "CR_LF_CRLF=1 BS_DEL=1\n");
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
    e=cyd_lcd_orientation(9U,cpc_video_palette_rgb565(1U));
    if(e!=ESP_OK) { (void)fail("LCD_ORIENTATION",(int)e); return; }
    printf("HW4-C2 ORIENTATION_PASS case=%u\n",
           cyd_lcd_current_orientation());
    if(!cpc_video_init(&s_video,s_vram,sizeof(s_vram),CPC_MODE_1) ||
       !cpc_video_set_ink(&s_video,0U,1U) ||
       !cpc_video_set_ink(&s_video,1U,24U) ||
       !cpc_video_set_border(&s_video,1U) ||
       !cpc_video_set_text_colors(&s_video,1U,0U) ||
       !cpc_text_init(&s_text,&s_video,glyph,NULL)) {
        (void)fail("VIDEO_INIT",-1); return;
    }
    printf("HW4-C2 VIDEO_READY mode=1 logical=320x200 "
           "cols=40 rows=25 vram_bytes=%u ink_fg=24 ink_bg=1\n",
           CPC_VIDEO_BYTES);
    /* Startup in existing MODE1 VRAM: no second renderer or splash delay. */
    if(!cpc_boot_console(&s_text,true)) {
        (void)fail("BOOT_LAYOUT",-1); return;
    }
    printf("HW4-C3-A BOOT_READY heading=ESP32_CYD input_col=0 input_row=12\n");
    if(!repaint_full()) return;
    if(bp_init(&s_basic.program,s_basic.bytes,sizeof(s_basic.bytes))!=BP_OK ||
       bvs_init(&s_basic.variables,s_basic.entries,VARIABLES_CAPACITY)!=BVS_OK ||
       bsr_init_with_store(&s_basic.runtime,&s_basic.program,
                            &s_basic.variables).status!=BSR_OK) {
        (void)fail("BASIC_INIT",-1); return;
    }
    uart_line_init(&s_line);
    if(!uart_init()) return;
    e=cyd_lcd_backlight(true);
    if(e!=ESP_OK) { (void)fail("BACKLIGHT",(int)e); return; }
    memory_report("interactive_ready");
    printf("HW4-C2 HELP submit_4_numbered_lines_then_RUN "
           "LIST_NEW=real_BSR !DEMO=HW4-C1 !CLS=screen_only\n");
    if(!prompt()) return;
    for(;;) {
        uint8_t ch=0U;
        int got=uart_read_bytes(UART_NUM_0,&ch,1U,pdMS_TO_TICKS(100));
        if(got<0) { (void)fail("UART_READ",got); return; }
        if(got==0) continue;
        UartLineEvent event=uart_line_feed(&s_line,ch);
        if(event==UART_LINE_APPEND) {
            if(!cpc_uart_console_append(&s_text,ch) || !repaint_dirty()) {
                (void)fail("ECHO",-1); return;
            }
        } else if(event==UART_LINE_DELETE) {
            /* Raw-byte provenance for the PO's keyboard investigation.
             * A lone '~' never triggers DELETE; only decoded ESC[3~ does. */
            if(ch==(uint8_t)'~')
                printf("HW4-C2 UART_EDIT sequence_hex=1b5b337e "
                       "key=ANSI_DELETE action=backspace\n");
            else
                printf("HW4-C2 UART_EDIT key_hex=%02x "
                       "action=backspace\n",(unsigned)ch);
            if(!cpc_uart_console_backspace(&s_text) || !repaint_dirty()) {
                (void)fail("DELETE",-1); return;
            }
        } else if(event==UART_LINE_OVERFLOW) {
            printf("HW4-C2 INPUT_OVERFLOW max_bytes=%u "
                   "policy=reject_entire_line\n",UART_LINE_CAPACITY);
        } else if(event==UART_LINE_READY) {
            if(!execute_line()) return;
            uart_line_ack(&s_line);
            memory_report("after_line");
        } else if(event==UART_LINE_REJECTED) {
            printf("HW4-C2 UART_LINE_REJECTED reason=%s "
                   "program_preserved=1\n",
                   s_line.rejected_ansi_incomplete ?
                       "incomplete_ansi" : "overflow");
            if(!cpc_uart_console_end_line(&s_text) ||
               !display_error() || !prompt()) return;
            uart_line_ack(&s_line);
        }
        /* NONE/IGNORED: CRLF pair, empty erase, non-ASCII or controls. */
    }
}
