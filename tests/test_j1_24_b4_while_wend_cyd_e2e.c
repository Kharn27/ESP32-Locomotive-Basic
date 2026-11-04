/* J1.24-B4 — C99 BSR -> CPC MODE 1 text -> Ready E2E.
 * Sources are a test-only transcription of J1.24-A CASES. Each program is
 * checked against sealed CPC program.bin after the ONLY permitted projection:
 * PRINT #8, -> PRINT. Captured printer text is an independent comparison.
 * No source fixture, firmware, CORE, or production dialect is changed. */
#include "basic_program.h"
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include "cpc_diag_policy.h"
#include "cpc_ready_policy.h"
#include "cpc_text.h"
#include "cpc_video.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(cond) do { if (!(cond)) { \
    fprintf(stderr, "J1.24-B4 FAIL %s/%s %s:%d: %s\n", \
            current_case, current_session, __FILE__, __LINE__, #cond); \
    return 1; \
} } while (0)

enum { PROGRAM_CAP=4096, FILE_CAP=8192, LINE_CAP=512,
       OUTPUT_CAP=1024, MAX_STEPS=512, MAX_LINES=12 };
typedef struct {
    const char *name;
    const char *semantic; /* expected ordered PRINT lines, trimmed, | separated */
    const char *lines[MAX_LINES];
} Positive;
#define POS(id, out, ...) { #id, out, { __VA_ARGS__ } }
static const Positive positives[] = {
    POS(ZERO_LITERAL,"ZERO",
        "10 WHILE 0","20 PRINT #8,\"BAD\"","30 WEND",
        "40 PRINT #8,\"ZERO\"","50 END"),
    POS(FALSE_REL,"FALSE",
        "10 A%=0","20 WHILE A%<0","30 PRINT #8,\"BAD\"",
        "40 A%=A%+1","50 WEND","60 PRINT #8,\"FALSE\"","70 END"),
    POS(ONCE_LT,"T|END",
        "10 A%=0","20 WHILE A%<1","30 PRINT #8,\"T\"",
        "40 A%=A%+1","50 WEND","60 PRINT #8,\"END\"","70 END"),
    POS(THREE_LT,"T|T|T|END",
        "10 A%=0","20 WHILE A%<3","30 PRINT #8,\"T\"",
        "40 A%=A%+1","50 WEND","60 PRINT #8,\"END\"","70 END"),
    POS(GT_DECREMENT,"3|2|1|END",
        "10 A%=3","20 WHILE A%>0","30 PRINT #8,A%",
        "40 A%=A%-1","50 WEND","60 PRINT #8,\"END\"","70 END"),
    POS(LE_BOUNDARY,"0|1|2|END",
        "10 A%=0","20 WHILE A%<=2","30 PRINT #8,A%",
        "40 A%=A%+1","50 WEND","60 PRINT #8,\"END\"","70 END"),
    POS(NE_EXIT,"0|1|END",
        "10 A%=0","20 WHILE A%<>2","30 PRINT #8,A%",
        "40 A%=A%+1","50 WEND","60 PRINT #8,\"END\"","70 END"),
    POS(EQ_FALSE,"END",
        "10 A%=1","20 WHILE A%=0","30 PRINT #8,\"BAD\"",
        "40 A%=A%+1","50 WEND","60 PRINT #8,\"END\"","70 END"),
    POS(EQ_ONCE,"T|END",
        "10 A%=1","20 WHILE A%=1","30 PRINT #8,\"T\"",
        "40 A%=2","50 WEND","60 PRINT #8,\"END\"","70 END"),
    POS(GE_DECREMENT,"2|1|0|END",
        "10 A%=2","20 WHILE A%>=0","30 PRINT #8,A%",
        "40 A%=A%-1","50 WEND","60 PRINT #8,\"END\"","70 END"),
    POS(NEST_2X2,"I|I|I|I|END",
        "10 A%=0","20 WHILE A%<2","30 B%=0","40 WHILE B%<2",
        "50 PRINT #8,\"I\"","60 B%=B%+1","70 WEND",
        "80 A%=A%+1","90 WEND","100 PRINT #8,\"END\"","110 END"),
    POS(NEST_SKIP_INNER,"OUTER|OUTER|END",
        "10 A%=0","20 WHILE A%<2","30 B%=0","40 WHILE B%<0",
        "50 PRINT #8,\"BAD\"","60 B%=B%+1","70 WEND",
        "80 PRINT #8,\"OUTER\"","90 A%=A%+1","100 WEND",
        "110 PRINT #8,\"END\"","120 END"),
    POS(COLON_SAME_LINE,"C|C|END",
        "10 A%=0:WHILE A%<2:PRINT #8,\"C\":A%=A%+1:WEND",
        "20 PRINT #8,\"END\"","30 END"),
    POS(COLON_CROSS_LINE,"C|C|END",
        "10 A%=0","20 WHILE A%<2:PRINT #8,\"C\"",
        "30 A%=A%+1:WEND","40 PRINT #8,\"END\"","50 END"),
    POS(EMPTY_BODY,"END",
        "10 A%=0","20 WHILE A%<0","30 WEND",
        "40 PRINT #8,\"END\"","50 END")
};
#undef POS

