/* HW4-C3-B2-C1: deterministic portable comparison, never a CYD SPI claim.
 * One identical 53-byte input at row 24, followed by LF/Ready/prompt:
 * previous per-character flush versus fully composed final frame. MIT. */
#include "cpc_uart_console.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define ALL UINT32_C(0x01ffffff)
typedef struct {
    uint32_t bands, flushes;
    uint32_t scrolls;
    uint8_t pixels[CPC_VIDEO_BYTES];
    uint32_t fnv;
    unsigned row, column;
    bool cursor;
} Capture;
static struct {
    uint8_t pre[8], pixels[CPC_VIDEO_BYTES], post[8];
} guard;
static CpcVideo video;
static CpcText text;
static uint8_t glyph(void *ctx,uint8_t ch,unsigned row)
{
    (void)ctx;
    return row==0U && ch!=(uint8_t)' ' ? UINT8_C(0x80) : 0U;
}
static bool transfer(void *context,unsigned band)
{
    Capture *out=(Capture *)context;
    assert(band<25U);
    ++out->bands;
    return true;
}
static void flush(Capture *out)
{
    ++out->flushes;
    assert(cpc_video_flush_dirty(&video,transfer,out));
}
static void init(void)
{
    memset(&guard,0,sizeof(guard));
    memset(guard.pre,0xa5,sizeof(guard.pre));
    memset(guard.post,0x5a,sizeof(guard.post));
    assert(cpc_video_init(&video,guard.pixels,sizeof(guard.pixels),CPC_MODE_1));
    assert(cpc_video_set_text_colors(&video,1U,0U));
    assert(cpc_text_init(&text,&video,glyph,NULL));
    const uint8_t newlines[24]={'\n','\n','\n','\n','\n','\n','\n','\n',
                                '\n','\n','\n','\n','\n','\n','\n','\n',
                                '\n','\n','\n','\n','\n','\n','\n','\n'};
    assert(cpc_text_write(&text,newlines,sizeof(newlines)));
    assert(cpc_video_take_dirty(&video)==ALL);
    assert(text.row==24U);
}
static void save(Capture *out)
{
    out->scrolls=(uint32_t)text.scrolls;
    out->fnv=text.input_fnv1a;
    out->row=text.row;
    out->column=text.column;
    out->cursor=video.cursor_visible;
    memcpy(out->pixels,guard.pixels,CPC_VIDEO_BYTES);
    for(unsigned i=0U;i<8U;++i) {
        assert(guard.pre[i]==UINT8_C(0xa5));
        assert(guard.post[i]==UINT8_C(0x5a));
    }
    assert(video.dirty_bands==0U);
}
static void scenario(Capture *out,bool flush_each)
{
    static const uint8_t input[]=
        "10 REM ************************************* XXXXXXXX";
    static const uint8_t ready[]="Ready\n";
    bool cleared=false;
    memset(out,0,sizeof(*out));
    init();
    /* The 53-byte scenario is deliberately screen-only (no BASIC ROM claim). */
    assert(sizeof(input)-1U==53U);
    for(size_t i=0U;i<sizeof(input)-1U;++i) {
        assert(cpc_uart_console_append(&text,input[i]));
        if(flush_each) flush(out);
    }
    assert(cpc_uart_console_end_line(&text));
    if(flush_each) flush(out);
    assert(cpc_text_write(&text,ready,sizeof(ready)-1U));
    if(flush_each) flush(out);
    assert(cpc_uart_console_prompt(&text,&cleared) && !cleared);
    flush(out);
    save(out);
}
typedef struct {
    unsigned calls, fail_at;
    bool sticky;
} LatchedTransport;
static bool latched_transfer(void *ctx,unsigned band)
{
    LatchedTransport *t=(LatchedTransport *)ctx;
    /* A latched device rejects further work; firmware must never invoke it
     * again after the first failure (only this one attempt is scheduled). */
    assert(!t->sticky);
    ++t->calls;
    if(band==t->fail_at) {
        t->sticky=true;
        return false;
    }
    return true;
}
static void failed_latched_transfer(void)
{
    static const unsigned points[]={0U,12U,24U};
    for(unsigned i=0U;i<3U;++i) {
        init();
        assert(cpc_video_scroll_up(&video,1U));
        LatchedTransport t={0U,points[i],false};
        /* Firmware B2-C1 policy: call flush once, leave latching intact. */
        assert(!cpc_video_flush_dirty(&video,latched_transfer,&t));
        assert(t.sticky && t.calls==points[i]+1U);
        uint32_t expected=ALL & ~((UINT32_C(1)<<points[i])-1U);
        assert(video.dirty_bands==expected);
        /* No second attempt: the failed band and all subsequent bands remain
         * dirty but are NOT sent to the simulated permanently failed device. */
        assert(t.calls==points[i]+1U);
        assert(!t.sticky || video.dirty_bands==expected);
    }
}
int main(void)
{
    static Capture old_path,new_path;
    scenario(&old_path,true);
    scenario(&new_path,false);
    assert(old_path.bands>new_path.bands);
    assert(new_path.bands==25U);
    assert(old_path.bands>=2U*new_path.bands);
    assert(new_path.flushes==1U);
    assert(old_path.flushes>new_path.flushes);
    assert(old_path.scrolls==new_path.scrolls);
    assert(old_path.fnv==new_path.fnv);
    assert(old_path.row==new_path.row);
    assert(old_path.column==new_path.column);
    assert(old_path.cursor==new_path.cursor);
    assert(memcmp(old_path.pixels,new_path.pixels,CPC_VIDEO_BYTES)==0);
    failed_latched_transfer();
    printf("B2-C1 FIXED_53 BEFORE flushes=%u bands=%u spi_bytes=%u "
           "AFTER flushes=%u bands=%u spi_bytes=%u scrolls=%u "
           "VRAM_IDENTICAL=1 FAIL_STOP_INJECTED=0,12,24 PASS\n",
           old_path.flushes,old_path.bands,old_path.bands*5120U,
           new_path.flushes,new_path.bands,new_path.bands*5120U,
           new_path.scrolls);
    return 0;
}
