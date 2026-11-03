/* HW4-DISP-PROFILE-A: bounded transport-independent repaint accounting. MIT. */
#ifndef HW4_DISP_PROFILE_H
#define HW4_DISP_PROFILE_H
#include <stdbool.h>
#include <stdint.h>
enum { HW4_DP_BINS=12, HW4_DP_FULL25=0, HW4_DP_PARTIAL=1,
       HW4_DP_SCROLL_ASSOCIATED=2, HW4_DP_CLASSES=3,
       HW4_DP_BAND_BYTES=5120, HW4_DP_TRACE_CAP=16, HW4_DP_TRACE_BYTES=13 };
typedef struct {
    uint32_t bands;       /* 1..25 successfully submitted 8px MODE1 bands */
    uint32_t scrolls;     /* logical scrolls since prior successful repaint */
    uint64_t completed_us;  /* monotonic time AFTER final DMA semaphore return */
    uint64_t wall_us;       /* entire logical dirty flush */
    uint64_t render_pack_us;/* cpc_video_render_row, palette and RGB565 packing */
    uint64_t submit_us;     /* synchronous draw_bitmap wall time */
    uint64_t wait_us;       /* semaphore wait wall time, includes scheduling */
    uint64_t scroll_cpu_wall_us; /* preceding scroll+E2 wall time, NOT repaint time */
} Hw4DpFrame;
typedef struct {
    uint32_t n, min_us, max_us, hist[HW4_DP_BINS];
    uint32_t one_scroll, multi_scroll, max_scrolls;
    uint64_t bands, scrolls;
    uint64_t wall_us, render_pack_us, submit_us, wait_us;
    uint64_t scroll_cpu_wall_us;
} Hw4DpClass;
/* Snapshot returned to observers; seq is derived from completion order. */
typedef struct {
    uint32_t seq, bands, scrolls, wall_us, gap_us;
} Hw4DpTrace;
typedef struct {
    Hw4DpClass classes[HW4_DP_CLASSES];
    uint32_t completed, rejected;
    uint64_t last_completed_us, gap_sum_us;
    uint32_t gaps, gap_min_us, gap_max_us;
    /* Lossless 13-byte record: 1 byte bands + 3 little-endian uint32.\n     * Stored wall/gap already have the same UINT32_MAX cap as before.\n     * No packed struct, unaligned pointer or platform endianness dependency. */
    uint8_t trace[HW4_DP_TRACE_CAP][HW4_DP_TRACE_BYTES];
    uint32_t trace_next, trace_size;
} Hw4DispProfile;
typedef char Hw4DpStaticBudget[(sizeof(Hw4DispProfile)<=720U)?1:-1];
extern const uint32_t hw4_dp_bounds_us[HW4_DP_BINS];
void hw4_dp_reset(Hw4DispProfile *p);
/* All three derived values are exact for every accepted frame. */
uint64_t hw4_dp_bytes(const Hw4DpClass *c);
uint64_t hw4_dp_other_us(const Hw4DpClass *c);
uint32_t hw4_dp_zero_scroll(const Hw4DpClass *c);
/* Chronological index 0 is the oldest retained frame; false is non-mutating. */
bool hw4_dp_trace_at(const Hw4DispProfile *p, uint32_t index, Hw4DpTrace *out);
bool hw4_dp_record(Hw4DispProfile *p, const Hw4DpFrame *f);
uint32_t hw4_dp_quantile_upper(const Hw4DpClass *c, unsigned percentile);
#endif
