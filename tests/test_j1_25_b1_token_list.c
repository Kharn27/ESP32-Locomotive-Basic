/* J1.25-B1: original and repeat CPC6128 RUN-independent RAM/LIST
 * oracle. Only CRLF -> LF is normalised on LIST printer transport. */
#include "basic_program.h"
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_session.h"
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

static const char *const cases[12] = {
    "ONE_INTEGER", "TWO_INTEGERS", "ONE_STRING", "QUOTED_COMMA",
    "MIXED_TYPES", "NEXT_DATA_LINE", "JUMP_OVER_DATA", "RESTORE_BEGIN",
    "RESTORE_TARGET", "DATA_COLON", "DATA_EXHAUSTED", "TYPE_MISMATCH"
};
static const char *const sessions[2] = {"original", "repeat"};
enum { BUF=2048 };

static int file_bytes(const char *path, uint8_t *dst, size_t cap, size_t *len)
{
    FILE *f = fopen(path, "rb");
    size_t n;
    int tail;
    if (!f) { perror(path); return 1; }
    n = fread(dst, 1u, cap, f);
    tail = fgetc(f);
    if (ferror(f) || tail != EOF || fclose(f) != 0) return 1;
    *len = n;
    return 0;
}

static int source_to_program(const uint8_t *source, size_t n, BasicProgram *bp)
{
    size_t pos = 0u;
    while (pos < n) {
        size_t start = pos, i;
        unsigned int line = 0u;
        uint8_t body[BUF];
        size_t body_len = 777u;
        while (pos < n && source[pos] != (uint8_t)'\n') ++pos;
        if (pos == n) return 1; /* sealed .bas ends in LF */
        i = start;
        if (i == pos || source[i] < (uint8_t)'0' ||
            source[i] > (uint8_t)'9') return 1;
        while (i < pos && source[i] >= (uint8_t)'0' &&
               source[i] <= (uint8_t)'9') {
            line = line * 10u + (unsigned int)(source[i] - (uint8_t)'0');
            if (line > 65535u) return 1;
            ++i;
        }
        if (i >= pos || source[i++] != (uint8_t)' ') return 1;
        if (bt_tokenize(source + i, pos - i, body, sizeof(body), &body_len)
            != BT_OK) {
            fprintf(stderr, "BT failure source: %.*s\n", (int)(pos - i),
                    (const char *)(source + i));
            return 1;
        }
        if (bp_put(bp, (uint16_t)line, body, body_len) != BP_OK) return 1;
        ++pos;
    }
    return 0;
}

static int list_to_source(const uint8_t *listed, size_t n,
                          uint8_t *dest, size_t cap, size_t *len)
{
    size_t i, k = 0u;
    for (i = 0u; i < n; ++i) {
        uint8_t c = listed[i];
        if (c == (uint8_t)'\r') {
            if (i + 1u >= n || listed[i+1u] != (uint8_t)'\n')
                return 1;
            continue;
        }
        if (k >= cap) return 1;
        dest[k++] = c;
    }
    *len = k;
    return 0;
}

static int verify_case(const char *root, const char *name,
                       const char *session)
{
    char path[512];
    uint8_t source[BUF], oracle_ram[BUF], oracle_list[BUF];
    uint8_t storage[BUF], output[BUF], listed[BUF], normalized[BUF];
    uint8_t storage2[BUF], exported2[BUF];
    BasicProgram bp, second;
    size_t source_len, ram_len, list_len, output_len = 777u;
    size_t listed_len = 777u, normalized_len = 777u, exported2_len = 777u;
    int n;
    n = snprintf(path, sizeof(path), "%s/tests/oracles/inputs/j1_25_a/%s.bas",
                 root, name);
    CHECK(n > 0 && (size_t)n < sizeof(path));
    CHECK(file_bytes(path, source, sizeof(source), &source_len) == 0);
    n = snprintf(path, sizeof(path),
                 "%s/tests/fixtures/cpc6128/j1_25_a_data_read_restore/%s/%s/program.bin",
                 root, session, name);
    CHECK(n > 0 && (size_t)n < sizeof(path));
    CHECK(file_bytes(path, oracle_ram, sizeof(oracle_ram), &ram_len) == 0);
    n = snprintf(path, sizeof(path),
                 "%s/tests/fixtures/cpc6128/j1_25_a_data_read_restore/%s/%s/list/printer.dat",
                 root, session, name);
    CHECK(n > 0 && (size_t)n < sizeof(path));
    CHECK(file_bytes(path, oracle_list, sizeof(oracle_list), &list_len) == 0);

    CHECK(bp_init(&bp, storage, sizeof(storage)) == BP_OK);
    CHECK(source_to_program(source, source_len, &bp) == 0);
    CHECK(bp_export(&bp, output, sizeof(output), &output_len) == BP_OK);
    if (ram_len != output_len || memcmp(output, oracle_ram, ram_len) != 0) {
        size_t i;
        fprintf(stderr, "%s/%s RAM DIFF %zu vs %zu\n",
                session, name, output_len, ram_len);
        for (i=0u; i < output_len || i < ram_len; ++i) {
            fprintf(stderr, " offset=%zu host=%02x cpc=%02x\n", i,
                    i < output_len ? output[i] : 0u,
                    i < ram_len ? oracle_ram[i] : 0u);
            if (i > 12u) break;
        }
        return 1;
    }
    CHECK(bl_list_program(&bp, listed, sizeof(listed), &listed_len) == BL_OK);
    CHECK(list_to_source(oracle_list, list_len, normalized,
                         sizeof(normalized), &normalized_len) == 0);
    if (normalized_len != listed_len ||
        memcmp(normalized, listed, normalized_len) != 0) {
        fprintf(stderr, "%s/%s LIST DIFF host=%.*s oracle=%.*s\n",
                session, name, (int)listed_len, (const char *)listed,
                (int)normalized_len, (const char *)normalized);
        return 1;
    }
    /* This corpus's pre-RUN CPC LIST is source-equivalent, including
     * TYPE_MISMATCH: never use its mutated post-editor list_after_hex. */
    CHECK(normalized_len == source_len);
    CHECK(memcmp(normalized, source, source_len) == 0);
    CHECK(bp_init(&second, storage2, sizeof(storage2)) == BP_OK);
    CHECK(source_to_program(listed, listed_len, &second) == 0);
    CHECK(bp_export(&second, exported2, sizeof(exported2), &exported2_len)
          == BP_OK);
    CHECK(exported2_len == ram_len);
    CHECK(memcmp(exported2, oracle_ram, ram_len) == 0);
    printf("B1 %-16s %-8s RAM_MATCH_EXACT=%zu LIST_MATCH=%zu RETOKEN_MATCH\n",
           name, session, ram_len, listed_len);
    return 0;
}

