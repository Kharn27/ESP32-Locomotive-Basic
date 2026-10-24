#include "basic_variable_types.h"

#include <string.h>

/* Linux/ESP32 supply uintptr_t, matching the J0.13 overlap contract. */
static int bvt_overlaps(const void *a, size_t a_length,
                         const void *b, size_t b_length)
{
    uintptr_t left = (uintptr_t)a;
    uintptr_t right = (uintptr_t)b;
    if (a_length == 0u || b_length == 0u) {
        return 0;
    }
    return left <= right ? right - left < a_length : left - right < b_length;
}

static int bvt_type_valid(BasicVariableType type)
{
    return type == BVT_INTEGER || type == BVT_REAL || type == BVT_STRING;
}

static int bvt_letter_index(char letter, size_t *out_index)
{
    unsigned char c = (unsigned char)letter;
    if (c >= (unsigned char)'a' && c <= (unsigned char)'z') {
        c = (unsigned char)(c - (unsigned char)'a' + (unsigned char)'A');
    }
    if (c < (unsigned char)'A' || c > (unsigned char)'Z') {
        return 0;
    }
    *out_index = (size_t)(c - (unsigned char)'A');
    return 1;
}

static uint8_t bvt_upper(uint8_t c)
{
    if (c >= (uint8_t)'a' && c <= (uint8_t)'z') {
        return (uint8_t)(c - (uint8_t)'a' + (uint8_t)'A');
    }
    return c;
}

static int bvt_upper_letter(uint8_t c)
{
    return c >= (uint8_t)'A' && c <= (uint8_t)'Z';
}

BVTStatus bvt_init(BasicVariableTypes *table)
{
    size_t i;
    if (table == NULL) {
        return BVT_INVALID_ARGUMENT;
    }
    for (i = 0u; i < BVT_ALPHABET_SIZE; ++i) {
        table->types[i] = (uint8_t)BVT_REAL;
    }
    return BVT_OK;
}

BVTStatus bvt_get_implicit(const BasicVariableTypes *table, char initial,
                           BasicVariableType *out_type)
{
    size_t index;
    uint8_t value;
    if (table == NULL || out_type == NULL) {
        return BVT_INVALID_ARGUMENT;
    }
    if (bvt_overlaps(table, sizeof(*table), out_type, sizeof(*out_type))) {
        return BVT_OVERLAPPING_MEMORY;
    }
    if (!bvt_letter_index(initial, &index)) {
        return BVT_INVALID_LETTER;
    }
    value = table->types[index];
    if (!bvt_type_valid((BasicVariableType)value)) {
        return BVT_INVALID_TYPE;
    }
    *out_type = (BasicVariableType)value;
    return BVT_OK;
}

BVTStatus bvt_set_range(BasicVariableTypes *table, char first, char last,
                         BasicVariableType type)
{
    size_t start, end, i;
    if (table == NULL) {
        return BVT_INVALID_ARGUMENT;
    }
    if (!bvt_type_valid(type)) {
        return BVT_INVALID_TYPE;
    }
    if (!bvt_letter_index(first, &start) || !bvt_letter_index(last, &end)) {
        return BVT_INVALID_LETTER;
    }
    if (start > end) {
        return BVT_INVALID_RANGE;
    }
    for (i = start; i <= end; ++i) {
        table->types[i] = (uint8_t)type;
    }
    return BVT_OK;
}

BVTStatus bvt_canonicalize(const uint8_t *source, size_t source_length,
                            size_t offset, BasicVariableName *out_name)
{
    BasicVariableRef reference;
    BasicVariableName temporary;
    BVRStatus status;
    size_t i;
    if (source == NULL || out_name == NULL || offset >= source_length) {
        return BVT_INVALID_ARGUMENT;
    }
    if (bvt_overlaps(source, source_length, out_name, sizeof(*out_name))) {
        return BVT_OVERLAPPING_MEMORY;
    }
    status = bvr_decode(source, source_length, offset, &reference);
    if (status != BVR_OK) {
        return BVT_INVALID_REFERENCE;
    }
    memset(&temporary, 0, sizeof(temporary));
    temporary.length = (uint8_t)reference.name_length;
    for (i = 0u; i < reference.name_length; ++i) {
        uint8_t letter = (uint8_t)(source[reference.name_offset + i] & 0x7fu);
        temporary.bytes[i] = bvt_upper(letter);
    }
    *out_name = temporary;
    return BVT_OK;
}

BVTStatus bvt_build_key(const BasicVariableName *name,
                         BasicVariableType effective_type,
                         BasicVariableKey *out_key)
{
    BasicVariableKey temporary;
    size_t i;
    if (name == NULL || out_key == NULL) {
        return BVT_INVALID_ARGUMENT;
    }
    if (bvt_overlaps(name, sizeof(*name), out_key, sizeof(*out_key))) {
        return BVT_OVERLAPPING_MEMORY;
    }
    if (!bvt_type_valid(effective_type)) {
        return BVT_INVALID_TYPE;
    }
    if (name->length == 0u || name->length > BVT_MAX_NAME_LENGTH) {
        return BVT_INVALID_NAME;
    }
    for (i = 0u; i < BVT_MAX_NAME_LENGTH; ++i) {
        uint8_t c = name->bytes[i];
        if (i >= name->length) {
            if (c != 0u) {
                return BVT_INVALID_NAME;
            }
        } else if (i == 0u) {
            if (!bvt_upper_letter(c)) {
                return BVT_INVALID_NAME;
            }
        } else if (!bvt_upper_letter(c) &&
                   (c < (uint8_t)'0' || c > (uint8_t)'9') && c != (uint8_t)'.') {
            return BVT_INVALID_NAME;
        }
    }
    memset(&temporary, 0, sizeof(temporary));
    temporary.type = (uint8_t)effective_type;
    temporary.name_length = name->length;
    memcpy(temporary.name, name->bytes, name->length);
    *out_key = temporary;
    return BVT_OK;
}
