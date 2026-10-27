#include "cpc_video.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static uint8_t pixels[CPC_VIDEO_BYTES + 2U];
static uint16_t line[322];
static uint8_t glyph(void *ctx, uint8_t ch, unsigned row)
{ (void)ctx; (void)ch; return row == 0U ? 0xffU : 0x81U; }
/* C2: a visible cursor overlays the VRAM using live PEN, so only its
 * raster band must be dirtied when that colour index changes. Repeat in
 * all three modes; expected TFT x depends on horizontal scaling. */
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

    /* Same PEN and changed PAPER do not change the cursor overlay. */
    assert(cpc_video_set_text_colors(&v, 0U, 0U));
    assert(cpc_video_take_dirty(&v) == 0U);
    assert(cpc_video_set_text_colors(&v, 0U, 1U));
    assert(cpc_video_take_dirty(&v) == 0U);
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

int main(void)
{
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
        assert(line[1] == 0xffe0);
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