static const char *current_case="setup", *current_session="host";
typedef struct {
    BasicProgram program;
    BasicVariableStore store;
    BasicSessionRuntime runtime;
    BasicVariableEntry entries[32];
    uint8_t program_bytes[PROGRAM_CAP], temporary[LINE_CAP];
    uint8_t output[OUTPUT_CAP];
    BEVideoEvent events[3];
    size_t written, event_written;
    CpcVideo video;
    CpcText text;
    uint8_t vram[CPC_VIDEO_BYTES];
    char drawn[OUTPUT_CAP];
    size_t drawn_len;
} Fixture;
static Fixture f;

static uint8_t glyph(void *unused, uint8_t ch, unsigned row)
{
    (void)unused;
    if (row==0U && f.drawn_len<sizeof(f.drawn))
        f.drawn[f.drawn_len++]=(char)ch;
    return ch==' ' ? 0U : 0x80U;
}
static int setup(void)
{
    memset(&f,0,sizeof f);
    CHECK(bp_init(&f.program,f.program_bytes,sizeof f.program_bytes)==BP_OK);
    CHECK(bvs_init(&f.store,f.entries,32U)==BVS_OK);
    CHECK(bsr_init_with_store(&f.runtime,&f.program,&f.store).status==BSR_OK);
    CHECK(cpc_video_init(&f.video,f.vram,sizeof f.vram,CPC_MODE_1));
    CHECK(cpc_text_init(&f.text,&f.video,glyph,NULL));
    return 0;
}
static BSRResult submit(const char *s)
{
    f.written=0U;
    return bsr_submit(&f.runtime,(const uint8_t*)s,strlen(s),
                      f.temporary,sizeof f.temporary,
                      f.output,sizeof f.output,&f.written);
}
static BSRResult step(void)
{
    f.written=0U;
    f.event_written=0U;
    return bsr_step_events(&f.runtime,f.output,sizeof f.output,&f.written,
                           f.events,3U,&f.event_written);
}
/* Only a literal "PRINT #8," selector is changed. NEVER the CPC sources. */
static int adapt(const char *src, char *dest, size_t cap, unsigned *changes)
{
    const char *needle="PRINT #8,", *p=src;
    size_t n=0U;
    *changes=0U;
    while (*p) {
        if (strncmp(p,needle,strlen(needle))==0) {
            const char replacement[]="PRINT ";
            if (cap-n<=sizeof replacement-1U) return 1;
            memcpy(dest+n,replacement,sizeof replacement-1U);
            n+=sizeof replacement-1U;
            p+=strlen(needle);
            ++*changes;
        } else {
            if (cap-n<=1U) return 1;
            dest[n++]=*p++;
        }
    }
    if (n>=cap) return 1;
    dest[n]=0;
    return 0;
}
/* Mirrors B2's token-level selector projection, never updates program.bin. */
static int project_body(const uint8_t *src, size_t len,
                        uint8_t *dst, size_t cap, size_t *size)
{
    size_t i=0U,k=0U;
    while (i<len) {
        if (i+4U<len && src[i]==0xbfU && src[i+1U]==' ' &&
            src[i+2U]=='#' && src[i+3U]==0x16U && src[i+4U]==',') {
            if (cap-k<2U) return 1;
            dst[k++]=0xbfU;
            dst[k++]=' ';
            i+=5U;
        } else {
            if (k==cap) return 1;
            dst[k++]=src[i++];
        }
    }
    *size=k;
    return 0;
}
static int read_fixture(const char *root,const char *session,const char *id,
                        const char *suffix,uint8_t *out,size_t cap,size_t *len)
{
    char path[512];
    FILE *fp;
    int n=snprintf(path,sizeof path,
        "%s/tests/fixtures/cpc6128/j1_24_a_while_wend/%s/%s/%s",
        root,session,id,suffix);
    if (n<0 || (size_t)n>=sizeof path) return 1;
    fp=fopen(path,"rb");
    if (!fp) { fprintf(stderr,"J1.24-B4 missing %s\n",path); return 1; }
    *len=fread(out,1U,cap,fp);
    if (*len==0U || fgetc(fp)!=EOF || ferror(fp) || fclose(fp)!=0) return 1;
    return 0;
}
static int verify_source_against_cpc(const char *root,const char *session,
                                     const Positive *item)
{
    uint8_t image[FILE_CAP],raw_bytes[PROGRAM_CAP],projected_bytes[PROGRAM_CAP];
    uint8_t body[LINE_CAP];
    size_t size=0U,at=0U,n=0U;
    BasicProgram raw,projected;
    BasicProgramLine line;
    BPStatus st;
    CHECK(read_fixture(root,session,item->name,"program.bin",
                       image,sizeof image,&size)==0);
    CHECK(bp_init(&raw,raw_bytes,sizeof raw_bytes)==BP_OK);
    CHECK(bp_import(&raw,image,size)==BP_OK);
    CHECK(bp_init(&projected,projected_bytes,sizeof projected_bytes)==BP_OK);
    while ((st=bp_next(&raw,&at,&line))==BP_OK) {
        CHECK(project_body(raw.data+line.body_offset,line.body_length,
                           body,sizeof body,&n)==0);
        CHECK(bp_put(&projected,line.number,body,n)==BP_OK);
    }
    CHECK(st==BP_END);
    CHECK(projected.size==f.program.size);
    CHECK(memcmp(projected.data,f.program.data,projected.size)==0);
    return 0;
}
static int oracle_prints(const char *root,const char *session,
                         const char *id,uint8_t *out,size_t cap,size_t *used)
{
    uint8_t src[FILE_CAP];
    size_t size=0U,i,k=0U,limit;
    static const char marker[]="J124_DIAG_BEGIN\r\n";
    CHECK(read_fixture(root,session,id,"run/printer.dat",
                       src,sizeof src,&size)==0);
    limit=size;
    for (i=0U;i+sizeof marker-1U<=size;++i)
        if (memcmp(src+i,marker,sizeof marker-1U)==0) {limit=i;break;}
    CHECK(limit<size);
    for (i=0U;i<limit;++i) {
        CHECK(k<cap);
        if (src[i]=='\r' && i+1U<limit && src[i+1U]=='\n') ++i;
        out[k++]=src[i];
    }
    *used=k;
    return 0;
}
static int semantic_lines(const uint8_t *output,size_t n,const char *expected)
{
    size_t i=0U,j=0U;
    while (i<n) {
        size_t begin=i,end,need=0U;
        while (i<n && output[i]!='\n') ++i;
        if (i==n) return 1;
        end=i++;
        while (begin<end && output[begin]==' ') ++begin;
        while (end>begin && output[end-1U]==' ') --end;
        while (expected[j+need] && expected[j+need]!='|') ++need;
        if (end-begin!=need || memcmp(output+begin,expected+j,need)!=0)
            return 1;
        j+=need;
        if (expected[j]=='|') ++j;
        else if (i<n) return 1;
    }
    return expected[j]=='\0' ? 0 : 1;
}
static int submit_sources(const Positive *item)
{
    size_t i;
    unsigned count=0U;
    for (i=0U;i<MAX_LINES && item->lines[i]!=NULL;++i) {
        char projected[LINE_CAP];
        unsigned changed=0U;
        CHECK(adapt(item->lines[i],projected,sizeof projected,&changed)==0);
        CHECK(submit(projected).status==BSR_OK);
        CHECK(f.written==0U);
        count+=changed;
    }
    CHECK(i>=3U && count>0U && f.program.size>0U);
    return 0;
}
static int run_positive(const char *root,const char *session,
                        const Positive *item)
{
    uint8_t actual[OUTPUT_CAP],expected[OUTPUT_CAP],vram_before[CPC_VIDEO_BYTES];
    size_t total=0U,wanted=0U,i,drawn=0U,steps=0U;
    bool ready=false,ended=false;
    BSRResult r;
    current_case=item->name;
    current_session=session;
    CHECK(setup()==0);
    CHECK(submit_sources(item)==0);
    CHECK(verify_source_against_cpc(root,session,item)==0);
    CHECK(oracle_prints(root,session,item->name,expected,
                        sizeof expected,&wanted)==0);
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(f.runtime.state==BSR_RUNNING && f.text.bytes_received==0U);
    memcpy(vram_before,f.vram,sizeof vram_before);
    for (i=0U;i<MAX_STEPS;++i) {
        r=step();
        if (r.status==BSR_END) { ended=true;break; }
        CHECK(r.status==BSR_OK && r.executor_status==BE_OK);
        CHECK(f.event_written==0U);
        CHECK(total+f.written<=sizeof actual);
        memcpy(actual+total,f.output,f.written);
        total+=f.written;
        if (f.written) CHECK(cpc_text_write(&f.text,f.output,f.written));
        ++steps;
        /* "Ready" belongs to RUN terminal transition, not each step. */
        CHECK(f.text.bytes_received==total);
    }
    CHECK(ended && i<MAX_STEPS);
    CHECK(f.runtime.state==BSR_IDLE && f.runtime.executor.while_depth==0U);
    CHECK(total==wanted && memcmp(actual,expected,total)==0);
    CHECK(semantic_lines(actual,total,item->semantic)==0);
    CHECK(f.text.bytes_received==total);
    CHECK(cpc_ready_policy_apply(&f.text,CPC_READY_RUN_RETURN,&ready));
    CHECK(ready && f.text.bytes_received==total+strlen("Ready\n"));
    for (i=0U;i<total;++i)
        if (actual[i]>=0x20U && actual[i]<=0x7eU) ++drawn;
    CHECK(f.drawn_len==drawn+5U);
    CHECK(memcmp(f.drawn+drawn,"Ready",5U)==0);
    CHECK(memcmp(f.vram,vram_before,sizeof vram_before)!=0);
    CHECK(f.text.glyphs_drawn==drawn+5U);
    CHECK(submit("LIST").status==BSR_OK && f.written>0U);
    CHECK(submit("NEW").status==BSR_OK && f.program.size==0U);
    CHECK(submit("LIST").status==BSR_OK && f.written==0U);
    printf("J1.24-B4 %s/%s E2E_MATCH_SEMANTIC steps=%zu print=%zu Ready=1 VRAM=YES\n",
           session,item->name,steps,total);
    return 0;
}
/* After NEW reinsert original CPC text through BSR, not direct bp_put. */
static int lifecycle(void)
{
    static const char *const lines[]={
        "10 A%=0","20 WHILE A%<3","30 PRINT \"T\"",
        "40 A%=A%+1","50 WEND","60 PRINT \"END\"","70 END"};
    uint8_t aggregate[64];
    size_t total=0U,i;
    bool ended=false,ready=false;
    BSRResult r;
    current_case="LIFECYCLE";
    current_session="reinsertion";
    CHECK(setup()==0);
    for(i=0U;i<sizeof lines/sizeof lines[0];++i)
        CHECK(submit(lines[i]).status==BSR_OK);
    CHECK(submit("LIST").status==BSR_OK && f.written>0U);
    CHECK(submit("NEW").status==BSR_OK);
    CHECK(submit("LIST").status==BSR_OK && f.written==0U);
    for(i=0U;i<sizeof lines/sizeof lines[0];++i)
        CHECK(submit(lines[i]).status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    for(i=0U;i<MAX_STEPS;++i) {
        r=step();
        if(r.status==BSR_END) {ended=true;break;}
        CHECK(r.status==BSR_OK && r.executor_status==BE_OK);
        CHECK(total+f.written<=sizeof aggregate);
        memcpy(aggregate+total,f.output,f.written);
        total+=f.written;
        if (f.written) CHECK(cpc_text_write(&f.text,f.output,f.written));
    }
    CHECK(ended && semantic_lines(aggregate,total,"T|T|T|END")==0);
    CHECK(cpc_ready_policy_apply(&f.text,CPC_READY_RUN_RETURN,&ready) && ready);
    CHECK(f.runtime.executor.while_depth==0U);
    puts("J1.24-B4 LIST/NEW/empty LIST/reinsert/RUN/Ready PASS");
    return 0;
}
/* A failing step, whether preview or commit, cannot partially mutate
 * runtime, store, program, video, buffers, or count arguments. */
static int failure_step(BEStatus cause)
{
    BasicSessionRuntime prior=f.runtime;
    BasicVariableStore store=f.store;
    BasicVariableEntry entries[32];
    uint8_t program[PROGRAM_CAP],vram[CPC_VIDEO_BYTES],out[OUTPUT_CAP];
    BEVideoEvent events[3];
    size_t n=177U,ev=199U;
    BSRResult r;
    memcpy(entries,f.entries,sizeof entries);
    memcpy(program,f.program_bytes,sizeof program);
    memcpy(vram,f.vram,sizeof vram);
    memset(f.output,0x5b,sizeof f.output);
    memset(f.events,0x6d,sizeof f.events);
    memcpy(out,f.output,sizeof out);
    memcpy(events,f.events,sizeof events);
    r=bsr_preview_step_events(&f.runtime,f.output,sizeof f.output,&n,
                               f.events,3U,&ev);
    CHECK(r.status==BSR_EXECUTOR_ERROR && r.executor_status==cause);
    CHECK(n==177U && ev==199U);
    CHECK(memcmp(out,f.output,sizeof out)==0);
    CHECK(memcmp(events,f.events,sizeof events)==0);
    CHECK(memcmp(&prior,&f.runtime,sizeof prior)==0);
    CHECK(memcmp(&store,&f.store,sizeof store)==0);
    CHECK(memcmp(entries,f.entries,sizeof entries)==0);
    CHECK(memcmp(program,f.program_bytes,sizeof program)==0);
    r=bsr_step_events(&f.runtime,f.output,sizeof f.output,&n,
                       f.events,3U,&ev);
    CHECK(r.status==BSR_EXECUTOR_ERROR && r.executor_status==cause);
    CHECK(n==177U && ev==199U);
    CHECK(memcmp(out,f.output,sizeof out)==0);
    CHECK(memcmp(events,f.events,sizeof events)==0);
    CHECK(memcmp(&prior,&f.runtime,sizeof prior)==0);
    CHECK(memcmp(&store,&f.store,sizeof store)==0);
    CHECK(memcmp(entries,f.entries,sizeof entries)==0);
    CHECK(memcmp(program,f.program_bytes,sizeof program)==0);
    CHECK(memcmp(vram,f.vram,sizeof vram)==0);
    CHECK(f.text.bytes_received==0U ||
          f.text.bytes_received==strlen("BEFORE\n"));
    /* Simple step must fail identically as well, B2's three-API contract. */
    r=bsr_step(&f.runtime,f.output,sizeof f.output,&n);
    CHECK(r.status==BSR_EXECUTOR_ERROR && r.executor_status==cause);
    CHECK(n==177U && memcmp(out,f.output,sizeof out)==0);
    CHECK(memcmp(&prior,&f.runtime,sizeof prior)==0);
    CHECK(memcmp(entries,f.entries,sizeof entries)==0);
    return 0;
}
static int negative(const char *label,const char *const *lines,size_t count,
                    unsigned pre_steps,BEStatus cause,
                    CpcDiagCategory category,CpcDiagOrigin origin,
                    const char *shown)
{
    size_t i,received;
    BSRResult r;
    CpcStepDiagnostic diag;
    bool ready=false;
    current_case=label;
    current_session="negative";
    CHECK(setup()==0);
    for(i=0U;i<count;++i) CHECK(submit(lines[i]).status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    for(i=0U;i<pre_steps;++i) {
        r=step();
        CHECK(r.status==BSR_OK && r.executor_status==BE_OK);
        if (f.written) CHECK(cpc_text_write(&f.text,f.output,f.written));
    }
    received=f.text.bytes_received;
    CHECK(failure_step(cause)==0);
    r=bsr_preview_step_events(&f.runtime,f.output,sizeof f.output,
                              &f.written,f.events,3U,&f.event_written);
    CHECK(r.status==BSR_EXECUTOR_ERROR && r.executor_status==cause);
    r=bsr_step_events(&f.runtime,f.output,sizeof f.output,
                      &f.written,f.events,3U,&f.event_written);
    CHECK(r.status==BSR_EXECUTOR_ERROR && r.executor_status==cause);
    diag=cpc_diag_policy_step(r,&f.runtime);
    CHECK(diag.category==category && diag.origin==origin);
    CHECK(bsr_stop(&f.runtime).status==BSR_OK);
    CHECK(cpc_diag_policy_write_step(&f.text,diag));
    CHECK(cpc_ready_policy_apply(&f.text,CPC_READY_RUN_RETURN,&ready) && ready);
    CHECK(f.text.bytes_received==received+strlen(shown)+strlen("Ready\n"));
    CHECK(f.drawn_len<sizeof f.drawn);
    f.drawn[f.drawn_len]='\0';
    CHECK(strstr(f.drawn,"AFTER")==NULL);
    CHECK(strstr(f.drawn,"Ready")!=NULL);
    CHECK(strstr(strstr(f.drawn,"Ready")+5U,"Ready")==NULL);
    CHECK(submit("LIST").status==BSR_OK && f.written>0U);
    CHECK(submit("NEW").status==BSR_OK);
    CHECK(submit("LIST").status==BSR_OK && f.written==0U);
    printf("J1.24-B4 %s atomicity/HOST-or-CPC/Ready PASS\n",label);
    return 0;
}
static int negatives(void)
{
    static const char *const orphan[]={
        "10 WEND","20 PRINT \"AFTER\"","30 END"};
    static const char *const unclosed[]={
        "10 WHILE 0","20 PRINT \"AFTER\"","30 END"};
    static const char *const operand[]={
        "10 WHILE 0","20 WEND 1","30 PRINT \"AFTER\"","40 END"};
    static const char *const before[]={
        "10 PRINT \"BEFORE\"","20 WHILE","30 WEND",
        "40 PRINT \"AFTER\"","50 END"};
    static const char *const colon[]={
        "10 A%=0:B%=1:WHILE 0","20 WEND",
        "30 PRINT \"AFTER\"","40 END"};
    CHECK(negative("WEND_ORPHAN",orphan,3U,0U,BE_WEND_WITHOUT_WHILE,
                   CPC_DIAG_WEND_UNEXPECTED,
                   CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE,
                   "Unexpected WEND in 10\n")==0);
    CHECK(negative("WHILE_UNCLOSED",unclosed,3U,0U,BE_WHILE_WITHOUT_WEND,
                   CPC_DIAG_WHILE_WEND_MISSING,
                   CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE,
                   "WEND missing in 10\n")==0);
    CHECK(negative("WEND_OPERAND",operand,4U,0U,BE_DIAG_CONTRADICTORY,
                   CPC_DIAG_HOST_GENERIC,CPC_DIAG_ORIGIN_HOST,
                   "ERROR\n")==0);
    CHECK(negative("PRINT_THEN_FAIL",before,5U,1U,BE_WHILE_OPERAND_MISSING,
                   CPC_DIAG_WHILE_OPERAND_MISSING,
                   CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE,
                   "Operand missing in 20\n")==0);
    CHECK(negative("COLON_UNMEASURED",colon,4U,0U,BE_UNSUPPORTED,
                   CPC_DIAG_HOST_GENERIC,CPC_DIAG_ORIGIN_HOST,
                   "ERROR\n")==0);
    return 0;
}
static int no_space(void)
{
    static const char *const lines[]={
        "10 A%=0","20 WHILE A%<1","30 PRINT \"T\"",
        "40 A%=1","50 WEND","60 END"};
    BasicSessionRuntime before;
    BasicVariableEntry entries[32];
    uint8_t data[PROGRAM_CAP],buffer[OUTPUT_CAP];
    size_t n=47U,events=53U,i;
    BSRResult r;
    current_case="CAPACITY";
    current_session="negative";
    CHECK(setup()==0);
    for(i=0U;i<6U;++i) CHECK(submit(lines[i]).status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(step().status==BSR_OK); /* A%=0 */
    CHECK(step().status==BSR_OK); /* WHILE true */
    before=f.runtime;
    memcpy(entries,f.entries,sizeof entries);
    memcpy(data,f.program_bytes,sizeof data);
    memset(f.output,0x33,sizeof f.output);
    memcpy(buffer,f.output,sizeof buffer);
    r=bsr_step_events(&f.runtime,f.output,1U,&n,f.events,3U,&events);
    CHECK(r.status==BSR_EXECUTOR_ERROR && r.executor_status==BE_NO_SPACE);
    CHECK(n==47U && events==53U && memcmp(f.output,buffer,sizeof buffer)==0);
    CHECK(memcmp(&before,&f.runtime,sizeof before)==0);
    CHECK(memcmp(entries,f.entries,sizeof entries)==0);
    CHECK(memcmp(data,f.program_bytes,sizeof data)==0);
    r=step();
    CHECK(r.status==BSR_OK && f.written==2U);
    CHECK(memcmp(f.output,"T\n",2U)==0);
    puts("J1.24-B4 bounded output capacity atomic and retry PASS");
    return 0;
}
int main(int argc,char **argv)
{
    static const char *const sessions[]={"original","repeat"};
    size_t i,j;
    if (argc!=2) {
        fputs("usage: test_j1_24_b4_while_wend_cyd_e2e REPOSITORY_ROOT\n",stderr);
        return 1;
    }
    CHECK(sizeof positives/sizeof positives[0]==15U);
    for(j=0U;j<2U;++j)
        for(i=0U;i<sizeof positives/sizeof positives[0];++i)
            CHECK(run_positive(argv[1],sessions[j],&positives[i])==0);
    CHECK(lifecycle()==0);
    CHECK(negatives()==0);
    CHECK(no_space()==0);
    puts("J1.24-B4 15/15 positive x original/repeat, C99 BSR->text->Ready,"
         " CPC semantic screen, atomicity and lifecycle PASS");
    return 0;
}
