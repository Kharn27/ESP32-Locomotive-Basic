/* HW4-RUN-BREAK-B: real portable BSR + PEN video + UART parser.
 * Tests route the same production functions as the sole CONSOLE owner;
 * no emulated ESP-IDF/CYD or invented CPC diagnostic. */
#include "hw4_run_break_input.h"
#include "hw4_run_scheduler.h"
#include "hw4_pen_bridge.h"
#include "cpc_ready_policy.h"
#include "cpc_diag_policy.h"
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if(!(x)) { \
    fprintf(stderr,"%s:%d %s\n",__FILE__,__LINE__,#x); return 1; \
} } while(0)
typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    Hw4RunScheduler scheduler;
    Hw4RunBreakInput parser;
    uint8_t image[2048],temporary[256],output[256];
    size_t written,event_written,ready_count;
    BEVideoEvent events[4];
    CpcVideo video;
    CpcText text;
    uint8_t vram[CPC_VIDEO_BYTES];
    size_t prints,events_seen;
    bool reject_replay;
} Fixture;
static Fixture f;
static uint8_t glyph(void *ctx,uint8_t ch,unsigned row)
{
    (void)ctx;
    return row==0u && ch!=(uint8_t)' ' ? 0x80u : 0u;
}
static int setup(void)
{
    memset(&f,0,sizeof(f));
    CHECK(bp_init(&f.program,f.image,sizeof(f.image))==BP_OK);
    CHECK(bsr_init(&f.runtime,&f.program).status==BSR_OK);
    CHECK(cpc_video_init(&f.video,f.vram,sizeof(f.vram),CPC_MODE_1));
    CHECK(cpc_video_set_ink(&f.video,0u,1u));
    CHECK(cpc_video_set_ink(&f.video,1u,24u));
    CHECK(cpc_video_set_ink(&f.video,2u,6u));
    CHECK(cpc_video_set_ink(&f.video,3u,18u));
    CHECK(cpc_video_set_text_colors(&f.video,1u,0u));
    CHECK(cpc_text_init(&f.text,&f.video,glyph,NULL));
    hw4_run_break_input_init(&f.parser);
    return 0;
}
static BSRResult submit(const char *s)
{
    return bsr_submit(&f.runtime,(const uint8_t *)s,strlen(s),
        f.temporary,sizeof(f.temporary),f.output,sizeof(f.output),&f.written);
}
static int start_run(void)
{
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(hw4_run_scheduler_init(&f.scheduler,&f.runtime));
    hw4_run_break_input_init(&f.parser);
    return 0;
}
static bool preflight(void *ctx,const uint8_t *bytes,size_t length,
                      const BEVideoEvent *events,size_t count)
{
    Fixture *p=(Fixture *)ctx;
    return hw4_pen_preflight(&p->text,bytes,length,events,count)==HW4_PEN_OK;
}
static bool replay(void *ctx,const uint8_t *bytes,size_t length,
                   const BEVideoEvent *events,size_t count)
{
    Fixture *p=(Fixture *)ctx;
    if(p->reject_replay) return false;
    if(hw4_pen_replay(&p->text,bytes,length,events,count)!=HW4_PEN_OK)
        return false;
    p->prints+=length;
    p->events_seen+=count;
    return true;
}
static Hw4RunSlice advance(size_t quantum)
{
    Hw4RunReceiver receiver={preflight,replay,NULL,&f};
    return hw4_run_scheduler_slice(&f.scheduler,quantum,&receiver,
       f.output,sizeof(f.output),&f.written,
       f.events,4u,&f.event_written);
}
static int finish_ready(void)
{
    bool emitted=false;
    CHECK(cpc_ready_policy_apply(&f.text,CPC_READY_RUN_RETURN,&emitted));
    CHECK(emitted);
    ++f.ready_count;
    return 0;
}
static int parser_edges(void)
{
    static const char *bad[]={"!BREAKX\n","!BREA\n","!BREAK \r",
                               "RUN\n","!SHOT\r","!BR\x1b" "EAK\n",
                               "!BREAK!BREAK\n"};
    size_t i,j;
    CHECK(setup()==0);
    {
        const char *p="!br";
        for(i=0u;i<strlen(p);++i)
            CHECK(hw4_run_break_input_feed(&f.parser,(uint8_t)p[i])
                  ==HW4_BREAK_INPUT_NONE);
        p="eAk\r\n";
        CHECK(hw4_run_break_input_feed(&f.parser,(uint8_t)p[0])
              ==HW4_BREAK_INPUT_NONE);
        CHECK(hw4_run_break_input_feed(&f.parser,(uint8_t)p[1])
              ==HW4_BREAK_INPUT_NONE);
        CHECK(hw4_run_break_input_feed(&f.parser,(uint8_t)p[2])
              ==HW4_BREAK_INPUT_NONE);
        CHECK(hw4_run_break_input_feed(&f.parser,(uint8_t)p[3])
              ==HW4_BREAK_INPUT_REQUEST);
        CHECK(hw4_run_break_input_feed(&f.parser,(uint8_t)p[4])
              ==HW4_BREAK_INPUT_NONE);
    }
    for(i=0u;i<sizeof(bad)/sizeof(bad[0]);++i) {
        for(j=0u;j<strlen(bad[i]);++j) {
            Hw4BreakInputEvent ev=hw4_run_break_input_feed(
                &f.parser,(uint8_t)bad[i][j]);
            CHECK(ev!=HW4_BREAK_INPUT_REQUEST);
        }
    }
    CHECK(f.parser.ignored_lines==sizeof(bad)/sizeof(bad[0]));
    CHECK(f.parser.overflow_lines>=2u);
    CHECK(hw4_run_break_input_feed(&f.parser,'!')==HW4_BREAK_INPUT_NONE);
    CHECK(hw4_run_break_input_feed(&f.parser,'\n')==HW4_BREAK_INPUT_IGNORED);
    {
        const char *p="!BREAK\n";
        for(i=0u;i<strlen(p)-1u;++i)
            CHECK(hw4_run_break_input_feed(&f.parser,(uint8_t)p[i])
                  ==HW4_BREAK_INPUT_NONE);
        CHECK(hw4_run_break_input_feed(&f.parser,'\n')
              ==HW4_BREAK_INPUT_REQUEST);
    }
    return 0;
}
static int infinite_run_and_fragmented_break(void)
{
    uint8_t initial[sizeof(f.image)];
    size_t i; Hw4RunSlice state;
    CHECK(setup()==0);
    CHECK(submit("10 PEN 3:PRINT \"SCROLL GREEN\"").status==BSR_OK);
    CHECK(submit("20 GOTO 10").status==BSR_OK);
    memcpy(initial,f.image,sizeof(initial));
    CHECK(start_run()==0);
    for(i=0u;i<130u;++i) {
        state=advance(32u);
        CHECK(state.state==HW4_RUN_YIELDED && state.steps==32u);
        CHECK(f.runtime.state==BSR_RUNNING && f.ready_count==0u);
    }
    CHECK(f.scheduler.total_steps==4160u);
    CHECK(f.prints==2080u*strlen("SCROLL GREEN\n"));
    CHECK(f.events_seen==2080u);
    CHECK(f.text.scrolls>1000u);
    CHECK(memcmp(initial,f.image,sizeof(initial))==0);
    {
        const char *a="!Br",*b="EaK\r\n";
        for(i=0u;i<strlen(a);++i)
            CHECK(hw4_run_break_input_feed(&f.parser,(uint8_t)a[i])
                  ==HW4_BREAK_INPUT_NONE);
        for(i=0u;i<strlen(b);++i) {
            Hw4BreakInputEvent ev=hw4_run_break_input_feed(&f.parser,(uint8_t)b[i]);
            if(i==3u) {
                CHECK(ev==HW4_BREAK_INPUT_REQUEST);
                CHECK(hw4_run_scheduler_request_break(&f.scheduler));
            } else CHECK(ev==HW4_BREAK_INPUT_NONE);
        }
    }
    {
        size_t prev=f.prints;
        state=advance(8u);
        CHECK(state.state==HW4_RUN_BROKEN && state.steps==0u);
        CHECK(f.prints==prev && f.scheduler.total_steps==4160u);
        CHECK(f.scheduler.stop_calls==1u && f.runtime.state==BSR_IDLE);
        CHECK(memcmp(initial,f.image,sizeof(initial))==0);
        CHECK(f.ready_count==0u);
    }
    CHECK(finish_ready()==0 && f.ready_count==1u);
    CHECK(submit("LIST").status==BSR_OK);
    CHECK(f.written==strlen("10 PEN 3:PRINT \"SCROLL GREEN\"\n20 GOTO 10\n"));
    CHECK(memcmp(f.output,"10 PEN 3:PRINT \"SCROLL GREEN\"\n20 GOTO 10\n",
                 f.written)==0);
    CHECK(start_run()==0);
    CHECK(advance(8u).state==HW4_RUN_YIELDED);
    CHECK(hw4_run_scheduler_request_break(&f.scheduler));
    CHECK(advance(8u).state==HW4_RUN_BROKEN);
    CHECK(submit("NEW").status==BSR_OK);
    CHECK(submit("LIST").status==BSR_OK && f.written==0u);
    return 0;
}
static int pen_error_and_video_reject(void)
{
    size_t cursor; BasicProgramLine line; CpcStepDiagnostic diag;
    CHECK(setup()==0);
    CHECK(submit("10 PEN 2").status==BSR_OK);
    CHECK(submit("20 PEN 16:PRINT \"NEVER\"").status==BSR_OK);
    CHECK(start_run()==0);
    CHECK(advance(1u).state==HW4_RUN_YIELDED);
    cursor=f.runtime.executor.cursor;
    CHECK(advance(8u).state==HW4_RUN_EXECUTOR_ERROR);
    CHECK(f.scheduler.last_result.executor_status==BE_INVALID_PEN);
    CHECK(f.runtime.executor.cursor==cursor);
    CHECK(bp_next(&f.program,&cursor,&line)==BP_OK && line.number==20u);
    diag=cpc_diag_policy_step(f.scheduler.last_result,&f.runtime);
    CHECK(diag.category==CPC_DIAG_PEN_IMPROPER_ARGUMENT);
    CHECK(diag.origin==CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE);
    CHECK(diag.line_number==20u);
    CHECK(bsr_stop(&f.runtime).status==BSR_OK);
    CHECK(finish_ready()==0);
    CHECK(setup()==0);
    CHECK(submit("10 PEN 2:PRINT \"NO\":INK 1,26").status==BSR_OK);
    CHECK(start_run()==0);
    CHECK(advance(8u).state==HW4_RUN_DISPLAY_ERROR);
    CHECK(f.scheduler.display_failure==HW4_RUN_DISPLAY_PREFLIGHT_FAILED);
    CHECK(f.prints==0u && f.events_seen==0u && f.text.bytes_received==0u);
    CHECK(advance(8u).state==HW4_RUN_INVALID_ARGUMENT);
    CHECK(bsr_stop(&f.runtime).status==BSR_OK);
    CHECK(setup()==0);
    CHECK(submit("10 PEN 2:PRINT \"NO\"").status==BSR_OK);
    CHECK(start_run()==0);
    f.reject_replay=true;
    CHECK(advance(8u).state==HW4_RUN_DISPLAY_ERROR);
    CHECK(f.scheduler.display_failure==HW4_RUN_DISPLAY_REPLAY_FAILED);
    CHECK(f.prints==0u && f.text.bytes_received==0u);
    return 0;
}
static int inline_end_and_no_reentry(void)
{
    CHECK(setup()==0);
    CHECK(submit("10 PEN 2:PRINT \"AVANT\":END:PRINT \"INVISIBLE\"").status==BSR_OK);
    CHECK(submit("20 PRINT \"NEVER\"").status==BSR_OK);
    CHECK(start_run()==0);
    CHECK(advance(1u).state==HW4_RUN_YIELDED);
    CHECK(f.prints==6u && f.events_seen==1u && f.ready_count==0u);
    CHECK(advance(8u).state==HW4_RUN_ENDED);
    CHECK(f.prints==6u && f.events_seen==1u);
    CHECK(finish_ready()==0 && f.ready_count==1u);
    CHECK(advance(1u).state==HW4_RUN_INVALID_ARGUMENT);
    return 0;
}
/* Source-level gate: ensure actual production CONSOLE dispatches the
 * independently tested C99 pieces, and cannot restore 256-step cutoff. */
