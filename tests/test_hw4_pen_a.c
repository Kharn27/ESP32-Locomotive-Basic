/* HW4-PEN-A: portable UART-like BASIC -> typed events -> MODE1 VRAM.
 * Does not simulate TFT hardware. Oracle A defines only 0..4 and 15. */
#include "hw4_pen_bridge.h"
#include "cpc_uart_console.h"
#include "cpc_diag_policy.h"
#include "cpc_ready_policy.h"
#include "basic_session_runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { OUT_CAP = 256, EVENT_CAP = 16 };
typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    uint8_t program_bytes[2048];
    uint8_t temp[256];
    uint8_t output[OUT_CAP];
    size_t written;
    BEVideoEvent events[EVENT_CAP];
    size_t event_written;
    CpcVideo video;
    CpcText text;
    uint8_t vram[CPC_VIDEO_BYTES];
} Fixture;
static Fixture f;

static uint8_t glyph(void *ctx, uint8_t ch, unsigned row)
{
    (void)ctx;
    return row == 0U && ch != (uint8_t)' ' ? 0x80U : 0U;
}

static void setup(void)
{
    memset(&f, 0x7a, sizeof(f));
    assert(bp_init(&f.program, f.program_bytes,
                   sizeof(f.program_bytes)) == BP_OK);
    assert(bsr_init(&f.runtime, &f.program).status == BSR_OK);
    assert(cpc_video_init(&f.video, f.vram, sizeof(f.vram), CPC_MODE_1));
    assert(cpc_video_set_ink(&f.video, 0U, 1U)); /* boot blue */
    assert(cpc_video_set_ink(&f.video, 1U, 24U)); /* boot yellow */
    assert(cpc_video_set_ink(&f.video, 2U, 6U)); /* configured red */
    assert(cpc_video_set_ink(&f.video, 3U, 18U)); /* configured green */
    assert(cpc_video_set_text_colors(&f.video, 1U, 0U));
    assert(cpc_text_init(&f.text, &f.video, glyph, NULL));
    assert(f.video.pen == 1U && f.video.paper == 0U);
    assert(f.video.ink[0] == 1U && f.video.ink[1] == 24U);
}

static BSRResult submit(const char *source)
{
    return bsr_submit(&f.runtime, (const uint8_t *)source, strlen(source),
                      f.temp, sizeof(f.temp), f.output, sizeof(f.output),
                      &f.written);
}

static BSRResult step(size_t out_capacity, size_t event_capacity)
{
    return bsr_step_events(&f.runtime, f.output, out_capacity, &f.written,
                           f.events, event_capacity, &f.event_written);
}

static uint8_t pixel_at(unsigned x, unsigned y)
{
    uint8_t pen = 255U;
    assert(cpc_video_get(&f.video, x, y, &pen));
    return pen;
}

static void assert_colour(unsigned row, uint8_t expected)
{
    uint16_t rgb[CPC_VIDEO_TFT_WIDTH];
    assert(pixel_at(0U, row * 8U) == expected);
    assert(cpc_video_render_row(&f.video, CPC_VIDEO_VIEW_TOP + row * 8U,
                                rgb, CPC_VIDEO_TFT_WIDTH));
    assert(rgb[0] == cpc_video_palette_rgb565(f.video.ink[expected]));
}

static uint32_t fnv(const uint8_t *p, size_t n)
{
    uint32_t value = UINT32_C(2166136261);
    size_t i;
    for (i = 0U; i < n; ++i)
        value = (value ^ p[i]) * UINT32_C(16777619);
    return value;
}

