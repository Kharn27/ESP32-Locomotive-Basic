#include "hw4_run_scheduler.h"
#include <stdint.h>

static Hw4RunSlice outcome(Hw4RunState state, size_t steps)
{
    Hw4RunSlice result = {state, steps};
    return result;
}

bool hw4_run_scheduler_init(Hw4RunScheduler *scheduler,
                            BasicSessionRuntime *runtime)
{
    BSRResult empty = {BSR_OK, {BS_OK, BT_OK, BP_OK, BL_OK}, BE_OK};
    if (scheduler == NULL || runtime == NULL || runtime->program == NULL ||
        runtime->state != BSR_RUNNING) return false;
    scheduler->runtime = runtime;
    scheduler->state = HW4_RUN_RUNNING;
    scheduler->last_result = empty;
    scheduler->display_failure = HW4_RUN_DISPLAY_NONE;
    scheduler->total_steps = 0u;
    scheduler->stop_calls = 0u;
    scheduler->break_pending = false;
    return true;
}

bool hw4_run_scheduler_request_break(Hw4RunScheduler *scheduler)
{
    if (scheduler == NULL ||
        (scheduler->state != HW4_RUN_RUNNING &&
         scheduler->state != HW4_RUN_YIELDED &&
         scheduler->state != HW4_RUN_BREAK_REQUESTED)) return false;
    scheduler->break_pending = true;
    scheduler->state = HW4_RUN_BREAK_REQUESTED;
    return true;
}

static bool arguments_ok(const Hw4RunScheduler *scheduler, size_t quantum,
                         const Hw4RunReceiver *receiver,
                         const uint8_t *output, const size_t *written,
                         const BEVideoEvent *events, size_t event_capacity,
                         const size_t *event_written)
{
    return scheduler != NULL && scheduler->runtime != NULL &&
           scheduler->runtime->program != NULL &&
           scheduler->runtime->state == BSR_RUNNING &&
           (scheduler->state == HW4_RUN_RUNNING ||
            scheduler->state == HW4_RUN_YIELDED ||
            scheduler->state == HW4_RUN_BREAK_REQUESTED) &&
           quantum > 0u && quantum <= HW4_RUN_QUANTUM_MAX &&
           receiver != NULL && receiver->preflight != NULL &&
           receiver->replay != NULL && output != NULL && written != NULL &&
           event_written != NULL &&
           (events != NULL || event_capacity == 0u) &&
           event_capacity <= SIZE_MAX / sizeof(*events);
}

Hw4RunSlice hw4_run_scheduler_slice(Hw4RunScheduler *scheduler,
                                   size_t quantum, const Hw4RunReceiver *receiver,
                                   uint8_t *output, size_t output_capacity,
                                   size_t *written, BEVideoEvent *events,
                                   size_t event_capacity, size_t *event_written)
{
    size_t steps = 0u;
    if (!arguments_ok(scheduler, quantum, receiver, output, written,
                      events, event_capacity, event_written))
        return outcome(HW4_RUN_INVALID_ARGUMENT, 0u);

    scheduler->state = scheduler->break_pending ? HW4_RUN_BREAK_REQUESTED
                                                : HW4_RUN_RUNNING;
    while (steps < quantum) {
        BSRResult step;
        if (receiver->poll_break != NULL &&
            receiver->poll_break(receiver->context))
            (void)hw4_run_scheduler_request_break(scheduler);
        if (scheduler->break_pending) {
            scheduler->last_result = bsr_stop(scheduler->runtime);
            ++scheduler->stop_calls;
            scheduler->state = scheduler->last_result.status == BSR_OK
                                 ? HW4_RUN_BROKEN : HW4_RUN_EXECUTOR_ERROR;
            scheduler->break_pending = false;
            return outcome(scheduler->state, steps);
        }
        step = bsr_step_events(scheduler->runtime, output, output_capacity,
                               written, events, event_capacity, event_written);
        scheduler->last_result = step;
        if (step.status == BSR_END) {
            scheduler->state = HW4_RUN_ENDED;
            return outcome(HW4_RUN_ENDED, steps);
        }
        if (step.status != BSR_OK) {
            /* BSR_INVALID_ARGUMENT and BSR_OVERLAP are host contracts,
             * never BASIC faults or CPC ERR/ERL. Keep original BSRResult
             * intact and never stop/reset: caller owns diagnosis/recovery. */
            if (step.status == BSR_INVALID_ARGUMENT ||
                step.status == BSR_OVERLAP) {
                scheduler->state = HW4_RUN_INVALID_ARGUMENT;
                return outcome(HW4_RUN_INVALID_ARGUMENT, steps);
            }
            /* Genuine executor failure: retain RUNNING + cursor for #195. */
            scheduler->state = HW4_RUN_EXECUTOR_ERROR;
            return outcome(HW4_RUN_EXECUTOR_ERROR, steps);
        }
        ++steps;
        if (scheduler->total_steps != SIZE_MAX) ++scheduler->total_steps;
        if (!receiver->preflight(receiver->context, output, *written,
                                 events, *event_written)) {
            scheduler->display_failure = HW4_RUN_DISPLAY_PREFLIGHT_FAILED;
            scheduler->state = HW4_RUN_DISPLAY_ERROR;
            return outcome(HW4_RUN_DISPLAY_ERROR, steps);
        }
        if (!receiver->replay(receiver->context, output, *written,
                              events, *event_written)) {
            scheduler->display_failure = HW4_RUN_DISPLAY_REPLAY_FAILED;
            scheduler->state = HW4_RUN_DISPLAY_ERROR;
            return outcome(HW4_RUN_DISPLAY_ERROR, steps);
        }
        /* BREAK during replay is handled before the following BASIC step. */
    }
    if (scheduler->break_pending) {
        scheduler->last_result = bsr_stop(scheduler->runtime);
        ++scheduler->stop_calls;
        scheduler->state = scheduler->last_result.status == BSR_OK
                             ? HW4_RUN_BROKEN : HW4_RUN_EXECUTOR_ERROR;
        scheduler->break_pending = false;
        return outcome(scheduler->state, steps);
    }
    scheduler->state = HW4_RUN_YIELDED;
    return outcome(HW4_RUN_YIELDED, steps);
}
