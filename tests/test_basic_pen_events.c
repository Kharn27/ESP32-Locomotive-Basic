#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_session_runtime.h"

#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    uint8_t storage[1024];
    uint8_t temporary[256];
    uint8_t output[256];
    BEVideoEvent events[4];
    size_t written;
    size_t event_written;
} Fixture;

static int setup(Fixture *f)
{
    memset(f, 0xa5, sizeof(*f));
    CHECK(bp_init(&f->program, f->storage, sizeof(f->storage)) == BP_OK);
    CHECK(bsr_init(&f->runtime, &f->program).status == BSR_OK);
    return 0;
}

static BSRResult submit(Fixture *f, const char *source)
{
    return bsr_submit(&f->runtime, (const uint8_t *)source, strlen(source),
                      f->temporary, sizeof(f->temporary), f->output,
                      sizeof(f->output), &f->written);
}

static BSRResult step(Fixture *f, size_t output_cap, size_t event_cap)
{
    return bsr_step_events(&f->runtime, f->output, output_cap, &f->written,
                           f->events, event_cap, &f->event_written);
}

/* Snapshot all state and both output channels; an error must preserve all. */
static int failed(Fixture *f, BEStatus expected, size_t output_cap,
                  size_t event_cap, int legacy)
{
    BasicSessionRuntime runtime = f->runtime;
    BasicProgram program = f->program;
    uint8_t storage[sizeof(f->storage)];
    uint8_t output[sizeof(f->output)];
    BEVideoEvent events[4];
    size_t written = f->written, event_written = f->event_written;
    BSRResult result;
    memcpy(storage, f->storage, sizeof(storage));
    memcpy(output, f->output, sizeof(output));
    memcpy(events, f->events, sizeof(events));
    result = legacy ? bsr_step(&f->runtime, f->output, output_cap, &f->written)
                    : step(f, output_cap, event_cap);
    CHECK(result.status == BSR_EXECUTOR_ERROR);
    CHECK(result.executor_status == expected);
    CHECK(memcmp(&f->runtime, &runtime, sizeof(runtime)) == 0);
    CHECK(memcmp(&f->program, &program, sizeof(program)) == 0);
    CHECK(memcmp(f->storage, storage, sizeof(storage)) == 0);
    CHECK(memcmp(f->output, output, sizeof(output)) == 0);
    CHECK(memcmp(f->events, events, sizeof(events)) == 0);
    CHECK(f->written == written && f->event_written == event_written);
    return 0;
}

static int oracle_token_and_listing(void)
{
    static const struct {
        const char *source;
        uint8_t bytes[4];
        size_t length;
        BEStatus legacy_status;
    } cases[] = {
        {"PEN 0",  {0xbbu,' ',0x0eu,0u}, 3u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 1",  {0xbbu,' ',0x0fu,0u}, 3u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 2",  {0xbbu,' ',0x10u,0u}, 3u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 3",  {0xbbu,' ',0x11u,0u}, 3u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 4",  {0xbbu,' ',0x12u,0u}, 3u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 15", {0xbbu,' ',0x19u,0x0fu}, 4u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 16", {0xbbu,' ',0x19u,0x10u}, 4u, BE_INVALID_PEN},
        {"PEN -1", {0xbbu,' ',0xf5u,0x0fu}, 4u, BE_INVALID_PEN}
    };
    static const char *invalid_source[] = {
        "PEN", "PEN A%", "PEN #8", "PEN -2", "PEN 1.5",
        "PEN 2,3", "PEN 17", "PEN +1", "PEN 1X"
    };
    size_t i;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        Fixture f;
        uint8_t encoded[16], listing[32];
        size_t n = 999u, listed = 777u;
        CHECK(setup(&f) == 0);
        memset(encoded, 0x55, sizeof(encoded));
        CHECK(bt_tokenize((const uint8_t *)cases[i].source,
                          strlen(cases[i].source), encoded, sizeof(encoded),
                          &n) == BT_OK);
        CHECK(n == cases[i].length);
        CHECK(memcmp(encoded, cases[i].bytes, n) == 0);
        CHECK(encoded[n] == 0x55u);
        memset(listing, 0x55, sizeof(listing));
        CHECK(bl_detokenize(encoded, n, listing, sizeof(listing),
                            &listed) == BL_OK);
        CHECK(listed == strlen(cases[i].source));
        CHECK(memcmp(listing, cases[i].source, listed) == 0);
        CHECK(listing[listed] == 0x55u);
        CHECK(bp_put(&f.program, 10u, encoded, n) == BP_OK);
        CHECK(be_init(&f.runtime.executor, &f.program) == BE_OK);
        f.runtime.state = BSR_RUNNING;
        CHECK(failed(&f, cases[i].legacy_status,
                     sizeof(f.output), 0u, 1) == 0);
        if (i < 6u) {
            CHECK(step(&f, sizeof(f.output), 1u).status == BSR_OK);
            CHECK(f.written == 0u && f.event_written == 1u);
            CHECK(f.events[0].type == BE_VIDEO_SET_TEXT_PEN);
            CHECK(f.events[0].pen == (i == 5u ? 15u : (uint8_t)i));
            CHECK(f.events[0].print_offset == 0u);
        } else {
            CHECK(failed(&f, BE_INVALID_PEN, sizeof(f.output), 4u, 0) == 0);
        }
    }
    for (i = 0u; i < sizeof(invalid_source)/sizeof(invalid_source[0]); ++i) {
        uint8_t encoded[32], copy[32];
        size_t count = 77u;
        memset(encoded, 0x5au, sizeof(encoded));
        memcpy(copy, encoded, sizeof(encoded));
        CHECK(bt_tokenize((const uint8_t *)invalid_source[i],
                          strlen(invalid_source[i]), encoded,
                          sizeof(encoded), &count) != BT_OK);
        CHECK(count == 77u && memcmp(encoded, copy, sizeof(encoded)) == 0);
    }
    return 0;
}