static void test_order_and_preserved_print(void)
{
    uint8_t prior = 0U;
    bool known = false;
    static const uint8_t expected[] = {'A','\n','B','\n'};
    setup();
    assert(submit("10 PEN 2:PRINT \"A\":PEN 1:PRINT \"B\"").status == BSR_OK);
    assert(submit("20 PEN 3:PRINT \"C\"").status == BSR_OK);
    assert(submit("30 END").status == BSR_OK);
    assert(submit("RUN").status == BSR_OK);
    assert(step(OUT_CAP, EVENT_CAP).status == BSR_OK);
    assert(f.written == sizeof(expected) && f.event_written == 2U);
    assert(memcmp(f.output, expected, sizeof(expected)) == 0);
    assert(f.events[0].type == BE_VIDEO_SET_TEXT_PEN &&
           f.events[0].pen == 2U && f.events[0].print_offset == 0U);
    assert(f.events[1].type == BE_VIDEO_SET_TEXT_PEN &&
           f.events[1].pen == 1U && f.events[1].print_offset == 2U);
    assert(hw4_pen_preflight(&f.text,f.output,f.written,f.events,
                             f.event_written) == HW4_PEN_OK);
    assert(hw4_pen_replay(&f.text,f.output,f.written,f.events,
                          f.event_written) == HW4_PEN_OK);
    assert(f.text.bytes_received == 4U && f.text.glyphs_drawn == 2U);
    assert(f.text.input_fnv1a == fnv(expected,sizeof(expected)));
    assert_colour(0U, 2U);
    assert_colour(1U, 1U);
    assert(cpc_video_read_cell(&f.video,0U,0U,&prior,&known));
    assert(known && prior == (uint8_t)'A');
    assert(cpc_video_read_cell(&f.video,0U,1U,&prior,&known));
    assert(known && prior == (uint8_t)'B');
    assert(step(OUT_CAP, EVENT_CAP).status == BSR_OK);
    assert(f.written == 2U && f.event_written == 1U);
    assert(memcmp(f.output,"C\n",2U) == 0);
    assert(f.events[0].pen == 3U && f.events[0].print_offset == 0U);
    assert(hw4_pen_replay(&f.text,f.output,f.written,f.events,
                          f.event_written) == HW4_PEN_OK);
    assert_colour(2U, 3U);
    assert(f.text.bytes_received == 6U && f.text.glyphs_drawn == 3U);
    assert(step(OUT_CAP, EVENT_CAP).status == BSR_OK);
    assert(f.written == 0U && f.event_written == 0U);
    assert(hw4_pen_replay(&f.text,f.output,0U,f.events,0U) == HW4_PEN_OK);
    assert(step(OUT_CAP, EVENT_CAP).status == BSR_END);
}

static void test_pen_only_and_oracle_bounds(void)
{
    setup();
    assert(submit("10 PEN 4").status == BSR_OK);
    assert(submit("20 PRINT \"D\"").status == BSR_OK);
    assert(submit("30 PEN 15").status == BSR_OK);
    assert(submit("40 PRINT \"E\"").status == BSR_OK);
    assert(submit("RUN").status == BSR_OK);
    assert(step(OUT_CAP, EVENT_CAP).status == BSR_OK);
    assert(f.written == 0U && f.event_written == 1U);
    assert(f.events[0].pen == 4U);
    assert(hw4_pen_replay(&f.text,f.output,0U,f.events,1U) == HW4_PEN_OK);
    assert(f.video.pen == 0U && f.text.bytes_received == 0U);
    assert(step(OUT_CAP, EVENT_CAP).status == BSR_OK);
    assert(f.event_written == 0U && f.written == 2U);
    assert(hw4_pen_replay(&f.text,f.output,f.written,f.events,0U) == HW4_PEN_OK);
    assert_colour(0U, 0U); /* on boot, blue-on-blue, NOT black-on-black */
    assert(step(OUT_CAP, EVENT_CAP).status == BSR_OK);
    assert(f.written == 0U && f.event_written == 1U);
    assert(f.events[0].pen == 15U);
    assert(hw4_pen_replay(&f.text,f.output,0U,f.events,1U) == HW4_PEN_OK);
    assert(f.video.pen == 3U);
    assert_colour(0U, 0U); /* retroactive recolouring forbidden */
    assert(step(OUT_CAP, EVENT_CAP).status == BSR_OK);
    assert(hw4_pen_replay(&f.text,f.output,f.written,f.events,
                          f.event_written) == HW4_PEN_OK);
    assert_colour(1U, 3U);
    assert(f.text.bytes_received == 4U && f.text.glyphs_drawn == 2U);
    /* Under the actual CPC-oracle black background, 4 -> 0 is black. */
    assert(cpc_video_set_ink(&f.video,0U,0U));
    {
        uint8_t mapped = 255U;
        assert(hw4_pen_pixel_index(&f.video,4U,&mapped) == HW4_PEN_OK);
        assert(mapped == 0U && cpc_video_palette_rgb565(f.video.ink[0]) == 0U);
    }
}

