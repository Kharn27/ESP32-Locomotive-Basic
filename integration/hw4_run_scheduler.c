#include "hw4_run_scheduler.h"
#include <stdint.h>
#include <string.h>

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
    scheduler->preview = NULL;
    return true;
}

bool hw4_run_scheduler_bind_preview(Hw4RunScheduler *scheduler,
                                    Hw4RunPreview *preview)
{
    if (scheduler == NULL || preview == NULL ||
        scheduler->runtime == NULL ||
        (scheduler->state != HW4_RUN_RUNNING &&
         scheduler->state != HW4_RUN_YIELDED) ||
        preview->output == NULL || preview->output_capacity == 0u ||
        (preview->events == NULL && preview->event_capacity != 0u) ||
        preview->event_capacity > SIZE_MAX / sizeof(BEVideoEvent))
        return false;
    scheduler->preview = preview;
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
                         const uint8_t *output,
                         const size_t *written,
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
           event_capacity <= SIZE_MAX / sizeof(*events) &&
           scheduler->preview != NULL &&
           scheduler->preview->output != NULL &&
           scheduler->preview->output_capacity != 0u &&
           (scheduler->preview->events != NULL ||
            scheduler->preview->event_capacity == 0u) &&
           scheduler->preview->event_capacity <= SIZE_MAX / sizeof(*events);
}

/* The preview validates its OWN scratch; it cannot validate the public
 * destination regions, which must still be disjoint before preflight.
 * Mirror the BSR public-region overlap contract WITHOUT writing there. */
typedef struct {
    const void *pointer;
    size_t length;
} Hw4RunRegion;

static bool regions_overlap(Hw4RunRegion a, Hw4RunRegion b)
{
    if (a.length == 0u || b.length == 0u) return false;
#if defined(UINTPTR_MAX)
    {
        const uintptr_t x = (uintptr_t)a.pointer, y = (uintptr_t)b.pointer;
        return x <= y ? y - x < a.length : x - y < b.length;
    }
#else
    (void)a;
    (void)b;
    return false; /* same C99 portability contract as BSR */
#endif
}

