#include "clk_04_a4_numeric_lab.h"
#include <limits.h>
#include <string.h>

A4Status a4_integer_to_real5(uint64_t value, uint8_t out[5]) {
    uint64_t adjusted, fraction;
    unsigned k = 0u, shift;
    uint8_t temp[5];
    if (!out) return A4_INVALID;
    if (value > UINT64_C(8589934590)) return A4_UNSUPPORTED;
    if (value == 0u) { memset(out, 0, 5); return A4_OK; }
    adjusted = value;
    while (adjusted > 1u) { adjusted >>= 1u; ++k; }
    if (k > 32u) return A4_UNSUPPORTED;
    shift = (k >= 31u) ? 0u : 31u-k;
    if (k > 31u) {
        if (value & UINT64_C(1)) return A4_UNSUPPORTED;
        adjusted = value >> 1u;
        fraction = adjusted - UINT64_C(0x80000000);
    } else {
        adjusted = value << shift; /* <= 0xffffffff */
        fraction = adjusted - UINT64_C(0x80000000);
    }
    if (fraction > UINT64_C(0x7fffffff)) return A4_UNSUPPORTED;
    for (unsigned i=0u; i<4u; ++i) temp[i]=(uint8_t)(fraction >> (8u*i));
    temp[4]=(uint8_t)(0x81u+k);
    memcpy(out,temp,sizeof temp);
    return A4_OK;
}

A4Status a4_times_two(uint32_t value, uint64_t *result) {
    if (!result) return A4_INVALID;
    *result=(uint64_t)value * UINT64_C(2);
    return A4_OK;
}
A4Status a4_ge_zero(uint32_t value, int *result) {
    (void)value;
    if (!result) return A4_INVALID;
    *result=-1; /* candidate CPC relation */
    return A4_OK;
}
A4Status a4_gt_32767(uint32_t value, int *result) {
    if (!result) return A4_INVALID;
    *result=value > UINT32_C(32767) ? -1 : 0;
    return A4_OK;
}
A4Status a4_print_candidate(int64_t value, uint8_t *dst,
                            size_t capacity, size_t *used) {
    uint64_t n;
    uint8_t tmp[32], digits[20];
    size_t count=0u, pos=0u;
    if (!dst || !used) return A4_INVALID;
    if (value < -1 || value > INT64_C(999999)) return A4_UNSUPPORTED;
    n = value == -1 ? UINT64_C(1) : (uint64_t)value;
    do { digits[count++]=(uint8_t)('0' + n%10u); n/=10u; } while(n);
    tmp[pos++]=value < 0 ? (uint8_t)'-' : (uint8_t)' ';
    while(count) tmp[pos++]=digits[--count];
    tmp[pos++]=(uint8_t)' ';
    tmp[pos++]=(uint8_t)'\r';
    tmp[pos++]=(uint8_t)'\n';
    if (capacity < pos) return A4_NO_SPACE;
    memcpy(dst,tmp,pos);
    *used=pos;
    return A4_OK;
}
