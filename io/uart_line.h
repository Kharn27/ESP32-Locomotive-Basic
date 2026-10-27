/* HW4-C2 portable UART0 line collector: never allocates, owns its bytes. */
#ifndef LOCO_UART_LINE_H
#define LOCO_UART_LINE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define UART_LINE_CAPACITY 120U
typedef enum {
    UART_LINE_NONE = 0,
    UART_LINE_APPEND,
    UART_LINE_DELETE,
    UART_LINE_READY,
    UART_LINE_REJECTED,
    UART_LINE_IGNORED,
    UART_LINE_OVERFLOW
} UartLineEvent;
typedef struct {
    uint8_t data[UART_LINE_CAPACITY + 1U];
    size_t length;
    bool poisoned;
    bool ready;
    bool last_cr;
    size_t rejected_lines;
    size_t nonascii_bytes;
} UartLine;
/* Input is arbitrary binary. ASCII 0x20..0x7e accepted; CR, LF and CRLF
 * commit one line. BS/DEL delete one editable byte. No cursor controls.
 * On overflow the WHOLE line is poisoned, never passed to BASIC, even if
 * edited shorter afterwards. Caller must invoke uart_line_ack() after
 * READY or REJECTED, before the next byte (including trailing CRLF LF).
 * The NUL sentinel is for diagnostics, not part of submitted source. */
void uart_line_init(UartLine *line);
UartLineEvent uart_line_feed(UartLine *line, uint8_t ch);
void uart_line_ack(UartLine *line);
#endif
