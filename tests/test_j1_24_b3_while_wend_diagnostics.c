/* J1.24-B3: real RUN/BSR -> central CPC mapping -> text -> Ready.
 * Historical ROM evidence is immutable; this C99 host test only reproduces
 * the already witnessed command syntax, never invents ERR/ERL semantics. */
#include "cpc_diag_policy.h"
#include "cpc_ready_policy.h"
#include "hw4_run_diag_source.h"
#include "basic_variable_store.h"
#include "cpc_video.h"
#include "cpc_text.h"
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if(!(x)) { \
    fprintf(stderr, "J1.24-B3 %s:%d %s\n", __FILE__,__LINE__,#x); \
    return 1; } } while(0)
enum { PROGRAM_CAP=4096, OUT_CAP=256 };
typedef struct {
    BasicProgram program;
    BasicVariableStore store;
    BasicSessionRuntime runtime;
    BasicVariableEntry entries[32];
    uint8_t program_bytes[PROGRAM_CAP], temporary[512], output[OUT_CAP];
    size_t written, events_written;
    BEVideoEvent events[3];
    CpcVideo video;
    CpcText text;
    uint8_t vram[CPC_VIDEO_BYTES];
} Fixture;
static Fixture f;
static char painted[256];
static size_t painted_size;

static uint8_t glyph(void *unused, uint8_t ch, unsigned row)
{
    (void)unused;
    if (row == 0U) {
        if (painted_size < sizeof painted)
            painted[painted_size++] = (char)ch;
    }
    return ch == ' ' ? 0U : 0x80U;
}
static int setup(void)
{
    memset(&f,0,sizeof f);
    painted_size=0U;
    CHECK(bp_init(&f.program,f.program_bytes,sizeof f.program_bytes)==BP_OK);
    CHECK(bvs_init(&f.store,f.entries,32U)==BVS_OK);
    CHECK(bsr_init_with_store(&f.runtime,&f.program,&f.store).status==BSR_OK);
    CHECK(cpc_video_init(&f.video,f.vram,sizeof f.vram,CPC_MODE_1));
    CHECK(cpc_text_init(&f.text,&f.video,glyph,NULL));
    return 0;
}
static BSRResult submit(const char *src)
{
    return bsr_submit(&f.runtime,(const uint8_t *)src,strlen(src),
        f.temporary,sizeof f.temporary,f.output,sizeof f.output,&f.written);
}
static BSRResult step(void)
{
    return bsr_step_events(&f.runtime,f.output,sizeof f.output,&f.written,
                           f.events,3U,&f.events_written);
}
static int write_print(void)
{
    if (f.written)
        CHECK(cpc_text_write(&f.text,f.output,f.written));
    return 0;
}
static int same_bytes(const void *a,const void *b,size_t n)
{
    return memcmp(a,b,n)==0;
}
/* Snapshot *before* the failed step. The policy must be read-only even
 * when it authenticates a real BSR error, including a future WEND locus. */
