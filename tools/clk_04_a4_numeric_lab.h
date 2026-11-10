#ifndef CLK_04_A4_NUMERIC_LAB_H
#define CLK_04_A4_NUMERIC_LAB_H
/* Experimental host-only lab: not a production REAL5 codec. C99. */
#include <stddef.h>
#include <stdint.h>
typedef enum {
    A4_OK = 0, A4_UNSUPPORTED = 1, A4_INVALID = 2, A4_NO_SPACE = 3
} A4Status;
/* Nonnegative integer samples, max 2*UINT32_MAX, exact 32-bit significand.
 * Five-byte destination remains untouched on error. */
A4Status a4_integer_to_real5(uint64_t value, uint8_t out[5]);
A4Status a4_times_two(uint32_t value, uint64_t *result);
A4Status a4_ge_zero(uint32_t value, int *result);
A4Status a4_gt_32767(uint32_t value, int *result);
/* Speculative PRINT-only candidate; NOT CPC evidence or general formatter.
 * -1..999999 only, byte buffer remains untouched on all failures. */
A4Status a4_print_candidate(int64_t value, uint8_t *dst,
                            size_t capacity, size_t *used);
#endif