static void assert_rejected_replay(const BEVideoEvent *events, size_t count,
                                   const uint8_t *bytes, size_t length,
                                   Hw4PenStatus expected)
{
    CpcVideo before_video=f.video;
    CpcText before_text=f.text;
    uint8_t before_vram[CPC_VIDEO_BYTES];
    memcpy(before_vram,f.vram,sizeof(before_vram));
    assert(hw4_pen_preflight(&f.text,bytes,length,events,count)==expected);
    assert(hw4_pen_replay(&f.text,bytes,length,events,count)==expected);
    assert(memcmp(&f.video,&before_video,sizeof(f.video))==0);
    assert(memcmp(&f.text,&before_text,sizeof(f.text))==0);
    assert(memcmp(f.vram,before_vram,sizeof(before_vram))==0);
}

static void test_bridge_preflight_atomic(void)
{
    const uint8_t print_bytes[]={'X','\n','Y','\n'};
    BEVideoEvent events[2]={{BE_VIDEO_SET_TEXT_PEN,2U,0U,0U,0U},
                             {BE_VIDEO_SET_TEXT_PEN,1U,2U,0U,0U}};
    setup();
    events[1].type=(BEVideoEventType)99;
    assert_rejected_replay(events,2U,print_bytes,sizeof(print_bytes),
                           HW4_PEN_INVALID_EVENT);
    events[1].type=BE_VIDEO_SET_TEXT_PEN;
    events[1].print_offset=sizeof(print_bytes)+1U;
    assert_rejected_replay(events,2U,print_bytes,sizeof(print_bytes),
                           HW4_PEN_BAD_OFFSET);
    events[0].print_offset=3U;
    events[1].print_offset=2U;
    assert_rejected_replay(events,2U,print_bytes,sizeof(print_bytes),
                           HW4_PEN_BAD_OFFSET);
    events[0].print_offset=0U;
    events[1].pen=16U;
    assert_rejected_replay(events,2U,print_bytes,sizeof(print_bytes),
                           HW4_PEN_UNSUPPORTED_LOGICAL);
    events[1].pen=5U;
    assert_rejected_replay(events,2U,print_bytes,sizeof(print_bytes),
                           HW4_PEN_UNSUPPORTED_LOGICAL);
    events[1].pen=15U;
    f.video.ink[3]=6U; /* No generalised logical->pixel palette alias. */
    assert_rejected_replay(events,2U,print_bytes,sizeof(print_bytes),
                           HW4_PEN_UNVERIFIED_VISUAL);
    f.video.ink[3]=18U;
    events[1].pen=4U;
    f.video.ink[0]=3U; /* Outside both documented pen4 contexts. */
    assert_rejected_replay(events,2U,print_bytes,sizeof(print_bytes),
                           HW4_PEN_UNVERIFIED_VISUAL);
    f.video.ink[0]=1U;
    assert_rejected_replay(NULL,1U,print_bytes,sizeof(print_bytes),
                           HW4_PEN_INVALID_ARGUMENT);
    assert_rejected_replay(events,2U,NULL,sizeof(print_bytes),
                           HW4_PEN_INVALID_ARGUMENT);
}

