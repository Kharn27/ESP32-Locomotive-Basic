#include "basic_tokenizer.h"
#include "basic_program.h"

#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: failed: %s\n", __FILE__, __LINE__, #x); \
    return 1; \
} } while (0)

#define VECTOR(name, ...) static const uint8_t name[] = {__VA_ARGS__}

VECTOR(hello, 0xbf,0x20,0x22,'H','E','L','L','O',0x22);
VECTOR(five, 0xbf,0x20,0x13);
VECTOR(ten, 0xbf,0x20,0x19,0x0a);
VECTOR(literal_keyword, 0xbf,0x20,0x22,'G','O','T','O',' ','1','0','0',0x22);
VECTOR(unclosed, 0xbf,0x20,0x22,'H','I');
VECTOR(go20, 0xa0,0x20,0x1e,0x14,0x00);
VECTOR(multi, 0xbf,0x20,0x13,0x01,0xbf,0x20,0x22,'A',0x22);
VECTOR(spaces, 0x20,0x20,0xbf,0x20,0x20,0x13,0x20,0x20,
               0x01,0x20,0x20,0xb1,0x20);
VECTOR(colon_in_string, 0xbf,0x22,'A',':','B',0x22);
VECTOR(literal_bytes, 0xbf,0x20,0x22,0x80,0xff,0x22);
VECTOR(empty_string, 0xbf,0x20,0x22,0x22);
VECTOR(zero, 0xbf,0x20,0x0e);
VECTOR(nine, 0xbf,0x20,0x17);
VECTOR(eleven, 0xbf,0x20,0x19,0x0b);
VECTOR(max_byte, 0xbf,0x20,0x19,0xff);
VECTOR(go1, 0xa0,0x20,0x1e,0x01,0x00);
VECTOR(go256, 0xa0,0x20,0x1e,0x00,0x01);
VECTOR(go65535, 0xa0,0x20,0x1e,0xff,0xff);
VECTOR(print_only, 0xbf);
VECTOR(print_plus_new, 0xbf,0x01,0xb1);
VECTOR(single_list, 0xa7);
VECTOR(single_run, 0xca);
VECTOR(single_new, 0xb1);
VECTOR(whitespace, 0x20,0x20,0x20);

static int expect_bytes(const uint8_t *source, size_t source_length,
                        const uint8_t *expected, size_t expected_length)
{
    uint8_t out[128];
    size_t written = 900;
    size_t i;
    memset(out, 0xa5, sizeof(out));
    CHECK(bt_tokenize(source, source_length, out, sizeof(out), &written) == BT_OK);
    CHECK(written == expected_length);
    CHECK(memcmp(out, expected, expected_length) == 0);
    for (i = expected_length; i < sizeof(out); ++i) {
        CHECK(out[i] == 0xa5);
    }
    return 0;
}

#define TEXT(src, bytes) \
    CHECK(expect_bytes((const uint8_t *)(src), sizeof(src) - 1u, \
                       (bytes), sizeof(bytes)) == 0)

static int test_vectors(void)
{
    static const uint8_t raw[] = {'P','R','I','N','T',' ','"',0x80,0xff,'"'};
    static const uint8_t blank[] = {0};
    TEXT("PRINT \"HELLO\"", hello);
    TEXT("PRINT 5", five);
    TEXT("PRINT 10", ten);
    TEXT("PRINT \"GOTO 100\"", literal_keyword);
    TEXT("PRINT \"HI", unclosed);
    TEXT("GOTO 20", go20);
    TEXT("PRINT 5:PRINT \"A\"", multi);
    TEXT("  print  5  :  new ", spaces);
    TEXT("PRINT\"A:B\"", colon_in_string);
    CHECK(expect_bytes(raw, sizeof(raw), literal_bytes,
                       sizeof(literal_bytes)) == 0);
    TEXT("PRINT \"\"", empty_string);
    TEXT("PRINT 0", zero);
    TEXT("PRINT 9", nine);
    TEXT("PRINT 11", eleven);
    TEXT("PRINT 255", max_byte);
    TEXT("GOTO 1", go1);
    TEXT("GOTO 256", go256);
    TEXT("GOTO 65535", go65535);
    TEXT("PRINT", print_only);
    TEXT("PRINT:NEW", print_plus_new);
    TEXT("LIST", single_list);
    TEXT("RUN", single_run);
    TEXT("NEW", single_new);
    TEXT("list", single_list);
    TEXT("rUn", single_run);
    TEXT("nEw", single_new);
    TEXT("GoTo 20", go20);
    TEXT("pRiNt 5", five);
    TEXT("? 5", five);
    TEXT("?", print_only);
    TEXT("   ", whitespace);
    CHECK(expect_bytes(blank, 0, blank, 0) == 0);
    return 0;
}

