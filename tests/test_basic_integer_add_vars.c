/* J1.7-B: exact F4 INTEGER reference/reference syntax and C99 atomicity. */
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_program.h"
#include "basic_executor.h"
#include "basic_variable_store.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); return 1; \
} } while (0)

typedef struct {
    BasicProgram program;
    uint8_t storage[512];
    BasicVariableStore store;
    BasicVariableEntry entries[6];
    BasicExecutor executor;
    uint8_t output[64];
    size_t written;
} Harness;

static BasicVariableKey key(uint8_t name)
{
    BasicVariableKey k = {0};
    k.type = (uint8_t)BVT_INTEGER;
    k.name_length = 1u;
    k.name[0] = name;
    return k;
}

static int setup(Harness *h, size_t count)
{
    memset(h, 0, sizeof(*h));
    CHECK(count <= 6u);
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(bvs_init(&h->store, count ? h->entries : NULL, count) == BVS_OK);
    return 0;
}

static int put(Harness *h, uint16_t line, const char *src)
{
    uint8_t body[128];
    size_t length = 0u;
    CHECK(bt_tokenize((const uint8_t *)src, strlen(src),
                      body, sizeof(body), &length) == BT_OK);
    CHECK(bp_put(&h->program, line, body, length) == BP_OK);
    return 0;
}

static int inject(Harness *h, uint8_t name, int16_t number)
{
    BasicVariableKey k = key(name);
    BasicVariableValue v = {0};
    v.type = (uint8_t)BVT_INTEGER;
    v.data.integer = number;
    CHECK(bvs_assign(&h->store, &k, &v) == BVS_OK);
    return 0;
}

static int equal(const Harness *h, uint8_t name, int16_t number)
{
    BasicVariableKey k = key(name);
    BasicVariableValue value = {0};
    CHECK(bvs_get(&h->store, &k, &value) == BVS_OK);
    CHECK(value.type == (uint8_t)BVT_INTEGER &&
          value.data.integer == number);
    return 0;
}

static int step(Harness *h)
{
    memset(h->output, 0x73, sizeof(h->output));
    h->written = 877u;
    CHECK(be_step(&h->executor, h->output,
                  sizeof(h->output), &h->written) == BE_OK);
    CHECK(h->written == 0u && h->output[0] == 0x73u);
    return 0;
}

/* Includes the complete allocation and all descriptor/output bytes. */
static int fails(Harness *h, BEStatus expected)
{
    BasicProgram p = h->program;
    BasicVariableStore s = h->store;
    BasicExecutor e = h->executor;
    uint8_t storage[sizeof(h->storage)];
    BasicVariableEntry entries[6];
    uint8_t output[sizeof(h->output)];
    memcpy(storage, h->storage, sizeof(storage));
    memcpy(entries, h->entries, sizeof(entries));
    memset(h->output, 0xa6, sizeof(h->output));
    memcpy(output, h->output, sizeof(output));
    h->written = 9321u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output),
                  &h->written) == expected);
    CHECK(h->written == 9321u);
    CHECK(memcmp(&p, &h->program, sizeof(p)) == 0);
    CHECK(memcmp(&s, &h->store, sizeof(s)) == 0);
    CHECK(memcmp(&e, &h->executor, sizeof(e)) == 0);
    CHECK(memcmp(storage, h->storage, sizeof(storage)) == 0);
    CHECK(memcmp(entries, h->entries, sizeof(entries)) == 0);
    CHECK(memcmp(output, h->output, sizeof(output)) == 0);
    return 0;
}

