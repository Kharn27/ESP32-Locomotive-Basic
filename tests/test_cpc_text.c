/* HW4-C1 portable adversarial tests: no LCD or CPC fixtures involved. */
#include "cpc_text.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint8_t before[8];
    uint8_t vram[CPC_VIDEO_BYTES];
    uint8_t after[8];
} Guarded;

static Guarded guarded;
static CpcVideo video;
static CpcText text_sink;

static uint8_t glyph(void *context, uint8_t ch, unsigned row)
{
    (void)context;
    /* Synthetic signature: printable glyph has one pixel at x0 in row0. */
    return row == 0U && ch != (uint8_t)' ' ? 0x80U : 0U;
}

static uint32_t digest(const uint8_t *data, size_t length)
{
    uint32_t hash = UINT32_C(2166136261);
    for (size_t i = 0U; i < length; ++i)
        hash = (hash ^ (uint32_t)data[i]) * UINT32_C(16777619);
    return hash;
}

static void integrity(void)
{
    for (size_t i = 0U; i < 8U; ++i) {
        assert(guarded.before[i] == 0xa5U);
        assert(guarded.after[i] == 0x5aU);
    }
}

static void reset(void)
{
    memset(&guarded, 0, sizeof(guarded));
    memset(guarded.before, 0xa5, 8U);
    memset(guarded.after, 0x5a, 8U);
    assert(cpc_video_init(&video, guarded.vram, sizeof(guarded.vram), CPC_MODE_1));
    assert(cpc_video_set_ink(&video, 0U, 1U));
    assert(cpc_video_set_ink(&video, 1U, 24U));
    assert(cpc_video_set_text_colors(&video, 1U, 0U));
    assert(cpc_text_init(&text_sink, &video, glyph, NULL));
}

static void pixel(unsigned x, unsigned y, uint8_t expected)
{
    uint8_t actual = 255U;
    assert(cpc_video_get(&video, x, y, &actual));
    assert(actual == expected);
}

static void test_print(void)
{
    static const uint8_t output[] = {' ', '5', ' ', '\n'};
    reset();
    assert(cpc_text_write(&text_sink, output, sizeof(output)));
    assert(text_sink.bytes_received == sizeof(output));
    assert(text_sink.input_fnv1a == digest(output, sizeof(output)));
    assert(text_sink.glyphs_drawn == 3U);
    assert(text_sink.column == 0U && text_sink.row == 1U);
    assert(video.cursor_column == 0U && video.cursor_row == 1U &&
           video.cursor_visible);
    pixel(8U, 0U, 1U);  /* '5' drawn from raw second byte */
    pixel(0U, 0U, 0U);  /* leading space preserved */
    assert((cpc_video_take_dirty(&video) & 3U) == 3U);
    assert(cpc_video_take_dirty(&video) == 0U);
    integrity();
}

static void test_crlf(void)
{
    static const uint8_t data[] = {'X','\r','Z','\r','\n','Y',1U,0x7fU};
    reset();
    assert(cpc_text_write(&text_sink, data, sizeof(data)));
    assert(text_sink.row == 1U && text_sink.column == 1U);
    assert(text_sink.controls_ignored == 2U);
    pixel(0U, 0U, 1U);
    pixel(0U, 8U, 1U);
    assert(text_sink.input_fnv1a == digest(data, sizeof(data)));
    integrity();
}

static void test_wrap_and_bottom(void)
{
    static uint8_t buffer[40U * 25U + 8U];
    memset(buffer, 'X', sizeof(buffer));
    reset();
    assert(cpc_text_write(&text_sink, buffer, 40U));
    assert(text_sink.row == 0U && text_sink.column == 40U);
    assert(video.cursor_row == 1U && video.cursor_column == 0U);
    assert(cpc_text_write(&text_sink, buffer, 1U));
    assert(text_sink.row == 1U && text_sink.column == 1U);
    reset();
    assert(cpc_text_write(&text_sink, buffer, 40U * 25U));
    assert(text_sink.row == 24U && text_sink.column == 40U);
    assert(!video.cursor_visible);
    const uint8_t original = guarded.vram[CPC_VIDEO_BYTES - 1U];
    assert(cpc_text_write(&text_sink, buffer, 8U));
    assert(text_sink.row == 25U && text_sink.bytes_clipped == 8U);
    assert(guarded.vram[CPC_VIDEO_BYTES - 1U] == original);
    assert(!video.cursor_visible);
    integrity();
}

static void test_partial_and_fail(void)
{
    static const uint8_t one[] = {'A','B','C'};
    reset();
    assert(cpc_text_write(&text_sink, one, 1U));
    assert(cpc_text_write(&text_sink, one + 1U, 2U));
    assert(text_sink.input_fnv1a == digest(one, sizeof(one)));
    assert(!cpc_text_write(&text_sink, NULL, 1U));
    assert(text_sink.bytes_received == 3U);
    assert(cpc_text_write(&text_sink, NULL, 0U));
    assert(!cpc_text_init(NULL, &video, glyph, NULL));
    assert(!cpc_text_init(&text_sink, NULL, glyph, NULL));
    integrity();
}

int main(void)
{
    test_print();
    test_crlf();
    test_wrap_and_bottom();
    test_partial_and_fail();
    puts("HW4-C1 text adapter PASS");
    return 0;
}
