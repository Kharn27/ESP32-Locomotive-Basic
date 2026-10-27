/* J1.6-B: bounded FB INTEGER MOD (not a general evaluator). */
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
    BasicVariableEntry entries[4];
    BasicExecutor executor;
    uint8_t output[64];
    size_t written;
} Harness;

static BasicVariableKey make_key(uint8_t name)
{
    BasicVariableKey key = {0};
    key.type = (uint8_t)BVT_INTEGER;
    key.name_length = 1u;
    key.name[0] = name;
    return key;
}

static int setup(Harness *h, size_t capacity)
{
    memset(h, 0, sizeof(*h));
    CHECK(capacity <= 4u);
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(bvs_init(&h->store, capacity ? h->entries : NULL, capacity) == BVS_OK);
    return 0;
}

static int put(Harness *h, uint16_t number, const char *source)
{
    uint8_t tokens[128];
    size_t n = 0u;
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      tokens, sizeof(tokens), &n) == BT_OK);
    CHECK(bp_put(&h->program, number, tokens, n) == BP_OK);
    return 0;
}

static int inject(Harness *h, uint8_t name, int16_t number)
{
    BasicVariableKey key = make_key(name);
    BasicVariableValue val = {0};
    val.type = (uint8_t)BVT_INTEGER;
    val.data.integer = number;
    CHECK(bvs_assign(&h->store, &key, &val) == BVS_OK);
    return 0;
}

static int equal(Harness *h, uint8_t name, int16_t number)
{
    BasicVariableKey key = make_key(name);
    BasicVariableValue val = {0};
    CHECK(bvs_get(&h->store, &key, &val) == BVS_OK);
    CHECK(val.type == (uint8_t)BVT_INTEGER && val.data.integer == number);
    return 0;
}

static int step(Harness *h)
{
    memset(h->output, 0x93, sizeof(h->output));
    h->written = 773u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output), &h->written) == BE_OK);
    CHECK(h->written == 0u && h->output[0] == 0x93u);
    return 0;
}

/* Every failed be_step() must preserve ALL observable caller-owned state. */
static int failure(Harness *h, BEStatus expected)
{
    BasicProgram before_p = h->program;
    BasicVariableStore before_s = h->store;
    BasicExecutor before_e = h->executor;
    uint8_t before_storage[sizeof(h->storage)];
    BasicVariableEntry before_entries[sizeof(h->entries)/sizeof(h->entries[0])];
    uint8_t before_output[sizeof(h->output)];
    memcpy(before_storage, h->storage, sizeof(before_storage));
    memcpy(before_entries, h->entries, sizeof(before_entries));
    memset(h->output, 0xa6, sizeof(h->output));
    memcpy(before_output, h->output, sizeof(before_output));
    h->written = 3456u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output), &h->written) == expected);
    CHECK(h->written == 3456u);
    CHECK(memcmp(&before_p, &h->program, sizeof(before_p)) == 0);
    CHECK(memcmp(&before_s, &h->store, sizeof(before_s)) == 0);
    CHECK(memcmp(&before_e, &h->executor, sizeof(before_e)) == 0);
    CHECK(memcmp(before_storage, h->storage, sizeof(before_storage)) == 0);
    CHECK(memcmp(before_entries, h->entries, sizeof(before_entries)) == 0);
    CHECK(memcmp(before_output, h->output, sizeof(before_output)) == 0);
    return 0;
}

