/* HW4-FONT-A: coverage/parity of the ORIGINAL font through real MODE1 video.
 * No ROM font data, no ESP-IDF dependencies, no replacement pixel renderer.
 */
#include "cpc_font.h"
#include "cpc_uart_console.h"
#include "uart_line.h"
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint8_t before[8];
    uint8_t vram[CPC_VIDEO_BYTES];
    uint8_t after[8];
} GuardedVram;
static GuardedVram guard;
static CpcVideo video;
static CpcText text;
static UartLine uart;
static uint16_t rgb[322];
static struct {
    BasicProgram program;
    BasicVariableStore variables;
    BasicSessionRuntime runtime;
    uint8_t bytes[8192];
    BasicVariableEntry entries[64];
    uint8_t temp[2048];
    uint8_t output[4096];
    size_t written;
} basic;

static uint32_t fnv_byte(uint32_t h, uint8_t value)
{
    return (h ^ value) * UINT32_C(16777619);
}
static void check_canaries(void)
{
    for (size_t i = 0U; i < 8U; ++i) {
        assert(guard.before[i] == 0xa5U);
        assert(guard.after[i] == 0x5aU);
    }
}
static void start_video(void)
{
    memset(&guard, 0, sizeof guard);
    memset(guard.before, 0xa5, sizeof guard.before);
    memset(guard.after, 0x5a, sizeof guard.after);
    assert(cpc_video_init(&video,guard.vram,sizeof guard.vram,CPC_MODE_1));
    assert(cpc_video_set_ink(&video,0U,1U));
    assert(cpc_video_set_ink(&video,1U,24U));
    assert(cpc_video_set_text_colors(&video,1U,0U));
    check_canaries();
}

/* Historical source font: 53 entries including space, plus eight exact
 * patterns formerly owned by the console. FNV-1a fingerprints pin all
 * 61 original definitions, in ascending ASCII order (code followed by
 * eight bytes). This avoids a second copy of the bitmap data.
 */
