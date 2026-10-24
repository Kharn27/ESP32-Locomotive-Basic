#ifndef BASIC_SESSION_RUNTIME_H
#define BASIC_SESSION_RUNTIME_H

#include <stddef.h>
#include <stdint.h>

#include "basic_executor.h"
#include "basic_session.h"

/* Host-side orchestration diagnostics. The nested fields preserve the
 * complete BSResult or BEStatus whenever their module reports an error.
 * These are not historical CPC ROM error numbers. */
typedef enum {
    BSR_OK = 0,
    BSR_END,
    BSR_NOT_RUNNING,
    BSR_BUSY,
    BSR_INVALID_ARGUMENT,
    BSR_OVERLAP,
    BSR_SESSION_ERROR,
    BSR_EXECUTOR_ERROR
} BSRStatus;

typedef enum {
    BSR_IDLE = 0,
    BSR_RUNNING
} BSRState;

typedef struct {
    BSRStatus status;
    BSResult session;
    BEStatus executor_status;
} BSRResult;

/* Stack/static-instantiable, caller owned; program and its storage are
 * borrowed. Do not modify the public fields except via bsr_* calls. */
typedef struct BasicSessionRuntime {
    BasicProgram *program;
    BasicExecutor executor;
    BSRState state;
} BasicSessionRuntime;

/* Validate program and initialize IDLE. Any failure preserves runtime.
 * runtime, program descriptor and entire program storage must be disjoint. */
BSRResult bsr_init(BasicSessionRuntime *runtime, BasicProgram *program);

/* Submit exactly source_length bytes. RUN (any ASCII case, with outer
 * ASCII spaces) validates and resets executor without executing a line.
 * LIST and blank input are allowed during RUNNING. NEW stops execution
 * only after the underlying session successfully clears the program.
 * Numbered edits during RUNNING return BSR_BUSY without side effects.
 *
 * On failure: output, *written, program, runtime remain unchanged; the
 * caller-provided temporary buffer may change if tokenization was reached.
 * All full-capacity regions (runtime descriptor, program descriptor,
 * program storage, source, temporary, output and *written) must be pairwise
 * disjoint. Non-NULL pointers are required even for zero capacities.
 */
BSRResult bsr_submit(BasicSessionRuntime *runtime,
                     const uint8_t *source, size_t source_length,
                     uint8_t *temporary, size_t temporary_capacity,
                     uint8_t *output, size_t output_capacity,
                     size_t *written);

/* Call be_step at most once. BSR_OK handles one BASIC line. BSR_END
 * transitions to IDLE, preserving output and *written on that call.
 * An executor error preserves RUNNING, cursor, output and *written;
 * the caller can retry (e.g. with a larger output) or explicitly stop.
 * No execution takes place when idle. */
BSRResult bsr_step(BasicSessionRuntime *runtime,
                   uint8_t *output, size_t output_capacity,
                   size_t *written);

/* Idempotent; drops RUNNING without touching stored BASIC lines. */
BSRResult bsr_stop(BasicSessionRuntime *runtime);

#endif