static void test_runtime_atomic_and_diagnostics(void)
{
    static const char *bad[]={"PEN 16","PEN -1","PEN 5","PEN 14"};
    static const BEStatus expected[]={BE_INVALID_PEN,BE_INVALID_PEN,
                                       BE_UNSUPPORTED,BE_UNSUPPORTED};
    size_t i;
    for(i=0U;i<4U;++i) {
        BasicSessionRuntime original;
        uint8_t out_copy[OUT_CAP];
        BEVideoEvent events_copy[EVENT_CAP];
        size_t written_copy, event_copy;
        BSRResult result;
        setup();
        {
            char cmd[48];
            int n=snprintf(cmd,sizeof(cmd),"10 PEN 2:PRINT \"Z\":%s",bad[i]);
            assert(n>0 && (size_t)n<sizeof(cmd));
            assert(submit(cmd).status==BSR_OK);
        }
        assert(submit("RUN").status==BSR_OK);
        memset(f.output,0x66,sizeof(f.output));
        memset(f.events,0x55,sizeof(f.events));
        f.written=19U; f.event_written=29U;
        original=f.runtime;
        memcpy(out_copy,f.output,sizeof(out_copy));
        memcpy(events_copy,f.events,sizeof(events_copy));
        written_copy=f.written; event_copy=f.event_written;
        result=step(OUT_CAP,EVENT_CAP);
        assert(result.status==BSR_EXECUTOR_ERROR &&
               result.executor_status==expected[i]);
        assert(memcmp(&f.runtime,&original,sizeof(original))==0);
        assert(memcmp(f.output,out_copy,sizeof(out_copy))==0);
        assert(memcmp(f.events,events_copy,sizeof(events_copy))==0);
        assert(f.written==written_copy && f.event_written==event_copy);
        assert(f.text.bytes_received==0U && f.video.pen==1U);
    }
    setup();
    assert(submit("10 PEN 2:PRINT \"A\":PEN 1:PRINT \"B\"").status==BSR_OK);
    assert(submit("RUN").status==BSR_OK);
    f.written=39U; f.event_written=43U;
    {
        BasicSessionRuntime before=f.runtime;
        assert(step(OUT_CAP,1U).executor_status==BE_NO_EVENT_SPACE);
        assert(memcmp(&f.runtime,&before,sizeof(before))==0);
        assert(f.written==39U && f.event_written==43U);
        assert(step(3U,EVENT_CAP).executor_status==BE_NO_SPACE);
        assert(memcmp(&f.runtime,&before,sizeof(before))==0);
        assert(f.text.bytes_received==0U && f.video.pen==1U);
    }
    assert(step(OUT_CAP,EVENT_CAP).status==BSR_OK);
    assert(hw4_pen_replay(&f.text,f.output,f.written,f.events,
                          f.event_written)==HW4_PEN_OK);
    assert(f.text.bytes_received==4U && f.video.pen==1U);

    /* The exact CONSOLE static capacity (3) must reject a fourth event
     * without committing a single byte or advancing the executor. */
    setup();
    assert(submit("10 PEN 2:PEN 1:PEN 3:PEN 2").status==BSR_OK);
    assert(submit("RUN").status==BSR_OK);
    f.written=55U; f.event_written=66U;
    {
        BasicSessionRuntime previous=f.runtime;
        BSRResult status=step(OUT_CAP,3U);
        assert(status.status==BSR_EXECUTOR_ERROR &&
               status.executor_status==BE_NO_EVENT_SPACE);
        assert(memcmp(&f.runtime,&previous,sizeof(previous))==0);
        assert(f.written==55U && f.event_written==66U);
        assert(f.video.pen==1U && f.text.bytes_received==0U);
    }
}

static void test_scrolling_preserves_text_counters(void)
{
    unsigned i;
    setup();
    for(i=0U;i<30U;++i) {
        char cmd[64];
        int n=snprintf(cmd,sizeof(cmd),"%u PEN %u:PRINT \"%c\"",
                       10U*(i+1U),i%2U==0U?2U:1U,(int)('A'+i%26U));
        assert(n>0 && (size_t)n<sizeof(cmd));
        assert(submit(cmd).status==BSR_OK);
    }
    assert(submit("RUN").status==BSR_OK);
    for(i=0U;i<30U;++i) {
        assert(step(OUT_CAP,EVENT_CAP).status==BSR_OK);
        assert(f.written==2U && f.event_written==1U);
        assert(hw4_pen_replay(&f.text,f.output,f.written,f.events,
                              f.event_written)==HW4_PEN_OK);
    }
    assert(step(OUT_CAP,EVENT_CAP).status==BSR_END);
    assert(f.text.bytes_received==60U);
    assert(f.text.glyphs_drawn==30U);
    assert(f.text.scrolls>0U && f.text.bytes_clipped==0U);
    assert(f.video.cursor_row < 25U);
    assert_colour(22U,2U); /* index 28 -> red, after scrolling */
    assert_colour(23U,1U); /* index 29 -> yellow */
}