static void old_glyphs_identical(void)
{
    static const uint8_t original_codes[] = {
        32,34,37,40,41,43,45,46,47,48,49,50,51,52,53,54,55,56,57,
        58,61,62,65,66,67,68,69,70,73,75,76,77,78,79,80,82,83,84,
        85,86,87,88,89,97,99,100,101,102,105,108,109,110,111,112,
        114,115,116,117,118,119,121
    };
    uint32_t hash = UINT32_C(2166136261);
    for (size_t i = 0U; i < sizeof original_codes; ++i) {
        const uint8_t ch = original_codes[i];
        hash = fnv_byte(hash,ch);
        for (unsigned y = 0U; y < 8U; ++y)
            hash = fnv_byte(hash,hw3_glyph_row(ch,y));
    }
    assert(hash == UINT32_C(0xee66f2f1));
    hash = fnv_byte(UINT32_C(2166136261),0x7fU);
    for (unsigned y = 0U; y < 8U; ++y)
        hash = fnv_byte(hash,hw3_glyph_row(0x7fU,y));
    assert(hash == UINT32_C(0x5a077bb6)); /* diagnostic copyright */
}
static void check_cell(unsigned column, unsigned row, uint8_t ch)
{
    for (unsigned y = 0U; y < 8U; ++y) {
        const uint8_t mask = hw3_glyph_row(ch,y);
        const unsigned y_screen = CPC_VIDEO_VIEW_TOP + row*8U + y;
        rgb[0] = UINT16_C(0xdead);
        rgb[321] = UINT16_C(0xbeef);
        assert(cpc_video_render_row(&video,y_screen,rgb+1U,320U));
        assert(rgb[0] == UINT16_C(0xdead) &&
               rgb[321] == UINT16_C(0xbeef));
        for (unsigned x = 0U; x < 8U; ++x) {
            const uint8_t expected =
                (mask & (uint8_t)(0x80U >> x)) ? 1U : 0U;
            uint8_t pen = 255U;
            assert(cpc_video_get(&video,column*8U+x,row*8U+y,&pen));
            assert(pen == expected);
            assert(rgb[1U+column*8U+x] ==
                   (expected ? UINT16_C(0xffe0) : UINT16_C(0x0010)));
        }
    }
}
static void printable_table_and_actual_video(void)
{
    uint8_t raw[95], frozen[95];
    size_t visible = 0U;
    start_video();
    assert(cpc_video_columns(&video) == 40U);
    assert(cpc_text_init(&text,&video,hw3_glyph_callback,NULL));
    uart_line_init(&uart);
    for (unsigned ch = 0x20U; ch <= 0x7eU; ++ch) {
        uint8_t any = 0U;
        for (unsigned y = 0U; y < 8U; ++y) {
            const uint8_t bits = hw3_glyph_row((uint8_t)ch,y);
            assert(bits == hw3_glyph_callback(NULL,(uint8_t)ch,y));
            any = (uint8_t)(any | bits);
        }
        if (ch == 0x20U) assert(any == 0U);
        else { assert(any != 0U); ++visible; }
        raw[ch-0x20U] = (uint8_t)ch;
    }
    assert(visible == 94U);
    for (unsigned ch = 0U; ch < 0x20U; ++ch)
        for (unsigned y = 0U; y < 8U; ++y)
            assert(hw3_glyph_row((uint8_t)ch,y) == 0U);
    for (unsigned y = 8U; y < 100U; ++y) {
        assert(hw3_glyph_row('!',y) == 0U);
        assert(hw3_glyph_callback(NULL,'G',y) == 0U);
    }
    for (unsigned ch = 0x80U; ch <= 0xffU; ++ch)
        for (unsigned y = 0U; y < 8U; ++y)
            assert(hw3_glyph_row((uint8_t)ch,y) == 0U);
    memcpy(frozen,raw,sizeof raw);

    /* Actual input adapter and actual MODE1 draw, including 40-col wraps.
     * This is an echo-only demonstration, never an invalid BASIC submit. */
    for (size_t i = 0U; i < sizeof raw; ++i) {
        assert(uart_line_feed(&uart,raw[i]) == UART_LINE_APPEND);
        assert(cpc_uart_console_append(&text,raw[i]));
        check_canaries();
    }
    assert(text.glyphs_drawn == 95U && text.scrolls == 0U);
    assert(text.row == 2U && text.column == 15U);
    assert(memcmp(raw,frozen,sizeof raw) == 0);
    assert(uart_line_feed(&uart,'\r') == UART_LINE_READY);
    assert(uart.length == sizeof raw);
    assert(memcmp(uart.data,raw,sizeof raw) == 0);
    for (size_t i = 0U; i < sizeof raw; ++i)
        check_cell((unsigned)(i % 40U),(unsigned)(i / 40U),raw[i]);

    /* Invalid cell requests do not mutate VRAM, nor can glyph row overflow. */
    uint8_t snapshot[CPC_VIDEO_BYTES];
    memcpy(snapshot,guard.vram,sizeof snapshot);
    assert(!cpc_video_put_cell(&video,40U,0U,'!',hw3_glyph_callback,NULL));
    assert(!cpc_video_put_cell(&video,0U,25U,'!',hw3_glyph_callback,NULL));
    assert(memcmp(snapshot,guard.vram,sizeof snapshot) == 0);
    check_canaries();
}
static BSRResult submit(const uint8_t *src, size_t size)
{
    return bsr_submit(&basic.runtime,src,size,basic.temp,sizeof basic.temp,
                      basic.output,sizeof basic.output,&basic.written);
}
static void source_list_pixels_and_clear(void)
{
    static const uint8_t source[] = "10 A%=2";
    static const uint8_t list_cmd[] = "LIST";
    static const uint8_t listing[] = "10 A%=2\n";
    uint8_t snapshot[sizeof basic.bytes];
    start_video();
    assert(cpc_text_init(&text,&video,hw3_glyph_callback,NULL));
    assert(bp_init(&basic.program,basic.bytes,sizeof basic.bytes)==BP_OK);
    assert(bvs_init(&basic.variables,basic.entries,64U)==BVS_OK);
    assert(bsr_init_with_store(&basic.runtime,&basic.program,
                               &basic.variables).status==BSR_OK);
    uart_line_init(&uart);
    for (size_t i=0U; i<sizeof source-1U; ++i) {
        assert(uart_line_feed(&uart,source[i])==UART_LINE_APPEND);
        assert(cpc_uart_console_append(&text,source[i]));
    }
    assert(uart_line_feed(&uart,'\r')==UART_LINE_READY);
    assert(uart.length==sizeof source-1U &&
           memcmp(uart.data,source,sizeof source-1U)==0);
    assert(submit(uart.data,uart.length).status==BSR_OK);
    const size_t program_size=basic.program.size;
    assert(program_size>0U);
    memcpy(snapshot,basic.bytes,sizeof snapshot);
    assert(cpc_uart_console_end_line(&text));
    assert(submit(list_cmd,sizeof list_cmd-1U).status==BSR_OK);
    assert(basic.written==sizeof listing-1U);
    assert(memcmp(basic.output,listing,sizeof listing-1U)==0);
    assert(cpc_text_write(&text,basic.output,basic.written));
    assert(basic.program.size==program_size &&
           memcmp(snapshot,basic.bytes,sizeof snapshot)==0);
    for(size_t i=0U;i<sizeof source-1U;++i) {
        check_cell((unsigned)i,0U,source[i]); /* typed source */
        check_cell((unsigned)i,1U,listing[i]); /* LIST printer */
    }
    check_canaries();

    /* !CLS is a host screen diagnostic. Clearing video never clears BASIC. */
    assert(cpc_uart_console_append(&text,'!'));
    assert(cpc_uart_console_append(&text,'C'));
    assert(cpc_uart_console_append(&text,'L'));
    assert(cpc_uart_console_append(&text,'S'));
    check_cell(0U,2U,'!');
    assert(cpc_uart_console_clear(&text));
    assert(basic.program.size==program_size &&
           memcmp(snapshot,basic.bytes,sizeof snapshot)==0);
    uint8_t zero=255U;
    assert(cpc_video_get(&video,0U,0U,&zero) && zero==0U);
    check_canaries();
}
int main(void)
{
    old_glyphs_identical();
    printable_table_and_actual_video();
    source_list_pixels_and_clear();
    puts("HW4-FONT-A: 95/95 mapped, 94 visible + blank space, 61 baseline glyphs / DEL pinned, actual MODE1 UART echo, source/LIST pixels, VRAM canaries PASS");
    return 0;
}
