/* HW4-C2-C1 minimal, bounded ANSI CSI intake, no heap and no echo. */
#include "uart_line.h"
#include <string.h>

void uart_line_init(UartLine *line)
{
    if (line != NULL) memset(line, 0, sizeof(*line));
}

static UartLineEvent erase_character(UartLine *line)
{
    if (line->length == 0U) return UART_LINE_NONE;
    line->data[--line->length] = 0U;
    return UART_LINE_DELETE;
}

static void ansi_clear(UartLine *line)
{
    line->ansi = UART_ANSI_TEXT;
    line->csi_length = 0U;
    line->csi_first = 0U;
}

UartLineEvent uart_line_feed(UartLine *line, uint8_t ch)
{
    if (line == NULL || line->ready) return UART_LINE_IGNORED;

    if (line->last_cr && ch == (uint8_t)'\n') {
        line->last_cr = false;
        return UART_LINE_NONE; /* CRLF generates exactly one line */
    }
    line->last_cr = false;

    /* A fragmented ESC/CSI is not an instruction; newline must reject
     * the incomplete edited line, not accidentally commit a BASIC edit. */
    if (ch == (uint8_t)'\r' || ch == (uint8_t)'\n') {
        line->last_cr = ch == (uint8_t)'\r';
        line->rejected_ansi_incomplete = line->ansi != UART_ANSI_TEXT;
        if (line->rejected_ansi_incomplete) {
            ++line->ansi_incomplete_rejected;
            line->poisoned = true;
        }
        ansi_clear(line);
        line->ready = true;
        if (line->poisoned) {
            ++line->rejected_lines;
            return UART_LINE_REJECTED;
        }
        return UART_LINE_READY;
    }

    /* Escape parser always precedes ASCII handling. No ANSI byte can enter
     * the source and cause a corresponding drawing operation. */
    if (ch == 0x1bU) {
        if (line->ansi != UART_ANSI_TEXT) ++line->ansi_sequences_ignored;
        line->ansi = UART_ANSI_ESC;
        line->csi_length = 0U;
        line->csi_first = 0U;
        return UART_LINE_IGNORED;
    }
    if (line->ansi == UART_ANSI_ESC) {
        if (ch == (uint8_t)'[') {
            line->ansi = UART_ANSI_CSI;
        } else {
            ++line->ansi_sequences_ignored; /* ESC + one unknown final */
            ansi_clear(line);
        }
        return UART_LINE_IGNORED;
    }
    if (line->ansi == UART_ANSI_CSI ||
        line->ansi == UART_ANSI_CSI_DISCARD) {
        /* ANSI CSI parameters/intermediates are 0x20..0x3f; the
         * final byte is 0x40..0x7e. Other bytes are ignored in place. */
        if (ch >= 0x40U && ch <= 0x7eU) {
            const bool is_delete =
                line->ansi == UART_ANSI_CSI &&
                ch == (uint8_t)'~' &&
                line->csi_length == 1U &&
                line->csi_first == (uint8_t)'3';
            ansi_clear(line);
            if (is_delete) {
                ++line->ansi_sequences_deleted;
                return erase_character(line); /* end-of-line only */
            }
            ++line->ansi_sequences_ignored;
            return UART_LINE_IGNORED;
        }
        if (ch >= 0x20U && ch <= 0x3fU &&
            line->ansi == UART_ANSI_CSI) {
            if (line->csi_length == 0U) line->csi_first = ch;
            if (line->csi_length < UART_CSI_MAX_BYTES)
                ++line->csi_length;
            else
                line->ansi = UART_ANSI_CSI_DISCARD;
        }
        return UART_LINE_IGNORED;
    }

    if (ch == 0x08U || ch == 0x7fU) return erase_character(line);
    if (ch < 0x20U || ch > 0x7eU) {
        ++line->nonascii_bytes;
        return UART_LINE_IGNORED;
    }
    if (line->poisoned) return UART_LINE_IGNORED;
    if (line->length >= UART_LINE_CAPACITY) {
        line->poisoned = true; /* cannot be undone by later delete */
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
    line->rejected_ansi_incomplete = false;
    ansi_clear(line);
    /* Retain last_cr to swallow at most one following LF. */
}
