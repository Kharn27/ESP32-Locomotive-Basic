/* HW4-EDIT-B1-A: the existing video task remains the sole LCD/DMA owner.
 * Scroll quantity ONE ROW per complete arrow CSI is HOST POLICY ONLY;
 * the true CPC 6128 number of rows per key is unverified. */
#include "cpc_screen_nav.h"
#include <stddef.h>
void cpc_screen_nav_init(CpcScreenNavigation *nav)
{
    if (nav != NULL) nav->anchor_valid = true;
}
static bool valid(const CpcScreenNavigation *nav, const CpcText *text,
                  const CpcUartEditor *edit, const UartLine *line)
{
    return nav != NULL && text != NULL && edit != NULL && line != NULL &&
           text->video != NULL && text->video->pixels != NULL &&
           text->video->mode == CPC_MODE_1 &&
           text->row < 25U && text->column <= 40U &&
           edit->row < 25U && edit->column < 40U &&
           edit->painted <= UART_LINE_CAPACITY &&
           line->length <= UART_LINE_CAPACITY &&
           line->cursor_pos <= line->length &&
           line->data[line->length] == 0U;
}
static void adjust_scroll(CpcScreenNavigation *nav, CpcText *text,
                          CpcUartEditor *edit, const UartLine *line,
                          bool image_up)
{
    if (image_up) {
        if (text->row == 0U) nav->anchor_valid = false;
        else --text->row;
        if (nav->anchor_valid) {
            if (edit->row == 0U) nav->anchor_valid = false;
            else --edit->row;
        }
    } else {
        if (text->row == 24U) nav->anchor_valid = false;
        else ++text->row;
        if (nav->anchor_valid) {
            /* The cursor slot at column 40 also belongs to the edited line.
             * If any portion will leave the screen, invalidate the anchor. */
            const size_t end = (size_t)edit->column + line->length;
            const unsigned last = edit->row + (unsigned)(end / 40U);
            if (last >= 24U) nav->anchor_valid = false;
            else ++edit->row;
        }
    }
    if (!nav->anchor_valid) {
        /* Explicit refocus will reprint only E3 into this blank row.
         * Never reconstruct or submit characters taken from E2. */
        text->row = image_up ? 24U : 0U;
        text->column = 0U;
    }
}
bool cpc_screen_nav_move(CpcScreenNavigation *nav, CpcText *text,
                         CpcUartEditor *edit, const UartLine *line,
                         UartLineEvent event)
{
    if (!valid(nav,text,edit,line)) return false;
    CpcVideo *v = text->video;
    unsigned row = v->cursor_row, col = v->cursor_column;
    if (row >= 25U || col >= 40U) return false;
    bool image_up = false, image_down = false;
    switch (event) {
    case UART_LINE_NAV_UP:
        if (row == 0U) image_down = true;
        else --row;
        break;
    case UART_LINE_NAV_DOWN:
        if (row == 24U) image_up = true;
        else ++row;
        break;
    case UART_LINE_NAV_LEFT:
        if (col > 0U) --col;
        else if (row > 0U) { --row; col = 39U; }
        break;
    case UART_LINE_NAV_RIGHT:
        if (col < 39U) ++col;
        else if (row < 24U) { ++row; col = 0U; }
        break;
    default:
        return false;
    }
    if (image_up && !cpc_video_scroll_up(v,1U)) return false;
    if (image_down && !cpc_video_scroll_down(v,1U)) return false;
    if (image_up || image_down)
        adjust_scroll(nav,text,edit,line,image_up);
    return cpc_video_cursor(v,col,row,true);
}
/* C1: ENTER is a CR/LF from the currently visible E1 cursor,
 * NOT a return to the (possibly scrolled-away) CpcText/E3 old anchor.
 * Restore the exact E3 buffer at column zero of the next row.
 * HOME remains separate and keeps the old refocus semantics. */
bool cpc_screen_nav_resume(CpcScreenNavigation *nav, CpcText *text,
                           CpcUartEditor *edit, const UartLine *line)
{
    if (!valid(nav,text,edit,line) || text->glyph == NULL) return false;
    CpcVideo *v = text->video;
    if (v->cursor_row >= 25U || v->cursor_column >= 40U) return false;
    unsigned target_row = v->cursor_row;
    if (target_row == 24U) {
        if (!cpc_video_scroll_up(v,1U)) return false;
        ++text->scrolls;
    } else {
        ++target_row;
    }
    text->row = target_row;
    text->column = 0U; /* CpcText 40 is deferred wrap, not an E1 column. */
    nav->anchor_valid = false;
    if (!cpc_uart_console_edit_begin(text,edit)) return false;
    /* Even if an older E3 fragment remains on screen, that is now E2
     * display only. Never recover it as input, repaint only from E3. */
    if (!cpc_uart_console_edit(text,edit,line,0U)) return false;
    nav->anchor_valid = true;
    return true;
}
bool cpc_screen_nav_home(CpcScreenNavigation *nav, CpcText *text,
                         CpcUartEditor *edit, const UartLine *line)
{
    if (!valid(nav,text,edit,line)) return false;
    if (!nav->anchor_valid) {
        if (text->column == 40U) text->column = 0U;
        if (!cpc_uart_console_edit_begin(text,edit)) return false;
        nav->anchor_valid = true;
        if (!cpc_uart_console_edit(text,edit,line,0U)) {
            nav->anchor_valid = false;
            return false;
        }
        return true;
    }
    return cpc_uart_console_edit(text,edit,line,line->length);
}
