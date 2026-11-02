/* J1.21-B2b: real BSR + transactional scheduler + MODE1 renderer.
 * Static caller-owned fixtures, no heap and no ESP32 emulation. */
#include "hw4_run_scheduler.h"
#include "hw4_pen_bridge.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d %s\n",     __FILE__, __LINE__, #x); return 1; } } while (0)
enum { PROGRAM=2048, OUTPUT=256, EVENTS=8, ENTRIES=12, ARENA=384 };
typedef struct {
    BasicProgram program;
    BasicVariableStore store;
    BasicVariableEntry entries[ENTRIES];
    uint8_t arena[ARENA];
    BasicSessionRuntime runtime;
    Hw4RunScheduler scheduler;
    CpcVideo video;
    CpcText text;
    uint8_t image[PROGRAM], temp[256], output[OUTPUT], vram[CPC_VIDEO_BYTES];
    BEVideoEvent events[EVENTS], preview_events[EVENTS];
    Hw4RunPreview preview;
    size_t written, event_written, replay_calls, preflight_calls;
    bool reject, replay_fail, corrupt_preview;
    Hw4PenStatus last_video;
} Fixture;
static Fixture f;
static uint8_t glyph(void *ignored, uint8_t c, unsigned row) {
    (void)ignored;
    return c == (uint8_t)' ' ? 0u : (row == 0u ? 0xffu : 0u);
}
static int setup(void) {
    memset(&f, 0, sizeof(f));
    CHECK(bp_init(&f.program, f.image, sizeof(f.image)) == BP_OK);
    CHECK(bvs_init_with_arena(&f.store, f.entries, ENTRIES,
                               f.arena, sizeof(f.arena)) == BVS_OK);
    CHECK(bsr_init_with_store(&f.runtime, &f.program, &f.store).status == BSR_OK);
    CHECK(cpc_video_init(&f.video, f.vram, sizeof(f.vram), CPC_MODE_1));
    CHECK(cpc_video_set_ink(&f.video, 0u, 1u));
    CHECK(cpc_video_set_ink(&f.video, 1u, 24u));
    CHECK(cpc_video_set_ink(&f.video, 2u, 6u));
    CHECK(cpc_video_set_ink(&f.video, 3u, 18u));
    CHECK(cpc_text_init(&f.text, &f.video, glyph, NULL));
    return 0;
}
static BSRResult submit(const char *line) {
    return bsr_submit(&f.runtime, (const uint8_t *)line, strlen(line),
           f.temp, sizeof(f.temp), f.output, sizeof(f.output), &f.written);
}
static int start(void) {
    CHECK(submit("RUN").status == BSR_OK);
    CHECK(hw4_run_scheduler_init(&f.scheduler, &f.runtime));
    f.preview=(Hw4RunPreview){f.temp,sizeof(f.temp),
                              f.preview_events,EVENTS,0u,0u};
    CHECK(hw4_run_scheduler_bind_preview(&f.scheduler, &f.preview));
    return 0;
}
static bool preflight(void *ctx, const uint8_t *bytes, size_t n,
                      const BEVideoEvent *events, size_t count) {
    Fixture *p = (Fixture *)ctx;
    ++p->preflight_calls;
    if (p->reject) return false;
    p->last_video = hw4_pen_preflight(&p->text, bytes, n, events, count);
    if (p->corrupt_preview && n > 0u) {
        /* Deliberate contract-violating injection, to exercise mismatch
         * fail-stop. Normal callbacks are pure. No video touched. */
        p->preview.output[0] ^= 1u;
    }
    return p->last_video == HW4_PEN_OK;
}
static bool replay(void *ctx, const uint8_t *bytes, size_t n,
                   const BEVideoEvent *events, size_t count) {
    Fixture *p = (Fixture *)ctx;
    if (p->replay_fail) return false;
    p->last_video = hw4_pen_replay(&p->text, bytes, n, events, count);
    if (p->last_video != HW4_PEN_OK) return false;
    ++p->replay_calls;
    return true;
}
static Hw4RunSlice step(unsigned quantum) {
    Hw4RunReceiver r = {preflight, replay, NULL, &f};
    return hw4_run_scheduler_slice(&f.scheduler, quantum, &r, f.output,
          sizeof(f.output), &f.written, f.events, EVENTS, &f.event_written);
}
typedef struct {
    BasicSessionRuntime runtime;
    BasicProgram program;
    BasicVariableStore store;
    BasicVariableEntry entries[ENTRIES];
    uint8_t image[PROGRAM], arena[ARENA], vram[CPC_VIDEO_BYTES];
    CpcVideo video;
    CpcText text;
    uint8_t output[OUTPUT];
    BEVideoEvent events[EVENTS];
    size_t written, event_written, steps;
} Snapshot;
static void capture(Snapshot *s) {
    s->runtime = f.runtime; s->program = f.program;
    s->store = f.store; s->video = f.video; s->text = f.text;
    memcpy(s->entries, f.entries, sizeof(s->entries));
    memcpy(s->image, f.image, sizeof(s->image));
    memcpy(s->arena, f.arena, sizeof(s->arena));
    memcpy(s->vram, f.vram, sizeof(s->vram));
    memcpy(s->output, f.output, sizeof(s->output));
    memcpy(s->events, f.events, sizeof(s->events));
    s->written = f.written; s->event_written = f.event_written;
    s->steps = f.scheduler.total_steps;
}
static int unchanged(const Snapshot *s) {
    CHECK(memcmp(&s->runtime, &f.runtime, sizeof(f.runtime)) == 0);
    CHECK(memcmp(&s->program, &f.program, sizeof(f.program)) == 0);
    CHECK(memcmp(&s->store, &f.store, sizeof(f.store)) == 0);
    CHECK(memcmp(s->entries, f.entries, sizeof(f.entries)) == 0);
    CHECK(memcmp(s->image, f.image, sizeof(f.image)) == 0);
    CHECK(memcmp(s->arena, f.arena, sizeof(f.arena)) == 0);
    CHECK(memcmp(s->vram, f.vram, sizeof(f.vram)) == 0);
    CHECK(memcmp(&s->video, &f.video, sizeof(f.video)) == 0);
    CHECK(memcmp(&s->text, &f.text, sizeof(f.text)) == 0);
    CHECK(memcmp(s->output, f.output, sizeof(f.output)) == 0);
    CHECK(memcmp(s->events, f.events, sizeof(f.events)) == 0);
    CHECK(s->written == f.written && s->event_written == f.event_written);
    CHECK(s->steps == f.scheduler.total_steps);
    return 0;
}
static int reject_case(const char *line, bool force, Hw4PenStatus reason) {
    static Snapshot before; Hw4RunSlice s;
    CHECK(setup() == 0);
    CHECK(submit(line).status == BSR_OK);
    CHECK(start() == 0);
    f.written = 123u; f.event_written = 77u;
    memset(f.output, 0x39, sizeof(f.output));
    memset(f.events, 0x48, sizeof(f.events));
    f.reject = force;
    capture(&before);
    s = step(4u);
    CHECK(s.state == HW4_RUN_DISPLAY_ERROR && s.steps == 0u);
    CHECK(f.scheduler.display_failure == HW4_RUN_DISPLAY_PREFLIGHT_FAILED);
    CHECK(f.scheduler.stop_calls == 0u && f.replay_calls == 0u);
    CHECK(f.preflight_calls == 1u && f.runtime.state == BSR_RUNNING);
    if (!force) CHECK(f.last_video == reason);
    CHECK(unchanged(&before) == 0);
    CHECK(step(1u).state == HW4_RUN_INVALID_ARGUMENT);
    return 0;
}
static int reject_after_assignment(const char *assign, const char *second) {
    static Snapshot before; Hw4RunSlice s;
    CHECK(setup() == 0);
    CHECK(submit(assign).status == BSR_OK);
    CHECK(submit(second).status == BSR_OK);
    CHECK(start() == 0);
    CHECK(step(1u).state == HW4_RUN_YIELDED);
    CHECK(f.scheduler.total_steps == 1u);
    f.written = 171u; f.event_written = 172u;
    memset(f.output, 0x35, sizeof(f.output));
    memset(f.events, 0x57, sizeof(f.events));
    f.reject = true;
    capture(&before);
    s = step(1u);
    CHECK(s.state == HW4_RUN_DISPLAY_ERROR && s.steps == 0u);
    CHECK(f.scheduler.display_failure == HW4_RUN_DISPLAY_PREFLIGHT_FAILED);
    CHECK(f.replay_calls == 1u && f.preflight_calls == 2u);
    CHECK(unchanged(&before) == 0);
    return 0;
}
/* Executable RED witness: reproduce BASE's old step-first scheduler order
 * (not the production scheduler). Video rejects only AFTER BSR committed.
 * GREEN uses reject_case() below to prove this path is eliminated. */
