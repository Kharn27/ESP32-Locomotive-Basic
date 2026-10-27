#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_program.h"
#include "basic_executor.h"
#include "basic_session_runtime.h"
#include "basic_variable_store.h"

#include <stdio.h>
#include <string.h>
#include <stdint.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

/* Synthetic ROM-derived vectors: not captures from an independent CPC. */
static int vector(const char *text, const uint8_t *expected, size_t expected_len)
{
    uint8_t bytes[128], listing[128], again[128];
    size_t n = 999u, printed = 999u, repeated = 999u;
    CHECK(bt_tokenize((const uint8_t *)text, strlen(text),
                      bytes, sizeof(bytes), &n) == BT_OK);
    CHECK(n == expected_len);
    CHECK(memcmp(bytes, expected, n) == 0);
    CHECK(bl_detokenize(bytes, n, listing, sizeof(listing), &printed) == BL_OK);
    CHECK(printed == strlen(text));
    CHECK(memcmp(listing, text, printed) == 0);
    CHECK(bt_tokenize(listing, printed, again, sizeof(again), &repeated) == BT_OK);
    CHECK(repeated == n && memcmp(again, bytes, n) == 0);
    return 0;
}

static int test_vectors(void)
{
    static const uint8_t a0[]   = {2,0,0,0xc1,0xef,0x0e};
    static const uint8_t a9[]   = {2,0,0,0xc1,0xef,0x17};
    static const uint8_t a10[]  = {2,0,0,0xc1,0xef,0x19,10};
    static const uint8_t a255[] = {2,0,0,0xc1,0xef,0x19,255};
    /* Synthetic vector pending independent CPC RAM image verification. */
    static const uint8_t bneg1[] = {2,0,0,0xc2,0xef,0xf5,0x0f};
    static const uint8_t bneg12[] = {2,0,0,0xc2,0xef,0xf5,0x19,12};
    static const uint8_t let[]  = {0xa5,' ',2,0,0,0xc1,0xef,0x10};
    static const uint8_t multi[] = {2,0,0,0xc1,0xef,0x10,1,0x98};
    static const uint8_t spaced[] = {' ',0xa5,' ',2,0,0,0xc1,' ',0xef,' ',0x10,' '};
    static const uint8_t dotted[] = {2,0,0,'A','B','C','.','2'|0x80,0xef,0x19,255};
    static const uint8_t lower[]  = {2,0,0,'a','2'|0x80,' ',0xef,' ',0x19,42};
    CHECK(vector("A%=0", a0, sizeof(a0)) == 0);
    CHECK(vector("A%=9", a9, sizeof(a9)) == 0);
    CHECK(vector("A%=10", a10, sizeof(a10)) == 0);
    CHECK(vector("A%=255", a255, sizeof(a255)) == 0);
    CHECK(vector("B%=-1", bneg1, sizeof(bneg1)) == 0);
    CHECK(vector("B%=-12", bneg12, sizeof(bneg12)) == 0);
    CHECK(vector("LET A%=2", let, sizeof(let)) == 0);
    CHECK(vector("A%=2:END", multi, sizeof(multi)) == 0);
    CHECK(vector(" LET A% = 2 ", spaced, sizeof(spaced)) == 0);
    CHECK(vector("ABC.2%=255", dotted, sizeof(dotted)) == 0);
    CHECK(vector("a2% = 42", lower, sizeof(lower)) == 0);
    return 0;
}

static int test_naming(void)
{
    uint8_t input[56], encoded[80], listed[80];
    size_t n = 0u, m = 0u, i;
    for (i = 0u; i < 40u; ++i) {
        input[i] = (uint8_t)('A' + (int)(i % 26u));
    }
    input[9] = '.';
    input[10] = '3';
    input[40] = '%';
    input[41] = '=';
    input[42] = '7';
    CHECK(bt_tokenize(input, 43u, encoded, sizeof(encoded), &n) == BT_OK);
    CHECK(n == 45u && encoded[0] == 2u && encoded[1] == 0u &&
          encoded[2] == 0u && encoded[42] == (uint8_t)(input[39] | 0x80u) &&
          encoded[43] == 0xefu && encoded[44] == 0x15u);
    CHECK(bl_detokenize(encoded, n, listed, sizeof(listed), &m) == BL_OK);
    CHECK(m == 43u && memcmp(input, listed, 43u) == 0);
    return 0;
}

