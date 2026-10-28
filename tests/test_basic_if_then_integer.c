/* J1.10-B: autonomous CPC IF INTEGER THEN line, atomic native transitions. */
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_executor.h"
#include "basic_variable_binding.h"
#include "basic_session_runtime.h"
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
    uint8_t output[128];
    size_t written;
} Harness;

static int setup(Harness *h)
{
    memset(h, 0, sizeof(*h));
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(bvs_init(&h->store, h->entries, 6u) == BVS_OK);
    return 0;
}

static int put(Harness *h, uint16_t number, const char *source)
{
    uint8_t body[128];
    size_t n = 0u;
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      body, sizeof(body), &n) == BT_OK);
    CHECK(bp_put(&h->program, number, body, n) == BP_OK);
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

/* Every failing be_step must preserve the entire output, descriptors,
 * line storage and live store entries, not merely the cursor. */
static int fails(Harness *h, BEStatus expected)
{
    BasicProgram program = h->program;
    BasicExecutor executor = h->executor;
    BasicVariableStore store = h->store;
    uint8_t storage[sizeof(h->storage)];
    BasicVariableEntry entries[6];
    uint8_t output[sizeof(h->output)];
    memcpy(storage, h->storage, sizeof(storage));
    memcpy(entries, h->entries, sizeof(entries));
    memset(h->output, 0x6du, sizeof(h->output));
    memcpy(output, h->output, sizeof(output));
    h->written = 998u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output),
                  &h->written) == expected);
    CHECK(h->written == 998u);
    CHECK(memcmp(&program, &h->program, sizeof(program)) == 0);
    CHECK(memcmp(&executor, &h->executor, sizeof(executor)) == 0);
    CHECK(memcmp(&store, &h->store, sizeof(store)) == 0);
    CHECK(memcmp(storage, h->storage, sizeof(storage)) == 0);
    CHECK(memcmp(entries, h->entries, sizeof(entries)) == 0);
    CHECK(memcmp(output, h->output, sizeof(output)) == 0);
    return 0;
}

static int token_listing(void)
{
    static const uint8_t original[] = {
        0xa1u,0x20u,0x02u,0x00u,0x00u,0xc1u,0x20u,0xebu,
        0x20u,0x1eu,0x3cu,0x00u
    };
    static const char *invalid[] = {
        "IF", "IF A%", "IF A% THEN", "IF A% THEN GOTO 60",
        "IF A% THEN PRINT 1", "IF A% THEN 60 ELSE 40",
        "IF A% THEN 60:PRINT 1", "PRINT 1:IF A% THEN 60",
        "IF A%=1 THEN 60", "IF 1 THEN 60", "IF A! THEN 60",
        "IF A$ THEN 60", "IF A%+B% THEN 60",
        "IF A% THEN 0", "IF A% THEN 65536",
        "IF A% THEN 60XYZ", "IF A%% THEN 60",
        "IF A% THEN 60 'comment", "IF A% THEN 60:END",
        "IF A% THEN -60", "IF A%THEN60"
    };
    size_t i, n = 0u, listed = 0u, again_n = 0u;
    uint8_t tokens[128], text[128], again[128], before[128];
    const char *source = "IF A% THEN 60";
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      tokens, sizeof(tokens), &n) == BT_OK);
    CHECK(n == sizeof(original) && memcmp(tokens, original, n) == 0);
    CHECK(bl_detokenize(tokens, n, text, sizeof(text), &listed) == BL_OK);
    CHECK(listed == strlen(source) && memcmp(text, source, listed) == 0);
    CHECK(bt_tokenize(text, listed, again, sizeof(again), &again_n) == BT_OK);
    CHECK(again_n == n && memcmp(tokens, again, n) == 0);
    /* Cache 20 EF is legal opaque CPC data, not lexical space/token. */
    tokens[3] = 0x20u;
    tokens[4] = 0xefu;
    CHECK(bl_detokenize(tokens, n, text, sizeof(text), &listed) == BL_OK);
    CHECK(listed == strlen(source) && memcmp(text, source, listed) == 0);
    tokens[3] = 0x00u;
    tokens[4] = 0x00u;
    for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        memset(tokens, 0x55, sizeof(tokens));
        memcpy(before, tokens, sizeof(before));
        n = 999u;
        CHECK(bt_tokenize((const uint8_t *)invalid[i], strlen(invalid[i]),
                          tokens, sizeof(tokens), &n) != BT_OK);
        CHECK(n == 999u && memcmp(tokens, before, sizeof(before)) == 0);
    }
    n = 654u;
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      tokens, 0u, &n) == BT_NO_SPACE);
    CHECK(n == 654u);
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      tokens, sizeof(tokens), (size_t *)(void *)tokens)
          == BT_INVALID_ARGUMENT);
    {
        uint8_t corrupt[] = {
            0xa1u,0x20u,0x02u,0x00u,0x00u,0xc1u,0x20u,
            0xebu,0x20u,0x1eu,0x3cu,0x00u
        };
        corrupt[7] = 0xa0u;
        CHECK(bl_detokenize(corrupt, sizeof(corrupt), text, sizeof(text),
                            &listed) == BL_BAD_SEQUENCE);
        corrupt[7] = 0xebu;
        CHECK(bl_detokenize(corrupt, sizeof(corrupt)-1u, text,
                            sizeof(text), &listed) == BL_TRUNCATED);
    }
    return 0;
}

