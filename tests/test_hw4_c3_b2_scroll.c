/* HW4-C3-B2: MODE1 scroll, text cursor, canaries and injected LCD failures.
 * HOST-only test; does not claim a real TFT DMA failure or ROM pixel oracle. */
#include "cpc_uart_console.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define ALL UINT32_C(0x01ffffff)
typedef struct { uint8_t pre[8], pixels[CPC_VIDEO_BYTES], post[8]; } Guard;
static Guard g;
static CpcVideo v;
static CpcText t;
static uint8_t before[CPC_VIDEO_BYTES];

static uint8_t glyph(void *ctx, uint8_t ch, unsigned row)
{
    (void)ctx;
    return row==0U && ch!=(uint8_t)' ' ? UINT8_C(0x80) : 0U;
}
static void canaries(void)
{
    for (unsigned i=0U;i<8U;++i) {
        assert(g.pre[i]==UINT8_C(0xa5));
        assert(g.post[i]==UINT8_C(0x5a));
    }
}
static void reset(void)
{
    memset(&g,0,sizeof(g));
    memset(g.pre,0xa5,sizeof(g.pre));
    memset(g.post,0x5a,sizeof(g.post));
    assert(cpc_video_init(&v,g.pixels,CPC_VIDEO_BYTES,CPC_MODE_1));
    assert(cpc_video_set_text_colors(&v,1U,0U));
    assert(cpc_text_init(&t,&v,glyph,NULL));
    assert(cpc_video_take_dirty(&v)==ALL);
}
static uint32_t fnv(const uint8_t *s,size_t n)
{
    uint32_t hash=UINT32_C(2166136261);
    for(size_t i=0U;i<n;++i)
        hash=(hash^(uint32_t)s[i])*UINT32_C(16777619);
    return hash;
}
static void scroll_pixels(void)
{
    for(unsigned paper=0U;paper<4U;++paper) {
        reset();
        assert(cpc_video_set_text_colors(&v,1U,paper));
        for(unsigned row=0U;row<25U;++row)
            memset(g.pixels+(size_t)row*640U,(int)row,640U);
        memcpy(before,g.pixels,sizeof(before));
        assert(cpc_video_scroll_up(&v,0U));
        assert(memcmp(before,g.pixels,sizeof(before))==0);
        assert(cpc_video_take_dirty(&v)==0U);
        assert(cpc_video_scroll_up(&v,1U));
        assert(memcmp(g.pixels,before+640U,15360U)==0);
        for(size_t j=15360U;j<CPC_VIDEO_BYTES;++j)
            assert(g.pixels[j]==(uint8_t)(paper*UINT8_C(0x55)));
        assert(cpc_video_take_dirty(&v)==ALL);
        assert(cpc_video_scroll_up(&v,1U));
        assert(memcmp(g.pixels,before+1280U,14720U)==0);
        assert(cpc_video_take_dirty(&v)==ALL);
        assert(cpc_video_scroll_up(&v,25U));
        for(size_t j=0U;j<CPC_VIDEO_BYTES;++j)
            assert(g.pixels[j]==(uint8_t)(paper*UINT8_C(0x55)));
        assert(cpc_video_take_dirty(&v)==ALL);
        canaries();
    }
}
static void reject_atomic(void)
{
    reset();
    CpcVideo state=v;
    memcpy(before,g.pixels,sizeof(before));
    assert(!cpc_video_scroll_up(NULL,1U));
    assert(!cpc_video_scroll_up(&v,26U));
    assert(!cpc_video_scroll_up(&v,UINT32_MAX));
    assert(memcmp(&v,&state,sizeof(v))==0);
    v.paper=4U;
    assert(!cpc_video_scroll_up(&v,1U));
    v=state;
    v.cursor_row=25U;
    assert(!cpc_video_scroll_up(&v,1U));
    v=state;
    v.cursor_column=40U;
    assert(!cpc_video_scroll_up(&v,1U));
    v=state;
    v.mode=CPC_MODE_2;
    assert(!cpc_video_scroll_up(&v,1U));
    v=state;
    assert(memcmp(before,g.pixels,sizeof(before))==0);
    assert(v.dirty_bands==0U);
    canaries();
}
typedef struct {
    unsigned fail_at, calls, first, last;
    bool fail;
} FakeDMA;
static bool fake_send(void *ctx,unsigned band)
{
    FakeDMA *d=(FakeDMA *)ctx;
    if(d->calls==0U) d->first=band;
    d->last=band;
    ++d->calls;
    assert(band<25U);
    return !(d->fail && band==d->fail_at);
}
static void failed_dma(void)
{
    static const unsigned positions[]={0U,12U,24U};
    for(unsigned z=0U;z<3U;++z) {
        reset();
        assert(cpc_video_scroll_up(&v,1U));
        FakeDMA d={positions[z],0U,0U,0U,true};
        assert(!cpc_video_flush_dirty(NULL,fake_send,&d));
        assert(!cpc_video_flush_dirty(&v,NULL,&d));
        assert(v.dirty_bands==ALL);
        assert(!cpc_video_flush_dirty(&v,fake_send,&d));
        assert(d.calls==positions[z]+1U);
        assert(d.first==0U && d.last==positions[z]);
        uint32_t expected=ALL & ~((UINT32_C(1)<<positions[z])-1U);
        assert(v.dirty_bands==expected);
        d.calls=0U;
        d.fail=false;
        assert(cpc_video_flush_dirty(&v,fake_send,&d));
        assert(d.first==positions[z] && d.last==24U);
        assert(d.calls==25U-positions[z]);
        assert(cpc_video_take_dirty(&v)==0U);
        canaries();
    }
}
static void text_boundary(void)
{
    uint8_t row[120U];
    memset(row,'Q',sizeof(row));
    reset();
    assert(cpc_text_write(&t,row,40U));
    assert(t.column==40U && t.row==0U && t.scrolls==0U);
    assert(cpc_text_write(&t,row,80U));
    assert(t.column==40U && t.row==2U && t.scrolls==0U);
    const uint8_t cr=(uint8_t)'\r';
    assert(cpc_text_write(&t,&cr,1U));
    assert(t.row==2U && t.column==0U);
    assert(cpc_text_write(&t,row,1U));
    assert(t.column==1U && t.row==2U);
    canaries();

    reset();
    uint8_t lfs[124U];
    memset(lfs,'\n',sizeof(lfs));
    assert(cpc_text_write(&t,lfs,sizeof(lfs)));
    assert(t.row==24U && t.column==0U && t.scrolls==100U);
    assert(t.bytes_received==sizeof(lfs));
    assert(t.input_fnv1a==fnv(lfs,sizeof(lfs)));
    assert(t.bytes_clipped==0U);
    assert(cpc_video_take_dirty(&v)==ALL);
    canaries();

    reset();
    uint8_t last[24U];
    memset(last,'\n',sizeof(last));
    assert(cpc_text_write(&t,last,sizeof(last)));
    assert(t.row==24U);
    assert(cpc_text_write(&t,row,40U));
    assert(t.row==24U && t.column==40U && !v.cursor_visible);
    const size_t drawn=t.glyphs_drawn;
    assert(cpc_text_write(&t,&cr,1U));
    assert(t.row==24U && t.column==0U && t.scrolls==0U);
    assert(t.glyphs_drawn==drawn);
    assert(cpc_text_write(&t,row,1U));
    assert(t.row==24U && t.column==1U);
    const uint8_t lf=(uint8_t)'\n';
    assert(cpc_text_write(&t,&lf,1U));
    assert(t.row==24U && t.column==0U && t.scrolls==1U);
    assert(v.cursor_visible && v.cursor_row==24U);
    canaries();
}
static void text_rejection(void)
{
    reset();
    const uint8_t a=(uint8_t)'A';
    CpcText copy=t;
    CpcVideo vcopy=v;
    memcpy(before,g.pixels,sizeof(before));
    assert(!cpc_text_write(&t,NULL,1U));
    t.row=25U;
    assert(!cpc_text_write(&t,&a,1U));
    t=copy;
    t.column=41U;
    assert(!cpc_text_write(&t,&a,1U));
    t=copy;
    t.bytes_received=SIZE_MAX;
    assert(!cpc_text_write(&t,&a,1U));
    t=copy;
    t.scrolls=SIZE_MAX;
    assert(!cpc_text_write(&t,&a,1U));
    t=copy;
    assert(memcmp(&t,&copy,sizeof(t))==0);
    assert(memcmp(&v,&vcopy,sizeof(v))==0);
    assert(memcmp(g.pixels,before,sizeof(before))==0);
    canaries();
}
static void uart_bottom(void)
{
    reset();
    bool page=true;
    uint8_t lf[24U];
    memset(lf,'\n',sizeof(lf));
    assert(cpc_text_write(&t,lf,sizeof(lf)));
    assert(cpc_uart_console_prompt(&t,&page) && !page);
    for(unsigned i=0U;i<120U;++i)
        assert(cpc_uart_console_append(&t,(uint8_t)'X'));
    assert(t.row==24U && t.column==40U && t.scrolls==2U);
    assert(cpc_uart_console_backspace(&t));
    assert(t.row==24U && t.column==39U);
    assert(cpc_uart_console_end_line(&t));
    assert(t.row==24U && t.scrolls==3U && t.column==0U);
    assert(cpc_uart_console_prompt(&t,&page) && !page);
    assert(cpc_uart_console_clear(&t)); /* explicit !CLS */
    assert(t.row==0U && t.column==0U && t.scrolls==0U);
    canaries();
}
int main(void)
{
    scroll_pixels(); reject_atomic(); failed_dma();
    text_boundary(); text_rejection(); uart_bottom();
    puts("HW4-C3-B2 MODE1 SCROLL + DMA RETRY HOST PASS");
    return 0;
}
