#include "basic_executor.h"
#include "basic_variable_binding.h"

#include <stdint.h>
#include <string.h>

typedef struct {
    int present;
    BasicVariableKey key;
    BasicVariableValue value;
} BEAssignment;

typedef struct {
    uint8_t *data; /* NULL for the validation/measurement pass. */
    size_t length;
} BEEmitter;

/* Distinct-object relational pointer comparisons are undefined by C99.
 * uintptr_t is available on Linux/ESP32; otherwise caller guarantees
 * disjointness. All nonzero spans must describe valid accessible objects. */
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

static BEStatus emit(BEEmitter *out, uint8_t value)
{
    if (out->length == SIZE_MAX) {
        return BE_NO_SPACE;
    }
    if (out->data != NULL) {
        out->data[out->length] = value;
    }
    ++out->length;
    return BE_OK;
}

static BEStatus emit_decimal(BEEmitter *out, uint8_t value)
{
    uint8_t digits[3];
    size_t count = 0u;
    unsigned int n = value;
    BEStatus status;
    do {
        digits[count++] = (uint8_t)((unsigned int)'0' + n % 10u);
        n /= 10u;
    } while (n != 0u);
    while (count != 0u) {
        status = emit(out, digits[--count]);
        if (status != BE_OK) {
            return status;
        }
    }
    return BE_OK;
}

static void skip_spaces(const uint8_t *body, size_t length, size_t *pos)
{
    while (*pos < length && body[*pos] == (uint8_t)' ') {
        ++*pos;
    }
}

static BEStatus unexpected(uint8_t token)
{
    if (token >= 0x80u || (token >= 0x0eu && token <= 0x1fu)) {
        return BE_UNKNOWN_TOKEN;
    }
    return BE_BAD_SEQUENCE;
}

static BEStatus store_error(BVSStatus status)
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

static BEStatus binding_error(BVBStatus status)
{
    switch (status) {
        case BVB_TRUNCATED: return BE_TRUNCATED;
        case BVB_OVERLAPPING_MEMORY: return BE_OVERLAP;
        default: return BE_BAD_SEQUENCE;
    }
}

/* A comment terminates this numbered line even if its tail appears to
 * contain further statements. Reject forbidden input control bytes in
 * manually imported bodies as well. */
static BEStatus comment_end(const uint8_t *body, size_t length, size_t pos,
                            size_t next_line, size_t *next)
{
    while (pos < length) {
        uint8_t c = body[pos++];
        if (c == 0u || c == (uint8_t)'\r' || c == (uint8_t)'\n') {
            return BE_BAD_SEQUENCE;
        }
    }
    *next = next_line;
    return BE_OK;
}

/* Parse/execute precisely the reached prefix of one numbered line.
 * A successful GOTO returns immediately; the suffix is not inspected.
 * next is written only on success. No output passes occur before validation. */
