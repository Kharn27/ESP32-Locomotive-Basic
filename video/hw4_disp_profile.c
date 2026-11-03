/* HW4-DISP-PROFILE-A: no heap, no UART, no IDF dependency. MIT. */
#include "hw4_disp_profile.h"
#include <limits.h>
#include <stddef.h>
#include <string.h>
const uint32_t hw4_dp_bounds_us[HW4_DP_BINS] = {
    500U, 1000U, 2000U, 4000U, 8000U, 16000U,
    32000U, 64000U, 128000U, 256000U, 512000U, UINT32_MAX
};
void hw4_dp_reset(Hw4DispProfile *p)
{
    if(p) memset(p,0,sizeof(*p));
}
static bool fits(uint64_t a,uint64_t b) { return b<=UINT64_MAX-a; }
uint64_t hw4_dp_bytes(const Hw4DpClass *c)
{
    return c ? c->bands*HW4_DP_BAND_BYTES : 0U;
}
uint64_t hw4_dp_other_us(const Hw4DpClass *c)
{
    return c ? c->wall_us-c->render_pack_us-c->submit_us-c->wait_us : 0U;
}
uint32_t hw4_dp_zero_scroll(const Hw4DpClass *c)
{
    return c ? c->n-c->one_scroll-c->multi_scroll : 0U;
}
/* Unaligned byte-level encoding, stable and C99-portable on host and Xtensa. */
static void put32(uint8_t *dst,uint32_t value)
{
    for(unsigned k=0U;k<4U;++k)
        dst[k]=(uint8_t)(value>>(k*8U));
}
static uint32_t get32(const uint8_t *src)
{
    uint32_t value=0U;
    for(unsigned k=0U;k<4U;++k)
        value|=(uint32_t)src[k]<<(k*8U);
    return value;
}
bool hw4_dp_trace_at(const Hw4DispProfile *p,uint32_t index,Hw4DpTrace *out)
{
    if(p==NULL || out==NULL || index>=p->trace_size ||
       p->trace_size>HW4_DP_TRACE_CAP ||
       p->trace_next>=HW4_DP_TRACE_CAP) return false;
    const uint32_t pos=(p->trace_next+HW4_DP_TRACE_CAP-p->trace_size+index)
                       %HW4_DP_TRACE_CAP;
    const uint8_t *const src=p->trace[pos];
    Hw4DpTrace decoded={
        .seq=p->completed-p->trace_size+index+1U,
        .bands=src[0],
        .scrolls=get32(src+1U),
        .wall_us=get32(src+5U),
        .gap_us=get32(src+9U)
    };
    *out=decoded;
    return true;
}
static bool class_fits(const Hw4DpClass *c,const Hw4DpFrame *f)
{
    /* Guard derived bytes before multiplying; accepted samples remain exact. */
    if(c->bands>UINT64_MAX/HW4_DP_BAND_BYTES-f->bands) return false;
    if(c->one_scroll>c->n || c->multi_scroll>c->n-c->one_scroll) return false;
    return c->n<UINT32_MAX && c->bands<=UINT64_MAX-f->bands &&
        fits(c->scrolls,f->scrolls) &&
        fits(c->wall_us,f->wall_us) &&
        fits(c->render_pack_us,f->render_pack_us) &&
        fits(c->submit_us,f->submit_us) && fits(c->wait_us,f->wait_us) &&
        fits(c->scroll_cpu_wall_us,f->scroll_cpu_wall_us) &&
        (f->scrolls==0U ? true :
         f->scrolls==1U ? c->one_scroll<UINT32_MAX :
                           c->multi_scroll<UINT32_MAX);
}
static void class_add(Hw4DpClass *c,const Hw4DpFrame *f)
{
    const uint32_t wall=(f->wall_us>UINT32_MAX)
            ? UINT32_MAX:(uint32_t)f->wall_us;
    unsigned bin=0U;
    while(bin<HW4_DP_BINS-1U && wall>hw4_dp_bounds_us[bin]) ++bin;
    if(c->n==0U || wall<c->min_us) c->min_us=wall;
    if(wall>c->max_us) c->max_us=wall;
    ++c->hist[bin];
    ++c->n;
    c->bands+=f->bands;
    c->scrolls+=f->scrolls;
    if(f->scrolls==1U) ++c->one_scroll;
    else if(f->scrolls>1U) ++c->multi_scroll;
    if(f->scrolls>c->max_scrolls) c->max_scrolls=f->scrolls;
    c->wall_us+=f->wall_us;
    c->render_pack_us+=f->render_pack_us;
    c->submit_us+=f->submit_us;
    c->wait_us+=f->wait_us;
    c->scroll_cpu_wall_us+=f->scroll_cpu_wall_us;
}
bool hw4_dp_record(Hw4DispProfile *p,const Hw4DpFrame *f)
{
    if(p==NULL || f==NULL) return false;
    uint64_t phases=0U;
    if(!fits(f->render_pack_us,f->submit_us)) goto reject;
    phases=f->render_pack_us+f->submit_us;
    if(!fits(phases,f->wait_us)) goto reject;
    phases+=f->wait_us;
    if(f->bands==0U || f->bands>25U || phases>f->wall_us ||
       p->completed==UINT32_MAX ||
       (p->completed && f->completed_us<p->last_completed_us) ||
       !fits(p->gap_sum_us,p->completed
           ? f->completed_us-p->last_completed_us:0U) ||
       (p->completed && p->gaps==UINT32_MAX)) goto reject;
    const unsigned category=f->bands==25U ? HW4_DP_FULL25:HW4_DP_PARTIAL;
    if(!class_fits(&p->classes[category],f) ||
       (f->scrolls && !class_fits(&p->classes[HW4_DP_SCROLL_ASSOCIATED],f)))
        goto reject;
    if(p->completed) {
        const uint64_t gap=f->completed_us-p->last_completed_us;
        const uint32_t g=gap>UINT32_MAX ? UINT32_MAX:(uint32_t)gap;
        if(p->gaps==0U || g<p->gap_min_us) p->gap_min_us=g;
        if(g>p->gap_max_us) p->gap_max_us=g;
        p->gap_sum_us+=gap;
        ++p->gaps;
    }
    const uint64_t gap=p->completed
        ? f->completed_us-p->last_completed_us:0U;
    uint8_t *trace=p->trace[p->trace_next];
    trace[0]=(uint8_t)f->bands;
    put32(trace+1U,f->scrolls);
    put32(trace+5U,f->wall_us>UINT32_MAX ? UINT32_MAX:(uint32_t)f->wall_us);
    put32(trace+9U,gap>UINT32_MAX ? UINT32_MAX:(uint32_t)gap);
    p->trace_next=(p->trace_next+1U)%HW4_DP_TRACE_CAP;
    if(p->trace_size<HW4_DP_TRACE_CAP) ++p->trace_size;
    class_add(&p->classes[category],f);
    if(f->scrolls) class_add(&p->classes[HW4_DP_SCROLL_ASSOCIATED],f);
    ++p->completed;
    p->last_completed_us=f->completed_us;
    return true;
reject:
    if(p->rejected<UINT32_MAX) ++p->rejected;
    return false;
}
uint32_t hw4_dp_quantile_upper(const Hw4DpClass *c,unsigned percentile)
{
    if(c==NULL || c->n==0U || percentile==0U || percentile>100U)
        return 0U;
    const uint64_t rank=((uint64_t)c->n*percentile+99U)/100U;
    uint64_t seen=0U;
    for(unsigned i=0U;i<HW4_DP_BINS;++i) {
        seen+=c->hist[i];
        if(seen>=rank) return hw4_dp_bounds_us[i];
    }
    return UINT32_MAX; /* corrupt histogram, never report an exact quantile */
}
