#include "basic_executor.h"
#include "basic_session_runtime.h"
#include "basic_tokenizer.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

typedef struct {
    BasicProgram program;
    uint8_t storage[2048];
    BasicVariableStore store;
    BasicVariableEntry entries[8];
    BasicExecutor executor;
    uint8_t output[128];
    size_t written;
} Harness;

static int setup(Harness *h)
{
    memset(h, 0, sizeof(*h));
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(bvs_init(&h->store, h->entries, 8u) == BVS_OK);
    return 0;
}

static int put(Harness *h, uint16_t line, const char *text)
{
    uint8_t token[128];
    size_t n = 0u;
    CHECK(bt_tokenize((const uint8_t *)text, strlen(text),
                      token, sizeof(token), &n) == BT_OK);
    CHECK(bp_put(&h->program, line, token, n) == BP_OK);
    return 0;
}

static int raw(Harness *h, uint16_t line, const uint8_t *body, size_t length)
{
    CHECK(bp_put(&h->program, line, body, length) == BP_OK);
    return 0;
}

static BasicVariableKey key_of(const char *text, BasicVariableType type)
{
    BasicVariableKey key;
    size_t i, n = strlen(text);
    memset(&key, 0, sizeof(key));
    key.type = (uint8_t)type;
    key.name_length = (uint8_t)n;
    for (i = 0u; i < n; ++i) {
        uint8_t c = (uint8_t)text[i];
        key.name[i] = c >= (uint8_t)'a' && c <= (uint8_t)'z' ?
                      (uint8_t)(c - (uint8_t)'a' + (uint8_t)'A') : c;
    }
    return key;
}

static int assign(Harness *h, const char *name, int16_t integer)
{
    BasicVariableKey key = key_of(name, BVT_INTEGER);
    BasicVariableValue value;
    memset(&value, 0, sizeof(value));
    value.type = (uint8_t)BVT_INTEGER;
    value.data.integer = integer;
    CHECK(bvs_assign(&h->store, &key, &value) == BVS_OK);
    return 0;
}

/* Compare all caller-owned variable entries before/after the successful read. */
static int print_step(Harness *h, const char *expected)
{
    BasicVariableEntry snapshot[8];
    BasicVariableStore descriptor = h->store;
    size_t size = strlen(expected), i;
    memcpy(snapshot, h->entries, sizeof(snapshot));
    memset(h->output, 0x6a, sizeof(h->output));
    h->written = 999u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output), &h->written) == BE_OK);
    CHECK(h->written == size && memcmp(h->output, expected, size) == 0);
    for (i = size; i < sizeof(h->output); ++i) {
        CHECK(h->output[i] == 0x6au);
    }
    CHECK(memcmp(snapshot, h->entries, sizeof(snapshot)) == 0);
    CHECK(memcmp(&descriptor, &h->store, sizeof(descriptor)) == 0);
    return 0;
}

static int empty_step(Harness *h)
{
    size_t i;
    memset(h->output, 0x6a, sizeof(h->output));
    h->written = 999u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output), &h->written) == BE_OK);
    CHECK(h->written == 0u);
    for (i = 0u; i < sizeof(h->output); ++i) {
        CHECK(h->output[i] == 0x6au);
    }
    return 0;
}

/* Every failure must leave the full output, written, cursor, store, and program
 * unchanged, even when a preceding PRINT statement had valid output. */
static int fails(Harness *h, BEStatus error, size_t capacity)
{
    uint8_t program_snapshot[sizeof(h->storage)];
    uint8_t output_snapshot[sizeof(h->output)];
    BasicVariableEntry entry_snapshot[8];
    BasicVariableStore descriptor = h->store;
    size_t cursor = h->executor.cursor;

    memcpy(program_snapshot, h->storage, sizeof(program_snapshot));
    memcpy(entry_snapshot, h->entries, sizeof(entry_snapshot));
    memset(h->output, 0x5d, sizeof(h->output));
    memcpy(output_snapshot, h->output, sizeof(output_snapshot));
    h->written = 7654u;
    CHECK(be_step(&h->executor, h->output, capacity, &h->written) == error);
    CHECK(h->written == 7654u && h->executor.cursor == cursor);
    CHECK(memcmp(program_snapshot, h->storage, sizeof(program_snapshot)) == 0);
    CHECK(memcmp(output_snapshot, h->output, sizeof(output_snapshot)) == 0);
    CHECK(memcmp(entry_snapshot, h->entries, sizeof(entry_snapshot)) == 0);
    CHECK(memcmp(&descriptor, &h->store, sizeof(descriptor)) == 0);
    return 0;
}

