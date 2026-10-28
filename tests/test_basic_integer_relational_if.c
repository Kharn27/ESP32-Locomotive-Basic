/* J1.13-B: six signed INTEGER relations, strictly autonomous IF ... THEN line. */
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_executor.h"
#include "basic_variable_binding.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); return 1; \
} } while (0)

typedef struct {
    BasicProgram program;
    uint8_t storage[1024];
    BasicVariableStore store;
    BasicVariableEntry entries[6];
    BasicExecutor executor;
    uint8_t output[96];
    size_t written;
} Harness;

static int setup(Harness *h)
{
    memset(h, 0, sizeof(*h));
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(bvs_init(&h->store, h->entries, 6u) == BVS_OK);
    return 0;
}

static int put(Harness *h, uint16_t line, const char *source)
{
    uint8_t body[128];
    size_t n = 0u;
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      body, sizeof(body), &n) == BT_OK);
    CHECK(bp_put(&h->program, line, body, n) == BP_OK);
    return 0;
}

static int variable(Harness *h, uint8_t name, int16_t number)
{
    BasicVariableKey key = {0};
    BasicVariableValue value = {0};
    key.type = (uint8_t)BVT_INTEGER;
    key.name_length = 1u;
    key.name[0] = name;
    value.type = (uint8_t)BVT_INTEGER;
    value.data.integer = number;
    CHECK(bvs_assign(&h->store, &key, &value) == BVS_OK);
    return 0;
}

static int fails(Harness *h, BEStatus expected)
{
    BasicExecutor executor = h->executor;
    BasicProgram program = h->program;
    BasicVariableStore store = h->store;
    uint8_t storage[sizeof(h->storage)];
    BasicVariableEntry entries[6];
    uint8_t output[sizeof(h->output)];
    memcpy(storage, h->storage, sizeof(storage));
    memcpy(entries, h->entries, sizeof(entries));
    memset(h->output, 0x5au, sizeof(h->output));
    memcpy(output, h->output, sizeof(output));
    h->written = 987u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output),
                  &h->written) == expected);
    CHECK(h->written == 987u);
    CHECK(memcmp(&executor, &h->executor, sizeof(executor)) == 0);
    CHECK(memcmp(&program, &h->program, sizeof(program)) == 0);
    CHECK(memcmp(&store, &h->store, sizeof(store)) == 0);
    CHECK(memcmp(storage, h->storage, sizeof(storage)) == 0);
    CHECK(memcmp(entries, h->entries, sizeof(entries)) == 0);
    CHECK(memcmp(output, h->output, sizeof(output)) == 0);
    return 0;
}

static int relation(uint8_t op, int16_t a, int16_t b)
{
    switch (op) {
    case 0xefu: return a == b;
    case 0xf2u: return a != b;
    case 0xf1u: return a < b;
    case 0xf3u: return a <= b;
    case 0xeeu: return a > b;
    case 0xf0u: return a >= b;
    default: return -1;
    }
}

