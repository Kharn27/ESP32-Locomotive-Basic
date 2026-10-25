#include "basic_executor.h"
#include "basic_tokenizer.h"
#include "basic_variable_binding.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); return 1; } } while (0)

typedef struct {
    BasicProgram program;
    uint8_t storage[1024];
    BasicVariableStore store;
    BasicVariableEntry entries[8];
    BasicExecutor executor;
    uint8_t output[64];
    size_t written;
} Harness;

static int setup(Harness *h, size_t capacity)
{
    memset(h, 0, sizeof(*h));
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(capacity <= 8u);
    CHECK(bvs_init(&h->store, capacity ? h->entries : NULL, capacity) == BVS_OK);
    return 0;
}

static int put(Harness *h, uint16_t line, const char *source)
{
    uint8_t tokens[160];
    size_t size = 0u;
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      tokens, sizeof(tokens), &size) == BT_OK);
    CHECK(bp_put(&h->program, line, tokens, size) == BP_OK);
    return 0;
}

static BasicVariableKey key_of(const char *name)
{
    BasicVariableKey key;
    size_t i;
    memset(&key, 0, sizeof(key));
    key.type = (uint8_t)BVT_INTEGER;
    key.name_length = (uint8_t)strlen(name);
    for (i = 0u; i < (size_t)key.name_length; ++i) {
        uint8_t c = (uint8_t)name[i];
        key.name[i] = c >= (uint8_t)'a' && c <= (uint8_t)'z' ?
                      (uint8_t)(c - (uint8_t)'a' + (uint8_t)'A') : c;
    }
    return key;
}

static int inject(Harness *h, const char *name, int16_t integer)
{
    BasicVariableKey key = key_of(name);
    BasicVariableValue value = {0};
    value.type = (uint8_t)BVT_INTEGER;
    value.data.integer = integer;
    CHECK(bvs_assign(&h->store, &key, &value) == BVS_OK);
    return 0;
}

static int equals(Harness *h, const char *name, int16_t integer)
{
    BasicVariableKey key = key_of(name);
    BasicVariableValue value = {0};
    CHECK(bvs_get(&h->store, &key, &value) == BVS_OK);
    CHECK(value.type == (uint8_t)BVT_INTEGER && value.data.integer == integer);
    return 0;
}

static int step(Harness *h)
{
    size_t i;
    memset(h->output, 0x9bu, sizeof(h->output));
    h->written = 700u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output), &h->written) == BE_OK);
    CHECK(h->written == 0u);
    for (i = 0u; i < sizeof(h->output); ++i) {
        CHECK(h->output[i] == 0x9bu);
    }
    return 0;
}

/* Verify full line atomicity, including unused array and buffer capacity. */
static int failure(Harness *h, BEStatus expected)
{
    BasicProgram before_program = h->program;
    BasicVariableStore before_store = h->store;
    BasicExecutor before_executor = h->executor;
    BasicVariableEntry before_entries[8];
    uint8_t before_storage[sizeof(h->storage)], before_output[sizeof(h->output)];
    memcpy(before_storage, h->storage, sizeof(before_storage));
    memcpy(before_entries, h->entries, sizeof(before_entries));
    memset(h->output, 0x65, sizeof(h->output));
    memcpy(before_output, h->output, sizeof(before_output));
    h->written = 4242u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output), &h->written) == expected);
    CHECK(h->written == 4242u);
    CHECK(memcmp(&before_program, &h->program, sizeof(before_program)) == 0);
    CHECK(memcmp(&before_executor, &h->executor, sizeof(before_executor)) == 0);
    CHECK(memcmp(&before_store, &h->store, sizeof(before_store)) == 0);
    CHECK(memcmp(before_entries, h->entries, sizeof(before_entries)) == 0);
    CHECK(memcmp(before_storage, h->storage, sizeof(before_storage)) == 0);
    CHECK(memcmp(before_output, h->output, sizeof(before_output)) == 0);
    return 0;
}

