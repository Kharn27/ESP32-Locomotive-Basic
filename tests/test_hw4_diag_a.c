/* HW4-DIAG-A: real bsr_submit -> real production diagnostic/Ready writer.
 * Screenshots A0 are independent and never generated from this test. */
#include "cpc_diag_policy.h"
#include "cpc_ready_policy.h"
#include "cpc_boot.h"
#include "cpc_uart_console.h"
#include "uart_line.h"
#include "basic_variable_store.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static struct { uint8_t pre[16], bytes[CPC_VIDEO_BYTES], post[16]; } guarded;
static CpcVideo video;
static CpcText text;
static UartLine line;
static struct {
    BasicProgram program;
    BasicVariableStore vars;
    BasicSessionRuntime runtime;
    uint8_t program_bytes[8192], temporary[2048], output[4096], arena[4096];
    BasicVariableEntry entries[64];
    size_t written;
} basic;
static char painted[512];
static size_t painted_count;
static unsigned ready_count;
static uint8_t before_program[8192];

static uint8_t glyph(void *context,uint8_t ch,unsigned row)
{
    (void)context;
    if(row==0U) {
        assert(painted_count<sizeof painted);
        painted[painted_count++]=(char)ch;
    }
    return ch==' ' ? 0U : (uint8_t)((row&1U) ? 0xf0U : 0x0fU);
}
static void canaries(void)
{
    for(size_t i=0;i<16U;++i)
        assert(guarded.pre[i]==0xa5U && guarded.post[i]==0x5aU);
}
static void init_console(void)
{
    memset(&guarded,0,sizeof guarded);
    memset(guarded.pre,0xa5,sizeof guarded.pre);
    memset(guarded.post,0x5a,sizeof guarded.post);
    assert(bp_init(&basic.program,basic.program_bytes,
                   sizeof basic.program_bytes)==BP_OK);
    assert(bvs_init_with_arena(&basic.vars,basic.entries,64U,basic.arena,
                               sizeof basic.arena)==BVS_OK);
    assert(bsr_init_with_store(&basic.runtime,&basic.program,&basic.vars).status==BSR_OK);
    assert(cpc_video_init(&video,guarded.bytes,CPC_VIDEO_BYTES,CPC_MODE_1));
    assert(cpc_text_init(&text,&video,glyph,NULL));
    painted_count=0U;
    assert(cpc_boot_console(&text,true)); /* initial Ready belongs to boot */
    painted_count=0U;
    ready_count=0U;
    uart_line_init(&line);
    bool clear=true;
    assert(cpc_uart_console_prompt(&text,&clear) && !clear);
    canaries();
}
static void compare_painted(const char *expected)
{
    size_t n=strlen(expected);
    assert(n==painted_count);
    assert(memcmp(painted,expected,n)==0);
}
static BSRResult real_submit(const char *command,
                             CpcDiagCategory category,
                             CpcReadyTransition transition,
                             bool failure,const char *painted_expected)
{
    uart_line_init(&line);
    for(size_t i=0U;command[i];++i) {
        const uint8_t ch=(uint8_t)command[i];
        assert(uart_line_feed(&line,ch)==UART_LINE_APPEND);
        assert(cpc_uart_console_append(&text,ch));
    }
    assert(uart_line_feed(&line,'\r')==UART_LINE_READY);
    assert(cpc_uart_console_end_line(&text));
    painted_count=0U;
    memcpy(before_program,basic.program_bytes,sizeof before_program);
    const size_t old_size=basic.program.size;
    basic.written=0U;
    BSRResult r=bsr_submit(&basic.runtime,line.data,line.length,
                          basic.temporary,sizeof basic.temporary,
                          basic.output,sizeof basic.output,&basic.written);
    assert((r.status!=BSR_OK)==failure);
    assert(cpc_diag_policy_select(line.data,line.length,r)==category);
    if(failure) {
        assert(basic.program.size==old_size);
        assert(memcmp(before_program,basic.program_bytes,
                      sizeof before_program)==0);
        assert(cpc_diag_policy_write(&text,category));
    } else if(basic.written) {
        assert(cpc_text_write(&text,basic.output,basic.written));
    }
    /* The production console emits Ready only AFTER execution finishes. */
    if(!failure && transition==CPC_READY_RUN_RETURN &&
       basic.runtime.state==BSR_RUNNING) {
        bool ended=false;
        for(unsigned step=0U;step<16U;++step) {
            basic.written=0U;
            BSRResult step_result=bsr_step(&basic.runtime,basic.output,
                                          sizeof basic.output,&basic.written);
            if(step_result.status==BSR_END) { ended=true; break; }
            assert(step_result.status==BSR_OK &&
                   step_result.executor_status==BE_OK);
            if(basic.written)
                assert(cpc_text_write(&text,basic.output,basic.written));
        }
        assert(ended && basic.runtime.state==BSR_IDLE);
    }
    bool emitted=false;
    assert(cpc_ready_policy_apply(&text,transition,&emitted));
    assert(emitted==cpc_ready_policy_emit(transition));
    if(emitted) ++ready_count;
    compare_painted(painted_expected);
    assert(text.column==0U);
    bool clear=true;
    assert(cpc_uart_console_prompt(&text,&clear) && !clear);
    uart_line_ack(&line);
    canaries();
    return r;
}
static void real_historical_cases(void)
{
    init_console();
    BSRResult absent=real_submit("10",CPC_DIAG_LINE_DOES_NOT_EXIST,
        CPC_READY_BASIC_DIAGNOSTIC,true,"Line does not existReady");
    assert(absent.status==BSR_SESSION_ERROR &&
           absent.session.status==BS_NOT_FOUND);
    assert(ready_count==1U && basic.program.size==2U);
    (void)real_submit("10 ",CPC_DIAG_LINE_DOES_NOT_EXIST,
        CPC_READY_BASIC_DIAGNOSTIC,true,"Line does not existReady");
    assert(ready_count==2U);
    (void)real_submit("10 PRINT 2",CPC_DIAG_HOST_GENERIC,
        CPC_READY_NUMBERED_STORED,false,"");
    assert(basic.program.size>2U && ready_count==2U);
    (void)real_submit("10",CPC_DIAG_HOST_GENERIC,
        CPC_READY_NUMBERED_STORED,false,"");
    assert(basic.program.size==2U && ready_count==2U);
    (void)real_submit("LIST",CPC_DIAG_HOST_GENERIC,
        CPC_READY_LIST_RETURN,false,"Ready");
    assert(basic.program.size==2U && ready_count==3U);
    (void)real_submit("NEW",CPC_DIAG_HOST_GENERIC,
        CPC_READY_NEW_RETURN,false,"Ready");
    (void)real_submit("10",CPC_DIAG_LINE_DOES_NOT_EXIST,
        CPC_READY_BASIC_DIAGNOSTIC,true,"Line does not existReady");
    assert(ready_count==5U);
    (void)real_submit("GOTO 999",CPC_DIAG_HOST_GENERIC,
        CPC_READY_BASIC_DIAGNOSTIC,true,"ERRORReady");
    (void)real_submit("listt",CPC_DIAG_HOST_GENERIC,
        CPC_READY_BASIC_DIAGNOSTIC,true,"ERRORReady");
    (void)real_submit("0",CPC_DIAG_HOST_GENERIC,
        CPC_READY_BASIC_DIAGNOSTIC,true,"ERRORReady");
    assert(ready_count==8U);
}
static void wrong_status_and_host_guards(void)
{
    init_console();
    basic.written=0U;
    const uint8_t source[]="10";
    BSRResult r=bsr_submit(&basic.runtime,source,2U,
                          basic.temporary,sizeof basic.temporary,
                          basic.output,sizeof basic.output,&basic.written);
    assert(cpc_diag_policy_select(source,2U,r)==CPC_DIAG_LINE_DOES_NOT_EXIST);
    assert(cpc_diag_policy_select(NULL,0U,r)==CPC_DIAG_HOST_GENERIC);
    assert(cpc_diag_policy_select((const uint8_t *)"10 PRINT 2",10U,r)==CPC_DIAG_HOST_GENERIC);
    assert(cpc_diag_policy_select((const uint8_t *)" 10",3U,r)==CPC_DIAG_HOST_GENERIC);
    assert(cpc_diag_policy_select((const uint8_t *)"0",1U,r)==CPC_DIAG_HOST_GENERIC);
    assert(cpc_diag_policy_select((const uint8_t *)"65536",5U,r)==CPC_DIAG_HOST_GENERIC);
    assert(cpc_diag_policy_select((const uint8_t *)"10\r",3U,r)==CPC_DIAG_HOST_GENERIC);
    BSRResult fake=r;
    fake.status=BSR_EXECUTOR_ERROR;
    assert(cpc_diag_policy_select(source,2U,fake)==CPC_DIAG_HOST_GENERIC);
    fake=r; fake.session.status=BS_UNSUPPORTED_DIRECT;
    assert(cpc_diag_policy_select(source,2U,fake)==CPC_DIAG_HOST_GENERIC);
    fake=r; fake.session.program_status=BP_NOT_FOUND;
    assert(cpc_diag_policy_select(source,2U,fake)==CPC_DIAG_HOST_GENERIC);
    assert(strcmp(cpc_diag_policy_message(CPC_DIAG_LINE_DOES_NOT_EXIST),
                  "Line does not exist")==0);
    assert(strcmp(cpc_diag_policy_message(CPC_DIAG_HOST_GENERIC),"ERROR")==0);
    painted_count=0U;
    assert(cpc_diag_policy_write(&text,CPC_DIAG_HOST_GENERIC));
    compare_painted("ERROR");
    const size_t current=text.glyphs_drawn;
    const unsigned row=text.row;
    assert(!cpc_diag_policy_write(NULL,CPC_DIAG_HOST_GENERIC));
    assert(!cpc_diag_policy_write(&text,CPC_DIAG_COUNT));
    assert(current==text.glyphs_drawn && row==text.row);
    canaries();
}
static void string_bonjour_and_run(void)
{
    init_console();
    (void)real_submit("10 A$=\"BONJOUR\"",CPC_DIAG_HOST_GENERIC,
        CPC_READY_NUMBERED_STORED,false,"");
    (void)real_submit("20 PRINT A$",CPC_DIAG_HOST_GENERIC,
        CPC_READY_NUMBERED_STORED,false,"");
    (void)real_submit("30 END",CPC_DIAG_HOST_GENERIC,
        CPC_READY_NUMBERED_STORED,false,"");
    (void)real_submit("RUN",CPC_DIAG_HOST_GENERIC,
        CPC_READY_RUN_RETURN,false,"BONJOURReady");
    assert(basic.runtime.state==BSR_IDLE && ready_count==1U);
    canaries();
}
static void scroll_diagnostic(void)
{
    init_console();
    text.row=24U;
    text.column=0U;
    const size_t scrolls=text.scrolls;
    assert(cpc_diag_policy_write(&text,CPC_DIAG_LINE_DOES_NOT_EXIST));
    bool emitted=false;
    assert(cpc_ready_policy_apply(&text,CPC_READY_BASIC_DIAGNOSTIC,&emitted));
    assert(emitted && text.row==24U && text.scrolls==scrolls+2U);
    assert(text.bytes_clipped==0U);
    canaries();
}
int main(void)
{
    real_historical_cases();
    wrong_status_and_host_guards();
    string_bonjour_and_run();
    scroll_diagnostic();
    puts("HW4-DIAG-A native diagnostic PASS : deletion, NEW/LIST, "
         "nonmatching errors, READY count, BONJOUR, canaries, scroll");
    return 0;
}