static int tokens_and_listing(void)
{
    static const char *symbols[] = {"=", "<>", "<", "<=", ">", ">="};
    static const uint8_t codes[] = {0xefu, 0xf2u, 0xf1u, 0xf3u, 0xeeu, 0xf0u};
    static const char *invalid[] = {
        "IF A%!=B% THEN 40", "IF A%==B% THEN 40",
        "IF A%<<B% THEN 40", "IF A%><B% THEN 40",
        "IF A%=>B% THEN 40", "IF A%< THEN 40",
        "IF A%> THEN 40", "IF A%<= THEN 40",
        "IF A%>= THEN 40", "IF A%<> THEN 40",
        "IF A%=B! THEN 40", "IF A!=B% THEN 40",
        "IF A%=1 THEN 40", "IF 1=B% THEN 40",
        "IF A%+1>B% THEN 40", "IF A%<B% THEN PRINT 1",
        "IF A%<B% THEN 40 ELSE 20", "IF A%<B% THEN 40:END"
    };
    size_t i;
    for (i = 0u; i < 6u; ++i) {
        uint8_t tokens[96], listed[96], again[96], immutable[96];
        char source[96];
        size_t n = 0u, listed_n = 0u, again_n = 0u;
        int formatted = snprintf(source, sizeof(source),
                                 "IF A%%%sB%% THEN 40", symbols[i]);
        CHECK(formatted > 0 && (size_t)formatted < sizeof(source));
        CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                          tokens, sizeof(tokens), &n) == BT_OK);
        CHECK(n == 17u && tokens[0] == 0xa1u && tokens[2] == 0x02u &&
              tokens[6] == codes[i] && tokens[7] == 0x02u &&
              tokens[12] == 0xebu && tokens[14] == 0x1eu);
        memcpy(immutable, tokens, n);
        CHECK(bl_detokenize(tokens, n, listed, sizeof(listed), &listed_n)
              == BL_OK);
        CHECK(listed_n == strlen(source) &&
              memcmp(listed, source, listed_n) == 0);
        CHECK(bt_tokenize(listed, listed_n, again, sizeof(again),
                          &again_n) == BT_OK);
        CHECK(again_n == n && memcmp(again, tokens, n) == 0);
        /* A cache containing spaces or comparator tokens is not syntax. */
        tokens[3] = 0x20u;
        tokens[4] = 0xefu;
        tokens[8] = 0xf1u;
        tokens[9] = 0x20u;
        CHECK(bl_detokenize(tokens, n, listed, sizeof(listed), &listed_n)
              == BL_OK);
        CHECK(listed_n == strlen(source) &&
              memcmp(listed, source, listed_n) == 0);
        memcpy(tokens, immutable, n);
        listed_n = 432u;
        memset(listed, 0x44, sizeof(listed));
        CHECK(bl_detokenize(tokens, n, listed, strlen(source)-1u,
                            &listed_n) == BL_NO_SPACE);
        CHECK(listed_n == 432u && listed[0] == 0x44u &&
              listed[sizeof(listed)-1u] == 0x44u);
        CHECK(memcmp(tokens, immutable, n) == 0);
    }
    for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        uint8_t body[96], before[96];
        size_t written = 777u;
        memset(body, 0x66, sizeof(body));
        memcpy(before, body, sizeof(body));
        CHECK(bt_tokenize((const uint8_t *)invalid[i], strlen(invalid[i]),
                          body, sizeof(body), &written) != BT_OK);
        CHECK(written == 777u && memcmp(before, body, sizeof(body)) == 0);
    }
    return 0;
}

static int all_signed_branches(void)
{
    static const char *symbols[] = {"=", "<>", "<", "<=", ">", ">="};
    static const uint8_t codes[] = {0xefu, 0xf2u, 0xf1u, 0xf3u, 0xeeu, 0xf0u};
    static const int16_t pairs[][2] = {
        {0,0}, {1,0}, {0,1}, {-1,1}, {1,-1},
        {INT16_MIN,INT16_MAX}, {INT16_MAX,INT16_MIN},
        {INT16_MIN,INT16_MIN}, {INT16_MAX,INT16_MAX}
    };
    size_t i, j;
    for (i = 0u; i < 6u; ++i) {
        for (j = 0u; j < sizeof(pairs)/sizeof(pairs[0]); ++j) {
            Harness h;
            BasicProgramLine next;
            char expression[64];
            int taken = relation(codes[i], pairs[j][0], pairs[j][1]);
            CHECK(taken == 0 || taken == 1);
            CHECK(setup(&h) == 0);
            CHECK(snprintf(expression, sizeof(expression),
                           "IF A%%%sB%% THEN 40", symbols[i]) > 0);
            CHECK(put(&h, 10u, expression) == 0);
            CHECK(put(&h, 20u, "PRINT 42") == 0);
            CHECK(put(&h, 30u, "END") == 0);
            CHECK(put(&h, 40u, "PRINT 81") == 0);
            CHECK(put(&h, 50u, "END") == 0);
            CHECK(variable(&h, (uint8_t)'A', pairs[j][0]) == 0);
            CHECK(variable(&h, (uint8_t)'B', pairs[j][1]) == 0);
            CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
            CHECK(bp_find(&h.program, taken ? 40u : 20u, &next) == BP_OK);
            h.written = 101u;
            CHECK(be_step(&h.executor, h.output, 0u, &h.written) == BE_OK);
            CHECK(h.written == 0u && h.executor.cursor == next.offset);
            CHECK(be_step(&h.executor, h.output, sizeof(h.output), &h.written) == BE_OK);
            CHECK(h.written == 3u &&
                  memcmp(h.output, taken ? "81\n" : "42\n", 3u) == 0);
        }
    }
    return 0;
}

