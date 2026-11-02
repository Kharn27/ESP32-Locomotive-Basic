/* J1.21-C1: real portable BASIC, typed CLS direct preparation only.
 * No fake display, temporary program insertion, heap, or HW4 includes. */
#include "basic_session_runtime.h"
#include "basic_tokenizer.h"
#include <stdio.h>
#include <string.h>
#define CHECK(c) do { if(!(c)) { \
    fprintf(stderr,"J1.21-C1 %s:%d: %s\n",__FILE__,__LINE__,#c); \
    return 1; } } while(0)
enum { PROGRAM=2048, ENTRIES=16, ARENA=512, OUT=256, EV=3 };
typedef struct {
    BasicProgram program;
    BasicVariableStore store;
    BasicVariableEntry entries[ENTRIES];
    uint8_t arena[ARENA], image[PROGRAM], tmp[256], output[OUT];
    BasicSessionRuntime runtime;
    BEVideoEvent events[EV];
    size_t written, event_written;
} Fixture;
typedef struct {
    BasicProgram program;
    BasicVariableStore store;
    BasicVariableEntry entries[ENTRIES];
    uint8_t arena[ARENA], image[PROGRAM];
    BasicSessionRuntime runtime;
} Snapshot;
static Fixture f;
static Snapshot before;
static int reset(void) {
    memset(&f,0,sizeof(f));
    CHECK(bp_init(&f.program,f.image,sizeof(f.image))==BP_OK);
    CHECK(bvs_init_with_arena(&f.store,f.entries,ENTRIES,
                              f.arena,sizeof(f.arena))==BVS_OK);
    CHECK(bsr_init_with_store(&f.runtime,&f.program,&f.store).status==BSR_OK);
    return 0;
}
static BSRResult submit(const char *source) {
    return bsr_submit(&f.runtime,(const uint8_t *)source,strlen(source),
                      f.tmp,sizeof(f.tmp),f.output,sizeof(f.output),&f.written);
}
static void snapshot(void) {
    before.program=f.program;before.store=f.store;before.runtime=f.runtime;
    memcpy(before.entries,f.entries,sizeof(f.entries));
    memcpy(before.arena,f.arena,sizeof(f.arena));
    memcpy(before.image,f.image,sizeof(f.image));
}
static int unchanged(void) {
    CHECK(memcmp(&before.program,&f.program,sizeof(f.program))==0);
    CHECK(memcmp(&before.store,&f.store,sizeof(f.store))==0);
    CHECK(memcmp(&before.runtime,&f.runtime,sizeof(f.runtime))==0);
    CHECK(memcmp(before.entries,f.entries,sizeof(f.entries))==0);
    CHECK(memcmp(before.arena,f.arena,sizeof(f.arena))==0);
    CHECK(memcmp(before.image,f.image,sizeof(f.image))==0);
    return 0;
}
static BSRResult direct_raw(const uint8_t *src,size_t len,
                            uint8_t *out,size_t outcap,size_t *n,
                            BEVideoEvent *ev,size_t cap,size_t *ne) {
    return bsr_prepare_direct_events(&f.runtime,src,len,out,outcap,n,ev,cap,ne);
}
static BSRResult direct(const char *src,size_t outcap,size_t cap) {
    return direct_raw((const uint8_t *)src,strlen(src),
                     f.output,outcap,&f.written,f.events,cap,&f.event_written);
}
static int counters_and_canaries(size_t wanted_n,size_t wanted_ev) {
    size_t i,j;
    CHECK(f.written==wanted_n && f.event_written==wanted_ev);
    for(i=0;i<sizeof(f.output);++i) CHECK(f.output[i]==0xa5u);
    for(i=1;i<EV;++i) {
        const uint8_t *e=(const uint8_t *)&f.events[i];
        for(j=0;j<sizeof(f.events[i]);++j) CHECK(e[j]==0x5au);
    }
    return 0;
}
static void buffers(void) {
    memset(f.output,0xa5,sizeof(f.output));
    memset(f.events,0x5a,sizeof(f.events));
    f.written=999u;f.event_written=888u;
}
static int positive_exact(void) {
    static const char *const cases[]={"CLS","cls","cLs"," ClS","CLS ",
                                      "   cLs   "};
    uint8_t tokens[32],same[32];size_t n=17u,i,j;
    CHECK(reset()==0);
    CHECK(submit("10 REM KEEP").status==BSR_OK);
    CHECK(submit("20 END").status==BSR_OK);
    CHECK(bt_tokenize((const uint8_t *)"CLS",3u,tokens,sizeof(tokens),&n)==BT_OK);
    CHECK(n==1u && tokens[0]==0x8au); /* sealed B1 CPC byte, not emitted PRINT */
    for(i=0u;i<sizeof(cases)/sizeof(cases[0]);++i) {
        snapshot();buffers();
        CHECK(direct(cases[i],OUT,1u).status==BSR_OK);
        CHECK(unchanged()==0);
        CHECK(f.events[0].type==BE_VIDEO_CLEAR_TEXT);
        CHECK(f.events[0].print_offset==0u && f.events[0].pen==0u);
        CHECK(f.events[0].ink==0u && f.events[0].colour==0u);
        CHECK(counters_and_canaries(0u,1u)==0);
        memcpy(same,f.output,sizeof(same));
        CHECK(memcmp(same,f.output,sizeof(same))==0);
        /* repeated direct preparation has no retained state */
        buffers();
        CHECK(direct(cases[i],0u,EV).status==BSR_OK);
        CHECK(unchanged()==0 && counters_and_canaries(0u,1u)==0);
        for(j=1u;j<EV;++j) CHECK(f.events[j].type==(BEVideoEventType)0x5a5a5a5a);
    }
    /* LIST and NEW still run through the exact pre-existing public path. */
    CHECK(submit("LIST").status==BSR_OK);
    CHECK(f.written>0u && memcmp(f.output,"10 REM KEEP\n",12u)==0);
    CHECK(submit("NEW").status==BSR_OK);
    CHECK(submit("LIST").status==BSR_OK && f.written==0u);
    return 0;
}
static int reject(const char *src,BSRStatus expected,BSStatus session,BEStatus ex) {
    BSRResult r;
    snapshot();buffers();
    r=direct(src,OUT,EV);
    CHECK(r.status==expected);
    if(expected==BSR_SESSION_ERROR) CHECK(r.session.status==session);
    if(expected==BSR_EXECUTOR_ERROR) CHECK(r.executor_status==ex);
    CHECK(unchanged()==0 && counters_and_canaries(999u,888u)==0);
    {
        const uint8_t *event_bytes=(const uint8_t *)&f.events[0];
        size_t i;
        for(i=0;i<sizeof(f.events[0]);++i)
            CHECK(event_bytes[i]==0x5au);
    }
    return 0;
}
static int negative_lexical(void) {
    static const char *const unsupported[]={
       "CLSX","CLS1","CLS #1","CLS#0","CLS #8","CLS PRINT \"X\"",
       "PRINT \"X\"","PEN 2","RUN","LIST","NEW","!CLS","",
       "CLS\t"," CLS \t","10 CLS", "REM CLS", "CLS+"
    };
    static const char *const multiple[]={
       "CLS:CLS","CLS:PRINT \"X\""," CLS :CLS ","CLS:"
    };
    static const uint8_t malformed[][6]={
       {'C','L','S','\0',0,0},{'C','L','S','\r',0,0},
       {'C','L','S','\n',0,0}
    };
    size_t i;
    CHECK(reset()==0);
    CHECK(submit("10 PRINT \"OK\"").status==BSR_OK);
    for(i=0;i<sizeof(unsupported)/sizeof(unsupported[0]);++i)
        CHECK(reject(unsupported[i],BSR_SESSION_ERROR,
                     BS_UNSUPPORTED_DIRECT,BE_OK)==0);
    for(i=0;i<sizeof(multiple)/sizeof(multiple[0]);++i)
        CHECK(reject(multiple[i],BSR_SESSION_ERROR,
                     BS_MULTIPLE_DIRECT,BE_OK)==0);
    for(i=0;i<3u;++i) {
        BSRResult result;
        snapshot();buffers();
        result=direct_raw(malformed[i],4u,f.output,OUT,&f.written,
                          f.events,EV,&f.event_written);
        CHECK(result.status==BSR_SESSION_ERROR &&
              result.session.status==BS_MALFORMED_INPUT);
        CHECK(unchanged()==0 && counters_and_canaries(999u,888u)==0);
    }
    /* RED reference: historical submit still rejects CLS without event API.
     * GREEN: prepare-direct succeeds, with no execution or BASIC mutation. */
    CHECK(submit("CLS").status==BSR_SESSION_ERROR);
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(reject("CLS",BSR_BUSY,BS_OK,BE_OK)==0);
    CHECK(bsr_stop(&f.runtime).status==BSR_OK);
    return 0;
}
static int nonmutating_failure(BSRResult r,BSRStatus status) {
    CHECK(r.status==status);
    CHECK(unchanged()==0 && counters_and_canaries(999u,888u)==0);
    return 0;
}
static int invalid_more(void) {
    const uint8_t *src=(const uint8_t *)"CLS";
    CHECK(reset()==0);
    snapshot();buffers();
    CHECK(nonmutating_failure(direct_raw(src,3u,f.output,OUT,&f.written,
                     f.events,0u,&f.event_written),BSR_EXECUTOR_ERROR)==0);
    CHECK(nonmutating_failure(direct_raw(src,3u,NULL,OUT,&f.written,
                     f.events,EV,&f.event_written),BSR_INVALID_ARGUMENT)==0);
    CHECK(nonmutating_failure(direct_raw(NULL,3u,f.output,OUT,&f.written,
                     f.events,EV,&f.event_written),BSR_INVALID_ARGUMENT)==0);
    CHECK(nonmutating_failure(direct_raw(src,3u,f.output,OUT,NULL,
                     f.events,EV,&f.event_written),BSR_INVALID_ARGUMENT)==0);
    CHECK(nonmutating_failure(direct_raw(src,3u,f.output,OUT,&f.written,
                     NULL,EV,&f.event_written),BSR_INVALID_ARGUMENT)==0);
    CHECK(nonmutating_failure(direct_raw(src,3u,f.output,OUT,&f.written,
                     f.events,EV,NULL),BSR_INVALID_ARGUMENT)==0);
    CHECK(nonmutating_failure(direct_raw(src,3u,f.image,3u,&f.written,
                     f.events,EV,&f.event_written),BSR_OVERLAP)==0);
    CHECK(nonmutating_failure(direct_raw(f.image,3u,f.output,OUT,&f.written,
                     f.events,EV,&f.event_written),BSR_OVERLAP)==0);
    CHECK(nonmutating_failure(direct_raw(src,3u,f.output,OUT,&f.written,
                     f.events,EV,&f.written),BSR_OVERLAP)==0);
    CHECK(nonmutating_failure(direct_raw(src,3u,f.output,OUT,&f.written,
                     (BEVideoEvent *)(void *)&f.runtime,1u,
                     &f.event_written),BSR_OVERLAP)==0);
    CHECK(nonmutating_failure(direct_raw(src,3u,f.store.string_arena,5u,
                     &f.written,f.events,EV,&f.event_written),BSR_OVERLAP)==0);
    CHECK(nonmutating_failure(direct_raw(src,3u,f.output,OUT,&f.written,
                     f.events,SIZE_MAX,&f.event_written),
                     BSR_INVALID_ARGUMENT)==0);
    CHECK(f.events[0].type==(BEVideoEventType)0x5a5a5a5a);
    return 0;
}
static int stores_cursor_stacks_and_legacy(void) {
    size_t i;
    const char *lines[]={"10 A%=7","20 A$=\"BONJOUR\"","30 A=0","40 END"};
    CHECK(reset()==0);
    for(i=0;i<sizeof(lines)/sizeof(lines[0]);++i)
        CHECK(submit(lines[i]).status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    for(i=0;i<3u;++i) {
        BEVideoEvent ev[2];size_t n=22u,ne=33u;
        CHECK(bsr_step_events(&f.runtime,f.output,OUT,&n,ev,2u,&ne).status==BSR_OK);
    }
    CHECK(bsr_stop(&f.runtime).status==BSR_OK);
    /* Preserve cursor/offset/stack byte-for-byte; no call to be_init. */
    f.runtime.executor.cursor=23u;
    f.runtime.executor.statement_offset=7u;
    memset(f.runtime.executor.call_stack,0x41,sizeof(f.runtime.executor.call_stack));
    memset(f.runtime.executor.for_stack,0x61,sizeof(f.runtime.executor.for_stack));
    snapshot();buffers();
    CHECK(direct(" cLs ",OUT,1u).status==BSR_OK);
    CHECK(unchanged()==0 && counters_and_canaries(0u,1u)==0);
    CHECK(submit("LIST").status==BSR_OK && f.written>0u);
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(reject("CLS",BSR_BUSY,BS_OK,BE_OK)==0);
    return 0;
}
static int read_whole(const char *root,const char *session,
                      const char *file,uint8_t *out,size_t cap,size_t *n) {
    char path[600];FILE *fp;int extra;
    CHECK(snprintf(path,sizeof(path),
          "%s/tests/fixtures/cpc6128/j1_21_a_cls/%s/D_FULL/%s",
          root,session,file)>0);
    fp=fopen(path,"rb");CHECK(fp!=NULL);
    *n=fread(out,1u,cap,fp);
    extra=fgetc(fp);
    CHECK(!ferror(fp) && extra==EOF && fclose(fp)==0 && *n>0u);
    return 0;
}
static int cpc_direct_oracle(const char *root) {
    static uint8_t original[2048],repeat[2048];
    static uint8_t captured[12000];
    size_t n,m;
    CHECK(read_whole(root,"original","program.bin",original,
                     sizeof(original),&n)==0);
    CHECK(read_whole(root,"repeat","program.bin",repeat,
                     sizeof(repeat),&m)==0);
    CHECK(n==m && memcmp(original,repeat,n)==0);
    CHECK(read_whole(root,"original","capture.json",captured,
                     sizeof(captured)-1u,&n)==0);
    captured[n]=0u;
    CHECK(strstr((char *)captured,"\"case\": \"D_FULL\"")!=NULL);
    CHECK(strstr((char *)captured,"\"classification\": \"OBSERVED_IN_REAL_ACQUISITION\"")!=NULL);
    CHECK(strstr((char *)captured,"\"err\": 0")!=NULL);
    CHECK(strstr((char *)captured,"\"erl\": 0")!=NULL);
    CHECK(strstr((char *)captured,
      "\"list_before_sha256\": \"df09df2a50d02191d8d287511a08bf8ba50cc56de6acdfa0f1e2906e0a85b683\"")!=NULL);
    CHECK(strstr((char *)captured,
      "\"list_after_sha256\": \"df09df2a50d02191d8d287511a08bf8ba50cc56de6acdfa0f1e2906e0a85b683\"")!=NULL);
    puts("J1.21-C1 CPC D_FULL original/repeat independent captured ERR=0 ERL=0 LIST conserved");
    return 0;
}
int main(int argc,char **argv) {
    CHECK(argc==2);
    CHECK(positive_exact()==0);
    CHECK(negative_lexical()==0);
    CHECK(invalid_more()==0);
    CHECK(stores_cursor_stacks_and_legacy()==0);
    CHECK(cpc_direct_oracle(argv[1])==0);
    puts("J1.21-C1 DIRECT_CLS_8A PURE_PREPARE EVENTS=1 PRINT=0 ATOMIC PASS");
    return 0;
}
