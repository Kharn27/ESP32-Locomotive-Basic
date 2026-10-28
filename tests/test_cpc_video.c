#include "cpc_video.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static uint8_t pixels[CPC_VIDEO_BYTES + 2U];
static uint16_t line[322];
static uint8_t glyph(void *ctx, uint8_t ch, unsigned row)
{ (void)ctx; (void)ch; return row == 0U ? 0xffU : 0x81U; }
/* A visible reverse-video cursor depends on both live PEN and PAPER.
 * Dirty only the cursor band on a text-colour change, in all modes. */
static void test_cursor_pen_dirty(CpcMode mode)
{
    CpcVideo v;
    static uint8_t saved[CPC_VIDEO_BYTES];
    const unsigned column = 3U;
    const unsigned row = 9U;
    const unsigned logical_x = column * 8U;
    const unsigned display_x = mode == CPC_MODE_0 ? logical_x * 2U :
                               mode == CPC_MODE_1 ? logical_x : logical_x / 2U;
    const unsigned physical_y = CPC_VIDEO_VIEW_TOP + row * 8U + 3U;
    const uint32_t cursor_band = UINT32_C(1) << row;
    assert(cpc_video_init(&v, pixels + 1U, CPC_VIDEO_BYTES, mode));
    assert(cpc_video_take_dirty(&v) == UINT32_C(0x01ffffff));
    assert(cpc_video_take_dirty(&v) == 0U);
    assert(cpc_video_cursor(&v, column, row, true));
    assert(cpc_video_take_dirty(&v) == (cursor_band | UINT32_C(1)));
    assert(cpc_video_take_dirty(&v) == 0U);
    memcpy(saved, pixels + 1U, sizeof(saved));
    assert(cpc_video_render_row(&v, physical_y, line + 1, 320));
    assert(line[1U + display_x] == UINT16_C(0xffe0)); /* old cursor PEN 1 */

    assert(cpc_video_set_text_colors(&v, 0U, 0U));
    assert(v.pen == 0U && v.paper == 0U);
    assert(v.dirty_bands == cursor_band);
    assert(cpc_video_render_row(&v, physical_y, line + 1, 320));
    assert(line[1U + display_x] == UINT16_C(0x0010)); /* new cursor PEN 0 */
    assert(memcmp(saved, pixels + 1U, sizeof(saved)) == 0);
    assert(cpc_video_take_dirty(&v) == cursor_band);
    assert(cpc_video_take_dirty(&v) == 0U);

    /* Changing PAPER alone repaints the cursor: the blank stored pixel
     * equals PEN=0, so its displayed index changes to PAPER=1. */
    assert(cpc_video_set_text_colors(&v, 0U, 0U));
    assert(cpc_video_take_dirty(&v) == 0U);
    assert(cpc_video_set_text_colors(&v, 0U, 1U));
    assert(cpc_video_take_dirty(&v) == cursor_band);
    assert(cpc_video_render_row(&v, physical_y, line + 1, 320));
    assert(line[1U + display_x] == UINT16_C(0xffe0));
    assert(!cpc_video_set_text_colors(&v, cpc_video_colors(&v), 0U));
    assert(cpc_video_take_dirty(&v) == 0U);
    assert(v.pen == 0U && v.paper == 1U);

    assert(cpc_video_cursor(&v, column, row, false));
    assert(cpc_video_take_dirty(&v) == cursor_band);
    assert(cpc_video_set_text_colors(&v, 1U, 0U));
    assert(cpc_video_take_dirty(&v) == 0U);
    assert(cpc_video_render_row(&v, physical_y, line + 1, 320));
    assert(line[1U + display_x] == UINT16_C(0x0010)); /* unchanged VRAM */
    assert(memcmp(saved, pixels + 1U, sizeof(saved)) == 0);

    /* The last legal band must remain representable by the 25-bit mask. */
    assert(cpc_video_cursor(&v, column, 24U, true));
    assert(cpc_video_take_dirty(&v) == ((UINT32_C(1) << 24U) | cursor_band));
    assert(cpc_video_set_text_colors(&v, 0U, 0U));
    assert(cpc_video_take_dirty(&v) == (UINT32_C(1) << 24U));
    assert(cpc_video_take_dirty(&v) == 0U);
    assert(memcmp(saved, pixels + 1U, sizeof(saved)) == 0);
    assert(pixels[0] == 0xaa && pixels[CPC_VIDEO_BYTES + 1U] == 0xaa);
}