static int expect_reject(const uint8_t *source, size_t length, BTStatus expected)
{
    uint8_t out[96], snapshot[96];
    size_t written = 0x1234u;
    memset(out, 0xa5, sizeof(out));
    memcpy(snapshot, out, sizeof(out));
    CHECK(bt_tokenize(source, length, out, sizeof(out), &written) == expected);
    CHECK(written == 0x1234u);
    CHECK(memcmp(snapshot, out, sizeof(out)) == 0);
    return 0;
}

#define REJECT(src, code) \
    CHECK(expect_reject((const uint8_t *)(src), sizeof(src) - 1u, code) == 0)

static int test_rejections(void)
{
    static const uint8_t nul[] = {'P','R','I','N','T',0,'5'};
    static const uint8_t cr[] = {'P','R','I','N','T',' ','"', '\r'};
    static const uint8_t lf[] = {'P','R','I','N','T',' ','"', '\n'};
    static const uint8_t control[] = {'P','R','I','N','T',' ',0x09,'5'};
    REJECT("PRINTX", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("SPRINT", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT1", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT.", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT_TEST", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("GOTO20", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT 5ABC", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT 5.0", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT 1+2", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT A", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT GOTO 20", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT \"A\"X", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT \"A\"\"B\"", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("FOR I=1 TO 3", BT_UNSUPPORTED_CONSTRUCT);
    /* GOSUB 20 is now covered by the J1.11-B positive encoding suite. */
    REJECT("LIST 10", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("RUN 20", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("PRINT -1", BT_UNSUPPORTED_CONSTRUCT);
    REJECT("GOTO -1", BT_MALFORMED_INPUT);
    REJECT("PRINT 256", BT_NUMBER_OUT_OF_RANGE);
    REJECT("PRINT 9999999999999999999999999", BT_NUMBER_OUT_OF_RANGE);
    REJECT("GOTO 65536", BT_NUMBER_OUT_OF_RANGE);
    REJECT("GOTO 999999999999999999999999", BT_NUMBER_OUT_OF_RANGE);
    REJECT("GOTO 0", BT_MALFORMED_INPUT);
    REJECT("GOTO", BT_MALFORMED_INPUT);
    REJECT("GOTO  ", BT_MALFORMED_INPUT);
    REJECT(":PRINT 5", BT_MALFORMED_INPUT);
    REJECT("PRINT 5:", BT_MALFORMED_INPUT);
    REJECT("PRINT 5:  ", BT_MALFORMED_INPUT);
    REJECT("PRINT 5::NEW", BT_MALFORMED_INPUT);
    CHECK(expect_reject(nul, sizeof(nul), BT_MALFORMED_INPUT) == 0);
    CHECK(expect_reject(cr, sizeof(cr), BT_MALFORMED_INPUT) == 0);
    CHECK(expect_reject(lf, sizeof(lf), BT_MALFORMED_INPUT) == 0);
    CHECK(expect_reject(control, sizeof(control),
                        BT_UNSUPPORTED_CONSTRUCT) == 0);
    return 0;
}

static int test_capacity_and_arguments(void)
{
    uint8_t out[16];
    uint8_t snapshot[16];
    uint8_t mutable_source[16] = {'P','R','I','N','T',' ','5'};
    size_t written = 77u;
    size_t exact;
    CHECK(bt_tokenize(NULL, 0, out, sizeof(out), &written) == BT_INVALID_ARGUMENT);
    CHECK(bt_tokenize(mutable_source, 7, NULL, 0, &written) == BT_INVALID_ARGUMENT);
    CHECK(bt_tokenize(mutable_source, 7, out, sizeof(out), NULL) == BT_INVALID_ARGUMENT);
    CHECK(written == 77u);
    memset(out, 0xcc, sizeof(out));
    memcpy(snapshot, out, sizeof(out));
    CHECK(bt_tokenize(mutable_source, 7, out, 2, &written) == BT_NO_SPACE);
    CHECK(bt_tokenize(mutable_source, 7, out, 0, &written) == BT_NO_SPACE);
    CHECK(written == 77u);
    CHECK(memcmp(out, snapshot, sizeof(out)) == 0);
    CHECK(bt_tokenize(mutable_source, 7, mutable_source,
                      sizeof(mutable_source), &written) == BT_INVALID_ARGUMENT);
    CHECK(bt_tokenize(mutable_source, 7, out, sizeof(out),
                      (size_t *)(void *)out) == BT_INVALID_ARGUMENT);
    CHECK(written == 77u);
    CHECK(bt_tokenize(mutable_source, 7, out, 3, &written) == BT_OK);
    exact = written;
    CHECK(exact == sizeof(five));
    CHECK(memcmp(out, five, exact) == 0);
    CHECK(out[exact] == 0xcc);
    return 0;
}

/* J0.2 F3 and F4 are STATICALLY DEDUCED, not independent CPC dumps. */
static const uint8_t j02_f3[] = {
    0x0a,0x00,0x0a,0x00,0xbf,0x20,0x22,'A',0x22,0x00,
    0x08,0x00,0x14,0x00,0xbf,0x20,0x10,0x00,0x00,0x00
};
static const uint8_t j02_f1bis[] = {
    0x0a,0x00,0x0a,0x00,0xbf,0x20,0x22,'H','I',0x00,0x00,0x00
};
static const uint8_t j02_f4[] = {
    0x0a,0x00,0x1e,0x00,0xa0,0x20,0x1e,0x14,0x00,0x00,0x00,0x00
};

static int store_text(BasicProgram *program, uint16_t number,
                      const char *source)
{
    uint8_t buffer[64];
    size_t written;
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      buffer, sizeof(buffer), &written) == BT_OK);
    CHECK(bp_put(program, number, buffer, written) == BP_OK);
    return 0;
}

static int test_program_integration(void)
{
    uint8_t storage[128], exported[128];
    uint8_t combined[sizeof(j02_f3) - 2u + sizeof(j02_f4)];
    BasicProgram program;
    BasicProgramLine line;
    size_t written = 0;

    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    CHECK(store_text(&program, 10, "PRINT \"A\"") == 0);
    CHECK(store_text(&program, 20, "PRINT 2") == 0);
    CHECK(bp_find(&program, 10, &line) == BP_OK);
    CHECK(line.body_length == 5u);
    CHECK(memcmp(program.data + line.body_offset, "\xbf\x20\x22\x41\x22", 5) == 0);
    CHECK(bp_find(&program, 20, &line) == BP_OK);
    CHECK(line.body_length == 3u && program.data[line.body_offset + 2u] == 0x10);
    CHECK(bp_export(&program, exported, sizeof(exported), &written) == BP_OK);
    CHECK(written == sizeof(j02_f3));
    CHECK(memcmp(exported, j02_f3, written) == 0);
    CHECK(store_text(&program, 30, "GOTO 20") == 0);
    CHECK(bp_find(&program, 30, &line) == BP_OK);
    CHECK(line.body_length == sizeof(go20));
    CHECK(memcmp(program.data + line.body_offset, go20, sizeof(go20)) == 0);
    memcpy(combined, j02_f3, sizeof(j02_f3) - 2u);
    memcpy(combined + sizeof(j02_f3) - 2u, j02_f4, sizeof(j02_f4));
    CHECK(bp_export(&program, exported, sizeof(exported), &written) == BP_OK);
    CHECK(written == sizeof(combined));
    CHECK(memcmp(exported, combined, written) == 0);
    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    CHECK(store_text(&program, 10, "PRINT \"HI") == 0);
    CHECK(bp_export(&program, exported, sizeof(exported), &written) == BP_OK);
    CHECK(written == sizeof(j02_f1bis));
    CHECK(memcmp(exported, j02_f1bis, written) == 0);
    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    CHECK(store_text(&program, 30, "GOTO 20") == 0);
    CHECK(bp_export(&program, exported, sizeof(exported), &written) == BP_OK);
    CHECK(written == sizeof(j02_f4));
    CHECK(memcmp(exported, j02_f4, written) == 0);
    return 0;
}

int main(void)
{
    CHECK(test_vectors() == 0);
    CHECK(test_rejections() == 0);
    CHECK(test_capacity_and_arguments() == 0);
    CHECK(test_program_integration() == 0);
    puts("basic_tokenizer: all tests passed");
    return 0;
}
