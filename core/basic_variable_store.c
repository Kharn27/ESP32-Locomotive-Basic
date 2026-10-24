#include "basic_variable_store.h"

#include <stdint.h>
#include <string.h>

/* Supported Linux / ESP32 platforms have uintptr_t. End-address additions
 * are deliberately avoided: subtraction cannot wrap for ordered addresses. */
static int overlaps(const void *a, size_t a_size, const void *b, size_t b_size)
{
    uintptr_t x = (uintptr_t)a;
    uintptr_t y = (uintptr_t)b;
    if (a_size == 0u || b_size == 0u) {
        return 0;
    }
    return x <= y ? y - x < a_size : x - y < b_size;
}

static int valid_type(uint8_t type)
{
    return type == (uint8_t)BVT_INTEGER || type == (uint8_t)BVT_REAL ||
           type == (uint8_t)BVT_STRING;
}

static int valid_key(const BasicVariableKey *key)
{
    size_t i;
    if (!valid_type(key->type) || key->name_length == 0u ||
        key->name_length > BVT_MAX_NAME_LENGTH) {
        return 0;
    }
    for (i = 0u; i < BVT_MAX_NAME_LENGTH; ++i) {
        uint8_t c = key->name[i];
        int upper = c >= (uint8_t)'A' && c <= (uint8_t)'Z';
        if (i >= key->name_length) {
            if (c != 0u) {
                return 0;
            }
        } else if (!upper && (i == 0u ||
                   !((c >= (uint8_t)'0' && c <= (uint8_t)'9') ||
                     c == (uint8_t)'.'))) {
            return 0;
        }
    }
    return 1;
}

static int equal_keys(const BasicVariableKey *a, const BasicVariableKey *b)
{
    return a->type == b->type && a->name_length == b->name_length &&
           memcmp(a->name, b->name, a->name_length) == 0;
}

static int valid_value(const BasicVariableValue *value)
{
    return valid_type(value->type) &&
           (value->type != (uint8_t)BVT_STRING ||
            (value->data.string.offset == 0u && value->data.string.length == 0u));
}

/* Structural and live-entry validation precedes all reads and mutations. */
static BVSStatus check_store(const BasicVariableStore *store, size_t *out_bytes,
                             int validate_entries)
{
    size_t bytes, i;
    if (store == NULL) {
        return BVS_INVALID_ARGUMENT;
    }
    if (store->capacity > SIZE_MAX / sizeof(BasicVariableEntry)) {
        return BVS_INVALID_STORE;
    }
    if ((store->capacity == 0u) != (store->entries == NULL) ||
        store->count > store->capacity) {
        return BVS_INVALID_STORE;
    }
    bytes = store->capacity * sizeof(BasicVariableEntry);
    if (overlaps(store, sizeof(*store), store->entries, bytes)) {
        return BVS_OVERLAPPING_MEMORY;
    }
    if (validate_entries != 0) {
        for (i = 0u; i < store->count; ++i) {
            const BasicVariableEntry *entry = &store->entries[i];
            if (!valid_key(&entry->key) || !valid_value(&entry->value) ||
                entry->value.type != entry->key.type) {
                return BVS_INVALID_STORE;
            }
        }
    }
    *out_bytes = bytes;
    return BVS_OK;
}

/* Check disjointness of an external argument against ALL storage capacity. */
static int unsafe(const BasicVariableStore *store, size_t bytes,
                  const void *argument, size_t length)
{
    return overlaps(store, sizeof(*store), argument, length) ||
           overlaps(store->entries, bytes, argument, length);
}

/* Internal find: caller has validated store and key; has no side effects. */
static size_t locate(const BasicVariableStore *store, const BasicVariableKey *key)
{
    size_t i;
    for (i = 0u; i < store->count; ++i) {
        if (equal_keys(&store->entries[i].key, key)) {
            return i;
        }
    }
    return store->count;
}

BVSStatus bvs_init(BasicVariableStore *store, BasicVariableEntry *entries,
                   size_t capacity)
{
    size_t bytes;
    if (store == NULL || (capacity == 0u) != (entries == NULL)) {
        return BVS_INVALID_ARGUMENT;
    }
    if (capacity > SIZE_MAX / sizeof(*entries)) {
        return BVS_INVALID_ARGUMENT;
    }
    bytes = capacity * sizeof(*entries);
    if (overlaps(store, sizeof(*store), entries, bytes)) {
        return BVS_OVERLAPPING_MEMORY;
    }
    if (bytes > 0u) {
        memset(entries, 0, bytes);
    }
    store->entries = entries;
    store->capacity = capacity;
    store->count = 0u;
    return BVS_OK;
}

