#include "hw4_cpc_escape_contract.h"
#include <stdio.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #expr); \
    return 1; } } while (0)

static int feed_expect(Hw4EscDecoder *d, uint8_t b, size_t count,
                       Hw4EscKey first, Hw4EscKey second)
{
    Hw4EscKey got[2] = { HW4_ESC_KEY_NONE, HW4_ESC_KEY_NONE };
    size_t n = hw4_esc_decoder_feed(d, b, got);
    CHECK(n == count);
    if (count > 0u) CHECK(got[0] == first);
    if (count > 1u) CHECK(got[1] == second);
    return 0;
}

static int run_scenarios(void)
{
    Hw4EscDecoder d;
    Hw4EscPhase phase;
    size_t i;
    hw4_esc_decoder_init(&d);

    /* ESC alone: pause; ordinary key resumes, any number of repetitions. */
    phase = HW4_ESC_RUNNING;
    for (i = 0u; i < 3u; ++i) {
        CHECK(feed_expect(&d, 0x1bu, 0u, 0, 0) == 0);
        CHECK(hw4_esc_decoder_release_pending(&d) == HW4_ESC_KEY_ESCAPE);
        CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_ESCAPE) == HW4_ESC_ACTION_PAUSE);
        CHECK(phase == HW4_ESC_PAUSED);
        CHECK(feed_expect(&d, (uint8_t)'x', 1u, HW4_ESC_KEY_OTHER, 0) == 0);
        CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_OTHER) == HW4_ESC_ACTION_RESUME);
        CHECK(phase == HW4_ESC_RUNNING);
    }
    /* Two distinct ESCs: only second requests a break. */
    CHECK(feed_expect(&d, 0x1bu, 0u, 0, 0) == 0);
    CHECK(feed_expect(&d, 0x1bu, 1u, HW4_ESC_KEY_ESCAPE, 0) == 0);
    CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_ESCAPE) == HW4_ESC_ACTION_PAUSE);
    CHECK(hw4_esc_decoder_finish(&d) == HW4_ESC_KEY_ESCAPE);
    CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_ESCAPE) == HW4_ESC_ACTION_BREAK_REQUEST);
    CHECK(phase == HW4_ESC_STOPPED);
    CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_ESCAPE) == HW4_ESC_ACTION_NONE);

    /* ANSI arrows, HOME, Delete and SS3 HOME: never generate raw ESC keys. */
    {
        const char *seqs[] = { "\033[D", "\033[C", "\033[A", "\033[3~",
                               "\033[1~", "\033[1;2D", "\033OH" };
        for (i = 0u; i < sizeof(seqs)/sizeof(seqs[0]); ++i) {
            const unsigned char *p = (const unsigned char *)seqs[i];
            size_t j, len = strlen(seqs[i]);
            hw4_esc_decoder_init(&d);
            for (j = 0u; j < len; ++j) {
                CHECK(feed_expect(&d, p[j], j + 1u == len ? 1u : 0u,
                                  HW4_ESC_KEY_ANSI, 0) == 0);
            }
            CHECK(hw4_esc_decoder_finish(&d) == HW4_ESC_KEY_NONE);
        }
    }
    /* Fragmented CSI (two reads) must survive a non-ESC release attempt. */
    CHECK(feed_expect(&d, 0x1bu, 0u, 0, 0) == 0);
    CHECK(feed_expect(&d, (uint8_t)'[', 0u, 0, 0) == 0);
    CHECK(hw4_esc_decoder_release_pending(&d) == HW4_ESC_KEY_NONE);
    CHECK(feed_expect(&d, (uint8_t)'D', 1u, HW4_ESC_KEY_ANSI, 0) == 0);
    /* ESC followed by ordinary character: both events, in order. */
    CHECK(feed_expect(&d, 0x1bu, 0u, 0, 0) == 0);
    CHECK(feed_expect(&d, (uint8_t)'z', 2u, HW4_ESC_KEY_ESCAPE,
                      HW4_ESC_KEY_OTHER) == 0);
    CHECK(hw4_esc_decoder_finish(&d) == HW4_ESC_KEY_NONE);

    /* Without a run, even a decoded double ESC has no BASIC side effect. */
    phase = HW4_ESC_PROMPT;
    CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_ESCAPE) == HW4_ESC_ACTION_NONE);
    CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_ESCAPE) == HW4_ESC_ACTION_NONE);
    CHECK(phase == HW4_ESC_PROMPT);
    /* Host !BREAK is not a CPC keyboard event, even while paused. */
    phase = HW4_ESC_PAUSED;
    CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_HOST_BREAK) == HW4_ESC_ACTION_NONE);
    CHECK(phase == HW4_ESC_PAUSED);
    CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_ANSI) == HW4_ESC_ACTION_RESUME);
    CHECK(phase == HW4_ESC_RUNNING);
    for (i = 0u; i < strlen("!BREAK\r"); ++i) {
        CHECK(feed_expect(&d, (uint8_t)"!BREAK\r"[i], 1u,
                          HW4_ESC_KEY_OTHER, 0) == 0);
    }
    return 0;
}

