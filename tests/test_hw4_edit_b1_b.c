/* HW4-EDIT-B1-B: U04 partial PO observation, not a complete CPC oracle.
 * The real portable console router, E1/E2/VRAM and native BASIC are exercised. */
#include "cpc_screen_nav.h"
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint8_t before[16], vram[CPC_VIDEO_BYTES], after[16];
} GuardedVram;
static GuardedVram guard;
static CpcVideo video;
static CpcText text;
static CpcUartEditor edit;
static CpcScreenNavigation nav;
static UartLine line;
static uint8_t program_canary[32];
static struct {
    BasicProgram program;
    BasicVariableStore variables;
    BasicSessionRuntime runtime;
    uint8_t bytes[8192], temporary[2048], output[4096];
    BasicVariableEntry entries[64];
    size_t written;
} basic;
typedef struct {
    GuardedVram screen;
    CpcVideo video;
    CpcText text;
    CpcUartEditor edit;
    CpcScreenNavigation nav;
    UartLine line;
    uint8_t program[sizeof program_canary];
} Snapshot;
static Snapshot before;

static void check_guards(void)
{
    for(size_t i=0U;i<16U;++i)
        assert(guard.before[i]==0xa5U && guard.after[i]==0x5aU);
    for(size_t i=0U;i<sizeof program_canary;++i)
        assert(program_canary[i]==0x96U);
    assert(line.length<=UART_LINE_CAPACITY && line.cursor_pos<=line.length);
    assert(line.data[line.length]==0U);
}
static uint8_t glyph(void *context,uint8_t ch,unsigned row)
{
    (void)context;
    return ch==' ' ? 0U : (uint8_t)((row&1U)!=0U ? 0xf0U : 0x0fU);
}
static void reset(unsigned row,unsigned col)
{
    memset(&guard,0,sizeof guard);
    memset(guard.before,0xa5U,sizeof guard.before);
    memset(guard.after,0x5aU,sizeof guard.after);
    memset(program_canary,0x96U,sizeof program_canary);
    assert(row<25U && col<40U);
    assert(cpc_video_init(&video,guard.vram,CPC_VIDEO_BYTES,CPC_MODE_1));
    assert(cpc_video_set_ink(&video,0U,1U));
    assert(cpc_video_set_ink(&video,1U,24U));
    assert(cpc_video_set_text_colors(&video,1U,0U));
    assert(cpc_text_init(&text,&video,glyph,NULL));
    text.row=row;
    text.column=col;
    assert(cpc_video_cursor(&video,col,row,true));
    uart_line_init(&line);
    assert(cpc_uart_console_edit_begin(&text,&edit));
    cpc_screen_nav_init(&nav);
    check_guards();
}
static UartLineEvent key(uint8_t ch)
{
    UartLineEvent event=uart_line_feed_screen(&line,ch);
    if(event==UART_LINE_NAV_LEFT || event==UART_LINE_NAV_RIGHT ||
       event==UART_LINE_NAV_UP || event==UART_LINE_NAV_DOWN)
        assert(cpc_screen_nav_move(&nav,&text,&edit,&line,event));
    else if(event==UART_LINE_RETURN_EDIT)
        assert(cpc_screen_nav_resume(&nav,&text,&edit,&line));
    else if(event==UART_LINE_RETURN_HOME)
        assert(cpc_screen_nav_home(&nav,&text,&edit,&line));
    else if(event==UART_LINE_APPEND || event==UART_LINE_DELETE ||
            event==UART_LINE_DELETE_FORWARD || event==UART_LINE_LEFT ||
            event==UART_LINE_RIGHT) {
        size_t changed=event==UART_LINE_APPEND ? line.cursor_pos-1U :
                       (event==UART_LINE_DELETE ||
                        event==UART_LINE_DELETE_FORWARD) ?
                       line.cursor_pos : line.length;
        assert(cpc_uart_console_edit(&text,&edit,&line,changed));
    }
    check_guards();
    return event;
}
static UartLineEvent seq(const char *input)
{
    UartLineEvent event=UART_LINE_NONE;
    for(size_t i=0U;input[i]!='\0';++i) event=key((uint8_t)input[i]);
    return event;
}
static void capture(void)
{
    memcpy(&before.screen,&guard,sizeof guard);
    memcpy(&before.video,&video,sizeof video);
    memcpy(&before.text,&text,sizeof text);
    memcpy(&before.edit,&edit,sizeof edit);
    memcpy(&before.nav,&nav,sizeof nav);
    memcpy(&before.line,&line,sizeof line);
    memcpy(before.program,program_canary,sizeof program_canary);
}
static void unchanged_visual_source(void)
{
    assert(memcmp(&guard,&before.screen,sizeof guard)==0);
    assert(memcmp(&video,&before.video,sizeof video)==0);
    assert(memcmp(&text,&before.text,sizeof text)==0);
    assert(memcmp(&edit,&before.edit,sizeof edit)==0);
    assert(memcmp(&nav,&before.nav,sizeof nav)==0);
    assert(memcmp(line.data,before.line.data,sizeof line.data)==0);
    assert(line.length==before.line.length);
    assert(line.cursor_pos==before.line.cursor_pos);
    assert(line.ready==before.line.ready);
    assert(line.poisoned==before.line.poisoned);
    assert(line.screen_navigation==before.line.screen_navigation);
    assert(memcmp(program_canary,before.program,sizeof program_canary)==0);
    check_guards();
}
static void blocked(uint8_t direction)
{
    /* CSI is fragmented on purpose; no premature event or byte leakage. */
    assert(key(0x1bU)==UART_LINE_IGNORED);
    assert(key('[')==UART_LINE_IGNORED);
    assert(key(direction)==UART_LINE_NAV_BLOCKED);
    assert(line.ansi==UART_ANSI_TEXT);
    unchanged_visual_source();
    /* A fully consumed blocked CSI restores the entire line state. */
    assert(memcmp(&line,&before.line,sizeof line)==0);
}
static void blocked_case(const char *source,size_t wanted_cursor)
{
    reset(9U,4U);
    assert(seq(source)==UART_LINE_APPEND);
    assert(line.length==strlen(source));
    while(line.cursor_pos>wanted_cursor)
        assert(seq("\x1b[D")==UART_LINE_LEFT);
    assert(!line.screen_navigation);
    capture();
    for(unsigned repeat=0U;repeat<8U;++repeat) {
        blocked('A');
        blocked('B');
    }
    /* Parameterized / unknown / oversized CSI still never enter E3. */
    assert(seq("\x1b[1;2A")==UART_LINE_IGNORED);
    assert(seq("\x1b[?25l")==UART_LINE_IGNORED);
    assert(seq("\x1b[2~")==UART_LINE_IGNORED);
    unchanged_visual_source();
    /* Delete-under intentionally remains an E3 edit: not a B1-B refusal. */
    if(wanted_cursor<line.length)
        assert(seq("\x1b[3~")==UART_LINE_DELETE_FORWARD);
    else
        assert(seq("\x1b[3~")==UART_LINE_NONE);
    check_guards();
}
static void hundred_and_twenty(void)
{
    char full[UART_LINE_CAPACITY+1U];
    memset(full,'X',UART_LINE_CAPACITY);
    full[UART_LINE_CAPACITY]='\0';
    reset(10U,0U);
    assert(seq(full)==UART_LINE_APPEND);
    for(unsigned i=0U;i<60U;++i) assert(seq("\x1b[D")==UART_LINE_LEFT);
    capture();
    blocked('A');
    blocked('B');
    assert(seq("\x1b[12345678901234567890A")==UART_LINE_IGNORED);
    unchanged_visual_source();
    assert(line.length==120U && line.data[120U]==0U);
    assert(key('Y')==UART_LINE_OVERFLOW);
    assert(line.poisoned && key(0x1bU)==UART_LINE_IGNORED);
    assert(key('[')==UART_LINE_IGNORED);
    assert(key('A')==UART_LINE_IGNORED);
    assert(key('\r')==UART_LINE_REJECTED);
    uart_line_ack(&line);
    check_guards();
}
static void empty_and_e1(void)
{
    reset(12U,4U);
    assert(seq("\x1b[A")==UART_LINE_NAV_UP);
    assert(video.cursor_row==11U);
    assert(seq("\x1b[B")==UART_LINE_NAV_DOWN);
    assert(video.cursor_row==12U);
    assert(seq("\x1b[H")==UART_LINE_RETURN_HOME);
    assert(!line.screen_navigation);
    assert(seq("10")==UART_LINE_APPEND);
    assert(seq("\x1b[A")==UART_LINE_NAV_BLOCKED);
    assert(key(0x08U)==UART_LINE_DELETE);
    assert(key(0x7fU)==UART_LINE_DELETE);
    assert(line.length==0U && line.data[0]==0U);
    assert(seq("\x1b[A")==UART_LINE_NAV_UP);
    assert(seq("\x1b[B")==UART_LINE_NAV_DOWN);
    assert(seq("\x1b[H")==UART_LINE_RETURN_HOME);
    assert(seq("10")==UART_LINE_APPEND);
    /* Legitimate host trajectory into E1 even with E3 occupied: exceeding
     * the right boundary. This combination is CPC_UNVERIFIED, unchanged. */
    assert(seq("\x1b[C")==UART_LINE_NAV_RIGHT);
    assert(line.screen_navigation && line.length==2U);
    assert(seq("\x1b[A")==UART_LINE_NAV_UP);
    assert(seq("\x1b[B")==UART_LINE_NAV_DOWN);
    assert(seq("\x1b[H")==UART_LINE_RETURN_HOME);
    assert(!line.screen_navigation && line.length==2U);
    assert(key('\r')==UART_LINE_READY); /* E3 Enter submits in one press */
    uart_line_ack(&line);
    assert(key('\n')==UART_LINE_NONE);  /* trailing CRLF never double submits */
}
static void c1_and_native_basic(void)
{
    reset(8U,0U);
    assert(seq("10 PRINT 2")==UART_LINE_APPEND);
    capture();
    blocked('A');
    blocked('B');
    assert(key('\r')==UART_LINE_READY); /* one Enter from E3 */
    assert(line.length==10U);
    assert(memcmp(line.data,"10 PRINT 2",11U)==0);
    assert(bp_init(&basic.program,basic.bytes,sizeof basic.bytes)==BP_OK);
    assert(bvs_init(&basic.variables,basic.entries,64U)==BVS_OK);
    assert(bsr_init_with_store(&basic.runtime,&basic.program,
                               &basic.variables).status==BSR_OK);
    BSRResult r=bsr_submit(&basic.runtime,line.data,line.length,
                           basic.temporary,sizeof basic.temporary,
                           basic.output,sizeof basic.output,&basic.written);
    assert(r.status==BSR_OK);
    uart_line_ack(&line);
    const uint8_t list[]="LIST",run[]="RUN";
    r=bsr_submit(&basic.runtime,list,sizeof list-1U,
                 basic.temporary,sizeof basic.temporary,
                 basic.output,sizeof basic.output,&basic.written);
    assert(r.status==BSR_OK && basic.written==11U);
    assert(memcmp(basic.output,"10 PRINT 2\n",11U)==0);
    r=bsr_submit(&basic.runtime,run,sizeof run-1U,
                 basic.temporary,sizeof basic.temporary,
                 basic.output,sizeof basic.output,&basic.written);
    assert(r.status==BSR_OK);
    r=bsr_step(&basic.runtime,basic.output,sizeof basic.output,&basic.written);
    assert(r.status==BSR_OK && r.executor_status==BE_OK);
    assert(basic.written==2U && memcmp(basic.output,"2\n",2U)==0);
    r=bsr_step(&basic.runtime,basic.output,sizeof basic.output,&basic.written);
    assert(r.status==BSR_END);
    check_guards();
    /* C1: E1 Enter is NOT BASIC submit and HOME is NOT Enter. */
    reset(6U,3U);
    assert(seq("\x1b[A")==UART_LINE_NAV_UP);
    assert(seq("\x1b[H")==UART_LINE_RETURN_HOME);
    assert(!line.ready);
    assert(seq("\x1b[A")==UART_LINE_NAV_UP);
    assert(key('\r')==UART_LINE_RETURN_EDIT);
    assert(!line.ready && !line.screen_navigation);
    assert(key('\n')==UART_LINE_NONE);
    assert(key('\r')==UART_LINE_READY);
}
int main(void)
{
    blocked_case("10",2U);
    blocked_case("10 PRINT 2",5U);
    hundred_and_twenty();
    empty_and_e1();
    c1_and_native_basic();
    puts("HW4-EDIT-B1-B U04 nonempty blocked / E1-E2-E3 / LIST RUN PASS");
    return 0;
}
