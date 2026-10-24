#include "basic_session_runtime.h"
#include "basic_tokenizer.h"
#include "basic_listing.h"

#include <stdio.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); \
    return 1; } } while (0)

typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    uint8_t storage[2048];
    uint8_t temporary[512];
    uint8_t output[2048];
    size_t written;
} Fixture;

static int init(Fixture *f)
{
    memset(f, 0xa5, sizeof(*f));
    CHECK(bp_init(&f->program, f->storage, sizeof(f->storage)) == BP_OK);
    CHECK(bsr_init(&f->runtime, &f->program).status == BSR_OK);
    return 0;
}

static BSRResult submit(Fixture *f, const char *s)
{
    return bsr_submit(&f->runtime, (const uint8_t *)s, strlen(s),
                      f->temporary, sizeof(f->temporary),
                      f->output, sizeof(f->output), &f->written);
}

static int token_case(const char *s, const uint8_t *expected, size_t n)
{
    uint8_t body[512];
    size_t written = 777u;
    memset(body, 0xa5, sizeof(body));
    CHECK(bt_tokenize((const uint8_t *)s, strlen(s),
                      body, sizeof(body), &written) == BT_OK);
    CHECK(written == n && memcmp(body, expected, n) == 0);
    CHECK(body[n] == 0xa5u);
    return 0;
}

static int test_cpc_markers(void)
{
    static const uint8_t rem[] = {0xc5u, ' ', 'P', 'R', 'I', 'N', ':', '"'};
    static const uint8_t apostrophe[] = {0x01u, 0xc0u, ' ', 'P', 'R', 'I', 'N', 'T', ':', '"'};
    static const uint8_t after_rem[] = {0xbfu, ' ', 0x19u, 42u,
                                        0x01u, 0xc5u, ' ', ':', 'G', 'O', 'T', 'O'};
    static const uint8_t after_quote[] = {0xbfu, ' ', '"', 'X', '"',
                                           0x01u, 0x01u, 0xc0u, ' ', ':', '"'};
    static const uint8_t implicit[] = {0xbfu, ' ', '"', 'X', '"',
                                        0x01u, 0xc0u, ' ', 'R', 'U', 'N'};
    static const uint8_t empty_rem[] = {0xc5u};
    static const uint8_t empty_ap[] = {0x01u, 0xc0u};
    CHECK(token_case("REM PRINT:\"", rem, sizeof(rem)) == 0);
    CHECK(token_case("' PRINT:\"", apostrophe, sizeof(apostrophe)) == 0);
    CHECK(token_case("PRINT 42:REM :GOTO", after_rem, sizeof(after_rem)) == 0);
    CHECK(token_case("PRINT \"X\":' :\"", after_quote, sizeof(after_quote)) == 0);
    CHECK(token_case("PRINT \"X\"' RUN", implicit, sizeof(implicit)) == 0);
    CHECK(token_case("REM", empty_rem, sizeof(empty_rem)) == 0);
    CHECK(token_case("'", empty_ap, sizeof(empty_ap)) == 0);
    return 0;
}

static int roundtrip(const uint8_t *input, size_t input_length)
{
    uint8_t original[512], text[512], encoded[512];
    size_t original_length = 99u, text_length = 88u, encoded_length = 77u;
    CHECK(bt_tokenize(input, input_length, original,
                      sizeof(original), &original_length) == BT_OK);
    CHECK(bl_detokenize(original, original_length, text,
                        sizeof(text), &text_length) == BL_OK);
    CHECK(bt_tokenize(text, text_length, encoded,
                      sizeof(encoded), &encoded_length) == BT_OK);
    CHECK(original_length == encoded_length);
    CHECK(memcmp(original, encoded, original_length) == 0);
    return 0;
}

