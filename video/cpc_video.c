#include "cpc_video.h"
#include <string.h>

#define ALL_DIRTY UINT32_C(0x01ffffff)
static const uint8_t initial_inks[16] = {
    1U,24U,20U,6U,26U,0U,2U,8U,10U,12U,14U,16U,18U,22U,1U,24U
};
static unsigned bits(CpcMode mode) { return 4U >> (unsigned)mode; }
static bool valid(const CpcVideo *v) { return v != NULL && v->pixels != NULL && (unsigned)v->mode <= 2U; }
unsigned cpc_video_width(const CpcVideo *v) { return valid(v) ? 160U << (unsigned)v->mode : 0U; }
unsigned cpc_video_columns(const CpcVideo *v) { return cpc_video_width(v) / 8U; }
unsigned cpc_video_colors(const CpcVideo *v) { return valid(v) ? 1U << bits(v->mode) : 0U; }

bool cpc_video_set_mode(CpcVideo *v, CpcMode mode)
{
    if (v == NULL || v->pixels == NULL || (unsigned)mode > 2U) return false;
    v->mode = mode;
    v->pen = 1U;
    v->paper = 0U;
    v->border = 1U;
    v->cursor_column = 0U;
    v->cursor_row = 0U;
    v->cursor_visible = false;
    v->mode2_display = CPC_MODE2_OR_PAIR;
    v->mode2_scroll_x = 0U;
    memcpy(v->ink, initial_inks, sizeof(v->ink));
    memset(v->pixels, 0, CPC_VIDEO_BYTES);
    v->dirty_bands = ALL_DIRTY;
    return true;
}
bool cpc_video_init(CpcVideo *v, uint8_t *pixels, size_t size, CpcMode mode)
{
    if (v == NULL || pixels == NULL || size < CPC_VIDEO_BYTES || (unsigned)mode > 2U) return false;
    memset(v, 0, sizeof(*v));
    v->pixels = pixels;
    return cpc_video_set_mode(v, mode);
}

