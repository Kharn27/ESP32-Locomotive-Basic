/* J1.2-B: ROM-backed CPC 1A vectors, bounded LIST and native INTEGER RUN. */
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include "basic_variable_binding.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

typedef struct {
    BasicProgram program;
    uint8_t storage[1024];
    BasicVariableStore store;
    BasicVariableEntry entries[4];
    BasicSessionRuntime runtime;
    uint8_t scratch[256];
    uint8_t output[256];
    size_t written;
} Harness;

static const struct {
    const char *source;
    uint8_t bytes[10];
    size_t length;
    int16_t value;
    const char *printed;
} cases[] = {
    {"B%=256",   {2,0,0,0xc2,0xef,0x1a,0x00,0x01}, 8u, 256, " 256 \n"},
    {"B%=-256",  {2,0,0,0xc2,0xef,0xf5,0x1a,0x00,0x01}, 9u, -256, "-256 \n"},
    {"B%=32767", {2,0,0,0xc2,0xef,0x1a,0xff,0x7f}, 8u, 32767, " 32767 \n"},
    {"B%=255",   {2,0,0,0xc2,0xef,0x19,0xff}, 7u, 255, " 255 \n"},
    {"B%=-255",  {2,0,0,0xc2,0xef,0xf5,0x19,0xff}, 8u, -255, "-255 \n"},
    {"B%=9",     {2,0,0,0xc2,0xef,0x17}, 6u, 9, " 9 \n"},
};

static int init(Harness *h)
{
    memset(h, 0, sizeof(*h));
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(bvs_init(&h->store, h->entries, 4u) == BVS_OK);
    CHECK(bsr_init_with_store(&h->runtime, &h->program, &h->store).status == BSR_OK);
    return 0;
}

static int submit(Harness *h, const char *source)
{
    BSRResult r = bsr_submit(&h->runtime, (const uint8_t *)source,
                            strlen(source), h->scratch, sizeof(h->scratch),
                            h->output, sizeof(h->output), &h->written);
    CHECK(r.status == BSR_OK);
    return 0;
}

static int test_vectors(void)
{
    size_t i;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        uint8_t bytes[64], listed[64], retokens[64];
        size_t n = 99u, m = 99u, second = 99u;
        const size_t source_length = strlen(cases[i].source);
        memset(bytes, 0xcbu, sizeof(bytes));
        CHECK(bt_tokenize((const uint8_t *)cases[i].source, source_length,
                          bytes, cases[i].length-1u, &n) == BT_NO_SPACE);
        CHECK(n == 99u && bytes[0] == 0xcbu);
        CHECK(bt_tokenize((const uint8_t *)cases[i].source, source_length,
                          bytes, cases[i].length, &n) == BT_OK);
        CHECK(n == cases[i].length &&
              memcmp(bytes, cases[i].bytes, n) == 0);
        memset(listed, 0xabu, sizeof(listed));
        CHECK(bl_detokenize(bytes, n, listed, source_length - 1u, &m) ==
              BL_NO_SPACE);
        CHECK(m == 99u && listed[0] == 0xabu);
        CHECK(bl_detokenize(bytes, n, listed, source_length, &m) == BL_OK);
        CHECK(m == source_length &&
              memcmp(listed, cases[i].source, m) == 0);
        CHECK(bt_tokenize(listed, m, retokens, sizeof(retokens), &second) == BT_OK);
        CHECK(second == n && memcmp(retokens, bytes, n) == 0);
    }
    return 0;
}