static int test_tokens_and_listing(void)
{
    static const struct {
        const char *source;
        uint8_t bytes[32];
        size_t count;
    } vectors[] = {
        {"B%=A% MOD 0",   {2,0,0,0xc2,0xef,2,0,0,0xc1,' ',0xfb,' ',0x0e}, 13},
        {"B%=A% MOD 3",   {2,0,0,0xc2,0xef,2,0,0,0xc1,' ',0xfb,' ',0x11}, 13},
        {"B%=A% MOD 255", {2,0,0,0xc2,0xef,2,0,0,0xc1,' ',0xfb,' ',0x19,255}, 14},
        {"LET B%=A% MOD 3", {0xa5,' ',2,0,0,0xc2,0xef,2,0,0,0xc1,' ',0xfb,' ',0x11}, 15},
        {"B% = A% MOD 255", {2,0,0,0xc2,' ',0xef,' ',2,0,0,0xc1,' ',0xfb,' ',0x19,255}, 16},
        {"B%=B% MOD 1", {2,0,0,0xc2,0xef,2,0,0,0xc2,' ',0xfb,' ',0x0f}, 13},
        /* MOD embedded in a legal identifier must not be split into FB. */
        {"B%=AMOD% MOD 1",
         {2,0,0,0xc2,0xef,2,0,0,'A','M','O',0xc4,' ',0xfb,' ',0x0f}, 16},
        {"B%=-32768", {2,0,0,0xc2,0xef,0xf5,0x1f,0,0,0,0,0x90}, 12},
        {"B%=A%+3", {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf4,0x11}, 11},
        {"B%=A%-3", {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf5,0x11}, 11},
        {"B%=A%*3", {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf6,0x11}, 11},
        {"B%=A%\\3", {2,0,0,0xc2,0xef,2,0,0,0xc1,0xf9,0x11}, 11}
    };
    size_t i, n, m, k;
    uint8_t token[96], text[96], again[96];
    for (i = 0u; i < sizeof(vectors)/sizeof(vectors[0]); ++i) {
        const char *source = vectors[i].source;
        CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                          token, sizeof(token), &n) == BT_OK);
        CHECK(n == vectors[i].count &&
              memcmp(token, vectors[i].bytes, n) == 0);
        CHECK(bl_detokenize(token, n, text, sizeof(text), &m) == BL_OK);
        CHECK(m == strlen(source) && memcmp(text, source, m) == 0);
        CHECK(bt_tokenize(text, m, again, sizeof(again), &k) == BT_OK);
        CHECK(k == n && memcmp(token, again, n) == 0);
    }
    {
        static const char *invalid[] = {
            "B%=A% MOD 256", "B%=A% MOD -1", "B%=A% MOD  -1",
            "B%=A% MOD +1", "B%=A% MOD 1-2", "B%=A% MOD 1+2",
            "B%=A% MOD C%", "B%=A! MOD 2", "B%=A$ MOD 2",
            "B%=A% MOD (2)", "B%=A% MOD 1.2", "B%=A% MOD 1E2",
            "B%=A% MOD 32768", "B%=A% MOD ", "B%=A% MOD 2/2",
            "B%=A% MOD 1:PRINT 2:", "B%=A% MOD 1: ",
            "B%=A% MOD1", "B%=A%MOD 1", "B%=A% MODERN 1", "B%=A% MODMOD 1",
            "B%=A% M OD 1", "B%=A% / 2", "B%=A% MOD 1 MOD 2"
        };
        uint8_t saved[sizeof(token)];
        memset(token, 0x7a, sizeof(token));
        memcpy(saved, token, sizeof(saved));
        for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
            n = 999u;
            CHECK(bt_tokenize((const uint8_t *)invalid[i], strlen(invalid[i]),
                              token, sizeof(token), &n) != BT_OK);
            CHECK(n == 999u && memcmp(saved, token, sizeof(token)) == 0);
        }
        n = 999u;
        CHECK(bt_tokenize((const uint8_t *)"B%=A% MOD 255", 13u,
                          token, 2u, &n) == BT_NO_SPACE);
        CHECK(n == 999u && memcmp(saved, token, sizeof(token)) == 0);
        n = 999u;
        CHECK(bt_tokenize((const uint8_t *)"B%=A% MOD 3", 11u,
                          token, sizeof(token), (size_t *)token) == BT_INVALID_ARGUMENT);
        CHECK(memcmp(saved, token, sizeof(token)) == 0);
    }
    /* An imported cache is opaque; the opcode after the source matters. */
    {
        static const uint8_t imported[] = {
            0xa5,2,0x20,0xef,0xc2,0xef,2,0xf4,0x20,0xc1,
            ' ',0xfb,' ',0x19,255
        };
        static const uint8_t broken[] = {
            2,0,0,0xc2,0xef,2,0,0,0xc1,' ',0xfb,' ',0x19,9
        };
        uint8_t before[96];
        CHECK(bl_detokenize(imported, sizeof(imported), text, sizeof(text), &m) == BL_OK);
        CHECK(m == strlen("LET B%=A% MOD 255") &&
              memcmp(text, "LET B%=A% MOD 255", m) == 0);
        memset(text, 0x74, sizeof(text));
        memcpy(before, text, sizeof(text));
        m = 99u;
        CHECK(bl_detokenize(imported, sizeof(imported), text, 2u, &m) == BL_NO_SPACE);
        CHECK(m == 99u && memcmp(before, text, sizeof(text)) == 0);
        m = 99u;
        CHECK(bl_detokenize(broken, sizeof(broken), text, sizeof(text), &m) ==
              BL_BAD_SEQUENCE);
        CHECK(m == 99u && memcmp(before, text, sizeof(text)) == 0);
    }
    return 0;
}