static int negative_atomicity(void)
{
    static const char *const malformed[] = {
        "DATA", "DATA 1,", "DATA \"UNCLOSED",
        "READ", "READ C%", "READ A!,B%", "READ A%,",
        "RESTORE 200", "RESTORE 65536", "RESTORE -1"
    };
    static const uint8_t bad_bl[][16] = {
        {0x8cu, ' ', '1', ',', 0u}, /* invalid text trailer */
        {0x8cu, ' ', '"', 'X', 0u}, /* incomplete quote */
        {0xc3u, ' ', 0x02u, 0u, 0u, 0xc3u, 0u}, /* forged ref */
        {0xc7u, ' ', 0x1eu, 0x65u, 0u}, /* unverified target */
        {0xc7u, ' ', 0x1eu, 0x64u}, /* short reference */
    };
    static const size_t bad_bl_n[] = {4u,4u,6u,5u,4u};
    uint8_t dst[64], frozen[64], source[128];
    static const uint8_t valid_data[] = "DATA 1";
    static const uint8_t valid_read[] = {0xc3u,' ',0x02u,0u,0u,0xc1u};
    size_t written;
    size_t i;
    for (i=0u; i < sizeof(malformed)/sizeof(malformed[0]); ++i) {
        written = 12345u;
        memset(dst, 0xa5, sizeof dst); memcpy(frozen, dst, sizeof dst);
        CHECK(bt_tokenize((const uint8_t *)malformed[i], strlen(malformed[i]),
                          dst, sizeof(dst), &written) != BT_OK);
        CHECK(written == 12345u && memcmp(dst, frozen, sizeof dst) == 0);
    }
    written=12345u;
    memset(dst, 0xa5, sizeof dst); memcpy(frozen, dst, sizeof dst);
    CHECK(bt_tokenize(valid_data, sizeof(valid_data)-1u, dst, 0u,
                      &written)==BT_NO_SPACE);
    CHECK(memcmp(dst,frozen,sizeof(dst))==0 && written==12345u);
    memcpy(source, valid_data, sizeof(valid_data));
    CHECK(bt_tokenize(source,sizeof(valid_data)-1u,source,sizeof(source),
                      &written)==BT_INVALID_ARGUMENT);
    CHECK(memcmp(dst,frozen,sizeof(dst))==0 && written==12345u);
    CHECK(bt_tokenize(valid_data,sizeof(valid_data)-1u,dst,sizeof(dst),
                      (size_t *)(void *)dst)==BT_INVALID_ARGUMENT);
    CHECK(written == 12345u);
    for(i=0u; i<sizeof(bad_bl)/sizeof(bad_bl[0]); ++i) {
        written=12345u;
        memset(dst,0xa5,sizeof dst); memcpy(frozen,dst,sizeof dst);
        CHECK(bl_detokenize(bad_bl[i],bad_bl_n[i],dst,sizeof(dst),
                            &written)!=BL_OK);
        CHECK(written==12345u && memcmp(dst,frozen,sizeof dst)==0);
    }
    written=12345u;
    memset(dst,0xa5,sizeof dst); memcpy(frozen,dst,sizeof dst);
    CHECK(bl_detokenize(valid_read,sizeof(valid_read),dst,0u,&written)
          ==BL_NO_SPACE);
    CHECK(written==12345u && memcmp(dst,frozen,sizeof dst)==0);
    CHECK(bl_detokenize(valid_read,sizeof(valid_read),dst,sizeof dst,
                        &written)==BL_OK);
    CHECK(written==7u && memcmp(dst,"READ A%",7u)==0);
    CHECK(dst[7]==0xa5u);
    CHECK(bl_detokenize(dst,written,dst,sizeof(dst),&written)==BL_OVERLAP);
    return 0;
}

int main(int argc, char **argv)
{
    size_t i, j;
    CHECK(argc == 2);
    CHECK(negative_atomicity() == 0);
    for (i=0u; i<sizeof(cases)/sizeof(cases[0]); ++i) {
        for(j=0u; j<2u; ++j)
            CHECK(verify_case(argv[1],cases[i],sessions[j]) == 0);
    }
    puts("J1.25-B1 TOKEN_LIST 12/12 original + 12/12 repeat MATCH_EXACT");
    return 0;
}