static int legacy_step_first_red_witness(void) {
    static Snapshot before;
    BSRResult old_step;
    CHECK(setup() == 0);
    CHECK(submit("10 PRINT \"NO\":INK 1,26:CLS").status == BSR_OK);
    CHECK(start() == 0);
    capture(&before);
    old_step = bsr_step_events(&f.runtime, f.output, sizeof(f.output),
                               &f.written, f.events, EVENTS, &f.event_written);
    CHECK(old_step.status == BSR_OK && f.written == 3u &&
          f.event_written == 2u);
    CHECK(hw4_pen_preflight(&f.text, f.output, f.written,
                           f.events, f.event_written) ==
          HW4_PEN_SET_INK_UNSUPPORTED);
    CHECK(f.runtime.executor.cursor != before.runtime.executor.cursor);
    CHECK(f.written != before.written);
    CHECK(!memcmp(f.vram, before.vram, sizeof(f.vram)));
    CHECK(!memcmp(f.image, before.image, sizeof(f.image)));
    puts("J1.21-B2b RED witness: step-first commits before rejected INK");
    return 0;
}
static int rejected_preflight_is_atomic(void) {
    /* Would fail with the old step -> preflight order: cursor advanced. */
    CHECK(reject_case("10 PRINT \"A\":CLS:PRINT \"B\"", true,
                      HW4_PEN_OK) == 0);
    CHECK(reject_after_assignment("10 A%=7", "20 PRINT A%:CLS") == 0);
    CHECK(reject_after_assignment("10 A$=\"X\"", "20 PRINT A$:CLS") == 0);
    CHECK(reject_case("10 PEN 2:PRINT \"NO\":INK 1,26:CLS",
                      false, HW4_PEN_SET_INK_UNSUPPORTED) == 0);
    return 0;
}
static int cls_program(void) {
    uint8_t paper_fill = (uint8_t)(2u * 0x55u);
    uint8_t pen, paper, inks[16];
    static uint8_t saved[PROGRAM];
    bool known = false; uint8_t c = 0u;
    CHECK(setup() == 0);
    CHECK(cpc_video_set_text_colors(&f.video, 1u, 2u));
    CHECK(cpc_text_write(&f.text, (const uint8_t *)"OLD", 3u));
    CHECK(submit("10 PRINT \"AVANT\"").status == BSR_OK);
    CHECK(submit("20 CLS").status == BSR_OK);
    CHECK(submit("30 PRINT \"APRES\"").status == BSR_OK);
    CHECK(submit("40 END").status == BSR_OK);
    memcpy(saved, f.image, sizeof(saved));
    CHECK(start() == 0);
    pen = f.video.pen; paper = f.video.paper;
    memcpy(inks, f.video.ink, sizeof(inks));
    CHECK(step(1u).state == HW4_RUN_YIELDED);
    CHECK(f.written == 6u && f.event_written == 0u);
    CHECK(step(1u).state == HW4_RUN_YIELDED);
    CHECK(f.written == 0u && f.event_written == 1u);
    CHECK(f.events[0].type == BE_VIDEO_CLEAR_TEXT);
    CHECK(f.text.column == 0u && f.text.row == 0u);
    CHECK(f.video.cursor_column == 0u && f.video.cursor_row == 0u);
    CHECK(f.video.dirty_bands == UINT32_C(0x01ffffff));
    for (size_t i = 0u; i < sizeof(f.vram); ++i)
        CHECK(f.vram[i] == paper_fill);
    CHECK(!memcmp(inks, f.video.ink, sizeof(inks)));
    CHECK(f.video.pen == pen && f.video.paper == paper);
    CHECK(cpc_video_read_cell(&f.video, 0u, 0u, &c, &known) && !known);
    CHECK(step(1u).state == HW4_RUN_YIELDED);
    CHECK(f.written == 6u && !memcmp(f.output, "APRES\n", 6u));
    CHECK(cpc_video_read_cell(&f.video, 0u, 0u, &c, &known) &&
          known && c == (uint8_t)'A');
    CHECK(step(2u).state == HW4_RUN_ENDED);
    CHECK(f.runtime.state == BSR_IDLE && f.scheduler.total_steps == 4u);
    CHECK(memcmp(saved, f.image, sizeof(saved)) == 0);
    CHECK(f.replay_calls == 4u);
    return 0;
}
static int ordered_inline(void) {
    bool known = false; uint8_t c = 0u;
    CHECK(setup() == 0);
    CHECK(submit("10 CLS:CLS").status == BSR_OK);
    CHECK(start() == 0);
    CHECK(step(1u).state == HW4_RUN_YIELDED);
    CHECK(f.event_written == 2u && f.written == 0u);
    CHECK(f.events[0].type == BE_VIDEO_CLEAR_TEXT);
    CHECK(f.events[1].type == BE_VIDEO_CLEAR_TEXT);
    CHECK(f.text.column == 0u && f.text.row == 0u);
    CHECK(setup() == 0);
    CHECK(submit("10 PRINT \"A\":CLS:PRINT \"B\"").status == BSR_OK);
    CHECK(start() == 0);
    CHECK(step(1u).state == HW4_RUN_YIELDED);
    CHECK(f.written == 4u && !memcmp(f.output, "A\nB\n", 4u));
    CHECK(f.event_written == 1u && f.events[0].print_offset == 2u);
    CHECK(cpc_video_read_cell(&f.video, 0u, 0u, &c, &known) &&
          known && c == (uint8_t)'B');
    CHECK(f.text.row == 1u && f.text.column == 0u);
    CHECK(setup() == 0);
    CHECK(submit("10 PEN 3:PRINT \"A\":CLS:PRINT \"B\"").status == BSR_OK);
    CHECK(start() == 0);
    CHECK(step(1u).state == HW4_RUN_YIELDED);
    CHECK(f.video.pen == 3u && f.video.ink[3] == 18u);
    CHECK(f.event_written == 2u && f.events[1].type == BE_VIDEO_CLEAR_TEXT);
    CHECK(cpc_video_read_cell(&f.video, 0u, 0u, &c, &known) &&
          known && c == (uint8_t)'B');
    return 0;
}
static int malformed_events_and_invalid_state(void) {
    static uint8_t pixels[CPC_VIDEO_BYTES];
    CpcVideo copy; BEVideoEvent e = {BE_VIDEO_CLEAR_TEXT, 0u, 1u, 0u, 0u};
    CHECK(setup() == 0);
    copy = f.video;
    memcpy(pixels, f.vram, sizeof(pixels));
    CHECK(hw4_pen_preflight(&f.text, (const uint8_t *)"", 0u, &e, 1u)
          == HW4_PEN_BAD_OFFSET);
    e.print_offset = 0u; e.pen = 1u;
    CHECK(hw4_pen_preflight(&f.text, (const uint8_t *)"", 0u, &e, 1u)
          == HW4_PEN_INVALID_EVENT);
    e.pen = 0u; e.type = (BEVideoEventType)99;
    CHECK(hw4_pen_preflight(&f.text, (const uint8_t *)"", 0u, &e, 1u)
          == HW4_PEN_INVALID_EVENT);
    CHECK(!memcmp(pixels, f.vram, sizeof(pixels)));
    CHECK(!memcmp(&copy, &f.video, sizeof(copy)));
    f.video.mode = CPC_MODE_0;
    CHECK(hw4_pen_preflight(&f.text, NULL, 0u, NULL, 0u)
          == HW4_PEN_TEXT_PRECHECK_FAILED);
    CHECK(!cpc_text_clear(&f.text));
    return 0;
}
static int replay_failure_and_mismatch(void) {
    CHECK(setup() == 0);
    CHECK(submit("10 PRINT \"A\":CLS").status == BSR_OK);
    CHECK(start() == 0);
    f.replay_fail = true;
    CHECK(step(4u).state == HW4_RUN_DISPLAY_ERROR);
    CHECK(f.scheduler.display_failure == HW4_RUN_DISPLAY_REPLAY_FAILED);
    CHECK(f.scheduler.total_steps == 1u && f.replay_calls == 0u);
    CHECK(f.runtime.executor.cursor != 0u);
    CHECK(step(1u).state == HW4_RUN_INVALID_ARGUMENT);
    CHECK(setup() == 0);
    CHECK(submit("10 PRINT \"B\":CLS").status == BSR_OK);
    CHECK(start() == 0);
    f.corrupt_preview = true;
    CHECK(step(1u).state == HW4_RUN_DISPLAY_ERROR);
    CHECK(f.scheduler.display_failure == HW4_RUN_DISPLAY_COMMIT_MISMATCH);
    CHECK(f.scheduler.total_steps == 0u && f.replay_calls == 0u);
    CHECK(f.runtime.state == BSR_RUNNING); /* no imaginary rollback */
    return 0;
}
int main(void) {
    CHECK(legacy_step_first_red_witness() == 0);
    CHECK(rejected_preflight_is_atomic() == 0);
    CHECK(cls_program() == 0);
    CHECK(ordered_inline() == 0);
    CHECK(malformed_events_and_invalid_state() == 0);
    CHECK(replay_failure_and_mismatch() == 0);
    puts("J1.21-B2b REAL_BSR VIDEO_CLS TRANSACTION PREFLIGHT_ATOMIC PASS");
    return 0;
}
