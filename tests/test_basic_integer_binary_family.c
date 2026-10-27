/* J1.9-B: F6/F9/FB explicit INTEGER operands and atomicity. */
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


typedef struct {
    const char *name, *op;
    int16_t a, b, expected;
    BEStatus error;
} Case;

static int token_listing(void)
{
    static const char *valid[] = {
        "C%=A%*B%", "C%=A%\\B%", "C%=A% MOD B%",
        "LET C%=A%*B%", "C% = A% * B%", "C% = A% \\ B%",
        "C% = A% MOD B%", "A%=A%*A%", "B%=A%\\B%",
        "C%=A% MOD A%"
    };
    static const char *invalid[] = {
        "C%=A%*B%+D%", "C%=A%\\B%*C%", "C%=A% MOD B%-D%",
        "C%=A%/(B%)", "C%=A%/B%", "C%=A% MODX B%",
        "C%=A% MOD B!", "C%=A%*B$", "C%=A%\\B%=D%",
        "C%=A%*B%1", "C%=A% MOD B%%", "C%=A%*B%+2",
        "C%=A%\\(B%)", "C%=A% MOD (B%)", "C%=A% MOD B%*2"
    };
    static const uint8_t tokens[] = {0xf6u,0xf9u,0xfbu};
    static const char *basic[] = {"C%=A%*B%", "C%=A%\\B%",
                                   "C%=A% MOD B%"};
    size_t i, n, listed, again_size;
    uint8_t data[128], text[128], again[128], before[128];
    for (i = 0u; i < sizeof(valid)/sizeof(valid[0]); ++i) {
        CHECK(bt_tokenize((const uint8_t *)valid[i], strlen(valid[i]),
                          data, sizeof(data), &n) == BT_OK);
        CHECK(bl_detokenize(data, n, text, sizeof(text), &listed) == BL_OK);
        CHECK(listed == strlen(valid[i]) &&
              memcmp(text, valid[i], listed) == 0);
        CHECK(bt_tokenize(text, listed, again, sizeof(again),
                          &again_size) == BT_OK);
        CHECK(again_size == n && memcmp(data, again, n) == 0);
    }
    for (i = 0u; i < 3u; ++i) {
        static const uint8_t signature[14] = {
            2,0,0,0xc3,0xef,2,0,0,0xc1,0,2,0,0,0xc2
        };
        uint8_t expected[sizeof(signature)];
        memcpy(expected, signature, sizeof(expected));
        expected[9] = tokens[i];
        CHECK(bt_tokenize((const uint8_t *)basic[i], strlen(basic[i]),
                          data, sizeof(data), &n) == BT_OK);
        if (i == 2u) {
            /* CPC preserves both spaces framing MOD (after A%, before B%). */
            static const uint8_t mod_bytes[] = {
                2,0,0,0xc3,0xef,2,0,0,0xc1,0x20,0xfb,0x20,2,0,0,0xc2
            };
            CHECK(n == sizeof(mod_bytes) &&
                  memcmp(data, mod_bytes, sizeof(mod_bytes)) == 0);
        } else {
            CHECK(n == sizeof(expected) &&
                  memcmp(data, expected, sizeof(expected)) == 0);
        }
    }
    memset(data, 0x6au, sizeof(data));
    memcpy(before, data, sizeof(data));
    for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        n = 876u;
        CHECK(bt_tokenize((const uint8_t *)invalid[i], strlen(invalid[i]),
                          data, sizeof(data), &n) != BT_OK);
        CHECK(n == 876u && memcmp(before, data, sizeof(data)) == 0);
    }
    n = 777u;
    CHECK(bt_tokenize((const uint8_t *)basic[0], strlen(basic[0]),
                      data, 4u, &n) == BT_NO_SPACE);
    CHECK(n == 777u && memcmp(before, data, sizeof(data)) == 0);
    return 0;
}

