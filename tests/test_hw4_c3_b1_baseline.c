/* HW4-C3-B1 original probes evolved in B2: scrolling regression, not CPC oracle.
 * Compile directly in the dedicated CI job; no runtime/CMake mutation.
 */
#include "cpc_uart_console.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct {
    uint8_t before[8];
    uint8_t pixels[CPC_VIDEO_BYTES];
    uint8_t after[8];
} Guard;
static Guard storage;
static CpcVideo video;
static CpcText text;
static uint8_t glyph(void *context, uint8_t ch, unsigned row)
{
    (void)context;
    return (row == 0U && ch != (uint8_t)' ') ? UINT8_C(0x80) : 0U;
}
static void guarded(void)
{
    for (size_t i = 0U; i < 8U; ++i) {
        assert(storage.before[i] == UINT8_C(0xa5));
        assert(storage.after[i] == UINT8_C(0x5a));
    }
}
static void setup(void)
{
    memset(&storage, 0, sizeof(storage));
    memset(storage.before, 0xa5, sizeof(storage.before));
    memset(storage.after, 0x5a, sizeof(storage.after));
    assert(cpc_video_init(&video, storage.pixels, CPC_VIDEO_BYTES, CPC_MODE_1));
    assert(cpc_video_set_ink(&video, 0U, 1U));
    assert(cpc_video_set_ink(&video, 1U, 24U));
    assert(cpc_video_set_text_colors(&video, 1U, 0U));
    assert(cpc_text_init(&text, &video, glyph, NULL));
    assert(cpc_video_take_dirty(&video) == UINT32_C(0x01ffffff));
}
static void pending_wrap_and_cr(void)
{
    uint8_t chars[40];
    uint8_t p = 9U;
    bool reset = false;
    memset(chars, 'X', sizeof(chars));
    setup();
    assert(cpc_text_write(&text, chars, sizeof(chars)));
    assert(text.row == 0U && text.column == 40U);
    assert(video.cursor_row == 1U && video.cursor_column == 0U);
    assert(cpc_video_get(&video, 312U, 0U, &p) && p == 1U);
    assert(cpc_text_write(&text, chars, 1U));
    assert(text.row == 1U && text.column == 1U);
    assert(cpc_video_get(&video, 0U, 8U, &p) && p == 1U);
    {
        const uint8_t cr = (uint8_t)'\r';
        assert(cpc_text_write(&text, &cr, 1U));
    }
    assert(text.row == 1U && text.column == 0U);
    assert(cpc_uart_console_prompt(&text, &reset) && !reset);
    assert(text.row == 1U && text.column == 0U);
    guarded();
}
static void artificial_reset_at_21(void)
{
    uint8_t lfs[21];
    uint8_t existing_program[] = {0x11U,0U,10U,0U,0x98U,0U,0U,0U};
    uint8_t original[sizeof(existing_program)];
    uint8_t p = 0xffU;
    bool reset = false;
    memset(lfs, '\n', sizeof(lfs));
    memcpy(original, existing_program, sizeof(original));
    setup();
    assert(cpc_video_put(&video, 10U, 0U, 1U));
    assert(cpc_text_write(&text, lfs, sizeof(lfs)));
    assert(text.row == 21U && text.column == 0U);
    assert(cpc_uart_console_prompt(&text, &reset));
    assert(!reset);  /* B2: no arbitrary four-row page reserve */
    assert(text.row == 21U && text.column == 0U);
    assert(text.bytes_received == sizeof(lfs));
    assert(cpc_video_get(&video, 10U, 0U, &p) && p == 1U);
    assert(memcmp(original, existing_program, sizeof(original)) == 0);
    assert((cpc_video_take_dirty(&video) & (UINT32_C(1) << 21U)) != 0U);
    guarded();
}
static void clipped_after_last_row(void)
{
    uint8_t lfs[24];
    uint8_t chars[40];
    bool reset = false;
    memset(lfs, '\n', sizeof(lfs));
    memset(chars, 'X', sizeof(chars));
    setup();
    assert(cpc_text_write(&text, lfs, sizeof(lfs)));
    assert(text.row == 24U && text.column == 0U);
    assert(cpc_text_write(&text, chars, sizeof(chars)));
    assert(text.row == 24U && text.column == 40U);
    assert(!video.cursor_visible);
    assert(cpc_uart_console_append(&text, (uint8_t)'Q'));
    assert(text.row == 24U && text.column == 1U && text.scrolls == 1U);
    assert(cpc_text_write(&text, chars, 2U));
    assert(text.row == 24U && text.column == 3U && text.bytes_clipped == 0U);
    assert(cpc_uart_console_prompt(&text, &reset) && !reset);
    assert(text.row == 24U && text.column == 0U && text.scrolls == 2U);
    guarded();
}
int main(void)
{
    pending_wrap_and_cr();
    artificial_reset_at_21();
    clipped_after_last_row();
    puts("HW4-C3-B2 B1 host probes migrated to scrolling; NOT CPC pixel proof");
    return 0;
}