static int test_end_to_end(void)
{
    size_t i;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        Harness h;
        BasicVariableKey key;
        BasicVariableValue value;
        char command[72];
        char expected_list[256];
        size_t n;
        CHECK(init(&h) == 0);
        CHECK(snprintf(command, sizeof(command), "10 %s", cases[i].source) > 0);
        CHECK(submit(&h, command) == 0);
        CHECK(submit(&h, "20 PRINT B%") == 0);
        CHECK(submit(&h, "30 END") == 0);
        CHECK(submit(&h, "LIST") == 0);
        CHECK(snprintf(expected_list, sizeof(expected_list),
                       "10 %s\n20 PRINT B%%\n30 END\n",
                       cases[i].source) > 0);
        CHECK(h.written == strlen(expected_list) &&
              memcmp(h.output, expected_list, h.written) == 0);
        CHECK(submit(&h, "RUN") == 0 && h.store.count == 0u);
        h.written = 123u;
        CHECK(bsr_step(&h.runtime, h.output, 0u, &h.written).status == BSR_OK);
        CHECK(h.written == 0u && h.store.count == 1u);
        memset(&key, 0, sizeof(key));
        key.type = (uint8_t)BVT_INTEGER;
        key.name_length = 1u;
        key.name[0] = (uint8_t)'B';
        CHECK(bvs_get(&h.store, &key, &value) == BVS_OK);
        CHECK(value.data.integer == cases[i].value);
        n = strlen(cases[i].printed);
        memset(h.output, 0xa5, sizeof(h.output));
        h.written = 333u;
        CHECK(bsr_step(&h.runtime, h.output, n - 1u, &h.written).status ==
              BSR_EXECUTOR_ERROR);
        CHECK(h.written == 333u && h.output[0] == 0xa5u &&
              h.store.count == 1u);
        CHECK(bsr_step(&h.runtime, h.output, n, &h.written).status == BSR_OK);
        CHECK(h.written == n && memcmp(h.output, cases[i].printed, n) == 0);
        CHECK(bsr_step(&h.runtime, h.output, sizeof(h.output), &h.written).status == BSR_OK);
        CHECK(bsr_step(&h.runtime, h.output, sizeof(h.output), &h.written).status == BSR_END);
        CHECK(submit(&h, "RUN") == 0 && h.store.count == 0u);
        CHECK(submit(&h, "NEW") == 0 && h.store.count == 0u &&
              h.program.size == 2u);
    }
    return 0;
}

static int test_reject_tokenizer(void)
{
    static const struct {const char *source; BTStatus reason;} bad[] = {
        {"B%=32768", BT_NUMBER_OUT_OF_RANGE},
        {"B%=-32768", BT_NUMBER_OUT_OF_RANGE},
        {"B%=65535", BT_NUMBER_OUT_OF_RANGE},
        {"B%=-65535", BT_NUMBER_OUT_OF_RANGE},
        {"B%=B%+256", BT_NUMBER_OUT_OF_RANGE},
        {"B%=-B%", BT_UNSUPPORTED_CONSTRUCT},
        {"B%=1-256", BT_UNSUPPORTED_CONSTRUCT},
    };
    uint8_t buffer[64];
    size_t i;
    memset(buffer, 0x6d, sizeof(buffer));
    for (i = 0u; i < sizeof(bad)/sizeof(bad[0]); ++i) {
        size_t written = 987u, j;
        CHECK(bt_tokenize((const uint8_t *)bad[i].source,
                          strlen(bad[i].source), buffer, sizeof(buffer),
                          &written) == bad[i].reason);
        CHECK(written == 987u);
        for (j = 0u; j < sizeof(buffer); ++j) CHECK(buffer[j] == 0x6du);
    }
    return 0;
}

static int test_malformed(void)
{
    /* Tokenized assignment B%=..; no raw source text or CPC oracle forged. */
    static const uint8_t zero_payload[] = {2,0,0,0xc2,0xef,0x1a};
    static const uint8_t one_payload[]  = {2,0,0,0xc2,0xef,0x1a,0};
    static const uint8_t small_0[]      = {2,0,0,0xc2,0xef,0x1a,0,0};
    static const uint8_t small_255[]    = {2,0,0,0xc2,0xef,0x1a,255,0};
    static const uint8_t over_32767[]   = {2,0,0,0xc2,0xef,0x1a,0,128};
    static const uint8_t over_65535[]   = {2,0,0,0xc2,0xef,0x1a,255,255};
    static const uint8_t neg_over[]     = {2,0,0,0xc2,0xef,0xf5,0x1a,0,128};
    static const uint8_t neg_trunc[]    = {2,0,0,0xc2,0xef,0xf5,0x1a,0};
    static const uint8_t neg_var[]      = {2,0,0,0xc2,0xef,0xf5,0x02,0,0,0xc2};
    static const uint8_t *const bodies[] = {
        zero_payload, one_payload, small_0, small_255, over_32767,
        over_65535, neg_over, neg_trunc, neg_var
    };
    static const size_t lengths[] = {
        sizeof(zero_payload), sizeof(one_payload), sizeof(small_0),
        sizeof(small_255), sizeof(over_32767), sizeof(over_65535),
        sizeof(neg_over), sizeof(neg_trunc), sizeof(neg_var)
    };
    static const BLStatus listing_errors[] = {
        BL_TRUNCATED, BL_TRUNCATED, BL_BAD_SEQUENCE, BL_BAD_SEQUENCE,
        BL_BAD_SEQUENCE, BL_BAD_SEQUENCE, BL_BAD_SEQUENCE, BL_TRUNCATED,
        BL_BAD_SEQUENCE
    };
    static const BEStatus runtime_errors[] = {
        BE_TRUNCATED, BE_TRUNCATED, BE_BAD_SEQUENCE, BE_BAD_SEQUENCE,
        BE_INTEGER_OVERFLOW, BE_INTEGER_OVERFLOW, BE_INTEGER_OVERFLOW,
        BE_TRUNCATED, BE_BAD_SEQUENCE
    };
    size_t i;
    for (i = 0u; i < sizeof(bodies)/sizeof(bodies[0]); ++i) {
        Harness h;
        BasicExecutor exec;
        BasicVariableEntry before[4];
        uint8_t output[96];
        size_t written = 918u, j, original_cursor;
        CHECK(init(&h) == 0);
        CHECK(bp_put(&h.program, 10u, bodies[i], lengths[i]) == BP_OK);
        CHECK(be_init_with_store(&exec, &h.program, &h.store) == BE_OK);
        original_cursor = exec.cursor;
        memcpy(before, h.entries, sizeof(before));
        memset(output, 0xacu, sizeof(output));
        CHECK(bl_detokenize(bodies[i], lengths[i], output,
                            sizeof(output), &written) == listing_errors[i]);
        CHECK(written == 918u);
        for (j=0u; j<sizeof(output); ++j) CHECK(output[j] == 0xacu);
        CHECK(be_step(&exec, output, sizeof(output), &written) == runtime_errors[i]);
        CHECK(written == 918u && exec.cursor == original_cursor &&
              h.store.count == 0u &&
              memcmp(before, h.entries, sizeof(before)) == 0);
        for (j=0u; j<sizeof(output); ++j) CHECK(output[j] == 0xacu);
    }
    return 0;
}