static int corpus(void)
{
    static const Case cases[] = {
        {"M_P2_P3","*",2,3,6,BE_OK},
        {"M_N3_P4","*",-3,4,-12,BE_OK},
        {"M_N7_N2","*",-7,-2,14,BE_OK},
        {"M_Z_PMAX","*",0,32767,0,BE_OK},
        {"M_NMIN_P1","*",-32768,1,-32768,BE_OK},
        {"M_NMIN_N1","*",-32768,-1,0,BE_INTEGER_OVERFLOW},
        {"M_PMAX_P2","*",32767,2,0,BE_INTEGER_OVERFLOW},
        {"M_P127_P128","*",127,128,16256,BE_OK},
        {"D_P7_P2","\\",7,2,3,BE_OK},
        {"D_N7_P2","\\",-7,2,-3,BE_OK},
        {"D_P7_N2","\\",7,-2,-3,BE_OK},
        {"D_N7_N2","\\",-7,-2,3,BE_OK},
        {"D_NMIN_P1","\\",-32768,1,-32768,BE_OK},
        {"D_NMIN_N1","\\",-32768,-1,0,BE_INTEGER_OVERFLOW},
        {"D_P7_Z","\\",7,0,0,BE_DIVISION_BY_ZERO},
        {"D_PMAX_P1","\\",32767,1,32767,BE_OK},
        {"R_P7_P3"," MOD ",7,3,1,BE_OK},
        {"R_N7_P3"," MOD ",-7,3,-1,BE_OK},
        {"R_P7_N3"," MOD ",7,-3,1,BE_OK},
        {"R_N7_N3"," MOD ",-7,-3,-1,BE_OK},
        {"R_NMIN_N1"," MOD ",-32768,-1,0,BE_OK},
        {"R_Z_P3"," MOD ",0,3,0,BE_OK},
        {"R_P7_Z"," MOD ",7,0,0,BE_DIVISION_BY_ZERO},
        {"R_NMIN_P255"," MOD ",-32768,255,-128,BE_OK},
    };
    size_t i, ok = 0u, overflow = 0u, zero = 0u;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        Harness h;
        BasicProgram imported;
        uint8_t storage[512], image[512], second[512], listing[256];
        char a[48], b[48], expr[80], full[256], output[48];
        size_t image_n = 0u, second_n = 0u, list_n = 0u;
        const Case *c = &cases[i];
        (void)c->name;
        CHECK(setup(&h, 6u) == 0);
        (void)snprintf(a, sizeof(a), "A%%=%d", (int)c->a);
        (void)snprintf(b, sizeof(b), "B%%=%d", (int)c->b);
        (void)snprintf(expr, sizeof(expr), "C%%=A%%%sB%%", c->op);
        (void)snprintf(full, sizeof(full),
                       "10 %s\n20 %s\n30 %s\n40 PRINT C%%\n50 END\n",
                       a, b, expr);
        CHECK(put(&h, 10u, a) == 0);
        CHECK(put(&h, 20u, b) == 0);
        CHECK(put(&h, 30u, expr) == 0);
        CHECK(put(&h, 40u, "PRINT C%") == 0);
        CHECK(put(&h, 50u, "END") == 0);
        CHECK(bp_export(&h.program, image, sizeof(image), &image_n) == BP_OK);
        CHECK(bp_init(&imported, storage, sizeof(storage)) == BP_OK);
        CHECK(bp_import(&imported, image, image_n) == BP_OK);
        CHECK(bl_list_program(&imported, listing, sizeof(listing), &list_n) == BL_OK);
        CHECK(list_n == strlen(full) && memcmp(listing, full, list_n) == 0);
        CHECK(bp_export(&imported, second, sizeof(second), &second_n) == BP_OK);
        CHECK(second_n == image_n && memcmp(second, image, image_n) == 0);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(step(&h) == 0 && equal(&h, 'A', c->a) == 0);
        CHECK(step(&h) == 0 && equal(&h, 'B', c->b) == 0);
        if (c->error != BE_OK) {
            CHECK(fails(&h, c->error) == 0);
            CHECK(fails(&h, c->error) == 0);
            CHECK(h.executor.cursor != 0u && h.store.count == 2u);
            CHECK(equal(&h, 'A', c->a) == 0);
            CHECK(equal(&h, 'B', c->b) == 0);
            /* Also an existing destination must remain bitwise untouched. */
            CHECK(inject(&h, 'C', 473) == 0);
            CHECK(fails(&h, c->error) == 0);
            CHECK(fails(&h, c->error) == 0);
            CHECK(equal(&h, 'C', 473) == 0);
            if (c->error == BE_DIVISION_BY_ZERO) ++zero;
            else if (c->error == BE_INTEGER_OVERFLOW) ++overflow;
            else CHECK(0);
        } else {
            CHECK(step(&h) == 0 && equal(&h, 'C', c->expected) == 0);
            h.written = 888u;
            CHECK(be_step(&h.executor, h.output, sizeof(h.output),
                          &h.written) == BE_OK);
            (void)snprintf(output, sizeof(output), "%s%d \n",
                           c->expected < 0 ? "" : " ", (int)c->expected);
            CHECK(h.written == strlen(output) &&
                  memcmp(h.output, output, h.written) == 0);
            CHECK(step(&h) == 0);
            h.written = 999u;
            CHECK(be_step(&h.executor, h.output, sizeof(h.output),
                          &h.written) == BE_END && h.written == 999u);
            ++ok;
        }
    }
    CHECK(ok == 19u && overflow == 3u && zero == 2u);
    return 0;
}

