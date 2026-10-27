/* HW4-C2: interactive UART lines -> real BASIC session -> MODE 1 pixels. */
#include "uart_line.h"
#include "cpc_uart_console.h"
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static struct {
    BasicProgram program;
    BasicVariableStore variables;
    BasicSessionRuntime runtime;
    uint8_t bytes[8192];
    BasicVariableEntry entries[64];
    uint8_t temp[2048];
    uint8_t output[4096];
    size_t written;
} b;
static UartLine line;
static uint8_t vram[CPC_VIDEO_BYTES];
static CpcVideo v;
static CpcText text;
static uint8_t glyph(void *ctx, uint8_t ch, unsigned y)
{ (void)ctx; return y==0U && ch!=' ' ? 0x80U : 0U; }
static void setup(void)
{
    bool page;
    assert(bp_init(&b.program,b.bytes,sizeof(b.bytes))==BP_OK);
    assert(bvs_init(&b.variables,b.entries,64U)==BVS_OK);
    assert(bsr_init_with_store(&b.runtime,&b.program,&b.variables).status==BSR_OK);
    assert(cpc_video_init(&v,vram,sizeof(vram),CPC_MODE_1));
    assert(cpc_text_init(&text,&v,glyph,NULL));
    uart_line_init(&line);
    assert(cpc_uart_console_prompt(&text,&page));
}
static BSRResult submit(const char *cmd)
{
    return bsr_submit(&b.runtime,(const uint8_t *)cmd,strlen(cmd),
                       b.temp,sizeof(b.temp),b.output,sizeof(b.output),
                       &b.written);
}
static void input(const char *source)
{
    bool page;
    const uint8_t *ptr=(const uint8_t *)source;
    for(size_t i=0U;ptr[i]!=0U;++i) {
        assert(uart_line_feed(&line,ptr[i])==UART_LINE_APPEND);
        assert(cpc_uart_console_append(&text,ptr[i]));
    }
    assert(uart_line_feed(&line,'\r')==UART_LINE_READY);
    assert(line.length==strlen(source));
    assert(memcmp(line.data,source,line.length)==0);
    assert(cpc_uart_console_end_line(&text));
    BSRResult r=bsr_submit(&b.runtime,line.data,line.length,
                  b.temp,sizeof(b.temp),b.output,sizeof(b.output),&b.written);
    assert(r.status==BSR_OK);
    if(b.written>0U) assert(cpc_text_write(&text,b.output,b.written));
    uart_line_ack(&line);
    assert(uart_line_feed(&line,'\n')==UART_LINE_NONE);
    assert(cpc_uart_console_prompt(&text,&page));
}
static void real_run(void)
{
    static const char *const src[] = {
        "10 A%=2", "20 B%=A%+3", "30 PRINT B%", "40 END"
    };
    for(size_t i=0U;i<4U;++i) input(src[i]);
    input("RUN");
    static const uint8_t expected[] = {' ','5',' ','\n'};
    uint8_t got[20]={0};
    size_t count=0U;
    unsigned steps=0U;
    for(;;) {
        BSRResult r=bsr_step(&b.runtime,b.output,sizeof(b.output),&b.written);
        if(r.status==BSR_END) break;
        assert(r.status==BSR_OK && r.executor_status==BE_OK);
        assert(++steps<=4U);
        assert(count+b.written<=sizeof(got));
        memcpy(got+count,b.output,b.written);
        count+=b.written;
        assert(cpc_text_write(&text,b.output,b.written));
    }
    assert(steps==4U && count==sizeof(expected));
    assert(memcmp(got,expected,sizeof(expected))==0);
    assert(b.runtime.state==BSR_IDLE);
    bool page;
    assert(cpc_uart_console_prompt(&text,&page));
}
static void list_new_and_fail_atomic(void)
{
    BSRResult r=submit("LIST");
    assert(r.status==BSR_OK && b.written>0U);
    const char *listing="10 A%=2\n20 B%=A%+3\n30 PRINT B%\n40 END\n";
    assert(b.written==strlen(listing));
    assert(memcmp(b.output,listing,b.written)==0);
    assert(cpc_text_write(&text,b.output,b.written));
    size_t size_before=b.program.size;
    static uint8_t copy[8192];
    memcpy(copy,b.bytes,sizeof(copy));
    r=submit("PRINT 2");
    assert(r.status==BSR_SESSION_ERROR);
    assert(b.program.size==size_before);
    assert(memcmp(b.bytes,copy,sizeof(copy))==0);
    r=submit("NEW");
    assert(r.status==BSR_OK);
    r=submit("LIST");
    assert(r.status==BSR_OK && b.written==0U);
    r=submit("RUN");
    assert(r.status==BSR_OK);
    r=bsr_step(&b.runtime,b.output,sizeof(b.output),&b.written);
    assert(r.status==BSR_END);
}
static void rejected_input_does_not_mutate(void)
{
    size_t n=b.program.size;
    static uint8_t copy[8192];
    memcpy(copy,b.bytes,sizeof(copy));
    uart_line_init(&line);
    for(size_t i=0;i<UART_LINE_CAPACITY;++i)
        assert(uart_line_feed(&line,'X')==UART_LINE_APPEND);
    assert(uart_line_feed(&line,'X')==UART_LINE_OVERFLOW);
    assert(uart_line_feed(&line,'\r')==UART_LINE_REJECTED);
    /* Deliberately do NOT invoke bsr_submit for a rejected host line. */
    uart_line_ack(&line);
    assert(b.program.size==n);
    assert(memcmp(b.bytes,copy,sizeof(copy))==0);
}
int main(void)
{
    setup(); real_run(); list_new_and_fail_atomic(); rejected_input_does_not_mutate();
    puts("HW4-C2 actual interactive bytes -> runtime -> VRAM, LIST NEW PASS");
    return 0;
}
