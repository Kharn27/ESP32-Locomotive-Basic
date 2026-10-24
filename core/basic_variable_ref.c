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


BVRStatus bvr_encode_explicit(const uint8_t *name, size_t name_length,
                              BVRExplicitType explicit_type,
                              uint8_t *destination, size_t destination_capacity,
                              size_t *written)
{
    size_t i;
    uint8_t marker;
    if (name == NULL || destination == NULL || written == NULL) {
        return BVR_INVALID_ARGUMENT;
    }
    if (ranges_overlap(name, name_length, destination, destination_capacity) ||
        ranges_overlap(written, sizeof(*written), destination, destination_capacity) ||
        ranges_overlap(written, sizeof(*written), name, name_length)) {
        return BVR_OVERLAPPING_MEMORY;
    }
    switch (explicit_type) {
    case BVR_TYPE_INTEGER: marker = 0x02u; break;
    case BVR_TYPE_STRING: marker = 0x03u; break;
    case BVR_TYPE_REAL: marker = 0x04u; break;
    default: return BVR_INVALID_ARGUMENT;
    }
    if (name_length == 0u) {
        return BVR_MALFORMED;
    }
    if (name_length > BVR_MAX_NAME_LENGTH) {
        return BVR_LIMIT_EXCEEDED;
    }
    for (i = 0u; i < name_length; ++i) {
        if (i == 0u ? !is_letter(name[i]) : !is_name_tail(name[i])) {
            return BVR_MALFORMED;
        }
    }
    if (destination_capacity < 3u + name_length) {
        return BVR_LIMIT_EXCEEDED;
    }
    destination[0] = marker;
    destination[1] = 0u;
    destination[2] = 0u;
    for (i = 0u; i < name_length; ++i) {
        destination[3u + i] = name[i];
    }
    destination[2u + name_length] |= 0x80u;
    *written = 3u + name_length;
    return BVR_OK;
}