static int test_assignment_then_print(void)
{
    Harness h;
    uint8_t original[sizeof(h.storage)];
    CHECK(setup(&h) == 0);
    CHECK(put(&h, 10u, "A%=2") == 0);
    CHECK(put(&h, 20u, "PRINT A%") == 0);
    CHECK(put(&h, 30u, "LET a%=9") == 0);
    CHECK(put(&h, 40u, "?A%") == 0);
    CHECK(put(&h, 50u, "END") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    memcpy(original, h.storage, sizeof(original));
    CHECK(empty_step(&h) == 0);
    CHECK(h.store.count == 1u);
    CHECK(print_step(&h, "2\n") == 0);
    CHECK(empty_step(&h) == 0);
    CHECK(h.store.count == 1u);
    CHECK(print_step(&h, "9\n") == 0);
    CHECK(empty_step(&h) == 0);
    h.written = 71u;
    CHECK(be_step(&h.executor, h.output, sizeof(h.output), &h.written) == BE_END);
    CHECK(h.written == 71u);
    CHECK(memcmp(original, h.storage, sizeof(original)) == 0);
    return 0;
}

static int test_all_signed_values(void)
{
    Harness h;
    static const int16_t numbers[] = {0, 9, 10, 255, 32767, -32768, -1};
    static const char *const prints[] = {
        "0\n", "9\n", "10\n", "255\n", "32767\n", "-32768\n", "-1\n"
    };
    size_t i;
    CHECK(setup(&h) == 0);
    CHECK(put(&h, 10u, "PRINT A%") == 0);
    for (i = 0u; i < sizeof(numbers) / sizeof(numbers[0]); ++i) {
        CHECK(assign(&h, "A", numbers[i]) == 0);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(print_step(&h, prints[i]) == 0);
        CHECK(h.store.count == 1u);
    }
    return 0;
}

static int test_long_names_and_opaque_caches(void)
{
    Harness h;
    char name[41], source[48];
    uint8_t original[sizeof(h.storage)];
    static const uint8_t cache_one[] = {0xbfu,0x02u,0x20u,0xefu,0xc1u};
    static const uint8_t cache_two[] = {0xbfu,' ',0x02u,0xefu,0x20u,0xe1u};
    size_t i;
    CHECK(setup(&h) == 0);
    name[0] = 'a';
    for (i = 1u; i < 40u; ++i) {
        name[i] = i % 7u == 0u ? '.' : (char)('0' + (int)(i % 10u));
    }
    name[40] = '\0';
    memcpy(source, "PRINT ", 6u);
    memcpy(source + 6u, name, 40u);
    source[46] = '%';
    source[47] = '\0';
    CHECK(put(&h, 10u, source) == 0);
    source[0] = '?';
    memmove(source + 1u, name, 40u);
    source[41] = '%';
    source[42] = '\0';
    CHECK(put(&h, 20u, source) == 0);
    CHECK(raw(&h, 30u, cache_one, sizeof(cache_one)) == 0);
    CHECK(raw(&h, 40u, cache_two, sizeof(cache_two)) == 0);
    CHECK(assign(&h, name, 123) == 0);
    CHECK(assign(&h, "A", 77) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    memcpy(original, h.storage, sizeof(original));
    CHECK(print_step(&h, "123\n") == 0);
    CHECK(print_step(&h, "123\n") == 0);
    CHECK(print_step(&h, "77\n") == 0);
    CHECK(print_step(&h, "77\n") == 0);
    CHECK(h.store.count == 2u);
    CHECK(memcmp(original, h.storage, sizeof(original)) == 0);
    return 0;
}

static int test_missing_and_multi_statement(void)
{
    Harness h;
    CHECK(setup(&h) == 0);
    CHECK(put(&h, 10u, "PRINT A%") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_VARIABLE_NOT_FOUND, sizeof(h.output)) == 0);
    CHECK(h.store.count == 0u);
    CHECK(put(&h, 10u, "PRINT \"HELLO\":PRINT A%") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_VARIABLE_NOT_FOUND, sizeof(h.output)) == 0);
    CHECK(assign(&h, "A", 2) == 0);
    CHECK(put(&h, 10u, "PRINT A%:PRINT B%") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_VARIABLE_NOT_FOUND, sizeof(h.output)) == 0);
    CHECK(put(&h, 10u, "PRINT A%:LET B%=2") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_UNSUPPORTED, sizeof(h.output)) == 0);
    return 0;
}

