/* HW4-RUN-BREAK-B: byte-only host command while RUN owns UART0.
 * Independent from E1/E3 editor, BASIC tokenizer and ESP-IDF. */
#ifndef HW4_RUN_BREAK_INPUT_H
#define HW4_RUN_BREAK_INPUT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define HW4_RUN_BREAK_BYTES 6u
typedef enum {
    HW4_BREAK_INPUT_NONE = 0,
    HW4_BREAK_INPUT_REQUEST,
    HW4_BREAK_INPUT_IGNORED
} Hw4BreakInputEvent;
typedef struct {
    uint8_t bytes[HW4_RUN_BREAK_BYTES];
    size_t length;
    bool discard;
    bool last_cr;
    size_t ignored_lines;
    size_t overflow_lines;
} Hw4RunBreakInput;
void hw4_run_break_input_init(Hw4RunBreakInput *input);
/* Only exact case-insensitive "!BREAK" + CR/LF triggers.
 * Whole line is discarded on overflow / mismatch; CRLF counts once.
 * No byte is ever forwarded to BASIC, display or prompt editor. */
Hw4BreakInputEvent hw4_run_break_input_feed(Hw4RunBreakInput *input,
                                             uint8_t byte);
#endif
