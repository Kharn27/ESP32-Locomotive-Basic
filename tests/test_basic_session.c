#include "basic_session.h"

#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

typedef struct {
    BasicProgram p;
    uint8_t storage[512], tmp[256], out[512];
    size_t written;
} Fixture;

typedef struct {
    uint8_t storage[512], out[512];
    size_t size, written;
} Snapshot;

static int setup(Fixture *f)
{
    memset(f, 0xa5, sizeof(*f));
    CHECK(bp_init(&f->p, f->storage, sizeof(f->storage)) == BP_OK);
    return 0;
}

static BSResult run_bytes(Fixture *f, const uint8_t *s, size_t length,
                          size_t scratch_capacity, size_t out_capacity)
{
    return bs_process_line(&f->p, s, length, f->tmp, scratch_capacity,
                           f->out, out_capacity, &f->written);
}

static BSResult run(Fixture *f, const char *s)
{
    return run_bytes(f, (const uint8_t *)s, strlen(s),
                     sizeof(f->tmp), sizeof(f->out));
}

static void save(const Fixture *f, Snapshot *s)
{
    memcpy(s->storage, f->storage, sizeof(s->storage));
    memcpy(s->out, f->out, sizeof(s->out));
    s->size = f->p.size;
    s->written = f->written;
}

static int same(const Fixture *f, const Snapshot *s)
{
    CHECK(f->p.size == s->size && f->written == s->written);
    CHECK(memcmp(f->storage, s->storage, sizeof(s->storage)) == 0);
    CHECK(memcmp(f->out, s->out, sizeof(s->out)) == 0);
    CHECK(bp_validate(&f->p) == BP_OK);
    return 0;
}

static int listing(Fixture *f, const char *expected)
{
    size_t n = strlen(expected);
    memset(f->out, 0x6b, sizeof(f->out));
    f->written = 999u;
    CHECK(run(f, " LIST ").status == BS_OK);
    CHECK(f->written == n && memcmp(f->out, expected, n) == 0);
    CHECK(f->out[n] == 0x6bu); /* No NUL appended. */
    CHECK(bp_validate(&f->p) == BP_OK);
    return 0;
}

static int test_edit(void)
{
    Fixture f;
    BasicProgramLine line;
    Snapshot s;
    CHECK(setup(&f) == 0);
    CHECK(run(&f, "30 PRINT \"FIN\"").status == BS_OK && f.written == 0u);
    CHECK(run(&f, "00010 PRINT \"HELLO\"").status == BS_OK);
    CHECK(run(&f, "20 GOTO 30").status == BS_OK);
    CHECK(listing(&f, "10 PRINT \"HELLO\"\n20 GOTO 30\n30 PRINT \"FIN\"\n") == 0);
    CHECK(bp_find(&f.p, 10u, &line) == BP_OK);
    CHECK(run(&f, "10 PRINT \"BONJOUR\"").status == BS_OK);
    CHECK(listing(&f, "10 PRINT \"BONJOUR\"\n20 GOTO 30\n30 PRINT \"FIN\"\n") == 0);
    CHECK(run(&f, "20   ").status == BS_OK && f.written == 0u);
    CHECK(listing(&f, "10 PRINT \"BONJOUR\"\n30 PRINT \"FIN\"\n") == 0);
    save(&f, &s);
    CHECK(run(&f, "20").status == BS_NOT_FOUND && same(&f, &s) == 0);
    CHECK(run(&f, "10  PRINT  1 ").status == BS_OK);
    CHECK(listing(&f, "10  PRINT  1 \n30 PRINT \"FIN\"\n") == 0);
    CHECK(run(&f, "10 PRINT 1").status == BS_OK);
    CHECK(listing(&f, "10 PRINT 1\n30 PRINT \"FIN\"\n") == 0);
    CHECK(run(&f, "10").status == BS_OK);
    CHECK(run(&f, "30 ").status == BS_OK);
    CHECK(listing(&f, "") == 0);
    CHECK(run(&f, "1 PRINT 1").status == BS_OK);
    CHECK(run(&f, "10 PRINT 10").status == BS_OK);
    CHECK(run(&f, "00065535 GOTO 1").status == BS_OK);
    CHECK(listing(&f, "1 PRINT 1\n10 PRINT 10\n65535 GOTO 1\n") == 0);
    return 0;
}

