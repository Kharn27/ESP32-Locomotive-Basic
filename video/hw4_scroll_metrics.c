/* HW4-SCROLL-OPT-A0: no TFT access, no UART, no allocation. MIT. */
#include "hw4_scroll_metrics.h"
#include <stddef.h>
#include <stdint.h>
const uint32_t hw4_scroll_bounds_us[HW4_SCROLL_BINS]={
    500U,1000U,2000U,4000U,8000U,16000U,
    32000U,64000U,128000U,256000U,512000U,UINT32_MAX
};
/* CpcText counts text/edit up-scrolls only. Navigation edge scrolls are
 * counted separately; no change to the underlying VIDEO or E2 APIs. */
void hw4_scroll_observe_text(Hw4ScrollMetrics *m, uint32_t up)
{
    if(m==NULL) return;
    if(up>=m->last_text_up) m->pending_up+=up-m->last_text_up;
    /* An unexpected reduction is an implicit reset: do not underflow. */
    else { ++m->resets; m->reset_pending=1U; m->pending_up+=up; }
    m->last_text_up=up;
}
void hw4_scroll_nav(Hw4ScrollMetrics *m,int direction)
{
    if(m==NULL) return;
    if(direction>0) ++m->pending_up;
    else if(direction<0) ++m->pending_down;
}
void hw4_scroll_clear(Hw4ScrollMetrics *m,uint32_t new_text_up)
{
    if(m==NULL) return;
    ++m->resets;
    m->reset_pending=1U;
    m->last_text_up=new_text_up;
}
void hw4_scroll_flush(Hw4ScrollMetrics *m,uint32_t bands,uint32_t us,
                      uint64_t bytes)
{
    if(m==NULL) return;
    const unsigned type=(m->pending_up||m->pending_down)
        ? HW4_SCROLL_ASSOCIATED : HW4_SCROLL_ORDINARY;
    Hw4ScrollClass *c=&m->cls[type];
    if(c->flushes==0U || us<c->min_us) c->min_us=us;
    if(us>c->max_us) c->max_us=us;
    ++c->flushes;
    c->bands+=bands;
    c->us_total+=us;
    c->spi_bytes+=bytes;
    unsigned bin=0U;
    while(bin<HW4_SCROLL_BINS-1U && us>hw4_scroll_bounds_us[bin]) ++bin;
    ++c->hist[bin];
    c->up+=m->pending_up; c->down+=m->pending_down;
    if(m->reset_pending) ++c->reset_tagged;
    m->pending_up=m->pending_down=m->reset_pending=0U;
}
uint32_t hw4_scroll_quantile_upper(const Hw4ScrollClass *c,unsigned percentile)
{
    if(c==NULL || c->flushes==0U || percentile==0U || percentile>100U)
        return 0U;
    const uint32_t rank=(uint32_t)(((uint64_t)c->flushes*percentile+99U)/100U);
    uint32_t seen=0U;
    for(unsigned i=0U;i<HW4_SCROLL_BINS;++i) {
        seen+=c->hist[i];
        if(seen>=rank) return hw4_scroll_bounds_us[i];
    }
    return UINT32_MAX; /* malformed histogram: analyzer will reject */
}