static bool public_overlap(const Hw4RunScheduler *scheduler,
                           const uint8_t *output, size_t output_capacity,
                           const size_t *written, const BEVideoEvent *events,
                           size_t event_capacity, const size_t *event_written)
{
    Hw4RunRegion parts[15];
    size_t n = 0u, i, j;
    const BasicSessionRuntime *runtime = scheduler->runtime;
    const Hw4RunPreview *preview = scheduler->preview;
    const BasicProgram *p = runtime->program;
    const BasicVariableStore *v = runtime->variables;
    if (p == NULL || p->data == NULL) return false; /* BSR reports invalid */
    parts[n++] = (Hw4RunRegion){runtime, sizeof(*runtime)};
    parts[n++] = (Hw4RunRegion){p, sizeof(*p)};
    parts[n++] = (Hw4RunRegion){p->data, p->capacity};
    parts[n++] = (Hw4RunRegion){output, output_capacity};
    parts[n++] = (Hw4RunRegion){written, sizeof(*written)};
    parts[n++] = (Hw4RunRegion){events, event_capacity * sizeof(*events)};
    parts[n++] = (Hw4RunRegion){event_written, sizeof(*event_written)};
    parts[n++] = (Hw4RunRegion){scheduler, sizeof(*scheduler)};
    parts[n++] = (Hw4RunRegion){preview->output, preview->output_capacity};
    parts[n++] = (Hw4RunRegion){preview->events,
                               preview->event_capacity * sizeof(*preview->events)};
    parts[n++] = (Hw4RunRegion){&preview->written, sizeof(preview->written)};
    parts[n++] = (Hw4RunRegion){&preview->event_written,
                               sizeof(preview->event_written)};
    if (v != NULL) {
        if (v->capacity > SIZE_MAX / sizeof(BasicVariableEntry))
            return false; /* BSR validates invalid store separately */
        parts[n++] = (Hw4RunRegion){v, sizeof(*v)};
        parts[n++] = (Hw4RunRegion){v->entries,
                                   v->capacity * sizeof(BasicVariableEntry)};
        parts[n++] = (Hw4RunRegion){v->string_arena, v->string_capacity};
    }
    for (i = 0u; i < n; ++i)
        for (j = i + 1u; j < n; ++j)
            if (regions_overlap(parts[i], parts[j])) return true;
    return false;
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

    if (public_overlap(scheduler, output, output_capacity,
                       written, events, event_capacity, event_written)) {
        BSRResult overlap = {BSR_OVERLAP, {BS_OK, BT_OK, BP_OK, BL_OK}, BE_OK};
        scheduler->last_result = overlap;
        scheduler->state = HW4_RUN_INVALID_ARGUMENT;
        return outcome(HW4_RUN_INVALID_ARGUMENT, 0u);
    }
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
        /* Stage on B2a's side-effect-free executor before asking VIDEO.
         * Neither output nor events (nor their public lengths) are touched. */
        Hw4RunPreview *preview = scheduler->preview;
        const size_t preview_output_capacity =
            output_capacity < preview->output_capacity ?
                output_capacity : preview->output_capacity;
        const size_t preview_event_capacity =
            event_capacity < preview->event_capacity ?
                event_capacity : preview->event_capacity;
        step = bsr_preview_step_events(
            scheduler->runtime, preview->output, preview_output_capacity,
            &preview->written, preview->events, preview_event_capacity,
            &preview->event_written);
        scheduler->last_result = step;
        if (step.status == BSR_END) {
            /* Only commit advances RUNNING -> IDLE; no video for END. */
            BSRResult end = bsr_step_events(scheduler->runtime, output,
                                            output_capacity, written, events,
                                            event_capacity, event_written);
            scheduler->last_result = end;
            if (end.status != BSR_END || end.executor_status != step.executor_status) {
                scheduler->display_failure = HW4_RUN_DISPLAY_COMMIT_MISMATCH;
                scheduler->state = HW4_RUN_DISPLAY_ERROR;
                return outcome(HW4_RUN_DISPLAY_ERROR, steps);
            }
            scheduler->state = HW4_RUN_ENDED;
            return outcome(HW4_RUN_ENDED, steps);
        }
        if (step.status != BSR_OK) {
            /* Preview faults preserve the public buffers and BASIC state.
             * Keep original provenance (in particular BSR_OVERLAP). */
            if (step.status == BSR_INVALID_ARGUMENT ||
                step.status == BSR_OVERLAP) {
                scheduler->state = HW4_RUN_INVALID_ARGUMENT;
                return outcome(HW4_RUN_INVALID_ARGUMENT, steps);
            }
            scheduler->state = HW4_RUN_EXECUTOR_ERROR;
            return outcome(HW4_RUN_EXECUTOR_ERROR, steps);
        }
        if (!receiver->preflight(receiver->context,
                                 preview->output,
                                 preview->written,
                                 preview->events,
                                 preview->event_written)) {
            scheduler->display_failure = HW4_RUN_DISPLAY_PREFLIGHT_FAILED;
            scheduler->state = HW4_RUN_DISPLAY_ERROR;
            return outcome(HW4_RUN_DISPLAY_ERROR, steps);
        }
        /* One serialized commit: callbacks are pure and may not change
         * borrowed BASIC state between preview and commit. */
        {
            const size_t preview_bytes = preview->written;
            const size_t preview_events = preview->event_written;
            size_t j;
            bool same;
            step = bsr_step_events(scheduler->runtime, output, output_capacity,
                                   written, events, event_capacity, event_written);
            scheduler->last_result = step;
            same = step.status == BSR_OK && step.executor_status == BE_OK &&
                   *written == preview_bytes && *event_written == preview_events;
            if (same && preview_bytes != 0u)
                same = memcmp(output, preview->output, preview_bytes) == 0;
            for (j = 0u; same && j < preview_events; ++j) {
                const BEVideoEvent *a = &events[j];
                const BEVideoEvent *b = &preview->events[j];
                same = a->type == b->type && a->pen == b->pen &&
                       a->print_offset == b->print_offset &&
                       a->ink == b->ink && a->colour == b->colour;
            }
            if (!same) {
                scheduler->display_failure = HW4_RUN_DISPLAY_COMMIT_MISMATCH;
                scheduler->state = HW4_RUN_DISPLAY_ERROR;
                return outcome(HW4_RUN_DISPLAY_ERROR, steps);
            }
        }
        ++steps; /* only successful verified commits count */
        if (scheduler->total_steps != SIZE_MAX) ++scheduler->total_steps;
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