static int test_roundtrips(void)
{
    static const char *sources[] = {
        "REM", "REM   ", "REM PRINT:GOTO:RUN \" QUOTES ",
        "'", "'  ", "'PRINT:REM:NEW \"", " PRINT \"HI\":REM \"HELLO:PRINT\"",
        "PRINT 42:'HERE : PRINT 255", "PRINT \"X\"' :IGNORE",
        "  REM : PRINT : GOTO 1", "PRINT \"LITERAL:RUN\"",
        "PRINT \"A\":PRINT \"B\":' AFTER"
    };
    static const uint8_t in_string[] = {'P','R','I','N','T',' ','"',0x01u,':','"',
                                         ':','R','E','M',' ','T','A','I','L'};
    static const uint8_t in_comment[] = {'\'', ' ', ':', 0x01u, 0xc5u, 0xbfu,
                                          0x80u, '"', 'T'};
    size_t i;
    for (i = 0u; i < sizeof(sources)/sizeof(sources[0]); ++i) {
        CHECK(roundtrip((const uint8_t *)sources[i], strlen(sources[i])) == 0);
    }
    CHECK(roundtrip(in_string, sizeof(in_string)) == 0);
    CHECK(roundtrip(in_comment, sizeof(in_comment)) == 0);
    return 0;
}

static int test_errors_and_atomicity(void)
{
    uint8_t output[64], original[64];
    size_t written;
    static const uint8_t forbidden[] = {'R','E','M',' ', 'X', '\n'};
    static const uint8_t forbidden2[] = {'\'',' ', 'X', 0u};
    static const uint8_t bad_marker[] = {0xc0u, 'X'};
    static const uint8_t bad_rem[] = {0xc5u, ' ', '\r'};
    static const uint8_t bad_ap[] = {0x01u, 0xc0u, 0u};
    static const uint8_t bad_prefix[] = {0x01u};
    static const uint8_t valid[] = {0x01u, 0xc0u, 'X', ':', 0xbfu};
    memset(output, 0x3au, sizeof(output));
    memcpy(original, output, sizeof(output));
    written = 999u;
    CHECK(bt_tokenize((const uint8_t *)"REM ABC", 7u, output, 6u,
                      &written) == BT_NO_SPACE);
    CHECK(written == 999u && memcmp(output, original, sizeof(output)) == 0);
    CHECK(bt_tokenize(forbidden, sizeof(forbidden), output,
                      sizeof(output), &written) == BT_MALFORMED_INPUT);
    CHECK(bt_tokenize(forbidden2, sizeof(forbidden2), output,
                      sizeof(output), &written) == BT_MALFORMED_INPUT);
    CHECK(written == 999u && memcmp(output, original, sizeof(output)) == 0);
    CHECK(bl_detokenize(valid, sizeof(valid), output, 2u,
                        &written) == BL_NO_SPACE);
    CHECK(bl_detokenize(bad_marker, sizeof(bad_marker), output,
                        sizeof(output), &written) == BL_UNKNOWN_TOKEN);
    CHECK(bl_detokenize(bad_rem, sizeof(bad_rem), output,
                        sizeof(output), &written) == BL_BAD_SEQUENCE);
    CHECK(bl_detokenize(bad_ap, sizeof(bad_ap), output,
                        sizeof(output), &written) == BL_BAD_SEQUENCE);
    CHECK(bl_detokenize(bad_prefix, sizeof(bad_prefix), output,
                        sizeof(output), &written) == BL_BAD_SEQUENCE);
    CHECK(written == 999u && memcmp(output, original, sizeof(output)) == 0);
    CHECK(bl_detokenize(valid, sizeof(valid), output,
                        sizeof(output), &written) == BL_OK);
    CHECK(written == 4u && memcmp(output, "'X:\xbf", 4u) == 0);
    return 0;
}

static int expect_step(Fixture *f, const char *expected)
{
    size_t n = strlen(expected);
    memset(f->output, 0x5cu, sizeof(f->output));
    f->written = 444u;
    CHECK(bsr_step(&f->runtime, f->output, sizeof(f->output),
                   &f->written).status == BSR_OK);
    CHECK(f->written == n && memcmp(f->output, expected, n) == 0);
    CHECK(f->output[n] == 0x5cu);
    return 0;
}

