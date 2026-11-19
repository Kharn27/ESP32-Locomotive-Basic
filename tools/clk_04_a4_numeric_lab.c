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

/* A6: domain is a predicate over the sealed A5 samples, NOT a lookup table
 * of expected printer bytes. Neither the decimal/exponential transition nor
 * round-half-tie policy is known outside these exact input classes. */
static unsigned a6_large_sample_class(uint64_t n) {
    /* A5 proves full decimal digits only for these two large powers of two. */
    if (n == (UINT64_C(1) << 23) || n == (UINT64_C(1) << 24)) return 1u;
    /* A5 proves the scientific form for these powers and boundary products. */
    if (n == (UINT64_C(1) << 31) || n == (UINT64_C(1) << 32) ||
        n == UINT32_MAX || n == UINT64_C(2) * UINT32_MAX) return 2u;
    return 0u;
}

A4Status a4_print_candidate(int64_t value, uint8_t *dst,
                            size_t capacity, size_t *used) {
    uint64_t n, mantissa, divisor;
    uint8_t tmp[32], digits[20];
    size_t count=0u, pos=0u;
    unsigned sample_class=0u, exponent=0u;
    if (!dst || !used) return A4_INVALID;
    if (value < -1) return A4_UNSUPPORTED;
    if (value > INT64_C(999999)) {
        sample_class=a6_large_sample_class((uint64_t)value);
        if (!sample_class) return A4_UNSUPPORTED;
    }
    n = value == -1 ? UINT64_C(1) : (uint64_t)value;
    tmp[pos++]=value < 0 ? (uint8_t)'-' : (uint8_t)' ';
    if (sample_class == 2u) {
        /* All authenticated A5 scientific samples have exponent 9.  Use
         * decimal integer arithmetic for six significant digits, never
         * float/double and never textual values from the ROM capture. */
        divisor=1u;
        while (n / divisor >= 10u) {
            divisor*=10u;
            ++exponent;
        }
        if (exponent != 9u) return A4_UNSUPPORTED;
        divisor/=UINT64_C(100000); /* 10^4 for the observed exponent 9 */
        mantissa=(n + divisor/2u)/divisor;
        if (mantissa < UINT64_C(100000) || mantissa > UINT64_C(999999))
            return A4_UNSUPPORTED;
        tmp[pos++]=(uint8_t)('0'+mantissa/UINT64_C(100000));
        tmp[pos++]=(uint8_t)'.';
        mantissa%=UINT64_C(100000);
        for (divisor=10000u; divisor; divisor/=10u) {
            tmp[pos++]=(uint8_t)('0'+mantissa/divisor);
            mantissa%=divisor;
        }
        tmp[pos++]=(uint8_t)'E';
        tmp[pos++]=(uint8_t)'+';
        tmp[pos++]=(uint8_t)('0'+exponent/10u);
        tmp[pos++]=(uint8_t)('0'+exponent%10u);
    } else {
        do { digits[count++]=(uint8_t)('0'+n%10u); n/=10u; } while(n);
        while(count) tmp[pos++]=digits[--count];
    }
    tmp[pos++]=(uint8_t)' ';
    tmp[pos++]=(uint8_t)'\r';
    tmp[pos++]=(uint8_t)'\n';
    if (capacity < pos) return A4_NO_SPACE;
    memcpy(dst,tmp,pos);
    *used=pos;
    return A4_OK;
}
