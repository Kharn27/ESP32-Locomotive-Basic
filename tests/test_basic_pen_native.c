/* J1.17-B: source/RAM CPC witnesses, typed PEN vs PRINT, atomic failure. */
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
    uint8_t storage[512];
    BasicSessionRuntime runtime;
    uint8_t scratch[128];
    uint8_t out[128];
    size_t written;
    BEVideoEvent events[2];
    size_t event_written;
} Harness;

static int setup(Harness *h)
{
    memset(h, 0, sizeof(*h));
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(bsr_init(&h->runtime, &h->program).status == BSR_OK);
    return 0;
}

static BSRResult submit(Harness *h, const char *s)
{
    return bsr_submit(&h->runtime, (const uint8_t *)s, strlen(s),
                      h->scratch, sizeof(h->scratch), h->out,
                      sizeof(h->out), &h->written);
}

static BSRResult event_step(Harness *h, size_t out_cap, size_t event_cap)
{
    return bsr_step_with_events(&h->runtime, h->out, out_cap, &h->written,
                                h->events, event_cap, &h->event_written);
}

typedef struct {
    const char *source;
    uint8_t bytes[4];
    size_t n;
    int value;
    BEStatus diagnostic;
} Witness;

static const Witness witnesses[] = {
    {"PEN 0",  {0xbbu,0x20u,0x0eu,0}, 3u, 0, BE_OK},
    {"PEN 1",  {0xbbu,0x20u,0x0fu,0}, 3u, 1, BE_OK},
    {"PEN 2",  {0xbbu,0x20u,0x10u,0}, 3u, 2, BE_OK},
    {"PEN 3",  {0xbbu,0x20u,0x11u,0}, 3u, 3, BE_OK},
    {"PEN 4",  {0xbbu,0x20u,0x12u,0}, 3u, 4, BE_OK},
    {"PEN 15", {0xbbu,0x20u,0x19u,0x0fu}, 4u, 15, BE_OK},
    {"PEN 16", {0xbbu,0x20u,0x19u,0x10u}, 4u, 16, BE_PEN_RANGE},
    {"PEN -1", {0xbbu,0x20u,0xf5u,0x0fu}, 4u, -1, BE_PEN_RANGE}
};