static int branching(void)
{
    static const int16_t values[] = {0,1,-1,INT16_MIN,INT16_MAX};
    size_t i;
    for (i = 0u; i < sizeof(values)/sizeof(values[0]); ++i) {
        Harness h;
        BasicProgramLine next;
        CHECK(setup(&h) == 0);
        CHECK(put(&h, 20u, "IF A% THEN 60") == 0);
        CHECK(put(&h, 30u, "PRINT 30") == 0);
        CHECK(put(&h, 40u, "END") == 0);
        CHECK(put(&h, 60u, "PRINT 60") == 0);
        CHECK(put(&h, 70u, "END") == 0);
        CHECK(variable(&h, (uint8_t)'A', values[i]) == 0);
        CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
        memset(h.output, 0xbbu, sizeof(h.output));
        h.written = 34u;
        CHECK(be_step(&h.executor, h.output, 0u, &h.written) == BE_OK);
        CHECK(h.written == 0u && h.output[0] == 0xbbu);
        CHECK(bp_find(&h.program, values[i] == 0 ? 30u : 60u, &next) == BP_OK);
        CHECK(h.executor.cursor == next.offset);
        CHECK(be_step(&h.executor, h.output, sizeof(h.output),
                      &h.written) == BE_OK);
        CHECK(h.written == 3u);
        CHECK(memcmp(h.output, values[i] == 0 ? "30\n" : "60\n", 3u) == 0);
        CHECK(be_step(&h.executor, h.output, sizeof(h.output),
                      &h.written) == BE_OK); /* END */
        CHECK(fails(&h, BE_END) == 0);
    }
    return 0;
}

