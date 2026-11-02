/* A1-P1 test: arithmetic model and fail-closed invalid parameters. */
#include "cyd_vscr_probe_policy.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void check(unsigned start)
{
    CydVscrPlan p;
    assert(cyd_vscr_plan(10U,320U,240U,start,&p));
    assert((unsigned)p.tfa+p.vsa+p.bfa==320U);
    const uint8_t a[6]={0,20,0,200,0,100}, b[6]={0,100,0,200,0,20};
    uint8_t bytes[6];
    cyd_vscr_def_bytes(&p,bytes);
    assert(memcmp(bytes,start ? b : a,6U)==0);
    uint16_t off=0U,addr=0U;
    assert(cyd_vscr_advance(off,1,1U,&off) && off==192U);
    assert(cyd_vscr_advance(off,-1,1U,&off) && off==0U);
    for(unsigned i=0;i<25U;++i) assert(cyd_vscr_advance(off,1,1U,&off));
    assert(off==0U);
    assert(cyd_vscr_address(&p,0U,20U,&addr) && addr==p.tfa+199U);
    assert(cyd_vscr_address(&p,0U,219U,&addr) && addr==p.tfa);
    for(unsigned i=0;i<200U;++i) {
        assert(cyd_vscr_address(&p,(uint16_t)i,219U,&addr));
        assert(addr>=p.tfa && addr<(unsigned)p.tfa+p.vsa);
    }
    for(unsigned i=0;i<20U;++i) assert(!cyd_vscr_address(&p,0U,i,&addr));
    for(unsigned i=220U;i<240U;++i) assert(!cyd_vscr_address(&p,0U,i,&addr));
    assert(!cyd_vscr_address(&p,0U,240U,&addr));
    assert(!cyd_vscr_address(&p,200U,50U,&addr));
    assert(!cyd_vscr_advance(0U,0,1U,&off));
    assert(!cyd_vscr_advance(0U,1,0U,&off));
    assert(!cyd_vscr_advance(0U,1,26U,&off));
    assert(!cyd_vscr_advance(200U,1,1U,&off));
}
int main(void)
{
    CydVscrPlan p;
    check(0U); check(80U);
    assert(!cyd_vscr_plan(9U,320U,240U,0U,&p));
    assert(!cyd_vscr_plan(10U,240U,320U,0U,&p));
    assert(!cyd_vscr_plan(10U,320U,239U,0U,&p));
    assert(!cyd_vscr_plan(10U,320U,240U,40U,&p));
    assert(!cyd_vscr_plan(10U,320U,240U,0U,NULL));
    puts("HW4-SCROLL-A1-P1 POLICY PASS two candidates + negative geometry/margins/rows");
    return 0;
}
