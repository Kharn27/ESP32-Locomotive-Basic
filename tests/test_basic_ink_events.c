#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_session_runtime.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    uint8_t storage[1024];
    uint8_t temporary[256];
    uint8_t output[256];
    BEVideoEvent events[5];
    size_t written;
    size_t events_written;
} Fixture;

static int init(Fixture *f)
{
    memset(f, 0xa5, sizeof(*f));
    CHECK(bp_init(&f->program, f->storage, sizeof(f->storage)) == BP_OK);
    CHECK(bsr_init(&f->runtime, &f->program).status == BSR_OK);
    return 0;
}

static BSRResult submit(Fixture *f, const char *s)
{
    return bsr_submit(&f->runtime, (const uint8_t *)s, strlen(s),
                      f->temporary, sizeof(f->temporary), f->output,
                      sizeof(f->output), &f->written);
}

static BSRResult step(Fixture *f, size_t outcap, size_t eventcap)
{
    return bsr_step_events(&f->runtime, f->output, outcap, &f->written,
                            f->events, eventcap, &f->events_written);
}

/* Entire output regions, descriptor, cursor and counters remain unchanged. */
static int failed(Fixture *f, BEStatus expected, size_t outcap,
                  size_t eventcap, int legacy)
{
    BasicSessionRuntime runtime = f->runtime;
    BasicProgram program = f->program;
    uint8_t storage[sizeof(f->storage)], output[sizeof(f->output)];
    BEVideoEvent events[5];
    size_t written = f->written, count = f->events_written;
    BSRResult result;
    memcpy(storage, f->storage, sizeof(storage));
    memcpy(output, f->output, sizeof(output));
    memcpy(events, f->events, sizeof(events));
    result = legacy ? bsr_step(&f->runtime, f->output, outcap, &f->written)
                    : step(f, outcap, eventcap);
    CHECK(result.status == BSR_EXECUTOR_ERROR);
    CHECK(result.executor_status == expected);
    CHECK(memcmp(&f->runtime, &runtime, sizeof(runtime)) == 0);
    CHECK(memcmp(&f->program, &program, sizeof(program)) == 0);
    CHECK(memcmp(f->storage, storage, sizeof(storage)) == 0);
    CHECK(memcmp(f->output, output, sizeof(output)) == 0);
    CHECK(memcmp(f->events, events, sizeof(events)) == 0);
    CHECK(f->written == written && f->events_written == count);
    return 0;
}

static int oracle_13(void)
{
    /* Exact L10 CPC RAM bodies, from unmodified J1.18-A sealed acquisitions.
     * Record format adds 2-byte size, 2-byte line, and trailing zero. */
    static const struct {
        const char *source;
        uint8_t body[8];
        size_t length;
        BEStatus run_status;
        uint8_t ink, colour;
    } cases[] = {
        {"INK 0,0",    {0xa2u,' ',0x0eu,',',0x0eu},                5u, BE_OK, 0u, 0u},
        {"INK 1,26",   {0xa2u,' ',0x0fu,',',0x19u,0x1au},          6u, BE_OK, 1u, 26u},
        {"INK 1,6",    {0xa2u,' ',0x0fu,',',0x14u},                5u, BE_OK, 1u, 6u},
        {"INK 2,6",    {0xa2u,' ',0x10u,',',0x14u},                5u, BE_OK, 2u, 6u},
        {"INK 3,18",   {0xa2u,' ',0x11u,',',0x19u,0x12u},          6u, BE_OK, 3u, 18u},
        {"INK 15,26",  {0xa2u,' ',0x19u,0x0fu,',',0x19u,0x1au},    7u, BE_OK, 15u, 26u},
        {"INK 1,27",   {0xa2u,' ',0x0fu,',',0x19u,0x1bu},          6u, BE_OK, 1u, 27u},
        {"INK 1,31",   {0xa2u,' ',0x0fu,',',0x19u,0x1fu},          6u, BE_OK, 1u, 31u},
        {"INK 1,26,6", {0xa2u,' ',0x0fu,',',0x19u,0x1au,',',0x14u},8u, BE_UNSUPPORTED, 0u, 0u},
        {"INK 16,26",  {0xa2u,' ',0x19u,0x10u,',',0x19u,0x1au},   7u, BE_INVALID_INK, 0u, 0u},
        {"INK -1,26",  {0xa2u,' ',0xf5u,0x0fu,',',0x19u,0x1au},   7u, BE_INVALID_INK, 0u, 0u},
        {"INK 1,32",   {0xa2u,' ',0x0fu,',',0x19u,0x20u},         6u, BE_INVALID_INK, 0u, 0u},
        {"INK 1,-1",   {0xa2u,' ',0x0fu,',',0xf5u,0x0fu},         6u, BE_INVALID_INK, 0u, 0u}
    };
    size_t i;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        Fixture f;
        uint8_t encoded[32], list[64];
        size_t n = 99u, listed = 88u;
        CHECK(init(&f) == 0);
        memset(encoded, 0x55, sizeof(encoded));
        CHECK(bt_tokenize((const uint8_t *)cases[i].source,
                          strlen(cases[i].source), encoded, sizeof(encoded), &n) == BT_OK);
        CHECK(n == cases[i].length);
        CHECK(memcmp(encoded, cases[i].body, n) == 0);
        CHECK(encoded[n] == 0x55u);
        memset(list, 0x55, sizeof(list));
        CHECK(bl_detokenize(encoded, n, list, sizeof(list), &listed) == BL_OK);
        CHECK(listed == strlen(cases[i].source));
        CHECK(memcmp(list, cases[i].source, listed) == 0);
        CHECK(list[listed] == 0x55u);
        CHECK(bp_put(&f.program, 10u, encoded, n) == BP_OK);
        CHECK(f.program.size == n + 7u);
        CHECK(f.storage[0] == n + 5u && f.storage[1] == 0u);
        CHECK(f.storage[2] == 10u && f.storage[3] == 0u);
        CHECK(memcmp(f.storage + 4u, cases[i].body, n) == 0);
        CHECK(f.storage[n + 4u] == 0u);
        CHECK(be_init(&f.runtime.executor, &f.program) == BE_OK);
        f.runtime.state = BSR_RUNNING;
        if (cases[i].run_status == BE_OK) {
            CHECK(failed(&f, BE_EVENT_RECEIVER_REQUIRED, sizeof(f.output), 0u, 1) == 0);
            CHECK(step(&f, sizeof(f.output), 1u).status == BSR_OK);
            CHECK(f.written == 0u && f.events_written == 1u);
            CHECK(f.events[0].type == BE_VIDEO_SET_INK);
            CHECK(f.events[0].pen == 0u);
            CHECK(f.events[0].ink == cases[i].ink &&
                  f.events[0].colour == cases[i].colour);
            CHECK(f.events[0].print_offset == 0u);
        } else {
            CHECK(failed(&f, cases[i].run_status, sizeof(f.output), 5u, 0) == 0);
        }
    }
    return 0;
}

