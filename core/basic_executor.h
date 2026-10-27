#ifndef BASIC_EXECUTOR_H
#define BASIC_EXECUTOR_H

#include <stddef.h>
#include <stdint.h>
#include "basic_program.h"
#include "basic_variable_store.h"

/* J0.7 host diagnostics, not Locomotive BASIC error codes. */
typedef enum {
    BE_OK = 0,
    BE_END,
    BE_INVALID_ARGUMENT,
    BE_BAD_PROGRAM,
    BE_TRUNCATED,
    BE_BAD_SEQUENCE,
    BE_UNKNOWN_TOKEN,
    BE_UNSUPPORTED,
    BE_MISSING_TARGET,
    BE_NO_SPACE,
    BE_OVERLAP,
    BE_STORE_FULL,
    BE_INVALID_STORE,
    BE_INVALID_KEY,
    BE_INVALID_TYPE,
    BE_VARIABLE_NOT_FOUND, /* Internal diagnostic, not a CPC error code. */
    BE_INTEGER_OVERFLOW, /* Internal range error; not a CPC numeric code. */
    BE_DIVISION_BY_ZERO /* Internal error, separate from CPC ERR=11. */
} BEStatus;

typedef struct {
    const BasicProgram *program; /* Borrowed; immutable through execution. */
    size_t cursor;               /* Offset of next record (or sentinel). */
    BasicVariableStore *variables; /* Optional borrowed caller-owned store. */
} BasicExecutor;

/* Validate a program and reset execution to its first line.
 * On failure executor remains unmodified. Executor, program metadata and
 * program storage must be disjoint, including unused storage capacity.
 */
BEStatus be_init(BasicExecutor *executor, const BasicProgram *program);
/* Explicit store variant. Does not clear the store; legacy be_init has no
 * store and continues returning BE_UNSUPPORTED for INTEGER assignment. */
BEStatus be_init_with_store(BasicExecutor *executor, const BasicProgram *program,
                            BasicVariableStore *variables);

/* With a store, standalone INTEGER assignments accept a 0..32767
 * immediate (CPC 0E..17, 19, 1A), with optional CPC unary-minus F5,
 * plus only -32768 via exact F5 1F 00 00 00 00 90 (REAL5 payload),
 * or exactly one explicit INTEGER source reference followed by binary
 * CPC F4 (+), F5 (-), F6 (*), F9 (\\) or FB (MOD), then one unsigned
 * decimal byte literal (0..255). J1.7-B additionally permits
 * F4 (+), J1.8-B binary F5 (-), and J1.9-B F6/F9/FB followed
 * by a SECOND explicit INTEGER reference; both sources are read and the
 * result is checked in int32_t before a single successful commit.
 * Unary F5 and binary F5 are distinguished by operand context.
 * A non-representable sum, difference or product returns BE_INTEGER_OVERFLOW.
 * F9 division truncates toward zero; a zero divisor returns the separate
 * BE_DIVISION_BY_ZERO before any division or mutation of the destination.
  * FB MOD uses the C99 int32_t remainder (dividend sign), with the same
  * zero-divisor guard; no floating point and no generic expressions.
 * These are internal status names, NOT historic CPC ERR numeric codes.
 *
 * With a store, PRINT reads existing explicit INTEGER (%) scalars only.
 * Missing variables return BE_VARIABLE_NOT_FOUND; without a store the
 * legacy API still returns BE_UNSUPPORTED. Numeric output is prototype
 * signed decimal + LF, not CPC PRINT formatting.
 *
 * Execute at most ONE numbered line. END commits the reached prefix's output
 * and moves the cursor to the program sentinel; the NEXT be_step returns
 * BE_END. This is the host step protocol, not CPC console timing.
 * BE_OK commits its output and cursor.
 * Output is raw bytes, no NUL, one LF per PRINT. On BE_OK *written is the
 * number of bytes emitted (possibly zero). BE_END and every error preserve
 * the entire output buffer, *written and executor, including the cursor.
 * All pointers are required, even for zero output capacity. Output (its full
 * capacity), written, executor, program and program storage must be disjoint.
 * The program must remain immutable from be_init through every be_step.
 */
BEStatus be_step(BasicExecutor *executor, uint8_t *output,
                 size_t output_capacity, size_t *written);

#endif
