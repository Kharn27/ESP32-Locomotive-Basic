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
    /* J0.16-C1: valid '?' aliases have no mandatory operand space.
     * LIST expands the mnemonic to PRINT and writes a textual separator. */
    {
        static const uint8_t short_alias[] = {0xbfu, 0x0eu};
        static const uint8_t long_alias[] = {0xbfu, 0x19u, 42u};
        CHECK(expect_decode(short_alias, sizeof(short_alias),
                            (const uint8_t *)"PRINT 0", 7u) == 0);
        CHECK(expect_decode(long_alias, sizeof(long_alias),
                            (const uint8_t *)"PRINT 42", 8u) == 0);
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


/* J1.19-B1: load the *existing* J1.19-A original and repeat capture.json,
 * not an invented CPC dump. Test lives in the existing basic_listing CTest,
 * leaving the root CMake file untouched while HW4-RUN-BREAK-B owns it. */
static int paper_hex_digit(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

static int paper_hex_field(const char *line, const char *key,
                           uint8_t *data, size_t capacity, size_t *length)
{
    const char *p = strstr(line, key);
    size_t n = 0u;
    if (p == NULL) return 0;
    p += strlen(key);
    while (*p != '\0' && *p != '"') {
        int high, low;
        if (*p == ' ') { ++p; continue; }
        if (p[1] == '\0' || p[1] == '"' || n == capacity)
            return -1;
        high = paper_hex_digit(p[0]);
        low = paper_hex_digit(p[1]);
        if (high < 0 || low < 0) return -1;
        data[n++] = (uint8_t)((high << 4) | low);
        p += 2;
    }
    if (*p != '"' || n == 0u) return -1;
    *length = n;
    return 1;
}

static int paper_capture(const char *session, const char *name,
                         uint8_t *record, size_t *record_len,
                         uint8_t *printer, size_t *printer_len)
{
    char path[1024], line[4096];
    const char *marker = strstr(__FILE__, "tests/test_basic_listing.c");
    FILE *f;
    int got_record = 0, got_printer = 0;
    if (marker != NULL) {
        size_t prefix = (size_t)(marker - __FILE__);
        if (prefix > 900u) return 1;
        if (snprintf(path, sizeof(path),
                     "%.*stests/fixtures/cpc6128/j1_19_a_paper/%s/%s/capture.json",
                     (int)prefix, __FILE__, session, name) < 0) return 1;
    } else {
        if (snprintf(path, sizeof(path),
                     "../tests/fixtures/cpc6128/j1_19_a_paper/%s/%s/capture.json",
                     session, name) < 0) return 1;
    }
    f = fopen(path, "rb");
    if (f == NULL) {
        fprintf(stderr, "J1.19-B1 fixture absent: %s\n", path);
        return 1; /* no skip or substitute oracle */
    }
    while (fgets(line, sizeof(line), f) != NULL) {
        int rc = paper_hex_field(line, "\"20\": \"", record, 16u, record_len);
        int pc = paper_hex_field(line, "\"list_printer_hex\": \"",
                                 printer, 1024u, printer_len);
        if (rc < 0 || pc < 0) { fclose(f); return 1; }
        if (rc == 1) ++got_record;
        if (pc == 1) ++got_printer;
    }
    if (ferror(f)) { fclose(f); return 1; }
    fclose(f);
    return got_record == 1 && got_printer == 1 ? 0 : 1;
}

static int test_paper_b1_oracle(void)
{
    static const struct {
        const char *case_id;
        const char *value;
        uint8_t encoded[2];
        size_t encoded_length;
    } samples[] = {
        {"P00", "0",  {0x0eu},         1u},
        {"P01", "1",  {0x0fu},         1u},
        {"P02", "2",  {0x10u},         1u},
        {"P03", "3",  {0x11u},         1u},
        {"P04", "4",  {0x12u},         1u},
        {"P15", "15", {0x19u, 0x0fu}, 2u},
        {"P16", "16", {0x19u, 0x10u}, 2u},
        {"PN1", "-1", {0xf5u, 0x0fu}, 2u}
    };
    static const char *const sessions[] = {"original", "repeat"};
    size_t i, session;
    for (i = 0u; i < sizeof(samples)/sizeof(samples[0]); ++i) {
        char source[32], expected_list[40], expected_printer[40];
        uint8_t body[16], roundtrip[16], output[64], exported[64];
        uint8_t storage[64], record[16], printer[1024], listed[64];
        size_t body_len = 99u, round_len = 0u, out_len = 0u, exported_len = 0u;
        size_t n, record_len, printer_len, j, expected_n;
        BasicProgram program;
        CHECK(snprintf(source, sizeof(source), "PAPER %s", samples[i].value) > 0);
        CHECK(snprintf(expected_list, sizeof(expected_list),
                       "20 PAPER %s\n", samples[i].value) > 0);
        CHECK(snprintf(expected_printer, sizeof(expected_printer),
                       "20 PAPER %s\r\n", samples[i].value) > 0);
        CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                          body, sizeof(body), &body_len) == BT_OK);
        CHECK(body_len == 2u + samples[i].encoded_length);
        CHECK(body[0] == 0xbau && body[1] == (uint8_t)' ');
        CHECK(memcmp(body + 2u, samples[i].encoded,
                     samples[i].encoded_length) == 0);
        CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
        CHECK(bp_put(&program, 20u, body, body_len) == BP_OK);
        CHECK(bp_export(&program, exported, sizeof(exported), &exported_len) == BP_OK);
        CHECK(bl_list_program(&program, listed, sizeof(listed), &out_len) == BL_OK);
        CHECK(out_len == strlen(expected_list));
        CHECK(memcmp(listed, expected_list, out_len) == 0);
        CHECK(bl_detokenize(body, body_len, output, sizeof(output), &n) == BL_OK);
        CHECK(n == strlen(source) && memcmp(output, source, n) == 0);
        CHECK(bt_tokenize(listed + 3u, out_len - 4u, roundtrip,
                          sizeof(roundtrip), &round_len) == BT_OK);
        CHECK(round_len == body_len && memcmp(roundtrip, body, body_len) == 0);
        for (session = 0u; session < 2u; ++session) {
            int saw_listing = 0;
            CHECK(paper_capture(sessions[session], samples[i].case_id,
                                record, &record_len, printer, &printer_len) == 0);
            CHECK(record_len == body_len + 5u);
            CHECK(record[0] == (uint8_t)record_len && record[1] == 0u);
            CHECK(record[2] == 20u && record[3] == 0u);
            CHECK(record[record_len - 1u] == 0u);
            CHECK(exported_len == record_len + 2u);
            CHECK(memcmp(record, exported, record_len) == 0);
            CHECK(exported[record_len] == 0u && exported[record_len+1u] == 0u);
            expected_n = strlen(expected_printer);
            for (j = 0u; j + expected_n <= printer_len; ++j) {
                if ((j == 0u || printer[j-1u] == (uint8_t)'\n') &&
                    memcmp(printer + j, expected_printer, expected_n) == 0)
                    saw_listing = 1;
            }
            CHECK(saw_listing);
        }
    }
    return 0;
}

