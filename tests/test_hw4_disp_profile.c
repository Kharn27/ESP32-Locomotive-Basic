/* HW4-DISP-PROFILE-A: logical classification and fail-safe accounting. MIT. */
#include "hw4_disp_profile.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
static Hw4DpFrame frame(unsigned bands,unsigned scrolls,uint64_t end)
{
    Hw4DpFrame f={0};
    f.bands=bands; f.scrolls=scrolls; f.completed_us=end;
    f.render_pack_us=(uint64_t)bands*200U;
    f.submit_us=(uint64_t)bands*100U;
    f.wait_us=(uint64_t)bands*500U;
    f.wall_us=(uint64_t)bands*1000U;
    f.scroll_cpu_wall_us=(uint64_t)scrolls*300U;
    return f;
}
int main(void)
{
    Hw4DispProfile p;
    hw4_dp_reset(&p);
    assert(p.completed==0U && hw4_dp_quantile_upper(&p.classes[0],50U)==0U);
    /* 3 logical scrolls with zero flush: no synthetic frame. */
    assert(p.completed==0U);
    Hw4DpFrame f=frame(25U,3U,100000U);
    assert(hw4_dp_record(&p,&f));
    assert(p.completed==1U && p.classes[HW4_DP_FULL25].n==1U);
    assert(p.classes[HW4_DP_SCROLL_ASSOCIATED].n==1U);
    assert(p.classes[HW4_DP_FULL25].multi_scroll==1U);
    assert(p.classes[HW4_DP_FULL25].bytes==128000U);
    assert(p.classes[HW4_DP_FULL25].other_us==5000U);
    /* One flush after one scroll, then a partial repaint with no scroll. */
    f=frame(3U,1U,140000U);
    assert(hw4_dp_record(&p,&f));
    f=frame(1U,0U,146000U);
    assert(hw4_dp_record(&p,&f));
    assert(p.completed==3U && p.gaps==2U && p.gap_sum_us==46000U);
    assert(p.trace_size==3U && p.trace[0].scrolls==3U &&
           p.trace[1].gap_us==40000U && p.trace[2].scrolls==0U);
    assert(p.classes[HW4_DP_PARTIAL].n==2U);
    assert(p.classes[HW4_DP_SCROLL_ASSOCIATED].n==2U);
    assert(p.classes[HW4_DP_PARTIAL].one_scroll==1U);
    assert(p.classes[HW4_DP_PARTIAL].zero_scroll==1U);
    assert(p.classes[HW4_DP_FULL25].scrolls==3U);
    assert(hw4_dp_quantile_upper(&p.classes[HW4_DP_FULL25],50U)==32000U);
    assert(hw4_dp_quantile_upper(&p.classes[HW4_DP_FULL25],95U)==32000U);
    assert(hw4_dp_quantile_upper(&p.classes[HW4_DP_PARTIAL],50U)==1000U);
    assert(hw4_dp_quantile_upper(&p.classes[HW4_DP_PARTIAL],95U)==4000U);
    assert(hw4_dp_quantile_upper(&p.classes[HW4_DP_PARTIAL],0U)==0U);
    assert(hw4_dp_quantile_upper(&p.classes[HW4_DP_PARTIAL],101U)==0U);
    /* Rejected samples do not change any successful aggregate. */
    Hw4DispProfile prior=p;
    f=frame(0U,0U,170000U);
    assert(!hw4_dp_record(&p,&f));
    f=frame(26U,0U,170000U);
    assert(!hw4_dp_record(&p,&f));
    f=frame(1U,0U,145999U);
    assert(!hw4_dp_record(&p,&f));
    f=frame(1U,0U,170000U); f.wall_us=1U;
    assert(!hw4_dp_record(&p,&f));
    assert(p.completed==prior.completed && p.gaps==prior.gaps &&
           p.classes[HW4_DP_PARTIAL].n==prior.classes[HW4_DP_PARTIAL].n);
    assert(p.rejected==prior.rejected+4U);
    /* Sum overflow is detected before mutating the class. */
    hw4_dp_reset(&p);
    p.classes[HW4_DP_FULL25].wall_us=UINT64_MAX;
    f=frame(25U,0U,100U);
    assert(!hw4_dp_record(&p,&f) && p.completed==0U);
    hw4_dp_reset(&p);
    p.completed=UINT32_MAX;
    assert(!hw4_dp_record(&p,&f));
    /* Exact histogram inclusivity at a bound, and saturating final bin. */
    hw4_dp_reset(&p);
    f=frame(1U,0U,1U); f.wall_us=500U; f.render_pack_us=0U;
    f.submit_us=0U; f.wait_us=0U;
    assert(hw4_dp_record(&p,&f));
    assert(hw4_dp_quantile_upper(&p.classes[HW4_DP_PARTIAL],50U)==500U);
    hw4_dp_reset(&p);
    f=frame(25U,0U,1U); f.wall_us=UINT64_C(10000000000);
    assert(hw4_dp_record(&p,&f));
    assert(hw4_dp_quantile_upper(&p.classes[HW4_DP_FULL25],95U)==UINT32_MAX);
    hw4_dp_reset(&p);
    for(unsigned i=1U;i<=20U;++i) {
        f=frame(1U,i%3U,(uint64_t)i*5000U);
        assert(hw4_dp_record(&p,&f));
    }
    assert(p.completed==20U && p.trace_size==HW4_DP_TRACE_CAP);
    assert(p.trace_next==4U && p.trace[4].seq==5U);
    assert(p.trace[3].seq==20U);
    puts("HW4-DISP-PROFILE-A host accounting PASS");
    return 0;
}
