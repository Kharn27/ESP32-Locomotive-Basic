/* HW4-TOUCH-T1: portable PENIRQ gesture policy, no ESP-IDF dependencies. */
#ifndef HW4_TOUCH_T1_H
#define HW4_TOUCH_T1_H
#include <stdbool.h>
#include <stdint.h>

#define HW4_TOUCH_DEBOUNCE_MS UINT64_C(50)
#define HW4_TOUCH_LONG_MS UINT64_C(3000)

typedef enum {
    HW4_TOUCH_NONE = 0,
    HW4_TOUCH_PRESS,
    HW4_TOUCH_SHORT_ROTATE,
    HW4_TOUCH_LONG_RESET
} Hw4TouchEvent;

typedef struct {
    uint64_t candidate_since_ms;
    uint64_t pressed_since_ms;
    uint64_t last_ms;
    bool candidate_pressed;
    bool stable_pressed;
    bool armed;
    bool active_pressed;
    bool long_fired;
} Hw4TouchT1;

/* Boot ALWAYS starts disarmed. A stable release of at least 50 ms is needed
 * even when the device restarts with a finger still on the panel. */
void hw4_touch_t1_init(Hw4TouchT1 *touch, bool initial_pressed,
                       uint64_t now_ms);

/* raw_pressed is the active-low /PENIRQ logical interpretation.
 * now_ms must be monotonic; an older sample is ignored.
 * PRESS occurs once after debouncing, SHORT only after a debounced release,
 * LONG at >=3000 ms while held (or at a release sampled past the deadline).
 * elapsed_ms is optional; written only when an event is returned. */
Hw4TouchEvent hw4_touch_t1_step(Hw4TouchT1 *touch, bool raw_pressed,
                               uint64_t now_ms, uint64_t *elapsed_ms);
#endif