static int test_paper_b1_rejections(void)
{
    static const struct {
        uint8_t body[5];
        size_t length;
        BLStatus expected;
    } cases[] = {
        {{0xbau, ' ', 0x19u},          3u, BL_TRUNCATED},
        {{0xbau, ' ', 0xf5u},          3u, BL_TRUNCATED},
        {{0xbau, ' ', 0x88u},          3u, BL_UNKNOWN_TOKEN},
        {{0xbau, ' ', 0x13u},          3u, BL_BAD_SEQUENCE},
        {{0xbau, ' ', 0x19u, 0x11u},   4u, BL_BAD_SEQUENCE},
        {{0xbau, ' ', 0x19u, 0x09u},   4u, BL_BAD_SEQUENCE},
        {{0xbau, ' ', 0xf5u, 0x10u},   4u, BL_BAD_SEQUENCE},
        {{0xbau},                      1u, BL_BAD_SEQUENCE}
    };
    uint8_t out[64], original[64], storage[8], body[] = {0xbau,' ',0x19u,0x10u};
    BasicProgram small;
    size_t n = 222u, i;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        memset(out, 0x57, sizeof(out));
        memcpy(original, out, sizeof(out));
        CHECK(bl_detokenize(cases[i].body, cases[i].length,
                            out, sizeof(out), &n) == cases[i].expected);
        CHECK(n == 222u && memcmp(out, original, sizeof(out)) == 0);
    }
    CHECK(bl_detokenize(body, sizeof(body), out, 7u, &n) == BL_NO_SPACE);
    CHECK(n == 222u && memcmp(out, original, sizeof(out)) == 0);
    CHECK(bp_init(&small, storage, sizeof(storage)) == BP_OK);
    memcpy(original, storage, sizeof(storage));
    CHECK(bp_put(&small, 20u, body, sizeof(body)) == BP_NO_SPACE);
    CHECK(small.size == 2u && memcmp(storage, original, sizeof(storage)) == 0);
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
    CHECK(test_paper_b1_oracle() == 0);
    CHECK(test_paper_b1_rejections() == 0);
    puts("basic_listing: OK");
    return 0;
}
