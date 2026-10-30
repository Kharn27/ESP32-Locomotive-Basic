#include "hw4_pen_bridge.h"
#include "cpc_uart_console.h"
#include <stdint.h>

Hw4PenStatus hw4_pen_pixel_index(const CpcVideo *video, uint8_t logical,
                                  uint8_t *pixel)
{
    if (video == NULL || video->pixels == NULL || pixel == NULL ||
        video->mode != CPC_MODE_1 || video->paper >= 4U)
        return HW4_PEN_INVALID_ARGUMENT;
    if (logical <= 3U) {
        *pixel = logical;
        return HW4_PEN_OK;
    }
    if (logical == 4U) {
        /* Observed invisible black-on-black: on the existing CYD boot
         * INK0=1 yields blue-on-blue instead. These are the ONLY two
         * explicitly bounded contexts for this approximation. */
        if (video->paper != 0U ||
            (video->ink[0] != 0U && video->ink[0] != 1U))
            return HW4_PEN_UNVERIFIED_VISUAL;
        *pixel = 0U;
        return HW4_PEN_OK;
    }
    if (logical == 15U) {
        if (video->ink[3] != 18U)
            return HW4_PEN_UNVERIFIED_VISUAL;
        *pixel = 3U;
        return HW4_PEN_OK;
    }
    return HW4_PEN_UNSUPPORTED_LOGICAL;
}

Hw4PenStatus hw4_pen_preflight(const CpcText *sink,
                               const uint8_t *print_bytes, size_t byte_count,
                               const BEVideoEvent *events, size_t event_count)
{
    const CpcVideo *video;
    size_t previous = 0U;
    size_t i;
    if (sink == NULL || sink->video == NULL || sink->glyph == NULL ||
        (print_bytes == NULL && byte_count != 0U) ||
        (events == NULL && event_count != 0U))
        return HW4_PEN_INVALID_ARGUMENT;
    video = sink->video;
    if (video->pixels == NULL || video->mode != CPC_MODE_1 ||
        video->pen >= 4U || video->paper >= 4U ||
        video->cursor_column >= 40U || video->cursor_row >= 25U ||
        sink->column > 40U || sink->row >= 25U ||
        SIZE_MAX - sink->bytes_received < byte_count ||
        SIZE_MAX - sink->glyphs_drawn < byte_count ||
        SIZE_MAX - sink->controls_ignored < byte_count ||
        SIZE_MAX - sink->scrolls < byte_count)
        return HW4_PEN_TEXT_PRECHECK_FAILED;
    for (i = 0U; i < event_count; ++i) {
        uint8_t pixel = 0U;
        Hw4PenStatus status;
        /* Reject J1.18-B INK before any PEN or PRINT slice is rendered. */
        if (events[i].type == BE_VIDEO_SET_INK)
            return HW4_PEN_SET_INK_UNSUPPORTED;
        if (events[i].type != BE_VIDEO_SET_TEXT_PEN)
            return HW4_PEN_INVALID_EVENT;
        if (events[i].print_offset < previous ||
            events[i].print_offset > byte_count)
            return HW4_PEN_BAD_OFFSET;
        status = hw4_pen_pixel_index(video, events[i].pen, &pixel);
        if (status != HW4_PEN_OK) return status;
        previous = events[i].print_offset;
    }
    return HW4_PEN_OK;
}

Hw4PenStatus hw4_pen_replay(CpcText *sink,
                            const uint8_t *print_bytes, size_t byte_count,
                            const BEVideoEvent *events, size_t event_count)
{
    size_t cursor = 0U;
    size_t i;
    Hw4PenStatus status = hw4_pen_preflight(sink, print_bytes, byte_count,
                                            events, event_count);
    if (status != HW4_PEN_OK) return status;
    for (i = 0U; i < event_count; ++i) {
        uint8_t pixel = 0U;
        const size_t next = events[i].print_offset;
        /* Already validated; no output slice passes an invalid event. */
        if (next != cursor &&
            !cpc_text_write(sink, print_bytes + cursor, next - cursor))
            return HW4_PEN_RENDER_FAILED;
        status = hw4_pen_pixel_index(sink->video, events[i].pen, &pixel);
        if (status != HW4_PEN_OK) return HW4_PEN_RENDER_FAILED;
        if (!cpc_video_set_text_colors(sink->video, pixel, sink->video->paper))
            return HW4_PEN_RENDER_FAILED;
        cursor = next;
    }
    if (byte_count != cursor &&
        !cpc_text_write(sink, print_bytes + cursor, byte_count - cursor))
        return HW4_PEN_RENDER_FAILED;
    return HW4_PEN_OK;
}

/* C1: CONSOLE-specific palette restoration after the real UART clear.
 * cpc_uart_console_clear() resets MODE1 and INK0/INK1; the PEN display
 * integration owns the additional explicit INK2=6 and INK3=18. Neither
 * core nor the generic UART/video layer adopts a global palette policy. */
bool hw4_pen_console_clear(CpcText *text)
{
    if (!cpc_uart_console_clear(text)) return false;
    return cpc_video_set_ink(text->video, 2U, 6U) &&
           cpc_video_set_ink(text->video, 3U, 18U);
}
