#ifndef HW4_CPC_ESCAPE_CONTRACT_H
#define HW4_CPC_ESCAPE_CONTRACT_H

/* HW4-ESC-BREAK-A: host-only C99 experiment. No firmware/BSR integration. */
#include <stdbool.h>
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

/* B1: CONSOLE transport threshold, NOT CPC ROM ESC timing. A raw 0x1b
 * cannot be identified as ESC until ANSI continuation is excluded.
 * Only an observed empty UART read permits the idle boundary below. */
#define HW4_ESC_UART_IDLE_US UINT64_C(50000)
typedef struct {
    Hw4EscDecoder decoder;
    Hw4EscPhase phase;
    uint64_t pending_since_us;
    bool pending_valid;
} Hw4EscRunControl;
void hw4_esc_run_control_init(Hw4EscRunControl *control);
/* At most two ordered transitions per input byte; defer_other suppresses
 * the ordinary-key RESUME while an exact !BREAK prefix is in progress. */
size_t hw4_esc_run_control_feed(Hw4EscRunControl *control, uint8_t byte,
                                uint64_t now_us, bool defer_other,
                                Hw4EscAction actions[2]);
/* Use ONLY on a proved UART RX idle boundary. Never finish a CSI/SS3 packet
 * at a read boundary: broken ANSI is quarantined by the decoder. */
Hw4EscAction hw4_esc_run_control_idle(Hw4EscRunControl *control,
                                      uint64_t now_us);

#endif
