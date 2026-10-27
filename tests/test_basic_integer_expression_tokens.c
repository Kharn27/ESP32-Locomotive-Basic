#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_program.h"
#include "basic_executor.h"
#include "basic_variable_store.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

/* ROM-derived, synthetic token vectors; not independent CPC captures. */
static int vector(const char *text, const uint8_t *expected, size_t expected_len)
{
    uint8_t tokens[160], listed[160], repeated[160];
    size_t n = 77u, m = 77u, k = 77u;
    CHECK(bt_tokenize((const uint8_t *)text, strlen(text),
                      tokens, sizeof(tokens), &n) == BT_OK);
    CHECK(n == expected_len && memcmp(tokens, expected, n) == 0);
    CHECK(bl_detokenize(tokens, n, listed, sizeof(listed), &m) == BL_OK);
    CHECK(m == strlen(text) && memcmp(listed, text, m) == 0);
    CHECK(bt_tokenize(listed, m, repeated, sizeof(repeated), &k) == BT_OK);
    CHECK(k == n && memcmp(repeated, tokens, n) == 0);
    return 0;
}

static int test_vectors(void)
{
    static const uint8_t plus0[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x0e};
    static const uint8_t plus9[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x17};
    static const uint8_t plus10[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x19,10};
    static const uint8_t plus255[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x19,255};
    static const uint8_t let[] = {0xa5,' ',2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x11};
    static const uint8_t spaced[] = {2,0,0,0xc2,' ',0xef,' ',2,0,0,0xc1,' ',0xf4,' ',0x19,255};
    static const uint8_t same[] = {2,0,0,0xc2,0xef,2,0,0,0xc2,0xf4,0x0f};
    static const uint8_t mixed[] = {0xa5,' ',2,0,0,0xe2,' ',0xef,' ',2,0,0,'a','.','2'|0x80,
                                    ' ',0xf4,' ',0x19,10};
    CHECK(vector("B%=A%+0", plus0, sizeof(plus0)) == 0);
    CHECK(vector("B%=A%+9", plus9, sizeof(plus9)) == 0);
    CHECK(vector("B%=A%+10", plus10, sizeof(plus10)) == 0);
    CHECK(vector("B%=A%+255", plus255, sizeof(plus255)) == 0);
    CHECK(vector("LET B%=A%+3", let, sizeof(let)) == 0);
    CHECK(vector("B% = A% + 255", spaced, sizeof(spaced)) == 0);
    CHECK(vector("B%=B%+1", same, sizeof(same)) == 0);
    CHECK(vector("LET b% = a.2% + 10", mixed, sizeof(mixed)) == 0);
    CHECK(vector("B%=3", (const uint8_t[]){2,0,0,0xc2,0xef,0x11}, 6u) == 0);
    CHECK(vector("LET B%=255", (const uint8_t[]){0xa5,' ',2,0,0,0xc2,0xef,0x19,255}, 9u) == 0);
    return 0;
}

static int test_long_names(void)
{
    char src[100], target[41];
    uint8_t tokens[160], listed[160], again[160];
    size_t i, n, m, k;
    for (i = 0u; i < 40u; ++i) {
        target[i] = i == 0u ? 'a' : (i % 7u == 0u ? '.' : (char)('0' + (int)(i % 10u)));
    }
    target[40] = '\0';
    (void)snprintf(src, sizeof(src), "B%%=%s%%+9", target);
    CHECK(bt_tokenize((const uint8_t *)src, strlen(src),
                      tokens, sizeof(tokens), &n) == BT_OK);
    CHECK(n == 50u);
    CHECK(tokens[5] == 2u && tokens[6] == 0u && tokens[7] == 0u);
    CHECK(tokens[47] == (uint8_t)((uint8_t)target[39] | 0x80u));
    CHECK(tokens[48] == 0xf4u && tokens[49] == 0x17u);
    CHECK(bl_detokenize(tokens, n, listed, sizeof(listed), &m) == BL_OK);
    CHECK(m == strlen(src) && memcmp(src, listed, m) == 0);
    CHECK(bt_tokenize(listed, m, again, sizeof(again), &k) == BT_OK);
    CHECK(k == n && memcmp(tokens, again, n) == 0);
    return 0;
}

