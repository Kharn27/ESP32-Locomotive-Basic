/* HW4-TOUCH-T1: real portable gesture state machine, no hardware mocks. */
#include "hw4_touch_t1.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define REQUIRE(x) do { if (!(x)) { \
    fprintf(stderr, "HW4-TOUCH-T1 FAIL line=%d expression=%s\n", __LINE__, #x); \
    exit(1); \
} } while (0)

static Hw4TouchEvent tick(Hw4TouchT1 *s, bool down, uint64_t ms)
{
    return hw4_touch_t1_step(s, down, ms, NULL);
}
static void ready(Hw4TouchT1 *s)
{
    hw4_touch_t1_init(s, false, 0U);
    REQUIRE(!s->armed);
    REQUIRE(tick(s, false, 49U) == HW4_TOUCH_NONE);
    REQUIRE(!s->armed);
    REQUIRE(tick(s, false, 50U) == HW4_TOUCH_NONE);
    REQUIRE(s->armed);
}
static void press(Hw4TouchT1 *s, uint64_t ms)
{
    REQUIRE(tick(s, true, ms) == HW4_TOUCH_NONE);
    REQUIRE(tick(s, true, ms + 49U) == HW4_TOUCH_NONE);
    REQUIRE(tick(s, true, ms + 50U) == HW4_TOUCH_PRESS);
}
static void release(Hw4TouchT1 *s, uint64_t ms, Hw4TouchEvent result)
{
    REQUIRE(tick(s, false, ms) == HW4_TOUCH_NONE);
    REQUIRE(tick(s, false, ms + 49U) == HW4_TOUCH_NONE);
    REQUIRE(tick(s, false, ms + 50U) == result);
}
static void two_taps(void)
{
    Hw4TouchT1 s;
    ready(&s);
    unsigned orientation = 10U;
    press(&s, 100U);
    release(&s, 180U, HW4_TOUCH_SHORT_ROTATE);
    orientation = orientation == 9U ? 10U : 9U;
    REQUIRE(orientation == 9U && s.armed && !s.active_pressed);
    press(&s, 300U);
    release(&s, 430U, HW4_TOUCH_SHORT_ROTATE);
    orientation = orientation == 9U ? 10U : 9U;
    REQUIRE(orientation == 10U);
    REQUIRE(tick(&s, false, 600U) == HW4_TOUCH_NONE);
}
static void bounce_and_short(void)
{
    Hw4TouchT1 s;
    ready(&s);
    REQUIRE(tick(&s, true, 100U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, false, 125U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, true, 140U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, false, 160U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, false, 210U) == HW4_TOUCH_NONE);
    REQUIRE(!s.active_pressed);
    press(&s, 300U);
    /* Brief contact dropout of <50 ms does not end the hold. */
    REQUIRE(tick(&s, false, 1000U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, true, 1025U) == HW4_TOUCH_NONE);
    release(&s, 1300U, HW4_TOUCH_SHORT_ROTATE);
    REQUIRE(tick(&s, false, 1400U) == HW4_TOUCH_NONE);
}
static void just_below_threshold(void)
{
    Hw4TouchT1 s;
    uint64_t duration=UINT64_MAX;
    ready(&s);
    press(&s, 100U);
    REQUIRE(hw4_touch_t1_step(&s, true, 2999U, &duration) == HW4_TOUCH_NONE);
    REQUIRE(hw4_touch_t1_step(&s, false, 3099U, &duration) == HW4_TOUCH_NONE);
    /* At the moment of the physical UP edge the hold was 2999 ms.
     * The 50-ms release debounce must not convert it into a long press. */
    REQUIRE(hw4_touch_t1_step(&s, false, 3149U, &duration) == HW4_TOUCH_SHORT_ROTATE);
    REQUIRE(duration == 2999U);
}
static void long_exact_and_unique(void)
{
    Hw4TouchT1 s;
    uint64_t elapsed=0U;
    ready(&s);
    press(&s, 100U);
    REQUIRE(hw4_touch_t1_step(&s, true, 3099U, &elapsed) == HW4_TOUCH_NONE);
    REQUIRE(hw4_touch_t1_step(&s, true, 3100U, &elapsed) == HW4_TOUCH_LONG_RESET);
    REQUIRE(elapsed == 3000U);
    REQUIRE(tick(&s, true, 5100U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, true, 8000U) == HW4_TOUCH_NONE);
    release(&s, 8100U, HW4_TOUCH_NONE);
    /* A later legitimate gesture still works if the mocked restart is not
     * actually called. */
    press(&s, 9000U);
    release(&s, 9140U, HW4_TOUCH_SHORT_ROTATE);
}
static void long_discovered_at_up(void)
{
    Hw4TouchT1 s;
    ready(&s);
    press(&s, 100U);
    REQUIRE(tick(&s, false, 3200U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, false, 3250U) == HW4_TOUCH_LONG_RESET);
    REQUIRE(tick(&s, false, 3300U) == HW4_TOUCH_NONE);
}
static void boot_held_and_restart_held(void)
{
    Hw4TouchT1 s;
    hw4_touch_t1_init(&s, true, 0U);
    REQUIRE(!s.armed);
    REQUIRE(tick(&s, true, 3000U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, true, 6000U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, false, 6100U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, false, 6150U) == HW4_TOUCH_NONE);
    REQUIRE(s.armed);
    press(&s, 6300U);
    REQUIRE(tick(&s, true, 9300U) == HW4_TOUCH_LONG_RESET);
    /* Simulate esp_restart() with the same uninterrupted finger still
     * asserting GPIO36: this new instance must NEVER reset again. */
    hw4_touch_t1_init(&s, true, 9400U);
    REQUIRE(tick(&s, true, 15000U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, false, 15100U) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, false, 15150U) == HW4_TOUCH_NONE);
    REQUIRE(s.armed);
    press(&s, 15300U);
    release(&s, 15500U, HW4_TOUCH_SHORT_ROTATE);
}
static void backwards_and_invalid(void)
{
    Hw4TouchT1 s;
    ready(&s);
    press(&s, 100U);
    REQUIRE(tick(&s, false, 149U) == HW4_TOUCH_NONE);
    REQUIRE(s.active_pressed);
    release(&s, 200U, HW4_TOUCH_SHORT_ROTATE);
    REQUIRE(hw4_touch_t1_step(NULL, true, 0U, NULL) == HW4_TOUCH_NONE);
    REQUIRE(tick(&s, false, 300U) == HW4_TOUCH_NONE);
}
int main(void)
{
    two_taps();
    bounce_and_short();
    just_below_threshold();
    long_exact_and_unique();
    long_discovered_at_up();
    boot_held_and_restart_held();
    backwards_and_invalid();
    puts("HW4-TOUCH-T1 HOST_PASS boot_held bounce two_taps short_2999 "
         "long_3000 unique_5000 restart_held monotonic");
    return 0;
}
