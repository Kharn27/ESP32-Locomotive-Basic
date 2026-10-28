/* HW4-EDIT-P1: host-only E2 MODE1 semantic coverage; no COPY behavior.
 * Pixel, source editor and existing cursor remain unchanged. MIT. */
#include "cpc_boot.h"
#include "cpc_uart_console.h"
#include "uart_line.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { N = CPC_VIDEO_MODE1_CELLS };
typedef struct {
    uint8_t before[8];
    CpcVideo value;
    uint8_t after[8];
} GuardVideo;
typedef struct {
    uint8_t before[8];
    uint8_t pixels[CPC_VIDEO_BYTES];
    uint8_t after[8];
} GuardPixels;
static GuardVideo gv;
static GuardPixels gp;
static CpcText text;
static uint8_t saved_pixels[CPC_VIDEO_BYTES];
static uint16_t render_before[320], render_after[320];

static uint8_t glyph(void *ctx, uint8_t ch, unsigned dy)
{
    (void)ctx;
    return ch == (uint8_t)' ' ? 0U : (uint8_t)(ch ^ (uint8_t)(dy * 23U));
}
static CpcVideo *v(void) { return &gv.value; }
static void guards(void)
{
    for (size_t i=0U; i<8U; ++i) {
        assert(gp.before[i] == 0xa5U && gp.after[i] == 0x5aU);
        assert(gv.before[i] == 0x96U && gv.after[i] == 0x69U);
    }
}
static void fresh(void)
{
    memset(&gv,0,sizeof gv);
    memset(&gp,0,sizeof gp);
    memset(gv.before,0x96,8U);
    memset(gv.after,0x69,8U);
    memset(gp.before,0xa5,8U);
    memset(gp.after,0x5a,8U);
    assert(cpc_video_init(v(),gp.pixels,CPC_VIDEO_BYTES,CPC_MODE_1));
    assert(cpc_text_init(&text,v(),glyph,NULL));
    guards();
}
static void cell(unsigned col,unsigned row,bool expected,uint8_t ch)
{
    uint8_t got = 0xe7U;
    bool known = !expected;
    assert(cpc_video_read_cell(v(),col,row,&got,&known));
    assert(known == expected);
    if (expected) assert(got == ch);
    else assert(got == 0xe7U); /* Unknown must not invent a space. */
}
static void all_unknown(void)
{
    for(unsigned row=0U;row<25U;++row)
        for(unsigned col=0U;col<40U;++col) cell(col,row,false,0U);
}
static void negative_unchanged(void)
{
    CpcVideo saved=*v();
    memcpy(saved_pixels,gp.pixels,sizeof saved_pixels);
    uint8_t ch=0xa6U;
    bool known=true;
    assert(!cpc_video_read_cell(NULL,0U,0U,&ch,&known));
    assert(!cpc_video_read_cell(v(),40U,0U,&ch,&known));
    assert(!cpc_video_read_cell(v(),0U,25U,&ch,&known));
    assert(!cpc_video_read_cell(v(),UINT32_MAX,0U,&ch,&known));
    assert(!cpc_video_read_cell(v(),0U,0U,NULL,&known));
    assert(!cpc_video_read_cell(v(),0U,0U,&ch,NULL));
    assert(ch==0xa6U && known);
    assert(!cpc_video_put_cell(v(),40U,0U,'X',glyph,NULL));
    assert(!cpc_video_put_cell(v(),0U,25U,'X',glyph,NULL));
    assert(!cpc_video_put_cell(v(),0U,0U,'X',NULL,NULL));
    assert(!cpc_video_put(v(),320U,0U,1U));
    assert(!cpc_video_put(v(),0U,200U,1U));
    assert(!cpc_video_put(v(),0U,0U,4U));
    assert(!cpc_video_scroll_up(v(),26U));
    assert(!cpc_video_scroll_up(v(),UINT32_MAX));
    assert(!cpc_video_set_mode(v(),(CpcMode)3));
    assert(memcmp(&saved,v(),sizeof saved)==0);
    assert(memcmp(saved_pixels,gp.pixels,sizeof saved_pixels)==0);
    guards();
}
static void test_glyph_and_pixel(void)
{
    fresh();
    all_unknown();
    cell(0U,0U,false,0U);
    assert(cpc_video_put_cell(v(),0U,0U,' ',glyph,NULL));
    cell(0U,0U,true,' ');
    assert(cpc_video_put_cell(v(),39U,24U,'Z',glyph,NULL));
    cell(39U,24U,true,'Z');
    assert(cpc_video_put_cell(v(),39U,24U,'A',glyph,NULL));
    cell(39U,24U,true,'A');
    /* Repaint changes E2 only after the full glyph, not each pixel. */
    assert(cpc_video_put_cell(v(),1U,1U,'B',glyph,NULL));
    cell(1U,1U,true,'B');
    assert(cpc_video_render_row(v(),20U+8U,render_before,320U));
    memcpy(saved_pixels,gp.pixels,sizeof saved_pixels);
    cell(0U,0U,true,' ');
    cell(1U,1U,true,'B');
    assert(cpc_video_render_row(v(),20U+8U,render_after,320U));
    assert(memcmp(render_before,render_after,sizeof render_before)==0);
    assert(memcmp(saved_pixels,gp.pixels,sizeof saved_pixels)==0);
    assert(cpc_video_put(v(),8U,8U,3U));
    cell(1U,1U,false,0U); /* Even drawing same colour means unknown. */
    cell(0U,0U,true,' ');
    cell(39U,24U,true,'A');
    assert(cpc_video_put_cell(v(),1U,1U,'C',glyph,NULL));
    cell(1U,1U,true,'C');
    negative_unchanged();
}
static uint8_t pattern(unsigned col,unsigned row)
{
    return (uint8_t)(33U + (row*40U+col)%90U);
}
static void fill_all(void)
{
    for(unsigned row=0U;row<25U;++row)
        for(unsigned col=0U;col<40U;++col)
            assert(cpc_video_put_cell(v(),col,row,pattern(col,row),glyph,NULL));
}
static void test_scroll(void)
{
    static const unsigned shifts[]={0U,1U,24U,25U};
    for(unsigned z=0U;z<4U;++z) {
        fresh();
        fill_all();
        const unsigned count=shifts[z];
        memcpy(saved_pixels,gp.pixels,sizeof saved_pixels);
        const uint32_t dirty=cpc_video_take_dirty(v());
        assert(dirty == UINT32_C(0x01ffffff));
        const CpcVideo before=*v();
        assert(cpc_video_scroll_up(v(),count));
        if (count==0U) {
            assert(memcmp(&before,v(),sizeof before)==0);
            assert(cpc_video_take_dirty(v())==0U);
        } else {
            const size_t remain=CPC_VIDEO_BYTES-(size_t)count*640U;
            assert(memcmp(gp.pixels,saved_pixels+(size_t)count*640U,remain)==0);
            for(size_t i=remain;i<CPC_VIDEO_BYTES;++i) assert(gp.pixels[i]==0U);
            assert(cpc_video_take_dirty(v())==UINT32_C(0x01ffffff));
        }
        for(unsigned row=0U;row<25U;++row)
            for(unsigned col=0U;col<40U;++col) {
                if(row+count<25U) cell(col,row,true,pattern(col,row+count));
                else cell(col,row,false,0U);
            }
        negative_unchanged();
        guards();
    }
    /* Shifting with a different PAPER fills exactly the raster, never E2. */
    for(unsigned paper=1U;paper<4U;++paper) {
        fresh();
        fill_all();
        assert(cpc_video_set_text_colors(v(),1U,paper));
        assert(cpc_video_scroll_up(v(),25U));
        for(size_t i=0U;i<CPC_VIDEO_BYTES;++i)
            assert(gp.pixels[i]==(uint8_t)(paper*0x55U));
        all_unknown();
        guards();
    }
}
static void test_text_boot_and_clear(void)
{
    fresh();
    assert(cpc_boot_console(&text,true));
    for(unsigned i=0U;i<CPC_BOOT_LINES;++i) {
        CpcBootLine line;
        assert(cpc_boot_line(i,true,&line));
        for(unsigned j=0U;line.text[j]!='\0';++j)
            cell(line.column+j,line.row,true,(uint8_t)(unsigned char)line.text[j]);
    }
    cell(39U,24U,false,0U);
    assert(text.bytes_received==0U && text.glyphs_drawn==0U);
    assert(cpc_uart_console_clear(&text));
    all_unknown();
    const uint8_t bytes[]={'A','B','\r','C','\n','D'};
    assert(cpc_text_write(&text,bytes,sizeof bytes));
    cell(0U,0U,true,'C');
    cell(1U,0U,true,'B');
    cell(0U,1U,true,'D');
    uint8_t full[40];
    memset(full,'Q',sizeof full);
    fresh();
    assert(cpc_text_write(&text,full,sizeof full));
    cell(39U,0U,true,'Q');
    cell(0U,1U,false,0U); /* deferred wrap */
    assert(cpc_text_write(&text,(const uint8_t *)"R",1U));
    cell(0U,1U,true,'R');
    fresh();
    assert(cpc_video_put_cell(v(),0U,1U,'M',glyph,NULL));
    uint8_t lfs[26];
    memset(lfs,'\n',sizeof lfs);
    assert(cpc_text_write(&text,lfs,sizeof lfs));
    cell(0U,0U,false,0U); /* after enough bottom scrolls */
    all_unknown();
    assert(cpc_video_put_cell(v(),3U,4U,'E',glyph,NULL));
    assert(cpc_video_set_mode(v(),CPC_MODE_0));
    uint8_t ch=0xb5U; bool known=true;
    assert(!cpc_video_read_cell(v(),3U,4U,&ch,&known));
    assert(ch==0xb5U && known);
    assert(cpc_video_put_cell(v(),3U,4U,'R',glyph,NULL));
    assert(!cpc_video_read_cell(v(),3U,4U,&ch,&known));
    assert(cpc_video_set_mode(v(),CPC_MODE_2));
    assert(!cpc_video_read_cell(v(),3U,4U,&ch,&known));
    assert(cpc_video_set_mode(v(),CPC_MODE_1));
    all_unknown();
    guards();
}
static void test_editor(void)
{
    fresh();
    UartLine source;
    CpcUartEditor edit;
    uart_line_init(&source);
    assert(cpc_uart_console_edit_begin(&text,&edit));
    static const char input[]="10 PRINT 2";
    for(size_t i=0U;i<sizeof input-1U;++i) {
        assert(uart_line_feed(&source,(uint8_t)input[i])==UART_LINE_APPEND);
        assert(cpc_uart_console_edit(&text,&edit,&source,i));
    }
    for(size_t i=0U;i<sizeof input-1U;++i) cell((unsigned)i,0U,true,(uint8_t)input[i]);
    static const uint8_t left[]={0x1bU,'[','D'};
    for(unsigned i=0U;i<3U;++i) {
        UartLineEvent e=uart_line_feed(&source,left[i]);
        if (e==UART_LINE_LEFT) assert(cpc_uart_console_edit(&text,&edit,&source,source.length));
    }
    assert(source.cursor_pos==source.length-1U && source.data[source.length-1U]=='2');
    cell(9U,0U,true,'2'); /* Cursor overlay never changes E2. */
    static const uint8_t right[]={0x1bU,'[','C'};
    for(unsigned i=0U;i<3U;++i) {
        UartLineEvent e=uart_line_feed(&source,right[i]);
        if (e==UART_LINE_RIGHT) assert(cpc_uart_console_edit(&text,&edit,&source,source.length));
    }
    cell(9U,0U,true,'2');
    assert(uart_line_feed(&source,0x08U)==UART_LINE_DELETE);
    assert(cpc_uart_console_edit(&text,&edit,&source,source.cursor_pos));
    cell(9U,0U,true,' ');
    assert(source.length==9U && source.data[9U]==0U);
    assert(cpc_uart_console_clear(&text));
    all_unknown();
    guards();
}
int main(void)
{
    assert(CPC_VIDEO_MODE1_CELLS==1000U);
    assert(CPC_VIDEO_MODE1_VALID_BYTES==125U);
    test_glyph_and_pixel();
    test_scroll();
    test_text_boot_and_clear();
    test_editor();
    puts("HW4-EDIT-P1 MODE1 E2 semantics, negatives, boot, text, editor, scroll PASS");
    return 0;
}
