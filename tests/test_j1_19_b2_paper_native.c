/* J1.19-B2 — sealed CPC PAPER literals, native events and atomic rejection.
 * The CPC archive is read independently by basic_listing (original/repeat);
 * these numeric records are its L20 witnesses, not simulated CPC execution. */
#include "basic_session_runtime.h"
#include "basic_listing.h"
#include "basic_tokenizer.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "J1.19-B2 %s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

enum { IMAGE_CAP=1024, OUT_CAP=128, EV_CAP=8, ENTRIES=4, ARENA=64 };
typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    BasicVariableStore store;
    BasicVariableEntry entries[ENTRIES];
    uint8_t arena[ARENA];
    uint8_t image[IMAGE_CAP], temporary[256], output[OUT_CAP];
    BEVideoEvent events[EV_CAP];
    size_t written, event_written;
} Fixture;

static Fixture f;
static int setup(void)
{
    memset(&f, 0x59, sizeof(f));
    CHECK(bp_init(&f.program, f.image, sizeof(f.image)) == BP_OK);
    CHECK(bvs_init_with_arena(&f.store, f.entries, ENTRIES, f.arena, ARENA) == BVS_OK);
    CHECK(bsr_init_with_store(&f.runtime, &f.program, &f.store).status == BSR_OK);
    return 0;
}
static BSRResult submit(const char *line)
{
    return bsr_submit(&f.runtime, (const uint8_t *)line, strlen(line),
                      f.temporary, sizeof(f.temporary), f.output,
                      sizeof(f.output), &f.written);
}
static void canaries(void)
{
    memset(f.output, 0x6a, sizeof(f.output));
    memset(f.events, 0x75, sizeof(f.events));
    f.written = 777u;
    f.event_written = 888u;
}
static int unchanged(const Fixture *before)
{
    CHECK(memcmp(&f, before, sizeof(f)) == 0);
    return 0;
}
static int rejected(BEStatus cause, size_t outcap, size_t eventcap,
                    int preview, int no_receiver, int legacy)
{
    Fixture before;
    BSRResult r;
    memcpy(&before, &f, sizeof(f));
    if (legacy) {
        r = bsr_step(&f.runtime, f.output, outcap, &f.written);
    } else if (preview) {
        r = bsr_preview_step_events(&f.runtime, f.output, outcap, &f.written,
              no_receiver ? NULL : f.events, eventcap, &f.event_written);
    } else {
        r = bsr_step_events(&f.runtime, f.output, outcap, &f.written,
              no_receiver ? NULL : f.events, eventcap, &f.event_written);
    }
    CHECK(r.status == BSR_EXECUTOR_ERROR && r.executor_status == cause);
    CHECK(unchanged(&before) == 0);
    return 0;
}
static int paper_payload(const BEVideoEvent *e, uint8_t value, size_t offset)
{
    CHECK(e->type == BE_VIDEO_SET_TEXT_PAPER);
    CHECK(e->pen == 0u && e->ink == value && e->colour == 0u);
    CHECK(e->print_offset == offset);
    return 0;
}
static int matrix(void)
{
    static const struct {
        const char *literal, *id;
        uint8_t body[4];
        size_t size;
        unsigned int value;
        BEStatus status;
    } cases[] = {
        {"0",  "P00", {0xbau,' ',0x0eu},       3u, 0u,  BE_OK},
        {"1",  "P01", {0xbau,' ',0x0fu},       3u, 1u,  BE_OK},
        {"2",  "P02", {0xbau,' ',0x10u},       3u, 2u,  BE_OK},
        {"3",  "P03", {0xbau,' ',0x11u},       3u, 3u,  BE_OK},
        {"4",  "P04", {0xbau,' ',0x12u},       3u, 4u,  BE_OK},
        {"15", "P15", {0xbau,' ',0x19u,0x0fu}, 4u, 15u, BE_OK},
        {"16", "P16", {0xbau,' ',0x19u,0x10u}, 4u, 16u, BE_INVALID_PAPER},
        {"-1", "PN1", {0xbau,' ',0xf5u,0x0fu}, 4u, 0u,  BE_INVALID_PAPER}
    };
    size_t i;
    CHECK(offsetof(BEVideoEvent, print_offset) > offsetof(BEVideoEvent, pen));
    CHECK(offsetof(BEVideoEvent, ink) ==
          offsetof(BEVideoEvent, print_offset) + sizeof(size_t));
    CHECK(offsetof(BEVideoEvent, colour) == offsetof(BEVideoEvent, ink) + 1u);
#if defined(ESP_PLATFORM)
    CHECK(sizeof(BEVideoEvent) == 16u);
    CHECK(offsetof(BEVideoEvent, print_offset) == 8u);
#endif
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        uint8_t encoded[16], listed[32];
        uint8_t preview_out[OUT_CAP], commit_out[OUT_CAP];
        BEVideoEvent preview_ev[EV_CAP], commit_ev[EV_CAP];
        Fixture before;
        size_t n = 55u, ln = 44u, pbytes = 222u, pevents = 333u;
        size_t cbytes = 444u, cevents = 555u;
        char command[40], expected[40];
        BSRResult p, c;
        CHECK(setup() == 0);
        CHECK(snprintf(command, sizeof(command), "20 PAPER %s", cases[i].literal) > 0);
        CHECK(snprintf(expected, sizeof(expected), "PAPER %s", cases[i].literal) > 0);
        memset(encoded, 0x51, sizeof(encoded));
        CHECK(bt_tokenize((const uint8_t *)expected, strlen(expected),
                          encoded, sizeof(encoded), &n) == BT_OK);
        CHECK(n == cases[i].size);
        CHECK(memcmp(encoded, cases[i].body, n) == 0 && encoded[n] == 0x51u);
        CHECK(bl_detokenize(encoded, n, listed, sizeof(listed), &ln) == BL_OK);
        CHECK(ln == strlen(expected) && memcmp(listed, expected, ln) == 0);
        CHECK(submit(command).status == BSR_OK);
        /* Exact independently archived CPC L20 record body, including
         * LE16 length, line number and terminal NUL; no ASCII parsing. */
        CHECK(f.image[0] == (uint8_t)(n + 5u) && f.image[1] == 0u);
        CHECK(f.image[2] == 20u && f.image[3] == 0u);
        CHECK(memcmp(f.image + 4u, cases[i].body, n) == 0);
        CHECK(f.image[n + 4u] == 0u);
        CHECK(submit("RUN").status == BSR_OK);
        canaries();
        if (cases[i].status != BE_OK) {
            CHECK(rejected(BE_INVALID_PAPER, sizeof(f.output), EV_CAP, 1, 0, 0) == 0);
            CHECK(rejected(BE_INVALID_PAPER, sizeof(f.output), EV_CAP, 0, 0, 0) == 0);
            CHECK(rejected(BE_INVALID_PAPER, sizeof(f.output), 0u, 0u, 1, 0) == 0);
            CHECK(rejected(BE_INVALID_PAPER, sizeof(f.output), 0u, 0, 0, 1) == 0);
            /* ERR=5/ERL=20 belongs ONLY to the independent CPC oracle;
             * this C99 result is a typed host cause, not a CPC number. */
        } else {
            CHECK(rejected(BE_EVENT_RECEIVER_REQUIRED, sizeof(f.output), 0u, 0, 1, 0) == 0);
            CHECK(rejected(BE_EVENT_RECEIVER_REQUIRED, sizeof(f.output), 0u, 1, 1, 0) == 0);
            CHECK(rejected(BE_EVENT_RECEIVER_REQUIRED, sizeof(f.output), 0u, 0, 0, 1) == 0);
            CHECK(rejected(BE_NO_EVENT_SPACE, sizeof(f.output), 0u, 0, 0, 0) == 0);
            CHECK(rejected(BE_NO_EVENT_SPACE, sizeof(f.output), 0u, 1, 0, 0) == 0);
            memset(preview_out, 0x6au, sizeof(preview_out));
            memset(commit_out, 0x6au, sizeof(commit_out));
            memset(preview_ev, 0x75, sizeof(preview_ev));
            memset(commit_ev, 0x75, sizeof(commit_ev));
            memcpy(&before, &f, sizeof(f));
            p = bsr_preview_step_events(&f.runtime, preview_out, sizeof(preview_out),
                    &pbytes, preview_ev, EV_CAP, &pevents);
            CHECK(p.status == BSR_OK && pbytes == 0u && pevents == 1u);
            CHECK(unchanged(&before) == 0);
            CHECK(paper_payload(&preview_ev[0], (uint8_t)cases[i].value, 0u) == 0);
            c = bsr_step_events(&f.runtime, commit_out, sizeof(commit_out),
                    &cbytes, commit_ev, EV_CAP, &cevents);
            CHECK(c.status == BSR_OK && cbytes == pbytes && cevents == pevents);
            CHECK(memcmp(preview_out, commit_out, sizeof(commit_out)) == 0);
            CHECK(memcmp(preview_ev, commit_ev, sizeof(commit_ev)) == 0);
            CHECK(paper_payload(&commit_ev[0], (uint8_t)cases[i].value, 0u) == 0);
            CHECK(commit_out[0] == 0x6au && commit_ev[1].pen == 0x75u);
            CHECK(f.runtime.executor.cursor != before.runtime.executor.cursor);
        }
        printf("%s: %s (L20 RAM exact; native %s)\n", cases[i].id,
               cases[i].literal, cases[i].status == BE_OK ? "EVENT" : "INVALID_PAPER");
    }
    return 0;
}
static int mixed_events(void)
{
    BSRResult r;
    CHECK(setup() == 0);
    CHECK(submit("20 PEN 1:PRINT \"A\":PAPER 2:CLS:INK 1,26:PRINT \"B\"").status == BSR_OK);
    CHECK(submit("30 END").status == BSR_OK);
    CHECK(submit("RUN").status == BSR_OK);
    canaries();
    CHECK(rejected(BE_NO_EVENT_SPACE, OUT_CAP, 3u, 0, 0, 0) == 0);
    CHECK(rejected(BE_NO_SPACE, 3u, EV_CAP, 0, 0, 0) == 0);
    CHECK(rejected(BE_EVENT_RECEIVER_REQUIRED, OUT_CAP, 0u, 0, 1, 0) == 0);
    r = bsr_step_events(&f.runtime, f.output, OUT_CAP, &f.written,
                         f.events, EV_CAP, &f.event_written);
    CHECK(r.status == BSR_OK && f.written == 4u && f.event_written == 4u);
    CHECK(memcmp(f.output, "A\nB\n", 4u) == 0 && f.output[4] == 0x6au);
    CHECK(f.events[0].type == BE_VIDEO_SET_TEXT_PEN &&
          f.events[0].pen == 1u && f.events[0].ink == 0u &&
          f.events[0].print_offset == 0u);
    CHECK(paper_payload(&f.events[1], 2u, 2u) == 0);
    CHECK(f.events[2].type == BE_VIDEO_CLEAR_TEXT &&
          f.events[2].print_offset == 2u);
    CHECK(f.events[3].type == BE_VIDEO_SET_INK &&
          f.events[3].pen == 0u && f.events[3].ink == 1u &&
          f.events[3].colour == 26u && f.events[3].print_offset == 2u);
    CHECK(f.events[4].type == (BEVideoEventType)0x75757575u ||
          f.events[4].ink == 0x75u); /* untouched canary */
    return 0;
}
static int errors_and_noncanonical(void)
{
    static const struct {
        uint8_t bytes[7];
        size_t size;
        BEStatus expected;
    } broken[] = {
        {{0xbau,' ',0x19u},             3u, BE_TRUNCATED},
        {{0xbau,' ',0xf5u},             3u, BE_TRUNCATED},
        {{0xbau,' ',0x19u,0x09u},       4u, BE_BAD_SEQUENCE},
        {{0xbau,' ',0xf5u,0x10u},       4u, BE_BAD_SEQUENCE},
        {{0xbau,' ',0x13u},             3u, BE_UNSUPPORTED},
        {{0xbau,' ',0x19u,0x0eu},       4u, BE_UNSUPPORTED},
        {{0xbau,' ',0x88u},             3u, BE_UNKNOWN_TOKEN},
        {{0xbau,' ',0x0eu,','},         4u, BE_BAD_SEQUENCE},
        {{0xbau},                       1u, BE_BAD_SEQUENCE}
    };
    static const char *const invalid[] = {
        "PAPER 5", "PAPER 14", "PAPER #8,2", "PAPER A%",
        "PAPER 2.0", "PAPER 1+1", "PAPER 17"
    };
    size_t i;
    for (i=0u;i<sizeof(broken)/sizeof(broken[0]);++i) {
        CHECK(setup() == 0);
        CHECK(bp_put(&f.program, 20u, broken[i].bytes, broken[i].size) == BP_OK);
        CHECK(be_init_with_store(&f.runtime.executor, &f.program, &f.store) == BE_OK);
        f.runtime.state = BSR_RUNNING;
        canaries();
        CHECK(rejected(broken[i].expected, OUT_CAP, EV_CAP, 1, 0, 0) == 0);
        CHECK(rejected(broken[i].expected, OUT_CAP, EV_CAP, 0, 0, 0) == 0);
    }
    for (i=0u;i<sizeof(invalid)/sizeof(invalid[0]);++i) {
        uint8_t encoded[32], saved[32];
        size_t n=81u;
        memset(encoded, 0x81, sizeof(encoded));
        memcpy(saved, encoded, sizeof(saved));
        CHECK(bt_tokenize((const uint8_t *)invalid[i], strlen(invalid[i]),
                          encoded, sizeof(encoded), &n) != BT_OK);
        CHECK(n==81u && memcmp(encoded, saved, sizeof(encoded))==0);
    }
    /* No prefix PRINT, PAPER event, store or cursor may leak on any error. */
    for (i=0u;i<2u;++i) {
        CHECK(setup() == 0);
        CHECK(submit(i==0u ? "20 PRINT \"A\":PAPER 16:PRINT \"B\""
                           : "20 PAPER 2:PRINT \"A\":PAPER -1").status == BSR_OK);
        CHECK(submit("RUN").status == BSR_OK);
        canaries();
        CHECK(rejected(BE_INVALID_PAPER, OUT_CAP, EV_CAP, 1, 0, 0) == 0);
        CHECK(rejected(BE_INVALID_PAPER, OUT_CAP, EV_CAP, 0, 0, 0) == 0);
    }
    CHECK(setup() == 0);
    CHECK(submit("20 PAPER 1:PRINT \"A\"").status == BSR_OK);
    CHECK(submit("RUN").status == BSR_OK);
    canaries();
    CHECK(rejected(BE_NO_SPACE, 1u, EV_CAP, 1, 0, 0) == 0);
    CHECK(rejected(BE_NO_SPACE, 1u, EV_CAP, 0, 0, 0) == 0);
    return 0;
}
int main(void)
{
    CHECK(matrix() == 0);
    CHECK(mixed_events() == 0);
    CHECK(errors_and_noncanonical() == 0);
    puts("J1.19-B2 PAPER: 8/8 sealed syntax cases, typed events and atomic failures");
    return 0;
}