static int imported_and_negative(void)
{
    uint8_t body[80], listed[128], retoken[128];
    size_t n = 0u, listed_n = 0u, again_n = 0u;
    Harness h;
    BasicProgramLine target;
    const char *source = "IF A%<B% THEN 90";
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      body, sizeof(body), &n) == BT_OK);
    CHECK(n == 17u);
    CHECK(setup(&h) == 0);
    CHECK(bp_put(&h.program, 10u, body, n) == BP_OK);
    CHECK(put(&h, 20u, "END") == 0);
    CHECK(variable(&h, (uint8_t)'A', 0) == 0);
    CHECK(variable(&h, (uint8_t)'B', 1) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_MISSING_TARGET) == 0);
    CHECK(variable(&h, (uint8_t)'B', -1) == 0);
    CHECK(be_step(&h.executor, h.output, 0u, &h.written) == BE_OK);
    CHECK(bp_find(&h.program, 20u, &target) == BP_OK);
    CHECK(h.executor.cursor == target.offset);
    CHECK(setup(&h) == 0);
    CHECK(bp_put(&h.program, 10u, body, n) == BP_OK);
    CHECK(variable(&h, (uint8_t)'A', 1) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_VARIABLE_NOT_FOUND) == 0);
    CHECK(variable(&h, (uint8_t)'B', 2) == 0);
    CHECK(be_init(&h.executor, &h.program) == BE_OK);
    CHECK(fails(&h, BE_UNSUPPORTED) == 0);
    /* Imported CPC references retain cache contents, including opcodes. */
    body[3] = 0x20u; body[4] = 0xf2u;
    body[8] = 0xefu; body[9] = 0x20u;
    CHECK(bl_detokenize(body, n, listed, sizeof(listed), &listed_n) == BL_OK);
    CHECK(listed_n == strlen(source) &&
          memcmp(listed, source, listed_n) == 0);
    CHECK(bt_tokenize(listed, listed_n, retoken, sizeof(retoken),
                      &again_n) == BT_OK);
    CHECK(again_n == n);
    /* Imported CPC token stream may omit ALL lexical separators.
     * The two BVR caches must never be treated as spaces or tokens. */
    {
        uint8_t compact[80], image[1024];
        size_t compact_n = 0u, image_n = 0u, k;
        for (k = 0u; k < n; ++k) {
            if (k != 1u && k != 11u && k != 13u)
                compact[compact_n++] = body[k];
        }
        CHECK(bl_detokenize(compact, compact_n, listed,
                            sizeof(listed), &listed_n) == BL_OK);
        CHECK(listed_n == strlen(source) &&
              memcmp(listed, source, listed_n) == 0);
        CHECK(setup(&h) == 0);
        CHECK(bp_put(&h.program, 10u, compact, compact_n) == BP_OK);
        CHECK(put(&h, 20u, "END") == 0);
        CHECK(bp_export(&h.program, image, sizeof(image), &image_n) == BP_OK);
        CHECK(bp_init(&h.program, h.storage, sizeof(h.storage)) == BP_OK);
        CHECK(bp_import(&h.program, image, image_n) == BP_OK);
        CHECK(variable(&h, (uint8_t)'A', 0) == 0);
        CHECK(variable(&h, (uint8_t)'B', 1) == 0);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        CHECK(fails(&h, BE_MISSING_TARGET) == 0);
        CHECK(variable(&h, (uint8_t)'B', -1) == 0);
        CHECK(be_step(&h.executor, h.output, 0u, &h.written) == BE_OK);
        CHECK(bp_find(&h.program, 20u, &target) == BP_OK);
        CHECK(h.executor.cursor == target.offset);
    }
    CHECK(setup(&h) == 0);
    CHECK(bp_put(&h.program, 10u, body, n) == BP_OK);
    CHECK(put(&h, 20u, "END") == 0);
    CHECK(variable(&h, (uint8_t)'A', 0) == 0);
    CHECK(variable(&h, (uint8_t)'B', 1) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_MISSING_TARGET) == 0);
    /* Each malformed imported token sequence must fail without mutation. */
    {
        static const size_t positions[] = {6u,7u,10u,12u,14u};
        static const uint8_t mutations[] = {0xfau,0x03u,0x00u,0xa0u,0x19u};
        size_t i;
        for (i = 0u; i < sizeof(positions)/sizeof(positions[0]); ++i) {
            uint8_t damaged[80];
            memcpy(damaged, body, n);
            damaged[positions[i]] = mutations[i];
            CHECK(setup(&h) == 0);
            CHECK(bp_put(&h.program, 10u, damaged, n) == BP_OK);
            CHECK(variable(&h, (uint8_t)'A', 0) == 0);
            CHECK(variable(&h, (uint8_t)'B', 1) == 0);
            CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
            CHECK(fails(&h, BE_BAD_SEQUENCE) == 0);
        }
    }
    CHECK(setup(&h) == 0);
    CHECK(bp_put(&h.program, 10u, body, 9u) == BP_OK);
    CHECK(variable(&h, (uint8_t)'A', 0) == 0);
    CHECK(variable(&h, (uint8_t)'B', 1) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_TRUNCATED) == 0);
    return 0;
}

int main(void)
{
    CHECK(tokens_and_listing() == 0);
    CHECK(all_signed_branches() == 0);
    CHECK(imported_and_negative() == 0);
    puts("J1.13-B six relations: tokens/LIST/RUN signed/atomic errors PASS");
    return 0;
}