static int test_errors(void)
{
    Fixture f;
    size_t i;
    Snapshot s;
    BSResult r;
    static const char *numbers[] = {
        "0 PRINT 1", "0000 PRINT 1", "65536 PRINT 1",
        "999999999999999999999999999999999999 PRINT 1",
        "00000000000065536 PRINT 1"
    };
    static const char *syntax[] = {
        "10PRINT 1", "10:PRINT 1", "10\tPRINT 1"
    };
    static const char *unknown[] = {
        "10 FOR I=1 TO 5", "10 PRINT I", "10 PRINT 1+2"
    };
    static const uint8_t control[][10] = {
        {'1','0',' ','P','R','I','N','T',' ',0u},
        {'1','0',' ','P','R','I','N','T',' ','\r'},
        {'1','0',' ','P','R','I','N','T',' ','\n'}
    };
    CHECK(setup(&f) == 0);
    CHECK(run(&f, "10 PRINT 1").status == BS_OK);
    for (i = 0u; i < sizeof(numbers)/sizeof(numbers[0]); ++i) {
        save(&f, &s);
        CHECK(run(&f, numbers[i]).status == BS_INVALID_LINE_NUMBER);
        CHECK(same(&f, &s) == 0);
    }
    for (i = 0u; i < sizeof(syntax)/sizeof(syntax[0]); ++i) {
        save(&f, &s);
        CHECK(run(&f, syntax[i]).status == BS_MALFORMED_INPUT);
        CHECK(same(&f, &s) == 0);
    }
    for (i = 0u; i < sizeof(unknown)/sizeof(unknown[0]); ++i) {
        save(&f, &s);
        r = run(&f, unknown[i]);
        CHECK(r.status == BS_TOKENIZER_ERROR);
        CHECK(r.tokenizer_status == BT_UNSUPPORTED_CONSTRUCT);
        CHECK(same(&f, &s) == 0);
    }
    for (i = 0u; i < sizeof(control)/sizeof(control[0]); ++i) {
        save(&f, &s);
        CHECK(run_bytes(&f, control[i], sizeof(control[i]),
                        sizeof(f.tmp), sizeof(f.out)).status == BS_MALFORMED_INPUT);
        CHECK(same(&f, &s) == 0);
    }
    save(&f, &s);
    r = run(&f, "10 PRINT 256");
    CHECK(r.status == BS_TOKENIZER_ERROR &&
          r.tokenizer_status == BT_NUMBER_OUT_OF_RANGE);
    CHECK(same(&f, &s) == 0);
    r = run_bytes(&f, (const uint8_t *)"10 PRINT 1", 10u, 1u, sizeof(f.out));
    CHECK(r.status == BS_TOKENIZER_ERROR && r.tokenizer_status == BT_NO_SPACE);
    CHECK(same(&f, &s) == 0);
    f.p.capacity = f.p.size; /* Valid but full. */
    save(&f, &s);
    r = run(&f, "20 PRINT 2");
    CHECK(r.status == BS_PROGRAM_ERROR && r.program_status == BP_NO_SPACE);
    CHECK(same(&f, &s) == 0);
    return 0;
}

static int test_commands(void)
{
    Fixture f;
    Snapshot s;
    BSResult r;
    size_t i;
    static const char *lists[] = {"LIST", "list", "LiSt", "  LIST  "};
    static const char *news[] = {"NEW", "new", "  NeW  "};
    static const char *unsupported[] = {
        "RUN", "PRINT 1", "GOTO 10", "LIST 10", "PRINT \"A:B\"", " 10 PRINT 1"
    };
    static const char *multiple[] = {"LIST:NEW", "LIST : NEW", "NEW:LIST",
                                      "PRINT 1:NEW"};
    CHECK(setup(&f) == 0);
    CHECK(listing(&f, "") == 0);
    CHECK(run(&f, "10 PRINT 1").status == BS_OK);
    for (i = 0u; i < sizeof(lists)/sizeof(lists[0]); ++i) {
        CHECK(run(&f, lists[i]).status == BS_OK);
        CHECK(f.written == strlen("10 PRINT 1\n"));
    }
    for (i = 0u; i < sizeof(unsupported)/sizeof(unsupported[0]); ++i) {
        save(&f, &s);
        CHECK(run(&f, unsupported[i]).status == BS_UNSUPPORTED_DIRECT);
        CHECK(same(&f, &s) == 0);
    }
    for (i = 0u; i < sizeof(multiple)/sizeof(multiple[0]); ++i) {
        save(&f, &s);
        CHECK(run(&f, multiple[i]).status == BS_MULTIPLE_DIRECT);
        CHECK(same(&f, &s) == 0);
    }
    save(&f, &s);
    r = run_bytes(&f, (const uint8_t *)"LIST", 4u, sizeof(f.tmp), 10u);
    CHECK(r.status == BS_LISTING_ERROR && r.listing_status == BL_NO_SPACE);
    CHECK(same(&f, &s) == 0);
    for (i = 0u; i < sizeof(news)/sizeof(news[0]); ++i) {
        CHECK(run(&f, "10 PRINT 1").status == BS_OK);
        CHECK(run(&f, news[i]).status == BS_OK);
        CHECK(f.written == 0u && f.p.size == 2u &&
              f.storage[0] == 0u && f.storage[1] == 0u);
        CHECK(listing(&f, "") == 0);
    }
    CHECK(run(&f, " ").status == BS_OK && f.written == 0u);
    CHECK(run(&f, "").status == BS_OK && f.written == 0u);
    CHECK(listing(&f, "") == 0);
    return 0;
}