static int run_case(const char *const *lines,size_t line_count,
                    size_t prior_steps,BEStatus failure,
                    CpcDiagCategory category,uint16_t fault,
                    const char *expected,const char *previous_print)
{
    uint8_t storage[PROGRAM_CAP],out[OUT_CAP],ev[sizeof f.events];
    BasicSessionRuntime runtime_before;
    BasicVariableStore store_before;
    BasicVariableEntry entries[32];
    uint8_t vram[CPC_VIDEO_BYTES];
    size_t n_before,ev_before,received_before,i;
    size_t expected_size=strlen(expected);
    CpcStepDiagnostic diag;
    BSRResult result;
    bool ready=false;
    uint16_t locus=999U;
    CHECK(setup()==0);
    for (i=0U;i<line_count;++i)
        CHECK(submit(lines[i]).status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    for (i=0U;i<prior_steps;++i) {
        f.written=0U;
        f.events_written=0U;
        result=step();
        CHECK(result.status==BSR_OK && result.executor_status==BE_OK);
        CHECK(write_print()==0);
    }
    received_before=f.text.bytes_received;
    CHECK(received_before==strlen(previous_print));
    memcpy(storage,f.program_bytes,sizeof storage);
    memcpy(entries,f.entries,sizeof entries);
    memcpy(vram,f.vram,sizeof vram);
    store_before=f.store;
    runtime_before=f.runtime;
    memset(f.output,0x5b,sizeof f.output);
    memset(f.events,0x6d,sizeof f.events);
    memcpy(out,f.output,sizeof out);
    memcpy(ev,f.events,sizeof ev);
    f.written=177U;
    f.events_written=199U;
    n_before=f.written;
    ev_before=f.events_written;
    result=step();
    CHECK(result.status==BSR_EXECUTOR_ERROR && result.executor_status==failure);
    CHECK(same_bytes(&runtime_before,&f.runtime,sizeof runtime_before));
    CHECK(same_bytes(&store_before,&f.store,sizeof store_before));
    CHECK(same_bytes(entries,f.entries,sizeof entries));
    CHECK(same_bytes(storage,f.program_bytes,sizeof storage));
    CHECK(same_bytes(vram,f.vram,sizeof vram));
    CHECK(same_bytes(out,f.output,sizeof out));
    CHECK(same_bytes(ev,f.events,sizeof ev));
    CHECK(f.written==n_before && f.events_written==ev_before);
    diag=cpc_diag_policy_step(result,&f.runtime);
    CHECK(diag.category==category);
    CHECK(diag.line_number==fault);
    CHECK(diag.origin==(category==CPC_DIAG_HOST_GENERIC ?
        CPC_DIAG_ORIGIN_HOST : CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE));
    CHECK(strcmp(hw4_run_diag_source(diag.origin),
          category==CPC_DIAG_HOST_GENERIC ? "HOST" :
           "NATIVE_WHILE_WEND_CPC_ORACLE")==0);
    CHECK(be_while_diagnostic_line(&f.runtime.executor,failure,&locus)==BE_OK);
    CHECK(locus==fault || category==CPC_DIAG_HOST_GENERIC);
    CHECK(same_bytes(&runtime_before,&f.runtime,sizeof runtime_before));
    CHECK(same_bytes(&store_before,&f.store,sizeof store_before));
    CHECK(same_bytes(entries,f.entries,sizeof entries));
    CHECK(same_bytes(storage,f.program_bytes,sizeof storage));
    CHECK(same_bytes(vram,f.vram,sizeof vram));
    CHECK(same_bytes(out,f.output,sizeof out));
    CHECK(same_bytes(ev,f.events,sizeof ev));
    CHECK(f.written==n_before && f.events_written==ev_before);
    {
        uint8_t tiny[64];
        size_t count=333U;
        memset(tiny,0x7c,sizeof tiny);
        CHECK(!cpc_diag_policy_format_step(diag,tiny,expected_size-1U,&count));
        CHECK(count==333U);
        for(i=0U;i<sizeof tiny;++i) CHECK(tiny[i]==0x7c);
        CHECK(cpc_diag_policy_format_step(diag,tiny,sizeof tiny,&count));
        CHECK(count==expected_size && memcmp(tiny,expected,count)==0);
    }
    CHECK(bsr_stop(&f.runtime).status==BSR_OK);
    CHECK(f.runtime.state==BSR_IDLE);
    CHECK(cpc_diag_policy_write_step(&f.text,diag));
    CHECK(cpc_ready_policy_apply(&f.text,CPC_READY_RUN_RETURN,&ready));
    CHECK(ready && f.text.bytes_received==
          received_before+expected_size+strlen("Ready\n"));
    CHECK(painted_size < sizeof painted);
    painted[painted_size]='\0';
    CHECK(strstr(painted,"Ready")!=NULL);
    CHECK(strstr(strstr(painted,"Ready")+5U,"Ready")==NULL);
    CHECK(strstr(painted,"AFTER")==NULL);
    CHECK(strstr(painted,"NEVER")==NULL);
    CHECK(strstr(painted,"BEFORE") == (strlen(previous_print)?painted:NULL));
    CHECK(same_bytes(storage,f.program_bytes,sizeof storage));
    CHECK(same_bytes(entries,f.entries,sizeof entries));
    CHECK(f.store.capacity==store_before.capacity);
    CHECK(submit("LIST").status==BSR_OK);
    CHECK(f.written>0U);
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(submit("NEW").status==BSR_OK);
    CHECK(submit("LIST").status==BSR_OK && f.written==0U);
    return 0;
}
#define CASE(arr,steps,reason,category,line,msg,before) \
    CHECK(run_case(arr,sizeof(arr)/sizeof((arr)[0]),steps, \
                   reason,category,line,msg,before)==0)
static int witnessed_and_renumbered(void)
{
    static const char *const orphan[]={
        "10 WEND","20 PRINT \"AFTER\"","30 END"};
    static const char *const missing_wend[]={
        "10 WHILE 0","20 PRINT \"AFTER\"","30 END"};
    static const char *const operand10[]={
        "10 WHILE","20 PRINT \"AFTER\"","30 WEND","40 END"};
    static const char *const operand20[]={
        "10 A%=0","20 WHILE A%<","30 PRINT \"AFTER\"",
        "40 WEND","50 END"};
    static const char *const orphan620[]={
        "620 WEND","700 PRINT \"AFTER\"","800 END"};
    static const char *const missing900[]={
        "900 WHILE 0","910 PRINT \"AFTER\"","920 END"};
    static const char *const operand65000[]={
        "65000 WHILE","65010 WEND","65535 PRINT \"AFTER\""};
    static const char *const before[]={
        "10 PRINT \"BEFORE\"","20 WHILE","30 WEND",
        "40 PRINT \"AFTER\""};
    static const char *const colon[]={
        "10 WHILE 0:PRINT \"NEVER\"","20 PRINT \"AFTER\""};
    static const char *const quote[]={
        "10 PRINT \"WEND:WHILE\"","20 WEND","30 PRINT \"AFTER\""};
    CASE(orphan,0U,BE_WEND_WITHOUT_WHILE,CPC_DIAG_WEND_UNEXPECTED,
         10U,"Unexpected WEND in 10\n","");
    CASE(missing_wend,0U,BE_WHILE_WITHOUT_WEND,
         CPC_DIAG_WHILE_WEND_MISSING,10U,"WEND missing in 10\n","");
    CASE(operand10,0U,BE_WHILE_OPERAND_MISSING,
         CPC_DIAG_WHILE_OPERAND_MISSING,10U,"Operand missing in 10\n","");
    CASE(operand20,1U,BE_WHILE_OPERAND_MISSING,
         CPC_DIAG_WHILE_OPERAND_MISSING,20U,"Operand missing in 20\n","");
    CASE(orphan620,0U,BE_WEND_WITHOUT_WHILE,CPC_DIAG_WEND_UNEXPECTED,
         620U,"Unexpected WEND in 620\n","");
    CASE(missing900,0U,BE_WHILE_WITHOUT_WEND,
         CPC_DIAG_WHILE_WEND_MISSING,900U,"WEND missing in 900\n","");
    CASE(operand65000,0U,BE_WHILE_OPERAND_MISSING,
         CPC_DIAG_WHILE_OPERAND_MISSING,65000U,
         "Operand missing in 65000\n","");
    CASE(before,1U,BE_WHILE_OPERAND_MISSING,
         CPC_DIAG_WHILE_OPERAND_MISSING,20U,
         "Operand missing in 20\n","BEFORE\n");
    CASE(colon,0U,BE_WHILE_WITHOUT_WEND,
         CPC_DIAG_WHILE_WEND_MISSING,10U,"WEND missing in 10\n","");
    CASE(quote,1U,BE_WEND_WITHOUT_WHILE,
         CPC_DIAG_WEND_UNEXPECTED,20U,"Unexpected WEND in 20\n",
         "WEND:WHILE\n");
    puts("J1.24-B3: 4 sealed forms + renumbered/colon/PRINT host derivatives PASS");
    return 0;
}
static int no_fabricated_mapping(void)
{
    BSRResult r = {0};
    CpcStepDiagnostic diag;
    BasicSessionRuntime saved;
    BasicVariableEntry before[32];
    uint8_t bytes[PROGRAM_CAP];
    static const BEStatus prohibited[]={
        BE_DIAG_CONTRADICTORY, BE_WHILE_CONDITION_INVALID,
        BE_WHILE_STACK_FULL, BE_UNSUPPORTED, BE_NO_EVENT_SPACE,
        BE_EVENT_RECEIVER_REQUIRED, BE_BAD_SEQUENCE
    };
    size_t i;
    CHECK(setup()==0);
    CHECK(submit("10 PRINT \"WHILE:WEND\"").status==BSR_OK);
    CHECK(submit("20 END").status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    r.status=BSR_EXECUTOR_ERROR;
    for(i=0U;i<sizeof(prohibited)/sizeof(prohibited[0]);++i) {
        r.executor_status=prohibited[i];
        diag=cpc_diag_policy_step(r,&f.runtime);
        CHECK(diag.category==CPC_DIAG_HOST_GENERIC &&
              diag.origin==CPC_DIAG_ORIGIN_HOST && diag.line_number==0U);
    }
    /* Forged typed statuses on a genuine, successful PRINT fail closed. */
    {
        static const BEStatus forged[]={
            BE_WEND_WITHOUT_WHILE,BE_WHILE_WITHOUT_WEND,
            BE_WHILE_OPERAND_MISSING
        };
        for(i=0U;i<sizeof(forged)/sizeof(forged[0]);++i) {
            r.executor_status=forged[i];
            diag=cpc_diag_policy_step(r,&f.runtime);
            CHECK(diag.category==CPC_DIAG_HOST_GENERIC);
        }
    }
    saved=f.runtime;
    memcpy(before,f.entries,sizeof before);
    memcpy(bytes,f.program_bytes,sizeof bytes);
    CHECK(submit("WHILE").status!=BSR_OK); /* direct, un-oracled */
    CHECK(f.runtime.state==BSR_RUNNING);
    CHECK(same_bytes(&saved,&f.runtime,sizeof saved));
    CHECK(same_bytes(before,f.entries,sizeof before));
    CHECK(same_bytes(bytes,f.program_bytes,sizeof bytes));
    r.status=BSR_NOT_RUNNING;
    r.executor_status=BE_WEND_WITHOUT_WHILE;
    CHECK(cpc_diag_policy_step(r,&f.runtime).category==CPC_DIAG_HOST_GENERIC);
    r.status=BSR_EXECUTOR_ERROR;
    saved=f.runtime;
    f.runtime.state=BSR_IDLE;
    CHECK(cpc_diag_policy_step(r,&f.runtime).category==CPC_DIAG_HOST_GENERIC);
    f.runtime=saved;
    f.runtime.executor.statement_offset=1U; /* inside PRINT payload */
    CHECK(cpc_diag_policy_step(r,&f.runtime).category==CPC_DIAG_HOST_GENERIC);
    f.runtime=saved;
    f.runtime.executor.cursor=f.program.size; /* corrupt cursor */
    CHECK(cpc_diag_policy_step(r,&f.runtime).category==CPC_DIAG_HOST_GENERIC);
    f.runtime=saved;
    CHECK(submit("NEW").status==BSR_OK);
    CHECK(submit("10 WHILE 0").status==BSR_OK);
    CHECK(submit("20 WEND 1").status==BSR_OK);
    CHECK(submit("30 PRINT \"AFTER\"").status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    r=step();
    CHECK(r.status==BSR_EXECUTOR_ERROR &&
          r.executor_status==BE_DIAG_CONTRADICTORY);
    diag=cpc_diag_policy_step(r,&f.runtime);
    CHECK(diag.category==CPC_DIAG_HOST_GENERIC &&
          diag.origin==CPC_DIAG_ORIGIN_HOST && diag.line_number==0U);
    CHECK(bsr_stop(&f.runtime).status==BSR_OK);
    CHECK(submit("NEW").status==BSR_OK);
    CHECK(submit("10 WHILE 1").status==BSR_OK);
    CHECK(submit("20 WEND").status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    r=step();
    CHECK(r.status==BSR_EXECUTOR_ERROR &&
          r.executor_status==BE_WHILE_CONDITION_INVALID);
    CHECK(cpc_diag_policy_step(r,&f.runtime).category==CPC_DIAG_HOST_GENERIC);
    puts("J1.24-B3: forged status/locus, invalid states, WEND 1 contradictions stay HOST");
    return 0;
}
static int formatter_guards(void)
{
    static const CpcDiagCategory cats[]={
        CPC_DIAG_WEND_UNEXPECTED,CPC_DIAG_WHILE_WEND_MISSING,
        CPC_DIAG_WHILE_OPERAND_MISSING};
    static const char *const expected[]={
        "Unexpected WEND in 65535\n",
        "WEND missing in 65535\n",
        "Operand missing in 65535\n"};
    size_t i,j;
    uint8_t buf[96],original[96];
    for(i=0U;i<3U;++i) {
        CpcStepDiagnostic d={
            cats[i],CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE,65535U};
        size_t n=123U;
        memset(buf,0x43,sizeof buf);
        memcpy(original,buf,sizeof buf);
        CHECK(cpc_diag_policy_format_step(d,buf,sizeof buf,&n));
        CHECK(n==strlen(expected[i]) && memcmp(buf,expected[i],n)==0);
        d.origin=CPC_DIAG_ORIGIN_HOST;
        n=123U;
        memcpy(buf,original,sizeof buf);
        CHECK(!cpc_diag_policy_format_step(d,buf,sizeof buf,&n));
        CHECK(n==123U && same_bytes(buf,original,sizeof buf));
        d.origin=CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE;
        d.line_number=0U;
        CHECK(!cpc_diag_policy_format_step(d,buf,sizeof buf,&n));
        CHECK(n==123U && same_bytes(buf,original,sizeof buf));
        d.line_number=65535U;
        for(j=0U;j<strlen(expected[i]);++j) {
            n=123U;
            CHECK(!cpc_diag_policy_format_step(d,buf,j,&n));
            CHECK(n==123U && same_bytes(buf,original,sizeof buf));
        }
        d.category=CPC_DIAG_COUNT;
        CHECK(!cpc_diag_policy_format_step(d,buf,sizeof buf,&n));
    }
    CHECK(strcmp(cpc_diag_policy_category(CPC_DIAG_WEND_UNEXPECTED),
                 "WEND_UNEXPECTED_CPC")==0);
    CHECK(strcmp(cpc_diag_policy_message(CPC_DIAG_WHILE_OPERAND_MISSING),
                 "Operand missing")==0);
    CHECK(strcmp(hw4_run_diag_source((CpcDiagOrigin)999),"HOST")==0);
    return 0;
}
int main(void)
{
    CHECK(witnessed_and_renumbered()==0);
    CHECK(no_fabricated_mapping()==0);
    CHECK(formatter_guards()==0);
    puts("J1.24-B3 true BSR + fail-closed CPC provenance + Ready PASS");
    return 0;
}
