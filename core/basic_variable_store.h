#ifndef BASIC_VARIABLE_STORE_H
#define BASIC_VARIABLE_STORE_H

#include <stddef.h>
#include <stdint.h>
#include "basic_variable_types.h"

/* Internal C99 statuses, NOT historical CPC BASIC error numbers. */
typedef enum {
    BVS_OK = 0,
    BVS_NOT_FOUND,
    BVS_ALREADY_EXISTS,
    BVS_FULL,
    BVS_INVALID_ARGUMENT,
    BVS_INVALID_KEY,
    BVS_INVALID_TYPE,
    BVS_INVALID_STORE,
    BVS_UNSUPPORTED_STRING,
    BVS_OVERLAPPING_MEMORY,
    BVS_NO_STRING_SPACE,
    BVS_INVALID_STRING
} BVSStatus;

typedef struct {
    uint32_t offset; /* Byte position within the caller-owned arena. */
    uint32_t length; /* Zero-length strings use offset=0. */
} BasicStringValue;

typedef struct {
    uint8_t type; /* Exactly BVT_INTEGER, BVT_REAL or BVT_STRING. */
    union {
        int16_t integer;
        uint8_t real5[5]; /* Raw CPC bytes, no host float conversion. */
        BasicStringValue string;
    } data;
} BasicVariableValue;

typedef struct {
    BasicVariableKey key; /* Full 40-byte identity; owned copy. */
    BasicVariableValue value;
} BasicVariableEntry;

typedef struct {
    BasicVariableEntry *entries; /* Caller-owned array; NULL when capacity 0. */
    size_t capacity;
    size_t count;
    uint8_t *string_arena; /* NULL for legacy bvs_init, never allocated. */
    size_t string_capacity;
    size_t string_slot_bytes; /* Fixed width per ENTRY (incl. numeric). */
} BasicVariableStore;

/* All buffers must be genuine accessible objects of the declared extent.
 * Store, entry array, keys and output/input objects must not overlap.
 * No allocation, hidden globals, conversion or BASIC program mutation.
 * Out-parameters are unchanged on any failure, including NOT_FOUND.
 * The caller must not externally mutate entries or metadata after init.
 */
BVSStatus bvs_init(BasicVariableStore *store, BasicVariableEntry *entries,
                   size_t capacity);
/* Same initialization, plus a disjoint caller-owned byte arena.  Each entry
 * owns [index*slot_bytes,(index+1)*slot_bytes), where slot_bytes=floor(
 * string_capacity/entry_capacity). This deliberately sacrifices space to
 * guarantee O(1) overwrite/reassignment, bounded memory, no fragmentation.
 * No CPC ROM maximum is inferred from this host storage policy.
 */
BVSStatus bvs_init_with_arena(BasicVariableStore *store,
                             BasicVariableEntry *entries, size_t capacity,
                             uint8_t *arena, size_t arena_capacity);
/* Validate an upcoming scalar STRING assignment with NO mutation. */
BVSStatus bvs_can_assign_string(const BasicVariableStore *store,
                               const BasicVariableKey *key,
                               const uint8_t *bytes, size_t length);
/* Atomic create-or-replace, including its fixed slot.  No malloc.
 * Input must be disjoint from descriptor, entries and arena (entire extent).
 * Embedded NUL, CR, LF and quotes are rejected. Empty strings are supported
 * with or without an arena.  All errors preserve bytes and metadata.
 */
BVSStatus bvs_assign_string(BasicVariableStore *store,
                            const BasicVariableKey *key,
                            const uint8_t *bytes, size_t length);
/* A borrowed immutable span, valid until reassignment/reset.  The result
 * pointer and length do not change on failure.  Not a NUL-terminated C string.
 */
BVSStatus bvs_string_span(const BasicVariableStore *store,
                          const BasicStringValue *value,
                          const uint8_t **out_bytes, size_t *out_length);
/* Pure structural validation, including live entries. */
BVSStatus bvs_validate(const BasicVariableStore *store);
BVSStatus bvs_reset(BasicVariableStore *store);
BVSStatus bvs_find(const BasicVariableStore *store, const BasicVariableKey *key,
                   size_t *out_index);
/* Existing key reports ALREADY_EXISTS without resetting its value. */
BVSStatus bvs_create(BasicVariableStore *store, const BasicVariableKey *key,
                     size_t *out_index);
BVSStatus bvs_get(const BasicVariableStore *store, const BasicVariableKey *key,
                  BasicVariableValue *out_value);
BVSStatus bvs_set(BasicVariableStore *store, const BasicVariableKey *key,
                  const BasicVariableValue *value);
/* Atomic create-or-update: no count, entry or value change on failure. */
BVSStatus bvs_assign(BasicVariableStore *store, const BasicVariableKey *key,
                     const BasicVariableValue *value);

#endif
