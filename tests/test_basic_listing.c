#include "basic_listing.h"
#include "basic_tokenizer.h"

#include <stdio.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); \
    return 1; } } while (0)

static int expect_decode(const uint8_t *body, size_t body_len,
                         const uint8_t *expected, size_t expected_len)
{
    uint8_t out[256];
    size_t written = SIZE_MAX;
    memset(out, 0xa5, sizeof(out));
    CHECK(bl_detokenize(body, body_len, out, sizeof(out), &written) == BL_OK);
    CHECK(written == expected_len);
    CHECK(memcmp(out, expected, expected_len) == 0);
    CHECK(out[expected_len] == 0xa5u); /* No NUL appended */
    return 0;
}

static int test_keywords_and_numbers(void)
{
    static const struct {uint8_t code; const char *word;} words[] = {
        {0xbfu, "PRINT"}, {0xa7u, "LIST"}, {0xcau, "RUN"},
        {0xb1u, "NEW"}, {0xa0u, "GOTO"}
    };
    size_t i;
    for (i = 0; i < sizeof(words)/sizeof(words[0]); ++i) {
        const uint8_t token[] = {words[i].code};
        if (words[i].code == 0xa0u) {
            /* A bare GOTO is not a representable J0.4 statement. */
            uint8_t out[32];
            size_t written = 17u;
            CHECK(bl_detokenize(token, 1u, out, sizeof(out), &written) == BL_BAD_SEQUENCE);
            CHECK(written == 17u);
        } else {
            CHECK(expect_decode(token, sizeof(token), (const uint8_t *)words[i].word,
                                strlen(words[i].word)) == 0);
        }
    }
    {
        static const struct {uint8_t token[3]; size_t n; const char *text;} cases[] = {
            {{0xbfu, 0x0eu, 0u}, 2u, "PRINT 0"},
            {{0xbfu, 0x17u, 0u}, 2u, "PRINT 9"},
            {{0xbfu, 0x19u, 10u}, 3u, "PRINT 10"},
            {{0xbfu, 0x19u, 11u}, 3u, "PRINT 11"},
            {{0xbfu, 0x19u, 255u}, 3u, "PRINT 255"}
        };
        for (i = 0; i < sizeof(cases)/sizeof(cases[0]); ++i) {
            uint8_t raw[4];
            raw[0] = cases[i].token[0]; raw[1] = (uint8_t)' ';
            memcpy(raw + 2, cases[i].token + 1, cases[i].n - 1u);
            CHECK(expect_decode(raw, cases[i].n + 1u,
                                (const uint8_t *)cases[i].text, strlen(cases[i].text)) == 0);
        }
    }
    {
        static const struct {uint16_t line; const char *text;} refs[] = {
            {1u, "GOTO 1"}, {20u, "GOTO 20"},
            {256u, "GOTO 256"}, {65535u, "GOTO 65535"}
        };
        for (i = 0; i < sizeof(refs)/sizeof(refs[0]); ++i) {
            uint8_t raw[] = {0xa0u, ' ', 0x1eu,
                             (uint8_t)(refs[i].line & 0xffu),
                             (uint8_t)(refs[i].line >> 8)};
            CHECK(expect_decode(raw, sizeof(raw),
                                (const uint8_t *)refs[i].text, strlen(refs[i].text)) == 0);
        }
    }
    return 0;
}

