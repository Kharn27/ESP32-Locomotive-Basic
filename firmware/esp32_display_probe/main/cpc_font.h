/*
 * HW3 original minimal boot-message font (not an extracted CPC ROM).
 * SPDX-License-Identifier: MIT
 * See docs/HW3-cpc-display-spike.md for attribution and limits.
 */
#pragma once
#include <stdint.h>

/* Each row is eight pixels; most glyphs intentionally have a one-pixel margin.
 * Bit 7 is the leftmost pixel. All ASCII 0x20..0x7e are defined;
 * space alone is blank, and nonprintable ASCII remains blank.
 * ASCII DEL (0x7f) is an original 8x8 copyright-symbol glyph.
 */
uint8_t hw3_glyph_row(uint8_t character, unsigned int row);

/* One canonical glyph source for HW3 and HW4 callback-based MODE1 video.
 * This adapter carries no glyph data and does not alter the HW3 API. */
static inline uint8_t hw3_glyph_callback(void *context, uint8_t character,
                                          unsigned int row)
{
    (void)context;
    return hw3_glyph_row(character, row);
}
