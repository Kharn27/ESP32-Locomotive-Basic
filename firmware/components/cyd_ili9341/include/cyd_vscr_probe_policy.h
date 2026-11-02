/* A1-P1: portable geometry checks, not proof of real controller support. MIT. */
#ifndef CYD_VSCR_PROBE_POLICY_H
#define CYD_VSCR_PROBE_POLICY_H
#include <stdbool.h>
#include <stdint.h>
typedef struct { uint16_t tfa, vsa, bfa, visible_start; } CydVscrPlan;
static inline bool cyd_vscr_plan(unsigned orientation, unsigned w, unsigned h,
                                 unsigned start, CydVscrPlan *p)
{
    if (!p || orientation!=10U || w!=320U || h!=240U ||
        (start!=0U && start!=80U)) return false;
    p->visible_start=(uint16_t)start;
    p->tfa=(uint16_t)(start+20U);
    p->vsa=200U;
    p->bfa=(uint16_t)(320U-p->tfa-p->vsa);
    return (unsigned)p->tfa+p->vsa+p->bfa==320U;
}
static inline void cyd_vscr_def_bytes(const CydVscrPlan *p, uint8_t b[6])
{
    const uint16_t v[3]={p->tfa,p->vsa,p->bfa};
    for(unsigned i=0;i<3U;++i) {
        b[i*2U]=(uint8_t)(v[i]>>8U);
        b[i*2U+1U]=(uint8_t)v[i];
    }
}
static inline bool cyd_vscr_advance(uint16_t old,int direction,
                                     unsigned rows,uint16_t *next)
{
    if (!next || old>=200U || (direction!=1 && direction!=-1) ||
        rows==0U || rows>25U) return false;
    const unsigned delta=(rows*8U)%200U;
    *next=(uint16_t)((old+(direction==1 ? 200U-delta : delta))%200U);
    return true;
}
static inline bool cyd_vscr_address(const CydVscrPlan *p,uint16_t offset,
                                    unsigned physical_y,uint16_t *addr)
{
    if (!p || !addr || offset>=200U || physical_y<20U || physical_y>=220U ||
        p->vsa!=200U || (unsigned)p->tfa+p->vsa+p->bfa!=320U ||
        (p->visible_start!=0U && p->visible_start!=80U) ||
        p->tfa!=(unsigned)p->visible_start+20U) return false;
    const unsigned scan=(unsigned)p->visible_start+239U-physical_y;
    if(scan<p->tfa || scan>=(unsigned)p->tfa+p->vsa) return false;
    *addr=(uint16_t)(p->tfa+(scan-p->tfa+offset)%200U);
    return true;
}
#endif
