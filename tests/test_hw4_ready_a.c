/* HW4-READY-A: the SAME C99 Ready writer linked by the ESP32 console.
 * Scenario data are from independent CPC A0-v2 PNGs, not disassembly. */
#include "cpc_ready_policy.h"
#include "cpc_uart_console.h"
#include "cpc_boot.h"
#include "uart_line.h"
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint8_t vram[CPC_VIDEO_BYTES];
static CpcVideo video;
static CpcText text;
static UartLine line;
static struct {
    BasicProgram program;
    BasicVariableStore store;
    BasicSessionRuntime runtime;
    uint8_t bytes[8192], temporary[2048], output[4096];
    BasicVariableEntry entries[64];
    size_t written;
} basic;
static unsigned ready_writes;

static uint8_t glyph(void *context,uint8_t ch,unsigned y)
{
    (void)context;
    return ch==' ' ? 0U : (uint8_t)((y & 1U) ? 0x42U : 0x3cU);
}
static void setup(void)
{
    assert(bp_init(&basic.program,basic.bytes,sizeof basic.bytes)==BP_OK);
    assert(bvs_init(&basic.store,basic.entries,64U)==BVS_OK);
    assert(bsr_init_with_store(&basic.runtime,&basic.program,&basic.store).status==BSR_OK);
    assert(cpc_video_init(&video,vram,sizeof vram,CPC_MODE_1));
    assert(cpc_text_init(&text,&video,glyph,NULL));
    uart_line_init(&line);
    ready_writes=0U;
    assert(cpc_boot_console(&text,true));
    const unsigned row=text.row,col=text.column;
    const size_t drawn=text.glyphs_drawn;
    bool emitted=true;
    assert(cpc_ready_policy_apply(&text,CPC_READY_BOOT_ALREADY_PAINTED,&emitted));
    assert(!emitted && row==text.row && col==text.column);
    assert(drawn==text.glyphs_drawn);
    bool page=true;
    assert(cpc_uart_console_prompt(&text,&page) && !page);
}
static void ready(CpcReadyTransition transition,bool expected)
{
    bool emitted=!expected;
    const size_t before=text.glyphs_drawn;
    const unsigned row=text.row;
    const size_t scrolls=text.scrolls;
    assert(cpc_ready_policy_apply(&text,transition,&emitted));
    assert(emitted==expected);
    assert(text.glyphs_drawn==before+(expected ? 5U : 0U));
    if(expected) {
        ++ready_writes;
        assert(text.row==row+1U || (row==24U && text.row==24U &&
                                    text.scrolls==scrolls+1U));
    } else {
        assert(text.row==row && text.scrolls==scrolls);
    }
    assert(text.column==0U);
    bool page=true;
    assert(cpc_uart_console_prompt(&text,&page) && !page);
}
static void submit(const char *command,CpcReadyTransition transition,
                   bool expect_diagnostic)
{
    uart_line_init(&line);
    for(size_t i=0U;command[i]!='\0';++i) {
        uint8_t ch=(uint8_t)command[i];
        assert(uart_line_feed(&line,ch)==UART_LINE_APPEND);
        assert(cpc_uart_console_append(&text,ch));
    }
    assert(uart_line_feed(&line,'\r')==UART_LINE_READY);
    assert(cpc_uart_console_end_line(&text));
    basic.written=0U;
    BSRResult r=bsr_submit(&basic.runtime,line.data,line.length,
                          basic.temporary,sizeof basic.temporary,
                          basic.output,sizeof basic.output,&basic.written);
    assert((r.status!=BSR_OK)==expect_diagnostic);
    if(expect_diagnostic) {
        static const uint8_t error[]="ERROR\n";
        assert(cpc_text_write(&text,error,sizeof error-1U));
    } else {
        if(basic.written>0U)
            assert(cpc_text_write(&text,basic.output,basic.written));
        if(transition==CPC_READY_RUN_RETURN && basic.runtime.state==BSR_RUNNING) {
            bool ended=false;
            for(unsigned step=0U;step<16U;++step) {
                basic.written=0U;
                r=bsr_step(&basic.runtime,basic.output,
                           sizeof basic.output,&basic.written);
                if(r.status==BSR_END) { ended=true; break; }
                assert(r.status==BSR_OK && r.executor_status==BE_OK);
                if(basic.written>0U)
                    assert(cpc_text_write(&text,basic.output,basic.written));
            }
            assert(ended && basic.runtime.state==BSR_IDLE);
        }
    }
    ready(transition,cpc_ready_policy_emit(transition));
    uart_line_ack(&line);
}
static void historical_matrix(void)
{
    setup();
    assert(!cpc_ready_policy_emit(CPC_READY_NUMBERED_STORED));
    assert(!cpc_ready_policy_emit(CPC_READY_EMPTY_ENTER));
    assert(cpc_ready_policy_emit(CPC_READY_LIST_RETURN));
    assert(cpc_ready_policy_emit(CPC_READY_NEW_RETURN));
    assert(cpc_ready_policy_emit(CPC_READY_RUN_RETURN));
    assert(cpc_ready_policy_emit(CPC_READY_BASIC_DIAGNOSTIC));
    assert(strcmp(cpc_ready_transition_name(CPC_READY_NUMBERED_STORED),
                  "NUMBERED_STORED")==0);

    submit("10 PRINT 2",CPC_READY_NUMBERED_STORED,false);
    submit("20 END",CPC_READY_NUMBERED_STORED,false);
    static uint8_t program_before[8192];
    memcpy(program_before,basic.bytes,sizeof program_before);
    size_t size_before=basic.program.size;
    submit("",CPC_READY_EMPTY_ENTER,false);
    assert(ready_writes==0U);
    assert(basic.program.size==size_before &&
           memcmp(program_before,basic.bytes,sizeof program_before)==0);

    submit("LIST",CPC_READY_LIST_RETURN,false);
    assert(ready_writes==1U);
    submit("RUN",CPC_READY_RUN_RETURN,false);
    assert(ready_writes==2U && basic.runtime.state==BSR_IDLE);
    submit("NEW",CPC_READY_NEW_RETURN,false);
    assert(ready_writes==3U);
    assert(basic.program.size<=size_before);
    submit("GOTO 999",CPC_READY_BASIC_DIAGNOSTIC,true);
    assert(ready_writes==4U);
}
static void host_diagnostics_and_guards(void)
{
    size_t before=basic.program.size;
    static uint8_t copy[8192];
    memcpy(copy,basic.bytes,sizeof copy);
    assert(cpc_uart_console_clear(&text));
    ready(CPC_READY_HOST_CLS,false);
    assert(basic.program.size==before &&
           memcmp(copy,basic.bytes,sizeof copy)==0);
    ready(CPC_READY_HOST_DEMO,true); /* legacy host choice, not CPC */
    assert(ready_writes==5U);
    static const uint8_t error[]="ERROR\n";
    assert(cpc_text_write(&text,error,sizeof error-1U));
    ready(CPC_READY_HOST_REJECTED,true);
    assert(ready_writes==6U);
    assert(basic.program.size==before &&
           memcmp(copy,basic.bytes,sizeof copy)==0);
    ready(CPC_READY_UNCHARACTERIZED_DIRECT,false);
    assert(ready_writes==6U);
    bool emitted=true;
    const unsigned row=text.row,col=text.column;
    assert(!cpc_ready_policy_apply(&text,CPC_READY_TRANSITION_COUNT,&emitted));
    assert(!cpc_ready_policy_apply(NULL,CPC_READY_LIST_RETURN,&emitted));
    assert(row==text.row && col==text.column && emitted);
}
static void bottom_scroll(void)
{
    setup();
    text.row=24U;
    text.column=0U;
    const size_t before=text.scrolls;
    ready(CPC_READY_NUMBERED_STORED,false);
    assert(text.scrolls==before && text.row==24U);
    ready(CPC_READY_LIST_RETURN,true);
    assert(text.scrolls==before+1U && text.row==24U);
    assert(text.bytes_clipped==0U);
}
int main(void)
{
    historical_matrix();
    host_diagnostics_and_guards();
    bottom_scroll();
    puts("HW4-READY-A production policy: boot/no duplicate, numbered x2, "
         "blank, LIST, RUN, NEW, error, host reject/CLS/DEMO and MODE1 scroll PASS");
    return 0;
}
