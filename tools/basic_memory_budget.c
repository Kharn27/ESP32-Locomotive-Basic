/*
 * J0.23 - portable C99 memory inventory. All type information comes from
 * the real core headers, never from hand-copied ABI sizes.
 *
 * This executable has no dependency on the host CLI or on ESP-IDF.
 * Scenario occupancy is hypothetical; capacity is caller-owned storage.
 */
#include "basic_program.h"
#include "basic_executor.h"
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include "basic_variable_ref.h"
#include "basic_variable_types.h"
#include "basic_session.h"
#include "basic_listing.h"
#include "basic_tokenizer.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define C99_ALIGNOF(type) offsetof(struct { char lead; type member; }, member)
#define TYPE_ROW(type) \
    printf("  %-27s %8zu %8zu\n", #type, sizeof(type), C99_ALIGNOF(type))

typedef struct {
    const char *name;
    size_t program_capacity;
    size_t program_used;
    size_t variable_capacity;
    size_t variable_count;
    size_t input_capacity;
    size_t input_used;
    size_t temporary_capacity;
    size_t temporary_used;
    size_t output_capacity;
    size_t output_used;
} MemoryScenario;

/* The occupancy column is illustrative, NOT an instrumented BASIC run. */
static const MemoryScenario scenarios[] = {
    {"small_16",     1024u,   320u,  16u,   8u,  256u, 128u,  512u, 256u,  2048u,  128u},
    {"8KiB_64",      8192u,  6144u,  64u,  48u,  512u, 256u, 2048u, 512u,  4096u, 1024u},
    {"16KiB_128",   16384u, 12288u, 128u,  96u,  512u, 256u, 2048u, 512u,  8192u, 2048u},
    {"stress_32KiB",32768u, 30720u, 256u, 240u, 1024u, 512u, 2048u,1024u, 16384u, 8192u}
};

static int checked_add(size_t *value, size_t delta)
{
    if (delta > SIZE_MAX - *value) {
        return 0;
    }
    *value += delta;
    return 1;
}

static int checked_mul(size_t count, size_t element_size, size_t *result)
{
    if (element_size != 0u && count > SIZE_MAX / element_size) {
        return 0;
    }
    *result = count * element_size;
    return 1;
}

static int audit_scenario(const MemoryScenario *s)
{
    size_t descriptors = sizeof(BasicProgram) + sizeof(BasicSessionRuntime)
                       + sizeof(BasicVariableStore) + sizeof(BasicVariableTypes);
    size_t entries_reserved, entries_occupied;
    size_t total = descriptors;
    size_t occupied = descriptors;

    if (s->program_used > s->program_capacity ||
        s->variable_count > s->variable_capacity ||
        s->input_used > s->input_capacity ||
        s->temporary_used > s->temporary_capacity ||
        s->output_used > s->output_capacity ||
        !checked_mul(s->variable_capacity, sizeof(BasicVariableEntry), &entries_reserved) ||
        !checked_mul(s->variable_count, sizeof(BasicVariableEntry), &entries_occupied) ||
        !checked_add(&total, s->program_capacity) ||
        !checked_add(&total, entries_reserved) ||
        !checked_add(&total, s->input_capacity) ||
        !checked_add(&total, s->temporary_capacity) ||
        !checked_add(&total, s->output_capacity) ||
        !checked_add(&occupied, s->program_used) ||
        !checked_add(&occupied, entries_occupied) ||
        !checked_add(&occupied, s->input_used) ||
        !checked_add(&occupied, s->temporary_used) ||
        !checked_add(&occupied, s->output_used) ||
        occupied > total) {
        fprintf(stderr, "Invalid or overflowing scenario: %s\n", s->name);
        return 0;
    }

    printf("  %-14s %8zu %8zu %9zu %7zu %7zu %7zu %10zu %10zu\n",
           s->name, descriptors, s->program_capacity, entries_reserved,
           s->input_capacity, s->temporary_capacity, s->output_capacity,
           total, occupied);
    return 1;
}

int main(void)
{
    size_t i;

    /* Portable structural invariants, not hard-coded host/ESP32 byte sizes. */
    if (sizeof(((BasicVariableKey *)0)->name) != BVT_MAX_NAME_LENGTH ||
        sizeof(((BasicVariableTypes *)0)->types) != BVT_ALPHABET_SIZE ||
        sizeof(BasicVariableEntry) <
            sizeof(BasicVariableKey) + sizeof(BasicVariableValue) ||
        sizeof(((BasicSessionRuntime *)0)->executor) != sizeof(BasicExecutor) ||
        sizeof(BasicStringValue) < 2u * sizeof(uint32_t) ||
        sizeof(((BasicVariableValue *)0)->data.real5) != 5u) {
        fprintf(stderr, "Unexpected core structure invariant\n");
        return EXIT_FAILURE;
    }

    printf("J0.23 C99 architecture-dependent type audit\n");
    printf("ABI: pointer=%zu, size_t=%zu, uint32_t=%zu (bytes)\n",
           sizeof(void *), sizeof(size_t), sizeof(uint32_t));
    printf("Core structures (bytes; C99 alignment via offsetof):\n");
    printf("  %-27s %8s %8s\n", "Type", "sizeof", "align");
    TYPE_ROW(BasicProgram);
    TYPE_ROW(BasicProgramLine);
    TYPE_ROW(BasicExecutor);
    TYPE_ROW(BasicSessionRuntime);
    TYPE_ROW(BasicVariableStore);
    TYPE_ROW(BasicVariableEntry);
    TYPE_ROW(BasicVariableKey);
    TYPE_ROW(BasicVariableValue);
    TYPE_ROW(BasicVariableName);
    TYPE_ROW(BasicVariableTypes);
    TYPE_ROW(BasicVariableRef);
    TYPE_ROW(BasicStringValue);
    TYPE_ROW(BSResult);
    TYPE_ROW(BSRResult);

    printf("\nCaller-owned scenarios (bytes, no heap overhead, no task stacks):\n");
    printf("  %-14s %8s %8s %9s %7s %7s %7s %10s %10s\n",
           "Scenario", "fixed", "program", "entries", "input", "temp",
           "output", "reserved", "occupied*");
    for (i = 0u; i < sizeof(scenarios) / sizeof(scenarios[0]); ++i) {
        if (!audit_scenario(&scenarios[i])) {
            return EXIT_FAILURE;
        }
    }
    puts("* Occupied is an illustrative working set, not a runtime measurement.");
    puts("  'fixed' = Program + SessionRuntime (includes Executor) + Store + Types.");
    puts("  Reserved = fixed + all caller buffers and the full entry array.");
    puts("  Excluded = call stacks, ESP-IDF, drivers, display and heap metadata.");
    return EXIT_SUCCESS;
}
