/* J1.21-B2a: next-step preview is the SAME verified executor path with
 * final commit disabled. No video/HW4, no heap, no CPC oracle mutation. */
#include "basic_session_runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(c) do { if (!(c)) { \
    fprintf(stderr,"J1.21-B2a %s:%d: %s\n",__FILE__,__LINE__,#c);return 1;\
} } while (0)
enum { PROGRAM_CAP=2048, OUT_CAP=256, EVENT_CAP=8, ENTRIES=8, ARENA=256 };
typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    BasicVariableStore store;
    BasicVariableEntry entries[ENTRIES];
    uint8_t arena[ARENA];
    uint8_t program_bytes[PROGRAM_CAP], temp[256], output[OUT_CAP];
    size_t written;
} Fixture;
static Fixture f;
static int reset(void) {
    memset(&f,0x65,sizeof(f));
    CHECK(bp_init(&f.program,f.program_bytes,sizeof(f.program_bytes))==BP_OK);
    CHECK(bvs_init_with_arena(&f.store,f.entries,ENTRIES,f.arena,ARENA)==BVS_OK);
    CHECK(bsr_init_with_store(&f.runtime,&f.program,&f.store).status==BSR_OK);
    return 0;
}
static BSRResult submit(const char *line) {
    return bsr_submit(&f.runtime,(const uint8_t *)line,strlen(line),
          f.temp,sizeof(f.temp),f.output,sizeof(f.output),&f.written);
}
typedef struct {
    BasicSessionRuntime runtime;
    BasicVariableStore store;
    BasicVariableEntry entries[ENTRIES];
    BasicProgram program;
    uint8_t arena[ARENA],bytes[PROGRAM_CAP];
} Snapshot;
static void snapshot(Snapshot *s) {
    s->runtime=f.runtime;s->store=f.store;s->program=f.program;
    memcpy(s->entries,f.entries,sizeof(f.entries));
    memcpy(s->arena,f.arena,sizeof(f.arena));
    memcpy(s->bytes,f.program_bytes,sizeof(f.program_bytes));
}
static int unchanged(const Snapshot *s) {
    CHECK(memcmp(&s->runtime,&f.runtime,sizeof(f.runtime))==0);
    CHECK(memcmp(&s->store,&f.store,sizeof(f.store))==0);
    CHECK(memcmp(s->entries,f.entries,sizeof(f.entries))==0);
    CHECK(memcmp(s->arena,f.arena,sizeof(f.arena))==0);
    CHECK(memcmp(&s->program,&f.program,sizeof(f.program))==0);
    CHECK(memcmp(s->bytes,f.program_bytes,sizeof(f.program_bytes))==0);
    return 0;
}
/* Preview may write ONLY staging buffers and counts; check repeated preview,
 * byte-for-byte event+PRINT equality on immediate commit and canaries. */
