/* HW4-EDIT-A: 120-byte in-place ASCII editor; minimal bounded CSI. MIT. */
#include "uart_line.h"
#include <string.h>

void uart_line_init(UartLine *line)
{
    if (line != NULL) memset(line, 0, sizeof(*line));
}

static UartLineEvent erase_before(UartLine *line)
{
    if (line->cursor_pos == 0U || line->poisoned) return UART_LINE_NONE;
    const size_t at = --line->cursor_pos;
    /* Copy the following suffix INCLUDING the NUL terminator. */
    memmove(line->data + at, line->data + at + 1U, line->length - at);
    --line->length;
    return UART_LINE_DELETE;
}

static UartLineEvent erase_under(UartLine *line)
{
    if (line->cursor_pos == line->length || line->poisoned)
        return UART_LINE_NONE;
    const size_t at = line->cursor_pos;
    memmove(line->data + at, line->data + at + 1U, line->length - at);
    --line->length;
    return UART_LINE_DELETE_FORWARD;
}

static void ansi_clear(UartLine *line)
{
    line->ansi = UART_ANSI_TEXT;
    line->csi_length = 0U;
    line->csi_first = 0U;
}

static UartLineEvent feed_impl(UartLine *line, uint8_t ch, bool screen_enabled)
{
    if (line == NULL || line->ready) return UART_LINE_IGNORED;
    if (line->last_cr && ch == (uint8_t)'\n') {
        line->last_cr = false;
        return UART_LINE_NONE;
    }
    line->last_cr = false;

    /* ENTER outside E3 only refocuses; never submits the older E2 cell.
     * An incomplete CSI is discarded without deleting the pending E3 line. */
    if (screen_enabled && line->screen_navigation &&
        (ch == (uint8_t)'\r' || ch == (uint8_t)'\n')) {
        line->last_cr = ch == (uint8_t)'\r';
        if (line->ansi != UART_ANSI_TEXT) {
            ++line->ansi_incomplete_rejected;
            ++line->ansi_sequences_ignored;
            ansi_clear(line);
            return UART_LINE_IGNORED;
        }
        line->screen_navigation = false;
        return UART_LINE_RETURN_EDIT;
    }

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

    /* Consume all escape bytes before ASCII handling. Unknown CSI never
     * reaches BASIC, even when fragmented or longer than our CSI budget. */
    if (ch == 0x1bU) {
        if (line->ansi != UART_ANSI_TEXT) ++line->ansi_sequences_ignored;
        line->ansi = UART_ANSI_ESC;
        line->csi_length = 0U;
        line->csi_first = 0U;
        return UART_LINE_IGNORED;
    }
    if (line->ansi == UART_ANSI_ESC) {
        if (ch == (uint8_t)'[') line->ansi = UART_ANSI_CSI;
        else {
            ++line->ansi_sequences_ignored;
            ansi_clear(line);
        }
        return UART_LINE_IGNORED;
    }
    if (line->ansi == UART_ANSI_CSI || line->ansi == UART_ANSI_CSI_DISCARD) {
        if (ch >= 0x40U && ch <= 0x7eU) {
            /* No parameters for arrows; precisely one '3' for DELETE.
             * Parameterised CSI and oversized CSI are always ignored. */
            const bool simple = line->ansi == UART_ANSI_CSI;
            const uint8_t n = line->csi_length;
            const uint8_t first = line->csi_first;
            ansi_clear(line);
            if (simple && n == 0U && screen_enabled && !line->poisoned &&
                (ch == (uint8_t)'A' || ch == (uint8_t)'B')) {
                line->screen_navigation = true;
                return ch == (uint8_t)'A' ? UART_LINE_NAV_UP : UART_LINE_NAV_DOWN;
            }
            if (simple && n == 0U && !line->poisoned &&
                (ch == (uint8_t)'D' || ch == (uint8_t)'C')) {
                const bool left = ch == (uint8_t)'D';
                if (screen_enabled &&
                    (line->screen_navigation ||
                     (left ? line->cursor_pos == 0U :
                             line->cursor_pos == line->length))) {
                    line->screen_navigation = true;
                    return left ? UART_LINE_NAV_LEFT : UART_LINE_NAV_RIGHT;
                }
                if (left) {
                    if (line->cursor_pos == 0U) return UART_LINE_NONE;
                    --line->cursor_pos;
                    return UART_LINE_LEFT;
                }
                if (line->cursor_pos == line->length) return UART_LINE_NONE;
                ++line->cursor_pos;
                return UART_LINE_RIGHT;
            }
            if (simple && n == 0U && ch == (uint8_t)'H' &&
                screen_enabled && line->screen_navigation) {
                line->screen_navigation = false;
                return UART_LINE_RETURN_HOME;
            }
            /* All remaining CSI, especially Delete-under, are inert in
             * SCREEN focus. Never run an E3 edit from a historic cell. */
            if (screen_enabled && line->screen_navigation) {
                ++line->ansi_sequences_ignored;
                return UART_LINE_IGNORED;
            }
            if (simple && n == 1U && first == (uint8_t)'3' &&
                ch == (uint8_t)'~') {
                ++line->ansi_sequences_deleted;
                return erase_under(line);
            }
            ++line->ansi_sequences_ignored;
            return UART_LINE_IGNORED;
        }
        if (ch >= 0x20U && ch <= 0x3fU && line->ansi == UART_ANSI_CSI) {
            if (line->csi_length == 0U) line->csi_first = ch;
            if (line->csi_length < UART_CSI_MAX_BYTES)
                ++line->csi_length;
            else line->ansi = UART_ANSI_CSI_DISCARD;
        }
        return UART_LINE_IGNORED;
    }

    if (screen_enabled && line->screen_navigation) return UART_LINE_IGNORED;
    if (ch == 0x08U || ch == 0x7fU) return erase_before(line);
    if (ch < 0x20U || ch > 0x7eU) {
        ++line->nonascii_bytes;
        return UART_LINE_IGNORED;
    }
    if (line->poisoned) return UART_LINE_IGNORED;
    if (line->length >= UART_LINE_CAPACITY) {
        line->poisoned = true; /* fail closed, even if later BS is sent */
        return UART_LINE_OVERFLOW;
    }
    /* Include old NUL; never copy beyond data[120]. */
    memmove(line->data + line->cursor_pos + 1U,
            line->data + line->cursor_pos,
            line->length - line->cursor_pos + 1U);
    line->data[line->cursor_pos++] = ch;
    ++line->length;
    return UART_LINE_APPEND;
}

UartLineEvent uart_line_feed(UartLine *line, uint8_t ch)
{
    return feed_impl(line, ch, false);
}
UartLineEvent uart_line_feed_screen(UartLine *line, uint8_t ch)
{
    return feed_impl(line, ch, true);
}
void uart_line_ack(UartLine *line)
{
    if (line == NULL || !line->ready) return;
    line->length = 0U;
    line->cursor_pos = 0U;
    line->data[0] = 0U;
    line->poisoned = false;
    line->ready = false;
    line->screen_navigation = false;
    line->rejected_ansi_incomplete = false;
    ansi_clear(line);
    /* Keep last_cr for exactly one following LF (CRLF coalescing). */
}
