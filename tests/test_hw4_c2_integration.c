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
    static const uint8_t ready[]="Ready\n";
    assert(cpc_text_write(&text,ready,sizeof(ready)-1U));
    assert(cpc_uart_console_prompt(&text,&page) && !page);
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
static void long_list_scroll_integration(void)
{
    char numbered[32];
    bool cleared=false;
    setup();
    for(unsigned i=1U;i<=32U;++i) {
        int n=snprintf(numbered,sizeof(numbered),"%u PRINT 7",i*10U);
        assert(n>0 && (size_t)n<sizeof(numbered));
        input(numbered);
        if(i==26U) {
            size_t stored=b.program.size;
            BSRResult first=submit("LIST");
            assert(first.status==BSR_OK && b.written>0U);
            assert(cpc_text_write(&text,b.output,b.written));
            static const uint8_t ready26[]="Ready\n";
            assert(cpc_text_write(&text,ready26,sizeof(ready26)-1U));
            assert(cpc_uart_console_prompt(&text,&cleared) && !cleared);
            assert(b.program.size==stored && text.row==24U);
        }
    }
    assert(b.program.size>0U && text.scrolls>0U);
    size_t bytes=b.program.size;
    static uint8_t snapshot[8192];
    memcpy(snapshot,b.bytes,sizeof(snapshot));
    for(unsigned pass=0U;pass<2U;++pass) {
        BSRResult r=submit("LIST");
        assert(r.status==BSR_OK && b.written>0U);
        assert(cpc_text_write(&text,b.output,b.written));
        static const uint8_t ready[]="Ready\n";
        assert(cpc_text_write(&text,ready,sizeof(ready)-1U));
        assert(cpc_uart_console_prompt(&text,&cleared) && !cleared);
        assert(text.row==24U && text.bytes_clipped==0U);
        assert(b.program.size==bytes && memcmp(snapshot,b.bytes,sizeof(snapshot))==0);
    }
    /* Explicit diagnostic !CLS may clear the screen, never the BASIC store. */
    assert(cpc_uart_console_clear(&text));
    assert(b.program.size==bytes && memcmp(snapshot,b.bytes,sizeof(snapshot))==0);
    assert(submit("LIST").status==BSR_OK && b.written>0U);
    assert(cpc_text_write(&text,b.output,b.written));
    assert(submit("RUN").status==BSR_OK);
    unsigned run_steps=0U;
    for (;;) {
        BSRResult step=bsr_step(&b.runtime,b.output,sizeof(b.output),&b.written);
        if(step.status==BSR_END) break;
        assert(step.status==BSR_OK && step.executor_status==BE_OK);
        assert(++run_steps<=32U);
        assert(cpc_text_write(&text,b.output,b.written));
    }
    assert(run_steps==32U && text.row==24U && text.bytes_clipped==0U);
    assert(b.program.size==bytes && memcmp(snapshot,b.bytes,sizeof(snapshot))==0);
    assert(submit("NEW").status==BSR_OK);
    assert(submit("LIST").status==BSR_OK && b.written==0U);
    assert(submit("RUN").status==BSR_OK);
    BSRResult r=bsr_step(&b.runtime,b.output,sizeof(b.output),&b.written);
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

/* A malformed/incomplete ANSI sequence must never be submitted to BASIC.
 * The same isolation applies even with a nonempty stored program. */
static void ansi_atomic_program_guard(void)
{
    static uint8_t snapshot[8192];
    assert(submit("10 PRINT 7").status==BSR_OK);
    size_t before=b.program.size;
    memcpy(snapshot,b.bytes,sizeof(snapshot));
    uart_line_init(&line);
    assert(uart_line_feed(&line,'2')==UART_LINE_APPEND);
    assert(uart_line_feed(&line,'0')==UART_LINE_APPEND);
    assert(uart_line_feed(&line,0x1bU)==UART_LINE_IGNORED);
    assert(uart_line_feed(&line,'[')==UART_LINE_IGNORED);
    assert(uart_line_feed(&line,'3')==UART_LINE_IGNORED);
    assert(uart_line_feed(&line,'\n')==UART_LINE_REJECTED);
    assert(line.poisoned && line.ansi_incomplete_rejected==1U);
    /* Firmware routes REJECTED to ERROR/prompt, never bsr_submit(). */
    uart_line_ack(&line);
    assert(b.program.size==before);
    assert(memcmp(b.bytes,snapshot,sizeof(snapshot))==0);
    assert(submit("LIST").status==BSR_OK);
    assert(b.written==strlen("10 PRINT 7\n"));
    assert(memcmp(b.output,"10 PRINT 7\n",b.written)==0);
    uart_line_init(&line);
    assert(uart_line_feed(&line,'X')==UART_LINE_APPEND);
    static const uint8_t seq[]={0x1bU,'[','3','~'};
    for(size_t i=0;i<3U;++i)
        assert(uart_line_feed(&line,seq[i])==UART_LINE_IGNORED);
    assert(uart_line_feed(&line,seq[3])==UART_LINE_NONE);
    assert(line.length==1U && line.cursor_pos==1U);
    assert(uart_line_feed(&line,0x08U)==UART_LINE_DELETE);
    assert(line.length==0U);
    assert(uart_line_feed(&line,'\r')==UART_LINE_READY);
    /* Empty candidate submission is benign, unchanged source. */
    uart_line_ack(&line);
    assert(b.program.size==before);
    assert(memcmp(b.bytes,snapshot,sizeof(snapshot))==0);
}
int main(void)
{
    setup(); real_run(); list_new_and_fail_atomic(); rejected_input_does_not_mutate(); ansi_atomic_program_guard(); long_list_scroll_integration();
    puts("HW4-C2 actual interactive bytes -> runtime -> VRAM, LIST NEW PASS");
    return 0;
}
