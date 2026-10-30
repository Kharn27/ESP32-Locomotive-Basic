/* HW4-PEN-A: portable integration only. Core and video have no dependency
 * on this module. No allocation, no LCD hardware, no encoded PRINT commands. */
#ifndef HW4_PEN_BRIDGE_H
#define HW4_PEN_BRIDGE_H

#include "basic_executor.h"
#include "cpc_text.h"

typedef enum {
    HW4_PEN_OK = 0,
    HW4_PEN_INVALID_ARGUMENT,
    HW4_PEN_INVALID_EVENT,
    HW4_PEN_BAD_OFFSET,
    HW4_PEN_UNSUPPORTED_LOGICAL,
    HW4_PEN_UNVERIFIED_VISUAL,
    HW4_PEN_TEXT_PRECHECK_FAILED,
    HW4_PEN_RENDER_FAILED,
    HW4_PEN_SET_INK_UNSUPPORTED /* J1.18-B: no renderer; whole step rejected */
} Hw4PenStatus;

/* C1-RUN-STOP: shared CONSOLE/host RUN-loop control.
 * A renderer reject already displayed its one diagnostic; return to Ready,
 * without calling bsr_step_events on a stopped runtime. */
typedef enum {
    HW4_PEN_DISPLAY_OK = 0,
    HW4_PEN_DISPLAY_REJECT_DIAGNOSED,
    HW4_PEN_DISPLAY_FATAL
} Hw4PenDisplayResult;
typedef enum {
    HW4_PEN_RUN_CONTINUE = 0,
    HW4_PEN_RUN_DONE,
    HW4_PEN_RUN_FATAL
} Hw4PenRunAction;
Hw4PenRunAction hw4_pen_run_after_display(Hw4PenDisplayResult result);

/* The mapping is deliberately bounded to the independently acquired
 * J1.17-A witnesses, NOT a general CPC palette algorithm:
 *   0..3 -> same MODE1 pixel index
 *   4    -> 0 only for paper 0, INK0=0 (CPC oracle black), or INK0=1
 *           (CYD boot blue). In both cases the glyph matches background.
 *   15   -> 3 only when INK3=18 (green, CPC oracle conditions).
 * Other logical pens and incompatible ink contexts fail without side effects.
 */
Hw4PenStatus hw4_pen_pixel_index(const CpcVideo *video, uint8_t logical,
                                  uint8_t *pixel);

/* Pure preflight: explicitly reject SET_INK, including preceding PEN/PRINT;
 * no pixels, counters or cursor may change during validation. Check event
 * types, indices, monotonic byte offsets and the entire
 * CpcText stream. No output bytes, video pixels or sink counters are changed.
 * Repeat validation before replay if external code changes ink/sink state. */
Hw4PenStatus hw4_pen_preflight(const CpcText *sink,
                               const uint8_t *print_bytes, size_t byte_count,
                               const BEVideoEvent *events, size_t event_count);

/* Replay PRINT slices and typed events in source order. No effect on
 * validation error. On HW4_PEN_OK every PRINT byte is consumed exactly once,
 * in the same order, and every video event is applied exactly once.
 * This function owns no buffer: caller must ensure no concurrent mutations. */
Hw4PenStatus hw4_pen_replay(CpcText *sink,
                            const uint8_t *print_bytes, size_t byte_count,
                            const BEVideoEvent *events, size_t event_count);
/* CONSOLE-owned !CLS path: delegates to the real UART screen clear,
 * then (in C1) must restore the explicit PEN ink context. */
bool hw4_pen_console_clear(CpcText *text);
#endif
