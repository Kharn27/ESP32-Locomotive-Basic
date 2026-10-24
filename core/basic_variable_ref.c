#include "basic_variable_ref.h"

/* The supported C99 targets (Linux and ESP32) both provide uintptr_t. */
static int ranges_overlap(const void *a, size_t a_size,
                          const void *b, size_t b_size)
{
    uintptr_t x = (uintptr_t)a;
    uintptr_t y = (uintptr_t)b;
    if (a_size == 0u || b_size == 0u) {
        return 0;
    }
    /* Difference rather than endpoint addition avoids integer wraparound. */
    return x <= y ? (y - x < a_size) : (x - y < b_size);
}

static int is_letter(uint8_t c)
{
    return (c >= (uint8_t)'A' && c <= (uint8_t)'Z') ||
           (c >= (uint8_t)'a' && c <= (uint8_t)'z');
}

static int is_name_tail(uint8_t c)
{
    return is_letter(c) || (c >= (uint8_t)'0' && c <= (uint8_t)'9') ||
           c == (uint8_t)'.';
}

BVRStatus bvr_decode(const uint8_t *source, size_t source_length,
                     size_t offset, BasicVariableRef *result)
{
    BasicVariableRef decoded;
    size_t name_available;
    size_t scan_count;
    size_t i;

    if (source == NULL || result == NULL || offset >= source_length) {
        return BVR_INVALID_ARGUMENT;
    }
    if (ranges_overlap(source, source_length, result, sizeof(*result))) {
        return BVR_OVERLAPPING_MEMORY;
    }

    decoded.marker = source[offset];
    switch (decoded.marker) {
        case 0x02u:
            decoded.family = BVR_FAMILY_EXPLICIT;
            decoded.explicit_type = BVR_TYPE_INTEGER;
            break;
        case 0x03u:
            decoded.family = BVR_FAMILY_EXPLICIT;
            decoded.explicit_type = BVR_TYPE_STRING;
            break;
        case 0x04u:
            decoded.family = BVR_FAMILY_EXPLICIT;
            decoded.explicit_type = BVR_TYPE_REAL;
            break;
        case 0x0bu:
        case 0x0cu:
        case 0x0du:
            decoded.family = BVR_FAMILY_UNSUFFIXED_OR_RESOLVED;
            decoded.explicit_type = BVR_TYPE_UNDETERMINED;
            break;
        default:
            return BVR_UNRECOGNIZED_MARKER;
    }

    /* Check remaining bytes BEFORE adding to offset or dereferencing. */
    if (source_length - offset < 4u) {
        return BVR_TRUNCATED;
    }
    decoded.cache_low = source[offset + 1u];
    decoded.cache_high = source[offset + 2u];
    decoded.reference_offset = offset;
    decoded.name_offset = offset + 3u;
    name_available = source_length - decoded.name_offset;
    scan_count = name_available < BVR_MAX_NAME_LENGTH ?
                 name_available : BVR_MAX_NAME_LENGTH;

    for (i = 0u; i < scan_count; ++i) {
        uint8_t encoded = source[decoded.name_offset + i];
        uint8_t character = (uint8_t)(encoded & 0x7fu);
        if (i == 0u ? !is_letter(character) : !is_name_tail(character)) {
            return BVR_MALFORMED;
        }
        if ((encoded & 0x80u) != 0u) {
            decoded.name_length = i + 1u;
            decoded.consumed = 3u + decoded.name_length;
            *result = decoded;
            return BVR_OK;
        }
    }
    return name_available > BVR_MAX_NAME_LENGTH ?
           BVR_LIMIT_EXCEEDED : BVR_TRUNCATED;
}