static int missing_and_malformed(void)
{
    Harness h;
    uint8_t data[] = {
        0xa1u,0x20u,0x02u,0x00u,0x00u,0xc1u,0x20u,
        0xebu,0x20u,0x1eu,0x5au,0x00u
    };
    CHECK(setup(&h) == 0);
    CHECK(put(&h, 20u, "IF A% THEN 90") == 0);
    CHECK(put(&h, 30u, "END") == 0);
    CHECK(variable(&h, (uint8_t)'A', 1) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_MISSING_TARGET) == 0);
    CHECK(variable(&h, (uint8_t)'A', 0) == 0);
    h.written = 888u;
    CHECK(be_step(&h.executor, h.output, 0u, &h.written) == BE_OK);
    CHECK(h.written == 0u);
    CHECK(be_step(&h.executor, h.output, 0u, &h.written) == BE_OK);
    CHECK(fails(&h, BE_END) == 0);

    CHECK(setup(&h) == 0);
    CHECK(put(&h, 20u, "IF A% THEN 90") == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_VARIABLE_NOT_FOUND) == 0);
    CHECK(be_init(&h.executor, &h.program) == BE_OK);
    CHECK(fails(&h, BE_UNSUPPORTED) == 0);

    /* Invalid imported token sequences are never fixed in place. */
    CHECK(setup(&h) == 0);
    data[5] = 0xc1u;
    CHECK(bp_put(&h.program, 20u, data, sizeof(data)-2u) == BP_OK);
    CHECK(variable(&h, (uint8_t)'A', 1) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_TRUNCATED) == 0);

    CHECK(setup(&h) == 0);
    data[7] = 0xa0u; /* bad THEN */
    CHECK(bp_put(&h.program, 20u, data, sizeof(data)) == BP_OK);
    CHECK(variable(&h, (uint8_t)'A', 1) == 0);
    CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
    CHECK(fails(&h, BE_BAD_SEQUENCE) == 0);
    CHECK(be_step(&h.executor, (uint8_t *)(void *)&h.executor,
                  sizeof(h.executor), &h.written) == BE_OVERLAP);
    return 0;
}

static int console_runtime(void)
{
    Harness h;
    BasicSessionRuntime runtime;
    uint8_t temp[160];
    uint8_t output[128];
    size_t written = 0u;
    BSRResult r;
    static const char *lines[] = {
        "10 A%=1", "20 IF A% THEN 40", "30 PRINT 30",
        "40 PRINT 40", "50 END"
    };
    size_t i;
    CHECK(setup(&h) == 0);
    CHECK(bsr_init_with_store(&runtime, &h.program, &h.store).status == BSR_OK);
    for (i = 0u; i < sizeof(lines)/sizeof(lines[0]); ++i) {
        r = bsr_submit(&runtime, (const uint8_t *)lines[i], strlen(lines[i]),
                       temp, sizeof(temp), output, sizeof(output), &written);
        CHECK(r.status == BSR_OK);
    }
    r = bsr_submit(&runtime, (const uint8_t *)"RUN", 3u,
                   temp, sizeof(temp), output, sizeof(output), &written);
    CHECK(r.status == BSR_OK);
    CHECK(bsr_step(&runtime, output, sizeof(output), &written).status == BSR_OK);
    CHECK(written == 0u);
    CHECK(bsr_step(&runtime, output, sizeof(output), &written).status == BSR_OK);
    CHECK(written == 0u);
    CHECK(bsr_step(&runtime, output, sizeof(output), &written).status == BSR_OK);
    CHECK(written == 3u && memcmp(output, "40\n", 3u) == 0);
    CHECK(bsr_step(&runtime, output, sizeof(output), &written).status == BSR_OK);
    CHECK(bsr_step(&runtime, output, sizeof(output), &written).status == BSR_END);
    return 0;
}


/* J1.10-B-C1 regression: imports can omit ANY of the three lexical
 * separators even though their A1/BVR/EB/1E token stream is executable.
 * LIST inserts only the missing ones; noncanonical imported bytes need
 * not equal re-tokenized canonical bytes, but their semantics must agree.
 */