static int test_spaces_and_strings(void)
{
    static const uint8_t spaces[] = {' ', ' ', 0xbfu, ' ', ' ', 0x12u, ' ', ' ',
                                     0x01u, ' ', 0xcau, ' ', ' '};
    static const uint8_t spaces_expected[] = "  PRINT  4  : RUN  ";
    static const uint8_t quoted[] = {0xbfu, ' ', '"', ':', 0xa7u, ' ',
                                     'G', 'O', 'T', 'O', ' ', 0x01u, '"'};
    static const uint8_t quoted_expected[] = {'P','R','I','N','T',' ', '"', ':',
                0xa7u, ' ', 'G','O','T','O',' ', 0x01u,'"'};
    static const uint8_t open[] = {0xbfu, ' ', '"', 'H', 'I'};
    static const uint8_t open_expected[] = "PRINT \"HI";
    static const uint8_t eightbit[] = {0xbfu, '"', 0x80u, 0xfeu, '"'};
    static const uint8_t eightbit_expected[] = {'P','R','I','N','T','"',0x80u,0xfeu,'"'};
    static const uint8_t only_spaces[] = {' ', ' ', ' '};
    static const uint8_t multi[] = {0xbfu, ' ', '"', ':', '"', 0x01u,
                                    ' ', 0xb1u, 0x01u, 0xa7u};
    static const uint8_t multi_expected[] = "PRINT \":\": NEW:LIST";
    CHECK(expect_decode(spaces, sizeof(spaces), spaces_expected,
                        sizeof(spaces_expected)-1u) == 0);
    CHECK(expect_decode(quoted, sizeof(quoted), quoted_expected,
                        sizeof(quoted_expected)) == 0);
    CHECK(expect_decode(open, sizeof(open), open_expected,
                        sizeof(open_expected)-1u) == 0);
    CHECK(expect_decode(eightbit, sizeof(eightbit), eightbit_expected,
                        sizeof(eightbit_expected)) == 0);
    CHECK(expect_decode(only_spaces, sizeof(only_spaces), only_spaces,
                        sizeof(only_spaces)) == 0);
    CHECK(expect_decode(multi, sizeof(multi), multi_expected,
                        sizeof(multi_expected)-1u) == 0);
    CHECK(expect_decode((const uint8_t *)"", 0u, (const uint8_t *)"", 0u) == 0);
    return 0;
}

static int test_decode_failures(void)
{
    static const struct {uint8_t raw[8]; size_t n; BLStatus status;} cases[] = {
        {{0xffu}, 1u, BL_UNKNOWN_TOKEN},
        {{0x18u}, 1u, BL_UNKNOWN_TOKEN},
        {{0x1eu}, 1u, BL_UNKNOWN_TOKEN},
        {{0xbfu, ' ', 0x19u}, 3u, BL_TRUNCATED},
        {{0xa0u, ' ', 0x1eu, 1u}, 4u, BL_TRUNCATED},
        {{0xa0u, ' ', 0x1eu, 0u, 0u}, 5u, BL_BAD_SEQUENCE},
        {{0xa0u, 0x1eu, 1u, 0u}, 4u, BL_BAD_SEQUENCE},
        {{0xbfu, 0x0eu}, 2u, BL_BAD_SEQUENCE},
        {{0xbfu, ' ', 0x19u, 5u}, 4u, BL_BAD_SEQUENCE},
        {{0xbfu, ' ', 0u}, 3u, BL_BAD_SEQUENCE},
        {{0xbfu, ' ', '"', 0u}, 4u, BL_BAD_SEQUENCE},
        {{0xbfu, ' ', '"', '\r'}, 4u, BL_BAD_SEQUENCE},
        {{0xbfu, ' ', '"', '\n'}, 4u, BL_BAD_SEQUENCE},
        {{0xbfu, 0x01u}, 2u, BL_BAD_SEQUENCE},
        {{0x01u, 0xbfu}, 2u, BL_BAD_SEQUENCE},
        {{0xbfu, 0x01u, 0x01u, 0xbfu}, 4u, BL_BAD_SEQUENCE},
        {{0xcau, 0x01u, ' '}, 3u, BL_BAD_SEQUENCE},
        {{0xcau, 'X'}, 2u, BL_BAD_SEQUENCE},
        {{0xcau, 0x0eu}, 2u, BL_UNKNOWN_TOKEN}
    };
    size_t i;
    for (i = 0; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        uint8_t dest[32], snapshot[32];
        size_t written = 12345u;
        memset(dest, 0xa3, sizeof(dest)); memcpy(snapshot, dest, sizeof(dest));
        CHECK(bl_detokenize(cases[i].raw, cases[i].n,
                            dest, sizeof(dest), &written) == cases[i].status);
        CHECK(written == 12345u && memcmp(dest, snapshot, sizeof(dest)) == 0);
    }
    return 0;
}

