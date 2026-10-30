#include "hw4_touch_t1.h"
#include <stddef.h>
#include <string.h>

void hw4_touch_t1_init(Hw4TouchT1 *touch, bool initial_pressed,
                       uint64_t now_ms)
{
    if (touch == NULL) return;
    memset(touch, 0, sizeof(*touch));
    touch->stable_pressed = initial_pressed;
    touch->candidate_pressed = initial_pressed;
    touch->candidate_since_ms = now_ms;
    touch->last_ms = now_ms;
}

/* Polling is intentionally pure: no GPIO, heap, clocks, tasks or LCD writes. */
Hw4TouchEvent hw4_touch_t1_step(Hw4TouchT1 *touch, bool raw_pressed,
                               uint64_t now_ms, uint64_t *elapsed_ms)
{
    if (touch == NULL || now_ms < touch->last_ms) return HW4_TOUCH_NONE;
    touch->last_ms = now_ms;
    if (raw_pressed != touch->candidate_pressed) {
        touch->candidate_pressed = raw_pressed;
        touch->candidate_since_ms = now_ms;
    }
    if (touch->candidate_pressed != touch->stable_pressed &&
        now_ms - touch->candidate_since_ms >= HW4_TOUCH_DEBOUNCE_MS) {
        touch->stable_pressed = touch->candidate_pressed;
        if (touch->stable_pressed) {
            if (touch->armed) {
                touch->active_pressed = true;
                touch->long_fired = false;
                touch->pressed_since_ms = touch->candidate_since_ms;
                if (elapsed_ms != NULL) *elapsed_ms = 0U;
                return HW4_TOUCH_PRESS;
            }
        } else if (touch->active_pressed) {
            uint64_t duration = touch->candidate_since_ms -
                                touch->pressed_since_ms;
            touch->active_pressed = false;
            if (!touch->long_fired) {
                touch->long_fired = duration >= HW4_TOUCH_LONG_MS;
                if (elapsed_ms != NULL) *elapsed_ms = duration;
                return touch->long_fired ? HW4_TOUCH_LONG_RESET
                                        : HW4_TOUCH_SHORT_ROTATE;
            }
        }
    }
    if (!touch->armed && !touch->candidate_pressed &&
        !touch->stable_pressed &&
        now_ms - touch->candidate_since_ms >= HW4_TOUCH_DEBOUNCE_MS)
        touch->armed = true;
    /* A raw release pending debounce must not cause a late long reset:
     * sample the exact release edge and decide on its verified duration. */
    if (touch->active_pressed && touch->stable_pressed &&
        touch->candidate_pressed && !touch->long_fired &&
        now_ms - touch->pressed_since_ms >= HW4_TOUCH_LONG_MS) {
        touch->long_fired = true;
        if (elapsed_ms != NULL) *elapsed_ms =
            now_ms - touch->pressed_since_ms;
        return HW4_TOUCH_LONG_RESET;
    }
    return HW4_TOUCH_NONE;
}