static int test_rejections(void)
{
    static const char *bad[] = {
        "A%=32768", "A%=B%", "A%=1+2",
        "A%=--1", "A%=-A%", "A%=1-2", "A%=-32768", "A%=65535",
        "A!=1.5", "A$=\"CPC\"", "A=5", "DEFINT A-Z", "A%=",
        "LET A%=", "LET A%=32768", "A%%=2", "A%$=2", "A%1=2",
        "A_%=2", "1A%=2", "%A=2", "A#=2", "A.%%=2",
        "A%=2:","A%=2::END", "A%=2 PRINT 3", "A%==2",
        "LET %=2", "LET 9A%=2", "LET A!=2", "LET A$=2",
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA%=2"
    };
    uint8_t destination[128], original[128];
    size_t i, n;
    memset(destination, 0x7au, sizeof(destination));
    memcpy(original, destination, sizeof(destination));
    for (i = 0u; i < sizeof(bad) / sizeof(bad[0]); ++i) {
        n = 123u;
        CHECK(bt_tokenize((const uint8_t *)bad[i], strlen(bad[i]),
                          destination, sizeof(destination), &n) != BT_OK);
        CHECK(n == 123u && memcmp(destination, original,
                                   sizeof(destination)) == 0);
    }
    return 0;
}

static int test_imported_and_bad_listing(void)
{
    uint8_t imported[] = {0xa5,2,0x34,0x12,0xc1,0xef,0x19,255};
    static const uint8_t too_short_cache[] = {2,0};
    static const uint8_t too_short_name[] = {2,0,0};
    static const uint8_t unterminated[] = {2,0,0,'A',0xef,0x10};
    static const uint8_t no_equal[] = {2,0,0,0xc1,0x10};
    static const uint8_t no_rhs[] = {2,0,0,0xc1,0xef};
    static const uint8_t short_rhs[] = {2,0,0,0xc1,0xef,0x19};
    static const uint8_t bad_rhs[] = {2,0,0,0xc1,0xef,0x19,3};
    static const uint8_t bad_family[] = {0xa5,0x03,0,0,0xc1,0xef,0x10};
    uint8_t output[128], snapshot[128], original[sizeof(imported)], encoded[128];
    size_t n, m, i;
    const struct {
        const uint8_t *data;
        size_t length;
    } invalid[] = {
        {too_short_cache,sizeof(too_short_cache)},
        {too_short_name,sizeof(too_short_name)},
        {unterminated,sizeof(unterminated)},
        {no_equal,sizeof(no_equal)},
        {no_rhs,sizeof(no_rhs)},
        {short_rhs,sizeof(short_rhs)},
        {bad_rhs,sizeof(bad_rhs)},
        {bad_family,sizeof(bad_family)}
    };
    memcpy(original, imported, sizeof(imported));
    memset(output, 0x5cu, sizeof(output));
    n = 999u;
    CHECK(bl_detokenize(imported, sizeof(imported),
                        output, sizeof(output), &n) == BL_OK);
    CHECK(n == strlen("LET A%=255"));
    CHECK(memcmp(output, "LET A%=255", n) == 0);
    CHECK(memcmp(original, imported, sizeof(imported)) == 0);
    CHECK(bt_tokenize(output, n, encoded, sizeof(encoded), &m) == BT_OK);
    CHECK(m == sizeof(imported) + 1u); /* LIST inserted missing LET space. */
    CHECK(encoded[0] == 0xa5u && encoded[1] == ' ' &&
          encoded[3] == 0u && encoded[4] == 0u);
    /* Normalisation du texte != identité binaire avec caches non nuls. */
    for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        memset(output, 0x5cu, sizeof(output));
        memcpy(snapshot, output, sizeof(output));
        n = 999u;
        CHECK(bl_detokenize(invalid[i].data, invalid[i].length,
                            output, sizeof(output), &n) != BL_OK);
        CHECK(n == 999u && memcmp(output, snapshot, sizeof(output)) == 0);
    }
    return 0;
}

static int test_program_imported_caches(void)
{
    /* Cache values are opaque: even 20 (space) and EF (=) MUST NOT be
     * consumed as syntax. The same rule holds for imported programme lines. */
    static const uint8_t implicit[] = {2,0x20,0xef,0xc1,0xef,0x10};
    static const uint8_t explicit_let[] = {0xa5,' ',2,0x20,0x20,0xc2,0xef,0x11};
    static const char *expected = "10 A%=2\n20 LET B%=3\n";
    uint8_t storage[128], image[128], before[128], output[128];
    size_t bytes, listed, saved;
    BasicProgram program;
    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    CHECK(bp_put(&program, 10u, implicit, sizeof(implicit)) == BP_OK);
    CHECK(bp_put(&program, 20u, explicit_let, sizeof(explicit_let)) == BP_OK);
    CHECK(bp_export(&program, before, sizeof(before), &saved) == BP_OK);
    CHECK(bl_list_program(&program, output, sizeof(output), &listed) == BL_OK);
    CHECK(listed == strlen(expected) && memcmp(output, expected, listed) == 0);
    CHECK(bp_export(&program, image, sizeof(image), &bytes) == BP_OK);
    CHECK(bytes == saved && memcmp(image, before, saved) == 0);
    return 0;
}