/* HW4-EDIT-A-C1 negative oracle: under a visible cursor an existing glyph
 * must remain visible with foreground and background exchanged. The old
 * opaque overlay painted both pixels with PEN and fails these assertions. */
static void test_cursor_inverse_red(void)
{
    CpcVideo v;
    static uint8_t saved[CPC_VIDEO_BYTES];
    memset(pixels, 0xa5, sizeof pixels);
    assert(cpc_video_init(&v, pixels + 1U, CPC_VIDEO_BYTES, CPC_MODE_1));
    assert(cpc_video_put_cell(&v, 3U, 4U, 'R', glyph, NULL));
    memcpy(saved, pixels + 1U, sizeof saved);
    assert(cpc_video_cursor(&v, 3U, 4U, true));
    assert(cpc_video_render_row(&v, CPC_VIDEO_VIEW_TOP + 4U * 8U + 1U,
                                line + 1U, 320U));
    /* glyph row 1 is 0x81: x=0 is PEN, x=1 is PAPER. */
    assert(line[1U + 24U] == UINT16_C(0x0010)); /* PEN glyph -> PAPER */
    assert(line[1U + 25U] == UINT16_C(0xffe0)); /* PAPER -> PEN */
    assert(memcmp(saved, pixels + 1U, sizeof saved) == 0);
    assert(pixels[0] == 0xa5U && pixels[CPC_VIDEO_BYTES + 1U] == 0xa5U);
}


/* C1 regression: real per-pixel inverse for a mixed glyph, mode 0 x2,
 * mode 1 x1, and all three MODE2 display transformations.
 * Cursor movement/hiding must never change the underlying 16000 bytes. */
