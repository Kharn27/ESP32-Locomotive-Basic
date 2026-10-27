/* HW4-C2 bounded portable serial line editor; C99, no dynamic memory. */
#include "uart_line.h"
#include <string.h>
void uart_line_init(UartLine *line)
{
    if (line != NULL) memset(line, 0, sizeof(*line));
}
UartLineEvent uart_line_feed(UartLine *line, uint8_t ch)
{
    if (line == NULL || line->ready) return UART_LINE_IGNORED;
    if (line->last_cr && ch == (uint8_t)'\n') {
        line->last_cr = false;
        return UART_LINE_NONE; /* CRLF has exactly one submit */
    }
    line->last_cr = false;
    if (ch == (uint8_t)'\r' || ch == (uint8_t)'\n') {
        line->last_cr = ch == (uint8_t)'\r';
        line->ready = true;
        if (line->poisoned) {
            ++line->rejected_lines;
            return UART_LINE_REJECTED;
        }
        return UART_LINE_READY;
    }
    if (ch == 0x08U || ch == 0x7fU) {
        if (line->length == 0U) return UART_LINE_NONE;
        line->data[--line->length] = 0U;
        return UART_LINE_DELETE;
    }
    if (ch < 0x20U || ch > 0x7eU) {
        ++line->nonascii_bytes;
        return UART_LINE_IGNORED;
    }
    if (line->poisoned) return UART_LINE_IGNORED;
    if (line->length >= UART_LINE_CAPACITY) {
        line->poisoned = true;
        return UART_LINE_OVERFLOW;
    }
    line->data[line->length++] = ch;
    line->data[line->length] = 0U;
    return UART_LINE_APPEND;
}
void uart_line_ack(UartLine *line)
{
    if (line == NULL || !line->ready) return;
    line->length = 0U;
    line->data[0] = 0U;
    line->poisoned = false;
    line->ready = false;
    /* Retain last_cr to swallow exactly one following LF. */
}