/* C1 regression: actual CONSOLE !CLS wrapper invokes the real
 * cpc_uart_console_clear(); no fake video reset or substituted sink.
 * The same source must FAIL on C1 red and PASS after palette restoration. */
static void run_c1_colour_cases(void)
{
    const uint8_t expected_pen[] = {2U,3U,15U,4U};
    const uint8_t expected_pixel[] = {2U,3U,3U,0U};
    const uint8_t expected_ink[] = {6U,18U,18U,1U};
    size_t i;
    assert(submit("RUN").status == BSR_OK);
    for(i=0U;i<4U;++i) {
        uint16_t rgb[CPC_VIDEO_TFT_WIDTH];
        assert(step(OUT_CAP,EVENT_CAP).status == BSR_OK);
        assert(f.event_written==1U && f.events[0].pen==expected_pen[i]);
        assert(f.events[0].print_offset==0U);
        assert(f.written==2U && f.output[1]=='\n');
        assert(hw4_pen_replay(&f.text,f.output,f.written,
                               f.events,f.event_written)==HW4_PEN_OK);
        assert(pixel_at(0U,(unsigned)i*8U)==expected_pixel[i]);
        assert(cpc_video_render_row(&f.video,
                  CPC_VIDEO_VIEW_TOP+(unsigned)i*8U,rgb,CPC_VIDEO_TFT_WIDTH));
        assert(rgb[0]==cpc_video_palette_rgb565(expected_ink[i]));
    }
    assert(f.text.bytes_received==8U && f.text.glyphs_drawn==4U);
    assert(f.video.cursor_visible && f.text.bytes_clipped==0U);
    {
        const size_t before_bytes=f.text.bytes_received;
        const uint8_t before_pen=f.video.pen;
        uint8_t before_vram[CPC_VIDEO_BYTES];
        BSRResult bad;
        memcpy(before_vram,f.vram,sizeof(before_vram));
        f.written=43U; f.event_written=47U;
        bad=step(OUT_CAP,EVENT_CAP);
        assert(bad.status==BSR_EXECUTOR_ERROR &&
               bad.executor_status==BE_INVALID_PEN);
        assert(f.written==43U && f.event_written==47U);
        assert(f.text.bytes_received==before_bytes &&
               f.video.pen==before_pen);
        assert(memcmp(before_vram,f.vram,sizeof(before_vram))==0);
    }
    assert(bsr_stop(&f.runtime).status == BSR_OK);
}
static void test_c1_real_console_cls_palette(void)
{
    const char *lines[] = {
        "10 PEN 2:PRINT \"R\"",
        "20 PEN 3:PRINT \"G\"",
        "30 PEN 15:PRINT \"F\"",
        "40 PEN 4:PRINT \"H\"",
        "50 PEN 16",
        "60 PRINT \"NEVER\""
    };
    bool cleared = true;
    size_t original_size;
    setup();
    for(size_t i=0U;i<sizeof(lines)/sizeof(lines[0]);++i)
        assert(submit(lines[i]).status==BSR_OK);
    original_size=f.program.size;
    assert(f.video.ink[2]==6U && f.video.ink[3]==18U);
    run_c1_colour_cases(); /* passes before !CLS */
    assert(hw4_pen_console_clear(&f.text)); /* must call real clear */
    assert(f.program.size==original_size);
    assert(f.video.mode==CPC_MODE_1 && f.video.paper==0U &&
           f.video.pen==1U);
    assert(f.video.ink[0]==1U && f.video.ink[1]==24U);
    /* C1 RED EXPECTATION: original cpc_uart_console_clear resets mode and
     * overwrites INK2/3 with defaults (20/6), not boot's 6/18. */
    assert(f.video.ink[2]==6U && f.video.ink[3]==18U);
    assert(f.text.bytes_received==0U && f.text.glyphs_drawn==0U);
    assert(cpc_uart_console_prompt(&f.text,&cleared) && !cleared);
    run_c1_colour_cases(); /* colour and PEN16 still valid after !CLS */
}


