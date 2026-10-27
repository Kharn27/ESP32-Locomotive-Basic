/* HW4-C2 portable serial intake unit tests, guard regions + 100 lines. */
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
    memset(&guard, 0, sizeof(guard));
    memset(guard.left, 0xa5, sizeof(guard.left));
    memset(guard.right, 0x5a, sizeof(guard.right));
    uart_line_init(&guard.line);
}
static void guarded(void)
{
    for (size_t i=0; i<sizeof(guard.left); ++i) {
        assert(guard.left[i] == 0xa5U);
        assert(guard.right[i] == 0x5aU);
    }
}
static UartLineEvent feed_string(const char *s)
{
    UartLineEvent e = UART_LINE_NONE;
    for (size_t i=0; s[i]!='\0'; ++i) e = uart_line_feed(&guard.line,(uint8_t)s[i]);
    return e;
}
static void basic(void)
{
    reset();
    assert(feed_string("10 A%=3") == UART_LINE_APPEND);
    assert(guard.line.length == 7U);
    assert(uart_line_feed(&guard.line,'\r') == UART_LINE_READY);
    assert(memcmp(guard.line.data, "10 A%=3",7U)==0);
    assert(uart_line_feed(&guard.line,'X')==UART_LINE_IGNORED);
    uart_line_ack(&guard.line);
    assert(uart_line_feed(&guard.line,'\n')==UART_LINE_NONE);
    assert(guard.line.length==0U);
    assert(feed_string("LIST\n")==UART_LINE_READY);
    assert(memcmp(guard.line.data,"LIST",4U)==0);
    uart_line_ack(&guard.line);
    assert(uart_line_feed(&guard.line,'\r')==UART_LINE_READY); /* empty */
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
    assert(uart_line_feed(&guard.line,0x1bU)==UART_LINE_IGNORED);
    assert(uart_line_feed(&guard.line,0xffU)==UART_LINE_IGNORED);
    assert(guard.line.nonascii_bytes==2U && guard.line.length==0U);
    assert(uart_line_feed(&guard.line,'!')==UART_LINE_APPEND);
    guarded();
}
static void overflow(void)
{
    reset();
    for(size_t i=0; i<UART_LINE_CAPACITY; ++i)
        assert(uart_line_feed(&guard.line,'P')==UART_LINE_APPEND);
    assert(guard.line.length==UART_LINE_CAPACITY);
    assert(guard.line.data[UART_LINE_CAPACITY]==0U);
    assert(uart_line_feed(&guard.line,'X')==UART_LINE_OVERFLOW);
    assert(uart_line_feed(&guard.line,'Y')==UART_LINE_IGNORED);
    assert(uart_line_feed(&guard.line,0x08U)==UART_LINE_DELETE);
    assert(guard.line.poisoned);
    assert(uart_line_feed(&guard.line,'\n')==UART_LINE_REJECTED);
    assert(guard.line.rejected_lines==1U);
    uart_line_ack(&guard.line);
    assert(!guard.line.poisoned && guard.line.length==0U);
    assert(feed_string("NEW\r\n")==UART_LINE_NONE);
    /* The CR produced READY before the trailing LF; explicit feed exercise. */
    reset();
    assert(feed_string("NEW\r")==UART_LINE_READY);
    uart_line_ack(&guard.line);
    assert(uart_line_feed(&guard.line,'\n')==UART_LINE_NONE);
    guarded();
}
static void hundred_lines(void)
{
    reset();
    for(size_t i=0; i<100U; ++i) {
        assert(feed_string("20 PRINT 2\r")==UART_LINE_READY);
        assert(guard.line.length==10U);
        uart_line_ack(&guard.line);
        assert(uart_line_feed(&guard.line,'\n')==UART_LINE_NONE);
    }
    guarded();
}
int main(void) {
    basic(); editing(); overflow(); hundred_lines();
    puts("HW4-C2 UART line editing PASS");
    return 0;
}
