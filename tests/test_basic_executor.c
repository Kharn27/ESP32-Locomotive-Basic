#include "basic_executor.h"
#include "basic_tokenizer.h"

#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

typedef struct {
    BasicProgram program;
    uint8_t storage[1024];
    uint8_t tokens[512];
    uint8_t output[512];
    BasicExecutor executor;
    size_t written;
} Fixture;

static int setup(Fixture *f)
{
    memset(f, 0xa5, sizeof(*f));
    CHECK(bp_init(&f->program, f->storage, sizeof(f->storage)) == BP_OK);
    return 0;
}

static int put(Fixture *f, uint16_t number, const char *source)
{
    size_t n = 777u;
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source), f->tokens,
                      sizeof(f->tokens), &n) == BT_OK);
    CHECK(bp_put(&f->program, number, f->tokens, n) == BP_OK);
    return 0;
}

static int put_raw(Fixture *f, uint16_t number,
                   const uint8_t *bytes, size_t length)
{
    CHECK(bp_put(&f->program, number, bytes, length) == BP_OK);
    return 0;
}

static int start(Fixture *f)
{
    CHECK(be_init(&f->executor, &f->program) == BE_OK);
    return 0;
}

static int step(Fixture *f, const uint8_t *expected, size_t length)
{
    size_t i;
    memset(f->output, 0x69, sizeof(f->output));
    f->written = SIZE_MAX;
    CHECK(be_step(&f->executor, f->output, sizeof(f->output),
                  &f->written) == BE_OK);
    CHECK(f->written == length);
    CHECK(memcmp(f->output, expected, length) == 0);
    for (i = length; i < sizeof(f->output); ++i) {
        CHECK(f->output[i] == 0x69u);
    }
    CHECK(bp_validate(&f->program) == BP_OK);
    return 0;
}

static int unchanged_after(Fixture *f, BEStatus expected,
                           uint8_t *output, size_t capacity, size_t *written)
{
    BasicExecutor before = f->executor;
    uint8_t saved[1024];
    uint8_t out_snapshot[512];
    size_t saved_written = *written;
    CHECK(capacity <= sizeof(out_snapshot));
    memcpy(saved, f->storage, sizeof(saved));
    memcpy(out_snapshot, output, capacity);
    CHECK(be_step(&f->executor, output, capacity, written) == expected);
    CHECK(f->executor.program == before.program &&
          f->executor.cursor == before.cursor);
    CHECK(*written == saved_written);
    CHECK(memcmp(f->storage, saved, sizeof(saved)) == 0);
    CHECK(memcmp(output, out_snapshot, capacity) == 0);
    return 0;
}

static int fails(Fixture *f, BEStatus status, size_t capacity)
{
    memset(f->output, 0x79, sizeof(f->output));
    f->written = 777u;
    CHECK(unchanged_after(f, status, f->output, capacity, &f->written) == 0);
    return 0;
}

static int test_main_path(void)
{
    Fixture f;
    CHECK(setup(&f) == 0);
    CHECK(put(&f, 40u, "PRINT 10") == 0);
    CHECK(put(&f, 20u, "GOTO 40") == 0);
    CHECK(put(&f, 30u, "PRINT \"SAUTE\"") == 0);
    CHECK(put(&f, 10u, "PRINT \"DEBUT\"") == 0);
    CHECK(start(&f) == 0);
    CHECK(step(&f, (const uint8_t *)"DEBUT\n", 6u) == 0);
    CHECK(step(&f, (const uint8_t *)"", 0u) == 0);
    CHECK(step(&f, (const uint8_t *)"10\n", 3u) == 0);
    CHECK(fails(&f, BE_END, sizeof(f.output)) == 0);
    CHECK(fails(&f, BE_END, sizeof(f.output)) == 0);
    return 0;
}

static int test_empty_and_natural_end(void)
{
    Fixture f;
    CHECK(setup(&f) == 0);
    CHECK(start(&f) == 0);
    CHECK(fails(&f, BE_END, sizeof(f.output)) == 0);
    CHECK(put(&f, 10u, "PRINT") == 0);
    CHECK(put(&f, 20u, "  ") == 0);
    CHECK(put(&f, 30u, "PRINT \"\"") == 0);
    CHECK(start(&f) == 0);
    CHECK(step(&f, (const uint8_t *)"\n", 1u) == 0);
    CHECK(step(&f, (const uint8_t *)"", 0u) == 0);
    CHECK(step(&f, (const uint8_t *)"\n", 1u) == 0);
    CHECK(fails(&f, BE_END, sizeof(f.output)) == 0);
    return 0;
}