/* HW4-PEN-A-C1-SYNC: true BASIC mixed PEN/INK/PRINT step.
 * Even PRINT that precedes SET_INK must not reach VRAM or text counters.
 * ABI J1.18-B adds ink/colour, but the three-event budget is preserved. */
static void test_j118b_ink_explicit_reject_no_partial_replay(void)
{
    const uint8_t expected[]={'A','\n','B','\n','C','\n'};
    uint8_t output_copy[OUT_CAP];
    size_t original_program_size;
    setup();
    assert(submit("10 PEN 2:PRINT \"A\":INK 1,26:PRINT \"B\":PEN 3:PRINT \"C\"").status==BSR_OK);
    original_program_size=f.program.size;
    assert(submit("RUN").status==BSR_OK);
    assert(step(OUT_CAP,3U).status==BSR_OK);
    assert(f.written==sizeof(expected) && f.event_written==3U);
    assert(memcmp(f.output,expected,sizeof(expected))==0);
    assert(f.events[0].type==BE_VIDEO_SET_TEXT_PEN &&
           f.events[0].pen==2U && f.events[0].print_offset==0U);
    assert(f.events[1].type==BE_VIDEO_SET_INK &&
           f.events[1].ink==1U && f.events[1].colour==26U &&
           f.events[1].print_offset==2U);
    assert(f.events[2].type==BE_VIDEO_SET_TEXT_PEN &&
           f.events[2].pen==3U && f.events[2].print_offset==4U);
    memcpy(output_copy,f.output,sizeof(output_copy));
    assert_rejected_replay(f.events,3U,f.output,f.written,
                           HW4_PEN_SET_INK_UNSUPPORTED);
    assert(memcmp(f.output,output_copy,sizeof(output_copy))==0);
    assert(f.text.bytes_received==0U && f.video.pen==1U);
    assert(f.video.ink[2]==6U && f.video.ink[3]==18U);
    assert(f.program.size==original_program_size);
    assert(hw4_pen_console_clear(&f.text)); /* real C1 !CLS path */
    assert(f.video.ink[2]==6U && f.video.ink[3]==18U);
    assert_rejected_replay(f.events,3U,f.output,f.written,
                           HW4_PEN_SET_INK_UNSUPPORTED);
    assert(f.program.size==original_program_size);
    assert_rejected_replay(&f.events[1],1U,f.output,f.written,
                           HW4_PEN_SET_INK_UNSUPPORTED);
}


/* C1-RUN-STOP: the production RUN-loop transition is shared with this host
 * harness; actual bsr_step_events, bridge preflight, diagnostic renderer,
 * Ready policy and real !CLS are exercised. The RED version reproduces
 * BSR_NOT_RUNNING + a second ERROR after a diagnosed SET_INK rejection. */
