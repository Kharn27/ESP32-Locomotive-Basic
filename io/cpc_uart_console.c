/* HW4-C3-B2: MODE1 UART echo with native scroll; no auto-page reset. */
#include "cpc_uart_console.h"
#include <stddef.h>
static bool valid(const CpcText *text)
{
    return text != NULL && text->video != NULL && text->glyph != NULL &&
           text->video->pixels != NULL && text->video->mode == CPC_MODE_1 &&
           text->row < 25U && text->column <= 40U;
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
    if (text->column != 0U) {
        const uint8_t lf = (uint8_t)'\n';
        if (!cpc_text_write(text, &lf, 1U)) return false;
    }
    return cpc_video_cursor(text->video, text->column, text->row, true);
}
bool cpc_uart_console_append(CpcText *text, uint8_t ch)
{
    if (!valid(text) || ch < 0x20U || ch > 0x7eU) return false;
    return cpc_text_write(text, &ch, 1U);
}
bool cpc_uart_console_backspace(CpcText *text)
{
    if (!valid(text)) return false;
    unsigned col = text->column, row = text->row;
    if (col > 0U) {
        --col;
    } else {
        if (row == 0U) return false;
        --row;
        col = 39U;
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


/* HW4-EDIT-A: redraw only the changed suffix, never a second RGB buffer.
 * Rows are linear MODE1 cells; native scrolling shifts existing pixels and
 * the byte-zero anchor together when the edited text reaches row 25. */
bool cpc_uart_console_edit_begin(CpcText *text, CpcUartEditor *edit)
{
    if (!valid(text) || edit == NULL || text->column >= 40U)
        return false;
    edit->row = text->row;
    edit->column = text->column;
    edit->painted = 0U;
    return true;
}
bool cpc_uart_console_edit(CpcText *text, CpcUartEditor *edit,
                           const UartLine *line, size_t changed_from)
{
    if (!valid(text) || edit == NULL || line == NULL ||
        text->video->pen >= 4U || text->video->paper >= 4U ||
        edit->row >= 25U || edit->column >= 40U ||
        edit->painted > UART_LINE_CAPACITY ||
        line->length > UART_LINE_CAPACITY ||
        line->cursor_pos > line->length ||
        line->data[line->length] != 0U ||
        changed_from > line->length) return false;
    const size_t count = line->length > edit->painted ?
                         line->length : edit->painted;
    /* Number of rows that the old or new painted cells extend past row24.
     * Do not scroll just to display the pending cursor at column 40. */
    const size_t rightmost = count == 0U ? 0U :
                              (size_t)edit->column + count - 1U;
    const unsigned last_row = edit->row + (unsigned)(rightmost / 40U);
    if (last_row >= 25U) {
        const unsigned scroll = last_row - 24U;
        if (scroll > edit->row || !cpc_video_scroll_up(text->video,scroll))
            return false;
        edit->row -= scroll;
        text->scrolls += scroll;
    }
    for (size_t i = changed_from; i < count; ++i) {
        const unsigned absolute = edit->column + (unsigned)i;
        const unsigned row = edit->row + absolute / 40U;
        const unsigned column = absolute % 40U;
        const uint8_t ch = i < line->length ? line->data[i] : (uint8_t)' ';
        if (!cpc_video_put_cell(text->video,column,row,ch,
                                text->glyph,text->glyph_context))
            return false; /* all coordinates validated above */
    }
    edit->painted = line->length;
    /* Text sink points to the END of the physical edited line for LF and
     * subsequent BASIC output, not to the movable editor cursor. */
    const unsigned span = edit->column + (unsigned)line->length;
    if (span > 0U && span % 40U == 0U) {
        text->row = edit->row + span / 40U - 1U;
        text->column = 40U; /* deferred wrap in CpcText */
    } else {
        text->row = edit->row + span / 40U;
        text->column = span % 40U;
    }
    /* A cursor between characters at col40 belongs to the next row,
     * except at the physical bottom where the pending end cursor hides. */
    const unsigned point = edit->column + (unsigned)line->cursor_pos;
    const unsigned cursor_row = edit->row + point / 40U;
    if (cursor_row >= 25U)
        return cpc_video_cursor(text->video,0U,24U,false);
    return cpc_video_cursor(text->video,point % 40U,cursor_row,true);
}
