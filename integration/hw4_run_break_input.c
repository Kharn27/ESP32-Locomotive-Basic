#include "hw4_run_break_input.h"
#include <string.h>

void hw4_run_break_input_init(Hw4RunBreakInput *input)
{
    if (input != NULL) memset(input, 0, sizeof(*input));
}

static bool is_break(const Hw4RunBreakInput *input)
{
    static const char word[] = "!BREAK";
    size_t i;
    if (input->length != HW4_RUN_BREAK_BYTES || input->discard)
        return false;
    for (i = 0u; i < HW4_RUN_BREAK_BYTES; ++i) {
        uint8_t c = input->bytes[i];
        if (c >= (uint8_t)'a' && c <= (uint8_t)'z')
            c = (uint8_t)(c - (uint8_t)'a' + (uint8_t)'A');
        if (c != (uint8_t)word[i]) return false;
    }
    return true;
}

Hw4BreakInputEvent hw4_run_break_input_feed(Hw4RunBreakInput *input,
                                             uint8_t byte)
{
    bool request, overflow;
    if (input == NULL) return HW4_BREAK_INPUT_IGNORED;
    if (input->last_cr && byte == (uint8_t)'\n') {
        input->last_cr = false;
        return HW4_BREAK_INPUT_NONE;
    }
    input->last_cr = false;
    if (byte == (uint8_t)'\r' || byte == (uint8_t)'\n') {
        request = is_break(input);
        overflow = input->discard;
        if (!request) {
            ++input->ignored_lines;
            if (overflow) ++input->overflow_lines;
        }
        input->length = 0u;
        input->discard = false;
        input->last_cr = byte == (uint8_t)'\r';
        return request ? HW4_BREAK_INPUT_REQUEST : HW4_BREAK_INPUT_IGNORED;
    }
    if (input->discard) return HW4_BREAK_INPUT_NONE;
    if (input->length == HW4_RUN_BREAK_BYTES) {
        input->discard = true;
        return HW4_BREAK_INPUT_NONE;
    }
    input->bytes[input->length++] = byte;
    return HW4_BREAK_INPUT_NONE;
}
