/* J1.15-C: shared, fixed CYD CONSOLE storage contract (not a CPC limit).
 * Included by firmware and the Linux integration test. No owned globals.
 */
#ifndef J1_15_C_STRING_ARENA_H
#define J1_15_C_STRING_ARENA_H

#include "basic_variable_store.h"

enum {
    J115C_VARIABLES_CAPACITY = 64,
    J115C_STRING_SLOT_BYTES = 64,
    J115C_STRING_ARENA_CAPACITY =
        J115C_VARIABLES_CAPACITY * J115C_STRING_SLOT_BYTES
};

/* C99 compile-time size invariant, independently of ESP-IDF compiler mode. */
typedef char J115C_ArenaIs4096[
    (J115C_STRING_ARENA_CAPACITY == 4096) ? 1 : -1];

/* Fail closed before mutating store/entries on a wrong memory extent.
 * The core continues to own all actual allocation/alias/slot checks.
 */
static inline BVSStatus j115c_init_store(BasicVariableStore *store,
                                        BasicVariableEntry *entries,
                                        size_t entry_count,
                                        uint8_t *arena, size_t arena_bytes)
{
    BVSStatus status;
    if (store == NULL || entries == NULL || arena == NULL ||
        entry_count != (size_t)J115C_VARIABLES_CAPACITY ||
        arena_bytes != (size_t)J115C_STRING_ARENA_CAPACITY)
        return BVS_INVALID_ARGUMENT;
    status = bvs_init_with_arena(store, entries, entry_count,
                                 arena, arena_bytes);
    if (status != BVS_OK)
        return status;
    if (store->entries != entries || store->string_arena != arena ||
        store->capacity != (size_t)J115C_VARIABLES_CAPACITY ||
        store->string_capacity != (size_t)J115C_STRING_ARENA_CAPACITY ||
        store->string_slot_bytes != (size_t)J115C_STRING_SLOT_BYTES ||
        bvs_validate(store) != BVS_OK)
        return BVS_INVALID_STORE;
    return BVS_OK;
}
#endif
