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
        {"PEN 5", {0xbbu,' ',0x13u,0u}, 3u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 6", {0xbbu,' ',0x14u,0u}, 3u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 7", {0xbbu,' ',0x15u,0u}, 3u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 8", {0xbbu,' ',0x16u,0u}, 3u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 9", {0xbbu,' ',0x17u,0u}, 3u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 10", {0xbbu,' ',0x19u,0x0au}, 4u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 11", {0xbbu,' ',0x19u,0x0bu}, 4u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 12", {0xbbu,' ',0x19u,0x0cu}, 4u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 13", {0xbbu,' ',0x19u,0x0du}, 4u, BE_EVENT_RECEIVER_REQUIRED},
        {"PEN 14", {0xbbu,' ',0x19u,0x0eu}, 4u, BE_EVENT_RECEIVER_REQUIRED},
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
        if (i < 16u) {
            CHECK(step(&f, sizeof(f.output), 1u).status == BSR_OK);
            CHECK(f.written == 0u && f.event_written == 1u);
            CHECK(f.events[0].type == BE_VIDEO_SET_TEXT_PEN);
            CHECK(f.events[0].pen == (uint8_t)i);
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

/* J1.17-C-B: each of the ten independently acquired native PEN values. */
static int new_pen_values_and_atomic_errors(void)
{
    unsigned int value;
    for (value = 5u; value <= 14u; ++value) {
        Fixture f;
        BSRResult result;
        char source[32], listed[32];
        size_t expected_length;
        CHECK(setup(&f) == 0);
        CHECK(snprintf(source, sizeof(source), "10 PEN %u", value) > 0);
        CHECK(snprintf(listed, sizeof(listed), "10 PEN %u\n", value) > 0);
        expected_length = strlen(listed);
        CHECK(submit(&f, source).status == BSR_OK);
        CHECK(submit(&f, "LIST").status == BSR_OK);
        CHECK(f.written == expected_length);
        CHECK(memcmp(f.output, listed, expected_length) == 0);
        CHECK(submit(&f, "RUN").status == BSR_OK);
        CHECK(failed(&f, BE_EVENT_RECEIVER_REQUIRED,
                     sizeof(f.output), 0u, 1) == 0);
        CHECK(failed(&f, BE_NO_EVENT_SPACE, sizeof(f.output), 0u, 0) == 0);
        result = step(&f, sizeof(f.output), 1u);
        CHECK(result.status == BSR_OK);
        CHECK(f.written == 0u && f.event_written == 1u);
        CHECK(f.events[0].type == BE_VIDEO_SET_TEXT_PEN);
        CHECK(f.events[0].pen == (uint8_t)value);
        CHECK(f.events[0].ink == 0u && f.events[0].colour == 0u);
        CHECK(f.events[0].print_offset == 0u);
        CHECK(step(&f, sizeof(f.output), 1u).status == BSR_END);
    }
    {
        static const char *const rejected[] = {
            "10 PEN 5:PRINT \"X\":PEN 16",
            "10 PEN 14:PRINT \"X\":PEN -1"
        };
        size_t i;
        for (i = 0u; i < sizeof(rejected)/sizeof(rejected[0]); ++i) {
            Fixture f;
            CHECK(setup(&f) == 0);
            CHECK(submit(&f, rejected[i]).status == BSR_OK);
            CHECK(submit(&f, "RUN").status == BSR_OK);
            CHECK(failed(&f, BE_INVALID_PEN, sizeof(f.output), 4u, 0) == 0);
            CHECK(submit(&f, "RUN").status == BSR_OK);
            CHECK(f.runtime.executor.cursor == 0u);
        }
    }
    {
        Fixture f;
        CHECK(setup(&f) == 0);
        CHECK(submit(&f, "10 PEN 5:PRINT \"X\":PEN 14").status == BSR_OK);
        CHECK(submit(&f, "RUN").status == BSR_OK);
        CHECK(failed(&f, BE_NO_EVENT_SPACE, sizeof(f.output), 1u, 0) == 0);
        CHECK(failed(&f, BE_NO_SPACE, 1u, 4u, 0) == 0);
    }
    return 0;
}

/* CPC immutable image check. Only the first complete L10 record is
 * compared with the native L10 record: later LOCATE (not native) and
 * screenshots are deliberately outside this executable test. */
static int load_oracle(const char *root, const char *era,
                       const char *round, const char *id,
                       uint8_t *data, size_t capacity, size_t *length)
{
    char path[512];
    FILE *file;
    size_t got;
    int extra;
    CHECK(snprintf(path, sizeof(path),
                   "%s/tests/fixtures/cpc6128/%s/%s/%s/program.bin",
                   root, era, round, id) > 0);
    file = fopen(path, "rb");
    if (file == NULL) {
        fprintf(stderr, "Cannot open sealed CPC image: %s\n", path);
        return 1;
    }
    got = fread(data, 1u, capacity, file);
    extra = fgetc(file);
    CHECK(!ferror(file) && extra == EOF);
    CHECK(fclose(file) == 0 && got > 8u);
    *length = got;
    return 0;
}

static int one_sealed_pen(const char *root, const char *era,
                          const char *id, const char *statement)
{
    Fixture f;
    uint8_t original[256], repeat[256], native[256];
    uint8_t tokens[32], again[32], list[32];
    size_t original_len, repeat_len, native_len, encoded = 88u;
    size_t relisted = 77u, count = 66u, line_length;
    char line[32], expected_list[32];
    CHECK(load_oracle(root, era, "original", id,
                      original, sizeof(original), &original_len) == 0);
    CHECK(load_oracle(root, era, "repeat", id,
                      repeat, sizeof(repeat), &repeat_len) == 0);
    CHECK(original_len == repeat_len &&
          memcmp(original, repeat, original_len) == 0);
    CHECK(setup(&f) == 0);
    CHECK(snprintf(line, sizeof(line), "10 %s", statement) > 0);
    CHECK(snprintf(expected_list, sizeof(expected_list), "10 %s\n",
                   statement) > 0);
    CHECK(bt_tokenize((const uint8_t *)statement, strlen(statement),
                      tokens, sizeof(tokens), &encoded) == BT_OK);
    CHECK(bl_detokenize(tokens, encoded, list, sizeof(list), &relisted) == BL_OK);
    CHECK(relisted == strlen(statement) &&
          memcmp(list, statement, relisted) == 0);
    CHECK(bt_tokenize(list, relisted, again, sizeof(again), &count) == BT_OK);
    CHECK(encoded == count && memcmp(tokens, again, count) == 0);
    CHECK(submit(&f, line).status == BSR_OK);
    CHECK(bp_export(&f.program, native, sizeof(native), &native_len) == BP_OK);
    line_length = (size_t)original[0] | ((size_t)original[1] << 8);
    CHECK(line_length == encoded + 5u && original_len >= line_length + 2u);
    CHECK(original[2] == 10u && original[3] == 0u);
    CHECK(native_len >= line_length + 2u);
    CHECK(memcmp(native, original, line_length) == 0);
    CHECK(submit(&f, "LIST").status == BSR_OK);
    CHECK(f.written == strlen(expected_list) &&
          memcmp(f.output, expected_list, f.written) == 0);
    return 0;
}

/* Historical J1.17-A (8 values) and J1.17-C-A (26 palette-context cases)
 * are consulted read-only, including original/repeat complete-image pairs. */
static int compare_sealed_pen_images(const char *root)
{
    static const struct { const char *id; const char *source; } old[] = {
        {"P00", "PEN 0"}, {"P01", "PEN 1"},
        {"P02", "PEN 2"}, {"P03", "PEN 3"},
        {"P04", "PEN 4"}, {"P15", "PEN 15"},
        {"P16", "PEN 16"}, {"PN1", "PEN -1"}
    };
    static const unsigned int values[] = {
        0u, 2u, 3u, 5u, 6u, 7u, 8u, 9u,
        10u, 11u, 12u, 13u, 14u
    };
    size_t i;
    for (i = 0u; i < sizeof(old)/sizeof(old[0]); ++i)
        CHECK(one_sealed_pen(root, "j1_17_a_pen",
                             old[i].id, old[i].source) == 0);
    for (i = 0u; i < sizeof(values)/sizeof(values[0]); ++i) {
        char name[4], statement[16];
        unsigned int context;
        CHECK(snprintf(statement, sizeof(statement),
                       "PEN %u", values[i]) > 0);
        for (context = 0u; context < 2u; ++context) {
            CHECK(snprintf(name, sizeof(name), "%c%02u",
                           context == 0u ? 'C' : 'D', values[i]) > 0);
            CHECK(one_sealed_pen(root, "j1_17_c_a_pen",
                                 name, statement) == 0);
        }
    }
    puts("J1.17-C-B CPC L10 RAM 8/8 A + 26/26 C-A original/repeat");
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

/* Event values stay logical even when MODE1 render would repeat colours. */
static int new_pen_mixed_print_event_order(void)
{
    Fixture f;
    BSRResult result;
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "10 PEN 5:PRINT \"X\":PEN 14:PRINT \"Y\":PEN 8").status == BSR_OK);
    CHECK(submit(&f, "20 PEN 12:PRINT \"Z\"").status == BSR_OK);
    CHECK(submit(&f, "30 END").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    memset(f.output, 0x61, sizeof(f.output));
    memset(f.events, 0x71, sizeof(f.events));
    f.written = 81u;
    f.event_written = 82u;
    CHECK(failed(&f, BE_EVENT_RECEIVER_REQUIRED, sizeof(f.output), 0u, 1) == 0);
    CHECK(failed(&f, BE_NO_EVENT_SPACE, sizeof(f.output), 2u, 0) == 0);
    CHECK(failed(&f, BE_NO_SPACE, 3u, 4u, 0) == 0);
    result = step(&f, sizeof(f.output), 3u);
    CHECK(result.status == BSR_OK);
    CHECK(f.written == 4u && f.event_written == 3u);
    CHECK(memcmp(f.output, "X\nY\n", 4u) == 0 && f.output[4] == 0x61u);
    CHECK(f.events[0].type == BE_VIDEO_SET_TEXT_PEN &&
          f.events[0].pen == 5u && f.events[0].print_offset == 0u);
    CHECK(f.events[1].type == BE_VIDEO_SET_TEXT_PEN &&
          f.events[1].pen == 14u && f.events[1].print_offset == 2u);
    CHECK(f.events[2].type == BE_VIDEO_SET_TEXT_PEN &&
          f.events[2].pen == 8u && f.events[2].print_offset == 4u);
    CHECK(f.events[0].ink == 0u && f.events[1].colour == 0u);
    result = step(&f, sizeof(f.output), 1u);
    CHECK(result.status == BSR_OK);
    CHECK(f.written == 2u && f.event_written == 1u);
    CHECK(memcmp(f.output, "Z\n", 2u) == 0);
    CHECK(f.events[0].type == BE_VIDEO_SET_TEXT_PEN &&
          f.events[0].pen == 12u && f.events[0].print_offset == 0u);
    result = step(&f, sizeof(f.output), 1u);
    CHECK(result.status == BSR_OK && f.written == 0u && f.event_written == 0u);
    CHECK(step(&f, sizeof(f.output), 1u).status == BSR_END);
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

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    CHECK(oracle_token_and_listing() == 0);
    CHECK(new_pen_values_and_atomic_errors() == 0);
    CHECK(compare_sealed_pen_images(argv[1]) == 0);
    CHECK(event_order_capacity_and_legacy() == 0);
    CHECK(new_pen_mixed_print_event_order() == 0);
    CHECK(direct_runtime_and_bad_tokens() == 0);
    puts("basic_pen_events: OK");
    return 0;
}
