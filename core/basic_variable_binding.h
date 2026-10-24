#ifndef BASIC_VARIABLE_BINDING_H
#define BASIC_VARIABLE_BINDING_H

#include <stddef.h>
#include <stdint.h>
#include "basic_variable_store.h"

/* Internal statuses only; never historical CPC BASIC error numbers. */
typedef enum {
    BVB_OK = 0,
    BVB_NOT_FOUND,
    BVB_INVALID_ARGUMENT,
    BVB_UNRECOGNIZED_MARKER,
    BVB_UNSUPPORTED_FAMILY,
    BVB_MALFORMED,
    BVB_TRUNCATED,
    BVB_LIMIT_EXCEEDED,
    BVB_OVERLAPPING_MEMORY,
    BVB_INVALID_REFERENCE,
    BVB_INVALID_STORE
} BVBStatus;

/*
 * Resolve a CPC explicit scalar variable at source[offset] into a J0.14 key.
 * Accepts only markers 02 (INTEGER), 03 (STRING), 04 (REAL => BVT_REAL=05).
 * On success returns its complete uppercase key and exact consumed byte count.
 * The CPC cache remains opaque. 0B/0C/0D yield UNSUPPORTED_FAMILY.
 *
 * Every buffer is caller-owned, genuinely accessible for its declared size,
 * alive throughout the call and disjoint from all other buffers. No allocation,
 * global state or source mutation. On any failure ALL outputs stay unchanged.
 */
BVBStatus bvb_resolve_explicit(const uint8_t *source, size_t source_length,
                               size_t offset, BasicVariableKey *out_key,
                               size_t *out_consumed);

/*
 * Resolve and retrieve an EXISTING scalar from the caller-owned J0.15 store.
 * On success commits key, consumed count and value together; on NOT_FOUND or
 * any other failure, none of these outputs changes. The store (descriptor and
 * its entire entry capacity) must also be disjoint from the source and outputs.
 * No implicit initialization, creation, type conversion or store mutation.
 */
BVBStatus bvb_read_explicit(const uint8_t *source, size_t source_length,
                            size_t offset, const BasicVariableStore *store,
                            BasicVariableKey *out_key, size_t *out_consumed,
                            BasicVariableValue *out_value);

#endif