static int test_witnesses(void)
{
    size_t i;
    for (i = 0u; i < sizeof(witnesses)/sizeof(witnesses[0]); ++i) {
        const Witness *w = &witnesses[i];
        Harness h;
        uint8_t encoded[32], listed[32];
        char line[40], listed_program[80];
        size_t n = 99u, l = 99u;
        BasicSessionRuntime before;
        BEVideoEvent event_before[2];
        uint8_t out_before[128];
        BSRResult r;
        CHECK(setup(&h) == 0);
        CHECK(bt_tokenize((const uint8_t *)w->source, strlen(w->source),
                          encoded, sizeof(encoded), &n) == BT_OK);
        CHECK(n == w->n && memcmp(encoded, w->bytes, n) == 0);
        CHECK(bl_detokenize(encoded, n, listed, sizeof(listed), &l) == BL_OK);
        CHECK(l == strlen(w->source) &&
              memcmp(listed, w->source, l) == 0);
        CHECK(snprintf(line, sizeof(line), "10 %s", w->source) > 0);
        CHECK(submit(&h, line).status == BSR_OK);
        CHECK(submit(&h, "20 PRINT \"X\"").status == BSR_OK);
        CHECK(submit(&h, "30 END").status == BSR_OK);
        CHECK(submit(&h, "LIST").status == BSR_OK);
        CHECK(snprintf(listed_program, sizeof(listed_program),
                       "10 %s\n20 PRINT \"X\"\n30 END\n", w->source) > 0);
        CHECK(h.written == strlen(listed_program) &&
              memcmp(h.out, listed_program, h.written) == 0);
        CHECK(submit(&h, "RUN").status == BSR_OK);
        memset(h.out, 0xa5, sizeof(h.out));
        memset(h.events, 0x5a, sizeof(h.events));
        h.written = 123u;
        h.event_written = 456u;
        before = h.runtime;
        memcpy(event_before, h.events, sizeof(event_before));
        memcpy(out_before, h.out, sizeof(out_before));
        r = bsr_step(&h.runtime, h.out, sizeof(h.out), &h.written);
        CHECK(r.status == BSR_EXECUTOR_ERROR &&
              r.executor_status == (w->diagnostic == BE_OK ?
                                     BE_EVENT_REQUIRED : w->diagnostic));
        CHECK(memcmp(&before, &h.runtime, sizeof(before)) == 0);
        CHECK(h.written == 123u &&
              memcmp(h.out, out_before, sizeof(h.out)) == 0);
        if (w->diagnostic == BE_OK) {
            r = event_step(&h, sizeof(h.out), 0u);
            CHECK(r.status == BSR_EXECUTOR_ERROR &&
                  r.executor_status == BE_EVENT_NO_SPACE);
            CHECK(memcmp(&before, &h.runtime, sizeof(before)) == 0);
            CHECK(h.event_written == 456u &&
                  memcmp(h.events, event_before, sizeof(h.events)) == 0);
        }
        r = event_step(&h, sizeof(h.out), 1u);
        if (w->diagnostic != BE_OK) {
            CHECK(r.status == BSR_EXECUTOR_ERROR &&
                  r.executor_status == w->diagnostic);
            CHECK(memcmp(&before, &h.runtime, sizeof(before)) == 0);
            CHECK(h.event_written == 456u && h.written == 123u);
            CHECK(memcmp(h.events, event_before, sizeof(h.events)) == 0);
            CHECK(memcmp(h.out, out_before, sizeof(h.out)) == 0);
            continue;
        }
        CHECK(r.status == BSR_OK && h.written == 0u);
        CHECK(h.event_written == 1u &&
              h.events[0].type == BE_VIDEO_SET_TEXT_PEN &&
              h.events[0].pen == (uint8_t)w->value);
        CHECK(h.events[1].type == event_before[1].type &&
              h.events[1].pen == event_before[1].pen);
        CHECK(memcmp(h.out, out_before, sizeof(h.out)) == 0);
        h.event_written = 999u;
        memset(h.out, 0x73, sizeof(h.out));
        CHECK(event_step(&h, 1u, 0u).status == BSR_EXECUTOR_ERROR);
        CHECK(h.event_written == 999u && h.out[0] == 0x73u);
        CHECK(event_step(&h, 2u, 0u).status == BSR_OK);
        CHECK(h.written == 2u && memcmp(h.out, "X\n", 2u) == 0);
        CHECK(h.event_written == 0u && h.events[0].pen == (uint8_t)w->value);
        CHECK(event_step(&h, sizeof(h.out), 0u).status == BSR_OK);
        CHECK(h.written == 0u && h.event_written == 0u);
        CHECK(event_step(&h, sizeof(h.out), 0u).status == BSR_END);
        CHECK(h.runtime.state == BSR_IDLE);
    }
    return 0;
}

static int test_unverified_and_bad_source(void)
{
    unsigned int v;
    static const char *bad[] = {
        "PEN", "PEN 1:PRINT 1", "PEN 1,2", "PEN -2",
        "PEN A%", "PEN 1+1", "PEN 17", "PEN0"
    };
    size_t i;
    uint8_t token[32];
    for (i=0u;i<sizeof(bad)/sizeof(bad[0]);++i) {
        size_t written = 777u;
        memset(token, 0x69, sizeof(token));
        CHECK(bt_tokenize((const uint8_t *)bad[i], strlen(bad[i]),
                          token, sizeof(token), &written) != BT_OK);
        CHECK(written == 777u && token[0] == 0x69u);
    }
    for (v=5u;v<=14u;++v) {
        Harness h;
        char input[40];
        BasicSessionRuntime before;
        BEVideoEvent e0;
        CHECK(setup(&h) == 0);
        CHECK(snprintf(input, sizeof(input), "10 PEN %u", v) > 0);
        CHECK(submit(&h, input).status == BSR_OK);
        CHECK(submit(&h, "RUN").status == BSR_OK);
        memset(h.events, 0x6a, sizeof(h.events));
        memset(h.out, 0xa3, sizeof(h.out));
        h.written = 99u;
        h.event_written = 88u;
        before = h.runtime;
        e0 = h.events[0];
        {
            BSRResult r = event_step(&h, sizeof(h.out), 1u);
            CHECK(r.status == BSR_EXECUTOR_ERROR &&
                  r.executor_status == BE_PEN_UNVERIFIED);
        }
        CHECK(memcmp(&before, &h.runtime, sizeof(before)) == 0);
        CHECK(h.written == 99u && h.event_written == 88u);
        CHECK(h.out[0] == 0xa3u &&
              memcmp(&h.events[0], &e0, sizeof(e0)) == 0);
    }
    return 0;
}