static int test_capacity(void)
{
    static const char *input = "LET ABC.2% = 255:END";
    uint8_t tokens[96], output[96], snapshot[96];
    size_t n = 177u, printed = 177u;
    CHECK(bt_tokenize((const uint8_t *)input, strlen(input),
                      tokens, 2u, &n) == BT_NO_SPACE);
    CHECK(n == 177u);
    CHECK(bt_tokenize((const uint8_t *)input, strlen(input),
                      tokens, sizeof(tokens), &n) == BT_OK);
    memset(output, 0xbdu, sizeof(output));
    memcpy(snapshot, output, sizeof(output));
    CHECK(bl_detokenize(tokens, n, output, strlen(input) - 1u,
                        &printed) == BL_NO_SPACE);
    CHECK(printed == 177u && memcmp(output, snapshot, sizeof(output)) == 0);
    CHECK(bt_tokenize((const uint8_t *)input, strlen(input),
                      output, 1u, &printed) == BT_NO_SPACE);
    CHECK(printed == 177u && memcmp(output, snapshot, sizeof(output)) == 0);
    return 0;
}

static int test_program_and_run(void)
{
    static const char *lines[] = {
        "A%=2", "LET B%=5", "A% = 10", "PRINT A%", "END"
    };
    static const char *expected =
        "10 A%=2\n20 LET B%=5\n30 A% = 10\n40 PRINT A%\n50 END\n";
    uint8_t storage[1024], body[128], saved[1024], image[1024], listing[1024];
    uint8_t output[256], snapshot[256];
    BasicProgram program;
    BasicExecutor executor;
    BasicVariableStore store;
    BasicVariableEntry entries[2], entries_before[2];
    size_t n, image_length, before_length, listed, i, at = 0u;
    BasicProgramLine line;
    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    for (i = 0u; i < sizeof(lines)/sizeof(lines[0]); ++i) {
        CHECK(bt_tokenize((const uint8_t *)lines[i], strlen(lines[i]),
                          body, sizeof(body), &n) == BT_OK);
        CHECK(bp_put(&program, (uint16_t)((i+1u)*10u), body, n) == BP_OK);
    }
    CHECK(bp_export(&program, saved, sizeof(saved), &before_length) == BP_OK);
    memset(listing, 0x2b, sizeof(listing));
    memset(output, 0x2b, sizeof(output));
    listed = 12345u;
    CHECK(bl_list_program(&program, output, 4u, &listed) == BL_NO_SPACE);
    CHECK(listed == 12345u);
    for (i = 0u; i < sizeof(output); ++i) CHECK(output[i] == 0x2bu);
    CHECK(bl_list_program(&program, listing, sizeof(listing), &listed) == BL_OK);
    CHECK(listed == strlen(expected) && memcmp(listing, expected, listed) == 0);
    CHECK(bp_export(&program, image, sizeof(image), &image_length) == BP_OK);
    CHECK(image_length == before_length &&
          memcmp(saved, image, image_length) == 0);
    for (i = 0u; i < 5u; ++i) {
        size_t end = at, again;
        while (end < listed && listing[end] != '\n') ++end;
        CHECK(end < listed && end >= at + 3u);
        CHECK(bt_tokenize(listing + at + 3u, end - at - 3u,
                          body, sizeof(body), &again) == BT_OK);
        CHECK(bp_find(&program, (uint16_t)((i+1u)*10u), &line) == BP_OK);
        CHECK(again == line.body_length &&
              memcmp(body, program.data + line.body_offset, again) == 0);
        at = end + 1u;
    }
    CHECK(at == listed);
    memset(entries, 0xa8, sizeof(entries));
    CHECK(bvs_init(&store, entries, 2u) == BVS_OK);
    CHECK(store.count == 0u);
    memcpy(entries_before, entries, sizeof(entries));
    CHECK(be_init(&executor, &program) == BE_OK);
    memset(output, 0x35, sizeof(output));
    memcpy(snapshot, output, sizeof(output));
    n = 987u;
    CHECK(be_step(&executor, output, sizeof(output), &n) == BE_UNSUPPORTED);
    CHECK(executor.cursor == 0u && n == 987u &&
          memcmp(output, snapshot, sizeof(output)) == 0);
    CHECK(store.count == 0u &&
          memcmp(entries_before, entries, sizeof(entries)) == 0);
    CHECK(bp_export(&program, image, sizeof(image), &image_length) == BP_OK);
    CHECK(image_length == before_length &&
          memcmp(saved, image, image_length) == 0);
    /* Import/export exact, without detokenisation or cache rewriting. */
    {
        uint8_t restored[1024];
        BasicProgram clone;
        size_t copied;
        CHECK(bp_init(&clone, restored, sizeof(restored)) == BP_OK);
        CHECK(bp_import(&clone, saved, before_length) == BP_OK);
        CHECK(bp_export(&clone, image, sizeof(image), &copied) == BP_OK);
        CHECK(copied == before_length &&
              memcmp(saved, image, before_length) == 0);
    }
    return 0;
}