static int test_program(void)
{
    Harness h;
    uint8_t original[sizeof(h.storage)];
    BasicProgramLine line;
    CHECK(setup(&h, 8u) == 0);
    CHECK(put(&h, 10u, "A%=2") == 0);
    CHECK(put(&h, 20u, "B%=A%+3") == 0);
    CHECK(put(&h, 30u, "PRINT B%") == 0);
    CHECK(put(&h, 40u, "END") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    memcpy(original, h.storage, sizeof(original));
    CHECK(step(&h) == 0 && equals(&h, "A", 2) == 0);
    CHECK(bp_find(&h.program, 20u, &line) == BP_OK);
    CHECK(h.executor.cursor == line.offset);
    CHECK(step(&h) == 0 && equals(&h, "B", 5) == 0);
    CHECK(h.store.count == 2u);
    h.written = 500u;
    CHECK(be_step(&h.executor, h.output, sizeof(h.output), &h.written) == BE_OK);
    CHECK(h.written == 2u && memcmp(h.output, "5\n", 2u) == 0);
    CHECK(step(&h) == 0);
    h.written = 123u;
    CHECK(be_step(&h.executor, h.output, sizeof(h.output), &h.written) == BE_END);
    CHECK(h.written == 123u);
    CHECK(memcmp(original, h.storage, sizeof(original)) == 0);
    return 0;
}

static int test_variants(void)
{
    Harness h;
    CHECK(setup(&h, 8u) == 0);
    CHECK(put(&h, 10u, "a%=9") == 0);
    CHECK(put(&h, 20u, "LET B%=a%+0") == 0);
    CHECK(put(&h, 30u, "B%=B%+1") == 0);
    CHECK(put(&h, 40u, "let c% = b% + 10") == 0);
    CHECK(put(&h, 50u, "D%=C%+255") == 0);
    CHECK(put(&h, 60u, "B% = A% + 255") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(step(&h) == 0 && equals(&h, "A", 9) == 0);
    CHECK(step(&h) == 0 && equals(&h, "B", 9) == 0);
    CHECK(step(&h) == 0 && equals(&h, "B", 10) == 0);
    CHECK(step(&h) == 0 && equals(&h, "C", 20) == 0);
    CHECK(step(&h) == 0 && equals(&h, "D", 275) == 0);
    CHECK(step(&h) == 0 && equals(&h, "B", 264) == 0);
    CHECK(h.store.count == 4u);
    return 0;
}

static int test_limits(void)
{
    static const struct {
        int16_t initial;
        uint8_t addend;
        BEStatus status;
        int16_t expected;
    } cases[] = {
        {INT16_MIN, 0u, BE_OK, INT16_MIN},
        {INT16_MIN, 255u, BE_OK, (int16_t)-32513},
        {-1, 255u, BE_OK, 254},
        {32767, 0u, BE_OK, 32767},
        {32512, 255u, BE_OK, 32767},
        {32513, 255u, BE_INTEGER_OVERFLOW, 777},
        {32767, 1u, BE_INTEGER_OVERFLOW, 777},
        {32767, 255u, BE_INTEGER_OVERFLOW, 777}
    };
    size_t i;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        Harness h;
        char input[32];
        CHECK(setup(&h, 3u) == 0);
        CHECK(inject(&h, "A", cases[i].initial) == 0);
        CHECK(inject(&h, "B", 777) == 0);
        (void)snprintf(input, sizeof(input), "B%%=A%%+%u",
                       (unsigned int)cases[i].addend);
        CHECK(put(&h, 10u, input) == 0);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        if (cases[i].status == BE_OK) {
            CHECK(step(&h) == 0);
            CHECK(equals(&h, "B", cases[i].expected) == 0);
        } else {
            CHECK(failure(&h, cases[i].status) == 0);
            CHECK(equals(&h, "B", 777) == 0);
        }
        CHECK(equals(&h, "A", cases[i].initial) == 0);
    }
    return 0;
}

static int test_errors(void)
{
    Harness h;
    static const uint8_t broken_cache[] = {2,0,0,0xc2,0xef,2,0x20};
    static const uint8_t broken_name[] = {2,0,0,0xc2,0xef,2,0,0,'A'};
    static const uint8_t missing_plus[] = {2,0,0,0xc2,0xef,2,0,0,0xc1};
    static const uint8_t missing_literal[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4};
    static const uint8_t broken_literal[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x19};
    static const uint8_t noncanonical[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x19,9};
    static const uint8_t wrong_op[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xef,0x11};
    static const uint8_t wrong_source[] = {2,0,0,0xc2,0xef,3,0,0,0xc1,0xf4,0x11};
    static const uint8_t extra[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x11,0xf4,0x11};
    static const struct { const uint8_t *bytes; size_t n; BEStatus error; } bad[] = {
        {broken_cache, sizeof(broken_cache), BE_TRUNCATED},
        {broken_name, sizeof(broken_name), BE_TRUNCATED},
        {missing_plus, sizeof(missing_plus), BE_TRUNCATED},
        {missing_literal, sizeof(missing_literal), BE_TRUNCATED},
        {broken_literal, sizeof(broken_literal), BE_TRUNCATED},
        {noncanonical, sizeof(noncanonical), BE_BAD_SEQUENCE},
        {wrong_op, sizeof(wrong_op), BE_BAD_SEQUENCE},
        {wrong_source, sizeof(wrong_source), BE_BAD_SEQUENCE},
        {extra, sizeof(extra), BE_BAD_SEQUENCE}
    };
    size_t i;
    CHECK(setup(&h, 3u) == 0);
    CHECK(put(&h, 10u, "B%=Z%+3") == 0);
    CHECK(inject(&h, "B", 17) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_VARIABLE_NOT_FOUND) == 0);
    CHECK(equals(&h, "B", 17) == 0);
    CHECK(inject(&h, "A", 2) == 0);
    for (i = 0u; i < sizeof(bad)/sizeof(bad[0]); ++i) {
        CHECK(bp_put(&h.program, 10u, bad[i].bytes, bad[i].n) == BP_OK);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(failure(&h, bad[i].error) == 0);
    }
    CHECK(equals(&h, "A", 2) == 0 && equals(&h, "B", 17) == 0);
    return 0;
}