static int equal_next(BSRStatus wanted, size_t output_cap,size_t event_cap,
                      size_t expected_events) {
    uint8_t staged[OUT_CAP], again[OUT_CAP], committed[OUT_CAP];
    BEVideoEvent events[EVENT_CAP], repeat[EVENT_CAP], committed_events[EVENT_CAP];
    size_t n=999u,ne=888u,n2=777u,ne2=666u,n3=555u,ne3=444u;
    BSRResult preview,preview2,commit;
    Snapshot before;
    size_t i;
    memset(staged,0xa5,sizeof(staged));memset(again,0xa5,sizeof(again));
    memset(committed,0xa5,sizeof(committed));
    memset(events,0xa5,sizeof(events));memset(repeat,0xa5,sizeof(repeat));
    memset(committed_events,0xa5,sizeof(committed_events));
    snapshot(&before);
    preview=bsr_preview_step_events(&f.runtime,staged,output_cap,&n,
                                    events,event_cap,&ne);
    CHECK(preview.status==wanted && unchanged(&before)==0);
    preview2=bsr_preview_step_events(&f.runtime,again,output_cap,&n2,
                                     repeat,event_cap,&ne2);
    CHECK(preview2.status==preview.status &&
          preview2.executor_status==preview.executor_status);
    CHECK(unchanged(&before)==0);
    CHECK(memcmp(staged,again,sizeof(staged))==0 &&
          memcmp(events,repeat,sizeof(events))==0);
    if(wanted==BSR_OK) {
        CHECK(n==n2 && ne==ne2 && ne==expected_events);
        for(i=n;i<sizeof(staged);++i) CHECK(staged[i]==0xa5u);
        for(i=ne;i<EVENT_CAP;++i) {
            const uint8_t *p=(const uint8_t *)&events[i];
            size_t j;
            for(j=0u;j<sizeof(events[i]);++j) CHECK(p[j]==0xa5u);
        }
    } else {
        CHECK(n==999u && ne==888u && n2==777u && ne2==666u);
        for(i=0;i<sizeof(staged);++i)CHECK(staged[i]==0xa5u);
    }
    /* Commit executed from unchanged exact state. END must leave staging
     * untouched on preview and only set runtime IDLE during commit. */
    commit=bsr_step_events(&f.runtime,committed,output_cap,&n3,
                           committed_events,event_cap,&ne3);
    CHECK(commit.status==wanted &&
          commit.executor_status==preview.executor_status);
    if(wanted==BSR_OK) {
        CHECK(n==n3 && ne==ne3);
        CHECK(memcmp(staged,committed,sizeof(staged))==0);
        CHECK(memcmp(events,committed_events,sizeof(events))==0);
    } else {
        CHECK(n3==555u && ne3==444u && unchanged(&before)==0);
    }
    return 0;
}
static int error_preview(BEStatus expected,size_t outcap,size_t eventcap,
                         int no_receiver) {
    Snapshot before;
    uint8_t data[OUT_CAP],original[OUT_CAP];
    BEVideoEvent events[EVENT_CAP],saved[EVENT_CAP];
    size_t n=123u,ne=456u;
    BSRResult r;
    memset(data,0x6d,sizeof(data));memset(events,0x72,sizeof(events));
    memcpy(original,data,sizeof(data));memcpy(saved,events,sizeof(events));
    snapshot(&before);
    r=bsr_preview_step_events(&f.runtime,data,outcap,&n,
          no_receiver?NULL:events,eventcap,&ne);
    CHECK(r.status==BSR_EXECUTOR_ERROR && r.executor_status==expected);
    CHECK(n==123u && ne==456u && unchanged(&before)==0);
    CHECK(memcmp(data,original,sizeof(data))==0 &&
          memcmp(events,saved,sizeof(events))==0);
    return 0;
}
static int cls_records(void) {
    uint8_t output[64],saved[64];size_t n=777u;
    BasicExecutor executor;BasicProgramLine record;
    Snapshot before;
    BEVideoEvent ev[2];size_t ne=999u;
    CHECK(reset()==0);
    CHECK(submit("10 CLS:CLS").status==BSR_OK);
    CHECK(bp_find(&f.program,10u,&record)==BP_OK);
    CHECK(record.body_length==3u &&
          memcmp(f.program.data+record.body_offset,
                 (const uint8_t[]){0x8a,0x01,0x8a},3u)==0);
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(error_preview(BE_EVENT_RECEIVER_REQUIRED,64u,0u,1)==0);
    CHECK(error_preview(BE_NO_EVENT_SPACE,64u,1u,0)==0);
    CHECK(equal_next(BSR_OK,64u,2u,2u)==0);
    CHECK(f.runtime.executor.statement_offset==0u);
    CHECK(reset()==0);
    CHECK(submit("10 CLS").status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    snapshot(&before); executor=f.runtime.executor;
    memset(output,0x76,sizeof(output));memcpy(saved,output,sizeof(saved));
    CHECK(be_step(&executor,output,sizeof(output),&n)==BE_EVENT_RECEIVER_REQUIRED);
    CHECK(memcmp(&executor,&before.runtime.executor,sizeof(executor))==0);
    CHECK(memcmp(output,saved,sizeof(output))==0 && n==777u);
    CHECK(bsr_preview_step_events(&f.runtime,output,sizeof(output),&n,
                                  ev,2u,&ne).status==BSR_OK);
    CHECK(n==0u && ne==1u && ev[0].type==BE_VIDEO_CLEAR_TEXT &&
          ev[0].print_offset==0u && ev[0].pen==0u &&
          ev[0].ink==0u && ev[0].colour==0u);
    CHECK(unchanged(&before)==0);
    CHECK(equal_next(BSR_OK,64u,2u,1u)==0);
    return 0;
}
static int print_and_colours(void) {
    uint8_t data[128];BEVideoEvent ev[8];size_t n=123,ne=456;
    Snapshot before;
    CHECK(reset()==0);
    CHECK(submit("10 PRINT \"A\":CLS:PRINT \"B\"").status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    snapshot(&before);
    CHECK(bsr_preview_step_events(&f.runtime,data,sizeof(data),&n,
                  ev,8u,&ne).status==BSR_OK);
    CHECK(n==4u && memcmp(data,"A\nB\n",4u)==0 && ne==1u);
    CHECK(ev[0].type==BE_VIDEO_CLEAR_TEXT && ev[0].print_offset==2u);
    CHECK(unchanged(&before)==0);
    CHECK(equal_next(BSR_OK,128u,8u,1u)==0);
    CHECK(reset()==0);
    CHECK(submit("10 PEN 2:PRINT \"A\":INK 1,26:CLS").status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    snapshot(&before);n=123;ne=456;
    CHECK(bsr_preview_step_events(&f.runtime,data,sizeof(data),&n,
                  ev,8u,&ne).status==BSR_OK);
    CHECK(n==2u && memcmp(data,"A\n",2u)==0 && ne==3u);
    CHECK(ev[0].type==BE_VIDEO_SET_TEXT_PEN && ev[0].print_offset==0u);
    CHECK(ev[1].type==BE_VIDEO_SET_INK && ev[1].print_offset==2u);
    CHECK(ev[2].type==BE_VIDEO_CLEAR_TEXT && ev[2].print_offset==2u);
    CHECK(unchanged(&before)==0);
    CHECK(equal_next(BSR_OK,128u,8u,3u)==0);
    return 0;
}
static int flow_and_stores(void) {
    size_t i;
    const struct {const char *lines[5];size_t count,steps;} cases[] = {
        {{"10 A%=1","20 PRINT A%","30 END"},3u,4u},
        {{"10 A=0","20 PRINT A","30 END"},3u,4u},
        {{"10 A=-1","20 PRINT A","30 END"},3u,4u},
        {{"10 A$=\"BONJOUR\"","20 PRINT A$","30 END"},3u,4u},
        {{"10 GOTO 30","20 PRINT \"NEVER\"","30 PRINT \"YES\"","40 END"},4u,4u},
        {{"10 GOSUB 30","20 END","30 PRINT \"SUB\"","40 RETURN"},4u,5u},
        {{"10 A%=1","20 IF A% THEN 40","30 PRINT \"NEVER\"","40 END"},4u,4u},
        {{"10 FOR I%=1 TO 2","20 PRINT I%","30 NEXT I%","40 END"},4u,8u}
    };
    for(i=0u;i<sizeof(cases)/sizeof(cases[0]);++i) {
        size_t j;
        CHECK(reset()==0);
        for(j=0u;j<cases[i].count;++j)
            CHECK(submit(cases[i].lines[j]).status==BSR_OK);
        CHECK(submit("RUN").status==BSR_OK);
        /* Stop once END has transitioned; no tests rely on future steps. */
        for(j=0u;j<cases[i].steps;++j)
            CHECK(equal_next(BSR_OK,OUT_CAP,EVENT_CAP,0u)==0);
        CHECK(equal_next(BSR_END,OUT_CAP,EVENT_CAP,0u)==0);
        CHECK(f.runtime.state==BSR_IDLE);
    }
    return 0;
}
static int negative_guards(void) {
    CHECK(reset()==0);
    CHECK(submit("10 PRINT \"LONG\"").status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(error_preview(BE_NO_SPACE,1u,EVENT_CAP,0)==0);
    CHECK(equal_next(BSR_OK,OUT_CAP,EVENT_CAP,0u)==0);
    CHECK(reset()==0);
    CHECK(submit("10 PEN 16").status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(error_preview(BE_INVALID_PEN,OUT_CAP,EVENT_CAP,0)==0);
    return 0;
}
int main(void) {
    CHECK(cls_records()==0);
    CHECK(print_and_colours()==0);
    CHECK(flow_and_stores()==0);
    CHECK(negative_guards()==0);
    puts("J1.21-B2a CORE_PREVIEW CLS_DOUBLE PRINT_PEN_INK INTEGER_STRING_REAL5 FLOW ATOMIC PASS");
    return 0;
}