/* C1: imported token streams must not cause LIST to advertise expressions
 * rejected by both the native tokenizer and the executor. Unlike the
 * preceding vectors, these 1A-addend images are NOT created by C99. */
static int test_imported_integer16_addend_rejection(void)
{
    static const uint8_t implicit[] = {
        2u,0u,0u,0xc2u,0xefu,2u,0u,0u,0xc2u,0xf4u,0x1au,0u,1u
    };
    static const uint8_t explicit_let[] = {
        0xa5u,' ',2u,0u,0u,0xc2u,0xefu,2u,0u,0u,0xc2u,
        0xf4u,0x1au,0u,1u
    };
    static const struct {
        const uint8_t *bytes;
        size_t length;
        const char *source;
    } bad[] = {
        {implicit, sizeof(implicit), "B%=B%+256"},
        {explicit_let, sizeof(explicit_let), "LET B%=B%+256"}
    };
    size_t i;
    for (i = 0u; i < sizeof(bad) / sizeof(bad[0]); ++i) {
        Harness h;
        BasicExecutor executor;
        BasicProgramLine imported_line;
        BasicVariableKey key;
        BasicVariableValue value = {0};
        BasicVariableEntry entries_before[4];
        uint8_t token_buf[96], listed[128], before_list[128];
        uint8_t source_buf[96], before_source[96];
        uint8_t storage_before[1024];
        size_t tokens = 555u, written = 777u, j, cursor_before;

        CHECK(init(&h) == 0);
        /* Preceding valid line makes program LIST partial output observable. */
        CHECK(bt_tokenize((const uint8_t *)"PRINT \"PREFIX\"",
                          strlen("PRINT \"PREFIX\""), token_buf,
                          sizeof(token_buf), &tokens) == BT_OK);
        CHECK(bp_put(&h.program, 10u, token_buf, tokens) == BP_OK);
        CHECK(bp_put(&h.program, 20u, bad[i].bytes, bad[i].length) == BP_OK);
        memcpy(storage_before, h.storage, sizeof(storage_before));

        memset(listed, 0x6cu, sizeof(listed));
        memcpy(before_list, listed, sizeof(before_list));
        CHECK(bl_detokenize(bad[i].bytes, bad[i].length, listed,
                            sizeof(listed), &written) == BL_BAD_SEQUENCE);
        CHECK(written == 777u &&
              memcmp(listed, before_list, sizeof(listed)) == 0);
        CHECK(bl_list_program(&h.program, listed, sizeof(listed),
                              &written) == BL_BAD_SEQUENCE);
        CHECK(written == 777u &&
              memcmp(listed, before_list, sizeof(listed)) == 0);
        /* Full session LIST must reject as well, before publishing a prefix. */
        h.written = 888u;
        memset(h.output, 0x73, sizeof(h.output));
        {
            BSRResult result = bsr_submit(
                &h.runtime, (const uint8_t *)"LIST", 4u,
                h.scratch, sizeof(h.scratch), h.output, sizeof(h.output),
                &h.written);
            CHECK(result.status == BSR_SESSION_ERROR &&
                  result.session.listing_status == BL_BAD_SEQUENCE);
        }
        CHECK(h.written == 888u);
        for (j = 0u; j < sizeof(h.output); ++j) {
            CHECK(h.output[j] == 0x73u);
        }

        memset(source_buf, 0xb9, sizeof(source_buf));
        memcpy(before_source, source_buf, sizeof(before_source));
        CHECK(bt_tokenize((const uint8_t *)bad[i].source,
                          strlen(bad[i].source), source_buf,
                          sizeof(source_buf), &written) ==
              BT_NUMBER_OUT_OF_RANGE);
        CHECK(written == 777u &&
              memcmp(source_buf, before_source, sizeof(source_buf)) == 0);

        /* Ensure the reference B% really resolves before evaluation fails. */
        memset(&key, 0, sizeof(key));
        key.type = (uint8_t)BVT_INTEGER;
        key.name_length = 1u;
        key.name[0] = (uint8_t)'B';
        value.type = (uint8_t)BVT_INTEGER;
        value.data.integer = 42;
        CHECK(bvs_assign(&h.store, &key, &value) == BVS_OK);
        memcpy(entries_before, h.entries, sizeof(entries_before));
        CHECK(bp_find(&h.program, 20u, &imported_line) == BP_OK);
        CHECK(be_init_with_store(&executor, &h.program, &h.store) == BE_OK);
        executor.cursor = imported_line.offset;
        cursor_before = executor.cursor;
        CHECK(be_step(&executor, listed, sizeof(listed), &written) ==
              BE_BAD_SEQUENCE);
        CHECK(executor.cursor == cursor_before &&
              written == 777u && h.store.count == 1u &&
              memcmp(entries_before, h.entries, sizeof(entries_before)) == 0 &&
              memcmp(listed, before_list, sizeof(listed)) == 0 &&
              memcmp(storage_before, h.storage, sizeof(storage_before)) == 0);
        CHECK(bvs_get(&h.store, &key, &value) == BVS_OK &&
              value.data.integer == 42);
    }
    return 0;
}

