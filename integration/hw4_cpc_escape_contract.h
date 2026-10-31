#ifndef HW4_CPC_ESCAPE_CONTRACT_H
#define HW4_CPC_ESCAPE_CONTRACT_H

/* HW4-ESC-BREAK-A: host-only C99 experiment. No firmware/BSR integration. */
#include <stddef.h>
#include <stdint.h>

typedef enum {
    HW4_ESC_KEY_NONE = 0,
    HW4_ESC_KEY_OTHER,
    HW4_ESC_KEY_ESCAPE,
    HW4_ESC_KEY_ANSI,
    HW4_ESC_KEY_REJECTED,
    HW4_ESC_KEY_HOST_BREAK /* synthetic higher-layer event; never decoded from UART */
} Hw4EscKey;

typedef enum {
    HW4_ESC_TEXT = 0,
    HW4_ESC_PENDING,
    HW4_ESC_CSI,
    HW4_ESC_SS3,
    HW4_ESC_CSI_DISCARD
} Hw4EscParseState;

typedef struct {
    Hw4EscParseState state;
    uint8_t sequence_length;
} Hw4EscDecoder;

/* At most two outputs per byte. ESC is ambiguous until the next byte or
 * release_pending() at a transport-level idle boundary. Not a CPC timeout. */
void hw4_esc_decoder_init(Hw4EscDecoder *decoder);
size_t hw4_esc_decoder_feed(Hw4EscDecoder *decoder, uint8_t byte,
                            Hw4EscKey out[2]);
/* Call ONLY when the UART ESC/CSI prefix ambiguity has actually expired;
 * never simply at an arbitrary uart_read_bytes() chunk boundary. */
Hw4EscKey hw4_esc_decoder_release_pending(Hw4EscDecoder *decoder);
/* A true end-of-input/reset, not the end of a UART read.
 * Truncated CSI/SS3 -> REJECTED; already rejected CSI in DISCARD -> NONE
 * (no duplicate event). Both clear state and rearm the next independent key. */
Hw4EscKey hw4_esc_decoder_finish(Hw4EscDecoder *decoder);

typedef enum {
    HW4_ESC_PROMPT = 0,
    HW4_ESC_RUNNING,
    HW4_ESC_PAUSED,
    HW4_ESC_STOPPED
} Hw4EscPhase;

typedef enum {
    HW4_ESC_ACTION_NONE = 0,
    HW4_ESC_ACTION_PAUSE,
    HW4_ESC_ACTION_RESUME,
    HW4_ESC_ACTION_BREAK_REQUEST
} Hw4EscAction;

/* Describes proposed host routing only. No BASIC STOP/CONT/ON BREAK logic. */
Hw4EscAction hw4_esc_route(Hw4EscPhase *phase, Hw4EscKey key);

#endif
