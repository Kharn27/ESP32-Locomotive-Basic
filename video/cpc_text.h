/* HW4-C1: bounded text sink between native BASIC bytes and CPC VRAM. MIT. */
#ifndef CPC_TEXT_H
#define CPC_TEXT_H
#include "cpc_video.h"

typedef struct {
    CpcVideo *video;           /* borrowed, exclusively owned by the rendering task */
    CpcGlyphRow glyph;
    void *glyph_context;
    unsigned column;           /* 0..40; 40 means wrap pending */
    unsigned row;              /* 0..24; bottom overflow scrolls MODE1 */
    size_t bytes_received;     /* every input byte, including ignored controls */
    size_t glyphs_drawn;
    size_t bytes_clipped;     /* retained ABI counter; normal MODE1 scroll never clips */
    size_t scrolls;           /* completed one-cell vertical scroll operations */
    size_t controls_ignored;
    uint32_t input_fnv1a;      /* digest of unmodified incoming BASIC bytes */
} CpcText;

/* Video must already be in MODE 1. The cursor is a non-destructive overlay.
 * The caller owns both video and memory. No malloc or LCD access here. */
bool cpc_text_init(CpcText *sink, CpcVideo *video,
                   CpcGlyphRow glyph, void *context);

/* Processes exactly length bytes (no NUL scanning).
 * ASCII 0x20..0x7e draws glyphs; CR resets column; LF advances one row
 * and resets column (CRLF therefore advances once). Unknown controls are
 * counted and ignored, printable characters absent from the font draw blank.
 * At 40 columns, wrap is pending until another printable character arrives.
 * In B2, a deferred wrap or LF at bottom moves the linear VRAM up
 * one text row, preserving the scroll counter, digest and non-destructive
 * cursor. A pending column 40 alone does not scroll until progression.
 * Failure on invalid arguments/overflow occurs before any mutation. */
bool cpc_text_write(CpcText *sink, const uint8_t *bytes, size_t length);
#endif