static int test_session_run_and_list(void)
{
    Fixture f;
    static const char *sources[] = {
        "60 REM", "20 PRINT \"BONJOUR\":REM PRINT \"INTERDIT\":GOTO 90",
        "10 REM :PRINT \"HIDDEN\"", "40 PRINT 42",
        "30 ' : PRINT \"HIDDEN\"",
        "50 PRINT \"END\":' : PRINT \"NEVER\"",
        "70 '"
    };
    const char *expected =
        "10 REM :PRINT \"HIDDEN\"\n"
        "20 PRINT \"BONJOUR\":REM PRINT \"INTERDIT\":GOTO 90\n"
        "30 ' : PRINT \"HIDDEN\"\n"
        "40 PRINT 42\n"
        "50 PRINT \"END\":' : PRINT \"NEVER\"\n"
        "60 REM\n"
        "70 '\n";
    size_t i;
    CHECK(init(&f) == 0);
    for (i = 0u; i < sizeof(sources)/sizeof(sources[0]); ++i) {
        CHECK(submit(&f, sources[i]).status == BSR_OK);
    }
    CHECK(submit(&f, "LIST").status == BSR_OK);
    CHECK(f.written == strlen(expected));
    CHECK(memcmp(f.output, expected, f.written) == 0);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(f.runtime.executor.cursor == 0u && f.runtime.state == BSR_RUNNING);
    CHECK(expect_step(&f, "") == 0);
    CHECK(expect_step(&f, "BONJOUR\n") == 0);
    CHECK(expect_step(&f, "") == 0);
    CHECK(expect_step(&f, "42\n") == 0);
    CHECK(expect_step(&f, "END\n") == 0);
    CHECK(expect_step(&f, "") == 0);
    CHECK(expect_step(&f, "") == 0);
    f.written = 777u;
    CHECK(bsr_step(&f.runtime, f.output, sizeof(f.output),
                   &f.written).status == BSR_END);
    CHECK(f.runtime.state == BSR_IDLE && f.written == 777u);
    return 0;
}

static int test_step_retry_and_goto(void)
{
    Fixture f;
    BasicSessionRuntime snapshot;
    uint8_t image[sizeof(f.output)];
    size_t written;
    BSRResult result;
    CHECK(init(&f) == 0);
    CHECK(submit(&f, "10 PRINT \"BONJOUR\":REM HIDDEN").status == BSR_OK);
    CHECK(submit(&f, "20 GOTO 40:' : NOT A STATEMENT").status == BSR_OK);
    CHECK(submit(&f, "30 PRINT \"SKIP\"").status == BSR_OK);
    CHECK(submit(&f, "40 PRINT 42").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    snapshot = f.runtime;
    memset(f.output, 0x91, sizeof(f.output));
    memcpy(image, f.output, sizeof(image));
    written = 555u;
    result = bsr_step(&f.runtime, f.output, 3u, &written);
    CHECK(result.status == BSR_EXECUTOR_ERROR &&
          result.executor_status == BE_NO_SPACE);
    CHECK(memcmp(&snapshot, &f.runtime, sizeof(snapshot)) == 0);
    CHECK(memcmp(image, f.output, sizeof(image)) == 0 && written == 555u);
    CHECK(expect_step(&f, "BONJOUR\n") == 0);
    CHECK(expect_step(&f, "") == 0); /* Jump to 40 despite a comment. */
    CHECK(expect_step(&f, "42\n") == 0);
    return 0;
}

static int test_imported_bad_comment(void)
{
    Fixture f;
    static const uint8_t bad[] = {0xc5u, 0u, 'X'};
    uint8_t before[sizeof(f.output)];
    BasicExecutor executor;
    size_t written = 999u;
    CHECK(init(&f) == 0);
    CHECK(bp_put(&f.program, 10u, bad, sizeof(bad)) == BP_OK);
    CHECK(be_init(&executor, &f.program) == BE_OK);
    memset(f.output, 0x63, sizeof(f.output));
    memcpy(before, f.output, sizeof(before));
    CHECK(be_step(&executor, f.output, sizeof(f.output),
                  &written) == BE_BAD_SEQUENCE);
    CHECK(executor.cursor == 0u && written == 999u);
    CHECK(memcmp(before, f.output, sizeof(before)) == 0);
    CHECK(bl_list_program(&f.program, f.output, sizeof(f.output),
                          &written) == BL_BAD_SEQUENCE);
    CHECK(written == 999u && memcmp(before, f.output, sizeof(before)) == 0);
    return 0;
}

int main(void)
{
    CHECK(test_cpc_markers() == 0);
    CHECK(test_roundtrips() == 0);
    CHECK(test_errors_and_atomicity() == 0);
    CHECK(test_session_run_and_list() == 0);
    CHECK(test_step_retry_and_goto() == 0);
    CHECK(test_imported_bad_comment() == 0);
    puts("J0.10 comments: OK");
    return 0;
}
