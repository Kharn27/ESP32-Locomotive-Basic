/* HW4-C2 portable UART0 line collector: caller-owned, no allocations. */
#ifndef LOCO_UART_LINE_H
#define LOCO_UART_LINE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define UART_LINE_CAPACITY 120U
#define UART_CSI_MAX_BYTES 16U

typedef enum {
    UART_LINE_NONE = 0,
    UART_LINE_APPEND,
    UART_LINE_DELETE, /* Backspace: before cursor (legacy enum) */
    UART_LINE_DELETE_FORWARD, /* ESC[3~: under cursor */
    UART_LINE_LEFT,
    UART_LINE_RIGHT,
    UART_LINE_READY,
    UART_LINE_REJECTED,
    UART_LINE_IGNORED,
    UART_LINE_OVERFLOW
} UartLineEvent;

typedef enum {
    UART_ANSI_TEXT = 0,
    UART_ANSI_ESC,
    UART_ANSI_CSI,
    UART_ANSI_CSI_DISCARD
} UartAnsiState;

typedef struct {
    uint8_t data[UART_LINE_CAPACITY + 1U];
    size_t length;
    size_t cursor_pos; /* 0..length, next insertion point */
    bool poisoned;
    bool ready;
    bool last_cr;
    bool rejected_ansi_incomplete;
    size_t rejected_lines;
    size_t nonascii_bytes;
    UartAnsiState ansi;
    uint8_t csi_length;
    uint8_t csi_first;
    size_t ansi_sequences_ignored;
    size_t ansi_sequences_deleted;
    size_t ansi_incomplete_rejected;
} UartLine;

/* C99 byte-oriented source editor, independent of terminal, TFT, BASIC.
 * ASCII 0x20..0x7e accepted; CR/LF/CRLF finalize exactly one line.
 * BS/DEL remove preceding byte; ESC[3~ removes byte under cursor.
 * ESC[D / ESC[C move the cursor without changing source; insertion shifts
 * the following bytes. At boundaries movement/deletion returns NONE.
 * Other bounded CSI sequences (even if fragmented) are fully consumed;
 * oversized CSI is discarded until its final byte. Escape state consumes
 * no source bytes and is never echoed. Incomplete ESC/CSI followed by
 * CR/LF rejects the ENTIRE line without any BASIC submission.
 * Source overflow similarly poisons and rejects the entire line.
 * APPEND/DELETE/DELETE_FORWARD and LEFT/RIGHT must each sync the visual
 * cursor from data/length/cursor_pos; rejected lines never reach BASIC.
 * Call uart_line_ack() after READY/REJECTED, before next byte. */
void uart_line_init(UartLine *line);
UartLineEvent uart_line_feed(UartLine *line, uint8_t ch);
void uart_line_ack(UartLine *line);
#endif
