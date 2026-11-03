/* Host negative + exact RGB565 payload oracle for the production A1 planner. */
#include "hw4_batch16_dma.h"
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define TFT_WIDTH 320U
#define VIEW_TOP 20U
#define VIEW_PIXELS 128000U
static uint8_t legacy[VIEW_PIXELS], batched[VIEW_PIXELS];
static uint8_t guarded[HW4_BATCH16_BUFFER_BYTES + 2U];

typedef struct {
    unsigned attempts;
    unsigned failure_on; /* 1-based, 0 => no failure */
    unsigned last_end_y;
    bool valid;
    bool capture;
} Sender;

static uint16_t pixel(unsigned y, unsigned x)
{
    return (uint16_t)((y * 137U + x * 271U) ^ ((x << 5U) | (y >> 2U)));
}
static bool fake_send(void *ptr, unsigned first, unsigned height)
{
    Sender *s = ptr;
    ++s->attempts;
    const unsigned y = VIEW_TOP + first * 8U;
    if (!((height == 16U && first < 24U && first % 2U == 0U) ||
          (height == 8U && first == 24U))) s->valid = false;
    if (y != s->last_end_y || y + height > 220U) s->valid = false;
    s->last_end_y = y + height;
    if (s->failure_on == s->attempts) return false;
    guarded[0] = 0xa5U;
    guarded[sizeof(guarded)-1U] = 0x5aU;
    for (unsigned row=0U;row<height;++row)
        for (unsigned x=0U;x<TFT_WIDTH;++x) {
            size_t pos = 1U + ((size_t)row*TFT_WIDTH+x)*2U;
            uint16_t colour=pixel(y+row,x);
            guarded[pos]=(uint8_t)(colour>>8U);
            guarded[pos+1U]=(uint8_t)colour;
        }
    if (guarded[0]!=0xa5U || guarded[sizeof(guarded)-1U]!=0x5aU)
        s->valid=false;
    if(s->capture) {
        const size_t offset=(size_t)first*HW4_BATCH16_BAND_BYTES;
        memcpy(batched+offset,guarded+1U,(size_t)height*TFT_WIDTH*2U);
    }
    return true;
}
static void test_exact(void)
{
    for(unsigned b=0U;b<25U;++b) for(unsigned row=0U;row<8U;++row)
        for(unsigned x=0U;x<TFT_WIDTH;++x) {
            const unsigned y=VIEW_TOP+b*8U+row;
            const size_t pos=(size_t)b*5120U+row*640U+x*2U;
            uint16_t colour=pixel(y,x);
            legacy[pos]=(uint8_t)(colour>>8U);
            legacy[pos+1U]=(uint8_t)colour;
        }
    Sender s={0U,0U,VIEW_TOP,true,true};
    uint32_t dirty=HW4_BATCH16_FULL_DIRTY;
    Hw4Batch16Stats metrics={0U};
    assert(hw4_batch16_eligible(true,1,10U,dirty));
    assert(hw4_batch16_flush(&dirty,fake_send,&s,&metrics));
    assert(s.valid && dirty==0U && s.attempts==13U && s.last_end_y==220U);
    assert(metrics.logical_bands==25U && metrics.physical_transfers==13U);
    assert(metrics.pixel_bytes==128000U);
    assert(memcmp(legacy,batched,VIEW_PIXELS)==0);
    assert(!hw4_batch16_eligible(false,1,10U,HW4_BATCH16_FULL_DIRTY));
    assert(!hw4_batch16_eligible(true,0,10U,HW4_BATCH16_FULL_DIRTY));
    assert(!hw4_batch16_eligible(true,2,10U,HW4_BATCH16_FULL_DIRTY));
    assert(!hw4_batch16_eligible(true,1,9U,HW4_BATCH16_FULL_DIRTY));
    assert(!hw4_batch16_eligible(true,1,11U,HW4_BATCH16_FULL_DIRTY));
    assert(!hw4_batch16_eligible(true,1,10U,0U));
    assert(!hw4_batch16_eligible(true,1,10U,HW4_BATCH16_FULL_DIRTY^2U));
    assert(!hw4_batch16_eligible(true,1,10U,UINT32_C(0x03ffffff)));
    for(unsigned i=1U;i<=13U;++i) {
        Sender f={0U,i,VIEW_TOP,true,false};
        Hw4Batch16Stats partial={999U,999U,999U};
        dirty=HW4_BATCH16_FULL_DIRTY;
        assert(!hw4_batch16_flush(&dirty,fake_send,&f,&partial));
        assert(f.valid && f.attempts==i);
        assert(partial.physical_transfers==i-1U);
        assert(partial.logical_bands==(i-1U)*2U);
        assert(partial.pixel_bytes==(uint64_t)(i-1U)*10240U);
        const uint32_t sent = (UINT32_C(1) << (2U*(i-1U))) - 1U;
        assert(dirty==(HW4_BATCH16_FULL_DIRTY & ~sent));
    }
    Sender reject={0U,0U,VIEW_TOP,true,false};
    Hw4Batch16Stats untouched={7U,7U,7U};
    assert(!hw4_batch16_flush(NULL,fake_send,&reject,&untouched));
    assert(reject.attempts==0U && untouched.logical_bands==7U);
    dirty=HW4_BATCH16_FULL_DIRTY & ~UINT32_C(4);
    assert(!hw4_batch16_flush(&dirty,fake_send,&reject,&untouched));
    assert(dirty==(HW4_BATCH16_FULL_DIRTY & ~UINT32_C(4)) && reject.attempts==0U);
    dirty=HW4_BATCH16_FULL_DIRTY;
    assert(!hw4_batch16_flush(&dirty,NULL,&reject,&untouched));
    assert(!hw4_batch16_flush(&dirty,fake_send,&reject,NULL));
    assert(dirty==HW4_BATCH16_FULL_DIRTY && reject.attempts==0U);
    puts("HW4-A1-C0 exact_payload=128000 transfers=13 logical=25 failures=13 no_retry=PASS");
}
int main(void) {test_exact();return 0;}
