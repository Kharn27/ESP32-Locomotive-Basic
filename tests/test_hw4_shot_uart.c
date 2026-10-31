/* HW4-SHOT-A: real portable C99 emitter against CpcVideo, not fake pixels. */
#include "hw4_shot_uart.h"
#include "cpc_video.h"
#include "uart_line.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    CpcVideo video;
    uint8_t vram[CPC_VIDEO_BYTES];
    FILE *wire;
    unsigned rendered, writes, yields;
    unsigned fail_render_at, fail_write_at;
} ShotTest;

static void setup(ShotTest *t)
{
    memset(t, 0, sizeof(*t));
    assert(cpc_video_init(&t->video,t->vram,sizeof(t->vram),CPC_MODE_1));
    assert(cpc_video_set_border(&t->video,1u));
    assert(cpc_video_set_ink(&t->video,0u,1u));
    assert(cpc_video_set_ink(&t->video,1u,24u));
    assert(cpc_video_set_ink(&t->video,2u,6u));
    assert(cpc_video_set_ink(&t->video,3u,18u));
    assert(cpc_video_set_text_colors(&t->video,1u,0u));
    assert(cpc_video_put(&t->video,16u,16u,2u));
    assert(cpc_video_put(&t->video,17u,16u,3u));
    assert(cpc_video_cursor(&t->video,5u,5u,true));
    t->fail_render_at = 300u;
    t->fail_write_at = 300u;
}
static bool render(void *ctx, unsigned y, uint16_t *scan, size_t n)
{
    ShotTest *t=(ShotTest *)ctx;
    assert(y == t->rendered++);
    if(y == t->fail_render_at) return false;
    return cpc_video_render_row(&t->video,y,scan,n);
}
static bool send_wire(void *ctx, const char *line, size_t n)
{
    ShotTest *t=(ShotTest *)ctx;
    if(t->writes++ == t->fail_write_at) return false;
    return fwrite(line,1u,n,t->wire) == n;
}
static void yielded(void *ctx) { ++((ShotTest *)ctx)->yields; }
static Hw4ShotStatus emit(ShotTest *t)
{
    return hw4_shot_emit(t,render,send_wire,yielded,
                         "HOST_001",1u,"LCD10_UNVERIFIED",
                         "HOST_TEST","fedcba9876543210");
}
static UartLineEvent feed(UartLine *line, const char *bytes, bool screen)
{
    UartLineEvent event=UART_LINE_NONE;
    while(*bytes) {
        event=screen ? uart_line_feed_screen(line,(uint8_t)*bytes) :
                       uart_line_feed(line,(uint8_t)*bytes);
        ++bytes;
    }
    return event;
}
static void home_routing(void)
{
    UartLine line, saved;
    uart_line_init(&line);
    assert(feed(&line,"10 PRINT \"A\"",true)==UART_LINE_APPEND);
    assert(feed(&line,"\x1b[D",true)==UART_LINE_LEFT);
    saved=line;
    assert(feed(&line,"\x1b[H",true)==UART_LINE_SCREENSHOT);
    assert(line.length==saved.length && line.cursor_pos==saved.cursor_pos);
    assert(!line.ready && !line.poisoned && !line.screen_navigation);
    assert(memcmp(line.data,saved.data,sizeof(line.data))==0);
    assert(feed(&line,"\x1b[1H",true)==UART_LINE_IGNORED);
    assert(feed(&line,"\x1b[H",false)==UART_LINE_IGNORED);
    assert(feed(&line,"\r",true)==UART_LINE_READY);
    assert(line.length==saved.length && !memcmp(line.data,saved.data,sizeof(line.data)));
    uart_line_ack(&line);
    assert(feed(&line,"\x1b[A",true)==UART_LINE_NAV_UP);
    assert(line.screen_navigation);
    assert(feed(&line,"\x1b[H",true)==UART_LINE_RETURN_HOME);
    assert(!line.screen_navigation && line.length==0u);
    assert(feed(&line,"\x1b[H",true)==UART_LINE_SCREENSHOT);
    uart_line_init(&line);
    assert(feed(&line,"\x1b[H",false)==UART_LINE_IGNORED);
}
static void invalid_and_abort(void)
{
    ShotTest *t=(ShotTest *)malloc(sizeof(*t));
    assert(t != NULL);
    setup(t);
    t->wire=tmpfile();
    assert(t->wire != NULL);
    assert(hw4_shot_emit(t,render,send_wire,yielded,"bad id",0u,
                         "LCD10_UNVERIFIED","HOST_TEST","fedcba9876543210")
           ==HW4_SHOT_BAD_ARGUMENT);
    assert(t->writes==0u && t->rendered==0u);
    assert(hw4_shot_emit(t,render,send_wire,yielded,"GOOD",0u,
                         "LCD10_UNVERIFIED","HOST_TEST","FEDCBA9876543210")
           ==HW4_SHOT_BAD_ARGUMENT);
    t->fail_render_at=13u;
    assert(emit(t)==HW4_SHOT_RENDER_ERROR);
    assert(t->rendered==14u && t->yields==13u);
    assert(fseek(t->wire,-90L,SEEK_END)==0);
    char tail[91]={0};
    assert(fread(tail,1u,90u,t->wire)==90u);
    assert(strstr(tail,"|ABORT|id=HOST_001|reason=RENDER_ERROR\n")!=NULL);
    fclose(t->wire);
    setup(t);
    t->wire=tmpfile();
    assert(t->wire != NULL);
    t->fail_write_at=2u;
    assert(emit(t)==HW4_SHOT_TRANSPORT_ERROR);
    assert(t->yields==1u && t->rendered==2u);
    fclose(t->wire);
    free(t);
}
static void positive(const char *file)
{
    ShotTest *t=(ShotTest *)malloc(sizeof(*t));
    assert(t != NULL);
    setup(t);
    CpcVideo previous=t->video;
    uint8_t original[CPC_VIDEO_BYTES];
    memcpy(original,t->vram,sizeof(original));
    t->wire=file ? fopen(file,"wb") : tmpfile();
    assert(t->wire != NULL);
    assert(emit(t)==HW4_SHOT_OK);
    assert(t->rendered==240u && t->yields==240u && t->writes==242u);
    assert(memcmp(original,t->vram,sizeof(original))==0);
    assert(memcmp(&previous,&t->video,sizeof(previous))==0);
    assert(fflush(t->wire)==0);
    assert(ftell(t->wire)>205440L);
    assert(fclose(t->wire)==0);
    free(t);
}
int main(int argc, char **argv)
{
    assert(argc==1 || (argc==3 && strcmp(argv[1],"--emit")==0));
    home_routing();
    invalid_and_abort();
    positive(argc==3 ? argv[2] : NULL);
    puts("hw4_shot_a_uart_emitter: OK");
    return 0;
}
