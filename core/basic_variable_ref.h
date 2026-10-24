#ifndef BASIC_VARIABLE_REF_H
#define BASIC_VARIABLE_REF_H

#include <stddef.h>
#include <stdint.h>

/* J0.13: internal decoder statuses, not CPC BASIC error numbers. */
typedef enum {
    BVR_OK = 0,
    BVR_INVALID_ARGUMENT,
    BVR_UNRECOGNIZED_MARKER,
    BVR_MALFORMED,
    BVR_TRUNCATED,
    BVR_LIMIT_EXCEEDED,
    BVR_OVERLAPPING_MEMORY
} BVRStatus;

typedef enum {
    BVR_FAMILY_EXPLICIT = 0,
    BVR_FAMILY_UNSUFFIXED_OR_RESOLVED
} BVRFamily;

typedef enum {
    BVR_TYPE_UNDETERMINED = 0,
    BVR_TYPE_INTEGER,
    BVR_TYPE_STRING,
    BVR_TYPE_REAL
} BVRExplicitType;

#define BVR_MAX_NAME_LENGTH 40u

typedef struct {
    uint8_t marker;
    BVRFamily family;
    BVRExplicitType explicit_type;
    uint8_t cache_low;
    uint8_t cache_high;
    size_t reference_offset;
    size_t name_offset;
    size_t name_length;
    size_t consumed;
} BasicVariableRef;

/*
 * Decode a scalar CPC variable reference beginning at source[offset].
 * The reference is: marker, two uninterpreted CPC cache bytes (little-endian
 * order), 1..40 encoded name bytes with bit 7 set on the final byte.
 *
 * The caller owns a valid source array of source_length bytes and a valid
 * result object. Both must remain alive for this call. The result contains no
 * pointers; decoded name bytes remain only in the caller-owned source.
 *
 * The entire source range and result object must be disjoint. Overlap is
 * rejected (on the supported Linux/ESP32 integer-pointer representations).
 * On ANY non-OK status, *result and all source bytes remain unchanged.
 * On success only *result is assigned; source is never written.
 * No allocator, mutable global state, CPC pointer conversion or type lookup.
 *
 * Initial offset >= source_length and NULL arguments are invalid arguments;
 * missing fields/terminator within a valid starting range are truncated.
 * More than 40 name characters is a limit error when byte 41 is present.
 */
BVRStatus bvr_decode(const uint8_t *source, size_t source_length,
                     size_t offset, BasicVariableRef *result);

/*
 * Encode only explicit scalar references (02 INTEGER %, 03 STRING $,
 * 04 REAL !). name is the UNSUFFIXED byte sequence, with explicit length.
 * One letter followed by 0..39 letters/digits/dots; case is preserved.
 * The wire representation is marker, 00 00 CPC cache, name bytes with
 * bit 7 set ONLY on the last byte. Required capacity is 3 + name_length.
 *
 * All buffers and written must be disjoint, including unused destination
 * capacity. On error destination, name and *written are unchanged.
 * BVR_LIMIT_EXCEEDED means a name over 40 bytes or insufficient capacity;
 * BVR_MALFORMED means an empty/invalid name.
 * Neither this API nor bvr_decode converts a CPC cache to a host pointer.
 */
BVRStatus bvr_encode_explicit(const uint8_t *name, size_t name_length,
                              BVRExplicitType explicit_type,
                              uint8_t *destination, size_t destination_capacity,
                              size_t *written);

#endif