static int unmeasured_and_atomic_errors(void)
{
    unsigned int value;
    for (value = 5u; value <= 14u; ++value) {
        Fixture f;
        char source[32];
        CHECK(setup(&f) == 0);
        CHECK(snprintf(source, sizeof(source), "10 PEN %u", value) > 0);
        CHECK(submit(&f, source).status == BSR_OK);
        CHECK(submit(&f, "RUN").status == BSR_OK);
        CHECK(failed(&f, BE_UNSUPPORTED, sizeof(f.output), 4u, 0) == 0);
    }
    {
        Fixture f;
        CHECK(setup(&f) == 0);
        CHECK(submit(&f, "10 PEN 4:PRINT \"X\":PEN 16").status == BSR_OK);
        CHECK(submit(&f, "RUN").status == BSR_OK);
        CHECK(failed(&f, BE_INVALID_PEN, sizeof(f.output), 4u, 0) == 0);
        CHECK(submit(&f, "RUN").status == BSR_OK);
        CHECK(f.runtime.executor.cursor == 0u);
    }
    {
        Fixture f;
        CHECK(setup(&f) == 0);
        CHECK(submit(&f, "10 PEN 4:PRINT \"X\":PEN 5").status == BSR_OK);
        CHECK(submit(&f, "RUN").status == BSR_OK);
        CHECK(failed(&f, BE_UNSUPPORTED, sizeof(f.output), 4u, 0) == 0);
    }
    return 0;
}