static int test_corrupt_references_and_noninteger(void)
{
    Harness h;
    static const uint8_t short_cache[] = {0xbfu,' ',0x02u,0x20u};
    static const uint8_t unterminated[] = {0xbfu,0x02u,0xefu,0x20u,'A'};
    static const uint8_t bad_name[] = {0xbfu,0x02u,0u,0u,0xa1u};
    static const uint8_t string_ref[] = {0xbfu,' ',0x03u,0u,0u,0xc1u};
    static const uint8_t real_ref[] = {0xbfu,' ',0x04u,0u,0u,0xc1u};
    static const uint8_t *const bodies[] = {
        short_cache, unterminated, bad_name, string_ref, real_ref
    };
    static const size_t lengths[] = {
        sizeof(short_cache), sizeof(unterminated), sizeof(bad_name),
        sizeof(string_ref), sizeof(real_ref)
    };
    static const BEStatus errors[] = {
        BE_TRUNCATED, BE_TRUNCATED, BE_BAD_SEQUENCE,
        BE_UNSUPPORTED, BE_UNSUPPORTED
    };
    size_t i;
    CHECK(setup(&h) == 0);
    CHECK(assign(&h, "A", 5) == 0);
    for (i = 0u; i < sizeof(bodies)/sizeof(bodies[0]); ++i) {
        CHECK(raw(&h, 10u, bodies[i], lengths[i]) == 0);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(fails(&h, errors[i], sizeof(h.output)) == 0);
    }
    return 0;
}

static int test_capacity_store_validation_and_overlap(void)
{
    Harness h;
    size_t untouched;
    CHECK(setup(&h) == 0);
    CHECK(put(&h, 10u, "PRINT A%") == 0);
    CHECK(assign(&h, "A", -32768) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_NO_SPACE, 6u) == 0);
    CHECK(fails(&h, BE_NO_SPACE, 0u) == 0);
    memset(h.output, 0xaa, sizeof(h.output));
    h.written = 87u;
    CHECK(be_step(&h.executor, h.output, 7u, &h.written) == BE_OK);
    CHECK(h.written == 7u && memcmp(h.output, "-32768\n", 7u) == 0);
    CHECK(h.output[7] == 0xaau);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    untouched = 334u;
    CHECK(be_step(&h.executor, (uint8_t *)(void *)h.entries, 1u,
                  &untouched) == BE_OVERLAP);
    CHECK(untouched == 334u);
    h.store.count = 9u; /* broken caller-owned store */
    CHECK(fails(&h, BE_INVALID_STORE, sizeof(h.output)) == 0);
    h.store.count = 1u;
    h.entries[0].value.type = (uint8_t)BVT_REAL; /* wrong live value type */
    CHECK(fails(&h, BE_INVALID_STORE, sizeof(h.output)) == 0);
    return 0;
}

static int test_legacy_and_prior_prints(void)
{
    Harness h;
    CHECK(setup(&h) == 0);
    CHECK(put(&h, 10u, "PRINT A%") == 0);
    CHECK(assign(&h, "A", 42) == 0);
    CHECK(be_init(&h.executor, &h.program) == BE_OK);
    CHECK(fails(&h, BE_UNSUPPORTED, sizeof(h.output)) == 0);
    CHECK(put(&h, 10u, "PRINT \"TXT\"") == 0);
    CHECK(put(&h, 20u, "PRINT 2") == 0);
    CHECK(put(&h, 30u, "PRINT") == 0);
    CHECK(put(&h, 40u, "END") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(print_step(&h, "TXT\n") == 0);
    CHECK(print_step(&h, "2\n") == 0);
    CHECK(print_step(&h, "\n") == 0);
    CHECK(empty_step(&h) == 0);
    return 0;
}

static int test_runtime_run_new_stop(void)
{
    Harness h;
    BasicSessionRuntime rt;
    BSRResult status;
    uint8_t temporary[128];
    CHECK(setup(&h) == 0);
    CHECK(put(&h, 10u, "A%=2") == 0);
    CHECK(put(&h, 20u, "PRINT A%") == 0);
    CHECK(put(&h, 30u, "END") == 0);
    CHECK(assign(&h, "A", 999) == 0);
    CHECK(bsr_init_with_store(&rt, &h.program, &h.store).status == BSR_OK);
    status = bsr_submit(&rt, (const uint8_t *)"RUN", 3u,
                        temporary, sizeof(temporary), h.output,
                        sizeof(h.output), &h.written);
    CHECK(status.status == BSR_OK && h.store.count == 0u);
    status = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(status.status == BSR_OK && h.written == 0u);
    status = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(status.status == BSR_OK && h.written == 2u);
    CHECK(memcmp(h.output, "2\n", 2u) == 0);
    status = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(status.status == BSR_OK);
    status = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(status.status == BSR_END);
    return 0;
}

int main(void)
{
    CHECK(test_assignment_then_print() == 0);
    CHECK(test_all_signed_values() == 0);
    CHECK(test_long_names_and_opaque_caches() == 0);
    CHECK(test_missing_and_multi_statement() == 0);
    CHECK(test_corrupt_references_and_noninteger() == 0);
    CHECK(test_capacity_store_validation_and_overlap() == 0);
    CHECK(test_legacy_and_prior_prints() == 0);
    CHECK(test_runtime_run_new_stop() == 0);
    puts("integer_variable_print: OK (synthetic CPC-derived fixtures)");
    return 0;
}
