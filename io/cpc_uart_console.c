/* HW4-C2 conservative 40x25 CPC-mode-1 UART echo; allocation-free. */
#include "cpc_uart_console.h"
#include <stddef.h>
static bool valid(const CpcText *text)
{
    return text != NULL && text->video != NULL && text->glyph != NULL &&
           text->video->pixels != NULL && text->video->mode == CPC_MODE_1 &&
           text->row <= 25U && text->column <= 40U;
}
bool cpc_uart_console_clear(CpcText *text)
{
    if (!valid(text)) return false;
    CpcVideo *video = text->video;
    CpcGlyphRow glyph = text->glyph;
    void *ctx = text->glyph_context;
    return cpc_video_set_mode(video, CPC_MODE_1) &&
           cpc_video_set_ink(video, 0U, 1U) &&
           cpc_video_set_ink(video, 1U, 24U) &&
           cpc_video_set_text_colors(video, 1U, 0U) &&
           cpc_text_init(text, video, glyph, ctx);
}
bool cpc_uart_console_prompt(CpcText *text, bool *reset_page)
{
    if (!valid(text) || reset_page == NULL) return false;
    *reset_page = false;
    if (text->column != 0U && text->row < 25U) {
        const uint8_t lf = (uint8_t)'\n';
        if (!cpc_text_write(text, &lf, 1U)) return false;
    }
    /* CPC has no artificial '>' input marker. Keep the cursor at col 0.
     * 120 editable ASCII bytes still require at most three text rows;
     * reserve four rows conservatively under the existing page policy. */
    if (text->row > 20U) {
        if (!cpc_uart_console_clear(text)) return false;
        *reset_page = true;
    }
    return cpc_video_cursor(text->video, text->column, text->row, true);
}
bool cpc_uart_console_append(CpcText *text, uint8_t ch)
{
    if (!valid(text) || ch < 0x20U || ch > 0x7eU ||
        text->row > 24U || (text->row == 24U && text->column >= 39U))
        return false;
    return cpc_text_write(text, &ch, 1U);
}
bool cpc_uart_console_backspace(CpcText *text)
{
    if (!valid(text) || text->row >= 25U) return false;
    unsigned col = text->column, row = text->row;
    if (col > 0U) {
        --col;
    } else {
        if (row == 0U) return false;
        --row;
        col = 39U; /* after a wrapped 40-column physical text row */
    }
    if (!cpc_video_put_cell(text->video, col, row, (uint8_t)' ',
                            text->glyph, text->glyph_context)) return false;
    text->column = col;
    text->row = row;
    return cpc_video_cursor(text->video, col, row, true);
}
bool cpc_uart_console_end_line(CpcText *text)
{
    static const uint8_t lf = (uint8_t)'\n';
    return valid(text) && cpc_text_write(text, &lf, 1U);
}