static int production_wiring(const char *path)
{
    FILE *fp=fopen(path,"rb");
    char src[55000];
    size_t n;
    static const char *required[]={
        "#include \"hw4_run_break_input.h\"",
        "hw4_run_scheduler_init(&s_run_scheduler",
        "hw4_run_scheduler_slice(&s_run_scheduler",
        "hw4_run_break_input_feed(&s_run_input,byte)",
        "hw4_run_scheduler_request_break(&s_run_scheduler)",
        "cpc_diag_policy_step(r,&s_basic.runtime)",
        "hw4_pen_preflight(&s_text",
        "hw4_pen_replay(&s_text",
        "if(slice.state==HW4_RUN_YIELDED)",
        "vTaskDelay(1)",
        "uart_flush_input(UART_NUM_0)",
        "s_run_skip_crlf_lf",
        "capture_screen(\"PROMPT\")"
    };
    size_t i;
    CHECK(fp!=NULL);
    n=fread(src,1u,sizeof(src)-1u,fp);
    CHECK(!ferror(fp) && fclose(fp)==0 && n<sizeof(src)-1u);
    src[n]='\0';
    CHECK(strstr(src,"RUN_STEP_BUDGET")==NULL);
    CHECK(strstr(src,"BSR_STEP_BUDGET_EXCEEDED")==NULL);
    for(i=0u;i<sizeof(required)/sizeof(required[0]);++i)
        CHECK(strstr(src,required[i])!=NULL);
    return 0;
}
int main(int argc,char **argv)
{
    CHECK(argc==2);
    CHECK(parser_edges()==0);
    CHECK(infinite_run_and_fragmented_break()==0);
    CHECK(pen_error_and_video_reject()==0);
    CHECK(inline_end_and_no_reentry()==0);
    CHECK(production_wiring(argv[1])==0);
    puts("HW4-RUN-BREAK-B real BSR/PEN parser 4160 steps + BREAK PASS");
    return 0;
}
