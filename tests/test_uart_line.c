/* HW4-C2-C1 end-to-end byte editing, ANSI CSI, 100 lines, canaries. */
#include "uart_line.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint8_t left[13];
    UartLine line;
    uint8_t right[13];
} Guard;
static Guard guard;

static void reset(void)
{
    memset(&guard,0,sizeof(guard));
    memset(guard.left,0xa5,sizeof(guard.left));
    memset(guard.right,0x5a,sizeof(guard.right));
    uart_line_init(&guard.line);
}
static void guarded(void)
{
    for(size_t i=0;i<sizeof(guard.left);++i) {
        assert(guard.left[i]==0xa5U);
        assert(guard.right[i]==0x5aU);
    }
    assert(guard.line.length<=UART_LINE_CAPACITY);
    assert(guard.line.cursor_pos<=guard.line.length);
    assert(guard.line.data[guard.line.length]==0U);
}
static UartLineEvent feed_string(const char *s)
{
    UartLineEvent e=UART_LINE_NONE;
    for(size_t i=0;s[i]!='\0';++i) e=uart_line_feed(&guard.line,(uint8_t)s[i]);
    return e;
}
static void basic(void)
{
    reset();
    assert(feed_string("10 A%=3")==UART_LINE_APPEND);
    assert(guard.line.length==7U);
    assert(uart_line_feed(&guard.line,'\r')==UART_LINE_READY);
    assert(memcmp(guard.line.data,"10 A%=3",7U)==0);
    assert(uart_line_feed(&guard.line,'X')==UART_LINE_IGNORED);
    uart_line_ack(&guard.line);
    assert(uart_line_feed(&guard.line,'\n')==UART_LINE_NONE);
    assert(guard.line.length==0U);
    assert(feed_string("LIST\n")==UART_LINE_READY);
    assert(memcmp(guard.line.data,"LIST",4U)==0);
    uart_line_ack(&guard.line);
    assert(uart_line_feed(&guard.line,'\r')==UART_LINE_READY);
    assert(guard.line.length==0U);
    uart_line_ack(&guard.line);
    assert(uart_line_feed(&guard.line,'\n')==UART_LINE_NONE);
    guarded();
}
static void editing(void)
{
    reset();
    assert(feed_string("ABC")==UART_LINE_APPEND);
    assert(uart_line_feed(&guard.line,0x08U)==UART_LINE_DELETE);
    assert(uart_line_feed(&guard.line,0x7fU)==UART_LINE_DELETE);
    assert(guard.line.length==1U && guard.line.data[0]=='A');
    assert(uart_line_feed(&guard.line,0x7fU)==UART_LINE_DELETE);
    assert(uart_line_feed(&guard.line,0x7fU)==UART_LINE_NONE);
    assert(uart_line_feed(&guard.line,0xffU)==UART_LINE_IGNORED);
    assert(guard.line.nonascii_bytes==1U);
    assert(uart_line_feed(&guard.line,'!')==UART_LINE_APPEND);
    guarded();
}
static void ansi_delete(void)
{
    reset();
    assert(feed_string("ABCD")==UART_LINE_APPEND);
    assert(guard.line.cursor_pos==4U);
    /* Delete at end is a no-op, unlike Backspace. */
    assert(feed_string("\x1b[3~")==UART_LINE_NONE);
    assert(guard.line.length==4U);
    assert(feed_string("\x1b[D")==UART_LINE_LEFT);
    assert(guard.line.cursor_pos==3U);
    assert(feed_string("\x1b[3~")==UART_LINE_DELETE_FORWARD);
    assert(guard.line.cursor_pos==3U && guard.line.length==3U);
    assert(memcmp(guard.line.data,"ABC",4U)==0);
    assert(feed_string("\x1b[D")==UART_LINE_LEFT);
    assert(uart_line_feed(&guard.line,0x08U)==UART_LINE_DELETE);
    assert(guard.line.cursor_pos==1U && guard.line.length==2U);
    assert(memcmp(guard.line.data,"AC",3U)==0);
    assert(feed_string("\x1b[C")==UART_LINE_RIGHT);
    assert(guard.line.cursor_pos==2U);
    assert(feed_string("\x1b[C")==UART_LINE_NONE);
    assert(guard.line.ansi_sequences_deleted==2U);
    guarded();
}
static void insert_mid_and_boundaries(void)
{
    reset();
    assert(feed_string("10 PRNT 2")==UART_LINE_APPEND);
    for(unsigned i=0U;i<4U;++i)
        assert(feed_string("\x1b[D")==UART_LINE_LEFT);
    assert(guard.line.cursor_pos==5U);
    assert(uart_line_feed(&guard.line,'I')==UART_LINE_APPEND);
    assert(guard.line.length==10U && guard.line.cursor_pos==6U);
    assert(memcmp(guard.line.data,"10 PRINT 2",11U)==0);
    for(unsigned i=0U;i<6U;++i)
        assert(feed_string("\x1b[D")==UART_LINE_LEFT);
    assert(feed_string("\x1b[D")==UART_LINE_NONE);
    assert(uart_line_feed(&guard.line,0x7fU)==UART_LINE_NONE);
    assert(guard.line.cursor_pos==0U && guard.line.length==10U);
    assert(uart_line_feed(&guard.line,'!')==UART_LINE_APPEND);
    assert(memcmp(guard.line.data,"!10 PRINT 2",12U)==0);
    for(unsigned i=0U;i<11U;++i)
        assert(feed_string("\x1b[C")==UART_LINE_RIGHT);
    assert(feed_string("\x1b[C")==UART_LINE_NONE);
    guarded();
}
static void ansi_ignored(void)
{
    reset();
    assert(feed_string("PRINT")==UART_LINE_APPEND);
    const char *seq[]={"\x1b[A","\x1b[3;1~","\x1b[?25l",
                       "\x1b[0m","\x1b[1;2H","\x1b[4~"};
    for(size_t i=0;i<sizeof(seq)/sizeof(seq[0]);++i) {
        assert(feed_string(seq[i])==UART_LINE_IGNORED);
        assert(guard.line.length==5U);
        assert(memcmp(guard.line.data,"PRINT",5U)==0);
    }
    assert(guard.line.ansi_sequences_ignored==6U);
    assert(uart_line_feed(&guard.line,' ') ==UART_LINE_APPEND);
    assert(uart_line_feed(&guard.line,'2')==UART_LINE_APPEND);
    assert(guard.line.length==7U);
    assert(memcmp(guard.line.data,"PRINT 2",7U)==0);
    guarded();
}
static void fragmented_and_incomplete(void)
{
    reset();
    assert(feed_string("10 PRINT")==UART_LINE_APPEND);
    assert(uart_line_feed(&guard.line,0x1bU)==UART_LINE_IGNORED);
    assert(uart_line_feed(&guard.line,'[')==UART_LINE_IGNORED);
    assert(uart_line_feed(&guard.line,'3')==UART_LINE_IGNORED);
    assert(guard.line.length==8U);
    assert(uart_line_feed(&guard.line,'\r')==UART_LINE_REJECTED);
    assert(guard.line.ansi_incomplete_rejected==1U && guard.line.poisoned);
    assert(guard.line.length==8U);
    uart_line_ack(&guard.line);
    assert(uart_line_feed(&guard.line,'\n')==UART_LINE_NONE);
    assert(guard.line.length==0U && guard.line.ansi==UART_ANSI_TEXT);
    assert(feed_string("LIST\x1b")==UART_LINE_IGNORED);
    assert(uart_line_feed(&guard.line,'\n')==UART_LINE_REJECTED);
    assert(guard.line.ansi_incomplete_rejected==2U);
    uart_line_ack(&guard.line);
    guarded();
}
static void bounded_malformed(void)
{
    reset();
    assert(feed_string("RUN")==UART_LINE_APPEND);
    assert(feed_string("\x1b[")==UART_LINE_IGNORED);
    for(size_t i=0;i<UART_CSI_MAX_BYTES+101U;++i)
        assert(uart_line_feed(&guard.line,'3')==UART_LINE_IGNORED);
    assert(guard.line.ansi==UART_ANSI_CSI_DISCARD);
    assert(uart_line_feed(&guard.line,'~')==UART_LINE_IGNORED);
    assert(guard.line.length==3U && memcmp(guard.line.data,"RUN",3U)==0);
    assert(feed_string("\x1b[?500;30m")==UART_LINE_IGNORED);
    assert(feed_string("\x1b" "X")==UART_LINE_IGNORED);
    assert(guard.line.length==3U);
    assert(uart_line_feed(&guard.line,'\n')==UART_LINE_READY);
    uart_line_ack(&guard.line);
    guarded();
}
static void overflow(void)
{
    reset();
    for(size_t i=0;i<UART_LINE_CAPACITY;++i)
        assert(uart_line_feed(&guard.line,'P')==UART_LINE_APPEND);
    assert(guard.line.length==UART_LINE_CAPACITY);
    assert(guard.line.data[UART_LINE_CAPACITY]==0U);
    assert(uart_line_feed(&guard.line,'X')==UART_LINE_OVERFLOW);
    assert(feed_string("\x1b[3~")==UART_LINE_NONE);
    assert(guard.line.poisoned);
    assert(uart_line_feed(&guard.line,'\n')==UART_LINE_REJECTED);
    uart_line_ack(&guard.line);
    assert(!guard.line.poisoned && guard.line.length==0U);
    guarded();
}
static void hundred_lines(void)
{
    reset();
    for(size_t i=0;i<100U;++i) {
        assert(feed_string("20 PRINT 2\r")==UART_LINE_READY);
        assert(guard.line.length==10U);
        uart_line_ack(&guard.line);
        assert(uart_line_feed(&guard.line,'\n')==UART_LINE_NONE);
    }
    guarded();
}
int main(void)
{
    basic(); editing(); ansi_delete(); insert_mid_and_boundaries(); ansi_ignored();
    fragmented_and_incomplete(); bounded_malformed(); overflow();
    hundred_lines();
    puts("HW4-C2-C1 UART ANSI CSI line editing PASS");
    return 0;
}
