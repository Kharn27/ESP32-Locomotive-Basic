#ifndef BASIC_LISTING_H
#define BASIC_LISTING_H

#include <stddef.h>
#include <stdint.h>
#include "basic_program.h"

/* J0.5 host-side diagnostics, not Locomotive BASIC error codes. */
typedef enum {
    BL_OK = 0,
    BL_INVALID_ARGUMENT,
    BL_NO_SPACE,
    BL_OVERFLOW,
    BL_OVERLAP,
    BL_UNKNOWN_TOKEN,
    BL_TRUNCATED,
    BL_BAD_SEQUENCE,
    BL_BAD_PROGRAM
} BLStatus;

/* Decode exactly body_length bytes, excluding the final CPC 00 marker.
 * On success *written is the number of bytes written, WITHOUT a NUL.
 * Inputs must remain immutable throughout the call. Source, destination,
 * and written may not overlap, even across unused destination capacity.
 * On any error destination and *written are unchanged.
 */
BLStatus bl_detokenize(const uint8_t *body, size_t body_length,
                       uint8_t *destination, size_t destination_capacity,
                       size_t *written);

/* Render a validated BasicProgram, in line-number order, as:
 * <decimal line> <decoded body>\n
 * No NUL terminator is appended. Each line gets exactly one prefix space,
 * without altering any spaces in its body. An empty program writes 0 bytes.
 * The program storage, output and written must not overlap. On any error,
 * the entire output buffer and *written remain unchanged.
 */
BLStatus bl_list_program(const BasicProgram *program,
                         uint8_t *destination, size_t destination_capacity,
                         size_t *written);

#endif
