/* HW4-C3-A: portable original HW3 glyph/layout integration, no ESP-IDF. */
#include "cpc_boot.h"
#include "cpc_font.h"
#include "cpc_uart_console.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct { uint8_t before[8],pixels[CPC_VIDEO_BYTES],after[8]; } Guard;
static Guard g;
static CpcVideo video;
static CpcText sink;
static uint16_t rgb[320];
static uint8_t glyph(void *ctx,uint8_t ch,unsigned y)
{ (void)ctx; return hw3_glyph_row(ch,y); }

static void start(void)
{
    memset(&g,0,sizeof g);
    memset(g.before,0xa5,sizeof g.before);
    memset(g.after,0x5a,sizeof g.after);
    assert(cpc_video_init(&video,g.pixels,CPC_VIDEO_BYTES,CPC_MODE_1));
    assert(cpc_video_set_ink(&video,0U,1U));
    assert(cpc_video_set_ink(&video,1U,24U));
    assert(cpc_video_set_border(&video,1U));
    assert(cpc_video_set_text_colors(&video,1U,0U));
    assert(cpc_text_init(&sink,&video,glyph,NULL));
}
static void guarded(void)
{
    for(size_t i=0U;i<8U;++i) {
        assert(g.before[i]==0xa5U);
        assert(g.after[i]==0x5aU);
    }
}
static void check(bool cyd)
{
    static const unsigned rows[5]={3U,5U,7U,10U,12U};
    static const char *const lines[5]={
        "Amstrad 128K Microcomputer (v3)",
        "\x7f" "1985 Amstrad Consumer Electronics plc",
        "and Locomotive Software Ltd.",
        "BASIC 1.1","Ready"
    };
    const unsigned input_row=cyd ? 12U : 13U;
    start();
    assert(!cpc_boot_console(NULL,cyd));
    assert(!cpc_boot_line(5U,cyd,NULL));
    assert(cpc_boot_console(&sink,cyd));
    assert(!cpc_boot_console(&sink,cyd)); /* cannot repeat over live editor */
    assert(sink.row==input_row && sink.column==0U);
    assert(video.cursor_visible && video.cursor_row==input_row && video.cursor_column==0U);
    assert(sink.bytes_received==0U && sink.glyphs_drawn==0U &&
           sink.input_fnv1a==UINT32_C(2166136261));
    for(unsigned i=0U;i<CPC_BOOT_LINES;++i) {
        CpcBootLine line;
        const char *expected=i==0U && cyd
          ? "ESP32 CYD 128K Microcomputer (v3)" : lines[i];
        assert(cpc_boot_line(i,cyd,&line));
        const unsigned expected_row=(cyd && i==2U) ? 6U
                                   : (cyd && i==3U) ? 9U
                                   : (cyd && i==4U) ? 11U : rows[i];
        assert(line.row==expected_row && strcmp(line.text,expected)==0);
        assert(line.column==(i<3U
              ? (40U-(unsigned)strlen(expected))/2U : i==3U ? 1U : 0U));
        assert(line.column+strlen(expected)<=40U);
        for(size_t j=0U;j<strlen(expected);++j) {
            uint8_t ch=(uint8_t)(unsigned char)expected[j];
            assert(ch!=(uint8_t)'>');
            uint8_t glyph_mask=0U;
            for(unsigned y=0U;y<8U;++y) {
                uint8_t bitmap=glyph(NULL,ch,y);
                glyph_mask=(uint8_t)(glyph_mask|bitmap);
                for(unsigned x=0U;x<8U;++x) {
                    uint8_t pen=3U;
                    assert(cpc_video_get(&video,(line.column+(unsigned)j)*8U+x,
                                         line.row*8U+y,&pen));
                    assert(pen==((bitmap & (uint8_t)(0x80U>>x)) ? 1U : 0U));
                }
            }
            if(ch!=' ') assert(glyph_mask!=0U);
        }
    }
    /* CYD logo has credits directly below copyright; HW3 OFF unchanged. */
    CpcBootLine copyright_line, credits_line, basic_line, ready_line;
    assert(cpc_boot_line(1U,cyd,&copyright_line));
    assert(cpc_boot_line(2U,cyd,&credits_line));
    assert(cpc_boot_line(3U,cyd,&basic_line));
    assert(cpc_boot_line(4U,cyd,&ready_line));
    assert(copyright_line.row==5U);
    assert(credits_line.row==(cyd ? 6U : 7U));
    assert(basic_line.row==(cyd ? 9U : 10U));
    assert(ready_line.row==(cyd ? 11U : 12U));
    assert(ready_line.row+1U==input_row);
    if(cyd) {
        assert(credits_line.row==copyright_line.row+1U);
    } else {
        /* Row 6 remains fully empty in the original HW3 OFF display. */
        for(unsigned x=0U;x<320U;++x) {
            for(unsigned y=48U;y<56U;++y) {
                uint8_t pen=255U;
                assert(cpc_video_get(&video,x,y,&pen));
                assert(pen==0U);
            }
        }
    }
    /* The old BASIC position is empty in ON; the opposite in HW3 OFF.
     * No glyph can leak into the adjacent, now-unused row. */
    const unsigned empty_basic_row=cyd ? 10U : 9U;
    for(unsigned y=empty_basic_row*8U; y<(empty_basic_row+1U)*8U; ++y)
        for(unsigned x=0U;x<320U;++x) {
            uint8_t pen=255U;
            assert(cpc_video_get(&video,x,y,&pen));
            assert(pen==0U);
        }
    CpcBootLine invalid;
    assert(!cpc_boot_line(CPC_BOOT_LINES,cyd,&invalid));
    /* Cursor overlay: framebuffer remains unchanged regardless of visibility. */
    static uint8_t snapshot[CPC_VIDEO_BYTES];
    memcpy(snapshot,g.pixels,sizeof snapshot);
    assert(cpc_video_render_row(&video,20U+input_row*8U,rgb,320U));
    assert(rgb[0]==UINT16_C(0xffe0));
    assert(cpc_video_cursor(&video,0U,input_row,false));
    assert(cpc_video_render_row(&video,20U+input_row*8U,rgb,320U));
    assert(rgb[0]==UINT16_C(0x0010));
    assert(memcmp(snapshot,g.pixels,sizeof snapshot)==0);
    assert(cpc_video_render_row(&video,0U,rgb,320U));
    for(unsigned x=0U;x<320U;++x) assert(rgb[x]==UINT16_C(0x0010));
    /* First prompt preserves banner; ON input follows Ready at row 12. */
    bool paged=true;
    assert(cpc_uart_console_prompt(&sink,&paged) && !paged);
    assert(sink.row==input_row && sink.column==0U);
    assert(cpc_uart_console_append(&sink,(uint8_t)'1'));
    assert(cpc_uart_console_append(&sink,(uint8_t)'0'));
    assert(sink.column==2U && sink.row==input_row);
    assert(cpc_uart_console_backspace(&sink));
    assert(sink.column==1U);
    assert(cpc_uart_console_end_line(&sink));
    assert(sink.row==input_row+1U && sink.column==0U);
    guarded();
    assert(cpc_uart_console_clear(&sink)); /* !CLS intentionally clears banner */
    assert(sink.row==0U && sink.column==0U);
    uint8_t pixel=3U;
    assert(cpc_video_get(&video,8U,3U*8U,&pixel) && pixel==0U);
    guarded();
}
static void pages(void)
{
    start();
    assert(cpc_boot_console(&sink,true));
    unsigned paged_count=0U;
    for(unsigned n=0U;n<100U;++n) {
        bool paged=false;
        assert(cpc_uart_console_prompt(&sink,&paged));
        if(paged) ++paged_count;
        for(unsigned i=0U;i<120U;++i)
            assert(cpc_uart_console_append(&sink,(uint8_t)'X'));
        assert(cpc_uart_console_end_line(&sink));
        assert(sink.row<=25U);
    }
    assert(paged_count>0U);
    guarded();
}
int main(void)
{
    check(false);
    check(true);
    const char *letters="UWY";
    for(size_t i=0U;letters[i]!='\0';++i) {
        uint8_t mask=0U;
        for(unsigned j=0U;j<8U;++j)
            mask=(uint8_t)(mask|hw3_glyph_row((uint8_t)letters[i],j));
        assert(mask!=0U);
    }
    pages();
    puts("HW4-C3-A boot/layout/VRAM/font/cursor/paging canaries PASS");
    return 0;
}
