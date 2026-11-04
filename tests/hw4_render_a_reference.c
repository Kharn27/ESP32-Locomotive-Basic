/* Frozen pre-RENDER-A generic pixel sampling, test/benchmark only.
 * Independent of the optimized MODE1 renderer; calls the unchanged
 * cpc_video_get() and cpc_video_palette_rgb565() from the baseline API.
 * Source: video/cpc_video.c at 21e95a7197413923bb5976067a0419bc729c20c1.
 * Do not simplify this reference or benchmark against the optimized path.
 */
#include "hw4_render_a_reference.h"
static unsigned reference_sampled_pen(const CpcVideo *v, unsigned x, unsigned y)
{
    unsigned lx = x;
    if (v->mode == CPC_MODE_0) lx /= 2U;
    if (v->mode == CPC_MODE_2) {
        lx = v->mode2_display == CPC_MODE2_VIEWPORT ? x + v->mode2_scroll_x : x * 2U;
    }
    uint8_t p = 0U;
    (void)cpc_video_get(v, lx, y, &p);
    if (v->mode == CPC_MODE_2 && v->mode2_display == CPC_MODE2_OR_PAIR) {
        uint8_t p2 = 0U;
        (void)cpc_video_get(v, lx + 1U, y, &p2);
        p = (uint8_t)(p | p2);
    }
    if (v->cursor_visible && y / 8U == v->cursor_row) {
        const unsigned start = (unsigned)v->cursor_column * 8U;
        const bool over = v->mode == CPC_MODE_2 &&
                          v->mode2_display == CPC_MODE2_OR_PAIR
                        ? (lx < start + 8U && lx + 1U >= start)
                        : (lx >= start && lx < start + 8U);
        if (over && v->pen != v->paper) {
            if (p == v->pen) p = v->paper;
            else if (p == v->paper) p = v->pen;
        }
    }
    return p;
}
bool hw4_render_a_reference(const CpcVideo *v, unsigned y,
                           uint16_t *out, size_t count)
{
    if (v == NULL || v->pixels == NULL || (unsigned)v->mode > 2U ||
        out == NULL || count < CPC_VIDEO_TFT_WIDTH ||
        y >= CPC_VIDEO_TFT_HEIGHT) return false;
    if (y < CPC_VIDEO_VIEW_TOP || y >= CPC_VIDEO_VIEW_TOP + CPC_VIDEO_VIEW_HEIGHT) {
        const uint16_t colour = cpc_video_palette_rgb565(v->border);
        for (unsigned x = 0; x < CPC_VIDEO_TFT_WIDTH; ++x) out[x] = colour;
    } else {
        unsigned ly = y - CPC_VIDEO_VIEW_TOP;
        for (unsigned x = 0; x < CPC_VIDEO_TFT_WIDTH; ++x)
            out[x] = cpc_video_palette_rgb565(v->ink[reference_sampled_pen(v,x,ly)]);
    }
    return true;
}