static int event_order_capacity_and_legacy(void)
{
    Fixture f;
    BSRResult result;
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "10 PEN 4:PRINT \"X\":PEN 15:PRINT \"Y\"").status == BSR_OK);
    CHECK(submit(&f, "20 PRINT \"Z\"").status == BSR_OK);
    CHECK(submit(&f, "30 END").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    memset(f.output, 0x63, sizeof(f.output));
    memset(f.events, 0x74, sizeof(f.events));
    f.written = 81u;
    f.event_written = 93u;
    CHECK(failed(&f, BE_EVENT_RECEIVER_REQUIRED, sizeof(f.output), 0u, 1) == 0);
    result = bsr_step_events(&f.runtime, f.output, sizeof(f.output),
                              &f.written, NULL, 0u, &f.event_written);
    CHECK(result.status == BSR_EXECUTOR_ERROR);
    CHECK(result.executor_status == BE_EVENT_RECEIVER_REQUIRED);
    CHECK(f.written == 81u && f.event_written == 93u &&
          f.runtime.executor.cursor == 0u && f.output[0] == 0x63u);
    CHECK(failed(&f, BE_NO_EVENT_SPACE, sizeof(f.output), 0u, 0) == 0);
    CHECK(failed(&f, BE_NO_EVENT_SPACE, sizeof(f.output), 1u, 0) == 0);
    CHECK(failed(&f, BE_NO_SPACE, 3u, 4u, 0) == 0);
    result = step(&f, sizeof(f.output), 2u);
    CHECK(result.status == BSR_OK && f.written == 4u && f.event_written == 2u);
    CHECK(memcmp(f.output, "X\nY\n", 4u) == 0);
    CHECK(f.output[4] == 0x63u);
    CHECK(f.events[0].type == BE_VIDEO_SET_TEXT_PEN &&
          f.events[0].pen == 4u && f.events[0].print_offset == 0u);
    CHECK(f.events[1].type == BE_VIDEO_SET_TEXT_PEN &&
          f.events[1].pen == 15u && f.events[1].print_offset == 2u);
    CHECK(f.runtime.executor.cursor != 0u);
    result = step(&f, sizeof(f.output), 2u);
    CHECK(result.status == BSR_OK && f.written == 2u &&
          f.event_written == 0u && memcmp(f.output, "Z\n", 2u) == 0);
    result = step(&f, sizeof(f.output), 2u);
    CHECK(result.status == BSR_OK && f.written == 0u && f.event_written == 0u);
    result = step(&f, sizeof(f.output), 2u);
    CHECK(result.status == BSR_END && result.executor_status == BE_END);
    return 0;
}

static int direct_runtime_and_bad_tokens(void)
{
    static const struct {
        uint8_t bytes[4];
        size_t n;
        BEStatus expect;
    } broken[] = {
        {{0xbbu,' ',0x19u,0u}, 3u, BE_TRUNCATED},
        {{0xbbu,' ',0xf5u,0u}, 3u, BE_TRUNCATED},
        {{0xbbu,' ',0x88u,0u}, 3u, BE_UNKNOWN_TOKEN},
        {{0xbbu,' ',0x19u,0x09u}, 4u, BE_BAD_SEQUENCE},
        {{0xbbu,' ',0x0eu,0x19u}, 4u, BE_UNKNOWN_TOKEN}
    };
    size_t i;
    for (i = 0u; i < sizeof(broken)/sizeof(broken[0]); ++i) {
        Fixture f;
        CHECK(setup(&f) == 0);
        CHECK(bp_put(&f.program, 10u, broken[i].bytes, broken[i].n) == BP_OK);
        CHECK(be_init(&f.runtime.executor, &f.program) == BE_OK);
        f.runtime.state = BSR_RUNNING;
        CHECK(failed(&f, broken[i].expect, sizeof(f.output), 4u, 0) == 0);
    }
    {
        Fixture f;
        BSRResult result;
        CHECK(setup(&f) == 0);
        CHECK(submit(&f, "10 PEN 4").status == BSR_OK);
        CHECK(submit(&f, "RUN").status == BSR_OK);
        result = bsr_step_events(&f.runtime, (uint8_t *)(void *)f.events,
                                  sizeof(f.events), &f.written, f.events, 1u,
                                  &f.event_written);
        CHECK(result.status == BSR_OVERLAP);
        result = bsr_step_events(&f.runtime, f.output, sizeof(f.output),
                                  &f.written, (BEVideoEvent *)(void *)&f.runtime,
                                  1u, &f.event_written);
        CHECK(result.status == BSR_OVERLAP);
        result = bsr_step_events(&f.runtime, f.output, sizeof(f.output),
                                  &f.written, f.events, 1u, &f.written);
        CHECK(result.status == BSR_OVERLAP);
        CHECK(f.runtime.executor.cursor == 0u);
        CHECK(step(&f, sizeof(f.output), 1u).status == BSR_OK);
        CHECK(f.event_written == 1u && f.events[0].pen == 4u);
    }
    return 0;
}

int main(void)
{
    CHECK(oracle_token_and_listing() == 0);
    CHECK(unmeasured_and_atomic_errors() == 0);
    CHECK(event_order_capacity_and_legacy() == 0);
    CHECK(direct_runtime_and_bad_tokens() == 0);
    puts("basic_pen_events: OK");
    return 0;
}