static void test_cursor_inverse_modes(CpcMode mode, CpcMode2Display display)
{
    CpcVideo v;
    static uint8_t saved[CPC_VIDEO_BYTES];
    const unsigned col = 3U, row = 9U, lx = 8U * col;
    unsigned fg_x, bg_x, empty_x;
    if (mode == CPC_MODE_0) {
        fg_x = 2U * lx; bg_x = fg_x + 4U; empty_x = fg_x + 16U;
    } else if (mode == CPC_MODE_1 || display == CPC_MODE2_VIEWPORT) {
        fg_x = lx; bg_x = fg_x + 2U; empty_x = fg_x + 8U;
    } else {
        fg_x = lx / 2U; bg_x = fg_x + 1U; empty_x = fg_x + 4U;
    }
    const unsigned physical_y = CPC_VIDEO_VIEW_TOP + row * 8U + 3U;

    memset(pixels, 0xa5, sizeof pixels);
    assert(cpc_video_init(&v, pixels + 1U, CPC_VIDEO_BYTES, mode));
    if (mode == CPC_MODE_2)
        assert(cpc_video_mode2_display(&v, display, 0U));
    assert(cpc_video_put_cell(&v, col, row, 'R', glyph, NULL));
    memcpy(saved, pixels + 1U, sizeof saved);
    assert(cpc_video_take_dirty(&v) != 0U);
    assert(cpc_video_render_row(&v, physical_y, line + 1U, 320U));
    assert(line[1U + fg_x] == UINT16_C(0xffe0));
    assert(line[1U + bg_x] == UINT16_C(0x0010));

    assert(cpc_video_cursor(&v, col, row, true));
    assert(cpc_video_take_dirty(&v) ==
           ((UINT32_C(1) << 0U) | (UINT32_C(1) << row)));
    assert(cpc_video_render_row(&v, physical_y, line + 1U, 320U));
    assert(line[1U + fg_x] == UINT16_C(0x0010)); /* glyph stays legible */
    assert(line[1U + bg_x] == UINT16_C(0xffe0));
    assert(memcmp(saved, pixels + 1U, sizeof saved) == 0);

    /* Moving onto a blank cell restores the glyph without a raster write. */
    assert(cpc_video_cursor(&v, col + 1U, row, true));
    assert(cpc_video_take_dirty(&v) == (UINT32_C(1) << row));
    assert(cpc_video_render_row(&v, physical_y, line + 1U, 320U));
    assert(line[1U + fg_x] == UINT16_C(0xffe0));
    assert(line[1U + bg_x] == UINT16_C(0x0010));
    assert(line[1U + empty_x] == UINT16_C(0xffe0)); /* empty => solid */
    assert(memcmp(saved, pixels + 1U, sizeof saved) == 0);
    assert(cpc_video_cursor(&v, col + 1U, row, false));
    assert(cpc_video_take_dirty(&v) == (UINT32_C(1) << row));
    assert(cpc_video_render_row(&v, physical_y, line + 1U, 320U));
    assert(line[1U + empty_x] == UINT16_C(0x0010));

    /* Changing both row and column dirties both bands, including row 24. */
    assert(cpc_video_cursor(&v, cpc_video_columns(&v) - 1U, 24U, true));
    assert(cpc_video_take_dirty(&v) ==
           ((UINT32_C(1) << row) | (UINT32_C(1) << 24U)));
    assert(cpc_video_cursor(&v, cpc_video_columns(&v) - 1U, 24U, false));
    assert(cpc_video_take_dirty(&v) == (UINT32_C(1) << 24U));
    assert(memcmp(saved, pixels + 1U, sizeof saved) == 0);
    assert(pixels[0] == 0xa5U && pixels[CPC_VIDEO_BYTES + 1U] == 0xa5U);
}

/* Only PEN/PAPER are exchanged; a third ink is never blindly inverted.
 * In particular an isolated PAPER change must dirty the visible cursor.
 * PEN==PAPER is an explicitly non-visible, non-destructive edge case. */