static void test_c1_run_stop_case(bool ink_only)
{
    unsigned run_index;
    setup();
    assert(submit(ink_only ? "10 INK 1,26" :
          "10 PEN 2:PRINT \"A\":INK 1,26:PRINT \"B\":PEN 3:PRINT \"C\"").status==BSR_OK);
    assert(submit("20 PRINT \"NEXT_STEP_NEVER\"").status==BSR_OK);
    const size_t original_size=f.program.size;
    for(run_index=0U;run_index<2U;++run_index) {
        unsigned attempts=0U,video_rejects=0U,errors=0U;
        unsigned step_fails=0U,prints=0U,ready=0U;
        bool ready_emitted=false,cleared=false;
        if(run_index==1U) {
            assert(hw4_pen_console_clear(&f.text)); /* real C1 !CLS */
            assert(f.program.size==original_size);
            assert(f.video.ink[2]==6U && f.video.ink[3]==18U);
        }
        assert(submit("RUN").status==BSR_OK);
        for(unsigned i=0U;i<4U;++i) {
            ++attempts;
            BSRResult r=step(OUT_CAP,3U);
            if(r.status==BSR_END) break;
            if(r.status!=BSR_OK || r.executor_status!=BE_OK) {
                ++step_fails;
                assert(r.status==BSR_NOT_RUNNING); /* RED second step */
                assert(cpc_diag_policy_write(&f.text,CPC_DIAG_HOST_GENERIC));
                ++errors;
                (void)bsr_stop(&f.runtime);
                break;
            }
            if(f.event_written!=0U) {
                Hw4PenStatus validation=hw4_pen_preflight(&f.text,f.output,
                                              f.written,f.events,f.event_written);
                Hw4PenDisplayResult render_result=HW4_PEN_DISPLAY_OK;
                if(validation!=HW4_PEN_OK) {
                    assert(validation==HW4_PEN_SET_INK_UNSUPPORTED);
                    ++video_rejects;
                    (void)bsr_stop(&f.runtime);
                    assert(cpc_diag_policy_write(&f.text,CPC_DIAG_HOST_GENERIC));
                    ++errors;
                    render_result=HW4_PEN_DISPLAY_REJECT_DIAGNOSED;
                } else {
                    assert(hw4_pen_replay(&f.text,f.output,f.written,
                                           f.events,f.event_written)==HW4_PEN_OK);
                    ++prints;
                }
                Hw4PenRunAction next=hw4_pen_run_after_display(render_result);
                if(next==HW4_PEN_RUN_DONE) break;
                if(next==HW4_PEN_RUN_FATAL) assert(false);
            } else if(f.written!=0U) {
                assert(cpc_text_write(&f.text,f.output,f.written));
                ++prints;
            }
        }
        assert(cpc_ready_policy_apply(&f.text,CPC_READY_RUN_RETURN,
                                      &ready_emitted));
        assert(ready_emitted);
        assert(cpc_uart_console_prompt(&f.text,&cleared) && !cleared);
        ++ready;
        fprintf(stderr,"C1-RUN-STOP %s pass=%u VIDEO_REJECT=%u ERROR=%u "
                       "BSR_NOT_RUNNING=%u PRINT_BYTES=%u Ready=%u attempts=%u\\n",
                ink_only?"INK_ONLY":"MIXED",run_index,video_rejects,errors,
                step_fails,prints,ready,attempts);
        fflush(stderr);
        assert(video_rejects==1U && errors==1U && step_fails==0U);
        assert(prints==0U && ready==1U && attempts==1U);
        assert(f.runtime.state!=BSR_RUNNING);
        assert(f.program.size==original_size);
        assert(f.video.pen==1U && f.video.ink[2]==6U && f.video.ink[3]==18U);
    }
}
static void test_c1_run_stop(void)
{
    test_c1_run_stop_case(false);
    test_c1_run_stop_case(true);
}

/* C1-RUN-STOP-C2: read the actual production function's last return,
 * then use it with real BSR steps and the shared RUN action. This is not
 * a mocked return: the known bad firmware 'return true' becomes enum 1. */
static Hw4PenDisplayResult c2_firmware_display_success(void)
{
    const char *path=getenv("HW4_PEN_C2_CONSOLE_SOURCE");
    char line[512];
    bool in_function=false,ended=false,found=false;
    Hw4PenDisplayResult result=HW4_PEN_DISPLAY_FATAL;
    FILE *file;
    assert(path!=NULL);
    file=fopen(path,"rb");
    assert(file!=NULL);
    while(fgets(line,sizeof(line),file)!=NULL) {
        if(!in_function) {
            if(strstr(line,"static Hw4PenDisplayResult display_print_events(")!=NULL)
                in_function=true;
            continue;
        }
        if(strstr(line,"static bool display_error(void)")!=NULL) {
            ended=true;
            break;
        }
        if(strstr(line,"return true;")!=NULL) {
            result=(Hw4PenDisplayResult)true;
            found=true;
        } else if(strstr(line,"return HW4_PEN_DISPLAY_OK;")!=NULL) {
            result=HW4_PEN_DISPLAY_OK;
            found=true;
        }
    }
    assert(fclose(file)==0);
    assert(in_function && ended && found);
    return result;
}

