/*
 * CLK-02 (Issue #310): bounded, CONSOLE-owned phase accounting.
 * Each observation is task elapsed wall time, never exclusive BASIC CPU,
 * FreeRTOS blocked time or LCD GRAM visibility. No runtime scheduling API.
 * Header is C99 so the EXACT arithmetic can be exercised by native CTest.
 */
#ifndef HW4_CLK02_PHASE_H
#define HW4_CLK02_PHASE_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    HW4_CLK02_STEP = 1,
    HW4_CLK02_DIRTY = 2,
    HW4_CLK02_FULL = 3,
    HW4_CLK02_YIELD = 4
} Hw4Clk02Kind;

typedef struct {
    uint64_t step_wall_us;
    uint64_t repaint_wall_us;
    uint64_t yield_wall_us;
    uint32_t step_calls;
    uint32_t repaint_calls;
    uint32_t full_repaints;
    uint32_t yield_calls;
    uint32_t repaint_flushes;  /* dirty-only completed attempts */
    uint32_t repaint_bands;    /* dirty bands + touch full bands */
    bool invalid;              /* monotonicity or integer overflow */
} Hw4Clk02Phase;

static inline void hw4_clk02_reset(Hw4Clk02Phase *phase)
{
    *phase = (Hw4Clk02Phase){0};
}

/* No telemetry emission here: one call per existing quantum/repaint/yield. */
static inline void hw4_clk02_record(Hw4Clk02Phase *phase, Hw4Clk02Kind kind,
                                    uint64_t begin_us, uint64_t end_us,
                                    uint32_t flushes, uint32_t bands)
{
    uint64_t *duration = NULL;
    uint32_t *calls = NULL;
    if (end_us < begin_us) {
        phase->invalid = true;
        return;
    }
    if (kind == HW4_CLK02_STEP) {
        duration = &phase->step_wall_us;
        calls = &phase->step_calls;
    } else if (kind == HW4_CLK02_DIRTY || kind == HW4_CLK02_FULL) {
        duration = &phase->repaint_wall_us;
        calls = &phase->repaint_calls;
    } else if (kind == HW4_CLK02_YIELD) {
        duration = &phase->yield_wall_us;
        calls = &phase->yield_calls;
    } else {
        phase->invalid = true;
        return;
    }
    const uint64_t delta = end_us - begin_us;
    if (UINT64_MAX - *duration < delta || *calls == UINT32_MAX ||
        UINT32_MAX - phase->repaint_flushes < flushes ||
        UINT32_MAX - phase->repaint_bands < bands ||
        (kind == HW4_CLK02_FULL && phase->full_repaints == UINT32_MAX)) {
        phase->invalid = true;
        return;
    }
    *duration += delta;
    ++(*calls);
    phase->repaint_flushes += flushes;
    phase->repaint_bands += bands;
    if (kind == HW4_CLK02_FULL)
        ++phase->full_repaints;
}

/* Result is an additive partition of RUN_DURATION, NOT a CPU breakdown.
 * The residual contains UART/touch work, logs, clock probes and gaps. */
static inline bool hw4_clk02_finish(const Hw4Clk02Phase *phase,
                                     uint64_t run_duration_us,
                                     uint64_t *other_wall_us)
{
    if (phase->invalid || run_duration_us == 0U ||
        phase->step_wall_us > run_duration_us ||
        phase->repaint_wall_us > run_duration_us - phase->step_wall_us)
        return false;
    uint64_t subtotal = phase->step_wall_us + phase->repaint_wall_us;
    if (phase->yield_wall_us > run_duration_us - subtotal)
        return false;
    subtotal += phase->yield_wall_us;
    *other_wall_us = run_duration_us - subtotal;
    return true;
}

#endif
