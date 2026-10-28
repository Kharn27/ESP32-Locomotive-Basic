/* HW4-C3-B2: bounded, allocation-free MODE1 text stream and scrolling. MIT. */
#include "cpc_text.h"
#include <stdint.h>
#include <string.h>

bool cpc_text_init(CpcText *sink, CpcVideo *video,
                   CpcGlyphRow glyph, void *context)
{
    if (sink == NULL || video == NULL || glyph == NULL ||
        video->pixels == NULL || video->mode != CPC_MODE_1 ||
        cpc_video_columns(video) != 40U)
        return false;
    CpcText candidate;
    memset(&candidate, 0, sizeof(candidate));
    candidate.video = video;
    candidate.glyph = glyph;
    candidate.glyph_context = context;
    candidate.input_fnv1a = UINT32_C(2166136261);
    if (!cpc_video_cursor(video, 0U, 0U, true))
        return false;
    *sink = candidate;
    return true;
}

static bool advance(CpcText *sink)
{
    if (sink->row == 24U) {
        if (!cpc_video_scroll_up(sink->video, 1U)) return false;
        ++sink->scrolls;
    } else {
        ++sink->row;
    }
    sink->column = 0U;
    return true;
}

bool cpc_text_write(CpcText *sink, const uint8_t *bytes, size_t length)
{
    if (sink == NULL || sink->video == NULL || sink->glyph == NULL ||
        sink->video->pixels == NULL || sink->video->mode != CPC_MODE_1 ||
        sink->video->paper >= 4U || sink->video->pen >= 4U ||
        sink->video->cursor_row >= 25U || sink->video->cursor_column >= 40U ||
        (bytes == NULL && length != 0U) ||
        SIZE_MAX - sink->bytes_received < length ||
        SIZE_MAX - sink->glyphs_drawn < length ||
        SIZE_MAX - sink->controls_ignored < length ||
        SIZE_MAX - sink->scrolls < length ||
        sink->column > 40U || sink->row >= 25U)
        return false;

    for (size_t i = 0U; i < length; ++i) {
        const uint8_t ch = bytes[i];
        sink->input_fnv1a = (sink->input_fnv1a ^ (uint32_t)ch) *
                            UINT32_C(16777619);
        ++sink->bytes_received;
        if (ch == (uint8_t)'\r') {
            sink->column = 0U;
        } else if (ch == (uint8_t)'\n') {
            if (!advance(sink)) return false; /* prevalidated */
        } else if (ch >= 0x20U && ch <= 0x7eU) {
            if (sink->column == 40U && !advance(sink))
                return false; /* prevalidated */
            if (!cpc_video_put_cell(sink->video, sink->column, sink->row,
                                    ch, sink->glyph, sink->glyph_context))
                return false; /* prevalidated MODE1 and bounded glyph */
            ++sink->glyphs_drawn;
            ++sink->column;
        } else {
            ++sink->controls_ignored;
        }
    }

    /* Bottom-right pending wrap must not erase the final visible glyph:
     * its cursor is hidden until the next printable character or LF. */
    if (sink->row == 24U && sink->column == 40U)
        return cpc_video_cursor(sink->video, 0U, 24U, false);
    if (sink->column == 40U)
        return cpc_video_cursor(sink->video, 0U, sink->row + 1U, true);
    return cpc_video_cursor(sink->video, sink->column, sink->row, true);
}