static int test_strings_and_numbers(void)
{
    Fixture f;
    static const uint8_t non_ascii[] = {
        'P','R','I','N','T',' ','"',0xe9u,':','X','"'
    };
    size_t n = 111u;
    CHECK(setup(&f) == 0);
    CHECK(put(&f, 10u, "PRINT 0:PRINT 9:PRINT 10:PRINT 255") == 0);
    CHECK(put(&f, 20u, "PRINT \"A:B\":PRINT \"\"") == 0);
    CHECK(put(&f, 30u, "PRINT \"NON FERMEE:ET LA SUITE") == 0);
    CHECK(bt_tokenize(non_ascii, sizeof(non_ascii), f.tokens,
                      sizeof(f.tokens), &n) == BT_OK);
    CHECK(bp_put(&f.program, 40u, f.tokens, n) == BP_OK);
    CHECK(start(&f) == 0);
    CHECK(step(&f, (const uint8_t *)"0\n9\n10\n255\n", 11u) == 0);
    CHECK(step(&f, (const uint8_t *)"A:B\n\n", 5u) == 0);
    CHECK(step(&f, (const uint8_t *)"NON FERMEE:ET LA SUITE\n", 23u) == 0);
    {
        static const uint8_t expected[] = {0xe9u,':','X','\n'};
        CHECK(step(&f, expected, sizeof(expected)) == 0);
    }
    CHECK(fails(&f, BE_END, sizeof(f.output)) == 0);
    return 0;
}

static int test_branches(void)
{
    Fixture f;
    CHECK(setup(&f) == 0);
    CHECK(put(&f, 10u, "PRINT \"A\":GOTO 30:PRINT \"NEVER\"") == 0);
    CHECK(put(&f, 20u, "PRINT \"SKIP\"") == 0);
    CHECK(put(&f, 30u, "PRINT \"B\":PRINT 255") == 0);
    CHECK(start(&f) == 0);
    CHECK(step(&f, (const uint8_t *)"A\n", 2u) == 0);
    CHECK(step(&f, (const uint8_t *)"B\n255\n", 6u) == 0);
    CHECK(fails(&f, BE_END, sizeof(f.output)) == 0);

    CHECK(setup(&f) == 0);
    CHECK(put(&f, 10u, "PRINT 1") == 0);
    CHECK(put(&f, 20u, "GOTO 10") == 0);
    CHECK(start(&f) == 0);
    CHECK(step(&f, (const uint8_t *)"1\n", 2u) == 0);
    CHECK(step(&f, (const uint8_t *)"", 0u) == 0);
    CHECK(step(&f, (const uint8_t *)"1\n", 2u) == 0);
    CHECK(step(&f, (const uint8_t *)"", 0u) == 0);

    CHECK(setup(&f) == 0);
    CHECK(put(&f, 10u, "GOTO 10") == 0);
    CHECK(start(&f) == 0);
    CHECK(step(&f, (const uint8_t *)"", 0u) == 0);
    CHECK(f.executor.cursor == 0u);
    CHECK(step(&f, (const uint8_t *)"", 0u) == 0);
    CHECK(f.executor.cursor == 0u);
    return 0;
}

static int test_missing_target_and_short_buffers(void)
{
    Fixture f;
    CHECK(setup(&f) == 0);
    CHECK(put(&f, 10u, "PRINT \"YES\":GOTO 100") == 0);
    CHECK(start(&f) == 0);
    CHECK(fails(&f, BE_MISSING_TARGET, sizeof(f.output)) == 0);
    CHECK(put(&f, 100u, "PRINT 255") == 0);
    CHECK(start(&f) == 0); /* Modification before execution only. */
    CHECK(fails(&f, BE_NO_SPACE, 3u) == 0);
    f.written = 999u;
    CHECK(be_step(&f.executor, f.output, 4u, &f.written) == BE_OK);
    CHECK(f.written == 4u && memcmp(f.output, "YES\n", 4u) == 0);
    CHECK(step(&f, (const uint8_t *)"255\n", 4u) == 0);
    CHECK(fails(&f, BE_END, 0u) == 0);
    return 0;
}

static int test_unsupported_and_unreached(void)
{
    Fixture f;
    static const char *commands[] = {"LIST", "RUN", "NEW"};
    size_t i;
    for (i = 0u; i < sizeof(commands)/sizeof(commands[0]); ++i) {
        CHECK(setup(&f) == 0);
        CHECK(put(&f, 10u, "PRINT 1") == 0);
        CHECK(put(&f, 20u, commands[i]) == 0);
        CHECK(start(&f) == 0);
        CHECK(step(&f, (const uint8_t *)"1\n", 2u) == 0);
        CHECK(fails(&f, BE_UNSUPPORTED, sizeof(f.output)) == 0);
    }
    CHECK(setup(&f) == 0);
    CHECK(put(&f, 10u, "GOTO 30:RUN") == 0);
    CHECK(put(&f, 20u, "LIST") == 0);
    CHECK(put(&f, 30u, "PRINT 9") == 0);
    CHECK(start(&f) == 0);
    CHECK(step(&f, (const uint8_t *)"", 0u) == 0);
    CHECK(step(&f, (const uint8_t *)"9\n", 2u) == 0);
    CHECK(fails(&f, BE_END, sizeof(f.output)) == 0);
    return 0;
}

