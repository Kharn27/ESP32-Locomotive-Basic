#include "basic_variable_binding.h"

#include <stdint.h>

/* Same overflow-free range comparison contract as J0.13-J0.15 on Linux/ESP32. */
static int overlaps(const void *a, size_t a_size, const void *b, size_t b_size)
{
    uintptr_t x = (uintptr_t)a;
    uintptr_t y = (uintptr_t)b;
    if (a_size == 0u || b_size == 0u) {
        return 0;
    }
    return x <= y ? y - x < a_size : x - y < b_size;
}

static BVBStatus ref_status(BVRStatus status)
{
    switch (status) {
        case BVR_OK: return BVB_OK;
        case BVR_INVALID_ARGUMENT: return BVB_INVALID_ARGUMENT;
        case BVR_UNRECOGNIZED_MARKER: return BVB_UNRECOGNIZED_MARKER;
        case BVR_MALFORMED: return BVB_MALFORMED;
        case BVR_TRUNCATED: return BVB_TRUNCATED;
        case BVR_LIMIT_EXCEEDED: return BVB_LIMIT_EXCEEDED;
        case BVR_OVERLAPPING_MEMORY: return BVB_OVERLAPPING_MEMORY;
        default: return BVB_INVALID_REFERENCE;
    }
}

static BVBStatus store_status(BVSStatus status)
{
    switch (status) {
        case BVS_OK: return BVB_OK;
        case BVS_NOT_FOUND: return BVB_NOT_FOUND;
        case BVS_OVERLAPPING_MEMORY: return BVB_OVERLAPPING_MEMORY;
        default: return BVB_INVALID_STORE;
    }
}

BVBStatus bvb_resolve_explicit(const uint8_t *source, size_t source_length,
                               size_t offset, BasicVariableKey *out_key,
                               size_t *out_consumed)
{
    BasicVariableRef reference;
    BasicVariableName name;
    BasicVariableKey key;
    BasicVariableType type;
    BVRStatus ref_result;
    BVTStatus type_result;

    if (source == NULL || out_key == NULL || out_consumed == NULL ||
        offset >= source_length) {
        return BVB_INVALID_ARGUMENT;
    }
    if (overlaps(source, source_length, out_key, sizeof(*out_key)) ||
        overlaps(source, source_length, out_consumed, sizeof(*out_consumed)) ||
        overlaps(out_key, sizeof(*out_key),
                 out_consumed, sizeof(*out_consumed))) {
        return BVB_OVERLAPPING_MEMORY;
    }
    ref_result = bvr_decode(source, source_length, offset, &reference);
    if (ref_result != BVR_OK) {
        return ref_status(ref_result);
    }
    if (reference.family != BVR_FAMILY_EXPLICIT) {
        return BVB_UNSUPPORTED_FAMILY;
    }
    /* Reference markers are NOT the same numeric space as runtime types. */
    switch (reference.explicit_type) {
        case BVR_TYPE_INTEGER: type = BVT_INTEGER; break;
        case BVR_TYPE_STRING: type = BVT_STRING; break;
        case BVR_TYPE_REAL: type = BVT_REAL; break;
        default: return BVB_INVALID_REFERENCE;
    }
    type_result = bvt_canonicalize(source, source_length, offset, &name);
    if (type_result != BVT_OK) {
        return type_result == BVT_OVERLAPPING_MEMORY ?
               BVB_OVERLAPPING_MEMORY : BVB_INVALID_REFERENCE;
    }
    type_result = bvt_build_key(&name, type, &key);
    if (type_result != BVT_OK) {
        return type_result == BVT_OVERLAPPING_MEMORY ?
               BVB_OVERLAPPING_MEMORY : BVB_INVALID_REFERENCE;
    }
    *out_key = key;
    *out_consumed = reference.consumed;
    return BVB_OK;
}

BVBStatus bvb_read_explicit(const uint8_t *source, size_t source_length,
                            size_t offset, const BasicVariableStore *store,
                            BasicVariableKey *out_key, size_t *out_consumed,
                            BasicVariableValue *out_value)
{
    BasicVariableKey key;
    BasicVariableValue value;
    size_t consumed;
    size_t entry_bytes;
    BVBStatus result;
    BVSStatus lookup;

    if (source == NULL || store == NULL || out_key == NULL ||
        out_consumed == NULL || out_value == NULL ||
        offset >= source_length) {
        return BVB_INVALID_ARGUMENT;
    }
    if (overlaps(source, source_length, out_key, sizeof(*out_key)) ||
        overlaps(source, source_length, out_consumed, sizeof(*out_consumed)) ||
        overlaps(source, source_length, out_value, sizeof(*out_value)) ||
        overlaps(out_key, sizeof(*out_key),
                 out_consumed, sizeof(*out_consumed)) ||
        overlaps(out_key, sizeof(*out_key), out_value, sizeof(*out_value)) ||
        overlaps(out_consumed, sizeof(*out_consumed),
                 out_value, sizeof(*out_value))) {
        return BVB_OVERLAPPING_MEMORY;
    }
    /* Check extent arithmetic, not store contents: bvs_get owns validation. */
    if (store->capacity > SIZE_MAX / sizeof(BasicVariableEntry) ||
        (store->capacity == 0u) != (store->entries == NULL) ||
        store->count > store->capacity) {
        return BVB_INVALID_STORE;
    }
    entry_bytes = store->capacity * sizeof(BasicVariableEntry);
    if (overlaps(store, sizeof(*store), source, source_length) ||
        overlaps(store, sizeof(*store), out_key, sizeof(*out_key)) ||
        overlaps(store, sizeof(*store), out_consumed, sizeof(*out_consumed)) ||
        overlaps(store, sizeof(*store), out_value, sizeof(*out_value)) ||
        overlaps(store->entries, entry_bytes, source, source_length) ||
        overlaps(store->entries, entry_bytes, out_key, sizeof(*out_key)) ||
        overlaps(store->entries, entry_bytes,
                 out_consumed, sizeof(*out_consumed)) ||
        overlaps(store->entries, entry_bytes, out_value, sizeof(*out_value))) {
        return BVB_OVERLAPPING_MEMORY;
    }

    result = bvb_resolve_explicit(source, source_length, offset,
                                  &key, &consumed);
    if (result != BVB_OK) {
        return result;
    }
    lookup = bvs_get(store, &key, &value);
    if (lookup != BVS_OK) {
        return store_status(lookup);
    }
    *out_key = key;
    *out_consumed = consumed;
    *out_value = value;
    return BVB_OK;
}
