#include "basic_executor.h"
#include "basic_session_runtime.h"
#include "basic_tokenizer.h"
#include "basic_variable_binding.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

typedef struct {
    BasicProgram program;
    uint8_t storage[1024];
    BasicVariableStore store;
    BasicVariableEntry entries[8];
    BasicExecutor executor;
    uint8_t output[128];
    size_t written;
} Harness;

static int setup(Harness *h, size_t capacity)
{
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(bvs_init(&h->store, capacity ? h->entries : NULL, capacity) == BVS_OK);
    return 0;
}

static int put(Harness *h, uint16_t line, const char *source)
{
    uint8_t tokens[128];
    size_t count = 0u;
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      tokens, sizeof(tokens), &count) == BT_OK);
    CHECK(bp_put(&h->program, line, tokens, count) == BP_OK);
    return 0;
}

static BasicVariableKey key(const char *name)
{
    BasicVariableKey k;
    size_t i;
    memset(&k, 0, sizeof(k));
    k.type = (uint8_t)BVT_INTEGER;
    k.name_length = (uint8_t)strlen(name);
    for (i = 0u; i < (size_t)k.name_length; ++i) {
        uint8_t c = (uint8_t)name[i];
        k.name[i] = c >= 'a' && c <= 'z' ? (uint8_t)(c - 'a' + 'A') : c;
    }
    return k;
}

static int has(Harness *h, const char *name, int16_t expected)
{
    BasicVariableKey k = key(name);
    BasicVariableValue v;
    CHECK(bvs_get(&h->store, &k, &v) == BVS_OK);
    CHECK(v.type == (uint8_t)BVT_INTEGER && v.data.integer == expected);
    return 0;
}

static int step_ok(Harness *h, size_t expected_cursor)
{
    memset(h->output, 0xa6, sizeof(h->output));
    h->written = 987u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output),
                  &h->written) == BE_OK);
    CHECK(h->written == 0u && h->executor.cursor == expected_cursor);
    for (size_t i = 0u; i < sizeof(h->output); ++i) {
        CHECK(h->output[i] == 0xa6);
    }
    return 0;
}