/* Every mode has 80 bytes per raster line; left pixel in high bits. */
static size_t at(CpcMode mode, unsigned x, unsigned y)
{
    return (size_t)y * 80U + (size_t)(x / (8U / bits(mode)));
}
static unsigned shift(CpcMode mode, unsigned x)
{
    const unsigned b = bits(mode);
    return 8U - b - (x % (8U / b)) * b;
}
bool cpc_video_get(const CpcVideo *v, unsigned x, unsigned y, uint8_t *pen)
{
    if (!valid(v) || pen == NULL || x >= cpc_video_width(v) || y >= 200U) return false;
    const unsigned b = bits(v->mode);
    *pen = (uint8_t)(((unsigned)v->pixels[at(v->mode,x,y)] >> shift(v->mode,x)) & ((1U << b) - 1U));
    return true;
}
bool cpc_video_put(CpcVideo *v, unsigned x, unsigned y, unsigned pen)
{
    if (!valid(v) || x >= cpc_video_width(v) || y >= 200U || pen >= cpc_video_colors(v)) return false;
    const size_t offset = at(v->mode, x, y);
    const unsigned sh = shift(v->mode,x);
    const uint8_t mask = (uint8_t)((cpc_video_colors(v) - 1U) << sh);
    v->pixels[offset] = (uint8_t)((v->pixels[offset] & (uint8_t)~mask) | (uint8_t)(pen << sh));
    v->dirty_bands |= UINT32_C(1) << (y / 8U);
    return true;
}
bool cpc_video_set_ink(CpcVideo *v, unsigned pen, unsigned colour)
{
    if (!valid(v) || pen >= 16U || colour >= 27U) return false;
    v->ink[pen] = (uint8_t)colour;
    v->dirty_bands = ALL_DIRTY;
    return true;
}
bool cpc_video_set_border(CpcVideo *v, unsigned colour)
{
    if (!valid(v) || colour >= 27U) return false;
    v->border = (uint8_t)colour;
    /* Border is outside logical dirty bands; caller must repaint margins. */
    return true;
}
bool cpc_video_set_text_colors(CpcVideo *v, unsigned pen, unsigned paper)
{
    if (!valid(v) || pen >= cpc_video_colors(v) || paper >= cpc_video_colors(v)) return false;
    /* Reverse-video overlay depends on both current PEN and PAPER, even
     * though a colour change never rewrites the stored raster.
     */
    if (v->cursor_visible && (v->pen != pen || v->paper != paper))
        v->dirty_bands |= UINT32_C(1) << v->cursor_row;
    v->pen = (uint8_t)pen;
    v->paper = (uint8_t)paper;
    return true;
}
bool cpc_video_put_cell(CpcVideo *v, unsigned column, unsigned row,
                        uint8_t ch, CpcGlyphRow glyph, void *context)
{
    if (!valid(v) || glyph == NULL || column >= cpc_video_columns(v) || row >= 25U) return false;
    for (unsigned dy = 0; dy < 8U; ++dy) {
        const uint8_t image = glyph(context, ch, dy);
        for (unsigned dx = 0; dx < 8U; ++dx) {
            unsigned colour = (image & (uint8_t)(0x80U >> dx)) != 0U ? v->pen : v->paper;
            (void)cpc_video_put(v, 8U * column + dx, 8U * row + dy, colour);
        }
    }
    return true;
}
bool cpc_video_cursor(CpcVideo *v, unsigned column, unsigned row, bool visible)
{
    if (!valid(v) || column >= cpc_video_columns(v) || row >= 25U) return false;
    v->dirty_bands |= UINT32_C(1) << v->cursor_row;
    v->cursor_column = (uint8_t)column;
    v->cursor_row = (uint8_t)row;
    v->cursor_visible = visible;
    v->dirty_bands |= UINT32_C(1) << row;
    return true;
}
bool cpc_video_mode2_display(CpcVideo *v, CpcMode2Display display, unsigned left)
{
    if (!valid(v) || (unsigned)display > 2U || (display == CPC_MODE2_VIEWPORT && left > 320U)) return false;
    if (v->mode != CPC_MODE_2) return false;
    v->mode2_display = display;
    v->mode2_scroll_x = (uint16_t)(display == CPC_MODE2_VIEWPORT ? left : 0U);
    v->dirty_bands = ALL_DIRTY;
    return true;
}
static unsigned sampled_pen(const CpcVideo *v, unsigned x, unsigned y)
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
        /* Overlay AFTER MODE0 scaling / MODE2 compositing, without changing
         * VRAM. Exchange only current text PEN/PAPER. Other ink indices are
         * graphics and must not be inverted as if they were text pixels.
         * Identical PEN/PAPER cannot produce a visible inverse.
         */
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
bool cpc_video_render_row(const CpcVideo *v, unsigned y, uint16_t *out, size_t count)
{
    if (!valid(v) || out == NULL || count < CPC_VIDEO_TFT_WIDTH || y >= CPC_VIDEO_TFT_HEIGHT) return false;
    if (y < CPC_VIDEO_VIEW_TOP || y >= CPC_VIDEO_VIEW_TOP + CPC_VIDEO_VIEW_HEIGHT) {
        const uint16_t colour = cpc_video_palette_rgb565(v->border);
        for (unsigned x = 0; x < CPC_VIDEO_TFT_WIDTH; ++x) out[x] = colour;
    } else {
        unsigned ly = y - CPC_VIDEO_VIEW_TOP;
        for (unsigned x = 0; x < CPC_VIDEO_TFT_WIDTH; ++x)
            out[x] = cpc_video_palette_rgb565(v->ink[sampled_pen(v,x,ly)]);
    }
    return true;
}
uint32_t cpc_video_take_dirty(CpcVideo *v)
{
    if (!valid(v)) return 0U;
    uint32_t result = v->dirty_bands;
    v->dirty_bands = 0U;
    return result;
}

/* HW4-C3-B2: MODE1 raster layout is linear, not CPC Z80 interleaved VRAM. */
bool cpc_video_scroll_up(CpcVideo *v, unsigned rows)
{
    if (!valid(v) || v->mode != CPC_MODE_1 || v->paper >= 4U ||
        rows > 25U || v->cursor_row >= 25U || v->cursor_column >= 40U)
        return false;
    if (rows == 0U) return true;
    const size_t shift_bytes = (size_t)rows * 640U;
    const size_t retained = CPC_VIDEO_BYTES - shift_bytes;
    const uint8_t paper = (uint8_t)(v->paper * UINT8_C(0x55));
    if (retained != 0U)
        memmove(v->pixels, v->pixels + shift_bytes, retained);
    memset(v->pixels + retained, paper, shift_bytes);
    v->dirty_bands |= ALL_DIRTY;
    return true;
}

bool cpc_video_flush_dirty(CpcVideo *v, CpcVideoBandSender send, void *ctx)
{
    if (!valid(v) || send == NULL) return false;
    uint32_t pending = cpc_video_take_dirty(v);
    for (unsigned band = 0U; band < 25U; ++band) {
        const uint32_t bit = UINT32_C(1) << band;
        if ((pending & bit) == 0U) continue;
        if (!send(ctx, band)) {
            /* Includes the failed band, excludes bands actually transferred.
             * Any new dirties set by the callback remain intact. */
            v->dirty_bands |= pending;
            return false;
        }
        pending &= ~bit;
    }
    return true;
}