static int order_and_atomicity(void)
{
    Fixture f;
    BSRResult result;
    CHECK(init(&f) == 0);
    CHECK(submit(&f, "10 PRINT \\"A\\":PEN 3:INK 1,26:PRINT \\"B\\"").status == BSR_OK);
    CHECK(submit(&f, "20 INK 1,6").status == BSR_OK);
    CHECK(submit(&f, "30 END").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    memset(f.output, 0x63, sizeof(f.output));
    memset(f.events, 0x74, sizeof(f.events));
    f.written = 80u;
    f.events_written = 90u;
    CHECK(failed(&f, BE_EVENT_RECEIVER_REQUIRED, sizeof(f.output), 0u, 1) == 0);
    result = bsr_step_events(&f.runtime, f.output, sizeof(f.output),
                            &f.written, NULL, 0u, &f.events_written);
    CHECK(result.status == BSR_EXECUTOR_ERROR &&
          result.executor_status == BE_EVENT_RECEIVER_REQUIRED);
    CHECK(f.written == 80u && f.events_written == 90u);
    CHECK(failed(&f, BE_NO_EVENT_SPACE, sizeof(f.output), 0u, 0) == 0);
    CHECK(failed(&f, BE_NO_EVENT_SPACE, sizeof(f.output), 1u, 0) == 0);
    CHECK(failed(&f, BE_NO_SPACE, 3u, 5u, 0) == 0);
    result = step(&f, sizeof(f.output), 2u);
    CHECK(result.status == BSR_OK && f.written == 4u && f.events_written == 2u);
    CHECK(memcmp(f.output, "A\\nB\\n", 4u) == 0 && f.output[4] == 0x63u);
    CHECK(f.events[0].type == BE_VIDEO_SET_TEXT_PEN &&
          f.events[0].pen == 3u && f.events[0].ink == 0u &&
          f.events[0].colour == 0u && f.events[0].print_offset == 2u);
    CHECK(f.events[1].type == BE_VIDEO_SET_INK &&
          f.events[1].ink == 1u && f.events[1].colour == 26u &&
          f.events[1].pen == 0u && f.events[1].print_offset == 2u);
    result = step(&f, sizeof(f.output), 2u);
    CHECK(result.status == BSR_OK && f.written == 0u && f.events_written == 1u);
    CHECK(f.events[0].type == BE_VIDEO_SET_INK &&
          f.events[0].colour == 6u && f.events[0].print_offset == 0u);
    result = step(&f, sizeof(f.output), 2u);
    CHECK(result.status == BSR_OK && f.written == 0u && f.events_written == 0u);
    result = step(&f, sizeof(f.output), 2u);
    CHECK(result.status == BSR_END && result.executor_status == BE_END);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(step(&f, sizeof(f.output), 2u).status == BSR_OK);
    CHECK(f.events[1].type == BE_VIDEO_SET_INK && f.events_written == 2u);
    return 0;
}

static int negative_tests(void)
{
    static const char *unknown[] = {
        "INK 0,26", "INK 4,6", "INK 1,30", "INK 2,26", "INK 16,1",
        "INK -1,6", "INK 1,26,6"
    };
    static const char *malformed[] = {
        "INK", "INK 1", "INK #8,6", "INK A%,6",
        "INK 1+0,6", "INK 1,6.5", "INK 1,26,5",
        "INK 1,6,6", "INK 1,33", "INK 17,26"
    };
    size_t i;
    for (i = 0u; i < sizeof(unknown)/sizeof(unknown[0]); ++i) {
        Fixture f;
        char line[64];
        CHECK(init(&f) == 0);
        CHECK(snprintf(line, sizeof(line), "10 %s", unknown[i]) > 0);
        CHECK(submit(&f, line).status == BSR_OK);
        CHECK(submit(&f, "RUN").status == BSR_OK);
        CHECK(failed(&f, BE_UNSUPPORTED, sizeof(f.output), 5u, 0) == 0);
    }
    for (i = 0u; i < sizeof(malformed)/sizeof(malformed[0]); ++i) {
        uint8_t encoded[64], copy[64];
        size_t count = 77u;
        memset(encoded, 0x5a, sizeof(encoded));
        memcpy(copy, encoded, sizeof(encoded));
        CHECK(bt_tokenize((const uint8_t *)malformed[i],
                          strlen(malformed[i]), encoded,
                          sizeof(encoded), &count) != BT_OK);
        CHECK(count == 77u && memcmp(encoded, copy, sizeof(encoded)) == 0);
    }
    {
        Fixture f;
        CHECK(init(&f) == 0);
        CHECK(submit(&f, "10 PRINT \\"X\\":INK 1,32").status == BSR_OK);
        CHECK(submit(&f, "RUN").status == BSR_OK);
        CHECK(failed(&f, BE_INVALID_INK, sizeof(f.output), 5u, 0) == 0);
    }
    {
        static const struct { uint8_t body[7]; size_t n; BEStatus expected; } bad[] = {
            {{0xa2u,' ',0x0fu,',',0x19u}, 5u, BE_TRUNCATED},
            {{0xa2u,' ',0x0fu,',',0xf5u}, 5u, BE_TRUNCATED},
            {{0xa2u,' ',0x88u,',',0x14u}, 5u, BE_UNKNOWN_TOKEN},
            {{0xa3u,' ',0x0fu,',',0x14u}, 5u, BE_UNKNOWN_TOKEN},
            {{0xa2u,' ',0x0fu,',',0x19u,0x09u}, 6u, BE_BAD_SEQUENCE}
        };
        for (i = 0u; i < sizeof(bad)/sizeof(bad[0]); ++i) {
            Fixture f;
            CHECK(init(&f) == 0);
            CHECK(bp_put(&f.program, 10u, bad[i].body, bad[i].n) == BP_OK);
            CHECK(be_init(&f.runtime.executor, &f.program) == BE_OK);
            f.runtime.state = BSR_RUNNING;
            CHECK(failed(&f, bad[i].expected, sizeof(f.output), 5u, 0) == 0);
        }
    }
    {
        Fixture f;
        BSRResult result;
        CHECK(init(&f) == 0);
        CHECK(submit(&f, "10 INK 1,26").status == BSR_OK);
        CHECK(submit(&f, "RUN").status == BSR_OK);
        result = bsr_step_events(&f.runtime, (uint8_t *)(void *)f.events,
                                 sizeof(f.events), &f.written, f.events, 1u,
                                 &f.events_written);
        CHECK(result.status == BSR_OVERLAP && f.runtime.executor.cursor == 0u);
        result = bsr_step_events(&f.runtime, f.output, sizeof(f.output),
                                 &f.written, (BEVideoEvent *)(void *)&f.runtime,
                                 1u, &f.events_written);
        CHECK(result.status == BSR_OVERLAP && f.runtime.executor.cursor == 0u);
        result = bsr_step_events(&f.runtime, f.output, sizeof(f.output),
                                 &f.written, f.events, 1u, &f.written);
        CHECK(result.status == BSR_OVERLAP && f.runtime.executor.cursor == 0u);
        CHECK(step(&f, sizeof(f.output), 1u).status == BSR_OK);
    }
    return 0;
}

int main(void)
{
    /* ABI regression: adding ink/colour uses bytes historically occupied by
     * padding after PEN, leaving print_offset and sizeof unchanged on the
     * current GCC/Clang host and ESP32 Xtensa configurations. */
    CHECK(offsetof(BEVideoEvent, type) == 0u);
    CHECK(offsetof(BEVideoEvent, pen) == sizeof(BEVideoEventType));
    CHECK(offsetof(BEVideoEvent, print_offset) == 8u);
    CHECK(sizeof(BEVideoEvent) == (sizeof(size_t) == 8u ? 16u : 12u));
    CHECK(oracle_13() == 0);
    CHECK(order_and_atomicity() == 0);
    CHECK(negative_tests() == 0);
    printf("basic_ink_events: OK, sizeof(BEVideoEvent)=%lu, print_offset=%lu\\n",
           (unsigned long)sizeof(BEVideoEvent),
           (unsigned long)offsetof(BEVideoEvent, print_offset));
    return 0;
}