/* The accepted old addition and direct 16-bit forms remain reversible. */
static int test_integer16_context_roundtrips(void)
{
    static const char *const inputs[] = {
        "B%=B%+255", "LET B%=B%+255", "B%=256", "B%=-256",
        "B%=32767", "B%=255", "B%=-255"
    };
    size_t i;
    for (i = 0u; i < sizeof(inputs) / sizeof(inputs[0]); ++i) {
        uint8_t tokens[96], listed[96], repeated[96];
        size_t n = 0u, m = 0u, r = 0u;
        CHECK(bt_tokenize((const uint8_t *)inputs[i], strlen(inputs[i]),
                          tokens, sizeof(tokens), &n) == BT_OK);
        CHECK(bl_detokenize(tokens, n, listed, sizeof(listed), &m) == BL_OK);
        CHECK(m == strlen(inputs[i]) &&
              memcmp(listed, inputs[i], m) == 0);
        CHECK(bt_tokenize(listed, m, repeated, sizeof(repeated), &r) == BT_OK);
        CHECK(r == n && memcmp(repeated, tokens, n) == 0);
    }
    /* Addition with 255 still runs; no widening to a 1A addend. */
    {
        Harness h;
        BSRResult result;
        CHECK(init(&h) == 0);
        CHECK(submit(&h, "10 B%=0") == 0);
        CHECK(submit(&h, "20 B%=B%+255") == 0);
        CHECK(submit(&h, "30 PRINT B%") == 0);
        CHECK(submit(&h, "40 END") == 0);
        CHECK(submit(&h, "RUN") == 0);
        result = bsr_step(&h.runtime, h.output, sizeof(h.output), &h.written);
        CHECK(result.status == BSR_OK && h.written == 0u);
        result = bsr_step(&h.runtime, h.output, sizeof(h.output), &h.written);
        CHECK(result.status == BSR_OK && h.written == 0u);
        result = bsr_step(&h.runtime, h.output, sizeof(h.output), &h.written);
        CHECK(result.status == BSR_OK && h.written == 6u &&
              memcmp(h.output, " 255 \n", 6u) == 0);
        CHECK(bsr_step(&h.runtime, h.output, sizeof(h.output),
                       &h.written).status == BSR_OK);
        CHECK(bsr_step(&h.runtime, h.output, sizeof(h.output),
                       &h.written).status == BSR_END);
    }
    return 0;
}

int main(void)
{
    CHECK(test_vectors() == 0);
    CHECK(test_end_to_end() == 0);
    CHECK(test_reject_tokenizer() == 0);
    CHECK(test_malformed() == 0);
    CHECK(test_imported_integer16_addend_rejection() == 0);
    CHECK(test_integer16_context_roundtrips() == 0);
    puts("J1.2-B INTEGER16: vector/list/run/capacity/atomicity PASS");
    return 0;
}
