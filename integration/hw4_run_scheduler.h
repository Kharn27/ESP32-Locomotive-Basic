/* HW4-RUN-BREAK-A: cooperative host scheduler; no hardware or heap. */
#ifndef HW4_RUN_SCHEDULER_H
#define HW4_RUN_SCHEDULER_H
#include "basic_session_runtime.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* At most 128 BASIC steps per host turn. Owner yields/polls between turns. */
#define HW4_RUN_QUANTUM_MAX 128u
typedef enum {
    HW4_RUN_IDLE = 0, HW4_RUN_RUNNING, HW4_RUN_YIELDED,
    HW4_RUN_BREAK_REQUESTED, HW4_RUN_BROKEN, HW4_RUN_ENDED,
    HW4_RUN_EXECUTOR_ERROR, HW4_RUN_DISPLAY_ERROR, HW4_RUN_INVALID_ARGUMENT
} Hw4RunState;
typedef enum {
    HW4_RUN_DISPLAY_NONE = 0, HW4_RUN_DISPLAY_PREFLIGHT_FAILED,
    HW4_RUN_DISPLAY_REPLAY_FAILED
} Hw4RunDisplayFailure;

/* Mandatory PRECHECK is read-only. REPLAY must consume ordered PRINT slices
 * and PEN/INK events exactly once, using each event's print_offset.
 * Replay failure is fail-stop, as already applied pixels cannot be undone.
 * Callbacks may request BREAK; completed step replay is never interrupted. */
typedef bool (*Hw4RunReceiverFn)(void *ctx, const uint8_t *print_bytes,
                                 size_t length, const BEVideoEvent *events,
                                 size_t count);
/* Optional input poll before each step. Scheduler itself is single-threaded;
 * C99 bool is NOT an ISR/task synchronization primitive. */
typedef bool (*Hw4RunPollBreakFn)(void *ctx);
typedef struct {
    Hw4RunReceiverFn preflight;
    Hw4RunReceiverFn replay;
    Hw4RunPollBreakFn poll_break;
    void *context;
} Hw4RunReceiver;
typedef struct {
    BasicSessionRuntime *runtime; /* borrowed; RUN already submitted */
    Hw4RunState state;
    BSRResult last_result; /* intact for diagnostics before bsr_stop */
    Hw4RunDisplayFailure display_failure;
    size_t total_steps; /* saturating statistic, not a total execution cap */
    unsigned stop_calls;
    bool break_pending;
} Hw4RunScheduler;
typedef struct {
    Hw4RunState state;
    size_t steps; /* BSR_OK calls in this slice */
} Hw4RunSlice;

/* Attach only to RUNNING BSR. For YIELDED, call slice again, not RUN.
 * After BROKEN/ENDED submit a new RUN explicitly and reinitialize. */
bool hw4_run_scheduler_init(Hw4RunScheduler *scheduler,
                            BasicSessionRuntime *runtime);
bool hw4_run_scheduler_request_break(Hw4RunScheduler *scheduler);
/* No mutation on bad quantum/arguments. A valid YIELD never calls bsr_stop.
 * Failed BSR or display status terminates driver without auto-stopping BSR:
 * owner can examine exact PEN error provenance before bsr_stop. */
Hw4RunSlice hw4_run_scheduler_slice(Hw4RunScheduler *scheduler,
                                   size_t quantum, const Hw4RunReceiver *receiver,
                                   uint8_t *output, size_t output_capacity,
                                   size_t *written, BEVideoEvent *events,
                                   size_t event_capacity, size_t *event_written);
#endif
