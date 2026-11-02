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
    BasicVariableStore *variables; /* NULL: legacy runtime, no assignment. */
    BasicExecutor executor;
    BSRState state;
} BasicSessionRuntime;

/* Validate program and initialize IDLE. Any failure preserves runtime.
 * runtime, program descriptor and entire program storage must be disjoint. */
BSRResult bsr_init(BasicSessionRuntime *runtime, BasicProgram *program);
/* Optional variable store; borrowed, never allocated. Store validated but not
 * reset here. A successful RUN or NEW clears it; STOP preserves its values. */
BSRResult bsr_init_with_store(BasicSessionRuntime *runtime, BasicProgram *program,
                              BasicVariableStore *variables);

/* Submit exactly source_length bytes. RUN (any ASCII case, with outer
 * ASCII spaces) validates and resets executor without executing a line.
 * LIST and blank input are allowed during RUNNING. NEW stops execution
 * only after the underlying session successfully clears the program.
 * Numbered edits during RUNNING return BSR_BUSY without side effects.
 *
 * On failure: output, *written, program, runtime remain unchanged; the
 * caller-provided temporary buffer may change if tokenization was reached.
 * When configured, the store descriptor/entries are also disjoint from all
 * argument regions and fully validated before any program mutation.
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

/* Typed portable event step. BEVideoEvent.print_offset preserves relative
 * order with PRINT within a single step. Legacy bsr_step will not silently
 * consume PEN without a receiver. No event or count mutations on failure. */
BSRResult bsr_step_events(BasicSessionRuntime *runtime,
                          uint8_t *output, size_t output_capacity,
                          size_t *written, BEVideoEvent *events,
                          size_t event_capacity, size_t *event_written);

/* B2a: preview of the next RUN step without advancing BSR_RUNNING,
 * executor cursor, GOSUB/FOR stacks or INTEGER/STRING/REAL5 store.
 * On BSR_OK, write output/events/counts only to caller's staging buffers.
 * BSR_END and failures leave counters and all staging/state unchanged.
 * Uses the same validation as bsr_step_events; preview again if any input
 * or caller-owned buffer/capacity changes before commit. The B2b scheduler
 * must compare staged and committed outputs/events before hardware replay
 * and fail-stop on divergence (no physical rollback claim).
 */
BSRResult bsr_preview_step_events(BasicSessionRuntime *runtime,
                                  uint8_t *output, size_t output_capacity,
                                  size_t *written, BEVideoEvent *events,
                                  size_t event_capacity, size_t *event_written);


/* J1.21-C1: pure/direct command preparation for the future C2 host.
 * Recognizes only an idle "CLS" (ASCII case-insensitive, outer spaces);
 * emits exactly one BE_VIDEO_CLEAR_TEXT with print_offset=0, zero PRINT
 * bytes, and sets written=0/event_written=1. This does NOT execute,
 * submit, insert a line, render pixels, or alter any BASIC/store state.
 * Existing bsr_submit keeps its RUN/LIST/NEW and unsupported-direct behavior.
 *
 * All regions (entire buffer capacities, source extent, both counters,
 * BSR/program/store/entries/string arena) must be pairwise disjoint.
 * Valid pointers required even for zero capacities; events may be NULL
 * only with capacity=0. On ANY failure every byte/counter is untouched.
 * BSR_BUSY denotes recognized CLS during RUNNING. Unsupported/malformed
 * direct source returns BSR_SESSION_ERROR with existing BSStatus provenance.
 * Missing event receiver returns BE_EVENT_RECEIVER_REQUIRED; non-NULL
 * events with zero capacity returns BE_NO_EVENT_SPACE.
 * No caller scratch, heap, new persistent state or global variables.
 */
BSRResult bsr_prepare_direct_events(BasicSessionRuntime *runtime,
                                    const uint8_t *source, size_t source_length,
                                    uint8_t *output, size_t output_capacity,
                                    size_t *written, BEVideoEvent *events,
                                    size_t event_capacity, size_t *event_written);

#endif