static int test_buffers_and_aliasing(void)
{
    static const uint8_t raw[] = {0xbfu, ' ', 0x19u, 255u};
    uint8_t dest[32];
    size_t written = 900u;
    memset(dest, 0x71, sizeof(dest));
    CHECK(bl_detokenize(raw, sizeof(raw), dest, 8u, &written) == BL_NO_SPACE);
    CHECK(written == 900u && dest[0] == 0x71u && dest[31] == 0x71u);
    CHECK(bl_detokenize(raw, sizeof(raw), dest, 9u, &written) == BL_OK);
    CHECK(written == 9u && memcmp(dest, "PRINT 255", 9u) == 0);
    CHECK(dest[9] == 0x71u);
    CHECK(bl_detokenize(dest, written, dest, sizeof(dest), &written) == BL_OVERLAP);
    CHECK(bl_detokenize(raw, sizeof(raw), dest, sizeof(dest),
                        (size_t *)(void *)dest) == BL_OVERLAP);
    CHECK(bl_detokenize(raw, sizeof(raw), dest, sizeof(dest), NULL) == BL_INVALID_ARGUMENT);
    CHECK(bl_detokenize(NULL, 0u, dest, sizeof(dest), &written) == BL_INVALID_ARGUMENT);
    CHECK(bl_detokenize(raw, sizeof(raw), NULL, 0u, &written) == BL_INVALID_ARGUMENT);
    CHECK(bl_detokenize(raw, sizeof(raw), dest, sizeof(dest),
                        (size_t *)(void *)raw) == BL_OVERLAP);
    return 0;
}

static int check_round_trip(const uint8_t *source, size_t len)
{
    uint8_t body1[512], body2[512], text[512];
    size_t n1 = 0, n2 = 0, nt = 0;
    CHECK(bt_tokenize(source, len, body1, sizeof(body1), &n1) == BT_OK);
    CHECK(bl_detokenize(body1, n1, text, sizeof(text), &nt) == BL_OK);
    CHECK(bt_tokenize(text, nt, body2, sizeof(body2), &n2) == BT_OK);
    CHECK(n1 == n2 && memcmp(body1, body2, n1) == 0);
    return 0;
}

static int test_round_trip(void)
{
    static const char *sources[] = {
        "", "   ", "LIST", "RUN", "NEW", "PRINT", "?", "print \"HELLO\"",
        "? 0010", "PRINT 0", "PRINT 9", "PRINT 10", "PRINT 11",
        "PRINT 255", "GOTO 00001", "GOTO 20", "GOTO 256",
        "GOTO 65535", "  PRINT   011  ", "PRINT \"HELLO:RUN\"",
        "PRINT \"HI", "RUN:PRINT 5: GOTO 100", "  NEW  : PRINT \"?\" "
    };
    static const uint8_t nonascii[] = {'?', ' ', '"', 0x80u, 0xffu, '"'};
    size_t i;
    for (i = 0; i < sizeof(sources)/sizeof(sources[0]); ++i) {
        CHECK(check_round_trip((const uint8_t *)sources[i], strlen(sources[i])) == 0);
    }
    CHECK(check_round_trip(nonascii, sizeof(nonascii)) == 0);
    return 0;
}

