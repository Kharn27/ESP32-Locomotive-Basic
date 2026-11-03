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
static bool class_fits(const Hw4DpClass *c,const Hw4DpFrame *f,
                       uint64_t other)
{
    const uint64_t bytes=(uint64_t)f->bands*HW4_DP_BAND_BYTES;
    return c->n<UINT32_MAX && c->bands<=UINT64_MAX-f->bands &&
        fits(c->bytes,bytes) && fits(c->scrolls,f->scrolls) &&
        fits(c->wall_us,f->wall_us) &&
        fits(c->render_pack_us,f->render_pack_us) &&
        fits(c->submit_us,f->submit_us) && fits(c->wait_us,f->wait_us) &&
        fits(c->other_us,other) &&
        fits(c->scroll_cpu_wall_us,f->scroll_cpu_wall_us) &&
        (f->scrolls==0U ? c->zero_scroll<UINT32_MAX :
         f->scrolls==1U ? c->one_scroll<UINT32_MAX :
                           c->multi_scroll<UINT32_MAX);
}
static void class_add(Hw4DpClass *c,const Hw4DpFrame *f,uint64_t other)
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
    c->bytes+=(uint64_t)f->bands*HW4_DP_BAND_BYTES;
    c->scrolls+=f->scrolls;
    if(f->scrolls==0U) ++c->zero_scroll;
    else if(f->scrolls==1U) ++c->one_scroll;
    else ++c->multi_scroll;
    if(f->scrolls>c->max_scrolls) c->max_scrolls=f->scrolls;
    c->wall_us+=f->wall_us;
    c->render_pack_us+=f->render_pack_us;
    c->submit_us+=f->submit_us;
    c->wait_us+=f->wait_us;
    c->other_us+=other;
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
    const uint64_t other=f->wall_us-phases;
    const unsigned category=f->bands==25U ? HW4_DP_FULL25:HW4_DP_PARTIAL;
    if(!class_fits(&p->classes[category],f,other) ||
       (f->scrolls && !class_fits(&p->classes[HW4_DP_SCROLL_ASSOCIATED],f,other)))
        goto reject;
    if(p->completed) {
        const uint64_t gap=f->completed_us-p->last_completed_us;
        const uint32_t g=gap>UINT32_MAX ? UINT32_MAX:(uint32_t)gap;
        if(p->gaps==0U || g<p->gap_min_us) p->gap_min_us=g;
        if(g>p->gap_max_us) p->gap_max_us=g;
        p->gap_sum_us+=gap;
        ++p->gaps;
    }
    class_add(&p->classes[category],f,other);
    if(f->scrolls) class_add(&p->classes[HW4_DP_SCROLL_ASSOCIATED],f,other);
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