static int test_programs(void)
{
    /* Results are the twelve CPC ERR/B% printer observations from J1.6-A. */
    static const struct { int16_t a; unsigned n; int16_t b; int zero; } cases[] = {
        {6,3,0,0}, {7,2,1,0}, {-7,2,-1,0}, {-7,3,-1,0},
        {-5,2,-1,0}, {INT16_MIN,1,0,0}, {INT16_MIN,255,-128,0},
        {INT16_MAX,255,127,0}, {2,255,2,0}, {255,255,0,0},
        {1,0,0,1}, {0,0,0,1}
    };
    size_t i;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        Harness h;
        BasicProgram imported;
        uint8_t imported_storage[512], binary[512], rebuilt[512], listing[256];
        char first[48], second[48], expected_source[192], numeric[48];
        size_t image_n = 0u, image_m = 0u, list_n = 0u;
        BasicVariableKey b = make_key('B');
        BasicVariableValue v;
        CHECK(setup(&h, 4u) == 0);
        (void)snprintf(first, sizeof(first), "A%%=%d", (int)cases[i].a);
        (void)snprintf(second, sizeof(second), "B%%=A%% MOD %u", cases[i].n);
        (void)snprintf(expected_source, sizeof(expected_source),
                       "10 %s\n20 %s\n30 PRINT B%%\n40 END\n", first, second);
        CHECK(put(&h, 10u, first) == 0);
        CHECK(put(&h, 20u, second) == 0);
        CHECK(put(&h, 30u, "PRINT B%") == 0);
        CHECK(put(&h, 40u, "END") == 0);
        CHECK(bp_export(&h.program, binary, sizeof(binary), &image_n) == BP_OK);
        CHECK(bp_init(&imported, imported_storage, sizeof(imported_storage)) == BP_OK);
        CHECK(bp_import(&imported, binary, image_n) == BP_OK);
        /* A truncated CPC program image must not be admitted as a whole. */
        CHECK(image_n >= 2u && bp_validate_image(binary, image_n - 1u) != BP_OK);
        CHECK(bp_export(&imported, rebuilt, sizeof(rebuilt), &image_m) == BP_OK);
        CHECK(image_m == image_n && memcmp(binary, rebuilt, image_n) == 0);
        CHECK(bl_list_program(&imported, listing, sizeof(listing), &list_n) == BL_OK);
        CHECK(list_n == strlen(expected_source) &&
              memcmp(listing, expected_source, list_n) == 0);
        image_m = 767u;
        CHECK(bp_export(&imported, rebuilt, 1u, &image_m) == BP_NO_SPACE);
        CHECK(image_m == 767u);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(step(&h) == 0 && equal(&h, 'A', cases[i].a) == 0);
        if (cases[i].zero) {
            /* Existing destination must be unmodified on zero-divisor retries. */
            CHECK(inject(&h, 'B', 733) == 0);
            CHECK(failure(&h, BE_DIVISION_BY_ZERO) == 0);
            CHECK(failure(&h, BE_DIVISION_BY_ZERO) == 0);
            CHECK(equal(&h, 'B', 733) == 0);
            CHECK(equal(&h, 'A', cases[i].a) == 0);
        } else {
            CHECK(step(&h) == 0 && equal(&h, 'B', cases[i].b) == 0);
            h.written = 989u;
            CHECK(be_step(&h.executor, h.output, sizeof(h.output),
                          &h.written) == BE_OK);
            (void)snprintf(numeric, sizeof(numeric), "%s%d \n",
                           cases[i].b >= 0 ? " " : "", (int)cases[i].b);
            CHECK(h.written == strlen(numeric) &&
                  memcmp(h.output, numeric, h.written) == 0);
            CHECK(step(&h) == 0);
            h.written = 78u;
            CHECK(be_step(&h.executor, h.output, sizeof(h.output), &h.written) == BE_END);
            CHECK(h.written == 78u);
        }
        CHECK(h.store.count == 2u);
        CHECK(bvs_get(&h.store, &b, &v) == BVS_OK);
    }
    return 0;
}

