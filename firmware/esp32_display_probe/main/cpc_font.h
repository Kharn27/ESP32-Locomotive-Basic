/*
 * HW3 original minimal boot-message font (not an extracted CPC ROM).
 * SPDX-License-Identifier: MIT
 * See docs/HW3-cpc-display-spike.md for attribution and limits.
 */
#pragma once
#include <stdint.h>

/* Each row is eight pixels; most glyphs intentionally have a one-pixel margin.
 * Bit 7 is the leftmost pixel. Unused ASCII code points render blank.
 * ASCII DEL (0x7f) is an original 8x8 copyright-symbol glyph.
 */
uint8_t hw3_glyph_row(uint8_t character, unsigned int row);
