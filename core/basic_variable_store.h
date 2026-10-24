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
    BVS_OVERLAPPING_MEMORY
} BVSStatus;

typedef struct {
    uint32_t offset; /* Reserved for a future, caller-owned byte arena. */
    uint32_t length; /* J0.15 requires offset == length == 0. */
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
} BasicVariableStore;

/* All buffers must be genuine accessible objects of the declared extent.
 * Store, entry array, keys and output/input objects must not overlap.
 * No allocation, hidden globals, conversion or BASIC program mutation.
 * Out-parameters are unchanged on any failure, including NOT_FOUND.
 * The caller must not externally mutate entries or metadata after init.
 */
BVSStatus bvs_init(BasicVariableStore *store, BasicVariableEntry *entries,
                   size_t capacity);
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

#endif