static int alias_and_failures(void)
{
    static const struct { const char *op; int16_t a,b; int16_t expected[4]; } ops[] = {
        {"*", 7,3,{21,21,49,49}},
        {"\\",7,3,{2,0,1,1}},
        {" MOD ",7,3,{1,3,0,0}}
    };
    static const uint8_t tokens[] = {0xf6u,0xf9u,0xfbu};
    size_t op, i;
    Harness h;
    for (op = 0u; op < 3u; ++op) {
        static const char *forms[] = {"A%=A%OPB%", "A%=B%OPA%",
                                       "A%=A%OPA%", "C%=A%OPA%"};
        for (i = 0u; i < 4u; ++i) {
            char expression[64];
            const char *f = forms[i];
            const char *where = strstr(f, "OP");
            size_t front = (size_t)(where - f);
            CHECK(front < sizeof(expression));
            memcpy(expression, f, front);
            expression[front] = '\0';
            (void)strcat(expression, ops[op].op);
            (void)strcat(expression, where + 2);
            CHECK(setup(&h, 6u) == 0);
            CHECK(inject(&h, 'A', ops[op].a) == 0);
            CHECK(inject(&h, 'B', ops[op].b) == 0);
            CHECK(put(&h, 10u, expression) == 0);
            CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
            CHECK(step(&h) == 0);
            CHECK(equal(&h, (uint8_t)expression[0],
                        ops[op].expected[i]) == 0);
        }
        /* Missing left or right value, store-full: complete bitwise rollback. */
        for (i = 0u; i < 3u; ++i) {
            char expr[64];
            (void)snprintf(expr,sizeof(expr),"C%%=A%%%sB%%",ops[op].op);
            CHECK(setup(&h, i == 2u ? 2u : 6u) == 0);
            if (i != 0u) CHECK(inject(&h,'A',7) == 0);
            if (i != 1u) CHECK(inject(&h,'B',3) == 0);
            CHECK(put(&h,10u,expr) == 0);
            CHECK(be_init_with_store(&h.executor,&h.program,&h.store) == BE_OK);
            CHECK(fails(&h, i == 2u ? BE_STORE_FULL : BE_VARIABLE_NOT_FOUND) == 0);
            CHECK(fails(&h, i == 2u ? BE_STORE_FULL : BE_VARIABLE_NOT_FOUND) == 0);
        }
        /* Opaque caches are data, including bytes resembling instructions. */
        {
            uint8_t raw[] = {
                2,0x20,0xef,0xc3,0xef,2,0xf4,0xf5,0xc1,0,
                2,0xfb,0x20,0xc2
            };
            uint8_t snap[sizeof(h.storage)], text[64];
            size_t n = 0u;
            const char *expected = ops[op].op;
            CHECK(setup(&h,6u) == 0);
            CHECK(inject(&h,'A',7) == 0);
            CHECK(inject(&h,'B',3) == 0);
            raw[9] = tokens[op];
            CHECK(bp_put(&h.program,10u,raw,sizeof(raw)) == BP_OK);
            memcpy(snap,h.storage,sizeof(snap));
            CHECK(bl_detokenize(raw,sizeof(raw),text,sizeof(text),&n) == BL_OK);
            /* Opaque cache bytes never enter the text. */
            CHECK(n > strlen(expected));
            CHECK(be_init_with_store(&h.executor,&h.program,&h.store) == BE_OK);
            CHECK(step(&h) == 0);
            CHECK(memcmp(snap,h.storage,sizeof(snap)) == 0);
        }
        /* Malformed serialized references, wrong opcode and suffixes. */
        for (i = 0u; i < 4u; ++i) {
            uint8_t raw[] = {2,0,0,0xc3,0xef,2,0,0,0xc1,
                             0,2,0,0,0xc2};
            size_t n = sizeof(raw);
            BEStatus expected = BE_BAD_SEQUENCE;
            CHECK(setup(&h,6u) == 0);
            CHECK(inject(&h,'A',7) == 0);
            CHECK(inject(&h,'B',3) == 0);
            raw[9] = tokens[op];
            if (i == 0u) {n = sizeof(raw) - 1u; expected = BE_TRUNCATED;}
            if (i == 1u) raw[10] = 3u; /* wrong right BVR tag */
            if (i == 2u) raw[9] = 0xefu; /* illegal operator */
            if (i == 3u) raw[0] = 3u; /* wrong destination type */
            CHECK(bp_put(&h.program,10u,raw,n) == BP_OK);
            CHECK(be_init_with_store(&h.executor,&h.program,&h.store) == BE_OK);
            CHECK(fails(&h,expected) == 0);
            CHECK(fails(&h,expected) == 0);
        }
    }
    /* Scope excludes suffix statements; no prefix commit. */
    CHECK(setup(&h,6u) == 0);
    CHECK(inject(&h,'A',7) == 0);
    CHECK(inject(&h,'B',3) == 0);
    CHECK(put(&h,10u,"C%=A%*B%:PRINT 1") == 0);
    CHECK(be_init_with_store(&h.executor,&h.program,&h.store) == BE_OK);
    CHECK(fails(&h,BE_UNSUPPORTED) == 0);
    CHECK(fails(&h,BE_UNSUPPORTED) == 0);
    /* Divisor alias zero fails before assigning to its source/destination. */
    CHECK(setup(&h,6u) == 0);
    CHECK(inject(&h,'A',0) == 0);
    CHECK(put(&h,10u,"A%=A%\\A%") == 0);
    CHECK(be_init_with_store(&h.executor,&h.program,&h.store) == BE_OK);
    CHECK(fails(&h,BE_DIVISION_BY_ZERO) == 0);
    CHECK(fails(&h,BE_DIVISION_BY_ZERO) == 0);
    CHECK(equal(&h,'A',0) == 0);
    /* Prefix success remains committed after output-buffer failure at PRINT. */
    CHECK(setup(&h,6u) == 0);
    CHECK(inject(&h,'A',7) == 0);
    CHECK(inject(&h,'B',3) == 0);
    CHECK(put(&h,10u,"C%=A%*B%") == 0);
    CHECK(put(&h,20u,"PRINT C%") == 0);
    CHECK(be_init_with_store(&h.executor,&h.program,&h.store) == BE_OK);
    CHECK(step(&h) == 0 && equal(&h,'C',21) == 0);
    {
        size_t n = 777u;
        uint8_t before[sizeof(h.output)];
        memset(h.output,0x66,sizeof(h.output));
        memcpy(before,h.output,sizeof(before));
        CHECK(be_step(&h.executor,h.output,0u,&n) == BE_NO_SPACE);
        CHECK(n == 777u && memcmp(before,h.output,sizeof(before)) == 0);
        CHECK(be_step(&h.executor,(uint8_t *)&h.executor,
                      sizeof(h.executor),&n) == BE_OVERLAP);
        CHECK(n == 777u && equal(&h,'C',21) == 0);
    }
    return 0;
}

int main(void)
{
    CHECK(token_listing() == 0);
    CHECK(corpus() == 0);
    CHECK(alias_and_failures() == 0);
    puts("J1.9-B INTEGER F6/F9/FB family / atomicity PASS");
    return 0;
}