BVSStatus bvs_reset(BasicVariableStore *store)
{
    size_t bytes;
    BVSStatus status = check_store(store, &bytes, 0);
    if (status != BVS_OK) {
        return status;
    }
    if (bytes > 0u) {
        memset(store->entries, 0, bytes);
    }
    store->count = 0u;
    return BVS_OK;
}

BVSStatus bvs_find(const BasicVariableStore *store, const BasicVariableKey *key,
                   size_t *out_index)
{
    size_t bytes, index;
    BVSStatus status;
    if (store == NULL || key == NULL || out_index == NULL) {
        return BVS_INVALID_ARGUMENT;
    }
    status = check_store(store, &bytes, 1);
    if (status != BVS_OK) {
        return status;
    }
    if (unsafe(store, bytes, key, sizeof(*key)) ||
        unsafe(store, bytes, out_index, sizeof(*out_index)) ||
        overlaps(key, sizeof(*key), out_index, sizeof(*out_index))) {
        return BVS_OVERLAPPING_MEMORY;
    }
    if (!valid_key(key)) {
        return BVS_INVALID_KEY;
    }
    index = locate(store, key);
    if (index == store->count) {
        return BVS_NOT_FOUND;
    }
    *out_index = index;
    return BVS_OK;
}

BVSStatus bvs_create(BasicVariableStore *store, const BasicVariableKey *key,
                     size_t *out_index)
{
    size_t bytes, index;
    BasicVariableEntry entry;
    BVSStatus status;
    if (store == NULL || key == NULL || out_index == NULL) {
        return BVS_INVALID_ARGUMENT;
    }
    status = check_store(store, &bytes, 1);
    if (status != BVS_OK) {
        return status;
    }
    if (unsafe(store, bytes, key, sizeof(*key)) ||
        unsafe(store, bytes, out_index, sizeof(*out_index)) ||
        overlaps(key, sizeof(*key), out_index, sizeof(*out_index))) {
        return BVS_OVERLAPPING_MEMORY;
    }
    if (!valid_key(key)) {
        return BVS_INVALID_KEY;
    }
    index = locate(store, key);
    if (index != store->count) {
        return BVS_ALREADY_EXISTS;
    }
    if (store->count == store->capacity) {
        return BVS_FULL;
    }
    memset(&entry, 0, sizeof(entry));
    entry.key = *key;
    entry.value.type = key->type;
    store->entries[index] = entry;
    store->count = index + 1u;
    *out_index = index;
    return BVS_OK;
}

BVSStatus bvs_get(const BasicVariableStore *store, const BasicVariableKey *key,
                  BasicVariableValue *out_value)
{
    size_t bytes, index;
    BVSStatus status;
    if (store == NULL || key == NULL || out_value == NULL) {
        return BVS_INVALID_ARGUMENT;
    }
    status = check_store(store, &bytes, 1);
    if (status != BVS_OK) {
        return status;
    }
    if (unsafe(store, bytes, key, sizeof(*key)) ||
        unsafe(store, bytes, out_value, sizeof(*out_value)) ||
        overlaps(key, sizeof(*key), out_value, sizeof(*out_value))) {
        return BVS_OVERLAPPING_MEMORY;
    }
    if (!valid_key(key)) {
        return BVS_INVALID_KEY;
    }
    index = locate(store, key);
    if (index == store->count) {
        return BVS_NOT_FOUND;
    }
    *out_value = store->entries[index].value;
    return BVS_OK;
}

BVSStatus bvs_set(BasicVariableStore *store, const BasicVariableKey *key,
                  const BasicVariableValue *value)
{
    size_t bytes, index;
    BVSStatus status;
    if (store == NULL || key == NULL || value == NULL) {
        return BVS_INVALID_ARGUMENT;
    }
    status = check_store(store, &bytes, 1);
    if (status != BVS_OK) {
        return status;
    }
    if (unsafe(store, bytes, key, sizeof(*key)) ||
        unsafe(store, bytes, value, sizeof(*value)) ||
        overlaps(key, sizeof(*key), value, sizeof(*value))) {
        return BVS_OVERLAPPING_MEMORY;
    }
    if (!valid_key(key)) {
        return BVS_INVALID_KEY;
    }
    if (!valid_type(value->type) || value->type != key->type) {
        return BVS_INVALID_TYPE;
    }
    if (!valid_value(value)) {
        return BVS_UNSUPPORTED_STRING;
    }
    index = locate(store, key);
    if (index == store->count) {
        return BVS_NOT_FOUND;
    }
    store->entries[index].value = *value;
    return BVS_OK;
}