static void test_cursor_inverse_palette_mode1(void)
{
    CpcVideo v;
    static uint8_t saved[CPC_VIDEO_BYTES];
    const unsigned col = 2U, row = 7U, y = row * 8U + 3U;
    const uint32_t band = UINT32_C(1) << row;
    memset(pixels, 0xa5, sizeof pixels);
    assert(cpc_video_init(&v, pixels + 1U, CPC_VIDEO_BYTES, CPC_MODE_1));
    assert(cpc_video_put_cell(&v, col, row, 'R', glyph, NULL));
    assert(cpc_video_put(&v, col * 8U + 4U, y, 3U)); /* unrelated ink */
    memcpy(saved, pixels + 1U, sizeof saved);
    assert(cpc_video_take_dirty(&v) != 0U);
    assert(cpc_video_cursor(&v, col, row, true));
    assert(cpc_video_take_dirty(&v) != 0U);
    assert(cpc_video_render_row(&v, CPC_VIDEO_VIEW_TOP + y, line + 1U, 320U));
    assert(line[1U + col * 8U] == cpc_video_palette_rgb565(v.ink[0]));
    assert(line[1U + col * 8U + 2U] == cpc_video_palette_rgb565(v.ink[1]));
    assert(line[1U + col * 8U + 4U] == cpc_video_palette_rgb565(v.ink[3]));
    assert(cpc_video_set_text_colors(&v, 1U, 2U));
    assert(cpc_video_take_dirty(&v) == band);
    assert(cpc_video_render_row(&v, CPC_VIDEO_VIEW_TOP + y, line + 1U, 320U));
    assert(line[1U + col * 8U] == cpc_video_palette_rgb565(v.ink[2]));
    assert(line[1U + col * 8U + 2U] == cpc_video_palette_rgb565(v.ink[0]));
    assert(line[1U + col * 8U + 4U] == cpc_video_palette_rgb565(v.ink[3]));
    assert(cpc_video_set_text_colors(&v, 1U, 0U));
    assert(cpc_video_take_dirty(&v) == band);
    assert(cpc_video_set_text_colors(&v, 2U, 0U)); /* changed PEN alone */
    assert(cpc_video_take_dirty(&v) == band);
    assert(cpc_video_render_row(&v, CPC_VIDEO_VIEW_TOP + y, line + 1U, 320U));
    assert(line[1U + col * 8U] == cpc_video_palette_rgb565(v.ink[1]));
    assert(line[1U + col * 8U + 2U] == cpc_video_palette_rgb565(v.ink[2]));
    assert(cpc_video_set_text_colors(&v, 0U, 0U)); /* no visible inverse */
    assert(cpc_video_take_dirty(&v) == band);
    assert(cpc_video_render_row(&v, CPC_VIDEO_VIEW_TOP + y, line + 1U, 320U));
    assert(line[1U + col * 8U] == cpc_video_palette_rgb565(v.ink[1]));
    assert(line[1U + col * 8U + 2U] == cpc_video_palette_rgb565(v.ink[0]));
    assert(cpc_video_set_text_colors(&v, 0U, 0U));
    assert(cpc_video_take_dirty(&v) == 0U);
    assert(!cpc_video_set_text_colors(&v, 4U, 0U));
    assert(cpc_video_take_dirty(&v) == 0U);
    assert(cpc_video_set_ink(&v, 0U, 3U));
    assert(cpc_video_take_dirty(&v) == UINT32_C(0x01ffffff));
    assert(cpc_video_render_row(&v, CPC_VIDEO_VIEW_TOP + y, line + 1U, 320U));
    assert(line[1U + col * 8U + 2U] == cpc_video_palette_rgb565(3U));
    assert(cpc_video_cursor(&v, col, row, false));
    assert(cpc_video_take_dirty(&v) == band);
    assert(memcmp(saved, pixels + 1U, sizeof saved) == 0);
    assert(pixels[0] == 0xa5U && pixels[CPC_VIDEO_BYTES + 1U] == 0xa5U);
}

