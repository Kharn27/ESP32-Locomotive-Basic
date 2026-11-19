#include "hw4_cpc_escape_contract.h"

#define HW4_ESC_MAX_CSI_BYTES 16u
#define HW4_ASCII_ESC 0x1bu

void hw4_esc_decoder_init(Hw4EscDecoder *decoder)
{
    if (decoder != NULL) {
        decoder->state = HW4_ESC_TEXT;
        decoder->sequence_length = 0u;
    }
}

size_t hw4_esc_decoder_feed(Hw4EscDecoder *decoder, uint8_t byte,
                            Hw4EscKey out[2])
{
    if (decoder == NULL || out == NULL) {
        return 0u;
    }
    switch (decoder->state) {
    case HW4_ESC_TEXT:
        if (byte == HW4_ASCII_ESC) {
            decoder->state = HW4_ESC_PENDING;
            return 0u;
        }
        out[0] = HW4_ESC_KEY_OTHER;
        return 1u;
    case HW4_ESC_PENDING:
        if (byte == (uint8_t)'[') {
            decoder->state = HW4_ESC_CSI;
            decoder->sequence_length = 0u;
            return 0u;
        }
        if (byte == (uint8_t)'O') {
            decoder->state = HW4_ESC_SS3;
            return 0u;
        }
        out[0] = HW4_ESC_KEY_ESCAPE;
        if (byte == HW4_ASCII_ESC) {
            /* First ESC is now unambiguous, second awaits a frame boundary. */
            return 1u;
        }
        decoder->state = HW4_ESC_TEXT;
        out[1] = HW4_ESC_KEY_OTHER;
        return 2u;
    case HW4_ESC_CSI:
        if (byte >= 0x40u && byte <= 0x7eu) {
            decoder->state = HW4_ESC_TEXT;
            decoder->sequence_length = 0u;
            out[0] = HW4_ESC_KEY_ANSI;
            return 1u;
        }
        if (byte < 0x20u || byte > 0x3fu) {
            /* Report once, then quarantine ALL remaining bytes until a
             * real ANSI final. Controls, including ESC, are not new keys. */
            decoder->state = HW4_ESC_CSI_DISCARD;
            out[0] = HW4_ESC_KEY_REJECTED;
            return 1u;
        }
        if (decoder->sequence_length == HW4_ESC_MAX_CSI_BYTES) {
            decoder->state = HW4_ESC_CSI_DISCARD;
            out[0] = HW4_ESC_KEY_REJECTED;
            return 1u;
        }
        ++decoder->sequence_length;
        return 0u;
    case HW4_ESC_SS3:
        decoder->state = HW4_ESC_TEXT;
        out[0] = byte >= 0x40u && byte <= 0x7eu
                     ? HW4_ESC_KEY_ANSI : HW4_ESC_KEY_REJECTED;
        return 1u;
    case HW4_ESC_CSI_DISCARD:
        /* Only an explicit ANSI final (0x40..0x7e) ends quarantine.
         * Everything else, even NUL, ESC and high-bit bytes, is consumed. */
        if (byte >= 0x40u && byte <= 0x7eu) {
            decoder->state = HW4_ESC_TEXT;
            decoder->sequence_length = 0u;
        }
        return 0u;
    default:
        hw4_esc_decoder_init(decoder);
        out[0] = HW4_ESC_KEY_REJECTED;
        return 1u;
    }
}

Hw4EscKey hw4_esc_decoder_release_pending(Hw4EscDecoder *decoder)
{
    if (decoder != NULL && decoder->state == HW4_ESC_PENDING) {
        decoder->state = HW4_ESC_TEXT;
        return HW4_ESC_KEY_ESCAPE;
    }
    return HW4_ESC_KEY_NONE;
}

Hw4EscKey hw4_esc_decoder_finish(Hw4EscDecoder *decoder)
{
    Hw4EscKey result = HW4_ESC_KEY_NONE;
    if (decoder != NULL) {
        if (decoder->state == HW4_ESC_PENDING) {
            result = HW4_ESC_KEY_ESCAPE;
        } else if (decoder->state == HW4_ESC_CSI ||
                   decoder->state == HW4_ESC_SS3) {
            /* Truncated prefix: one rejection at contractual end/reset.
             * CSI_DISCARD already emitted REJECTED when it became invalid. */
            result = HW4_ESC_KEY_REJECTED;
        }
        hw4_esc_decoder_init(decoder);
    }
    return result;
}

Hw4EscAction hw4_esc_route(Hw4EscPhase *phase, Hw4EscKey key)
{
    if (phase == NULL || *phase == HW4_ESC_PROMPT ||
        *phase == HW4_ESC_STOPPED) {
        return HW4_ESC_ACTION_NONE;
    }
    if (key == HW4_ESC_KEY_ESCAPE) {
        if (*phase == HW4_ESC_PAUSED) {
            *phase = HW4_ESC_STOPPED;
            return HW4_ESC_ACTION_BREAK_REQUEST;
        }
        *phase = HW4_ESC_PAUSED;
        return HW4_ESC_ACTION_PAUSE;
    }
    if (*phase == HW4_ESC_PAUSED &&
        (key == HW4_ESC_KEY_OTHER || key == HW4_ESC_KEY_ANSI)) {
        *phase = HW4_ESC_RUNNING;
        return HW4_ESC_ACTION_RESUME;
    }
    return HW4_ESC_ACTION_NONE;
}

void hw4_esc_run_control_init(Hw4EscRunControl *control)
{
    if (control == NULL) return;
    hw4_esc_decoder_init(&control->decoder);
    control->phase = HW4_ESC_RUNNING;
    control->pending_since_us = 0u;
    control->pending_valid = false;
}

size_t hw4_esc_run_control_feed(Hw4EscRunControl *control, uint8_t byte,
                                uint64_t now_us, bool defer_other,
                                Hw4EscAction actions[2])
{
    Hw4EscKey keys[2] = {HW4_ESC_KEY_NONE, HW4_ESC_KEY_NONE};
    size_t count, i, written = 0u;
    if (control == NULL || actions == NULL) return 0u;
    count = hw4_esc_decoder_feed(&control->decoder, byte, keys);
    if (control->decoder.state == HW4_ESC_PENDING) {
        /* ESC ESC produces one key plus a new pending ESC prefix. */
        control->pending_since_us = now_us;
        control->pending_valid = true;
    } else {
        control->pending_valid = false;
    }
    for (i = 0u; i < count; ++i) {
        Hw4EscAction action;
        if (keys[i] == HW4_ESC_KEY_OTHER &&
            (defer_other || byte < (uint8_t)' ' || byte > (uint8_t)'~'))
            continue; /* !BREAK and Ctrl+C cannot resume a paused RUN. */
        action = hw4_esc_route(&control->phase, keys[i]);
        if (action != HW4_ESC_ACTION_NONE) actions[written++] = action;
    }
    return written;
}

Hw4EscAction hw4_esc_run_control_idle(Hw4EscRunControl *control,
                                      uint64_t now_us)
{
    Hw4EscKey key;
    if (control == NULL || !control->pending_valid ||
        control->decoder.state != HW4_ESC_PENDING ||
        now_us < control->pending_since_us ||
        now_us - control->pending_since_us < HW4_ESC_UART_IDLE_US)
        return HW4_ESC_ACTION_NONE;
    key = hw4_esc_decoder_release_pending(&control->decoder);
    control->pending_valid = false;
    return hw4_esc_route(&control->phase, key);
}
