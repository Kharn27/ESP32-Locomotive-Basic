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
    return valid_type(value->type);
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
    if ((store->string_capacity == 0u) != (store->string_arena == NULL) ||
        store->string_capacity > UINT32_MAX ||
        (store->string_capacity != 0u &&
         (store->capacity == 0u ||
          store->string_slot_bytes != store->string_capacity / store->capacity ||
          store->string_slot_bytes == 0u)) ||
        (store->string_capacity == 0u && store->string_slot_bytes != 0u)) {
        return BVS_INVALID_STORE;
    }
    if (overlaps(store, sizeof(*store), store->entries, bytes) ||
        overlaps(store, sizeof(*store), store->string_arena,
                 store->string_capacity) ||
        overlaps(store->entries, bytes, store->string_arena,
                 store->string_capacity)) {
        return BVS_OVERLAPPING_MEMORY;
    }
    if (validate_entries != 0) {
        for (i = 0u; i < store->count; ++i) {
            const BasicVariableEntry *entry = &store->entries[i];
            if (!valid_key(&entry->key) || !valid_value(&entry->value) ||
                entry->value.type != entry->key.type) {
                return BVS_INVALID_STORE;
            }
            if (entry->value.type == (uint8_t)BVT_STRING) {
                const BasicStringValue *v = &entry->value.data.string;
                if (v->length == 0u) {
                    if (v->offset != 0u) return BVS_INVALID_STORE;
                } else if (store->string_arena == NULL ||
                           v->length > store->string_slot_bytes ||
                           v->offset != i * store->string_slot_bytes) {
                    return BVS_INVALID_STORE;
                }
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
           overlaps(store->entries, bytes, argument, length) ||
           overlaps(store->string_arena, store->string_capacity, argument, length);
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

BVSStatus bvs_init_with_arena(BasicVariableStore *store,
                             BasicVariableEntry *entries, size_t capacity,
                             uint8_t *arena, size_t arena_capacity)
{
    size_t bytes;
    if (store == NULL || (capacity == 0u) != (entries == NULL) ||
        (arena_capacity == 0u) != (arena == NULL) ||
        arena_capacity > UINT32_MAX ||
        (arena_capacity != 0u &&
         (capacity == 0u || arena_capacity / capacity == 0u))) {
        return BVS_INVALID_ARGUMENT;
    }
    if (capacity > SIZE_MAX / sizeof(*entries)) {
        return BVS_INVALID_ARGUMENT;
    }
    bytes = capacity * sizeof(*entries);
    if (overlaps(store, sizeof(*store), entries, bytes) ||
        overlaps(store, sizeof(*store), arena, arena_capacity) ||
        overlaps(entries, bytes, arena, arena_capacity)) {
        return BVS_OVERLAPPING_MEMORY;
    }
    if (bytes > 0u) memset(entries, 0, bytes);
    if (arena_capacity > 0u) memset(arena, 0, arena_capacity);
    store->entries = entries;
    store->capacity = capacity;
    store->count = 0u;
    store->string_arena = arena;
    store->string_capacity = arena_capacity;
    store->string_slot_bytes = arena_capacity == 0u ? 0u : arena_capacity/capacity;
    return BVS_OK;
}

BVSStatus bvs_init(BasicVariableStore *store, BasicVariableEntry *entries,
                   size_t capacity)
{
    return bvs_init_with_arena(store, entries, capacity, NULL, 0u);
}

BVSStatus bvs_validate(const BasicVariableStore *store)
{
    size_t bytes;
    return check_store(store, &bytes, 1);
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
    if (store->string_capacity > 0u) {
        memset(store->string_arena, 0, store->string_capacity);
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
    if (value->type == (uint8_t)BVT_STRING &&
        (value->data.string.offset != 0u || value->data.string.length != 0u)) {
        return BVS_UNSUPPORTED_STRING; /* External descriptor cannot own bytes. */
    }
    index = locate(store, key);
    if (index == store->count) {
        return BVS_NOT_FOUND;
    }
    store->entries[index].value = *value;
    return BVS_OK;
}

/* Validate every aspect before the sole commit. Unlike create+set there is
 * no externally visible half-created entry when the store is exhausted. */
BVSStatus bvs_assign(BasicVariableStore *store, const BasicVariableKey *key,
                     const BasicVariableValue *value)
{
    size_t bytes, index;
    BVSStatus status;
    BasicVariableEntry entry;
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
    if (value->type == (uint8_t)BVT_STRING &&
        (value->data.string.offset != 0u || value->data.string.length != 0u)) {
        return BVS_UNSUPPORTED_STRING; /* Use bvs_assign_string for byte ownership. */
    }
    index = locate(store, key);
    if (index == store->count) {
        if (index == store->capacity) {
            return BVS_FULL;
        }
        memset(&entry, 0, sizeof(entry));
        entry.key = *key;
        entry.value = *value;
        store->entries[index] = entry;
        store->count = index + 1u;
    } else {
        store->entries[index].value = *value;
    }
    return BVS_OK;
}

/* Everything except the final write is pure and shared with the executor
 * preflight.  The assigned slot is indexed by the complete key identity. */
static BVSStatus preflight_string(const BasicVariableStore *store,
                                 const BasicVariableKey *key,
                                 const uint8_t *source, size_t length,
                                 size_t *out_index)
{
    size_t bytes, index, i;
    BVSStatus status;
    if (store == NULL || key == NULL || (length != 0u && source == NULL))
        return BVS_INVALID_ARGUMENT;
    status = check_store(store, &bytes, 1);
    if (status != BVS_OK) return status;
    if (unsafe(store, bytes, key, sizeof(*key)) ||
        unsafe(store, bytes, source, length) ||
        overlaps(key, sizeof(*key), source, length))
        return BVS_OVERLAPPING_MEMORY;
    if (!valid_key(key)) return BVS_INVALID_KEY;
    if (key->type != (uint8_t)BVT_STRING) return BVS_INVALID_TYPE;
    for (i = 0u; i < length; ++i) {
        uint8_t ch = source[i];
        if (ch < 0x20u || ch > 0x7eu || ch == (uint8_t)'"')
            return BVS_INVALID_STRING;
    }
    index = locate(store, key);
    if (index == store->count && index == store->capacity)
        return BVS_FULL;
    if (length > 0u && (store->string_arena == NULL ||
                         length > store->string_slot_bytes))
        return BVS_NO_STRING_SPACE;
    *out_index = index;
    return BVS_OK;
}

BVSStatus bvs_can_assign_string(const BasicVariableStore *store,
                                const BasicVariableKey *key,
                                const uint8_t *bytes, size_t length)
{
    size_t index;
    return preflight_string(store, key, bytes, length, &index);
}

BVSStatus bvs_assign_string(BasicVariableStore *store,
                            const BasicVariableKey *key,
                            const uint8_t *bytes, size_t length)
{
    size_t index;
    BasicVariableEntry entry;
    BVSStatus status = preflight_string(store, key, bytes, length, &index);
    if (status != BVS_OK) return status;
    memset(&entry, 0, sizeof(entry));
    entry.key = *key;
    entry.value.type = (uint8_t)BVT_STRING;
    if (length != 0u) {
        entry.value.data.string.offset = (uint32_t)(index*store->string_slot_bytes);
        entry.value.data.string.length = (uint32_t)length;
    }
    /* No later operation can fail.  Zero old content (no stale bytes)
     * and rewrite the same slot: unlimited reassignments, no exhaustion. */
    if (store->string_slot_bytes != 0u) {
        uint8_t *slot = store->string_arena + index*store->string_slot_bytes;
        memset(slot, 0, store->string_slot_bytes);
        if (length != 0u) memcpy(slot, bytes, length);
    }
    store->entries[index] = entry;
    if (index == store->count) ++store->count;
    return BVS_OK;
}

BVSStatus bvs_string_span(const BasicVariableStore *store,
                          const BasicStringValue *value,
                          const uint8_t **out_bytes, size_t *out_length)
{
    size_t bytes, i;
    BVSStatus status;
    if (store == NULL || value == NULL || out_bytes == NULL || out_length == NULL)
        return BVS_INVALID_ARGUMENT;
    status = check_store(store, &bytes, 1);
    if (status != BVS_OK) return status;
    if (unsafe(store, bytes, value, sizeof(*value)) ||
        unsafe(store, bytes, out_bytes, sizeof(*out_bytes)) ||
        unsafe(store, bytes, out_length, sizeof(*out_length)) ||
        overlaps(value, sizeof(*value), out_bytes, sizeof(*out_bytes)) ||
        overlaps(value, sizeof(*value), out_length, sizeof(*out_length)) ||
        overlaps(out_bytes, sizeof(*out_bytes), out_length, sizeof(*out_length)))
        return BVS_OVERLAPPING_MEMORY;
    if (value->length == 0u && value->offset == 0u) {
        *out_bytes = NULL; *out_length = 0u; return BVS_OK;
    }
    /* The provided descriptor must correspond to an existing live entry. */
    for (i = 0u; i < store->count; ++i) {
        const BasicVariableValue *item = &store->entries[i].value;
        if (item->type == (uint8_t)BVT_STRING &&
            item->data.string.offset == value->offset &&
            item->data.string.length == value->length && value->length != 0u) {
            *out_bytes = store->string_arena + value->offset;
            *out_length = value->length;
            return BVS_OK;
        }
    }
    return BVS_INVALID_STRING;
}
