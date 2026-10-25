#include "basic_session_runtime.h"

#include <stdint.h>

static BSRResult result(BSRStatus status, BSResult session, BEStatus executor)
{
    BSRResult r = {status, session, executor};
    return r;
}

static BSRResult simple(BSRStatus status)
{
    BSResult s = {BS_OK, BT_OK, BP_OK, BL_OK};
    return result(status, s, BE_OK);
}

static BSRResult from_session(BSResult status)
{
    return result(status.status == BS_OK ? BSR_OK : BSR_SESSION_ERROR,
                  status, BE_OK);
}

static BSRResult from_executor(BEStatus status)
{
    BSResult s = {BS_OK, BT_OK, BP_OK, BL_OK};
    return result(BSR_EXECUTOR_ERROR, s, status);
}

/* Relational comparisons of unrelated pointers are undefined in C99.
 * Linux and ESP32 expose uintptr_t. Otherwise disjointness is contractual. */
static int overlaps(const void *a, size_t an, const void *b, size_t bn)
{
    if (an == 0u || bn == 0u) {
        return 0;
    }
#if defined(UINTPTR_MAX)
    {
        uintptr_t x = (uintptr_t)a;
        uintptr_t y = (uintptr_t)b;
        return x <= y ? y - x < an : x - y < bn;
    }
#else
    (void)a;
    (void)b;
    return 0;
#endif
}

static int submit_overlap(const BasicSessionRuntime *runtime,
                          const uint8_t *source, size_t source_length,
                          const uint8_t *temporary, size_t temporary_capacity,
                          const uint8_t *output, size_t output_capacity,
                          const size_t *written)
{
    const void *parts[9];
    size_t lengths[9];
    size_t count = runtime->variables == NULL ? 7u : 9u;
    size_t i, j;
    parts[0] = runtime;
    lengths[0] = sizeof(*runtime);
    parts[1] = runtime->program;
    lengths[1] = sizeof(*runtime->program);
    parts[2] = runtime->program->data;
    lengths[2] = runtime->program->capacity;
    parts[3] = source;
    lengths[3] = source_length;
    parts[4] = temporary;
    lengths[4] = temporary_capacity;
    parts[5] = output;
    lengths[5] = output_capacity;
    parts[6] = written;
    lengths[6] = sizeof(*written);
    if (runtime->variables != NULL) {
        parts[7] = runtime->variables;
        lengths[7] = sizeof(*runtime->variables);
        parts[8] = runtime->variables->entries;
        lengths[8] = runtime->variables->capacity * sizeof(BasicVariableEntry);
    }
    for (i = 0u; i < count; ++i) {
        for (j = i + 1u; j < count; ++j) {
            if (overlaps(parts[i], lengths[i], parts[j], lengths[j])) {
                return 1;
            }
        }
    }
    return 0;
}

static int step_overlap(const BasicSessionRuntime *runtime,
                        const uint8_t *output, size_t capacity,
                        const size_t *written)
{
    const BasicProgram *program = runtime->program;
    return overlaps(runtime, sizeof(*runtime), program, sizeof(*program)) ||
           overlaps(runtime, sizeof(*runtime), program->data, program->capacity) ||
           overlaps(program, sizeof(*program), program->data, program->capacity) ||
           overlaps(output, capacity, runtime, sizeof(*runtime)) ||
           overlaps(output, capacity, program, sizeof(*program)) ||
           overlaps(output, capacity, program->data, program->capacity) ||
           overlaps(written, sizeof(*written), runtime, sizeof(*runtime)) ||
           overlaps(written, sizeof(*written), program, sizeof(*program)) ||
           overlaps(written, sizeof(*written), program->data, program->capacity) ||
           overlaps(written, sizeof(*written), output, capacity) ||
           (runtime->variables != NULL &&
           (overlaps(runtime, sizeof(*runtime), runtime->variables, sizeof(*runtime->variables)) ||
            overlaps(runtime, sizeof(*runtime), runtime->variables->entries,
                     runtime->variables->capacity * sizeof(BasicVariableEntry)) ||
            overlaps(output, capacity, runtime->variables, sizeof(*runtime->variables)) ||
            overlaps(output, capacity, runtime->variables->entries,
                     runtime->variables->capacity * sizeof(BasicVariableEntry)) ||
            overlaps(written, sizeof(*written), runtime->variables, sizeof(*runtime->variables)) ||
            overlaps(written, sizeof(*written), runtime->variables->entries,
                     runtime->variables->capacity * sizeof(BasicVariableEntry))));
}

static uint8_t upper(uint8_t c)
{
    return c >= (uint8_t)'a' && c <= (uint8_t)'z'
        ? (uint8_t)(c - (uint8_t)'a' + (uint8_t)'A') : c;
}

static int command_is(const uint8_t *s, size_t length, const char *literal)
{
    size_t i = 0u;
    while (literal[i] != '\0') {
        if (i >= length || upper(s[i]) != (uint8_t)literal[i]) {
            return 0;
        }
        ++i;
    }
    return i == length;
}

/* Store diagnostics remain in the executor namespace, not CPC codes. */
static BEStatus bsr_store_error(BVSStatus status)
{
    switch (status) {
        case BVS_OK: return BE_OK;
        case BVS_FULL: return BE_STORE_FULL;
        case BVS_INVALID_KEY: return BE_INVALID_KEY;
        case BVS_INVALID_TYPE: return BE_INVALID_TYPE;
        case BVS_OVERLAPPING_MEMORY: return BE_OVERLAP;
        default: return BE_INVALID_STORE;
    }
}