static int test_literals_and_names(void)
{
    Harness h;
    BasicProgramLine line;
    uint8_t before[sizeof(h.storage)];
    CHECK(setup(&h, 8u) == 0);
    CHECK(put(&h, 10u, "A%=0") == 0);
    CHECK(put(&h, 20u, "A%=9") == 0);
    CHECK(put(&h, 30u, "A%=10") == 0);
    CHECK(put(&h, 40u, "LET B%=255") == 0);
    CHECK(put(&h, 50u, "a%=2") == 0);
    CHECK(put(&h, 60u, "let abcdefghijk.123%=7") == 0);
    CHECK(put(&h, 70u, "ABCDEFGHIJKLMN.1234567890ABCD%=42") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    memcpy(before, h.storage, sizeof(before));
    for (uint16_t line_no = 10u; line_no <= 70u; line_no += 10u) {
        CHECK(bp_find(&h.program, line_no, &line) == BP_OK);
        CHECK(step_ok(&h, line.next_offset) == 0);
        if (line_no == 10u) CHECK(has(&h, "A", 0) == 0);
        if (line_no == 20u) CHECK(has(&h, "A", 9) == 0);
        if (line_no == 30u) CHECK(has(&h, "A", 10) == 0);
        if (line_no == 40u) CHECK(has(&h, "B", 255) == 0);
        if (line_no == 50u) CHECK(has(&h, "A", 2) == 0);
    }
    CHECK(h.store.count == 4u);
    CHECK(has(&h, "ABCDEFGHIJK.123", 7) == 0);
    CHECK(has(&h, "ABCDEFGHIJKLMN.1234567890ABCD", 42) == 0);
    CHECK(memcmp(h.storage, before, sizeof(before)) == 0);
    h.written = 123u;
    CHECK(be_step(&h.executor, h.output, sizeof(h.output), &h.written) == BE_END);
    CHECK(h.written == 123u);
    return 0;
}

static int test_caches(void)
{
    Harness h;
    static const uint8_t implicit[] = {2u,0x20u,0xefu,0xc1u,0xefu,0x10u};
    static const uint8_t explicit_let[] = {0xa5u,' ',2u,0xefu,0x20u,0xc2u,0xefu,0x19u,255u};
    BasicProgramLine line;
    uint8_t original[sizeof(h.storage)];
    CHECK(setup(&h, 2u) == 0);
    CHECK(bp_put(&h.program, 10u, implicit, sizeof(implicit)) == BP_OK);
    CHECK(bp_put(&h.program, 20u, explicit_let, sizeof(explicit_let)) == BP_OK);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    memcpy(original, h.storage, sizeof(original));
    CHECK(bp_find(&h.program, 10u, &line) == BP_OK);
    CHECK(step_ok(&h, line.next_offset) == 0);
    CHECK(has(&h, "A", 2) == 0);
    CHECK(bp_find(&h.program, 20u, &line) == BP_OK);
    CHECK(step_ok(&h, line.next_offset) == 0);
    CHECK(has(&h, "B", 255) == 0);
    CHECK(memcmp(original, h.storage, sizeof(original)) == 0);
    return 0;
}

static int failure(Harness *h, BEStatus expected)
{
    uint8_t before[sizeof(h->storage)];
    BasicVariableEntry entries_before[8];
    BasicVariableStore store_before = h->store;
    size_t cursor_before = h->executor.cursor;
    memcpy(before, h->storage, sizeof(before));
    memcpy(entries_before, h->entries, sizeof(entries_before));
    memset(h->output, 0x78, sizeof(h->output));
    h->written = 345u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output),
                  &h->written) == expected);
    CHECK(h->executor.cursor == cursor_before && h->written == 345u);
    CHECK(h->store.count == store_before.count &&
          h->store.capacity == store_before.capacity &&
          h->store.entries == store_before.entries);
    CHECK(memcmp(entries_before, h->entries, sizeof(entries_before)) == 0);
    CHECK(memcmp(before, h->storage, sizeof(before)) == 0);
    for (size_t i = 0u; i < sizeof(h->output); ++i) {
        CHECK(h->output[i] == 0x78);
    }
    return 0;
}

static int test_invalid_images(void)
{
    static const uint8_t bad1[] = {2u,0u}; /* truncated cache */
    static const uint8_t bad2[] = {2u,0u,0u}; /* missing name */
    static const uint8_t bad3[] = {2u,0u,0u,'A','B','C'}; /* unterminated name */
    static const uint8_t bad4[] = {2u,0u,0u,0xc1u,0x10u};
    static const uint8_t bad5[] = {2u,0u,0u,0xc1u,0xefu,0x19u};
    static const uint8_t bad6[] = {2u,0u,0u,0xc1u,0xefu,0x19u,9u};
    static const uint8_t bad7[] = {0xa5u,3u,0u,0u,0xc1u,0xefu,0x10u};
    static const uint8_t bad8[] = {2u,0u,0u,0xc1u,0xefu,0x1au};
    static const uint8_t bad9[] = {2u,0u,0u,0xc1u,0xefu,0x10u,0x01u,0x98u};
    static const uint8_t *const data[] = {
        bad1,bad2,bad3,bad4,bad5,bad6,bad7,bad8,bad9
    };
    static const size_t len[] = {
        sizeof(bad1),sizeof(bad2),sizeof(bad3),sizeof(bad4),sizeof(bad5),
        sizeof(bad6),sizeof(bad7),sizeof(bad8),sizeof(bad9)
    };
    static const BEStatus errors[] = {
        BE_TRUNCATED,BE_TRUNCATED,BE_TRUNCATED,BE_BAD_SEQUENCE,
        BE_TRUNCATED,BE_BAD_SEQUENCE,BE_BAD_SEQUENCE,BE_BAD_SEQUENCE,
        BE_UNSUPPORTED
    };
    Harness h;
    CHECK(setup(&h, 2u) == 0);
    for (size_t i = 0u; i < sizeof(data)/sizeof(data[0]); ++i) {
        CHECK(bp_put(&h.program, 10u, data[i], len[i]) == BP_OK);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(failure(&h, errors[i]) == 0);
    }
    CHECK(h.store.count == 0u);
    CHECK(put(&h, 10u, "PRINT \"X\":A%=2") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_UNSUPPORTED) == 0);
    CHECK(put(&h, 10u, "A%=2:END") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_UNSUPPORTED) == 0);
    CHECK(put(&h, 10u, "GOTO 20:A%=2") == 0);
    CHECK(put(&h, 20u, "END") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_UNSUPPORTED) == 0);
    CHECK(put(&h, 10u, "END:LET A%=2") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_UNSUPPORTED) == 0);
    return 0;
}

