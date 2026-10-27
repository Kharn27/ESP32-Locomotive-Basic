/* HW4-C2 40x25 pagination, prompt, echo and bounded erase with canaries. */
#include "cpc_uart_console.h"
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
    assert(t.column==1U);
    assert(cpc_uart_console_append(&t,'X'));
    assert(cpc_video_get(&v,8U,0U,&p) && p==1U);
    assert(cpc_uart_console_backspace(&t));
    assert(t.column==1U && t.row==0U);
    assert(cpc_video_get(&v,8U,0U,&p) && p==0U);
    assert(cpc_uart_console_append(&t,'5'));
    assert(cpc_uart_console_end_line(&t) && t.row==1U);
    assert(cpc_uart_console_prompt(&t,&page) && !page);
    assert(t.row==1U && t.column==1U);
    guarded();
}
static void wrap_erase(void) {
    bool page = false;
    init();
    assert(cpc_uart_console_prompt(&t,&page));
    for(size_t i=0U; i<45U; ++i)
        assert(cpc_uart_console_append(&t,'X'));
    assert(t.row==1U && t.column==6U);
    for(size_t i=0U;i<7U;++i) assert(cpc_uart_console_backspace(&t));
    assert(t.row==0U && t.column==39U);
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
    assert(pages > 0U);
    assert(cpc_uart_console_clear(&t));
    assert(t.row==0U && t.column==0U);
    guarded();
}
int main(void) {
    edits(); wrap_erase(); saturation();
    puts("HW4-C2 visual echo/page canaries PASS");
    return 0;
}