static int test_listing(void)
{
    uint8_t storage[2048], dest[2048], raw[256];
    size_t n, written;
    BasicProgram program;
    static const char *inputs[] = {"PRINT \"HI\"", "GOTO 20", "RUN", ""};
    static const uint16_t numbers[] = {30u, 10u, 65535u, 20u};
    static const char expected[] =
            "10 GOTO 20\n20 \n30 PRINT \"HI\"\n65535 RUN\n";
    size_t i;
    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    memset(dest, 0xcc, sizeof(dest));
    written = 123u;
    CHECK(bl_list_program(&program, dest, sizeof(dest), &written) == BL_OK);
    CHECK(written == 0u && dest[0] == 0xccu);
    for (i = 0; i < sizeof(inputs)/sizeof(inputs[0]); ++i) {
        CHECK(bt_tokenize((const uint8_t *)inputs[i], strlen(inputs[i]),
                          raw, sizeof(raw), &n) == BT_OK);
        CHECK(bp_put(&program, numbers[i], raw, n) == BP_OK);
    }
    written = 0u;
    CHECK(bl_list_program(&program, dest, sizeof(dest), &written) == BL_OK);
    CHECK(written == sizeof(expected)-1u);
    CHECK(memcmp(dest, expected, written) == 0);
    CHECK(dest[written] == 0xccu);
    {
        uint8_t backup[2048];
        size_t stale = 777u;
        memcpy(backup, dest, sizeof(dest));
        CHECK(bl_list_program(&program, dest, written - 1u, &stale) == BL_NO_SPACE);
        CHECK(stale == 777u && memcmp(dest, backup, sizeof(dest)) == 0);
        CHECK(bl_list_program(&program, dest, written, &stale) == BL_OK);
        CHECK(stale == written && memcmp(dest, expected, written) == 0);
        CHECK(bl_list_program(&program, storage, sizeof(storage), &stale) == BL_OVERLAP);
        CHECK(bl_list_program(&program, dest, sizeof(dest),
                              (size_t *)(void *)storage) == BL_OVERLAP);
        CHECK(bl_list_program(&program, dest, sizeof(dest),
                              (size_t *)(void *)dest) == BL_OVERLAP);
    }
    /* A tokenized record can be structurally valid but semantically invalid. */
    {
        static const uint8_t bad[] = {0xbfu, ' ', 0x19u};
        uint8_t out[64];
        size_t stale = 111u;
        CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
        CHECK(bp_put(&program, 50u, bad, sizeof(bad)) == BP_OK);
        memset(out, 0x77, sizeof(out));
        CHECK(bl_list_program(&program, out, sizeof(out), &stale) == BL_TRUNCATED);
        CHECK(stale == 111u && out[0] == 0x77u && out[63] == 0x77u);
    }
    return 0;
}

static int test_bad_images(void)
{
    uint8_t storage[128], output[128];
    BasicProgram program;
    size_t written = 100u;
    static const uint8_t malformed[][9] = {
        {1u, 0u, 10u, 0u, 0u, 0u, 0u, 0u, 0u},
        {5u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u},
        {6u, 0u, 10u, 0u, 0xcau, 0x99u, 0u, 0u, 0u}
    };
    size_t i;
    memset(output, 0x55, sizeof(output));
    for (i = 0; i < sizeof(malformed)/sizeof(malformed[0]); ++i) {
        program.data = (uint8_t *)(void *)malformed[i];
        program.capacity = sizeof(malformed[i]);
        program.size = sizeof(malformed[i]);
        CHECK(bl_list_program(&program, output, sizeof(output), &written) == BL_BAD_PROGRAM);
        CHECK(written == 100u && output[0] == 0x55u);
    }
    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    program.size = program.capacity + 1u;
    CHECK(bl_list_program(&program, output, sizeof(output), &written) == BL_BAD_PROGRAM);
    CHECK(written == 100u && output[0] == 0x55u);
    CHECK(bl_list_program(NULL, output, sizeof(output), &written) == BL_INVALID_ARGUMENT);
    CHECK(bl_list_program(&program, NULL, 0u, &written) == BL_INVALID_ARGUMENT);
    CHECK(bl_list_program(&program, output, sizeof(output), NULL) == BL_INVALID_ARGUMENT);
    return 0;
}

int main(void)
{
    CHECK(test_keywords_and_numbers() == 0);
    CHECK(test_spaces_and_strings() == 0);
    CHECK(test_decode_failures() == 0);
    CHECK(test_buffers_and_aliasing() == 0);
    CHECK(test_round_trip() == 0);
    CHECK(test_listing() == 0);
    CHECK(test_bad_images() == 0);
    puts("basic_listing: OK");
    return 0;
}
