/* HW4-SCROLL-OPT-A0: cumulative, allocation-free observation only. MIT. */
#ifndef HW4_SCROLL_METRICS_H
#define HW4_SCROLL_METRICS_H
#include <stdint.h>
enum { HW4_SCROLL_BINS=12, HW4_SCROLL_ORDINARY=0, HW4_SCROLL_ASSOCIATED=1 };
typedef struct {
    uint32_t flushes, bands, min_us, max_us;
    uint32_t hist[HW4_SCROLL_BINS];
    uint32_t up, down, reset_tagged;
    uint64_t us_total, spi_bytes;
} Hw4ScrollClass;
typedef struct {
    Hw4ScrollClass cls[2];
    uint32_t pending_up, pending_down, last_text_up;
    uint32_t resets, reset_pending, report_seq;
} Hw4ScrollMetrics;
typedef char HW4ScrollMetricsBudget[(sizeof(Hw4ScrollMetrics)<=256U)?1:-1];
void hw4_scroll_observe_text(Hw4ScrollMetrics *m, uint32_t up);
void hw4_scroll_nav(Hw4ScrollMetrics *m, int direction); /* +1 image up, -1 image down */
void hw4_scroll_clear(Hw4ScrollMetrics *m, uint32_t new_text_up);
void hw4_scroll_flush(Hw4ScrollMetrics *m, uint32_t bands, uint32_t us,
                      uint64_t bytes);
uint32_t hw4_scroll_quantile_upper(const Hw4ScrollClass *c, unsigned percentile);
extern const uint32_t hw4_scroll_bounds_us[HW4_SCROLL_BINS];
#endif
