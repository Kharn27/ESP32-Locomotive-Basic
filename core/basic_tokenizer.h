#ifndef BASIC_TOKENIZER_H
#define BASIC_TOKENIZER_H

#include <stddef.h>
#include <stdint.h>

/* J0.4 subset only. These are internal C status codes, NOT CPC error codes. */
typedef enum {
    BT_OK = 0,
    BT_INVALID_ARGUMENT,
    BT_NO_SPACE,
    BT_NUMBER_OUT_OF_RANGE,
    BT_UNSUPPORTED_CONSTRUCT,
    BT_MALFORMED_INPUT
} BTStatus;

/*
 * Tokenize exactly source_length bytes of a BASIC statement body.
 * The caller owns source and destination; neither is retained.
 *
 * The result excludes the line number and final 00 byte: bp_put appends it.
 * On failure destination (the entire buffer) and *written remain unchanged.
 * No dynamic allocation is performed. Source/destination storage and *written
 * must be distinct and non-overlapping, including destination_capacity bytes.
 * Both pointers must designate valid objects with the supplied extents.
 *
 * Embedded NUL, CR and LF are rejected, including within quoted strings.
 * An empty source succeeds with *written=0. Spaces are preserved byte-for-byte.
 * See docs/J0.4-basic-tokenizer.md for the deliberately narrow grammar.
 */
BTStatus bt_tokenize(const uint8_t *source, size_t source_length,
                     uint8_t *destination, size_t destination_capacity,
                     size_t *written);

#endif
