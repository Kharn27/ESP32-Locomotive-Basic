/* HW4-DISP-RENDER-A: same MODE1 states, frozen baseline vs optimized API.
 * Compile e.g. GCC/Clang -O3 -std=c99 on Linux. This is a HOST CPU
 * benchmark, NOT a CYD or SPI timing measurement. No synthetic sleep.
 */
#define _POSIX_C_SOURCE 200809L
#include "hw4_render_a_reference.h"
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { SAMPLES = 15, BATCH = 24 };
static uint8_t vram[CPC_VIDEO_BYTES];
static uint16_t scan[320U];
static uint16_t check[320U];
static volatile uint64_t sink;
typedef bool (*Renderer)(const CpcVideo *, unsigned, uint16_t *, size_t);
typedef struct {
    const char *name;
    unsigned start_y;
    unsigned end_y;
} Case;
typedef struct {
    uint64_t min_ns;
    uint64_t median_ns;
    uint64_t max_ns;
} Stats;
static uint64_t monotonic_ns(void)
{
    struct timespec t = {0};
    if (clock_gettime(CLOCK_MONOTONIC, &t) != 0) {
        perror("clock_gettime");
        exit(2);
    }
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) +
           (uint64_t)t.tv_nsec;
}
static int order_u64(const void *a, const void *b)
{
    const uint64_t x = *(const uint64_t *)a;
    const uint64_t y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}
static uint8_t glyph(void *ignored, uint8_t ch, unsigned row)
{
    (void)ignored;
    return (uint8_t)(((unsigned)ch * 37U + row * 29U) ^ (0xa5U >> (row % 4U)));
}
static void make_case(CpcVideo *v, unsigned n)
{
    if (!cpc_video_init(v, vram, CPC_VIDEO_BYTES, CPC_MODE_1)) exit(2);
    for (unsigned p = 0U; p < 4U; ++p)
        if (!cpc_video_set_ink(v, p, (3U + 6U * p) % 27U)) exit(2);
    if (!cpc_video_set_border(v, 15U)) exit(2);
    if (n == 0U) {
        memset(v->pixels, 0x55, CPC_VIDEO_BYTES); /* uniform ink 1 */
    } else if (n == 1U) {
        for (unsigned row = 0U; row < 25U; ++row)
            for (unsigned col = 0U; col < 40U; ++col)
                if (!cpc_video_put_cell(v, col, row,
                    (uint8_t)((row * 19U + col * 37U) & 255U), glyph, NULL))
                    exit(2);
    } else if (n == 2U) {
        for (unsigned i = 0U; i < CPC_VIDEO_BYTES; ++i)
            v->pixels[i] = (uint8_t)(i % 2U == 0U ? 0x1bU : 0xe4U);
    } else {
        uint32_t state = UINT32_C(0x91bd7423);
        for (unsigned i = 0U; i < CPC_VIDEO_BYTES; ++i) {
            state ^= state << 13U;
            state ^= state >> 17U;
            state ^= state << 5U;
            v->pixels[i] = (uint8_t)state;
        }
    }
    if (n == 4U || n == 5U) {
        if (!cpc_video_set_text_colors(v, 1U, 0U) ||
            !cpc_video_cursor(v, 39U, n == 4U ? 24U : 9U, true))
            exit(2);
    }
}
static void verify_same_image(const CpcVideo *v, unsigned start, unsigned end)
{
    for (unsigned y = start; y < end; ++y) {
        if (!hw4_render_a_reference(v, y, check, 320U) ||
            !cpc_video_render_row(v, y, scan, 320U)) exit(3);
        for (unsigned x = 0U; x < 320U; ++x)
            if (check[x] != scan[x]) {
                fprintf(stderr, "BENCHMARK_PIXEL_MISMATCH x=%u y=%u\n", x, y);
                exit(3);
            }
    }
}
static uint64_t timed(Renderer fn, const CpcVideo *v, const Case *c)
{
    const uint64_t start = monotonic_ns();
    for (unsigned repeat = 0U; repeat < BATCH; ++repeat)
        for (unsigned y = c->start_y; y < c->end_y; ++y) {
            if (!fn(v, y, scan, 320U)) exit(2);
            /* The scanline must be computed; no elision of all rendering.
             * Both implementations run in separate linked C objects. */
            sink += scan[(y * 17U + repeat) % 320U];
        }
    const uint64_t end = monotonic_ns();
    return (end - start) / BATCH; /* ns per complete requested repaint */
}
static Stats stats(uint64_t samples[SAMPLES])
{
    qsort(samples, SAMPLES, sizeof(samples[0]), order_u64);
    const Stats out = {samples[0], samples[SAMPLES / 2], samples[SAMPLES - 1]};
    return out;
}
int main(void)
{
    static const Case cases[] = {
        {"uniform_full25", 20U, 220U},
        {"dense_text_full25", 20U, 220U},
        {"four_inks_full25", 20U, 220U},
        {"graphic_full25", 20U, 220U},
        {"border_cursor_full240", 0U, 240U},
        {"partial_cursor_band8", 20U + 9U * 8U, 20U + 10U * 8U}
    };
#if defined(__clang__)
    const char *compiler = "clang";
#elif defined(__GNUC__)
    const char *compiler = "gcc";
#else
    const char *compiler = "unknown";
#endif
    uint64_t total_ref = 0U, total_new = 0U;
    printf("HW4_RENDER_A_BENCH compiler=%s samples=%d batch=%d "
           "scope=linux_host_cpu_only metric=ns_per_requested_repaint "
           "reference=main_21e95a7_frozen_generic\n",
           compiler, SAMPLES, BATCH);
    for (unsigned n = 0U; n < sizeof(cases) / sizeof(cases[0]); ++n) {
        CpcVideo v;
        make_case(&v, n);
        verify_same_image(&v, cases[n].start_y, cases[n].end_y);
        uint64_t ref[SAMPLES], opt[SAMPLES];
        for (unsigned sample = 0U; sample < SAMPLES; ++sample) {
            if ((sample % 2U) == 0U) {
                ref[sample] = timed(hw4_render_a_reference, &v, &cases[n]);
                opt[sample] = timed(cpc_video_render_row, &v, &cases[n]);
            } else {
                opt[sample] = timed(cpc_video_render_row, &v, &cases[n]);
                ref[sample] = timed(hw4_render_a_reference, &v, &cases[n]);
            }
        }
        const Stats a = stats(ref), b = stats(opt);
        const double gain = a.median_ns != 0U ?
            100.0 * (1.0 - (double)b.median_ns / (double)a.median_ns) : 0.0;
        printf("CASE=%s rows=%u ref_min_ns=%" PRIu64
               " ref_median_ns=%" PRIu64 " ref_max_ns=%" PRIu64
               " new_min_ns=%" PRIu64 " new_median_ns=%" PRIu64
               " new_max_ns=%" PRIu64 " gain_pct=%.2f\n",
               cases[n].name, cases[n].end_y - cases[n].start_y,
               a.min_ns, a.median_ns, a.max_ns,
               b.min_ns, b.median_ns, b.max_ns, gain);
        total_ref += a.median_ns;
        total_new += b.median_ns;
    }
    printf("AGGREGATE median_sum_ref_ns=%" PRIu64
           " median_sum_new_ns=%" PRIu64 " gain_pct=%.2f sink=%" PRIu64
           " ON_DEVICE_UNVERIFIED=1\n",
           total_ref, total_new,
           total_ref != 0U ?
               100.0 * (1.0 - (double)total_new / (double)total_ref) : 0.0,
           sink);
    return 0;
}