static int test_integration(void)
{
    Fixture f;
    CHECK(setup(&f) == 0);
    CHECK(run(&f, "30 PRINT \"FIN\"").status == BS_OK && f.written == 0u);
    CHECK(run(&f, "10 PRINT \"DEBUT\"").status == BS_OK && f.written == 0u);
    CHECK(run(&f, "20 GOTO 30").status == BS_OK && f.written == 0u);
    CHECK(listing(&f, "10 PRINT \"DEBUT\"\n20 GOTO 30\n30 PRINT \"FIN\"\n") == 0);
    CHECK(run(&f, "20").status == BS_OK && f.written == 0u);
    CHECK(listing(&f, "10 PRINT \"DEBUT\"\n30 PRINT \"FIN\"\n") == 0);
    CHECK(run(&f, "NEW").status == BS_OK && f.written == 0u);
    CHECK(listing(&f, "") == 0);
    return 0;
}

static int test_aliases_and_invalid(void)
{
    Fixture f;
    Snapshot s;
    BSResult r;
    static const uint8_t bad[] = {0xbfu, ' ', 0x19u};
    CHECK(setup(&f) == 0);
    CHECK(run(&f, "10 PRINT 1").status == BS_OK);
    save(&f, &s);
    r = bs_process_line(&f.p, (const uint8_t *)"LIST", 4u,
                        f.tmp, sizeof(f.tmp), f.storage, sizeof(f.storage), &f.written);
    CHECK(r.status == BS_OVERLAP && same(&f, &s) == 0);
    r = bs_process_line(&f.p, (const uint8_t *)"10 PRINT 2", 10u,
                        f.storage, sizeof(f.storage), f.out, sizeof(f.out), &f.written);
    CHECK(r.status == BS_OVERLAP && same(&f, &s) == 0);
    r = bs_process_line(&f.p, f.storage, 1u,
                        f.tmp, sizeof(f.tmp), f.out, sizeof(f.out), &f.written);
    CHECK(r.status == BS_OVERLAP && same(&f, &s) == 0);
    r = bs_process_line(&f.p, (const uint8_t *)"LIST", 4u,
                        f.tmp, sizeof(f.tmp), f.tmp + 1u, sizeof(f.tmp)-1u, &f.written);
    CHECK(r.status == BS_OVERLAP && same(&f, &s) == 0);
    r = bs_process_line(&f.p, (const uint8_t *)"LIST", 4u,
                        f.tmp, sizeof(f.tmp), f.out, sizeof(f.out),
                        (size_t *)(void *)f.out);
    CHECK(r.status == BS_OVERLAP && same(&f, &s) == 0);
    r = bs_process_line(&f.p, (const uint8_t *)"LIST", 4u,
                        f.tmp, sizeof(f.tmp), f.out, sizeof(f.out),
                        (size_t *)(void *)&f.p);
    CHECK(r.status == BS_OVERLAP && same(&f, &s) == 0);
    CHECK(bs_process_line(NULL, (const uint8_t *)"", 0u, f.tmp, sizeof(f.tmp),
                          f.out, sizeof(f.out), &f.written).status == BS_INVALID_ARGUMENT);
    CHECK(bs_process_line(&f.p, NULL, 0u, f.tmp, sizeof(f.tmp),
                          f.out, sizeof(f.out), &f.written).status == BS_INVALID_ARGUMENT);
    CHECK(bs_process_line(&f.p, (const uint8_t *)"", 0u, NULL, 0u,
                          f.out, sizeof(f.out), &f.written).status == BS_INVALID_ARGUMENT);
    CHECK(bs_process_line(&f.p, (const uint8_t *)"", 0u, f.tmp, sizeof(f.tmp),
                          NULL, 0u, &f.written).status == BS_INVALID_ARGUMENT);
    CHECK(bs_process_line(&f.p, (const uint8_t *)"", 0u, f.tmp, sizeof(f.tmp),
                          f.out, sizeof(f.out), NULL).status == BS_INVALID_ARGUMENT);
    CHECK(same(&f, &s) == 0);
    CHECK(bp_init(&f.p, f.storage, sizeof(f.storage)) == BP_OK);
    CHECK(bp_put(&f.p, 20u, bad, sizeof(bad)) == BP_OK);
    save(&f, &s);
    r = run(&f, "LIST");
    CHECK(r.status == BS_LISTING_ERROR && r.listing_status == BL_TRUNCATED);
    CHECK(same(&f, &s) == 0);
    f.storage[0] = 1u;
    r = run(&f, "NEW");
    CHECK(r.status == BS_PROGRAM_ERROR && r.program_status == BP_BAD_FORMAT);
    CHECK(f.storage[0] == 1u);
    return 0;
}

int main(void)
{
    CHECK(test_edit() == 0);
    CHECK(test_errors() == 0);
    CHECK(test_commands() == 0);
    CHECK(test_integration() == 0);
    CHECK(test_aliases_and_invalid() == 0);
    puts("basic_session: OK");
    return 0;
}