static int test_bad_tokens(void)
{
    Fixture f;
    size_t i;
    static const uint8_t t0[] = {0xbfu,' ',0x19u};
    static const uint8_t t1[] = {0xa0u,' ',0x1eu};
    static const uint8_t t2[] = {0xa0u,' ',0x1eu,10u};
    static const uint8_t t3[] = {0xbfu,' ',0x88u};
    static const uint8_t t4[] = {0xbfu,' ',0x19u,9u};
    static const uint8_t t5[] = {0xbfu,0x01u,0x01u,0xbfu};
    static const uint8_t t6[] = {0xbfu,' ',0x0eu,0x01u};
    static const uint8_t t7[] = {0xbfu,' ','"','A','\r'};
    static const uint8_t t8[] = {0x1du,0u,0u};
    static const uint8_t t9[] = {0xa0u,' ',0x1eu,0u,0u};
    static const uint8_t t10[] = {0xbfu,' ',0u};
    static const struct {
        const uint8_t *bytes;
        size_t size;
        BEStatus status;
    } cases[] = {
        {t0, sizeof(t0), BE_TRUNCATED},
        {t1, sizeof(t1), BE_TRUNCATED},
        {t2, sizeof(t2), BE_TRUNCATED},
        {t3, sizeof(t3), BE_UNKNOWN_TOKEN},
        {t4, sizeof(t4), BE_BAD_SEQUENCE},
        {t5, sizeof(t5), BE_BAD_SEQUENCE},
        {t6, sizeof(t6), BE_BAD_SEQUENCE},
        {t7, sizeof(t7), BE_BAD_SEQUENCE},
        {t8, sizeof(t8), BE_UNKNOWN_TOKEN},
        {t9, sizeof(t9), BE_BAD_SEQUENCE},
        {t10, sizeof(t10), BE_BAD_SEQUENCE}
    };
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        CHECK(setup(&f) == 0);
        CHECK(put_raw(&f, 10u, cases[i].bytes, cases[i].size) == 0);
        CHECK(start(&f) == 0);
        CHECK(fails(&f, cases[i].status, sizeof(f.output)) == 0);
    }
    /* Unreached garbage after a branch is not inspected. */
    CHECK(setup(&f) == 0);
    {
        static const uint8_t line[] = {
            0xa0u,' ',0x1eu,20u,0u,0x01u,0xbfu,' ',0x19u
        };
        CHECK(put_raw(&f, 10u, line, sizeof(line)) == 0);
    }
    CHECK(put(&f, 20u, "PRINT 1") == 0);
    CHECK(start(&f) == 0);
    CHECK(step(&f, (const uint8_t *)"", 0u) == 0);
    CHECK(step(&f, (const uint8_t *)"1\n", 2u) == 0);
    return 0;
}

static int test_invalid_and_overlap(void)
{
    Fixture f;
    BasicExecutor old;
    CHECK(setup(&f) == 0);
    CHECK(put(&f, 10u, "PRINT 1") == 0);
    CHECK(be_init(NULL, &f.program) == BE_INVALID_ARGUMENT);
    CHECK(be_init(&f.executor, NULL) == BE_INVALID_ARGUMENT);
    CHECK(start(&f) == 0);
    old = f.executor;
    CHECK(be_init((BasicExecutor *)(void *)&f.program, &f.program) == BE_OVERLAP);
    CHECK(f.executor.program == old.program && f.executor.cursor == old.cursor);
    CHECK(be_step(NULL, f.output, sizeof(f.output), &f.written) == BE_INVALID_ARGUMENT);
    CHECK(be_step(&f.executor, NULL, 0u, &f.written) == BE_INVALID_ARGUMENT);
    CHECK(be_step(&f.executor, f.output, sizeof(f.output), NULL) == BE_INVALID_ARGUMENT);
    f.written = 222u;
    CHECK(be_step(&f.executor, f.storage, sizeof(f.storage), &f.written) == BE_OVERLAP);
    CHECK(be_step(&f.executor, (uint8_t *)(void *)&f.executor,
                  sizeof(f.executor), &f.written) == BE_OVERLAP);
    CHECK(be_step(&f.executor, (uint8_t *)(void *)&f.program,
                  sizeof(f.program), &f.written) == BE_OVERLAP);
    CHECK(be_step(&f.executor, f.output, sizeof(f.output), &f.program.size) == BE_OVERLAP);
    CHECK(be_step(&f.executor, f.output, sizeof(f.output),
                  (size_t *)(void *)f.output) == BE_OVERLAP);
    CHECK(f.written == 222u && f.executor.cursor == old.cursor);
    CHECK(bp_validate(&f.program) == BP_OK);
    f.storage[0] = 1u; /* Corrupt record length, not a valid program. */
    CHECK(fails(&f, BE_BAD_PROGRAM, sizeof(f.output)) == 0);
    CHECK(be_init(&f.executor, &f.program) == BE_BAD_PROGRAM);
    CHECK(f.executor.cursor == old.cursor);
    return 0;
}

int main(void)
{
    CHECK(test_main_path() == 0);
    CHECK(test_empty_and_natural_end() == 0);
    CHECK(test_strings_and_numbers() == 0);
    CHECK(test_branches() == 0);
    CHECK(test_missing_target_and_short_buffers() == 0);
    CHECK(test_unsupported_and_unreached() == 0);
    CHECK(test_bad_tokens() == 0);
    CHECK(test_invalid_and_overlap() == 0);
    puts("basic_executor: OK");
    return 0;
}