static int test_raw_and_aliasing(void)
{
    static const struct {
        uint8_t bytes[7];
        size_t n;
        BEStatus status;
    } invalid[] = {
        {{0xbbu,0x20u},2u,BE_TRUNCATED},
        {{0xbbu,0x20u,0x19u},3u,BE_TRUNCATED},
        {{0xbbu,0x20u,0xf5u},3u,BE_TRUNCATED},
        {{0xbbu,0x20u,0x19u,0x04u},4u,BE_BAD_SEQUENCE},
        {{0xbbu,0x20u,0x10u,0x01u,0xbfu},5u,BE_BAD_SEQUENCE},
        {{0xbbu,0x20u,0x0eu,0xffu},4u,BE_BAD_SEQUENCE},
        {{0xbbu,0x20u,0xf5u,0x10u},4u,BE_BAD_SEQUENCE}
    };
    size_t i;
    for (i=0u;i<sizeof(invalid)/sizeof(invalid[0]);++i) {
        Harness h;
        BEVideoEvent old_events[2];
        BasicSessionRuntime old_runtime;
        uint8_t old_output[128];
        CHECK(setup(&h) == 0);
        CHECK(bp_put(&h.program, 10u, invalid[i].bytes, invalid[i].n) == BP_OK);
        CHECK(submit(&h, "RUN").status == BSR_OK);
        memset(h.out, 0x93, sizeof(h.out));
        memset(h.events, 0x88, sizeof(h.events));
        h.written=123u;
        h.event_written=456u;
        old_runtime=h.runtime;
        memcpy(old_output,h.out,sizeof(old_output));
        memcpy(old_events,h.events,sizeof(old_events));
        {
            BSRResult r=event_step(&h,sizeof(h.out),2u);
            CHECK(r.status==BSR_EXECUTOR_ERROR &&
                  r.executor_status==invalid[i].status);
        }
        CHECK(memcmp(&h.runtime,&old_runtime,sizeof(old_runtime))==0 &&
              memcmp(h.out,old_output,sizeof(old_output))==0 &&
              memcmp(h.events,old_events,sizeof(old_events))==0 &&
              h.written==123u && h.event_written==456u);
    }
    {
        Harness h;
        BEVideoEvent before[2];
        BasicSessionRuntime runtime_before;
        CHECK(setup(&h) == 0);
        CHECK(submit(&h,"10 PEN 4").status==BSR_OK);
        CHECK(submit(&h,"RUN").status==BSR_OK);
        h.written=9u;h.event_written=17u;
        memcpy(before,h.events,sizeof(before));
        runtime_before=h.runtime;
        CHECK(bsr_step_with_events(&h.runtime,h.out,sizeof(h.out),&h.written,
                  (BEVideoEvent *)(void *)h.out,1u,&h.event_written).status
                  ==BSR_OVERLAP);
        CHECK(bsr_step_with_events(&h.runtime,h.out,sizeof(h.out),&h.written,
                  h.events,1u,&h.written).status==BSR_OVERLAP);
        CHECK(bsr_step_with_events(&h.runtime,h.out,sizeof(h.out),&h.written,
                  h.events,1u,NULL).status==BSR_INVALID_ARGUMENT);
        CHECK(bsr_step_with_events(&h.runtime,h.out,sizeof(h.out),&h.written,
                  NULL,0u,&h.event_written).status==BSR_INVALID_ARGUMENT);
        CHECK(h.written==9u && h.event_written==17u &&
              memcmp(&h.runtime,&runtime_before,sizeof(runtime_before))==0 &&
              memcmp(h.events,before,sizeof(before))==0);
    }
    return 0;
}

int main(void)
{
    CHECK(test_witnesses()==0);
    CHECK(test_unverified_and_bad_source()==0);
    CHECK(test_raw_and_aliasing()==0);
    puts("j1_17_b_pen_native: OK");
    return 0;
}