static int test_run_no_partial_print(void)
{
    static const char *line = "PRINT \"INTERDIT\":A%=2";
    uint8_t storage[128], body[128], output[128], before[128];
    BasicProgram program;
    BasicExecutor executor;
    size_t n, written = 77u;
    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    CHECK(bt_tokenize((const uint8_t *)line, strlen(line),
                      body, sizeof(body), &n) == BT_OK);
    CHECK(bp_put(&program, 10u, body, n) == BP_OK);
    CHECK(be_init(&executor, &program) == BE_OK);
    memset(output, 0x7au, sizeof(output));
    memcpy(before, output, sizeof(before));
    CHECK(be_step(&executor, output, sizeof(output), &written) == BE_UNSUPPORTED);
    CHECK(written == 77u && executor.cursor == 0u &&
          memcmp(before, output, sizeof(before)) == 0);
    return 0;
}


/* J1.1: CPC unary token and literal must remain a single bounded construct. */
static int test_signed_literal_capacity(void)
{
    static const char source[] = "B%=-12";
    static const uint8_t expected[] = {2u,0u,0u,0xc2u,0xefu,0xf5u,0x19u,12u};
    static const uint8_t truncated[] = {2u,0u,0u,0xc2u,0xefu,0xf5u};
    static const uint8_t bad_operand[] = {2u,0u,0u,0xc2u,0xefu,0xf5u,0x02u};
    uint8_t encoded[8], output[24];
    size_t written = 77u;
    memset(encoded, 0xa9, sizeof(encoded));
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source), encoded,
                      sizeof(encoded) - 1u, &written) == BT_NO_SPACE);
    CHECK(written == 77u);
    for (size_t i = 0u; i < sizeof(encoded); ++i) {
        CHECK(encoded[i] == 0xa9u);
    }
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source), encoded,
                      sizeof(encoded), &written) == BT_OK);
    CHECK(written == sizeof(expected) &&
          memcmp(encoded, expected, sizeof(expected)) == 0);
    memset(output, 0xb7, sizeof(output));
    written = 77u;
    CHECK(bl_detokenize(encoded, sizeof(encoded), output, strlen(source) - 1u,
                        &written) == BL_NO_SPACE);
    CHECK(written == 77u);
    for (size_t i = 0u; i < sizeof(output); ++i) {
        CHECK(output[i] == 0xb7u);
    }
    CHECK(bl_detokenize(encoded, sizeof(encoded), output, strlen(source),
                        &written) == BL_OK);
    CHECK(written == strlen(source) &&
          memcmp(output, source, written) == 0);
    written = 77u;
    CHECK(bl_detokenize(truncated, sizeof(truncated), output, sizeof(output),
                        &written) == BL_TRUNCATED);
    CHECK(bl_detokenize(bad_operand, sizeof(bad_operand), output, sizeof(output),
                        &written) == BL_BAD_SEQUENCE);
    return 0;
}

int main(void)
{
    CHECK(test_vectors() == 0);
    CHECK(test_signed_literal_capacity() == 0);
    CHECK(test_naming() == 0);
    CHECK(test_rejections() == 0);
    CHECK(test_imported_and_bad_listing() == 0);
    CHECK(test_program_imported_caches() == 0);
    CHECK(test_capacity() == 0);
    CHECK(test_program_and_run() == 0);
    CHECK(test_run_no_partial_print() == 0);
    puts("J0.18 INTEGER assignment tokens: OK (synthetic vectors)");
    return 0;
}
