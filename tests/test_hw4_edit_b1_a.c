/* HW4-EDIT-B1-A: E1/E2/E3 regression, host policy != exact CPC ROM. */
#include "cpc_screen_nav.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct {uint8_t before[16],pixels[CPC_VIDEO_BYTES],after[16];} Guard;
static Guard g;
static CpcVideo v;
static CpcText text;
static CpcUartEditor edit;
static CpcScreenNavigation nav;
static UartLine line;
static uint8_t pixels[CPC_VIDEO_BYTES],chars[1000],valids[125],source[121];
static uint16_t rgb_before[320],rgb_after[320];
static uint8_t prog[32];
static uint8_t glyph(void *ctx,uint8_t c,unsigned r)
{
    (void)ctx;
    return c==' ' ? 0U : (uint8_t)((r&1U)?0xf0U:0x0fU);
}
static void guards(void)
{
    for(size_t i=0U;i<16U;++i)
        assert(g.before[i]==0xa5U && g.after[i]==0x5aU);
    for(size_t i=0U;i<sizeof prog;++i) assert(prog[i]==0x96U);
    assert(line.length<=120U && line.cursor_pos<=line.length);
    assert(line.data[line.length]==0U);
}
static void reset(unsigned row,unsigned col)
{
    memset(&g,0,sizeof g);
    memset(g.before,0xa5,sizeof g.before);
    memset(g.after,0x5a,sizeof g.after);
    memset(prog,0x96,sizeof prog);
    assert(row<25U && col<40U);
    assert(cpc_video_init(&v,g.pixels,CPC_VIDEO_BYTES,CPC_MODE_1));
    assert(cpc_video_set_ink(&v,0U,1U));
    assert(cpc_video_set_ink(&v,1U,24U));
    assert(cpc_video_set_text_colors(&v,1U,0U));
    assert(cpc_text_init(&text,&v,glyph,NULL));
    text.row=row;text.column=col;
    assert(cpc_video_cursor(&v,col,row,true));
    uart_line_init(&line);
    assert(cpc_uart_console_edit_begin(&text,&edit));
    cpc_screen_nav_init(&nav);guards();
}
static void save(void)
{
    memcpy(pixels,g.pixels,sizeof pixels);
    memcpy(chars,v.cell_char,sizeof chars);
    memcpy(valids,v.cell_valid,sizeof valids);
    memcpy(source,line.data,sizeof source);
}
static void same(void)
{
    assert(memcmp(pixels,g.pixels,sizeof pixels)==0);
    assert(memcmp(chars,v.cell_char,sizeof chars)==0);
    assert(memcmp(valids,v.cell_valid,sizeof valids)==0);
    assert(memcmp(source,line.data,sizeof source)==0);
    guards();
}
static UartLineEvent feed(uint8_t ch)
{
    UartLineEvent e=uart_line_feed_screen(&line,ch);
    if(e==UART_LINE_NAV_UP||e==UART_LINE_NAV_DOWN||
       e==UART_LINE_NAV_LEFT||e==UART_LINE_NAV_RIGHT)
        assert(cpc_screen_nav_move(&nav,&text,&edit,&line,e));
    else if(e==UART_LINE_RETURN_EDIT)
        assert(cpc_screen_nav_resume(&nav,&text,&edit,&line));
    else if(e==UART_LINE_APPEND||e==UART_LINE_DELETE||
            e==UART_LINE_DELETE_FORWARD||e==UART_LINE_LEFT||
            e==UART_LINE_RIGHT) {
        size_t from=e==UART_LINE_APPEND?line.cursor_pos-1U:
                    (e==UART_LINE_DELETE||e==UART_LINE_DELETE_FORWARD)?
                    line.cursor_pos:line.length;
        assert(cpc_uart_console_edit(&text,&edit,&line,from));
    }
    return e;
}
static UartLineEvent seq(const char *s)
{
    UartLineEvent e=UART_LINE_NONE;
    for(size_t i=0U;s[i];++i)e=feed((uint8_t)s[i]);
    return e;
}
static void cell(unsigned c,unsigned r,bool expected,uint8_t ch)
{
    uint8_t got=0xeeU;bool known=!expected;
    assert(cpc_video_read_cell(&v,c,r,&got,&known));
    assert(known==expected);
    if(expected)assert(got==ch);
    else assert(got==0xeeU);
}
static void fill(void)
{
    for(unsigned r=0U;r<25U;++r)
        for(unsigned c=0U;c<40U;++c)
            assert(cpc_video_put_cell(&v,c,r,(uint8_t)('A'+r),glyph,NULL));
}
static void arrows(void)
{
    reset(12U,19U);save();
    assert(seq("\x1b[A")==UART_LINE_NAV_UP);
    assert(v.cursor_row==11U && v.cursor_column==19U);
    assert(seq("\x1b[B")==UART_LINE_NAV_DOWN);
    assert(v.cursor_row==12U && v.cursor_column==19U);
    same();
    assert(seq("\x1b[H")==UART_LINE_RETURN_EDIT);
    assert(!line.screen_navigation);
    assert(feed('\r')==UART_LINE_READY);
    uart_line_ack(&line);
    reset(5U,0U);save();
    assert(seq("\x1b[D")==UART_LINE_NAV_LEFT);
    assert(v.cursor_row==4U && v.cursor_column==39U);
    assert(seq("\x1b[C")==UART_LINE_NAV_RIGHT);
    assert(v.cursor_row==5U && v.cursor_column==0U);
    same();
    assert(seq("\x1b[H")==UART_LINE_RETURN_EDIT);
    reset(0U,0U);
    assert(seq("\x1b[D")==UART_LINE_NAV_LEFT);
    assert(v.cursor_row==0U && v.cursor_column==0U);
    reset(24U,39U);
    assert(seq("\x1b[C")==UART_LINE_NAV_RIGHT);
    assert(v.cursor_row==24U && v.cursor_column==39U);
}
static void overlay(void)
{
    reset(8U,8U);
    assert(cpc_video_put_cell(&v,9U,8U,'Q',glyph,NULL));
    save();
    assert(cpc_video_render_row(&v,84U,rgb_before,320U));
    assert(seq("\x1b[C")==UART_LINE_NAV_RIGHT);
    assert(cpc_video_render_row(&v,84U,rgb_after,320U));
    assert(memcmp(rgb_before,rgb_after,sizeof rgb_before)!=0);
    same();cell(9U,8U,true,'Q');
    assert(seq("\x1b[D")==UART_LINE_NAV_LEFT);
    assert(cpc_video_render_row(&v,84U,rgb_after,320U));
    assert(memcmp(rgb_before,rgb_after,sizeof rgb_before)==0);
    same();
}
static void scroll(void)
{
    reset(0U,19U);fill();save();
    assert(seq("\x1b[A")==UART_LINE_NAV_UP);
    assert(v.cursor_row==0U&&v.cursor_column==19U);
    assert(memcmp(g.pixels+640U,pixels,CPC_VIDEO_BYTES-640U)==0);
    cell(0U,0U,false,0U);cell(39U,0U,false,0U);
    cell(0U,1U,true,'A');cell(39U,24U,true,'X');
    reset(24U,19U);fill();save();
    assert(seq("\x1b[B")==UART_LINE_NAV_DOWN);
    assert(v.cursor_row==24U&&v.cursor_column==19U);
    assert(memcmp(g.pixels,pixels+640U,CPC_VIDEO_BYTES-640U)==0);
    cell(0U,0U,true,'B');cell(39U,23U,true,'Y');
    cell(0U,24U,false,0U);
    for(unsigned i=0U;i<25U;++i) assert(cpc_video_scroll_down(&v,1U));
    for(unsigned r=0U;r<25U;++r)for(unsigned c=0U;c<40U;++c)
        cell(c,r,false,0U);
    for(unsigned i=0U;i<25U;++i) assert(cpc_video_scroll_up(&v,1U));
    guards();
}
static void invalid_and_paper(void)
{
    for(unsigned p=0U;p<4U;++p) {
        reset(12U,12U);
        assert(cpc_video_set_text_colors(&v,1U,p));
        assert(cpc_video_put_cell(&v,0U,0U,'Q',glyph,NULL));
        save();
        assert(cpc_video_scroll_down(&v,0U));
        same();
        assert(!cpc_video_scroll_down(&v,26U));
        assert(!cpc_video_scroll_down(&v,UINT32_MAX));
        same();
        assert(cpc_video_scroll_down(&v,1U));
        for(size_t i=0U;i<640U;++i)
            assert(g.pixels[i]==(uint8_t)(p*0x55U));
        cell(0U,0U,false,0U);cell(0U,1U,true,'Q');
        assert(cpc_video_scroll_down(&v,25U));
        for(size_t i=0U;i<CPC_VIDEO_BYTES;++i)
            assert(g.pixels[i]==(uint8_t)(p*0x55U));
    }
    assert(cpc_video_set_mode(&v,CPC_MODE_0));
    save();assert(!cpc_video_scroll_down(&v,1U));same();
    assert(cpc_video_set_mode(&v,CPC_MODE_2));
    assert(!cpc_video_scroll_down(&v,1U));
    assert(!cpc_video_scroll_down(NULL,1U));guards();
}
static void e3_and_ansi(void)
{
    reset(8U,0U);
    assert(seq("10 PRNT 2")==UART_LINE_APPEND);
    for(unsigned i=0U;i<4U;++i)assert(seq("\x1b[D")==UART_LINE_LEFT);
    assert(feed('I')==UART_LINE_APPEND);
    assert(memcmp(line.data,"10 PRINT 2",11U)==0);
    save();
    assert(seq("\x1b[A")==UART_LINE_NAV_UP);
    assert(feed('Z')==UART_LINE_IGNORED);
    assert(feed(0x08U)==UART_LINE_IGNORED);
    assert(seq("\x1b[3~")==UART_LINE_IGNORED);
    same();assert(line.cursor_pos==6U);
    assert(feed('\r')==UART_LINE_RETURN_EDIT);
    assert(feed('\n')==UART_LINE_NONE);
    assert(!line.ready && !line.screen_navigation);
    assert(feed('\r')==UART_LINE_READY);
    assert(memcmp(line.data,"10 PRINT 2",11U)==0);
    uart_line_ack(&line);
    reset(7U,10U);
    assert(seq("LIST")==UART_LINE_APPEND);
    assert(seq("\x1b[A")==UART_LINE_NAV_UP);
    save();
    assert(feed(0x1bU)==UART_LINE_IGNORED);
    assert(feed('[')==UART_LINE_IGNORED);
    assert(feed('3')==UART_LINE_IGNORED);
    assert(feed('\r')==UART_LINE_IGNORED);
    assert(feed('\n')==UART_LINE_NONE);same();
    assert(!line.ready && line.screen_navigation);
    assert(seq("\x1b[1;2A")==UART_LINE_IGNORED);
    assert(seq("\x1b[?25l")==UART_LINE_IGNORED);
    assert(seq("\x1b[3~")==UART_LINE_IGNORED);
    assert(seq("\x1b[H")==UART_LINE_RETURN_EDIT);
    assert(feed(0x1bU)==UART_LINE_IGNORED);
    assert(feed('[')==UART_LINE_IGNORED);
    assert(feed('3')==UART_LINE_IGNORED);
    assert(feed('\r')==UART_LINE_REJECTED);
    uart_line_ack(&line);
    reset(8U,0U);
    for(unsigned i=0U;i<120U;++i)assert(feed('A')==UART_LINE_APPEND);
    save();
    assert(feed('X')==UART_LINE_OVERFLOW);
    assert(seq("\x1b[A")==UART_LINE_IGNORED);
    assert(!line.screen_navigation);
    assert(feed('\n')==UART_LINE_REJECTED);
    assert(memcmp(source,line.data,sizeof source)==0);
    uart_line_ack(&line);guards();
}
static void expelled_e3(void)
{
    reset(0U,0U);
    assert(seq("10 PRINT 2")==UART_LINE_APPEND);
    assert(cpc_video_cursor(&v,0U,24U,true));
    assert(seq("\x1b[B")==UART_LINE_NAV_DOWN);
    assert(!nav.anchor_valid);
    assert(memcmp(line.data,"10 PRINT 2",11U)==0);
    assert(feed('\r')==UART_LINE_RETURN_EDIT);
    assert(nav.anchor_valid&&!line.ready);
    cell(edit.column,edit.row,true,'1');
    assert(feed('\r')==UART_LINE_READY);
    uart_line_ack(&line);guards();
}
int main(void)
{
    arrows();overlay();scroll();invalid_and_paper();e3_and_ansi();
    expelled_e3();
    puts("HW4-EDIT-B1-A E1/E2/E3 destructive navigation PASS");
    return 0;
}
