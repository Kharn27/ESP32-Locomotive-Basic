/* HW4-C3-B2 40x25 scrolling, prompt, echo and bounded erase with canaries. */
#include "cpc_uart_console.h"
#include "uart_line.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct { uint8_t pre[8], data[CPC_VIDEO_BYTES], post[8]; } Guard;
static Guard g;
static CpcVideo v;
static CpcText t;
static uint8_t glyph(void *ctx, uint8_t ch, unsigned row) {
    (void)ctx;
    return (row==0U && ch!=' ') ? 0x80U : 0U;
}
static void init(void) {
    memset(&g, 0, sizeof(g));
    memset(g.pre,0xa5U,8U);
    memset(g.post,0x5aU,8U);
    assert(cpc_video_init(&v,g.data,sizeof(g.data),CPC_MODE_1));
    assert(cpc_video_set_ink(&v,0U,1U));
    assert(cpc_video_set_ink(&v,1U,24U));
    assert(cpc_video_set_text_colors(&v,1U,0U));
    assert(cpc_text_init(&t,&v,glyph,NULL));
}
static void guarded(void) {
    for(size_t i=0U;i<8U;++i) {
        assert(g.pre[i]==0xa5U);
        assert(g.post[i]==0x5aU);
    }
}
static void edits(void) {
    bool page = false;
    uint8_t p = 0;
    init();
    assert(cpc_uart_console_prompt(&t,&page) && !page);
    assert(t.column==0U && t.row==0U);
    assert(v.cursor_visible && v.cursor_column==0U && v.cursor_row==0U);
    /* Cursor is an overlay, not a rendered '>' character in CPC VRAM. */
    assert(cpc_video_get(&v,0U,0U,&p) && p==0U);
    assert(cpc_uart_console_append(&t,'X'));
    assert(cpc_video_get(&v,0U,0U,&p) && p==1U);
    assert(cpc_uart_console_backspace(&t));
    assert(t.column==0U && t.row==0U);
    assert(cpc_video_get(&v,0U,0U,&p) && p==0U);
    assert(cpc_uart_console_append(&t,'5'));
    assert(cpc_uart_console_end_line(&t) && t.row==1U);
    assert(cpc_uart_console_prompt(&t,&page) && !page);
    assert(t.row==1U && t.column==0U);
    assert(v.cursor_visible && v.cursor_column==0U && v.cursor_row==1U);
    assert(cpc_video_get(&v,0U,8U,&p) && p==0U);
    guarded();
}
static void wrap_erase(void) {
    bool page = false;
    init();
    assert(cpc_uart_console_prompt(&t,&page));
    for(size_t i=0U; i<45U; ++i)
        assert(cpc_uart_console_append(&t,'X'));
    assert(t.row==1U && t.column==5U);
    for(size_t i=0U;i<7U;++i) assert(cpc_uart_console_backspace(&t));
    assert(t.row==0U && t.column==38U);
    guarded();
}

/* A single UART parser event drives exactly one matching VRAM mutation.
 * ESC/CSI intermediate bytes MUST leave both source and pixels unchanged. */
static void ansi_screen_sync(void) {
    bool page=false;
    UartLine line;
    uint8_t p=7U;
    init();
    uart_line_init(&line);
    assert(cpc_uart_console_prompt(&t,&page) && !page);
    for(size_t i=0;i<3U;++i) {
        uint8_t ch=(uint8_t)("ABC"[i]);
        assert(uart_line_feed(&line,ch)==UART_LINE_APPEND);
        assert(cpc_uart_console_append(&t,ch));
    }
    assert(line.length==3U && t.column==3U);
    assert(cpc_video_get(&v,2U*8U,0U,&p) && p==1U); /* C */
    assert(cpc_video_get(&v,3U*8U,0U,&p) && p==0U); /* no prompt glyph */
    /* Move under C and delete forward; unlike legacy tail-delete. */
    assert(uart_line_feed(&line,0x1bU)==UART_LINE_IGNORED);
    assert(uart_line_feed(&line,'[')==UART_LINE_IGNORED);
    assert(uart_line_feed(&line,'D')==UART_LINE_LEFT);
    CpcUartEditor edit;
    /* This older test uses tail-only drawing: we position the live view
     * explicitly at its current end, then check the new editor below. */
    assert(cpc_uart_console_edit_begin(&t,&edit));
    /* The editor anchor belongs at column zero, not the tail of ABC. */
    edit.row=0U; edit.column=0U; edit.painted=3U;
    assert(cpc_uart_console_edit(&t,&edit,&line,line.length));
    static const uint8_t ansi[]={0x1bU,'[','3','~'};
    for(size_t i=0;i<3U;++i)
        assert(uart_line_feed(&line,ansi[i])==UART_LINE_IGNORED);
    assert(uart_line_feed(&line,ansi[3U])==UART_LINE_DELETE_FORWARD);
    assert(cpc_uart_console_edit(&t,&edit,&line,line.cursor_pos));
    assert(t.column==2U && line.length==2U);
    assert(memcmp(line.data,"AB",2U)==0);
    assert(cpc_video_get(&v,2U*8U,0U,&p) && p==0U);
    static const uint8_t unknown[]={0x1bU,'[','1',';','2','D'};
    for(size_t i=0;i<sizeof(unknown);++i)
        assert(uart_line_feed(&line,unknown[i])==UART_LINE_IGNORED);
    assert(line.length==2U && line.cursor_pos==2U);
    /* Move back to delete B using Backspace; source/VRAM agree. */
    assert(uart_line_feed(&line,0x08U)==UART_LINE_DELETE);
    assert(cpc_uart_console_edit(&t,&edit,&line,line.cursor_pos));
    assert(t.column==1U && line.length==1U && line.data[0]=='A');
    assert(cpc_video_get(&v,1U*8U,0U,&p) && p==0U);
    assert(cpc_video_get(&v,0U,0U,&p) && p==1U);
    assert(uart_line_feed(&line,'\r')==UART_LINE_READY);
    assert(line.length==1U && line.data[0]=='A');
    uart_line_ack(&line);
    guarded();
}

static void saturation(void) {
    bool page = false;
    size_t pages=0U;
    init();
    for (size_t i=0U;i<100U;++i) {
        assert(cpc_uart_console_prompt(&t,&page));
        if(page) ++pages;
        for(size_t j=0U;j<UART_LINE_CAPACITY;++j)
            assert(cpc_uart_console_append(&t,'X'));
        assert(cpc_uart_console_end_line(&t));
        assert(t.row<=25U);
    }
    assert(pages == 0U);
    assert(t.scrolls > 0U && t.row < 25U && t.bytes_clipped == 0U);
    assert(cpc_uart_console_clear(&t));
    assert(t.row==0U && t.column==0U);
    guarded();
}
int main(void) {
    edits(); wrap_erase(); ansi_screen_sync(); saturation();
    puts("HW4-C3-B2 visual echo/scroll canaries PASS");
    return 0;
}