static int imported_if_listing_roundtrip(void)
{
    unsigned int mask, cache;
    for (cache = 0u; cache < 2u; ++cache) {
        for (mask = 0u; mask < 8u; ++mask) {
            uint8_t body[20], original[20], listed[80], tokens[80];
            uint8_t full[160], before_full[1024], output_snapshot[80];
            uint8_t image[1024];
            char expected[80], expected_line[160];
            Harness h;
            BasicProgramLine dest;
            BasicProgram saved_program;
            BasicVariableStore saved_store;
            BasicVariableEntry saved_entries[6];
            size_t n = 0u, listed_n = 987u, again_n = 0u;
            size_t full_n = 777u, image_n = 0u;
            size_t expected_n, expected_full_n, i;
            int fmt, line_fmt;
            const char *first = (mask & 1u) != 0u ? "  " : " ";
            const char *second = (mask & 2u) != 0u ? "  " : " ";
            const char *third = (mask & 4u) != 0u ? "   " : " ";
            /* Vary retained separators so C1 must preserve their actual
             * counts, not simply force one space everywhere. */
            fmt = snprintf(expected, sizeof(expected), "IF%sA%%%sTHEN%s60",
                           first, second, third);
            CHECK(fmt > 0 && (size_t)fmt < sizeof(expected));
            expected_n = (size_t)fmt;
            line_fmt = snprintf(expected_line, sizeof(expected_line),
                                "20 %s\n30 PRINT 31\n40 END\n"
                                "60 PRINT 61\n70 END\n", expected);
            CHECK(line_fmt > 0 && (size_t)line_fmt < sizeof(expected_line));
            expected_full_n = (size_t)line_fmt;

            body[n++] = 0xa1u;
            if ((mask & 1u) != 0u) {
                body[n++] = (uint8_t)' ';
                body[n++] = (uint8_t)' ';
            }
            body[n++] = 0x02u;
            body[n++] = cache != 0u ? 0x20u : 0x00u;
            body[n++] = cache != 0u ? 0xefu : 0x00u;
            body[n++] = 0xc1u;
            if ((mask & 2u) != 0u) {
                body[n++] = (uint8_t)' ';
                body[n++] = (uint8_t)' ';
            }
            body[n++] = 0xebu;
            if ((mask & 4u) != 0u) {
                body[n++] = (uint8_t)' ';
                body[n++] = (uint8_t)' ';
                body[n++] = (uint8_t)' ';
            }
            body[n++] = 0x1eu;
            body[n++] = 0x3cu;
            body[n++] = 0x00u;
            memcpy(original, body, n);

            /* On failure the entire destination and written are intact. */
            memset(listed, 0xacu, sizeof(listed));
            memcpy(output_snapshot, listed, sizeof(listed));
            CHECK(bl_detokenize(body, n, listed, expected_n - 1u,
                                &listed_n) == BL_NO_SPACE);
            CHECK(listed_n == 987u &&
                  memcmp(listed, output_snapshot, sizeof(listed)) == 0);
            CHECK(memcmp(original, body, n) == 0);
            CHECK(bl_detokenize(body, n, listed, 0u,
                                &listed_n) == BL_NO_SPACE);
            CHECK(listed_n == 987u &&
                  memcmp(listed, output_snapshot, sizeof(listed)) == 0);

            CHECK(bl_detokenize(body, n, listed, expected_n,
                                &listed_n) == BL_OK);
            CHECK(listed_n == expected_n &&
                  memcmp(listed, expected, expected_n) == 0);
            for (i = expected_n; i < sizeof(listed); ++i) {
                CHECK(listed[i] == 0xacu);
            }
            CHECK(memcmp(original, body, n) == 0);
            CHECK(bt_tokenize(listed, listed_n, tokens,
                              sizeof(tokens), &again_n) == BT_OK);
            /* The native canonical representation never loses the target
             * and is itself LIST-roundtrip safe. */
            {
                uint8_t again_listed[80];
                size_t again_listed_n = 0u;
                CHECK(bl_detokenize(tokens, again_n, again_listed,
                                    sizeof(again_listed),
                                    &again_listed_n) == BL_OK);
                CHECK(again_listed_n == expected_n &&
                      memcmp(again_listed, expected, expected_n) == 0);
            }

            CHECK(setup(&h) == 0);
            CHECK(bp_put(&h.program, 20u, body, n) == BP_OK);
            CHECK(put(&h, 30u, "PRINT 31") == 0);
            CHECK(put(&h, 40u, "END") == 0);
            CHECK(put(&h, 60u, "PRINT 61") == 0);
            CHECK(put(&h, 70u, "END") == 0);
            /* Import a complete CPC-shaped image, not only a manufactured
             * body passed directly to the detokenizer. */
            CHECK(bp_export(&h.program, image, sizeof(image),
                            &image_n) == BP_OK);
            CHECK(bp_init(&h.program, h.storage,
                          sizeof(h.storage)) == BP_OK);
            CHECK(bp_import(&h.program, image, image_n) == BP_OK);
            CHECK(memcmp(h.storage, image, image_n) == 0);
            CHECK(bp_find(&h.program, 60u, &dest) == BP_OK);
            saved_program = h.program;
            saved_store = h.store;
            memcpy(saved_entries, h.entries, sizeof(saved_entries));
            memcpy(before_full, h.storage, sizeof(before_full));
            /* A full LIST is also responsible for atomicity and exact
             * program image preservation, including BVR cache bytes. */
            memset(full, 0x5cu, sizeof(full));
            CHECK(bl_list_program(&h.program, full, 0u, &full_n)
                  == BL_NO_SPACE);
            CHECK(full_n == 777u);
            for (i = 0u; i < sizeof(full); ++i) {
                CHECK(full[i] == 0x5cu);
            }
            CHECK(bl_list_program(&h.program, full, expected_full_n - 1u,
                                  &full_n) == BL_NO_SPACE);
            CHECK(full_n == 777u);
            for (i = 0u; i < sizeof(full); ++i) {
                CHECK(full[i] == 0x5cu);
            }
            CHECK(bl_list_program(&h.program, full, expected_full_n,
                                  &full_n) == BL_OK);
            CHECK(full_n == expected_full_n);
            CHECK(memcmp(full, expected_line, expected_full_n) == 0);
            CHECK(memcmp(before_full, h.storage, sizeof(before_full)) == 0);
            CHECK(memcmp(h.storage, image, image_n) == 0);
            CHECK(memcmp(&h.program, &saved_program, sizeof(saved_program)) == 0);
            CHECK(memcmp(&h.store, &saved_store, sizeof(saved_store)) == 0);
            CHECK(memcmp(h.entries, saved_entries, sizeof(saved_entries)) == 0);

            CHECK(variable(&h, (uint8_t)'A', 1) == 0);
            CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
            memset(h.output, 0xbbu, sizeof(h.output));
            h.written = 912u;
            CHECK(be_step(&h.executor, h.output, 0u, &h.written) == BE_OK);
            CHECK(h.written == 0u && h.executor.cursor == dest.offset);
            for (i = 0u; i < sizeof(h.output); ++i) {
                CHECK(h.output[i] == 0xbbu);
            }
            CHECK(be_step(&h.executor, h.output, sizeof(h.output),
                          &h.written) == BE_OK);
            CHECK(h.written == 3u && memcmp(h.output, "61\n", 3u) == 0);
            CHECK(memcmp(before_full, h.storage, sizeof(before_full)) == 0);
            CHECK(memcmp(original, body, n) == 0);
            CHECK(variable(&h, (uint8_t)'A', 0) == 0);
            CHECK(be_init_with_store(&h.executor, &h.program, &h.store) == BE_OK);
            CHECK(be_step(&h.executor, h.output, 0u, &h.written) == BE_OK);
            CHECK(be_step(&h.executor, h.output, sizeof(h.output),
                          &h.written) == BE_OK);
            CHECK(h.written == 3u && memcmp(h.output, "31\n", 3u) == 0);
        }
    }
    return 0;
}

int main(void)
{
    CHECK(token_listing() == 0);
    CHECK(imported_if_listing_roundtrip() == 0);
    CHECK(branching() == 0);
    CHECK(missing_and_malformed() == 0);
    CHECK(console_runtime() == 0);
    puts("J1.10-B IF INTEGER: tokens, LIST, branches, errors and atomicity OK");
    return 0;
}
