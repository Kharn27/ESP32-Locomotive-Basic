/* HW4-PEN-A: portable UART-like BASIC -> typed events -> MODE1 VRAM.
 * Host tests and sealed J1.17-A/C-A CPC cases; no real TFT simulation. */
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
/* Observe actual glyphs emitted by the production CpcText sink. */
static bool capture_diag;
static char diagnostic_glyphs[96];
static size_t diagnostic_glyph_count;

static uint8_t glyph(void *ctx, uint8_t ch, unsigned row)
{
    (void)ctx;
    if(capture_diag && row==0U) {
        assert(diagnostic_glyph_count<sizeof(diagnostic_glyphs));
        diagnostic_glyphs[diagnostic_glyph_count++]=(char)ch;
    }
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
    /* Historical PEN15 / red-green fixture: explicitly non-default
     * now that CONSOLE boot and !CLS use genuine CPC cyan/red. */
    assert(cpc_video_set_ink(&f.video, 2U, 6U)); /* experimental red */
    assert(cpc_video_set_ink(&f.video, 3U, 18U)); /* PEN15 green witness */
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
    /* This boot-red/green palette is neither oracle C nor default D. */
    assert_rejected_replay(events,2U,print_bytes,sizeof(print_bytes),
                           HW4_PEN_UNVERIFIED_VISUAL);
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
    /* Host ERR=5 operands remain rejected; 5/14 now emit native events. */
    static const char *bad[]={"PEN 16","PEN -1"};
    static const BEStatus expected[]={BE_INVALID_PEN,BE_INVALID_PEN};
    size_t i;
    for(i=0U;i<2U;++i) {
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


/* Historical experimental INK2 red/INK3 green C1 witness: real BSR and
 * cpc_uart_console_clear() path. After !CLS the CPC palette is checked
 * before explicitly restoring this legacy colour witness for replay. */
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
    /* !CLS now restores CPC cyan/red: the prior green PEN15 context
     * is NOT inherited. Keep the historical experimental witness explicit. */
    assert(f.video.ink[2]==20U && f.video.ink[3]==6U);
    assert(f.text.bytes_received==0U && f.text.glyphs_drawn==0U);
    assert(cpc_video_set_ink(&f.video,2U,6U)); /* experimental red */
    assert(cpc_video_set_ink(&f.video,3U,18U)); /* PEN15 green witness */
    assert(cpc_uart_console_prompt(&f.text,&cleared) && !cleared);
    run_c1_colour_cases(); /* historic context explicitly configured */
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
    assert(f.video.ink[2]==20U && f.video.ink[3]==6U);
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
            assert(f.video.ink[2]==20U && f.video.ink[3]==6U);
            /* Retain the old red/green test context, explicitly. */
            assert(cpc_video_set_ink(&f.video,2U,6U));
            assert(cpc_video_set_ink(&f.video,3U,18U));
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
/* B: the CONSOLE now uses a bool replay callback, not an enum display
 * function. Verify its exact success condition in production source;
 * a literal 'return true' or 'return HW4_PEN_DISPLAY_OK' fails closed. */
static Hw4PenDisplayResult c2_firmware_display_success(void)
{
    const char *path=getenv("HW4_PEN_C2_CONSOLE_SOURCE");
    char line[512];
    bool in_function=false,ended=false,found=false;
    FILE *file;
    assert(path!=NULL);
    file=fopen(path,"rb");
    assert(file!=NULL);
    while(fgets(line,sizeof(line),file)!=NULL) {
        if(!in_function) {
            if(strstr(line,"static bool run_replay(")!=NULL)
                in_function=true;
            continue;
        }
        if(strstr(line,"static bool display_error(void)")!=NULL) {
            ended=true;
            break;
        }
        if(strstr(line,"return s_run_video_failure==HW4_PEN_OK;")!=NULL)
            found=true;
        if(strstr(line,"return true;")!=NULL ||
           strstr(line,"return HW4_PEN_DISPLAY_OK;")!=NULL)
            found=false;
    }
    assert(fclose(file)==0);
    assert(in_function && ended && found);
    return HW4_PEN_DISPLAY_OK;
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
            assert(f.video.ink[2]==20U && f.video.ink[3]==6U);
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


/* HW4-DIAG-PEN-A: actual runtime errors, real record numbers and text/Ready
 * sink. This catches the previous ERROR fallback and a hardcoded "in 10". */
static void test_diag_pen_run_case(const char *line10, const char *line20,
                                   uint16_t bad_line, bool repeat_after_cls)
{
    const char *expected=bad_line==10U ?
        "Improper argument in 10\n" : "Improper argument in 20\n";
    const char *expected_painted=bad_line==10U ?
        "Improper argument in 10Ready" : "Improper argument in 20Ready";
    const size_t expected_length=strlen(expected);
    uint8_t saved_program[sizeof(f.program_bytes)];
    setup();
    assert(submit(line10).status==BSR_OK);
    assert(submit(line20).status==BSR_OK);
    assert(submit("30 PRINT \"NEVER\"").status==BSR_OK);
    const size_t stored_size=f.program.size;
    memcpy(saved_program,f.program_bytes,sizeof(saved_program));
    for(unsigned pass=0U;pass<(repeat_after_cls?2U:1U);++pass) {
        uint8_t vram_before[CPC_VIDEO_BYTES];
        uint8_t output_before[OUT_CAP];
        BEVideoEvent events_before[EVENT_CAP];
        BasicSessionRuntime runtime_before;
        uint8_t buffer[48];
        size_t size=99U;
        bool ready=false;
        CpcStepDiagnostic diag;
        if(pass!=0U) {
            assert(hw4_pen_console_clear(&f.text)); /* production !CLS */
            assert(f.program.size==stored_size);
        }
        assert(submit("RUN").status==BSR_OK);
        if(bad_line==20U) {
            BSRResult first=step(OUT_CAP,3U);
            assert(first.status==BSR_OK && f.written==0U &&
                   f.event_written==1U);
            assert(hw4_pen_replay(&f.text,f.output,f.written,
                                  f.events,f.event_written)==HW4_PEN_OK);
        }
        memcpy(vram_before,f.vram,sizeof(vram_before));
        memset(f.output,0x5a,sizeof(f.output));
        memset(f.events,0x66,sizeof(f.events));
        f.written=41U;
        f.event_written=43U;
        memcpy(output_before,f.output,sizeof(output_before));
        memcpy(events_before,f.events,sizeof(events_before));
        runtime_before=f.runtime;
        BSRResult r=step(OUT_CAP,3U);
        assert(r.status==BSR_EXECUTOR_ERROR &&
               r.executor_status==BE_INVALID_PEN);
        assert(memcmp(&f.runtime,&runtime_before,sizeof(runtime_before))==0);
        assert(memcmp(f.output,output_before,sizeof(output_before))==0);
        assert(memcmp(f.events,events_before,sizeof(events_before))==0);
        assert(f.written==41U && f.event_written==43U);
        assert(memcmp(f.vram,vram_before,sizeof(vram_before))==0);
        assert(f.program.size==stored_size);
        assert(memcmp(f.program_bytes,saved_program,sizeof(saved_program))==0);
        diag=cpc_diag_policy_step(r,&f.runtime); /* BEFORE stop */
        assert(diag.category==CPC_DIAG_PEN_IMPROPER_ARGUMENT);
        assert(diag.origin==CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE);
        assert(diag.line_number==bad_line);
        assert(cpc_diag_policy_format_step(diag,buffer,sizeof(buffer),&size));
        assert(size==expected_length && memcmp(buffer,expected,size)==0);
        memset(buffer,0x6c,sizeof(buffer));
        size=71U;
        assert(!cpc_diag_policy_format_step(diag,buffer,expected_length-1U,&size));
        assert(size==71U && buffer[0]==0x6cU);
        assert(bsr_stop(&f.runtime).status==BSR_OK);
        assert(f.runtime.state==BSR_IDLE);
        assert(cpc_diag_policy_step(r,&f.runtime).category==CPC_DIAG_HOST_GENERIC);
        /* Same two production writers and RUN_RETURN transition as CONSOLE. */
        capture_diag=true;
        diagnostic_glyph_count=0U;
        assert(cpc_diag_policy_write_step(&f.text,diag));
        assert(cpc_ready_policy_apply(&f.text,CPC_READY_RUN_RETURN,&ready));
        assert(ready);
        capture_diag=false;
        assert(diagnostic_glyph_count==strlen(expected_painted));
        assert(memcmp(diagnostic_glyphs,expected_painted,
                      diagnostic_glyph_count)==0);
        assert(strstr(expected_painted,"NEVER")==NULL);
        assert(f.text.bytes_clipped==0U);
    }
    capture_diag=false;
}
static void test_diag_pen_native_and_host_guards(void)
{
    uint8_t message[48];
    size_t size=0U;
    CpcStepDiagnostic host={CPC_DIAG_HOST_GENERIC,CPC_DIAG_ORIGIN_HOST,0U};
    CpcStepDiagnostic forged={CPC_DIAG_PEN_IMPROPER_ARGUMENT,
                             CPC_DIAG_ORIGIN_HOST,10U};
    assert(cpc_diag_policy_format_step(host,message,sizeof(message),&size));
    assert(size==6U && memcmp(message,"ERROR\n",size)==0);
    assert(!cpc_diag_policy_format_step(forged,message,sizeof(message),&size));
    forged.origin=CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE;
    forged.line_number=0U;
    assert(!cpc_diag_policy_format_step(forged,message,sizeof(message),&size));

    test_diag_pen_run_case("10 PEN 16","20 PRINT \"NEVER_BEFORE\"",10U,true);
    test_diag_pen_run_case("10 PEN -1","20 END",10U,false);
    test_diag_pen_run_case("10 PEN 2","20 PEN 16",20U,true);
    test_diag_pen_run_case("10 PEN 2","20 PEN -1",20U,false);
    test_diag_pen_run_case("10 PEN 2:PRINT \"NEVER_BEFORE\":PEN 16",
                           "20 END",10U,false);

    /* J1.17-C-B: 5/14 are now valid logical CPC events.
     * HW4 bridge still rejects unverified physical mapping, independently
     * of native BASIC execution. Never claim a false CPC diagnostic. */
    for(unsigned n=5U;n<=14U;n+=9U) {
        char cmd[32];
        BSRResult r;
        setup();
        assert(snprintf(cmd,sizeof(cmd),"10 PEN %u",n)>0);
        assert(submit(cmd).status==BSR_OK);
        assert(submit("RUN").status==BSR_OK);
        r=step(OUT_CAP,3U);
        assert(r.status==BSR_OK && f.written==0U && f.event_written==1U);
        assert(f.events[0].type==BE_VIDEO_SET_TEXT_PEN &&
               f.events[0].pen==(uint8_t)n &&
               f.events[0].print_offset==0U);
        /* Logical PEN 5/14 is now valid; this non-oracle palette
         * still must not be silently rendered as an arbitrary colour. */
        assert(hw4_pen_preflight(&f.text,f.output,f.written,
                   f.events,f.event_written)==HW4_PEN_UNVERIFIED_VISUAL);
    }
    setup();
    assert(submit("10 PEN 2:PEN 1:PEN 3:PEN 2").status==BSR_OK);
    assert(submit("RUN").status==BSR_OK);
    {
        BSRResult r=step(OUT_CAP,3U);
        assert(r.executor_status==BE_NO_EVENT_SPACE);
        assert(cpc_diag_policy_step(r,&f.runtime).category==CPC_DIAG_HOST_GENERIC);
    }
    setup();
    assert(submit("10 INK 1,26").status==BSR_OK);
    assert(submit("RUN").status==BSR_OK);
    {
        BSRResult r=step(OUT_CAP,3U);
        assert(r.status==BSR_OK && f.event_written==1U);
        assert(hw4_pen_preflight(&f.text,f.output,f.written,
                    f.events,f.event_written)==HW4_PEN_SET_INK_UNSUPPORTED);
        assert(cpc_diag_policy_step(r,&f.runtime).category==CPC_DIAG_HOST_GENERIC);
    }
    setup();
    {
        BSRResult r=submit("RUN+");
        assert(r.status!=BSR_OK);
        assert(cpc_diag_policy_select((const uint8_t *)"RUN+",4U,r)
               ==CPC_DIAG_HOST_GENERIC);
        assert(cpc_diag_policy_step(r,&f.runtime).category==CPC_DIAG_HOST_GENERIC);
    }
    setup();
    {
        BSRResult r=submit("PEN 16"); /* no native direct PEN RUN context */
        assert(r.status!=BSR_OK);
        assert(cpc_diag_policy_step(r,&f.runtime).category==CPC_DIAG_HOST_GENERIC);
    }
}


/* HW4-PAL-BOOT-CPC-B1: source-level CONSOLE boot contract plus the real
 * BSR -> bridge -> MODE1 RGB565 path. The old experimental PEN15 witness
 * remains separately configured in setup(); this CPC context rejects it. */
static void test_cpc_palette_boot_source(void)
{
    const char *path=getenv("HW4_PEN_C2_CONSOLE_SOURCE");
    char line[512];
    FILE *file;
    bool ink2=false,ink3=false,context=false;
    assert(path!=NULL);
    file=fopen(path,"rb");
    assert(file!=NULL);
    while(fgets(line,sizeof(line),file)!=NULL) {
        if(strstr(line,"cpc_video_set_ink(&s_video,2U,20U)")!=NULL)
            ink2=true;
        if(strstr(line,"cpc_video_set_ink(&s_video,3U,6U)")!=NULL)
            ink3=true;
        if(strstr(line,"ink0=1_blue ink1=24_yellow ink2=20_cyan ink3=6_red")!=NULL)
            context=true;
    }
    assert(fclose(file)==0);
    assert(ink2 && ink3 && context);
}

static void test_cpc_palette_run_and_clear(void)
{
    static const uint8_t expected_pen[]={1U,2U,3U};
    static const uint8_t expected_ink[]={24U,20U,6U};
    uint8_t saved[sizeof(f.program_bytes)];
    size_t saved_size;
    unsigned pass;
    setup();
    /* The generic video MODE1 init is already CPC-correct. Override
     * the historical fixture's explicitly experimental green profile. */
    assert(cpc_video_set_ink(&f.video,2U,20U));
    assert(cpc_video_set_ink(&f.video,3U,6U));
    assert(f.video.ink[0]==1U && f.video.ink[1]==24U &&
           f.video.ink[2]==20U && f.video.ink[3]==6U);
    assert(submit("10 PEN 1:PRINT \"Y\"").status==BSR_OK);
    assert(submit("20 PEN 2:PRINT \"C\"").status==BSR_OK);
    assert(submit("30 PEN 3:PRINT \"R\"").status==BSR_OK);
    assert(submit("40 END").status==BSR_OK);
    saved_size=f.program.size;
    memcpy(saved,f.program_bytes,sizeof(saved));
    for(pass=0U;pass<2U;++pass) {
        uint16_t rgb[CPC_VIDEO_TFT_WIDTH];
        unsigned i;
        assert(submit("RUN").status==BSR_OK);
        for(i=0U;i<3U;++i) {
            assert(step(OUT_CAP,EVENT_CAP).status==BSR_OK);
            assert(f.written==2U && f.event_written==1U);
            assert(f.events[0].type==BE_VIDEO_SET_TEXT_PEN);
            assert(f.events[0].pen==expected_pen[i]);
            assert(hw4_pen_preflight(&f.text,f.output,f.written,
                                    f.events,f.event_written)==HW4_PEN_OK);
            assert(hw4_pen_replay(&f.text,f.output,f.written,
                                 f.events,f.event_written)==HW4_PEN_OK);
            assert_colour(i,expected_pen[i]);
            assert(f.video.ink[expected_pen[i]]==expected_ink[i]);
            assert(cpc_video_render_row(&f.video,
                     CPC_VIDEO_VIEW_TOP+i*8U,rgb,CPC_VIDEO_TFT_WIDTH));
            /* Glyph starts at x=0; x=7 is PAPER0, still CPC blue. */
            assert(rgb[7]==cpc_video_palette_rgb565(1U));
        }
        assert(step(OUT_CAP,EVENT_CAP).status==BSR_OK);
        assert(step(OUT_CAP,EVENT_CAP).status==BSR_END);
        assert(f.program.size==saved_size &&
               memcmp(saved,f.program_bytes,sizeof(saved))==0);
        assert(f.video.cursor_visible && f.text.bytes_clipped==0U);
        if(pass==0U) {
            uint8_t mapped=0xAAU;
            BEVideoEvent fifteen={BE_VIDEO_SET_TEXT_PEN,15U,0U,0U,0U};
            assert(hw4_pen_pixel_index(&f.video,15U,&mapped)==
                   HW4_PEN_UNVERIFIED_VISUAL);
            assert(mapped==0xAAU);
            assert_rejected_replay(&fifteen,1U,NULL,0U,
                                   HW4_PEN_UNVERIFIED_VISUAL);
            /* A user-visible ink change must not survive !CLS, unlike
             * native CLS in RUN, which preserves the current inks. */
            assert(cpc_video_set_ink(&f.video,2U,26U));
            assert(cpc_video_set_ink(&f.video,3U,18U));
            assert(hw4_pen_console_clear(&f.text));
            assert(f.video.ink[0]==1U && f.video.ink[1]==24U &&
                   f.video.ink[2]==20U && f.video.ink[3]==6U);
            assert(f.video.mode==CPC_MODE_1 && f.video.paper==0U &&
                   f.video.pen==1U && f.video.border==1U);
            assert(f.text.row==0U && f.text.column==0U);
            assert(f.program.size==saved_size &&
                   memcmp(saved,f.program_bytes,sizeof(saved))==0);
        }
    }
}

static void test_cpc_palette_native_cls_keeps_inks(void)
{
    setup();
    assert(cpc_video_set_ink(&f.video,2U,20U));
    assert(cpc_video_set_ink(&f.video,3U,6U));
    assert(submit("10 PEN 3:PRINT \"X\":CLS:PRINT \"R\"").status==BSR_OK);
    assert(submit("20 END").status==BSR_OK);
    assert(submit("RUN").status==BSR_OK);
    assert(step(OUT_CAP,EVENT_CAP).status==BSR_OK);
    assert(f.event_written==2U && f.events[0].type==BE_VIDEO_SET_TEXT_PEN &&
           f.events[1].type==BE_VIDEO_CLEAR_TEXT);
    assert(hw4_pen_preflight(&f.text,f.output,f.written,
                             f.events,f.event_written)==HW4_PEN_OK);
    assert(hw4_pen_replay(&f.text,f.output,f.written,
                          f.events,f.event_written)==HW4_PEN_OK);
    assert(f.video.ink[0]==1U && f.video.ink[1]==24U &&
           f.video.ink[2]==20U && f.video.ink[3]==6U);
    assert(pixel_at(0U,0U)==3U && f.text.scrolls==0U);
    assert_colour(0U,3U);
}

/* J1.21-C2: the exact C1 direct event is consumed by the existing HW4
 * MODE1 bridge, not a 10 CLS / RUN workaround and not host !CLS. */
static void test_j121_c2_direct_cls_mode1(void)
{
    static const char *const spellings[]={"CLS","cls","cLs","  ClS  "};
    BasicVariableStore store;
    BasicVariableEntry entries[16];
    uint8_t original_program[sizeof(f.program_bytes)];
    BasicVariableEntry original_entries[16];
    BasicProgram program_before;
    BasicSessionRuntime runtime_before;
    BasicVariableStore store_before;
    uint8_t inks_before[4];
    uint8_t old_pen,old_paper,old_border,read_cell;
    bool known=false,emitted=true,cleared=true;
    size_t old_program_size;
    setup();
    assert(bvs_init(&store,entries,16U)==BVS_OK);
    assert(bsr_init_with_store(&f.runtime,&f.program,&store).status==BSR_OK);
    assert(submit("10 A%=2").status==BSR_OK);
    assert(submit("20 END").status==BSR_OK);
    assert(submit("RUN").status==BSR_OK);
    for(unsigned step_index=0U;step_index<8U;++step_index) {
        BSRResult result=step(OUT_CAP,EVENT_CAP);
        if(result.status==BSR_END) break;
        assert(result.status==BSR_OK);
    }
    assert(f.runtime.state==BSR_IDLE && store.count==1U);
    old_program_size=f.program.size;
    program_before=f.program;
    runtime_before=f.runtime;
    store_before=store;
    memcpy(original_program,f.program_bytes,sizeof(original_program));
    memcpy(original_entries,entries,sizeof(original_entries));
    assert(cpc_video_set_ink(&f.video,0U,6U));
    assert(cpc_video_set_ink(&f.video,1U,26U));
    assert(cpc_video_set_ink(&f.video,2U,20U));
    assert(cpc_video_set_ink(&f.video,3U,18U));
    assert(cpc_video_set_border(&f.video,15U));
    assert(cpc_video_set_text_colors(&f.video,3U,2U));
    memcpy(inks_before,f.video.ink,sizeof(inks_before));
    old_pen=f.video.pen;old_paper=f.video.paper;old_border=f.video.border;
    for(size_t i=0U;i<sizeof(spellings)/sizeof(spellings[0]);++i) {
        static const uint8_t marked[]="SCREEN_CONTENT";
        BEVideoEvent untouched;
        CpcText text_before;
        CpcVideo video_before;
        assert(cpc_text_write(&f.text,marked,sizeof(marked)-1U));
        assert(pixel_at(0U,0U)!=old_paper || i!=0U);
        /* API C1 writes exactly one event, no temporary BASIC mutation. */
        f.written=123U;f.event_written=456U;
        assert(bsr_prepare_direct_events(&f.runtime,
               (const uint8_t *)spellings[i],strlen(spellings[i]),
               f.output,sizeof(f.output),&f.written,
               f.events,1U,&f.event_written).status==BSR_OK);
        assert(f.written==0U && f.event_written==1U);
        assert(f.events[0].type==BE_VIDEO_CLEAR_TEXT &&
               f.events[0].print_offset==0U &&
               f.events[0].pen==0U && f.events[0].ink==0U &&
               f.events[0].colour==0U);
        assert(f.program.size==old_program_size &&
               memcmp(&f.program,&program_before,sizeof(program_before))==0);
        assert(memcmp(f.program_bytes,original_program,sizeof(original_program))==0);
        assert(memcmp(&f.runtime,&runtime_before,sizeof(runtime_before))==0);
        assert(memcmp(&store,&store_before,sizeof(store_before))==0);
        assert(memcmp(entries,original_entries,sizeof(original_entries))==0);
        text_before=f.text;video_before=f.video;
        assert(hw4_pen_preflight(&f.text,f.output,0U,f.events,1U)==HW4_PEN_OK);
        assert(memcmp(&f.text,&text_before,sizeof(text_before))==0 &&
               memcmp(&f.video,&video_before,sizeof(video_before))==0);
        assert(hw4_pen_replay(&f.text,f.output,0U,f.events,1U)==HW4_PEN_OK);
        for(size_t j=0U;j<sizeof(f.vram);++j)
            assert(f.vram[j]==(uint8_t)(old_paper*0x55U));
        assert(pixel_at(0U,0U)==old_paper);
        assert(cpc_video_read_cell(&f.video,0U,0U,&read_cell,&known) && !known);
        assert(f.text.row==0U && f.text.column==0U);
        assert(f.video.mode==CPC_MODE_1 && f.video.pen==old_pen &&
               f.video.paper==old_paper && f.video.border==old_border);
        assert(memcmp(f.video.ink,inks_before,sizeof(inks_before))==0);
        assert(memcmp(f.program_bytes,original_program,sizeof(original_program))==0);
        assert(memcmp(entries,original_entries,sizeof(original_entries))==0);
        assert(memcmp(&f.runtime,&runtime_before,sizeof(runtime_before))==0);
        emitted=true;cleared=true;
        assert(cpc_ready_policy_apply(&f.text,CPC_READY_UNCHARACTERIZED_DIRECT,&emitted));
        assert(!emitted);
        assert(cpc_uart_console_prompt(&f.text,&cleared) && !cleared);
        /* Rejected video preflight is entirely non-mutating. */
        untouched=f.events[0];
        f.events[0].pen=1U; /* malformed CLEAR_TEXT reserved field */
        text_before=f.text;video_before=f.video;
        assert(hw4_pen_preflight(&f.text,f.output,0U,f.events,1U)==
               HW4_PEN_INVALID_EVENT);
        assert(hw4_pen_replay(&f.text,f.output,0U,f.events,1U)==
               HW4_PEN_INVALID_EVENT);
        assert(memcmp(&f.text,&text_before,sizeof(text_before))==0);
        assert(memcmp(&f.video,&video_before,sizeof(video_before))==0);
        assert(f.events[0].pen==1U);
        f.events[0]=untouched;
    }
    /* Host !CLS deliberately restores the boot palette, unlike native CLS. */
    assert(hw4_pen_console_clear(&f.text));
    assert(f.video.ink[0]==1U && f.video.ink[1]==24U &&
           f.video.ink[2]==20U && f.video.ink[3]==6U);
    assert(f.program.size==old_program_size &&
           memcmp(f.program_bytes,original_program,sizeof(original_program))==0);
}

static void test_j121_c2_direct_rejections_and_running(void)
{
    static const char *const other[]={
        "CLS:CLS","CLS #1","CLSX","PRINT \"X\"","10 CLS",
        "LIST","NEW","RUN","!CLS"
    };
    setup();
    for(size_t i=0U;i<sizeof(other)/sizeof(other[0]);++i) {
        f.written=55U;f.event_written=66U;
        memset(f.events,0x5a,sizeof(f.events));
        assert(bsr_prepare_direct_events(&f.runtime,
               (const uint8_t *)other[i],strlen(other[i]),
               f.output,sizeof(f.output),&f.written,
               f.events,1U,&f.event_written).status!=BSR_OK);
        assert(f.written==55U && f.event_written==66U);
        for(size_t j=0U;j<sizeof(f.events);++j)
            assert(((const uint8_t *)f.events)[j]==0x5aU);
    }
    f.written=55U;f.event_written=66U;
    assert(bsr_prepare_direct_events(&f.runtime,
           (const uint8_t *)"CLS",3U,f.output,sizeof(f.output),&f.written,
           f.events,0U,&f.event_written).executor_status==BE_NO_EVENT_SPACE);
    assert(f.written==55U && f.event_written==66U);
    assert(submit("10 PRINT \"RUNNING\"").status==BSR_OK);
    assert(submit("RUN").status==BSR_OK);
    f.written=55U;f.event_written=66U;
    assert(bsr_prepare_direct_events(&f.runtime,
           (const uint8_t *)"CLS",3U,f.output,sizeof(f.output),&f.written,
           f.events,1U,&f.event_written).status==BSR_BUSY);
    assert(f.written==55U && f.event_written==66U);
    assert(f.runtime.state==BSR_RUNNING);
    assert(bsr_stop(&f.runtime).status==BSR_OK);
}

/* Source contract: executing direct CLS must use C1/bridge and fail-stop;
 * this canary specifically rejects a host-only bridge test with NO console
 * integration. It does not claim to execute ESP-IDF UART or LCD on Linux. */
static void test_j121_c2_console_wiring_contract(void)
{
    const char *path=getenv("HW4_PEN_C2_CONSOLE_SOURCE");
    static char source[80000];
    const char *start,*end,*prepared,*preflight,*end_line,*replay,*fail_stop;
    FILE *fp;
    size_t n;
    assert(path!=NULL);
    fp=fopen(path,"rb");
    assert(fp!=NULL);
    n=fread(source,1U,sizeof(source)-1U,fp);
    assert(!ferror(fp) && feof(fp) && fclose(fp)==0);
    source[n]='\0';
    start=strstr(source,"static bool execute_line(");
    assert(start!=NULL);
    end=strstr(start,"static bool uart_init(");
    assert(end!=NULL);
    prepared=strstr(start,"bsr_prepare_direct_events(");
    preflight=strstr(start,"hw4_pen_preflight(");
    end_line=strstr(start,"cpc_uart_console_end_line(&s_text)");
    replay=strstr(start,"hw4_pen_replay(");
    fail_stop=strstr(start,"return fail(\"DIRECT_CLS_REPLAY\"");
    assert(prepared!=NULL && prepared<end && preflight!=NULL &&
           end_line!=NULL && replay!=NULL && fail_stop!=NULL);
    assert(prepared<preflight && preflight<end_line &&
           end_line<replay && replay<fail_stop && fail_stop<end);
    assert(strstr(start,"s_basic.runtime.state==BSR_IDLE")<prepared);
    assert(strstr(start,"if(direct_cls) {")!=NULL);
    assert(strstr(start,"CPC_READY_UNCHARACTERIZED_DIRECT")!=NULL);
}

/* HW4-PEN-LOGICAL-B1: compare a bounded native MODE1 candidate with the
 * independently sealed J1.17-C-A C/D colour observations. The CPC oracle
 * records only background-coloured ROI for PEN8/12, NOT their hidden index.
 * Pixel 0 is the candidate representation, checked separately below.
 * Source archive + external seals are enforced by CPC-PERMANENT CI. */
static void j117_ca_palette(unsigned context)
{
    static const uint8_t c[4]={0U,26U,6U,18U};
    static const uint8_t d[4]={1U,24U,20U,6U};
    const uint8_t *ink=context==0U ? c:d;
    for(unsigned i=0U;i<4U;++i)
        assert(cpc_video_set_ink(&f.video,i,ink[i]));
    assert(cpc_video_set_text_colors(&f.video,1U,0U));
}

static void test_j117_ca_pens_mode1_oracle_contexts(void)
{
    /* C: white/red/green/background; D: yellow/cyan/red/background.
     * No general logical->pixel folding for other modes or ink contexts. */
    static const uint8_t candidate_pixel[10]=
        {1U,2U,3U,0U,1U,2U,3U,0U,1U,2U};
    static const uint8_t c_observed_ink[10]=
        {26U,6U,18U,0U,26U,6U,18U,0U,26U,6U};
    static const uint8_t d_observed_ink[10]=
        {24U,20U,6U,1U,24U,20U,6U,1U,24U,20U};
    static const char printed[]="J117PEN\n";
    for(unsigned context=0U;context<2U;++context) {
        for(unsigned pen=5U;pen<=14U;++pen) {
            const unsigned k=pen-5U;
            const uint8_t *observed=context==0U ?
                                    c_observed_ink:d_observed_ink;
            char line[32], expected_list[80];
            uint16_t rendered[CPC_VIDEO_TFT_WIDTH];
            uint8_t mapped=255U;
            bool ready=false,reset_page=true,known=false;
            uint8_t listed=0U;
            size_t saved_size;
            unsigned ready_count=0U;
            setup();
            j117_ca_palette(context);
            assert(snprintf(line,sizeof(line),"10 PEN %u",pen)>0);
            assert(submit(line).status==BSR_OK);
            assert(submit("20 PRINT \"J117PEN\"").status==BSR_OK);
            assert(submit("30 END").status==BSR_OK);
            saved_size=f.program.size;
            assert(snprintf(expected_list,sizeof(expected_list),
                "10 PEN %u\n20 PRINT \"J117PEN\"\n30 END\n",pen)>0);
            assert(submit("LIST").status==BSR_OK);
            assert(f.written==strlen(expected_list) &&
                   memcmp(f.output,expected_list,f.written)==0);
            assert(hw4_pen_pixel_index(&f.video,(uint8_t)pen,&mapped)
                   ==HW4_PEN_OK);
            assert(mapped==candidate_pixel[k]); /* chosen internal index */
            assert(submit("RUN").status==BSR_OK);
            assert(step(OUT_CAP,3U).status==BSR_OK);
            assert(f.written==0U && f.event_written==1U);
            assert(f.events[0].type==BE_VIDEO_SET_TEXT_PEN &&
                   f.events[0].pen==pen && f.events[0].print_offset==0U);
            assert(hw4_pen_preflight(&f.text,f.output,f.written,
                   f.events,f.event_written)==HW4_PEN_OK);
            assert(hw4_pen_replay(&f.text,f.output,f.written,
                   f.events,f.event_written)==HW4_PEN_OK);
            assert(step(OUT_CAP,3U).status==BSR_OK);
            assert(f.written==sizeof(printed)-1U && f.event_written==0U);
            assert(memcmp(f.output,printed,f.written)==0);
            assert(hw4_pen_replay(&f.text,f.output,f.written,
                   f.events,f.event_written)==HW4_PEN_OK);
            assert(f.text.bytes_received==f.written);
            assert(f.text.glyphs_drawn==sizeof(printed)-2U);
            assert(cpc_video_render_row(&f.video,CPC_VIDEO_VIEW_TOP,
                   rendered,CPC_VIDEO_TFT_WIDTH));
            /* This is the OBSERVED CPC colour, unlike the local index. */
            assert(rendered[0]==cpc_video_palette_rgb565(observed[k]));
            if(pen==8U || pen==12U) {
                /* Background-only CPC ROI: do not claim measured index 0. */
                assert(rendered[0]==cpc_video_palette_rgb565(f.video.ink[0]));
                assert(pixel_at(0U,0U)==candidate_pixel[k]);
            } else {
                assert(pixel_at(0U,0U)==candidate_pixel[k]);
                assert(rendered[0]!=cpc_video_palette_rgb565(f.video.ink[0]));
            }
            assert(cpc_video_read_cell(&f.video,0U,0U,&listed,&known));
            assert(known && listed==(uint8_t)'J');
            assert(step(OUT_CAP,3U).status==BSR_OK); /* END */
            assert(f.written==0U && f.event_written==0U);
            assert(step(OUT_CAP,3U).status==BSR_END);
            assert(cpc_ready_policy_apply(&f.text,CPC_READY_RUN_RETURN,&ready));
            if(ready) ++ready_count;
            assert(ready_count==1U);
            assert(cpc_uart_console_prompt(&f.text,&reset_page) && !reset_page);
            assert(f.program.size==saved_size);
        }
    }
}

/* A later forbidden event must reject the entire PEN5+PRINT step BEFORE
 * even the first glyph/cursor/ink mutation. An unmeasured ink combination
 * must not turn a coincidentally identical RGB into a certified mapping. */
static void test_j117_ca_palette_and_atomic_guards(void)
{
    const uint8_t bytes[]={'A','\n','B','\n'};
    BEVideoEvent events[2]={
        {BE_VIDEO_SET_TEXT_PEN,5U,0U,0U,0U},
        {BE_VIDEO_SET_TEXT_PEN,6U,2U,0U,0U}
    };
    setup(); /* mixed boot palette is neither witnessed C nor D */
    assert_rejected_replay(events,2U,bytes,sizeof(bytes),
                           HW4_PEN_UNVERIFIED_VISUAL);
    setup();
    j117_ca_palette(0U);
    assert(cpc_video_set_ink(&f.video,1U,24U)); /* C partially changed */
    assert_rejected_replay(events,2U,bytes,sizeof(bytes),
                           HW4_PEN_UNVERIFIED_VISUAL);
    setup();
    j117_ca_palette(1U);
    assert(cpc_video_set_ink(&f.video,3U,18U)); /* D partially changed */
    assert_rejected_replay(events,2U,bytes,sizeof(bytes),
                           HW4_PEN_UNVERIFIED_VISUAL);
    setup();
    j117_ca_palette(0U);
    assert(cpc_video_set_text_colors(&f.video,1U,1U)); /* not PAPER0 */
    assert_rejected_replay(events,2U,bytes,sizeof(bytes),
                           HW4_PEN_UNVERIFIED_VISUAL);
    setup();
    j117_ca_palette(1U);
    events[1].type=BE_VIDEO_SET_INK;
    assert_rejected_replay(events,2U,bytes,sizeof(bytes),
                           HW4_PEN_SET_INK_UNSUPPORTED);
    events[1].type=BE_VIDEO_SET_TEXT_PEN;
    events[1].pen=16U;
    assert_rejected_replay(events,2U,bytes,sizeof(bytes),
                           HW4_PEN_UNSUPPORTED_LOGICAL);
    /* The positive pen5 preflight does not exempt a subsequent bad offset. */
    events[1].pen=6U;
    events[1].print_offset=5U;
    assert_rejected_replay(events,2U,bytes,sizeof(bytes),
                           HW4_PEN_BAD_OFFSET);
}

int main(int argc, char **argv)
{
    /* Separate, explicitly named B1 gate: no firmware-source canary needed.
     * The full historical HW4 test still runs these same regressions. */
    if(argc==2 && strcmp(argv[1],"--b1")==0) {
        test_j117_ca_pens_mode1_oracle_contexts();
        test_j117_ca_palette_and_atomic_guards();
        puts("HW4-PEN-LOGICAL-B1: CPC C/D MODE1 and atomic negatives PASS");
        return 0;
    }
    assert(argc==1);
    test_j121_c2_console_wiring_contract();
    test_j121_c2_direct_rejections_and_running();
    test_j121_c2_direct_cls_mode1();
    test_cpc_palette_boot_source();
    test_cpc_palette_run_and_clear();
    test_cpc_palette_native_cls_keeps_inks();
    test_diag_pen_native_and_host_guards();
    test_j117_ca_pens_mode1_oracle_contexts();
    test_j117_ca_palette_and_atomic_guards();
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