BSRResult bsr_init_with_store(BasicSessionRuntime *runtime, BasicProgram *program,
                              BasicVariableStore *variables)
{
    BasicExecutor candidate;
    BEStatus status;
    if (runtime == NULL || program == NULL || program->data == NULL) {
        return simple(BSR_INVALID_ARGUMENT);
    }
    if (variables != NULL) {
        status = bsr_store_error(bvs_validate(variables));
        if (status != BE_OK) {
            return from_executor(status);
        }
        if (overlaps(runtime, sizeof(*runtime), variables, sizeof(*variables)) ||
            overlaps(runtime, sizeof(*runtime), variables->entries,
                     variables->capacity * sizeof(BasicVariableEntry))) {
            return simple(BSR_OVERLAP);
        }
    }
    if (overlaps(runtime, sizeof(*runtime), program, sizeof(*program)) ||
        overlaps(runtime, sizeof(*runtime), program->data, program->capacity) ||
        overlaps(program, sizeof(*program), program->data, program->capacity)) {
        return simple(BSR_OVERLAP);
    }
    status = be_init_with_store(&candidate, program, variables);
    if (status != BE_OK) {
        return from_executor(status);
    }
    runtime->program = program;
    runtime->variables = variables;
    runtime->executor = candidate;
    runtime->state = BSR_IDLE;
    return simple(BSR_OK);
}

BSRResult bsr_init(BasicSessionRuntime *runtime, BasicProgram *program)
{
    return bsr_init_with_store(runtime, program, NULL);
}

BSRResult bsr_submit(BasicSessionRuntime *runtime,
                     const uint8_t *source, size_t source_length,
                     uint8_t *temporary, size_t temporary_capacity,
                     uint8_t *output, size_t output_capacity,
                     size_t *written)
{
    size_t start, end;
    BSResult session_result;

    if (runtime == NULL || runtime->program == NULL ||
        runtime->program->data == NULL || source == NULL ||
        temporary == NULL || output == NULL || written == NULL) {
        return simple(BSR_INVALID_ARGUMENT);
    }
    if (runtime->variables != NULL) {
        BEStatus store_status = bsr_store_error(bvs_validate(runtime->variables));
        if (store_status != BE_OK) {
            return from_executor(store_status);
        }
    }
    if (submit_overlap(runtime, source, source_length, temporary,
                       temporary_capacity, output, output_capacity, written)) {
        return simple(BSR_OVERLAP);
    }
    /* The J0.6 grammar recognizes numbered lines only at byte zero. */
    if (runtime->state == BSR_RUNNING && source_length != 0u &&
        source[0] >= (uint8_t)'0' && source[0] <= (uint8_t)'9') {
        return simple(BSR_BUSY);
    }

    start = 0u;
    while (start < source_length && source[start] == (uint8_t)' ') {
        ++start;
    }
    end = source_length;
    while (end > start && source[end - 1u] == (uint8_t)' ') {
        --end;
    }
    if (command_is(source + start, end - start, "RUN")) {
        BasicExecutor candidate;
        BEStatus status = be_init_with_store(&candidate, runtime->program,
                                             runtime->variables);
        if (status != BE_OK) {
            return from_executor(status);
        }
        if (runtime->variables != NULL) {
            status = bsr_store_error(bvs_reset(runtime->variables));
            if (status != BE_OK) {
                return from_executor(status);
            }
        }
        runtime->executor = candidate;
        runtime->state = BSR_RUNNING;
        *written = 0u;
        return simple(BSR_OK);
    }

    session_result = bs_process_line(runtime->program, source, source_length,
                                     temporary, temporary_capacity,
                                     output, output_capacity, written);
    if (session_result.status == BS_OK &&
        command_is(source + start, end - start, "NEW")) {
        if (runtime->variables != NULL) {
            BEStatus store_status = bsr_store_error(bvs_reset(runtime->variables));
            if (store_status != BE_OK) {
                return from_executor(store_status);
            }
        }
        runtime->state = BSR_IDLE;
    }
    return from_session(session_result);
}

BSRResult bsr_step(BasicSessionRuntime *runtime,
                   uint8_t *output, size_t output_capacity, size_t *written)
{
    BEStatus status;
    if (runtime == NULL || runtime->program == NULL ||
        runtime->program->data == NULL || output == NULL || written == NULL) {
        return simple(BSR_INVALID_ARGUMENT);
    }
    if (runtime->variables != NULL) {
        BEStatus store_status = bsr_store_error(bvs_validate(runtime->variables));
        if (store_status != BE_OK) {
            return from_executor(store_status);
        }
    }
    if (step_overlap(runtime, output, output_capacity, written)) {
        return simple(BSR_OVERLAP);
    }
    if (runtime->state != BSR_RUNNING) {
        return simple(BSR_NOT_RUNNING);
    }
    status = be_step(&runtime->executor, output, output_capacity, written);
    if (status == BE_END) {
        BSRResult ended = simple(BSR_END);
        runtime->state = BSR_IDLE;
        ended.executor_status = BE_END;
        return ended;
    }
    if (status != BE_OK) {
        return from_executor(status);
    }
    return simple(BSR_OK);
}

BSRResult bsr_stop(BasicSessionRuntime *runtime)
{
    if (runtime == NULL || runtime->program == NULL) {
        return simple(BSR_INVALID_ARGUMENT);
    }
    runtime->state = BSR_IDLE;
    return simple(BSR_OK);
}