static BEStatus execute_line(const BasicProgram *program,
                             const BasicProgramLine *line,
                             BEEmitter *out, size_t *next,
                             BasicVariableStore *variables,
                             BEAssignment *assignment)
{
    const uint8_t *body = program->data + line->body_offset;
    size_t length = line->body_length;
    size_t pos = 0u;
    BEStatus status;

    for (;;) {
        size_t argument_start;
        uint8_t token;
        skip_spaces(body, length, &pos);
        if (pos == length) {
            *next = line->next_offset;
            return BE_OK;
        }
        token = body[pos++];
        if (token == 0xc5u) { /* REM */
            return comment_end(body, length, pos, line->next_offset, next);
        }
        if (token == 0x01u && pos < length && body[pos] == 0xc0u) {
            /* Apostrophe marker E1BC: 01 C0, not an empty statement. */
            return comment_end(body, length, pos + 1u,
                               line->next_offset, next);
        }
        if (token == 0xbfu) { /* PRINT */
            argument_start = pos;
            skip_spaces(body, length, &pos);
            if (pos < length && body[pos] != 0x01u) {
                token = body[pos++];
                if (token == (uint8_t)'"') {
                    /* A quoted string may contain raw 0x01 (or ':').
                     * Only the closing quote or end of body terminates it.
                     * 0x01 separates statements only outside strings. */
                    while (pos < length) {
                        uint8_t c = body[pos++];
                        if (c == (uint8_t)'"') {
                            break;
                        }
                        if (c == 0u || c == (uint8_t)'\r' ||
                            c == (uint8_t)'\n') {
                            return BE_BAD_SEQUENCE;
                        }
                        status = emit(out, c);
                        if (status != BE_OK) {
                            return status;
                        }
                    }
                } else if (token >= 0x0eu && token <= 0x17u) {
                    if (argument_start == pos - 1u) {
                        return BE_BAD_SEQUENCE;
                    }
                    status = emit_decimal(out, (uint8_t)(token - 0x0eu));
                    if (status != BE_OK) {
                        return status;
                    }
                } else if (token == 0x19u) {
                    uint8_t value;
                    if (pos == length) {
                        return BE_TRUNCATED;
                    }
                    value = body[pos++];
                    if (argument_start == pos - 2u || value < 10u) {
                        return BE_BAD_SEQUENCE;
                    }
                    status = emit_decimal(out, value);
                    if (status != BE_OK) {
                        return status;
                    }
                } else if (token >= 0x02u && token <= 0x04u) {
                    /* Valid explicit scalar syntax is stored/listed only.
                     * Never resolve caches or read the variable store here. */
                    return BE_UNSUPPORTED;
                } else {
                    return unexpected(token);
                }
            }
            status = emit(out, (uint8_t)'\n');
            if (status != BE_OK) {
                return status;
            }
        } else if (token == 0xa0u) { /* GOTO */
            uint16_t destination;
            BasicProgramLine target;
            BPStatus bp_status;
            argument_start = pos;
            skip_spaces(body, length, &pos);
            if (pos == length || body[pos] == 0x01u) {
                return BE_BAD_SEQUENCE;
            }
            token = body[pos++];
            if (token != 0x1eu) {
                return unexpected(token);
            }
            if (length - pos < 2u) {
                return BE_TRUNCATED;
            }
            destination = (uint16_t)((uint16_t)body[pos] |
                ((uint16_t)body[pos + 1u] << 8));
            pos += 2u;
            if (destination == 0u || argument_start == pos - 3u) {
                return BE_BAD_SEQUENCE;
            }
            skip_spaces(body, length, &pos);
            if (pos < length && body[pos] != 0x01u) {
                return unexpected(body[pos]);
            }
            bp_status = bp_find(program, destination, &target);
            if (bp_status == BP_NOT_FOUND) {
                return BE_MISSING_TARGET;
            }
            if (bp_status != BP_OK) {
                return BE_BAD_PROGRAM;
            }
            *next = target.offset;
            return BE_OK;
        } else if (token == 0x98u) { /* END — basic.asm E663, CC31. */
            /* Validate only the reached statement's syntax. As for GOTO,
             * a suffix after an explicit colon is never executed here. */
            skip_spaces(body, length, &pos);
            if (pos < length && body[pos] != 0x01u) {
                return unexpected(body[pos]);
            }
            /* bp_next() sees this program's terminal 00 00 at size - 2.
             * The host observes BE_OK now, BE_END on its next call. */
            *next = program->size - 2u;
            return BE_OK;
        } else if (token == 0x02u || token == 0xa5u) {
            BasicVariableKey key;
            BasicVariableValue value;
            size_t consumed, start;
            uint8_t literal;
            BVBStatus resolved;
            /* This is intentionally not a general expression evaluator. */
            if (variables == NULL) {
                return BE_UNSUPPORTED;
            }
            if (token == 0xa5u) {
                skip_spaces(body, length, &pos);
                if (pos == length) {
                    return BE_TRUNCATED;
                }
                if (body[pos] != 0x02u) {
                    return BE_BAD_SEQUENCE;
                }
                start = pos;
            } else {
                start = pos - 1u;
            }
            resolved = bvb_resolve_explicit(body, length, start, &key, &consumed);
            if (resolved != BVB_OK) {
                return binding_error(resolved);
            }
            if (key.type != (uint8_t)BVT_INTEGER) {
                return BE_INVALID_TYPE;
            }
            pos = start + consumed;
            skip_spaces(body, length, &pos);
            if (pos == length) {
                return BE_TRUNCATED;
            }
            if (body[pos++] != 0xefu) {
                return BE_BAD_SEQUENCE;
            }
            skip_spaces(body, length, &pos);
            if (pos == length) {
                return BE_TRUNCATED;
            }
            literal = body[pos++];
            if (literal >= 0x0eu && literal <= 0x17u) {
                value.data.integer = (int16_t)(literal - 0x0eu);
            } else if (literal == 0x19u) {
                if (pos == length) {
                    return BE_TRUNCATED;
                }
                literal = body[pos++];
                if (literal < 10u) {
                    return BE_BAD_SEQUENCE;
                }
                value.data.integer = (int16_t)literal;
            } else {
                return BE_BAD_SEQUENCE;
            }
            skip_spaces(body, length, &pos);
            /* Multi-statement lines with an assignment are not in J0.19.
             * Do not commit a prefix, including if a comment follows it. */
            if (pos < length && body[pos] == 0x01u) {
                return BE_UNSUPPORTED;
            }
            if (pos != length) {
                return BE_BAD_SEQUENCE;
            }
            value.type = (uint8_t)BVT_INTEGER;
            assignment->present = 1;
            assignment->key = key;
            assignment->value = value;
            *next = line->next_offset;
            return BE_OK;
        } else if (token == 0xa7u || token == 0xb1u || token == 0xcau) {
            return BE_UNSUPPORTED; /* LIST, NEW, RUN in stored programs. */
        } else {
            return unexpected(token);
        }
        skip_spaces(body, length, &pos);
        if (pos == length) {
            *next = line->next_offset;
            return BE_OK;
        }
        if (body[pos] != 0x01u) {
            return unexpected(body[pos]);
        }
        if (pos + 1u < length && body[pos + 1u] == 0xc0u) {
            return comment_end(body, length, pos + 2u,
                               line->next_offset, next);
        }
        ++pos;
        {
            size_t following = pos;
            skip_spaces(body, length, &following);
            if (following == length ||
                (body[following] == 0x01u &&
                 (following + 1u == length ||
                  body[following + 1u] != 0xc0u))) {
                return BE_BAD_SEQUENCE;
            }
        }
    }
}