static int run_negative(void)
{
    Hw4EscDecoder d;
    Hw4EscPhase phase = HW4_ESC_RUNNING;
    size_t i;
    Hw4EscKey out[2];
    hw4_esc_decoder_init(&d);
    /* 17 parameter bytes: reject, then quarantine the rest until final. */
    CHECK(feed_expect(&d, 0x1bu, 0u, 0, 0) == 0);
    CHECK(feed_expect(&d, (uint8_t)'[', 0u, 0, 0) == 0);
    for (i = 0u; i < 16u; ++i) {
        CHECK(feed_expect(&d, (uint8_t)'1', 0u, 0, 0) == 0);
    }
    CHECK(feed_expect(&d, (uint8_t)'2', 1u, HW4_ESC_KEY_REJECTED, 0) == 0);
    CHECK(feed_expect(&d, (uint8_t)'3', 0u, 0, 0) == 0);
    CHECK(feed_expect(&d, (uint8_t)'D', 0u, 0, 0) == 0);
    CHECK(hw4_esc_decoder_finish(&d) == HW4_ESC_KEY_NONE);
    CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_REJECTED) == HW4_ESC_ACTION_NONE);

    /* Control/ESC embedded in CSI is rejected, not a surprise BREAK. */
    CHECK(feed_expect(&d, 0x1bu, 0u, 0, 0) == 0);
    CHECK(feed_expect(&d, (uint8_t)'[', 0u, 0, 0) == 0);
    CHECK(feed_expect(&d, 0x1bu, 1u, HW4_ESC_KEY_REJECTED, 0) == 0);
    CHECK(hw4_esc_decoder_finish(&d) == HW4_ESC_KEY_NONE);
    CHECK(feed_expect(&d, 0x1bu, 0u, 0, 0) == 0);
    CHECK(feed_expect(&d, (uint8_t)'[', 0u, 0, 0) == 0);
    CHECK(hw4_esc_decoder_finish(&d) == HW4_ESC_KEY_REJECTED);
    CHECK(feed_expect(&d, 0x1bu, 0u, 0, 0) == 0);
    CHECK(feed_expect(&d, (uint8_t)'O', 0u, 0, 0) == 0);
    CHECK(feed_expect(&d, (uint8_t)'\r', 1u, HW4_ESC_KEY_REJECTED, 0) == 0);
    CHECK(hw4_esc_decoder_finish(&d) == HW4_ESC_KEY_NONE);
    /* No partial output for invalid API invocation. */
    CHECK(hw4_esc_decoder_feed(NULL, 0x1bu, out) == 0u);
    CHECK(hw4_esc_decoder_feed(&d, 0x1bu, NULL) == 0u);
    CHECK(hw4_esc_decoder_release_pending(NULL) == HW4_ESC_KEY_NONE);
    CHECK(hw4_esc_decoder_finish(NULL) == HW4_ESC_KEY_NONE);
    CHECK(hw4_esc_route(NULL, HW4_ESC_KEY_ESCAPE) == HW4_ESC_ACTION_NONE);

    /* Negative differential: naive "ESC byte -> BREAK" is incorrect in two ways. */
    {
        const unsigned char ansi[] = { 0x1bu, '[', 'D' };
        unsigned int naive_breaks = 0u;
        unsigned int actual_breaks = 0u;
        hw4_esc_decoder_init(&d);
        for (i = 0u; i < sizeof(ansi); ++i) {
            size_t j, n = hw4_esc_decoder_feed(&d, ansi[i], out);
            if (ansi[i] == 0x1bu) ++naive_breaks;
            for (j = 0u; j < n; ++j) {
                if (hw4_esc_route(&phase, out[j]) == HW4_ESC_ACTION_BREAK_REQUEST)
                    ++actual_breaks;
            }
        }
        CHECK(naive_breaks == 1u && actual_breaks == 0u);
        CHECK(hw4_esc_decoder_finish(&d) == HW4_ESC_KEY_NONE);
        CHECK(hw4_esc_decoder_feed(&d, 0x1bu, out) == 0u);
        CHECK(hw4_esc_decoder_release_pending(&d) == HW4_ESC_KEY_ESCAPE);
        CHECK(hw4_esc_route(&phase, HW4_ESC_KEY_ESCAPE) == HW4_ESC_ACTION_PAUSE);
    }
    return 0;
}

int main(void)
{
    if (run_scenarios() != 0 || run_negative() != 0) return 1;
    puts("HW4-ESC-BREAK-A transport C99 scenarios + negative differential PASS (NOT CPC oracle)");
    return 0;
}
