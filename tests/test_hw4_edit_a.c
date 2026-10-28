/* HW4-EDIT-A: real UART -> movable editor -> MODE1 -> BASIC session.
 * C99 host, no LCD driver, ROM glyphs, allocations or ESP-IDF. */
#include "uart_line.h"
#include "cpc_uart_console.h"
#include "cpc_font.h"
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct { uint8_t pre[16],pixels[CPC_VIDEO_BYTES],post[16]; } Guard;
static Guard guard;
static CpcVideo video;
static CpcText text;
static CpcUartEditor edit;
static UartLine line;
static struct {
    BasicProgram program;
    BasicVariableStore variables;
    BasicSessionRuntime runtime;
    uint8_t bytes[8192],temp[2048],output[4096];
    BasicVariableEntry entries[64];
    size_t written;
} basic;
static void canaries(void)
{
    for (size_t i=0U;i<16U;++i) {
        assert(guard.pre[i]==0xa5U && guard.post[i]==0x5aU);
    }
    assert(line.length<=120U && line.cursor_pos<=line.length);
    assert(line.data[line.length]==0U);
}
static void new_screen(void)
{
    memset(&guard,0,sizeof guard);
    memset(guard.pre,0xa5,sizeof guard.pre);
    memset(guard.post,0x5a,sizeof guard.post);
    assert(cpc_video_init(&video,guard.pixels,CPC_VIDEO_BYTES,CPC_MODE_1));
    assert(cpc_video_set_ink(&video,0U,1U));
    assert(cpc_video_set_ink(&video,1U,24U));
    assert(cpc_video_set_text_colors(&video,1U,0U));
    assert(cpc_text_init(&text,&video,hw3_glyph_callback,NULL));
    uart_line_init(&line);
    assert(cpc_uart_console_edit_begin(&text,&edit));
    canaries();
}
static UartLineEvent key(uint8_t ch)
{
    UartLineEvent e=uart_line_feed(&line,ch);
    if(e==UART_LINE_APPEND || e==UART_LINE_DELETE ||
       e==UART_LINE_DELETE_FORWARD || e==UART_LINE_LEFT ||
       e==UART_LINE_RIGHT) {
        const size_t first=e==UART_LINE_APPEND ? line.cursor_pos-1U :
                           (e==UART_LINE_DELETE ||
                            e==UART_LINE_DELETE_FORWARD) ?
                            line.cursor_pos : line.length;
        assert(cpc_uart_console_edit(&text,&edit,&line,first));
    }
    canaries();
    return e;
}
static UartLineEvent seq(const char *s)
{
    UartLineEvent last=UART_LINE_NONE;
    for (size_t i=0U;s[i]!='\0';++i) last=key((uint8_t)s[i]);
    return last;
}
static void visible(const char *want)
{
    const size_t n=strlen(want);
    assert(line.length==n && memcmp(line.data,want,n+1U)==0);
    for(size_t i=0U;i<n;++i) {
        const unsigned abs=edit.column+(unsigned)i;
        const unsigned row=edit.row+abs/40U, col=abs%40U;
        for(unsigned dy=0U;dy<8U;++dy) {
            const uint8_t mask=hw3_glyph_row((uint8_t)want[i],dy);
            for(unsigned dx=0U;dx<8U;++dx) {
                uint8_t pen=3U;
                assert(cpc_video_get(&video,8U*col+dx,8U*row+dy,&pen));
                assert(pen==((mask & (0x80U>>dx))!=0U ? 1U : 0U));
            }
        }
    }
    canaries();
}
static void empty_cell(unsigned pos)
{
    const unsigned abs=edit.column+pos;
    const unsigned row=edit.row+abs/40U,col=abs%40U;
    assert(row<25U);
    for(unsigned dy=0U;dy<8U;++dy)
        for(unsigned dx=0U;dx<8U;++dx) {
            uint8_t p=3U;
            assert(cpc_video_get(&video,8U*col+dx,8U*row+dy,&p));
            assert(p==0U);
        }
}
static BSRResult submit(const uint8_t *s,size_t n)
{
    return bsr_submit(&basic.runtime,s,n,basic.temp,sizeof basic.temp,
                      basic.output,sizeof basic.output,&basic.written);
}
static void start_basic(void)
{
    assert(bp_init(&basic.program,basic.bytes,sizeof basic.bytes)==BP_OK);
    assert(bvs_init(&basic.variables,basic.entries,64U)==BVS_OK);
    assert(bsr_init_with_store(&basic.runtime,&basic.program,
                               &basic.variables).status==BSR_OK);
}
static void commit_line(void)
{
    assert(key('\r')==UART_LINE_READY);
    assert(cpc_uart_console_end_line(&text));
    assert(submit(line.data,line.length).status==BSR_OK);
    uart_line_ack(&line);
    bool reset=true;
    assert(cpc_uart_console_prompt(&text,&reset) && !reset);
    assert(cpc_uart_console_edit_begin(&text,&edit));
    canaries();
}
static void source_edit_list_run(void)
{
    new_screen();
    start_basic();
    assert(seq("10 PRNT 2")==UART_LINE_APPEND);
    for(unsigned i=0U;i<4U;++i) assert(seq("\x1b[D")==UART_LINE_LEFT);
    assert(line.cursor_pos==5U);
    assert(key('I')==UART_LINE_APPEND);
    visible("10 PRINT 2");
    /* C1: real editor cursor over 'N' in PRINT must preserve readable
     * inverted glyph, then restore its RGB565 pixels when moved off. */
    {
        uint16_t screen[320];
        uint8_t vram_copy[CPC_VIDEO_BYTES];
        const unsigned x = (unsigned)video.cursor_column * 8U;
        const unsigned y = CPC_VIDEO_VIEW_TOP + (unsigned)video.cursor_row * 8U + 2U;
        const uint8_t bits = hw3_glyph_row((uint8_t)'N', 2U);
        assert(video.cursor_column == 6U && video.cursor_row == 0U);
        assert(bits != 0U && bits != 0xffU);
        memcpy(vram_copy, guard.pixels, sizeof vram_copy);
        assert(cpc_video_render_row(&video, y, screen, 320U));
        for (unsigned dx = 0U; dx < 8U; ++dx) {
            const bool ink = (bits & (uint8_t)(0x80U >> dx)) != 0U;
            assert(screen[x + dx] ==
                   cpc_video_palette_rgb565(video.ink[ink ? video.paper : video.pen]));
        }
        assert(seq("\x1b[D") == UART_LINE_LEFT); /* leave 'N' */
        assert(cpc_video_render_row(&video, y, screen, 320U));
        for (unsigned dx = 0U; dx < 8U; ++dx) {
            const bool ink = (bits & (uint8_t)(0x80U >> dx)) != 0U;
            assert(screen[x + dx] ==
                   cpc_video_palette_rgb565(video.ink[ink ? video.pen : video.paper]));
        }
        assert(memcmp(vram_copy, guard.pixels, sizeof vram_copy) == 0);
        assert(seq("\x1b[C") == UART_LINE_RIGHT); /* return to 'N' */
        assert(memcmp(vram_copy, guard.pixels, sizeof vram_copy) == 0);
    }
    assert(video.cursor_column==6U && video.cursor_row==0U);
    commit_line();
    assert(seq("20 PRIXNT 3")==UART_LINE_APPEND);
    for(unsigned i=0U;i<5U;++i) assert(seq("\x1b[D")==UART_LINE_LEFT);
    assert(line.cursor_pos==6U && video.cursor_column==6U);
    assert(seq("\x1b[3~")==UART_LINE_DELETE_FORWARD);
    visible("20 PRINT 3");
    assert(video.cursor_column==6U && video.cursor_row==1U);
    commit_line();
    static const uint8_t list[]="LIST";
    static const uint8_t expected[]="10 PRINT 2\n20 PRINT 3\n";
    assert(submit(list,sizeof list-1U).status==BSR_OK);
    assert(basic.written==sizeof expected-1U);
    assert(memcmp(basic.output,expected,sizeof expected-1U)==0);
    uint8_t program[sizeof basic.bytes];
    memcpy(program,basic.bytes,sizeof program);
    static const uint8_t run[]="RUN";
    assert(submit(run,sizeof run-1U).status==BSR_OK);
    uint8_t printed[64]={0};
    size_t count=0U;
    for(unsigned steps=0U;steps<8U;++steps) {
        BSRResult x=bsr_step(&basic.runtime,basic.output,
                             sizeof basic.output,&basic.written);
        if(x.status==BSR_END) break;
        assert(x.status==BSR_OK && x.executor_status==BE_OK);
        assert(count+basic.written<=sizeof printed);
        memcpy(printed+count,basic.output,basic.written);
        count+=basic.written;
    }
    assert(count==4U);
    assert(memcmp(printed,"2\n3\n",4U)==0);
    assert(memcmp(program,basic.bytes,sizeof program)==0);
    /* Host !CLS clears just the video, not BASIC store. */
    assert(cpc_uart_console_clear(&text));
    assert(memcmp(program,basic.bytes,sizeof program)==0);
    static const uint8_t newcmd[]="NEW";
    assert(submit(newcmd,sizeof newcmd-1U).status==BSR_OK);
    assert(submit(list,sizeof list-1U).status==BSR_OK);
    assert(basic.written==0U);
    canaries();
}
static void wrap_and_overflow(void)
{
    new_screen();
    for(unsigned i=0U;i<120U;++i) assert(key('X')==UART_LINE_APPEND);
    assert(line.length==120U && edit.painted==120U);
    assert(edit.row==0U && text.row==2U && text.column==40U);
    for(unsigned i=0U;i<81U;++i) assert(seq("\x1b[D")==UART_LINE_LEFT);
    assert(line.cursor_pos==39U && video.cursor_column==39U);
    /* At capacity, insertion rejects the whole line, with no VRAM change. */
    uint8_t saved[CPC_VIDEO_BYTES];
    memcpy(saved,guard.pixels,sizeof saved);
    assert(key('Y')==UART_LINE_OVERFLOW && line.poisoned);
    assert(memcmp(saved,guard.pixels,sizeof saved)==0);
    assert(key(0x08U)==UART_LINE_NONE);
    assert(line.length==120U && line.cursor_pos==39U);
    assert(key('\r')==UART_LINE_REJECTED);
    assert(memcmp(saved,guard.pixels,sizeof saved)==0);
    uart_line_ack(&line);
    assert(line.length==0U && line.cursor_pos==0U);
    /* New editing starts on the next line after explicit LF. */
    assert(cpc_uart_console_end_line(&text));
    bool cleared=false;
    assert(cpc_uart_console_prompt(&text,&cleared) && !cleared);
    assert(cpc_uart_console_edit_begin(&text,&edit));
    assert(seq("1234567890")==UART_LINE_APPEND);
    for(unsigned i=0U;i<9U;++i) assert(seq("\x1b[D")==UART_LINE_LEFT);
    assert(key(0x7fU)==UART_LINE_DELETE);
    visible("234567890");
    empty_cell(9U);
    canaries();
}
static void scroll_bottom_and_rejected_ansi(void)
{
    new_screen();
    static const uint8_t lf='\n';
    for(unsigned i=0U;i<24U;++i)
        assert(cpc_text_write(&text,&lf,1U));
    assert(text.row==24U && text.column==0U);
    assert(cpc_uart_console_edit_begin(&text,&edit));
    for(unsigned i=0U;i<81U;++i) assert(key('X')==UART_LINE_APPEND);
    assert(text.row==24U && text.column==1U);
    assert(text.scrolls==2U && edit.row==22U);
    for(unsigned i=0U;i<42U;++i) assert(seq("\x1b[D")==UART_LINE_LEFT);
    assert(line.cursor_pos==39U);
    assert(key(0x08U)==UART_LINE_DELETE);
    assert(line.length==80U && line.cursor_pos==38U);
    assert(seq("\x1b[3~")==UART_LINE_DELETE_FORWARD);
    assert(line.length==79U && line.cursor_pos==38U);
    assert(key('Q')==UART_LINE_APPEND);
    assert(line.length==80U && line.cursor_pos==39U);
    assert(video.cursor_row==22U && video.cursor_column==39U);
    for(unsigned i=0U;i<80U;++i) {
        const unsigned row=edit.row+i/40U,col=i%40U;
        const uint8_t b=line.data[i];
        assert(row<25U);
        for(unsigned y=0U;y<8U;++y) {
            uint8_t pen;
            const uint8_t pattern=hw3_glyph_row(b,y);
            for(unsigned x=0U;x<8U;++x) {
                assert(cpc_video_get(&video,8U*col+x,8U*row+y,&pen));
                assert(pen==((pattern & (0x80U>>x))!=0U ? 1U : 0U));
            }
        }
    }
    empty_cell(80U);
    /* A truncated CSI is rejected without altering pixels or BASIC data. */
    uint8_t snapshot[CPC_VIDEO_BYTES];
    memcpy(snapshot,guard.pixels,sizeof snapshot);
    assert(key(0x1bU)==UART_LINE_IGNORED);
    assert(key('[')==UART_LINE_IGNORED);
    assert(key('3')==UART_LINE_IGNORED);
    assert(key('\r')==UART_LINE_REJECTED);
    assert(memcmp(snapshot,guard.pixels,sizeof snapshot)==0);
    canaries();
}
int main(void)
{
    source_edit_list_run();
    wrap_and_overflow();
    scroll_bottom_and_rejected_ansi();
    puts("HW4-EDIT-A UART source/LIST/RUN, cursor/wrap/scroll/VRAM/canaries PASS");
    return 0;
}