int main(void)
{
    test_cursor_inverse_red();
    test_cursor_inverse_modes(CPC_MODE_0, CPC_MODE2_OR_PAIR);
    test_cursor_inverse_modes(CPC_MODE_1, CPC_MODE2_OR_PAIR);
    test_cursor_inverse_modes(CPC_MODE_2, CPC_MODE2_OR_PAIR);
    test_cursor_inverse_modes(CPC_MODE_2, CPC_MODE2_EVEN);
    test_cursor_inverse_modes(CPC_MODE_2, CPC_MODE2_VIEWPORT);
    test_cursor_inverse_palette_mode1();
    CpcVideo v;
    assert(!cpc_video_init(&v, pixels, CPC_VIDEO_BYTES - 1U, CPC_MODE_1));
    for (unsigned mode = 0; mode < 3U; ++mode) {
        memset(pixels, 0xaa, sizeof(pixels));
        assert(cpc_video_init(&v, pixels + 1U, CPC_VIDEO_BYTES, (CpcMode)mode));
        assert(pixels[0] == 0xaa && pixels[CPC_VIDEO_BYTES + 1U] == 0xaa);
        const unsigned w = 160U << mode, max = mode == 0U ? 16U : mode == 1U ? 4U : 2U;
        assert(cpc_video_width(&v) == w && cpc_video_columns(&v) == w / 8U);
        assert(cpc_video_colors(&v) == max);
        uint8_t p = 255;
        assert(cpc_video_put(&v, 0, 0, max-1U));
        assert(cpc_video_put(&v, w-1U, 199, max-1U));
        assert(cpc_video_get(&v, 0, 0, &p) && p == max-1U);
        assert(cpc_video_get(&v, w-1U, 199, &p) && p == max-1U);
        assert(!cpc_video_put(&v,w,0,1) && !cpc_video_put(&v,0,200,1));
        assert(!cpc_video_put(&v,0,0,max) && !cpc_video_get(&v,w,0,&p));
        assert(pixels[0] == 0xaa && pixels[CPC_VIDEO_BYTES + 1U] == 0xaa);
        assert(cpc_video_set_text_colors(&v, 1, 0));
        assert(cpc_video_put_cell(&v, 0, 0, 'X', glyph, NULL));
        assert(cpc_video_get(&v, 0, 0, &p) && p == 1U);
        assert(cpc_video_get(&v, 1, 1, &p) && p == 0U);
        assert(!cpc_video_put_cell(&v, w/8U,0,'X',glyph,NULL));
        assert(cpc_video_render_row(&v,0,line+1U,320));
        assert(line[1] == 0x0010 && line[320] == 0x0010);
        assert(cpc_video_render_row(&v,239,line+1U,320));
        assert(line[1] == 0x0010 && line[320] == 0x0010);
        assert(cpc_video_render_row(&v,20,line+1U,320));
        assert(line[1] == 0xffe0);
        assert(cpc_video_render_row(&v,219,line+1U,320));
        assert(line[0] == 0 && line[321] == 0);
        uint8_t snapshot[CPC_VIDEO_BYTES];
        memcpy(snapshot, pixels+1, sizeof(snapshot));
        assert(cpc_video_cursor(&v,0,0,true));
        assert(cpc_video_render_row(&v,21,line+1,320));
        assert(line[1] == 0x0010); /* glyph foreground reversed to PAPER */
        assert(cpc_video_cursor(&v,0,0,false));
        assert(memcmp(snapshot,pixels+1,sizeof(snapshot))==0);
        assert(cpc_video_render_row(&v,21,line+1,320));
        assert(line[3] == 0x0010); /* restored glyph background */
        assert(cpc_video_take_dirty(&v)!=0 && cpc_video_take_dirty(&v)==0);
        assert(cpc_video_set_ink(&v,1,6));
        assert(cpc_video_render_row(&v,20,line+1,320));
        assert(line[1] == 0xf800);
        assert(cpc_video_set_mode(&v,(CpcMode)mode));
        assert(pixels[1] == 0 && pixels[CPC_VIDEO_BYTES] == 0);
        assert(v.pen == 1 && v.paper == 0 && v.cursor_visible == false);
    }
    for (unsigned mode = 0U; mode < 3U; ++mode) {
        memset(pixels, 0xaa, sizeof(pixels));
        test_cursor_pen_dirty((CpcMode)mode);
    }
    assert(cpc_video_palette_rgb565(24)==0xffe0);
    assert(cpc_video_palette_rgb565(1)==0x0010);
    assert(cpc_video_palette_rgb565(26)==0xffff);
    assert(cpc_video_palette_rgb565(27)==0xffff);
    assert(cpc_video_init(&v,pixels+1,CPC_VIDEO_BYTES,CPC_MODE_2));
    assert(cpc_video_put(&v,1,20,1));
    assert(cpc_video_render_row(&v,40,line+1,320) && line[1] == 0xffe0);
    assert(cpc_video_mode2_display(&v,CPC_MODE2_EVEN,0));
    assert(cpc_video_render_row(&v,40,line+1,320) && line[1] == 0x0010);
    assert(cpc_video_mode2_display(&v,CPC_MODE2_VIEWPORT,1));
    assert(cpc_video_render_row(&v,40,line+1,320) && line[1] == 0xffe0);
    assert(!cpc_video_mode2_display(&v,CPC_MODE2_VIEWPORT,321));
    assert(!cpc_video_render_row(&v,240,line+1,320));
    puts("HW4-A C99 video PASS");
    return 0;
}