static int test_rejections_and_capacity(void)
{
    static const char *bad[] = {
        "B%=A%", "B%=A%+3+4", "B%=A%*C%",
        "B%=A%+C%", "B%=3+A%", "B%=A!+3", "B%=A$+3",
        "B%=A%+256", "B%=A%+-1", "B%=(A%+3)",
        "B%=A%+","B%=A% + 3X","B%=A%%+3",
        "B%=A%/3", "B%=A%+10.5"
    };
    uint8_t tokens[160], saved[160];
    size_t i, written;
    memset(tokens, 0x65, sizeof(tokens));
    memcpy(saved, tokens, sizeof(saved));
    for (i = 0u; i < sizeof(bad)/sizeof(bad[0]); ++i) {
        written = 888u;
        CHECK(bt_tokenize((const uint8_t *)bad[i], strlen(bad[i]),
                          tokens, sizeof(tokens), &written) != BT_OK);
        CHECK(written == 888u && memcmp(tokens, saved, sizeof(tokens)) == 0);
    }
    written = 888u;
    CHECK(bt_tokenize((const uint8_t *)"B%=A%+255", 9u, tokens, 2u,
                      &written) == BT_NO_SPACE);
    CHECK(written == 888u && memcmp(tokens, saved, sizeof(tokens)) == 0);
    return 0;
}

static int test_imports_and_corruption(void)
{
    static const uint8_t imported[] = {0xa5,2,0x20,0xef,0xc2,0xef,
                                       2,0xf4,0x20,0xc1,0xf4,0x19,255};
    static const uint8_t bad_cache[] = {2,0,0,0xc2,0xef,2,0x20};
    static const uint8_t bad_name[] = {2,0,0,0xc2,0xef,2,0,0,'A'};
    static const uint8_t bad_plus[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xef,0x11};
    static const uint8_t missing_plus[] = {2,0,0,0xc2,0xef,2,0,0,0xc1};
    static const uint8_t missing_number[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4};
    static const uint8_t missing_byte[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x19};
    static const uint8_t bad_short[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x19,9};
    static const uint8_t extra_plus[] = {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x11,0xf4,0x12};
    static const uint8_t wrong_type[] = {2,0,0,0xc2,0xef,3,0,0,0xc1,0xf4,0x11};
    static const struct {
        const uint8_t *body; size_t size;
    } bad[] = {
        {bad_cache,sizeof(bad_cache)}, {bad_name,sizeof(bad_name)},
        {bad_plus,sizeof(bad_plus)}, {missing_plus,sizeof(missing_plus)},
        {missing_number,sizeof(missing_number)}, {missing_byte,sizeof(missing_byte)},
        {bad_short,sizeof(bad_short)}, {extra_plus,sizeof(extra_plus)},
        {wrong_type,sizeof(wrong_type)}
    };
    BasicProgram p, q;
    uint8_t backing1[256], backing2[256], image[256], image2[256];
    uint8_t list[160], snapshot[160], roundtrip[160];
    size_t n, m, k, i, first, second;
    CHECK(bp_init(&p, backing1, sizeof(backing1)) == BP_OK);
    CHECK(bp_init(&q, backing2, sizeof(backing2)) == BP_OK);
    CHECK(bp_put(&p, 10u, imported, sizeof(imported)) == BP_OK);
    CHECK(bp_export(&p, image, sizeof(image), &first) == BP_OK);
    CHECK(bp_import(&q, image, first) == BP_OK);
    CHECK(bp_export(&q, image2, sizeof(image2), &second) == BP_OK);
    CHECK(second == first && memcmp(image, image2, first) == 0);
    CHECK(bl_list_program(&q, list, sizeof(list), &n) == BL_OK);
    CHECK(n == strlen("10 LET B%=A%+255\n"));
    CHECK(memcmp(list, "10 LET B%=A%+255\n", n) == 0);
    CHECK(bp_export(&q, image2, sizeof(image2), &second) == BP_OK);
    CHECK(second == first && memcmp(image, image2, first) == 0);
    CHECK(bl_detokenize(imported, sizeof(imported), list, sizeof(list), &n) == BL_OK);
    CHECK(n == strlen("LET B%=A%+255"));
    CHECK(bt_tokenize(list, n, roundtrip, sizeof(roundtrip), &m) == BT_OK);
    CHECK(m == sizeof(imported) + 1u);
    CHECK(roundtrip[0] == 0xa5u && roundtrip[1] == ' ');
    CHECK(roundtrip[3] == 0u && roundtrip[4] == 0u);
    CHECK(roundtrip[8] == 0u && roundtrip[9] == 0u);
    memset(list, 0x5a, sizeof(list));
    memcpy(snapshot, list, sizeof(list));
    for (i = 0u; i < sizeof(bad)/sizeof(bad[0]); ++i) {
        k = 432u;
        CHECK(bl_detokenize(bad[i].body, bad[i].size, list,
                            sizeof(list), &k) != BL_OK);
        CHECK(k == 432u && memcmp(list, snapshot, sizeof(list)) == 0);
    }
    k = 432u;
    CHECK(bl_detokenize(bad_cache, sizeof(bad_cache), list,
                        sizeof(list), &k) == BL_TRUNCATED);
    k = 432u;
    CHECK(bl_detokenize(missing_number, sizeof(missing_number), list,
                        sizeof(list), &k) == BL_TRUNCATED);
    k = 432u;
    CHECK(bl_detokenize(imported, sizeof(imported), list, 2u, &k) == BL_NO_SPACE);
    CHECK(k == 432u && memcmp(list, snapshot, sizeof(list)) == 0);
    return 0;
}

