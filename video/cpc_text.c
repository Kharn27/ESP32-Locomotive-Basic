/* HW4-C1: portable, allocation-free BASIC output adapter. MIT. */
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

bool cpc_text_write(CpcText *sink, const uint8_t *bytes, size_t length)
{
    if (sink == NULL || sink->video == NULL || sink->glyph == NULL ||
        sink->video->pixels == NULL || sink->video->mode != CPC_MODE_1 ||
        (bytes == NULL && length != 0U) ||
        SIZE_MAX - sink->bytes_received < length ||
        sink->column > 40U || sink->row > 25U)
        return false;

    for (size_t i = 0U; i < length; ++i) {
        const uint8_t ch = bytes[i];
        sink->input_fnv1a = (sink->input_fnv1a ^ (uint32_t)ch) *
                            UINT32_C(16777619);
        ++sink->bytes_received;
        if (ch == (uint8_t)'\r') {
            sink->column = 0U;
        } else if (ch == (uint8_t)'\n') {
            sink->column = 0U;
            if (sink->row < 25U) ++sink->row;
        } else if (ch >= 0x20U && ch <= 0x7eU) {
            if (sink->column == 40U) {
                sink->column = 0U;
                if (sink->row < 25U) ++sink->row;
            }
            if (sink->row == 25U) {
                ++sink->bytes_clipped;
            } else {
                if (!cpc_video_put_cell(sink->video, sink->column,
                                        sink->row, ch, sink->glyph,
                                        sink->glyph_context))
                    return false; /* unreachable for initialized MODE 1 */
                ++sink->glyphs_drawn;
                ++sink->column;
            }
        } else {
            ++sink->controls_ignored;
        }
    }

    /* Cursor only changes VRAM's dirty mask; never overwrites glyph pixels. */
    if (sink->row == 25U || (sink->row == 24U && sink->column == 40U)) {
        return cpc_video_cursor(sink->video, 0U, 24U, false);
    }
    if (sink->column == 40U)
        return cpc_video_cursor(sink->video, 0U, sink->row + 1U, true);
    return cpc_video_cursor(sink->video, sink->column, sink->row, true);
}