static int test_failure_cases(void)
{
    Harness h;
    BasicVariableKey missing = make_key('B');
    BasicVariableValue value;
    uint8_t tokens[64], before_output[64];
    size_t n;
    /* Missing destination remains missing after MOD by zero. */
    CHECK(setup(&h, 3u) == 0);
    CHECK(inject(&h, 'A', INT16_MIN) == 0);
    CHECK(put(&h, 10u, "B%=A% MOD 0") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_DIVISION_BY_ZERO) == 0);
    CHECK(failure(&h, BE_DIVISION_BY_ZERO) == 0);
    CHECK(h.store.count == 1u);
    CHECK(bvs_get(&h.store, &missing, &value) == BVS_NOT_FOUND);
    CHECK(equal(&h, 'A', INT16_MIN) == 0);
    /* Full store must refuse creation without any partial mutation. */
    CHECK(setup(&h, 1u) == 0);
    CHECK(inject(&h, 'A', 3) == 0);
    CHECK(put(&h, 10u, "B%=A% MOD 1") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_STORE_FULL) == 0);
    CHECK(h.store.count == 1u);
    /* A source that was never assigned is rejected. */
    CHECK(setup(&h, 3u) == 0);
    CHECK(put(&h, 10u, "B%=A% MOD 1") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_VARIABLE_NOT_FOUND) == 0);
    /* An imported destination of the wrong CPC explicit type is rejected.
     * No bytes or variables are committed on a type error. */
    {
        static const uint8_t wrong_destination[] = {
            0xa5,3,0,0,0xc2,0xef,2,0,0,0xc1,' ',0xfb,' ',0x0f
        };
        CHECK(setup(&h, 3u) == 0);
        CHECK(inject(&h, 'A', 8) == 0);
        CHECK(bp_put(&h.program, 10u, wrong_destination,
                     sizeof(wrong_destination)) == BP_OK);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(failure(&h, BE_BAD_SEQUENCE) == 0);
        CHECK(equal(&h, 'A', 8) == 0);
    }
    /* One statement per line, even if source accepted a colon. */
    CHECK(setup(&h, 3u) == 0);
    CHECK(inject(&h, 'A', 4) == 0);
    CHECK(put(&h, 10u, "B%=A% MOD 1:PRINT 3") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(failure(&h, BE_UNSUPPORTED) == 0);
    /* A nonsensical token stream cannot partially initialize destination. */
    {
        static const struct { uint8_t body[16]; size_t len; BEStatus status; } bad[] = {
            {{2,0,0,0xc2,0xef,2,0,0,0xc1,0xfb},10,BE_TRUNCATED},
            {{2,0,0,0xc2,0xef,2,0,0,0xc1,0xfb,0x19},11,BE_TRUNCATED},
            {{2,0,0,0xc2,0xef,2,0,0,0xc1,0xfb,0x19,9},12,BE_BAD_SEQUENCE},
            {{2,0,0,0xc2,0xef,2,0,0,0xc1,0xfb,0x1a,0,1},13,BE_BAD_SEQUENCE},
            {{2,0,0,0xc2,0xef,2,0,0,0xc1,0xfb,0x1f,0,0,0,0,0x90},16,BE_BAD_SEQUENCE},
            {{2,0,0,0xc2,0xef,2,0,0,0xc1,0xfb,0xfb,0x0f},12,BE_BAD_SEQUENCE},
            {{2,0,0,0xc2,0xef,3,0,0,0xc1,0xfb,0x0f},11,BE_BAD_SEQUENCE},
            /* Imported source is STRING, not INTEGER: fail before store mutation. */
            {{2,0,0,0xc2,0xef,3,0,0,0xc1,' ',0xfb,' ',0x0f},13,BE_BAD_SEQUENCE},
            {{2,0,0,0xc2,0xef,2,0,0,0xc1,0xef,0x0f},11,BE_BAD_SEQUENCE},
            {{2,0,0,0xc2,0xef,2,0,0,0xc1,0xfb,0x0f,0xf4,0x0f},13,BE_BAD_SEQUENCE}
        };
        size_t i;
        for (i = 0u; i < sizeof(bad)/sizeof(bad[0]); ++i) {
            CHECK(setup(&h, 3u) == 0);
            CHECK(inject(&h, 'A', 8) == 0);
            CHECK(bp_put(&h.program, 10u, bad[i].body, bad[i].len) == BP_OK);
            CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
            CHECK(failure(&h, bad[i].status) == 0);
            CHECK(h.store.count == 1u && equal(&h, 'A', 8) == 0);
        }
    }
    /* Overlap/capacity checks must fail before any state or write. */
    CHECK(setup(&h, 3u) == 0);
    CHECK(inject(&h, 'A', 9) == 0);
    CHECK(put(&h, 10u, "B%=A% MOD 3") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    memcpy(before_output, h.output, sizeof(before_output));
    n = 775u;
    CHECK(be_step(&h.executor, (uint8_t *)&h.executor, sizeof(h.executor),
                  &n) == BE_OVERLAP);
    CHECK(n == 775u && memcmp(before_output, h.output, sizeof(h.output)) == 0);
    CHECK(h.executor.cursor == 0u && h.store.count == 1u);
    CHECK(bt_tokenize((const uint8_t *)"B%=A% MOD 3", 11u,
                      tokens, sizeof(tokens), &n) == BT_OK);
    CHECK(bl_detokenize(tokens, n, tokens, sizeof(tokens), &n) == BL_OVERLAP);
    /* Full output-capacity guard on PRINT after a successful MOD. */
    CHECK(setup(&h, 3u) == 0);
    CHECK(inject(&h, 'A', 9) == 0);
    CHECK(put(&h, 10u, "B%=A% MOD 3") == 0);
    CHECK(put(&h, 20u, "PRINT B%") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(step(&h) == 0 && equal(&h, 'B', 0) == 0);
    n = 787u;
    memset(h.output, 0x75, sizeof(h.output));
    memcpy(before_output, h.output, sizeof(before_output));
    CHECK(be_step(&h.executor, h.output, 0u, &n) == BE_NO_SPACE);
    CHECK(n == 787u && memcmp(before_output, h.output, sizeof(h.output)) == 0);
    CHECK(equal(&h, 'B', 0) == 0);
    CHECK(h.executor.cursor != 0u);
    CHECK(be_step(&h.executor, h.output, sizeof(h.output), &n) == BE_OK);
    CHECK(n == 4u && memcmp(h.output, " 0 \n", 4u) == 0);
    return 0;
}

int main(void)
{
    CHECK(test_tokens_and_listing() == 0);
    CHECK(test_programs() == 0);
    CHECK(test_failure_cases() == 0);
    puts("J1.6-B INTEGER MOD / FB / atomicity tests PASS");
    return 0;
}
