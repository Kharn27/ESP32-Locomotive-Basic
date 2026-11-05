/* HW4-DISP-RENDER-A: frozen reference vs production renderer, RGB565 EXACT.
 * Full 320x240 comparison, no mocks; the original generic decoder is
 * compiled independently from tests/hw4_render_a_reference.c.
 */
#include "hw4_render_a_reference.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t vram[CPC_VIDEO_BYTES + 2U];
static uint8_t saved[CPC_VIDEO_BYTES];
static uint16_t reference_pixels[322U];
static uint16_t optimized_pixels[322U];
static uint64_t rows_checked;
static uint64_t pixels_checked;
static uint32_t random_state = UINT32_C(0x91bd7423);

static uint32_t next_random(void)
{
    random_state ^= random_state << 13U;
    random_state ^= random_state >> 17U;
    random_state ^= random_state << 5U;
    return random_state;
}
static void compare_row(const CpcVideo *v, unsigned y, const char *case_name)
{
    for (unsigned x = 0U; x < 322U; ++x) {
        reference_pixels[x] = UINT16_C(0x6a5b);
        optimized_pixels[x] = UINT16_C(0x6a5b);
    }
    const bool a = hw4_render_a_reference(v, y, reference_pixels + 1U, 320U);
    const bool b = cpc_video_render_row(v, y, optimized_pixels + 1U, 320U);
    if (!a || !b) {
        fprintf(stderr, "RENDER_A FALSE_RETURN case=%s y=%u reference=%d fast=%d\n",
                case_name, y, (int)a, (int)b);
        exit(1);
    }
    for (unsigned x = 0U; x < 320U; ++x) {
        if (reference_pixels[x + 1U] != optimized_pixels[x + 1U]) {
            fprintf(stderr, "RENDER_A PIXEL_DIFF case=%s mode=%u y=%u x=%u "
                    "ref=%04x new=%04x\n", case_name, (unsigned)v->mode,
                    y, x, (unsigned)reference_pixels[x + 1U],
                    (unsigned)optimized_pixels[x + 1U]);
            exit(1);
        }
    }
    assert(reference_pixels[0] == UINT16_C(0x6a5b) &&
           optimized_pixels[0] == UINT16_C(0x6a5b));
    assert(reference_pixels[321] == UINT16_C(0x6a5b) &&
           optimized_pixels[321] == UINT16_C(0x6a5b));
    ++rows_checked;
    pixels_checked += 320U;
}
static void compare_full(const CpcVideo *v, const char *case_name)
{
    memcpy(saved, v->pixels, CPC_VIDEO_BYTES);
    for (unsigned y = 0U; y < CPC_VIDEO_TFT_HEIGHT; ++y)
        compare_row(v, y, case_name);
    assert(memcmp(saved, v->pixels, CPC_VIDEO_BYTES) == 0);
}
static uint8_t glyph(void *ignored, uint8_t ch, unsigned row)
{
    (void)ignored;
    return (uint8_t)((((unsigned)ch * 37U + row * 29U) ^ (0xa5U >> (row % 4U))) & 255U);
}
static void setup(CpcVideo *v, CpcMode mode)
{
    memset(vram, 0xa5, sizeof vram);
    assert(cpc_video_init(v, vram + 1U, CPC_VIDEO_BYTES, mode));
    assert(vram[0] == 0xa5U && vram[CPC_VIDEO_BYTES + 1U] == 0xa5U);
}
static void test_mode1_uniform_and_inks(void)
{
    CpcVideo v;
    setup(&v, CPC_MODE_1);
    for (unsigned p = 0U; p < 4U; ++p) {
        memset(v.pixels, (int)(p * 0x55U), CPC_VIDEO_BYTES);
        for (unsigned ink = 0U; ink < 27U; ++ink) {
            for (unsigned k = 0U; k < 4U; ++k)
                assert(cpc_video_set_ink(&v, k, (ink + 7U * k) % 27U));
            assert(cpc_video_set_border(&v, (ink * 11U) % 27U));
            assert(cpc_video_set_text_colors(&v, p, (p + 1U) % 4U));
            assert(cpc_video_cursor(&v, ink % 40U, ink % 25U, ink % 2U == 0U));
            compare_full(&v, "uniform_27_inks_border_cursor");
        }
    }
}
static void test_mode1_all_bytes_and_text(void)
{
    CpcVideo v;
    setup(&v, CPC_MODE_1);
    for (unsigned i = 0U; i < CPC_VIDEO_BYTES; ++i)
        v.pixels[i] = (uint8_t)(i & 255U);
    assert(cpc_video_set_text_colors(&v, 1U, 0U));
    assert(cpc_video_cursor(&v, 39U, 24U, true));
    compare_full(&v, "all_256_vram_bytes_cursor_edge");
    assert(cpc_video_cursor(&v, 0U, 0U, true));
    compare_full(&v, "all_bytes_cursor_top_left");
    assert(cpc_video_cursor(&v, 0U, 0U, false));
    compare_full(&v, "all_bytes_cursor_hidden");

    for (unsigned row = 0U; row < 25U; ++row)
        for (unsigned col = 0U; col < 40U; ++col) {
            const uint8_t ch = (uint8_t)((col * 37U + row * 19U) & 255U);
            assert(cpc_video_put_cell(&v, col, row, ch, glyph, NULL));
        }
    assert(cpc_video_cursor(&v, 17U, 12U, true));
    compare_full(&v, "dense_real_put_cell");
    assert(cpc_video_scroll_up(&v, 1U));
    compare_full(&v, "scroll_up_1");
    assert(cpc_video_scroll_down(&v, 2U));
    compare_full(&v, "scroll_down_2");
    assert(cpc_video_scroll_up(&v, 25U));
    compare_full(&v, "scroll_up_25");
}
typedef struct {
    CpcVideo *v;
    unsigned expected;
    unsigned count;
    bool reject;
} BandContext;
static bool compare_band(void *arg, unsigned band)
{
    BandContext *c = (BandContext *)arg;
    assert(band == c->expected + c->count);
    for (unsigned dy = 0U; dy < 8U; ++dy)
        compare_row(c->v, CPC_VIDEO_VIEW_TOP + band * 8U + dy, "dirty_band");
    ++c->count;
    return !c->reject;
}
static void test_dirty_partial_full(void)
{
    CpcVideo v;
    setup(&v, CPC_MODE_1);
    for (unsigned i = 0U; i < CPC_VIDEO_BYTES; ++i)
        v.pixels[i] = (uint8_t)(next_random() & 255U);
    BandContext ctx = {&v, 0U, 0U, false};
    assert(cpc_video_flush_dirty(&v, compare_band, &ctx));
    assert(ctx.count == 25U && cpc_video_take_dirty(&v) == 0U);
    assert(cpc_video_put(&v, 7U, 8U * 9U + 2U, 3U));
    assert(v.dirty_bands == (UINT32_C(1) << 9U));
    ctx.expected = 9U; ctx.count = 0U; ctx.reject = true;
    assert(!cpc_video_flush_dirty(&v, compare_band, &ctx));
    assert(v.dirty_bands == (UINT32_C(1) << 9U));
    ctx.count = 0U; ctx.reject = false;
    assert(cpc_video_flush_dirty(&v, compare_band, &ctx));
    assert(ctx.count == 1U && v.dirty_bands == 0U);
    assert(cpc_video_set_ink(&v, 0U, 26U));
    assert(v.dirty_bands == UINT32_C(0x01ffffff));
    ctx.expected = 0U; ctx.count = 0U;
    assert(cpc_video_flush_dirty(&v, compare_band, &ctx));
    assert(ctx.count == 25U && v.dirty_bands == 0U);
}
static void test_random_multimode(void)
{
    CpcVideo v;
    for (unsigned mode = 0U; mode < 3U; ++mode) {
        setup(&v, (CpcMode)mode);
        for (unsigned iter = 0U; iter < 30U; ++iter) {
            for (unsigned i = 0U; i < CPC_VIDEO_BYTES; ++i)
                v.pixels[i] = (uint8_t)(next_random() & 255U);
            for (unsigned ink = 0U; ink < 16U; ++ink)
                assert(cpc_video_set_ink(&v, ink, next_random() % 27U));
            assert(cpc_video_set_border(&v, next_random() % 27U));
            const unsigned colours = cpc_video_colors(&v);
            const unsigned pen = next_random() % colours;
            const unsigned paper = next_random() % colours;
            assert(cpc_video_set_text_colors(&v, pen, paper));
            if (mode == 2U) {
                const unsigned disp = iter % 3U;
                const unsigned left = disp == 2U ?
                        (iter % 4U == 0U ? 0U : iter % 4U == 1U ? 1U :
                         iter % 4U == 2U ? 319U : 320U) : 0U;
                assert(cpc_video_mode2_display(&v, (CpcMode2Display)disp, left));
            }
            const unsigned columns = cpc_video_columns(&v);
            assert(cpc_video_cursor(&v, next_random() % columns,
                                    next_random() % 25U, (iter & 1U) != 0U));
            compare_full(&v, mode == 0U ? "MODE0_random" :
                             mode == 1U ? "MODE1_random" : "MODE2_random_submodes");
        }
    }
}
static void test_negative_and_boundary(void)
{
    CpcVideo v;
    setup(&v, CPC_MODE_1);
    uint16_t out[322U];
    for (unsigned i = 0U; i < 322U; ++i) out[i] = UINT16_C(0x6a5b);
    assert(!cpc_video_render_row(&v, 20U, out + 1U, 319U));
    assert(!hw4_render_a_reference(&v, 20U, out + 1U, 319U));
    assert(!cpc_video_render_row(&v, 240U, out + 1U, 320U));
    assert(!hw4_render_a_reference(&v, 240U, out + 1U, 320U));
    assert(!cpc_video_render_row(&v, 20U, NULL, 320U));
    assert(!hw4_render_a_reference(&v, 20U, NULL, 320U));
    assert(!cpc_video_render_row(NULL, 20U, out + 1U, 320U));
    assert(!hw4_render_a_reference(NULL, 20U, out + 1U, 320U));
    for (unsigned i = 0U; i < 322U; ++i)
        assert(out[i] == UINT16_C(0x6a5b));
    assert(!cpc_video_set_ink(&v, 4U, 27U));
    assert(!cpc_video_set_text_colors(&v, 4U, 0U));
    assert(!cpc_video_cursor(&v, 40U, 24U, true));
    /* Directly corrupting the public column to 40 cannot cause an OOB
     * overlay; the frozen generic path simply finds no covered pixels. */
    v.cursor_column = 40U;
    v.cursor_visible = true;
    compare_full(&v, "cursor_outside_ignored");
    assert(vram[0] == 0xa5U && vram[CPC_VIDEO_BYTES + 1U] == 0xa5U);
}
int main(void)
{
    test_mode1_uniform_and_inks();
    test_mode1_all_bytes_and_text();
    test_dirty_partial_full();
    test_random_multimode();
    test_negative_and_boundary();
    printf("HW4-DISP-RENDER-A PIXEL_EXACT=PASS diff_pixels=0 "
           "rows=%" PRIu64 " pixels=%" PRIu64 " MODE0_MODE1_MODE2=PASS "
           "cursor_border_dirty_scroll=PASS VRAM_BYTES=16000\n",
           rows_checked, pixels_checked);
    return 0;
}