static int test_capacity_cache_and_multi(void)
{
    Harness h;
    static const uint8_t opaque[] = {
        2,0x20,0xef,0xc2,0xef,2,0xf4,0x20,0xc1,0xf4,0x11
    };
    static const uint8_t multi[] = {
        2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x11,0x01,0xbf,' ',0x11
    };
    CHECK(setup(&h, 1u) == 0);
    CHECK(inject(&h, "A", 2) == 0);
    CHECK(put(&h, 10u, "B%=A%+3") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_STORE_FULL) == 0 && h.store.count == 1u);
    CHECK(setup(&h, 2u) == 0);
    CHECK(inject(&h, "A", 2) == 0);
    CHECK(bp_put(&h.program, 10u, opaque, sizeof(opaque)) == BP_OK);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(step(&h) == 0 && equals(&h, "B", 5) == 0);
    CHECK(h.storage[0] != 0u); /* Program body was not rewritten. */
    CHECK(bp_put(&h.program, 10u, multi, sizeof(multi)) == BP_OK);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_UNSUPPORTED) == 0);
    CHECK(put(&h, 10u, "PRINT \"X\":B%=A%+3") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_UNSUPPORTED) == 0);
    CHECK(be_init(&h.executor, &h.program) == BE_OK);
    CHECK(failure(&h, BE_UNSUPPORTED) == 0);
    return 0;
}

int main(void)
{
    CHECK(test_program() == 0);
    CHECK(test_variants() == 0);
    CHECK(test_limits() == 0);
    CHECK(test_errors() == 0);
    CHECK(test_capacity_cache_and_multi() == 0);
    puts("J0.22 native INTEGER addition runtime tests passed");
    return 0;
}