static int tokenizer_listing(void)
{
    static const uint8_t expected[] = {
        0x02,0,0,0xc3,0xef,0x02,0,0,0xc1,0xf4,0x02,0,0,0xc2
    };
    static const char *valid[] = {
        "C%=A%+B%", "LET C%=A%+B%", "C% = A% + B%",
        "A%=A%+B%", "A%=B%+A%", "A%=A%+A%", "C%=A%+A%"
    };
    static const char *invalid[] = {
        "C%=A!+B%", "C%=A$+B%", "C%=A%+B!", "C%=A%+B$",
        "C%=A%+B%+C%", "C%=A%+(B%)", "C%=A%+B%*C%",
        "C%=A%+B%=A%", "C%=A%+2+B%", "C%=A%-B%",
        "C%=A%*B%", "C%=A%\\B%", "C%=A% MOD B%",
        "C%=A%+B%%", "C%=A%+B%1", "C%=A%+_B%",
        "C%=A%+B%+", "C%=A%+B%/2"
    };
    uint8_t body[128], text[128], again[128], before[128];
    size_t i, n, m, k;
    CHECK(bt_tokenize((const uint8_t *)valid[0], strlen(valid[0]),
                      body, sizeof(body), &n) == BT_OK);
    CHECK(n == sizeof(expected) &&
          memcmp(body, expected, sizeof(expected)) == 0);
    for (i = 0u; i < sizeof(valid)/sizeof(valid[0]); ++i) {
        CHECK(bt_tokenize((const uint8_t *)valid[i], strlen(valid[i]),
                          body, sizeof(body), &n) == BT_OK);
        CHECK(bl_detokenize(body, n, text, sizeof(text), &m) == BL_OK);
        CHECK(m == strlen(valid[i]) &&
              memcmp(text, valid[i], m) == 0);
        CHECK(bt_tokenize(text, m, again, sizeof(again), &k) == BT_OK);
        CHECK(k == n && memcmp(body, again, n) == 0);
    }
    memset(body, 0x6a, sizeof(body));
    memcpy(before, body, sizeof(before));
    for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        n = 876u;
        CHECK(bt_tokenize((const uint8_t *)invalid[i], strlen(invalid[i]),
                          body, sizeof(body), &n) != BT_OK);
        CHECK(n == 876u && memcmp(body, before, sizeof(body)) == 0);
    }
    n = 87u;
    CHECK(bt_tokenize((const uint8_t *)valid[0], strlen(valid[0]),
                      body, 4u, &n) == BT_NO_SPACE);
    CHECK(n == 87u && memcmp(body, before, sizeof(body)) == 0);
    return 0;
}

static int corpus(void)
{
    static const struct { int16_t a, b, c; int overflow; } cases[] = {
        {2,3,5,0},{7,-2,5,0},{-7,2,-5,0},{-7,-3,-10,0},
        {INT16_MIN,1,INT16_MIN+1,0},{INT16_MIN,0,INT16_MIN,0},
        {INT16_MAX,0,INT16_MAX,0},{INT16_MAX,1,0,1},
        {INT16_MIN,-1,0,1},{255,255,510,0},{0,0,0,0},{1,-1,0,0}
    };
    size_t i;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        Harness h;
        BasicProgram imported;
        uint8_t imported_storage[512], binary[512], copy[512], listing[256];
        char a[48], b[48], full[192], printable[48];
        size_t size = 0u, copy_size = 0u, list_size = 0u;
        CHECK(setup(&h, 6u) == 0);
        (void)snprintf(a, sizeof(a), "A%%=%d", (int)cases[i].a);
        (void)snprintf(b, sizeof(b), "B%%=%d", (int)cases[i].b);
        (void)snprintf(full, sizeof(full),
                       "10 %s\n20 %s\n30 C%%=A%%+B%%\n40 PRINT C%%\n50 END\n", a, b);
        CHECK(put(&h, 10u, a) == 0);
        CHECK(put(&h, 20u, b) == 0);
        CHECK(put(&h, 30u, "C%=A%+B%") == 0);
        CHECK(put(&h, 40u, "PRINT C%") == 0);
        CHECK(put(&h, 50u, "END") == 0);
        CHECK(bp_export(&h.program, binary, sizeof(binary), &size) == BP_OK);
        CHECK(bp_init(&imported, imported_storage, sizeof(imported_storage)) == BP_OK);
        CHECK(bp_import(&imported, binary, size) == BP_OK);
        CHECK(bp_export(&imported, copy, sizeof(copy), &copy_size) == BP_OK);
        CHECK(copy_size == size && memcmp(binary, copy, size) == 0);
        CHECK(bl_list_program(&imported, listing, sizeof(listing), &list_size) == BL_OK);
        CHECK(list_size == strlen(full) && memcmp(listing, full, list_size) == 0);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(step(&h) == 0 && equal(&h, 'A', cases[i].a) == 0);
        CHECK(step(&h) == 0 && equal(&h, 'B', cases[i].b) == 0);
        if (cases[i].overflow) {
            /* Existing AND absent destinations both remain intact. */
            CHECK(fails(&h, BE_INTEGER_OVERFLOW) == 0);
            CHECK(fails(&h, BE_INTEGER_OVERFLOW) == 0);
            CHECK(h.store.count == 2u);
            CHECK(inject(&h, 'C', 473) == 0);
            CHECK(fails(&h, BE_INTEGER_OVERFLOW) == 0);
            CHECK(equal(&h, 'C', 473) == 0);
        } else {
            CHECK(step(&h) == 0 && equal(&h, 'C', cases[i].c) == 0);
            h.written = 888u;
            CHECK(be_step(&h.executor, h.output, sizeof(h.output),
                          &h.written) == BE_OK);
            (void)snprintf(printable, sizeof(printable),
                           "%s%d \n", cases[i].c >= 0 ? " " : "",
                           (int)cases[i].c);
            CHECK(h.written == strlen(printable) &&
                  memcmp(h.output, printable, h.written) == 0);
            CHECK(step(&h) == 0);
            h.written = 999u;
            CHECK(be_step(&h.executor, h.output, sizeof(h.output),
                          &h.written) == BE_END && h.written == 999u);
        }
    }
    return 0;
}