static int test_full_and_atomic(void)
{
    Harness h;
    BasicVariableKey a = key("A"), b = key("B"), invalid = a;
    BasicVariableValue value, wrong;
    BasicVariableEntry snapshot[8];
    CHECK(setup(&h, 1u) == 0);
    CHECK(put(&h, 10u, "A%=2") == 0);
    CHECK(put(&h, 20u, "B%=3") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    {
        BasicProgramLine line;
        CHECK(bp_find(&h.program, 10u, &line) == BP_OK);
        CHECK(step_ok(&h, line.next_offset) == 0);
    }
    CHECK(has(&h, "A", 2) == 0);
    CHECK(failure(&h, BE_STORE_FULL) == 0);
    CHECK(h.store.count == 1u);
    memset(&value, 0, sizeof(value));
    value.type = (uint8_t)BVT_INTEGER;
    value.data.integer = 123;
    CHECK(bvs_assign(&h.store, &a, &value) == BVS_OK);
    CHECK(has(&h, "A", 123) == 0 && h.store.count == 1u);
    memcpy(snapshot, h.entries, sizeof(snapshot));
    CHECK(bvs_assign(&h.store, &b, &value) == BVS_FULL);
    invalid.name[0] = (uint8_t)'a';
    CHECK(bvs_assign(&h.store, &invalid, &value) == BVS_INVALID_KEY);
    wrong = value; wrong.type = (uint8_t)BVT_STRING;
    CHECK(bvs_assign(&h.store, &a, &wrong) == BVS_INVALID_TYPE);
    CHECK(bvs_assign(&h.store, &h.entries[0].key, &value) ==
          BVS_OVERLAPPING_MEMORY);
    CHECK(memcmp(snapshot, h.entries, sizeof(snapshot)) == 0);
    h.store.count = 2u;
    CHECK(failure(&h, BE_INVALID_STORE) == 0);
    h.store.count = 1u;
    h.entries[0].value.type = (uint8_t)BVT_REAL;
    CHECK(failure(&h, BE_INVALID_STORE) == 0);
    return 0;
}

static int test_overlap_and_legacy(void)
{
    Harness h;
    size_t saved;
    CHECK(setup(&h, 1u) == 0);
    CHECK(put(&h, 10u, "A%=2") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    saved = 91u;
    CHECK(be_step(&h.executor, (uint8_t *)(void *)h.entries, 1u, &saved) ==
          BE_OVERLAP);
    CHECK(saved == 91u && h.store.count == 0u);
    CHECK(be_init(&h.executor, &h.program) == BE_OK);
    CHECK(failure(&h, BE_UNSUPPORTED) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    h.store.capacity = SIZE_MAX;
    CHECK(failure(&h, BE_INVALID_STORE) == 0);
    h.store.capacity = 1u;
    --h.program.size; /* Damaged record/sentinel, not merely bad body. */
    CHECK(failure(&h, BE_BAD_PROGRAM) == 0);
    ++h.program.size;
    return 0;
}

static int test_output_capacity(void)
{
    Harness h;
    BasicProgramLine line;
    CHECK(setup(&h, 1u) == 0);
    CHECK(put(&h, 10u, "PRINT \"X\"") == 0);
    CHECK(put(&h, 20u, "A%=255") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    memset(h.output, 0x71, sizeof(h.output));
    h.written = 333u;
    CHECK(be_step(&h.executor, h.output, 0u, &h.written) == BE_NO_SPACE);
    CHECK(h.written == 333u && h.executor.cursor == 0u &&
          h.store.count == 0u && h.output[0] == 0x71u);
    CHECK(be_step(&h.executor, h.output, sizeof(h.output),
                  &h.written) == BE_OK);
    CHECK(h.written == 2u && memcmp(h.output, "X\n", 2u) == 0);
    CHECK(bp_find(&h.program, 20u, &line) == BP_OK);
    h.written = 333u;
    h.output[0] = 0x71u;
    CHECK(be_step(&h.executor, h.output, 0u, &h.written) == BE_OK);
    CHECK(h.written == 0u && h.output[0] == 0x71u &&
          h.executor.cursor == line.next_offset);
    CHECK(has(&h, "A", 255) == 0);
    return 0;
}

static int submit(Harness *h, BasicSessionRuntime *rt, const char *text,
                  BSRStatus expected)
{
    uint8_t scratch[256];
    BSRResult result = bsr_submit(rt, (const uint8_t *)text, strlen(text),
                                  scratch, sizeof(scratch), h->output,
                                  sizeof(h->output), &h->written);
    CHECK(result.status == expected);
    return 0;
}

static int test_run_new_and_regressions(void)
{
    Harness h;
    BasicSessionRuntime rt;
    BSRResult r;
    CHECK(setup(&h, 3u) == 0);
    CHECK(put(&h, 10u, "A%=2") == 0);
    CHECK(put(&h, 20u, "PRINT \"PASS\"") == 0);
    CHECK(put(&h, 30u, "GOTO 50") == 0);
    CHECK(put(&h, 40u, "PRINT \"SKIP\"") == 0);
    CHECK(put(&h, 50u, "'COMMENT") == 0);
    CHECK(put(&h, 60u, "REM IGNORE") == 0);
    CHECK(put(&h, 70u, "END") == 0);
    CHECK(put(&h, 80u, "PRINT \"NEVER\"") == 0);
    CHECK(bsr_init_with_store(&rt, &h.program, &h.store).status == BSR_OK);
    h.written = 10u;
    CHECK(submit(&h, &rt, "RUN", BSR_OK) == 0);
    CHECK(h.written == 0u && h.store.count == 0u);
    r = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(r.status == BSR_OK && h.written == 0u && h.store.count == 1u);
    CHECK(has(&h, "A", 2) == 0);
    r = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(r.status == BSR_OK && h.written == 5u &&
          memcmp(h.output, "PASS\n", 5u) == 0);
    r = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(r.status == BSR_OK); /* GOTO 50 */
    r = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(r.status == BSR_OK); /* apostrophe */
    r = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(r.status == BSR_OK); /* REM */
    r = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(r.status == BSR_OK); /* END */
    r = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(r.status == BSR_END && rt.state == BSR_IDLE);
    CHECK(submit(&h, &rt, "RUN", BSR_OK) == 0);
    CHECK(h.store.count == 0u); /* previous successful run cleared */
    CHECK(submit(&h, &rt, "NEW", BSR_OK) == 0);
    CHECK(h.store.count == 0u && rt.state == BSR_IDLE);
    CHECK(h.program.size == 2u);
    CHECK(submit(&h, &rt, "10 B%=9", BSR_OK) == 0);
    CHECK(submit(&h, &rt, "RUN", BSR_OK) == 0);
    r = bsr_step(&rt, h.output, sizeof(h.output), &h.written);
    CHECK(r.status == BSR_OK && has(&h, "B", 9) == 0);
    CHECK(submit(&h, &rt, "RUN", BSR_OK) == 0);
    CHECK(h.store.count == 0u);
    h.store.count = 4u;
    CHECK(submit(&h, &rt, "NEW", BSR_EXECUTOR_ERROR) == 0);
    CHECK(h.program.size > 2u && rt.state == BSR_RUNNING);
    CHECK(submit(&h, &rt, "RUN", BSR_EXECUTOR_ERROR) == 0);
    h.store.count = 0u;
    return 0;
}

int main(void)
{
    CHECK(test_literals_and_names() == 0);
    CHECK(test_caches() == 0);
    CHECK(test_invalid_images() == 0);
    CHECK(test_full_and_atomic() == 0);
    CHECK(test_overlap_and_legacy() == 0);
    CHECK(test_output_capacity() == 0);
    CHECK(test_run_new_and_regressions() == 0);
    puts("integer_assignment_runtime: OK (synthetic CPC-derived fixtures)");
    return 0;
}