BEStatus be_init_with_store(BasicExecutor *executor, const BasicProgram *program,
                            BasicVariableStore *variables)
{
    size_t entry_bytes = 0u;
    if (executor == NULL || program == NULL) {
        return BE_INVALID_ARGUMENT;
    }
    if (bp_validate(program) != BP_OK) {
        return BE_BAD_PROGRAM;
    }
    if (variables != NULL) {
        BEStatus error = store_error(bvs_validate(variables));
        if (error != BE_OK) {
            return error;
        }
        entry_bytes = variables->capacity * sizeof(BasicVariableEntry);
    }
    if (overlaps(executor, sizeof(*executor), program, sizeof(*program)) ||
        overlaps(executor, sizeof(*executor), program->data, program->capacity) ||
        overlaps(program, sizeof(*program), program->data, program->capacity) ||
        (variables != NULL &&
         (overlaps(variables, sizeof(*variables), executor, sizeof(*executor)) ||
          overlaps(variables, sizeof(*variables), program, sizeof(*program)) ||
          overlaps(variables, sizeof(*variables), program->data, program->capacity) ||
          overlaps(variables->entries, entry_bytes, executor, sizeof(*executor)) ||
          overlaps(variables->entries, entry_bytes, program, sizeof(*program)) ||
          overlaps(variables->entries, entry_bytes, program->data, program->capacity)))) {
        return BE_OVERLAP;
    }
    executor->program = program;
    executor->cursor = 0u;
    executor->variables = variables;
    return BE_OK;
}

BEStatus be_init(BasicExecutor *executor, const BasicProgram *program)
{
    return be_init_with_store(executor, program, NULL);
}