static int failure_and_alias(void)
{
    static const struct { const char *s; int a, b, result; } alias[] = {
        {"A%=A%+B%",4,7,11}, {"A%=B%+A%",4,7,11},
        {"A%=A%+A%",4,7,8}, {"C%=A%+A%",4,7,8}
    };
    static const struct {
        uint8_t bytes[20]; size_t len; BEStatus error;
    } corrupt[] = {
        {{2,0,0,0xc3,0xef,2,0,0,0xc1,0xf4,2,0,0},13,BE_TRUNCATED},
        {{2,0,0,0xc3,0xef,2,0,0,0xc1,0xf4,3,0,0,0xc2},14,BE_BAD_SEQUENCE},
        {{2,0,0,0xc3,0xef,2,0,0,0xc1,0xf4,4,0,0,0xc2},14,BE_BAD_SEQUENCE},
        {{2,0,0,0xc3,0xef,2,0,0,0xc1,0xf4,2,0,0,0xc2,0xf4,0x0f},16,BE_BAD_SEQUENCE},
        {{2,0,0,0xc3,0xef,2,0,0,0xc1,0xf5,2,0,0,0xc2},14,BE_BAD_SEQUENCE}
    };
    Harness h;
    size_t i;
    for (i = 0u; i < sizeof(alias)/sizeof(alias[0]); ++i) {
        CHECK(setup(&h, 6u) == 0);
        CHECK(inject(&h, 'A', (int16_t)alias[i].a) == 0);
        CHECK(inject(&h, 'B', (int16_t)alias[i].b) == 0);
        CHECK(put(&h, 10u, alias[i].s) == 0);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(step(&h) == 0);
        CHECK(equal(&h, alias[i].s[0], (int16_t)alias[i].result) == 0);
    }
    CHECK(setup(&h, 6u) == 0);
    CHECK(inject(&h, 'B', 3) == 0);
    CHECK(put(&h, 10u, "C%=A%+B%") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_VARIABLE_NOT_FOUND) == 0);
    CHECK(setup(&h, 6u) == 0);
    CHECK(inject(&h, 'A', 3) == 0);
    CHECK(put(&h, 10u, "C%=A%+B%") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_VARIABLE_NOT_FOUND) == 0);
    /* Distinguish errors and preserve the entire already-full variable store. */
    CHECK(setup(&h, 2u) == 0);
    CHECK(inject(&h, 'A', 3) == 0);
    CHECK(inject(&h, 'B', 2) == 0);
    CHECK(put(&h, 10u, "C%=A%+B%") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_STORE_FULL) == 0);
    CHECK(setup(&h, 6u) == 0);
    CHECK(inject(&h, 'A', 3) == 0);
    CHECK(inject(&h, 'B', 2) == 0);
    for (i = 0u; i < sizeof(corrupt)/sizeof(corrupt[0]); ++i) {
        CHECK(bp_put(&h.program, 10u, corrupt[i].bytes, corrupt[i].len) == BP_OK);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(fails(&h, corrupt[i].error) == 0);
    }
    /* Imported reference cache may contain apparently meaningful opcodes. */
    {
        static const uint8_t opaque[] = {
            2,0x20,0xef,0xc3,0xef,2,0xf4,0x20,0xc1,
            0xf4,2,0xef,0xf4,0xc2
        };
        uint8_t image[512], text[64];
        size_t length = 0u, written = 0u;
        CHECK(bp_put(&h.program, 10u, opaque, sizeof(opaque)) == BP_OK);
        CHECK(bp_export(&h.program, image, sizeof(image), &length) == BP_OK);
        CHECK(bl_detokenize(opaque, sizeof(opaque), text, sizeof(text), &written) == BL_OK);
        CHECK(written == strlen("C%=A%+B%") &&
              memcmp(text, "C%=A%+B%", written) == 0);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(step(&h) == 0 && equal(&h, 'C', 5) == 0);
        CHECK(bp_export(&h.program, text, 0u, &written) == BP_NO_SPACE);
        CHECK(memcmp(h.storage, image, length) == 0);
    }
    return 0;
}

int main(void)
{
    CHECK(tokenizer_listing() == 0);
    CHECK(corpus() == 0);
    CHECK(failure_and_alias() == 0);
    puts("J1.7-B INTEGER variable+variable F4 / atomicity PASS");
    return 0;
}
