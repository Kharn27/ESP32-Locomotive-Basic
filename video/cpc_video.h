/* Portable, caller-owned CPC video surface; not a Z80 memory image. MIT. */
#ifndef CPC_VIDEO_H
#define CPC_VIDEO_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define CPC_VIDEO_BYTES 16000U
#define CPC_VIDEO_TFT_WIDTH 320U
#define CPC_VIDEO_TFT_HEIGHT 240U
#define CPC_VIDEO_VIEW_TOP 20U
#define CPC_VIDEO_VIEW_HEIGHT 200U

typedef enum { CPC_MODE_0 = 0, CPC_MODE_1 = 1, CPC_MODE_2 = 2 } CpcMode;
typedef enum {
    CPC_MODE2_OR_PAIR = 0, /* preserve any bright pixel in each pair */
    CPC_MODE2_EVEN = 1,    /* left pixel of each pair */
    CPC_MODE2_VIEWPORT = 2 /* 320 consecutive logical pixels at 1:1 */
} CpcMode2Display;
typedef uint8_t (*CpcGlyphRow)(void *ctx, uint8_t character, unsigned row);
typedef struct {
    uint8_t *pixels; /* exactly CPC_VIDEO_BYTES bytes supplied by caller */
    CpcMode mode;
    CpcMode2Display mode2_display;
    uint16_t mode2_scroll_x; /* 0..320 when displaying a MODE2 viewport */
    uint8_t ink[16]; /* CPC firmware colour indices 0..26 */
    uint8_t pen;
    uint8_t paper;
    uint8_t border;
    uint8_t cursor_column;
    uint8_t cursor_row;
    bool cursor_visible;
    uint32_t dirty_bands; /* bit i = logical raster rows 8*i..8*i+7 */
} CpcVideo;

bool cpc_video_init(CpcVideo *video, uint8_t *pixels, size_t length, CpcMode mode);
bool cpc_video_set_mode(CpcVideo *video, CpcMode mode);
unsigned cpc_video_width(const CpcVideo *video);
unsigned cpc_video_columns(const CpcVideo *video);
unsigned cpc_video_colors(const CpcVideo *video);
bool cpc_video_put(CpcVideo *video, unsigned x, unsigned y, unsigned pen);
bool cpc_video_get(const CpcVideo *video, unsigned x, unsigned y, uint8_t *pen);
bool cpc_video_set_ink(CpcVideo *video, unsigned pen, unsigned colour);
bool cpc_video_set_border(CpcVideo *video, unsigned colour);
bool cpc_video_set_text_colors(CpcVideo *video, unsigned pen, unsigned paper);
bool cpc_video_put_cell(CpcVideo *video, unsigned column, unsigned row,
                        uint8_t character, CpcGlyphRow glyph, void *context);
bool cpc_video_cursor(CpcVideo *video, unsigned column, unsigned row, bool visible);
bool cpc_video_mode2_display(CpcVideo *video, CpcMode2Display display, unsigned left);
/* Exactly width=320 colours; y is absolute TFT y in [0,239]. No allocation. */
bool cpc_video_render_row(const CpcVideo *video, unsigned y,
                          uint16_t *rgb565, size_t pixel_capacity);
/* MODE1 only: move raster rows up in the linear 16000-byte surface.
 * 0 rows is a no-op; 1..25 are valid; invalid calls change nothing. */
bool cpc_video_scroll_up(CpcVideo *video, unsigned rows);
/* Drain dirty bands in ascending order. On callback failure, restore the
 * failed band and every not-yet-sent band for a subsequent retry. */
typedef bool (*CpcVideoBandSender)(void *context, unsigned band);
bool cpc_video_flush_dirty(CpcVideo *video, CpcVideoBandSender send,
                           void *context);
uint32_t cpc_video_take_dirty(CpcVideo *video);
uint16_t cpc_video_palette_rgb565(unsigned colour); /* 0xffff for invalid */
void cpc_video_palette_rgb888(unsigned colour, uint8_t rgb[3]);
#endif
