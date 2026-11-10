/* CLK-02: host C99 tests use exactly the firmware's aggregate helper. */
#include "hw4_clk02_phase.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static void positive(void)
{
    Hw4Clk02Phase p;
    uint64_t other = 9U;
    hw4_clk02_reset(&p);
    hw4_clk02_record(&p, HW4_CLK02_STEP, 100U, 400U, 0U, 0U);
    hw4_clk02_record(&p, HW4_CLK02_DIRTY, 500U, 600U, 1U, 3U);
    hw4_clk02_record(&p, HW4_CLK02_YIELD, 700U, 1000U, 0U, 0U);
    assert(!p.invalid);
    assert(hw4_clk02_finish(&p, 1000U, &other));
    assert(p.step_wall_us == 300U && p.repaint_wall_us == 100U);
    assert(p.yield_wall_us == 300U && other == 300U);
    assert(p.step_calls == 1U && p.repaint_calls == 1U &&
           p.yield_calls == 1U && p.repaint_flushes == 1U &&
           p.repaint_bands == 3U && p.full_repaints == 0U);
    hw4_clk02_record(&p, HW4_CLK02_FULL, 1100U, 1200U, 0U, 30U);
    assert(hw4_clk02_finish(&p, 1100U, &other));
    assert(other == 300U && p.repaint_wall_us == 200U);
    assert(p.repaint_calls == 2U && p.full_repaints == 1U &&
           p.repaint_bands == 33U);
}

static void negative(void)
{
    Hw4Clk02Phase p;
    uint64_t other = 9876U;
    hw4_clk02_reset(&p);
    assert(!hw4_clk02_finish(&p, 0U, &other));
    hw4_clk02_record(&p, HW4_CLK02_STEP, 20U, 19U, 0U, 0U);
    assert(p.invalid && !hw4_clk02_finish(&p, 10U, &other));
    hw4_clk02_reset(&p);
    hw4_clk02_record(&p, (Hw4Clk02Kind)0, 0U, 10U, 0U, 0U);
    assert(p.invalid);
    hw4_clk02_reset(&p);
    hw4_clk02_record(&p, HW4_CLK02_STEP, 0U, 100U, 0U, 0U);
    assert(!hw4_clk02_finish(&p, 99U, &other));
    assert(other == 9876U);
    hw4_clk02_reset(&p);
    hw4_clk02_record(&p, HW4_CLK02_STEP, 0U, UINT64_MAX, 0U, 0U);
    hw4_clk02_record(&p, HW4_CLK02_STEP, 0U, 1U, 0U, 0U);
    assert(p.invalid);
    hw4_clk02_reset(&p);
    p.step_calls = UINT32_MAX;
    hw4_clk02_record(&p, HW4_CLK02_STEP, 0U, 1U, 0U, 0U);
    assert(p.invalid);
    hw4_clk02_reset(&p);
    p.repaint_bands = UINT32_MAX;
    hw4_clk02_record(&p, HW4_CLK02_FULL, 0U, 1U, 0U, 30U);
    assert(p.invalid);
    hw4_clk02_reset(&p);
    p.repaint_flushes = UINT32_MAX;
    hw4_clk02_record(&p, HW4_CLK02_DIRTY, 0U, 1U, 1U, 0U);
    assert(p.invalid);
    hw4_clk02_reset(&p);
    p.full_repaints = UINT32_MAX;
    hw4_clk02_record(&p, HW4_CLK02_FULL, 0U, 1U, 0U, 30U);
    assert(p.invalid);
}

int main(void)
{
    positive();
    negative();
    puts("CLK02_PHASE_C99_PASS bounded disjoint task-wall accounting");
    return 0;
}
