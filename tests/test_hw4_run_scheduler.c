/* HW4-RUN-BREAK-A: executable tests with the real C99 BasicSessionRuntime.
 * No hardware, heap, extra FreeRTOS task or fake 256-step budget. */
#include "hw4_run_scheduler.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x); return 1; } } while (0)
enum { EVENTS=8, STORAGE=2048, OUTPUT=256 };
typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    Hw4RunScheduler scheduler;
    uint8_t image[STORAGE];
    uint8_t temporary[256];
    uint8_t output[OUTPUT];
    BEVideoEvent events[EVENTS];
    size_t written, event_written;
} Fixture;
typedef struct {
    size_t calls, bytes, pens, preflights, polls;
    size_t request_at, poll_at;
    bool reject_preflight, reject_replay, reject_ink;
    char order[64];
    size_t order_len;
} Sink;
static Fixture f;
static Sink s;
static int setup(void) {
    memset(&f,0,sizeof(f)); memset(&s,0,sizeof(s));
    CHECK(bp_init(&f.program,f.image,sizeof(f.image))==BP_OK);
    CHECK(bsr_init(&f.runtime,&f.program).status==BSR_OK);
    return 0;
}
static BSRResult submit(const char *source) {
    return bsr_submit(&f.runtime,(const uint8_t *)source,strlen(source),
      f.temporary,sizeof(f.temporary),f.output,sizeof(f.output),&f.written);
}
static int run(void) {
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(hw4_run_scheduler_init(&f.scheduler,&f.runtime));
    return 0;
}
/* Preflight stays pure: no PRINT or PEN mutation, including rejected INK. */
static bool preflight(void *context,const uint8_t *p,size_t n,
                       const BEVideoEvent *events,size_t count) {
    Sink *sink=(Sink *)context; size_t i, prior=0u;
    (void)p;
    ++sink->preflights;
    if(sink->reject_preflight) return false;
    for(i=0u;i<count;++i) {
        if(events[i].print_offset<prior || events[i].print_offset>n) return false;
        prior=events[i].print_offset;
        if(events[i].type==BE_VIDEO_SET_INK && sink->reject_ink) return false;
        if(events[i].type!=BE_VIDEO_SET_INK &&
           events[i].type!=BE_VIDEO_SET_TEXT_PEN) return false;
    }
    return true;
}
/* Ordered PRINT bytes and typed video events, recorded without a renderer. */
static bool replay(void *context,const uint8_t *p,size_t n,
                   const BEVideoEvent *events,size_t count) {
    Sink *sink=(Sink *)context; size_t i,j,prev=0u;
    if(sink->reject_replay) return false;
    for(i=0u;i<=count;++i) {
        size_t next=i==count?n:events[i].print_offset;
        for(j=prev;j<next;++j) {
            if(sink->order_len<sizeof(sink->order))
                sink->order[sink->order_len++]=(char)p[j];
        }
        if(i<count) {
            ++sink->pens;
            if(sink->order_len<sizeof(sink->order))
                sink->order[sink->order_len++]=
                    events[i].type==BE_VIDEO_SET_INK ? 'I' :
                    (char)('0'+events[i].pen);
        }
        prev=next;
    }
    ++sink->calls; sink->bytes+=n;
    if(sink->request_at!=0u && sink->calls==sink->request_at)
        (void)hw4_run_scheduler_request_break(&f.scheduler);
    return true;
}
static bool poll(void *context) {
    Sink *sink=(Sink *)context;
    ++sink->polls;
    return sink->poll_at!=0u && sink->polls>=sink->poll_at;
}
static Hw4RunSlice step(size_t quantum,size_t outcap,size_t eventcap) {
    Hw4RunReceiver receiver={preflight,replay,poll,&s};
    return hw4_run_scheduler_slice(&f.scheduler,quantum,&receiver,
         f.output,outcap,&f.written,f.events,eventcap,&f.event_written);
}
static int unbounded_loop_and_break(void) {
    uint8_t original[STORAGE]; size_t i;
    CHECK(setup()==0);
    CHECK(submit("10 PEN 3:PRINT \"SCROLL GREEN\"").status==BSR_OK);
    CHECK(submit("20 GOTO 10").status==BSR_OK);
    memcpy(original,f.image,sizeof(original));
    CHECK(run()==0);
    for(i=0u;i<130u;++i) {
        Hw4RunSlice r=step(32u,OUTPUT,EVENTS);
        CHECK(r.state==HW4_RUN_YIELDED && r.steps==32u);
        CHECK(f.runtime.state==BSR_RUNNING);
        CHECK(f.scheduler.stop_calls==0u);
    }
    CHECK(f.scheduler.total_steps==4160u && s.calls==4160u);
    CHECK(s.bytes==2080u*strlen("SCROLL GREEN\n") && s.pens==2080u);
    CHECK(memcmp(s.order,"3SCROLL GREEN\n3SCROLL GREEN\n",28u)==0);
    CHECK(memcmp(f.image,original,sizeof(original))==0);
    CHECK(bp_validate(&f.program)==BP_OK);
    CHECK(hw4_run_scheduler_request_break(&f.scheduler));
    CHECK(step(32u,OUTPUT,EVENTS).state==HW4_RUN_BROKEN);
    CHECK(f.scheduler.stop_calls==1u && f.runtime.state==BSR_IDLE);
    CHECK(s.calls==4160u && memcmp(f.image,original,sizeof(original))==0);
    CHECK(!hw4_run_scheduler_request_break(&f.scheduler));
    CHECK(step(1u,OUTPUT,EVENTS).state==HW4_RUN_INVALID_ARGUMENT);
    CHECK(run()==0); /* A new RUN is explicit; a yield does NOT restart. */
    CHECK(step(8u,OUTPUT,EVENTS).state==HW4_RUN_YIELDED);
    CHECK(f.scheduler.total_steps==8u && f.scheduler.stop_calls==0u);
    return 0;
}
static int break_during_callback_and_poll(void) {
    CHECK(setup()==0);
    CHECK(submit("10 PRINT \"YES\"").status==BSR_OK);
    CHECK(submit("20 GOTO 10").status==BSR_OK);
    CHECK(run()==0); s.request_at=3u;
    {
        Hw4RunSlice r=step(32u,OUTPUT,EVENTS);
        CHECK(r.state==HW4_RUN_BROKEN && r.steps==3u);
        CHECK(s.bytes==8u && f.scheduler.stop_calls==1u);
    }
    CHECK(run()==0); s.request_at=0u; s.poll_at=s.polls+1u;
    {
        size_t before=s.calls;
        Hw4RunSlice r=step(32u,OUTPUT,EVENTS);
        CHECK(r.state==HW4_RUN_BROKEN && r.steps==0u);
        CHECK(s.calls==before && f.scheduler.stop_calls==1u);
    }
    return 0;
}
static int end_and_event_order(void) {
    CHECK(setup()==0);
    CHECK(submit("10 PEN 2:PRINT \"A\":PEN 1:PRINT \"B\"").status==BSR_OK);
    CHECK(submit("20 END").status==BSR_OK);
    CHECK(submit("30 PRINT \"NEVER\"").status==BSR_OK);
    CHECK(run()==0);
    CHECK(step(1u,OUTPUT,EVENTS).state==HW4_RUN_YIELDED);
    CHECK(s.bytes==4u && s.pens==2u);
    CHECK(memcmp(s.order,"2A\n1B\n",6u)==0);
    CHECK(step(8u,OUTPUT,EVENTS).state==HW4_RUN_ENDED);
    CHECK(f.scheduler.last_result.status==BSR_END);
    CHECK(f.scheduler.last_result.executor_status==BE_END);
    CHECK(f.runtime.state==BSR_IDLE && s.bytes==4u);
    CHECK(f.scheduler.stop_calls==0u);
    return 0;
}
static int pen_error_context_and_atomicity(void) {
    size_t cursor; BasicProgramLine line;
    uint8_t original[STORAGE];
    CHECK(setup()==0);
    CHECK(submit("10 PEN 2").status==BSR_OK);
    CHECK(submit("20 PEN 16:PRINT \"NEVER\"").status==BSR_OK);
    memcpy(original,f.image,sizeof(original));
    CHECK(run()==0);
    CHECK(step(1u,OUTPUT,EVENTS).state==HW4_RUN_YIELDED);
    cursor=f.runtime.executor.cursor;
    CHECK(step(8u,OUTPUT,EVENTS).state==HW4_RUN_EXECUTOR_ERROR);
    CHECK(f.scheduler.last_result.status==BSR_EXECUTOR_ERROR);
    CHECK(f.scheduler.last_result.executor_status==BE_INVALID_PEN);
    CHECK(f.runtime.state==BSR_RUNNING);
    CHECK(f.runtime.executor.cursor==cursor);
    CHECK(bp_next(&f.program,&cursor,&line)==BP_OK && line.number==20u);
    CHECK(s.bytes==0u && f.scheduler.stop_calls==0u);
    CHECK(memcmp(f.image,original,sizeof(original))==0);
    CHECK(step(1u,OUTPUT,EVENTS).state==HW4_RUN_INVALID_ARGUMENT);
    CHECK(bsr_stop(&f.runtime).status==BSR_OK);
    return 0;
}
static int negative_arguments_and_limits(void) {
    BasicSessionRuntime before;
    Hw4RunReceiver receiver={preflight,replay,poll,&s};
    CHECK(setup()==0);
    CHECK(!hw4_run_scheduler_init(&f.scheduler,&f.runtime));
    CHECK(submit("10 PEN 2:PRINT \"HELLO\"").status==BSR_OK);
    CHECK(submit("RUN+").status==BSR_SESSION_ERROR);
    CHECK(run()==0); before=f.runtime;
    CHECK(step(0u,OUTPUT,EVENTS).state==HW4_RUN_INVALID_ARGUMENT);
    CHECK(step(HW4_RUN_QUANTUM_MAX+1u,OUTPUT,EVENTS).state==HW4_RUN_INVALID_ARGUMENT);
    CHECK(hw4_run_scheduler_slice(&f.scheduler,1u,NULL,f.output,OUTPUT,
          &f.written,f.events,EVENTS,&f.event_written).state==HW4_RUN_INVALID_ARGUMENT);
    receiver.preflight=NULL;
    CHECK(hw4_run_scheduler_slice(&f.scheduler,1u,&receiver,f.output,OUTPUT,
          &f.written,f.events,EVENTS,&f.event_written).state==HW4_RUN_INVALID_ARGUMENT);
    CHECK(memcmp(&f.runtime,&before,sizeof(before))==0);
    CHECK(f.scheduler.total_steps==0u);
    CHECK(step(1u,OUTPUT,0u).state==HW4_RUN_EXECUTOR_ERROR);
    CHECK(f.scheduler.last_result.executor_status==BE_NO_EVENT_SPACE);
    CHECK(s.calls==0u && s.preflights==0u);
    CHECK(run()==0);
    CHECK(step(1u,1u,EVENTS).state==HW4_RUN_EXECUTOR_ERROR);
    CHECK(f.scheduler.last_result.executor_status==BE_NO_SPACE);
    CHECK(s.calls==0u);
    return 0;
}
static int display_fail_stop(void) {
    CHECK(setup()==0);
    CHECK(submit("10 PEN 3:PRINT \"FIRST\"").status==BSR_OK);
    CHECK(submit("20 PEN 3:PRINT \"SECOND\"").status==BSR_OK);
    CHECK(run()==0); s.reject_preflight=true;
    CHECK(step(8u,OUTPUT,EVENTS).state==HW4_RUN_DISPLAY_ERROR);
    CHECK(f.scheduler.display_failure==HW4_RUN_DISPLAY_PREFLIGHT_FAILED);
    CHECK(s.calls==0u && f.scheduler.stop_calls==0u);
    CHECK(f.runtime.state==BSR_RUNNING);
    CHECK(step(8u,OUTPUT,EVENTS).state==HW4_RUN_INVALID_ARGUMENT);
    CHECK(run()==0); s.reject_preflight=false; s.reject_replay=true;
    CHECK(step(8u,OUTPUT,EVENTS).state==HW4_RUN_DISPLAY_ERROR);
    CHECK(f.scheduler.display_failure==HW4_RUN_DISPLAY_REPLAY_FAILED);
    CHECK(s.calls==0u);
    return 0;
}
static int ink_rejects_whole_step(void) {
    CHECK(setup()==0);
    CHECK(submit("10 PEN 2:PRINT \"NO\":INK 1,26").status==BSR_OK);
    CHECK(submit("20 PRINT \"NEVER\"").status==BSR_OK);
    CHECK(run()==0); s.reject_ink=true;
    CHECK(step(4u,OUTPUT,EVENTS).state==HW4_RUN_DISPLAY_ERROR);
    CHECK(f.scheduler.display_failure==HW4_RUN_DISPLAY_PREFLIGHT_FAILED);
    CHECK(s.calls==0u && s.bytes==0u && s.pens==0u);
    CHECK(f.scheduler.stop_calls==0u);
    return 0;
}
int main(void) {
    CHECK(unbounded_loop_and_break()==0);
    CHECK(break_during_callback_and_poll()==0);
    CHECK(end_and_event_order()==0);
    CHECK(pen_error_context_and_atomicity()==0);
    CHECK(negative_arguments_and_limits()==0);
    CHECK(display_fail_stop()==0);
    CHECK(ink_rejects_whole_step()==0);
    puts("HW4-RUN-BREAK-A: 4160 real BSR steps + BREAK/END/errors PASS");
    return 0;
}