static int test_atomic_execution(void)
{
    BasicProgram p;
    BasicExecutor e;
    BasicVariableStore store;
    BasicVariableEntry entries[4], entry_copy[4];
    BasicVariableKey a, b;
    BasicVariableValue v;
    uint8_t storage[512], before[512], tokens[160], out[100], out_copy[100];
    size_t n, written, cursor;
    const char *lines[] = {"A%=2", "B%=A%+3", "PRINT B%", "END"};
    size_t i;
    CHECK(bp_init(&p, storage, sizeof(storage)) == BP_OK);
    CHECK(bvs_init(&store, entries, 4u) == BVS_OK);
    for (i = 0u; i < 4u; ++i) {
        CHECK(bt_tokenize((const uint8_t *)lines[i], strlen(lines[i]),
                          tokens, sizeof(tokens), &n) == BT_OK);
        CHECK(bp_put(&p, (uint16_t)((i + 1u) * 10u), tokens, n) == BP_OK);
    }
    CHECK(be_init_with_store(&e, &p, &store) == BE_OK);
    memset(out, 0x99, sizeof(out));
    written = 111u;
    CHECK(be_step(&e, out, sizeof(out), &written) == BE_OK);
    CHECK(written == 0u && store.count == 1u);
    memset(&a, 0, sizeof(a));
    a.type = (uint8_t)BVT_INTEGER;
    a.name_length = 1u;
    a.name[0] = (uint8_t)'A';
    CHECK(bvs_get(&store, &a, &v) == BVS_OK);
    CHECK(v.data.integer == 2);
    memcpy(before, storage, sizeof(before));
    memcpy(entry_copy, entries, sizeof(entries));
    memset(out, 0x77, sizeof(out));
    memcpy(out_copy, out, sizeof(out));
    cursor = e.cursor;
    written = 876u;
    CHECK(be_step(&e, out, sizeof(out), &written) == BE_OK);
    CHECK(written == 0u && e.cursor != cursor);
    CHECK(memcmp(before, storage, sizeof(before)) == 0);
    CHECK(memcmp(out_copy, out, sizeof(out)) == 0);
    CHECK(store.count == 2u);
    CHECK(bvs_get(&store, &a, &v) == BVS_OK && v.data.integer == 2);
    b = a;
    b.name[0] = (uint8_t)'B';
    CHECK(bvs_get(&store, &b, &v) == BVS_OK && v.data.integer == 5);
    memcpy(entry_copy, entries, sizeof(entries));
    CHECK(be_step(&e, out, sizeof(out), &written) == BE_OK);
    CHECK(written == 4u && memcmp(out, " 5 \n", 4u) == 0);
    CHECK(memcmp(entry_copy, entries, sizeof(entries)) == 0);
    CHECK(be_step(&e, out, sizeof(out), &written) == BE_OK);
    CHECK(be_step(&e, out, sizeof(out), &written) == BE_END);
    CHECK(bp_init(&p, storage, sizeof(storage)) == BP_OK);
    CHECK(bt_tokenize((const uint8_t *)"PRINT \"X\":B%=A%+3",
                      strlen("PRINT \"X\":B%=A%+3"),
                      tokens, sizeof(tokens), &n) == BT_OK);
    CHECK(bp_put(&p, 10u, tokens, n) == BP_OK);
    CHECK(be_init_with_store(&e, &p, &store) == BE_OK);
    memcpy(before, storage, sizeof(before));
    memcpy(entry_copy, entries, sizeof(entries));
    memset(out, 0x77, sizeof(out));
    memcpy(out_copy, out, sizeof(out));
    written = 876u;
    CHECK(be_step(&e, out, sizeof(out), &written) == BE_UNSUPPORTED);
    CHECK(written == 876u && e.cursor == 0u);
    CHECK(memcmp(before, storage, sizeof(before)) == 0);
    CHECK(memcmp(entry_copy, entries, sizeof(entries)) == 0);
    CHECK(memcmp(out_copy, out, sizeof(out)) == 0);
    return 0;
}

int main(void)
{
    CHECK(test_vectors() == 0);
    CHECK(test_long_names() == 0);
    CHECK(test_rejections_and_capacity() == 0);
    CHECK(test_imports_and_corruption() == 0);
    CHECK(test_atomic_execution() == 0);
    puts("J0.21 INTEGER expression token tests passed");
    return 0;
}