static void test_c1_c2_successive_pen_lines_reach_end(void)
{
    static const char *const program[]={
        "10 PEN 2:PRINT \"A\"",
        "20 PEN 1:PRINT \"B\"",
        "30 PEN 3:PRINT \"C\"",
        "40 PRINT \"NEXT_STEP_REACHED\"",
        "50 END"
    };
    setup();
    for(size_t i=0U;i<sizeof(program)/sizeof(program[0]);++i)
        assert(submit(program[i]).status==BSR_OK);
    const size_t stored=f.program.size;
    const Hw4PenDisplayResult nominal=c2_firmware_display_success();
    assert(hw4_pen_run_after_display(HW4_PEN_DISPLAY_OK)==HW4_PEN_RUN_CONTINUE);
    assert(hw4_pen_run_after_display(HW4_PEN_DISPLAY_REJECT_DIAGNOSED)==HW4_PEN_RUN_DONE);
    assert(hw4_pen_run_after_display(HW4_PEN_DISPLAY_FATAL)==HW4_PEN_RUN_FATAL);
    for(unsigned pass=0U;pass<2U;++pass) {
        unsigned calls=0U,pen_lines=0U,marker=0U,ended=0U;
        bool ready=false,cleared=false;
        if(pass!=0U) {
            assert(hw4_pen_console_clear(&f.text)); /* real !CLS */
            assert(f.video.ink[2]==6U && f.video.ink[3]==18U);
            assert(f.program.size==stored);
        }
        assert(submit("RUN").status==BSR_OK);
        for(unsigned i=0U;i<8U;++i) {
            ++calls;
            BSRResult r=step(OUT_CAP,3U); /* real CONSOLE event budget */
            if(r.status==BSR_END) { ++ended; break; }
            assert(r.status==BSR_OK && r.executor_status==BE_OK);
            if(f.event_written!=0U) {
                assert(f.event_written==1U);
                assert(f.events[0].type==BE_VIDEO_SET_TEXT_PEN);
                assert(hw4_pen_preflight(&f.text,f.output,f.written,
                       f.events,f.event_written)==HW4_PEN_OK);
                assert(hw4_pen_replay(&f.text,f.output,f.written,
                       f.events,f.event_written)==HW4_PEN_OK);
                ++pen_lines;
                Hw4PenRunAction next=hw4_pen_run_after_display(nominal);
                if(next!=HW4_PEN_RUN_CONTINUE) break;
            } else if(f.written!=0U) {
                assert(f.written==18U);
                assert(memcmp(f.output,"NEXT_STEP_REACHED\n",18U)==0);
                assert(cpc_text_write(&f.text,f.output,f.written));
                ++marker;
            }
        }
        fprintf(stderr,"C1-RUN-STOP-C2 pass=%u nominal=%d steps=%u PEN=%u PRINT_MARKER=%u END=%u\n",
                pass,(int)nominal,calls,pen_lines,marker,ended);
        fflush(stderr);
        assert(pen_lines==3U && marker==1U && ended==1U && calls==6U);
        assert(f.program.size==stored);
        assert(cpc_ready_policy_apply(&f.text,CPC_READY_RUN_RETURN,&ready));
        assert(ready);
        assert(cpc_uart_console_prompt(&f.text,&cleared) && !cleared);
    }
}

int main(void)
{
    test_order_and_preserved_print();
    test_pen_only_and_oracle_bounds();
    test_bridge_preflight_atomic();
    test_runtime_atomic_and_diagnostics();
    test_scrolling_preserves_text_counters();
    test_c1_real_console_cls_palette();
    test_j118b_ink_explicit_reject_no_partial_replay();
    test_c1_run_stop();
    test_c1_c2_successive_pen_lines_reach_end();
    puts("HW4-PEN-A: typed events, native MODE1 pixels, scroll and atomicity PASS");
    return 0;
}
