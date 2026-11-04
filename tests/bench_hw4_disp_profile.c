/* HW4-DISP-PROFILE-A: host-only measurement, never claimed as ESP32 cycles. */
#define _POSIX_C_SOURCE 200809L
#include "hw4_disp_profile.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
static uint64_t ns(void)
{
    struct timespec t={0};
    int rc=clock_gettime(CLOCK_MONOTONIC,&t);
    assert(rc==0);
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}
int main(void)
{
    enum { N=50000 };
    volatile uint32_t sink=0U;
    const uint64_t a=ns();
    for(uint32_t i=0U;i<N;++i) sink+=(i&1U);
    const uint64_t b=ns();
    Hw4DispProfile p={0};
    Hw4DpFrame f={0};
    f.bands=25U; f.wall_us=180000U;
    f.render_pack_us=50000U; f.submit_us=15000U;
    f.wait_us=110000U;
    const uint64_t c=ns();
    for(uint32_t i=0U;i<N;++i) {
        f.completed_us=(uint64_t)(i+1U)*200000U;
        if(!hw4_dp_record(&p,&f)) return 1;
        sink+=(i&1U);
    }
    const uint64_t d=ns();
    assert(p.completed==N && p.classes[HW4_DP_FULL25].n==N);
    printf("HW4-DISP-PROFILE HOST_OVERHEAD_ESTIMATE n=%u baseline_ns=%llu "
           "record_loop_ns=%llu net_ns_per_record=%llu "
           "scope=host_instrumentation_only not_esp32_cpu=1 sink=%u\n",
           N,(unsigned long long)(b-a),(unsigned long long)(d-c),
           (unsigned long long)((d-c>b-a ? (d-c)-(b-a):0U)/N),
           (unsigned)sink);
    return 0;
}