BEStatus be_step(BasicExecutor *executor, uint8_t *output,
                 size_t output_capacity, size_t *written)
{
    const BasicProgram *program;
    BasicProgramLine line;
    BEEmitter probe = {NULL, 0u};
    BEAssignment assignment = {0};
    BEAssignment second = {0};
    BasicVariableStore *variables;
    size_t entry_bytes = 0u;
    BEEmitter writer;
    size_t next = 0u;
    size_t check_next = 0u;
    BPStatus bp_status;
    BEStatus status;
    size_t current;

    if (executor == NULL || output == NULL || written == NULL) {
        return BE_INVALID_ARGUMENT;
    }
    program = executor->program;
    if (program == NULL) {
        return BE_INVALID_ARGUMENT;
    }
    if (bp_validate(program) != BP_OK) {
        return BE_BAD_PROGRAM;
    }
    if (overlaps(executor, sizeof(*executor), program, sizeof(*program)) ||
        overlaps(executor, sizeof(*executor), program->data, program->capacity) ||
        overlaps(program, sizeof(*program), program->data, program->capacity) ||
        overlaps(output, output_capacity, executor, sizeof(*executor)) ||
        overlaps(output, output_capacity, program, sizeof(*program)) ||
        overlaps(output, output_capacity, program->data, program->capacity) ||
        overlaps(written, sizeof(*written), output, output_capacity) ||
        overlaps(written, sizeof(*written), executor, sizeof(*executor)) ||
        overlaps(written, sizeof(*written), program, sizeof(*program)) ||
        overlaps(written, sizeof(*written), program->data, program->capacity)) {
        return BE_OVERLAP;
    }
    variables = executor->variables;
    if (variables != NULL) {
        status = store_error(bvs_validate(variables));
        if (status != BE_OK) {
            return status;
        }
        entry_bytes = variables->capacity * sizeof(BasicVariableEntry);
        if (overlaps(variables, sizeof(*variables), executor, sizeof(*executor)) ||
            overlaps(variables, sizeof(*variables), program, sizeof(*program)) ||
            overlaps(variables, sizeof(*variables), program->data, program->capacity) ||
            overlaps(variables, sizeof(*variables), output, output_capacity) ||
            overlaps(variables, sizeof(*variables), written, sizeof(*written)) ||
            overlaps(variables->entries, entry_bytes, executor, sizeof(*executor)) ||
            overlaps(variables->entries, entry_bytes, program, sizeof(*program)) ||
            overlaps(variables->entries, entry_bytes, program->data, program->capacity) ||
            overlaps(variables->entries, entry_bytes, output, output_capacity) ||
            overlaps(variables->entries, entry_bytes, written, sizeof(*written))) {
            return BE_OVERLAP;
        }
    }
    current = executor->cursor;
    bp_status = bp_next(program, &current, &line);
    if (bp_status == BP_END) {
        return BE_END;
    }
    if (bp_status != BP_OK) {
        return BE_BAD_PROGRAM;
    }
    status = execute_line(program, &line, &probe, &next, variables, &assignment);
    if (status != BE_OK) {
        return status;
    }
    if (probe.length > output_capacity) {
        return BE_NO_SPACE;
    }
    writer.data = output;
    writer.length = 0u;
    status = execute_line(program, &line, &writer, &check_next, variables, &second);
    if (status != BE_OK || writer.length != probe.length || check_next != next ||
        assignment.present != second.present ||
        (assignment.present &&
         (assignment.key.type != second.key.type ||
          assignment.key.name_length != second.key.name_length ||
          memcmp(assignment.key.name, second.key.name, BVT_MAX_NAME_LENGTH) != 0 ||
          assignment.value.data.integer != second.value.data.integer))) {
        /* Unreachable while the documented immutable-input contract holds. */
        return BE_BAD_PROGRAM;
    }
    if (assignment.present) {
        status = store_error(bvs_assign(variables, &assignment.key, &assignment.value));
        if (status != BE_OK) {
            return status;
        }
    }
    *written = writer.length;
    executor->cursor = next;
    return BE_OK;
}
