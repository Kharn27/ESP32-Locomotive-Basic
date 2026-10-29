#include "hw4_scroll_metrics.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
    Hw4ScrollMetrics m={0};
    assert(sizeof(m)<=256U);
    hw4_scroll_flush(&m,2U,900U,10240U);
    assert(m.cls[0].flushes==1U && m.cls[0].bands==2U);
    hw4_scroll_observe_text(&m,2U);
    hw4_scroll_nav(&m,-1);
    hw4_scroll_flush(&m,25U,130000U,128000U);
    assert(m.cls[1].flushes==1U && m.cls[1].up==2U &&
           m.cls[1].down==1U && m.cls[1].bands==25U);
    assert(m.cls[1].spi_bytes==128000U &&
           hw4_scroll_quantile_upper(&m.cls[1],95U)==256000U);
    hw4_scroll_observe_text(&m,3U);
    hw4_scroll_clear(&m,0U); /* !CLS retains pending event */
    hw4_scroll_observe_text(&m,1U);
    hw4_scroll_flush(&m,25U,150000U,128000U);
    assert(m.resets==1U && m.cls[1].up==4U && m.cls[1].down==1U);
    assert(m.cls[1].reset_tagged==1U && m.cls[1].flushes==2U);
    assert(hw4_scroll_quantile_upper(&m.cls[1],50U)==256000U);
    hw4_scroll_flush(&m,1U,500U,5120U);
    assert(m.cls[0].flushes==2U && m.cls[0].min_us==500U &&
           m.cls[0].max_us==900U);
    assert(m.cls[0].reset_tagged==0U && m.cls[1].reset_tagged==1U);
    hw4_scroll_nav(&m,1);
    hw4_scroll_nav(&m,-1);
    hw4_scroll_flush(&m,25U,600000U,128000U);
    assert(m.cls[1].up==5U && m.cls[1].down==2U);
    assert(m.cls[1].hist[11]==1U && m.cls[1].flushes==3U);
    /* Unexpected reset fails safe against unsigned underflow. */
    hw4_scroll_observe_text(&m,0U);
    assert(m.resets==2U && m.reset_pending==1U);
    hw4_scroll_flush(&m,1U,1000U,5120U);
    assert(m.cls[0].reset_tagged==1U);
    assert(m.cls[1].flushes+m.cls[0].flushes==6U);
    puts("HW4-SCROLL-A0 C99 classification PASS");
    return 0;
}
