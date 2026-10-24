#ifndef BASIC_EXECUTOR_H
#define BASIC_EXECUTOR_H

#include <stddef.h>
#include <stdint.h>
#include "basic_program.h"

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
    BE_OVERLAP
} BEStatus;

typedef struct {
    const BasicProgram *program; /* Borrowed; immutable through execution. */
    size_t cursor;               /* Offset of next record (or sentinel). */
} BasicExecutor;

/* Validate a program and reset execution to its first line.
 * On failure executor remains unmodified. Executor, program metadata and
 * program storage must be disjoint, including unused storage capacity.
 */
BEStatus be_init(BasicExecutor *executor, const BasicProgram *program);

/* Execute at most ONE numbered line. END commits the reached prefix's output
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
