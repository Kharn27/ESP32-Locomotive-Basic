#include "basic_executor.h"
#include "basic_variable_binding.h"
#include "basic_variable_ref.h"

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

/* CPC INTEGER variable PRINT: sign/alignment and trailing blank.
 * Transport newline belongs to execute_line(), never to this formatter.
 * Widen before negation so INT16_MIN is representable. */
static BEStatus emit_integer(BEEmitter *out, int16_t value)
{
    uint8_t digits[5];
    size_t count = 0u;
    int32_t magnitude = (int32_t)value;
    unsigned int n;
    BEStatus status;
    if (magnitude >= 0) {
        status = emit(out, (uint8_t)' ');
        if (status != BE_OK) {
            return status;
        }
    } else {
        status = emit(out, (uint8_t)'-');
        if (status != BE_OK) {
            return status;
        }
        magnitude = -magnitude;
    }
    n = (unsigned int)magnitude;
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
    return emit(out, (uint8_t)' ');
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
        case BVB_NOT_FOUND: return BE_VARIABLE_NOT_FOUND;
        case BVB_INVALID_STORE: return BE_INVALID_STORE;
        case BVB_OVERLAPPING_MEMORY: return BE_OVERLAP;
        default: return BE_BAD_SEQUENCE;
    }
}

/* J1.14-B inline IF arm: parse a complete INTEGER BVR EF immediate,
 * even if that arm will not be taken. No store lookup or mutation here.
 * The two-pass caller preflights capacity and commits only the chosen arm. */
static BEStatus inline_if_arm(const uint8_t *body, size_t length,
                              size_t *at, BEAssignment *arm)
{
    BasicVariableKey key;
    size_t consumed = 0u;
    BVBStatus resolved;
    uint8_t literal;
    unsigned int number;
    skip_spaces(body, length, at);
    if (*at == length) return BE_TRUNCATED;
    if (body[*at] != 0x02u) return BE_BAD_SEQUENCE;
    resolved = bvb_resolve_explicit(body, length, *at, &key, &consumed);
    if (resolved != BVB_OK) return binding_error(resolved);
    if (key.type != (uint8_t)BVT_INTEGER) return BE_INVALID_TYPE;
    *at += consumed;
    skip_spaces(body, length, at);
    if (*at == length) return BE_TRUNCATED;
    if (body[(*at)++] != 0xefu) return BE_BAD_SEQUENCE;
    skip_spaces(body, length, at);
    if (*at == length) return BE_TRUNCATED;
    literal = body[(*at)++];
    if (literal >= 0x0eu && literal <= 0x17u) {
        number = (unsigned int)(literal - 0x0eu);
    } else if (literal == 0x19u) {
        if (*at == length) return BE_TRUNCATED;
        number = (unsigned int)body[(*at)++];
        if (number < 10u) return BE_BAD_SEQUENCE;
    } else {
        return BE_BAD_SEQUENCE;
    }
    arm->present = 1;
    arm->key = key;
    arm->value.type = (uint8_t)BVT_INTEGER;
    arm->value.data.integer = (int16_t)number;
    return BE_OK;
}

/* Evaluate one explicit INTEGER source and unsigned-byte operand, or
 * for F4/F5/F6/F9/FB one more explicit INTEGER source reference.
 * One decoder serves both executor passes; only caller-local values change.
 * The reference cache is opaque and bvb_read_explicit never edits it. */
static BEStatus evaluate_integer_binary(const uint8_t *body, size_t length,
                                          size_t source_start,
                                          const BasicVariableStore *variables,
                                          size_t *next_pos, int16_t *number)
{
    BasicVariableKey source;
    BasicVariableValue value;
    size_t consumed = 0u;
    size_t pos;
    uint8_t token, operand, operation;
    int32_t result;
    int32_t rhs;
    BVBStatus resolved = bvb_read_explicit(body, length, source_start,
                                           variables, &source, &consumed, &value);
    if (resolved != BVB_OK) {
        return binding_error(resolved);
    }
    if (source.type != (uint8_t)BVT_INTEGER ||
        value.type != (uint8_t)BVT_INTEGER) {
        return BE_INVALID_TYPE;
    }
    pos = source_start + consumed;
    skip_spaces(body, length, &pos);
    if (pos == length) {
        return BE_TRUNCATED;
    }
    operation = body[pos++];
    if (operation != 0xf4u && operation != 0xf5u &&
        operation != 0xf6u && operation != 0xf9u && operation != 0xfbu) {
        return BE_BAD_SEQUENCE;
    }
    skip_spaces(body, length, &pos);
    if (pos == length) {
        return BE_TRUNCATED;
    }
    token = body[pos++];
    if (token == 0x02u) {
        BasicVariableKey right_key;
        BasicVariableValue right_value;
        size_t right_consumed = 0u;
        BVBStatus right = bvb_read_explicit(body, length, pos - 1u,
                                             variables, &right_key,
                                             &right_consumed, &right_value);
        if (right != BVB_OK) {
            return binding_error(right);
        }
        if (right_key.type != (uint8_t)BVT_INTEGER ||
            right_value.type != (uint8_t)BVT_INTEGER) {
            return BE_INVALID_TYPE;
        }
        rhs = (int32_t)right_value.data.integer;
        pos = pos - 1u + right_consumed;
    } else if (token >= 0x0eu && token <= 0x17u) {
        operand = (uint8_t)(token - 0x0eu);
        rhs = (int32_t)operand;
    } else if (token == 0x19u) {
        if (pos == length) {
            return BE_TRUNCATED;
        }
        operand = body[pos++];
        if (operand < 10u) {
            return BE_BAD_SEQUENCE;
        }
        rhs = (int32_t)operand;
    } else {
        return BE_BAD_SEQUENCE;
    }
    /* Check before dividing: no host UB and no destination/cache mutation.
     * C99 int32_t division truncates toward zero; MIN / -1 is safe in
     * int32_t and rejected after range-check for F9, but MOD gives zero. */
    if ((operation == 0xf9u || operation == 0xfbu) && rhs == 0) {
        return BE_DIVISION_BY_ZERO;
    }
    /* Widen before arithmetic; never rely on signed overflow or wrapping. */
    result = operation == 0xf4u
        ? (int32_t)value.data.integer + rhs
        : operation == 0xf5u
          ? (int32_t)value.data.integer - rhs
          : operation == 0xf6u
            ? (int32_t)value.data.integer * rhs
            : operation == 0xf9u
              ? (int32_t)value.data.integer / rhs
              : (int32_t)value.data.integer % rhs;
    if (result < INT16_MIN || result > INT16_MAX) {
        return BE_INTEGER_OVERFLOW;
    }
    *number = (int16_t)result;
    *next_pos = pos;
    return BE_OK;
}


/* FOR/NEXT INTEGER literals are the same strictly bounded CPC encodings
 * already admitted by the scalar assignment path, not REAL expressions. */
static BEStatus for_literal(const uint8_t *body, size_t length,
                            size_t *at, int16_t *result)
{
    size_t pos = *at;
    int negative = 0;
    int32_t magnitude;
    uint8_t token;
    static const uint8_t min_real5[5] = {0,0,0,0,0x90};
    skip_spaces(body, length, &pos);
    if (pos == length) return BE_TRUNCATED;
    token = body[pos++];
    if (token == 0xf5u) {
        negative = 1;
        if (pos == length) return BE_TRUNCATED;
        token = body[pos++];
    }
    if (token >= 0x0eu && token <= 0x17u) {
        magnitude = (int32_t)(token - 0x0eu);
    } else if (token == 0x19u) {
        if (pos == length) return BE_TRUNCATED;
        magnitude = body[pos++];
        if (magnitude < 10) return BE_BAD_SEQUENCE;
    } else if (token == 0x1au) {
        if (length - pos < 2u) return BE_TRUNCATED;
        magnitude = (int32_t)((uint32_t)body[pos] |
                              ((uint32_t)body[pos + 1u] << 8));
        pos += 2u;
        if (magnitude < 256) return BE_BAD_SEQUENCE;
    } else if (token == 0x1fu && negative) {
        if (length - pos < 5u) return BE_TRUNCATED;
        if (memcmp(body + pos, min_real5, 5u) != 0) return BE_BAD_SEQUENCE;
        pos += 5u;
        magnitude = 32768;
    } else {
        return BE_BAD_SEQUENCE;
    }
    magnitude = negative ? -magnitude : magnitude;
    if (magnitude < INT16_MIN || magnitude > INT16_MAX) {
        return BE_INTEGER_OVERFLOW;
    }
    *result = (int16_t)magnitude;
    *at = pos;
    return BE_OK;
}

static int for_same_key(const BasicVariableKey *a, const BasicVariableKey *b)
{
    return a->type == b->type && a->name_length == b->name_length &&
           memcmp(a->name, b->name, BVT_MAX_NAME_LENGTH) == 0;
}

/* Decode FOR control before inspecting the program or making any assignment.
 * The name reference's two cache bytes are deliberately never interpreted. */
static BEStatus for_header(const uint8_t *body, size_t length, size_t *at,
                           BasicVariableKey *key, int16_t *initial,
                           int16_t *limit, int16_t *step)
{
    size_t pos = *at, consumed = 0u;
    BEStatus status;
    BVBStatus resolved;
    skip_spaces(body, length, &pos);
    if (pos == length) return BE_TRUNCATED;
    resolved = bvb_resolve_explicit(body, length, pos, key, &consumed);
    if (resolved != BVB_OK) return binding_error(resolved);
    if (key->type != (uint8_t)BVT_INTEGER) return BE_INVALID_TYPE;
    pos += consumed;
    skip_spaces(body, length, &pos);
    if (pos == length || body[pos++] != 0xefu) return BE_BAD_SEQUENCE;
    status = for_literal(body, length, &pos, initial);
    if (status != BE_OK) return status;
    skip_spaces(body, length, &pos);
    if (pos == length || body[pos++] != 0xecu) return BE_BAD_SEQUENCE;
    status = for_literal(body, length, &pos, limit);
    if (status != BE_OK) return status;
    skip_spaces(body, length, &pos);
    *step = 1;
    if (pos < length && body[pos] == 0xe6u) {
        ++pos;
        status = for_literal(body, length, &pos, step);
        if (status != BE_OK) return status;
        skip_spaces(body, length, &pos);
    }
    if (*step == 0) return BE_UNSUPPORTED; /* STEP 0 not oracle-verified. */
    if (pos < length && body[pos] != 0x01u) return unexpected(body[pos]);
    *at = pos;
    return BE_OK;
}

/* J1.12-B2-C1: the implicit apostrophe is 01 C0; an explicit
 * colon before an apostrophe is 01 01 C0. At a statement boundary
 * keep the whole comment marker, otherwise skip just the colon.
 * Caller has already verified pos < length and body[pos] == 01. */
static size_t for_next_continuation(const uint8_t *body, size_t length,
                                    size_t pos)
{
    return pos + 1u < length && body[pos + 1u] == 0xc0u
           ? pos : pos + 1u;
}

/* Locate the matching structural NEXT without executing intervening code.
 * Only statement starts count. Quoted strings, REM, apostrophes, variable
 * cache bytes and numeric token payloads cannot create phantom statements.
 * O(program size), fixed 8-frame local nesting stack, no heap or recursion. */
static BEStatus for_match(const BasicProgram *program,
                          const BasicProgramLine *first, size_t start,
                          const BasicVariableKey *wanted,
                          size_t *exit_cursor, size_t *exit_statement)
{
    BasicProgramLine line;
    BasicVariableKey nested[BE_FOR_STACK_CAPACITY];
    size_t depth = 0u, scan = first->offset, pos = start;
    int first_line = 1;
    BPStatus bp_status;
    while ((bp_status = bp_next(program, &scan, &line)) == BP_OK) {
        const uint8_t *body = program->data + line.body_offset;
        size_t n = line.body_length;
        if (!first_line) pos = 0u;
        first_line = 0;
        while (pos < n) {
            uint8_t token;
            skip_spaces(body, n, &pos);
            if (pos >= n) break;
            token = body[pos];
            if (token == 0x01u) {
                if (pos + 1u < n && body[pos + 1u] == 0xc0u) break;
                ++pos;
                continue;
            }
            if (token == 0xc5u) break;
            ++pos;
            if (token == 0x9eu) {
                size_t count = 0u, p = pos;
                BVBStatus resolved;
                if (depth == BE_FOR_STACK_CAPACITY) return BE_FOR_STACK_FULL;
                skip_spaces(body, n, &p);
                resolved = bvb_resolve_explicit(body, n, p, &nested[depth], &count);
                if (resolved != BVB_OK) return binding_error(resolved);
                if (nested[depth].type != (uint8_t)BVT_INTEGER) return BE_INVALID_TYPE;
                ++depth;
            } else if (token == 0xb0u) {
                BasicVariableKey key;
                const BasicVariableKey *expected = depth == 0u ?
                                                   wanted : &nested[depth - 1u];
                size_t count = 0u;
                skip_spaces(body, n, &pos);
                if (pos < n && body[pos] == 0x02u) {
                    BVBStatus resolved = bvb_resolve_explicit(body, n, pos,
                                                               &key, &count);
                    if (resolved != BVB_OK) return binding_error(resolved);
                    if (key.type != (uint8_t)BVT_INTEGER) return BE_INVALID_TYPE;
                    if (!for_same_key(&key, expected))
                        return BE_NEXT_VARIABLE_MISMATCH;
                    pos += count;
                }
                skip_spaces(body, n, &pos);
                if (pos < n && body[pos] != 0x01u)
                    return unexpected(body[pos]);
                if (depth == 0u) {
                    if (pos < n) {
                        *exit_cursor = line.offset;
                        *exit_statement = for_next_continuation(body, n, pos);
                    } else {
                        *exit_cursor = line.next_offset;
                        *exit_statement = 0u;
                    }
                    return BE_OK;
                }
                --depth;
            }
            /* Seek next real ':' separator, ignoring payload bytes. */
            {
                int quoted = 0;
                while (pos < n) {
                    uint8_t c = body[pos];
                    if (c == (uint8_t)'"') {
                        quoted = !quoted; ++pos; continue;
                    }
                    if (!quoted && (c == 0x01u || c == 0xc5u)) break;
                    if (!quoted && ((c >= 0x02u && c <= 0x04u) ||
                                    (c >= 0x0bu && c <= 0x0du))) {
                        BasicVariableRef ref;
                        if (bvr_decode(body, n, pos, &ref) != BVR_OK)
                            return BE_BAD_SEQUENCE;
                        pos += ref.consumed;
                        continue;
                    }
                    if (!quoted && (c == 0x19u || c == 0x1au ||
                                    c == 0x1du || c == 0x1eu || c == 0x1fu)) {
                        size_t payload = c == 0x19u ? 1u : (c == 0x1fu ? 5u : 2u);
                        if (n - pos <= payload) return BE_TRUNCATED;
                        pos += payload + 1u;
                        continue;
                    }
                    ++pos;
                }
            }
            if (pos < n && body[pos] == 0xc5u) break;
        }
    }
    return bp_status == BP_END ? BE_FOR_WITHOUT_NEXT : BE_BAD_PROGRAM;
}

/* Pure action description prepared by both executor passes; never mutate
 * the call stack until validation, capacity, output and replay all succeed. */
typedef enum { BE_FLOW_NONE, BE_FLOW_PUSH, BE_FLOW_POP, BE_FLOW_CLEAR } BEFlowAction;
typedef enum { BE_FOR_NONE, BE_FOR_PUSH, BE_FOR_POP } BEForAction;
typedef struct {
    BEFlowAction action;
    BECallFrame frame;
    size_t next_statement;
    BEForAction for_action;
    BEForFrame for_frame;
} BEFlow;

/* A branch or END may skip a suffix. In J0.19, no numbered line
 * containing an actual subsequent assignment is executable. Locate only
 * statement starts, never CPC cache bytes or quoted payloads. */
static int suffix_assignment(const uint8_t *body, size_t length, size_t pos)
{
    while (pos < length && body[pos] == 0x01u) {
        int quoted = 0;
        ++pos;
        skip_spaces(body, length, &pos);
        if (pos == length || (body[pos] == 0x01u && pos + 1u < length &&
                               body[pos + 1u] == 0xc0u)) {
            return 0;
        }
        if (body[pos] == 0x02u || body[pos] == 0xa5u) {
            return 1;
        }
        while (pos < length) {
            uint8_t c = body[pos];
            if (c == (uint8_t)'"') {
                quoted = !quoted;
                ++pos;
            } else if (!quoted && c == 0xc5u) {
                return 0; /* REM */
            } else if (!quoted && c == 0x01u) {
                if (pos + 1u < length && body[pos + 1u] == 0xc0u) {
                    return 0; /* apostrophe */
                }
                break;
            } else if (!quoted && ((c >= 0x02u && c <= 0x04u) ||
                                   (c >= 0x0bu && c <= 0x0du))) {
                BasicVariableRef ref;
                if (bvr_decode(body, length, pos, &ref) == BVR_OK) {
                    pos += ref.consumed;
                } else {
                    ++pos;
                }
            } else if (!quoted && (c == 0x19u || c == 0x1au ||
                                    c == 0x1eu || c == 0x1du ||
                                    c == 0x1fu)) {
                size_t payload = c == 0x19u ? 1u : (c == 0x1fu ? 5u : 2u);
                pos += length - pos > payload ? payload + 1u : length - pos;
            } else {
                ++pos;
            }
        }
    }
    return 0;
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
                             const BasicProgramLine *line, size_t start_pos,
                             const BasicExecutor *executor,
                             BEEmitter *out, size_t *next, BEFlow *flow,
                             BasicVariableStore *variables,
                             BEAssignment *assignment)
{
    const uint8_t *body = program->data + line->body_offset;
    size_t length = line->body_length;
    size_t pos = start_pos;
    int preceding_statement = 0;
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
                } else if (token == 0x02u) {
                    BasicVariableKey key;
                    BasicVariableValue value;
                    size_t consumed = 0u;
                    size_t start = pos - 1u;
                    BVBStatus resolved;
                    /* The binding layer handles opaque CPC cache bytes,
                     * canonical names and exact typed lookup, without mutation. */
                    if (variables == NULL) {
                        return BE_UNSUPPORTED;
                    }
                    resolved = bvb_read_explicit(body, length, start, variables,
                                                 &key, &consumed, &value);
                    if (resolved != BVB_OK) {
                        return binding_error(resolved);
                    }
                    if (key.type != (uint8_t)BVT_INTEGER ||
                        value.type != (uint8_t)BVT_INTEGER) {
                        return BE_INVALID_TYPE;
                    }
                    pos = start + consumed;
                    status = emit_integer(out, value.data.integer);
                    if (status != BE_OK) {
                        return status;
                    }
                } else if (token == 0x03u || token == 0x04u) {
                    return BE_UNSUPPORTED; /* STRING and REAL5 postponed. */
                } else {
                    return unexpected(token);
                }
            }
            status = emit(out, (uint8_t)'\n');
            if (status != BE_OK) {
                return status;
            }
        } else if (token == 0xa1u) { /* IF integer% [relation integer%] THEN line */
            BasicVariableKey key;
            BasicVariableValue value;
            int take_branch;
            BasicProgramLine target;
            size_t consumed = 0u;
            uint16_t destination;
            BVBStatus resolved;
            BPStatus found;
            if (preceding_statement || variables == NULL) {
                return BE_UNSUPPORTED; /* Autonomous IF, store required. */
            }
            skip_spaces(body, length, &pos);
            if (pos == length) {
                return BE_TRUNCATED;
            }
            if (body[pos] != 0x02u) {
                return BE_BAD_SEQUENCE;
            }
            resolved = bvb_read_explicit(body, length, pos, variables,
                                         &key, &consumed, &value);
            if (resolved != BVB_OK) {
                return binding_error(resolved);
            }
            if (key.type != (uint8_t)BVT_INTEGER ||
                value.type != (uint8_t)BVT_INTEGER) {
                return BE_INVALID_TYPE;
            }
            pos += consumed;
            take_branch = value.data.integer != 0;
            skip_spaces(body, length, &pos);
            if (pos == length) {
                return BE_TRUNCATED;
            }
            if (body[pos] == 0xefu || body[pos] == 0xf2u ||
                body[pos] == 0xf1u || body[pos] == 0xf3u ||
                body[pos] == 0xeeu || body[pos] == 0xf0u) {
                uint8_t relation = body[pos++];
                BasicVariableKey right_key;
                BasicVariableValue right_value;
                size_t right_consumed = 0u;
                int16_t lhs = value.data.integer;
                int16_t rhs;
                skip_spaces(body, length, &pos);
                if (pos == length) return BE_TRUNCATED;
                if (body[pos] != 0x02u) return BE_BAD_SEQUENCE;
                resolved = bvb_read_explicit(body, length, pos, variables,
                                             &right_key, &right_consumed,
                                             &right_value);
                if (resolved != BVB_OK) return binding_error(resolved);
                if (right_key.type != (uint8_t)BVT_INTEGER ||
                    right_value.type != (uint8_t)BVT_INTEGER)
                    return BE_INVALID_TYPE;
                rhs = right_value.data.integer;
                switch (relation) {
                case 0xefu: take_branch = lhs == rhs; break;
                case 0xf2u: take_branch = lhs != rhs; break;
                case 0xf1u: take_branch = lhs < rhs; break;
                case 0xf3u: take_branch = lhs <= rhs; break;
                case 0xeeu: take_branch = lhs > rhs; break;
                default: take_branch = lhs >= rhs; break;
                }
                pos += right_consumed;
                skip_spaces(body, length, &pos);
                if (pos == length) return BE_TRUNCATED;
            }
            if (body[pos++] != 0xebu) {
                return BE_BAD_SEQUENCE;
            }
            skip_spaces(body, length, &pos);
            if (pos == length) {
                return BE_TRUNCATED;
            }
            if (body[pos] == 0x02u) {
                BEAssignment then_arm = {0};
                BEAssignment else_arm = {0};
                int has_else = 0;
                /* Validate BOTH inline arms before choosing a commit.
                 * 01 97 is only legal here as a paired lexical ELSE. */
                status = inline_if_arm(body, length, &pos, &then_arm);
                if (status != BE_OK) return status;
                skip_spaces(body, length, &pos);
                if (pos < length) {
                    if (length - pos < 2u ||
                        body[pos] != 0x01u || body[pos + 1u] != 0x97u)
                        return BE_BAD_SEQUENCE;
                    pos += 2u;
                    status = inline_if_arm(body, length, &pos, &else_arm);
                    if (status != BE_OK) return status;
                    has_else = 1;
                    skip_spaces(body, length, &pos);
                }
                if (pos != length) return BE_BAD_SEQUENCE;
                if (take_branch) *assignment = then_arm;
                else if (has_else) *assignment = else_arm;
                /* False without ELSE leaves C% and store capacity intact. */
                *next = line->next_offset;
                return BE_OK;
            }
            if (body[pos++] != 0x1eu) {
                return BE_BAD_SEQUENCE;
            }
            if (length - pos < 2u) {
                return BE_TRUNCATED;
            }
            destination = (uint16_t)((uint16_t)body[pos] |
                          ((uint16_t)body[pos + 1u] << 8));
            pos += 2u;
            if (destination == 0u) {
                return BE_BAD_SEQUENCE;
            }
            skip_spaces(body, length, &pos);
            if (pos != length) {
                return BE_BAD_SEQUENCE; /* ELSE, colon, or suffix. */
            }
            if (!take_branch) {
                *next = line->next_offset;
                return BE_OK; /* Never resolve an untaken target. */
            }
            found = bp_find(program, destination, &target);
            if (found == BP_NOT_FOUND) {
                return BE_MISSING_TARGET;
            }
            if (found != BP_OK) {
                return BE_BAD_PROGRAM;
            }
            *next = target.offset;
            return BE_OK;
        } else if (token == 0xa0u || token == 0x9fu) { /* GOTO / GOSUB */
            int is_gosub = token == 0x9fu;
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
            if (variables != NULL && suffix_assignment(body, length, pos)) {
                return BE_UNSUPPORTED;
            }
            if (is_gosub) {
                if (executor->call_depth >= BE_GOSUB_STACK_CAPACITY) {
                    return BE_CALL_STACK_FULL;
                }
                flow->action = BE_FLOW_PUSH;
                if (pos < length) {
                    /* 01 C0 is an implicit apostrophe comment marker, NOT
                     * a ':' separator. Resume on its complete 01 C0 pair.
                     * An explicit colon before apostrophe is 01 01 C0:
                     * skip only the first 01 and keep the second marker. */
                    size_t continuation =
                        (pos + 1u < length && body[pos + 1u] == 0xc0u)
                        ? pos : pos + 1u;
                    skip_spaces(body, length, &continuation);
                    if (continuation == length ||
                        (body[continuation] == 0x01u &&
                         (continuation + 1u == length ||
                          body[continuation + 1u] != 0xc0u))) {
                        return BE_BAD_SEQUENCE;
                    }
                    flow->frame.cursor = line->offset;
                    flow->frame.statement_offset = continuation;
                } else {
                    flow->frame.cursor = line->next_offset;
                    flow->frame.statement_offset = 0u;
                }
            }
            *next = target.offset;
            return BE_OK;
        } else if (token == 0xc9u) { /* RETURN */
            skip_spaces(body, length, &pos);
            if (pos < length && body[pos] != 0x01u) {
                return unexpected(body[pos]);
            }
            if (executor->call_depth == 0u) {
                return BE_RETURN_WITHOUT_GOSUB;
            }
            flow->action = BE_FLOW_POP;
            *next = executor->call_stack[executor->call_depth - 1u].cursor;
            flow->next_statement =
                executor->call_stack[executor->call_depth - 1u].statement_offset;
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
            if (variables != NULL && suffix_assignment(body, length, pos)) {
                return BE_UNSUPPORTED;
            }
            *next = program->size - 2u;
            flow->action = BE_FLOW_CLEAR;
            return BE_OK;
        } else if (token == 0x02u || token == 0xa5u) {
            BasicVariableKey key;
            BasicVariableValue value = {0};
            size_t consumed, start;
            uint8_t literal;
            int negative = 0;
            int reference_rhs = 0;
            int32_t magnitude = 0;
            BVBStatus resolved;
            /* Multi-statement lines must not commit a PRINT prefix or
             * an assignment on the same line. The probe stays pure. */
            if (preceding_statement) {
                return BE_UNSUPPORTED;
            }
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
            if (literal == 0xf5u) {
                /* Tokenized CPC unary minus, not a signed-byte encoding.
                 * The RHS must still be one immediate positive literal. */
                negative = 1;
                if (pos == length) {
                    return BE_TRUNCATED;
                }
                literal = body[pos++];
            }
            if (literal >= 0x0eu && literal <= 0x17u) {
                magnitude = (int32_t)(literal - 0x0eu);
            } else if (literal == 0x19u) {
                if (pos == length) {
                    return BE_TRUNCATED;
                }
                literal = body[pos++];
                if (literal < 10u) {
                    return BE_BAD_SEQUENCE;
                }
                magnitude = (int32_t)literal;
            } else if (literal == 0x1au) {
                uint32_t word;
                if (length - pos < 2u) {
                    return BE_TRUNCATED;
                }
                word = (uint32_t)body[pos] |
                       ((uint32_t)body[pos + 1u] << 8);
                pos += 2u;
                if (word < 256u) {
                    return BE_BAD_SEQUENCE; /* 19, not noncanonical 1A. */
                }
                if (word > (uint32_t)INT16_MAX) {
                    return BE_INTEGER_OVERFLOW;
                }
                magnitude = (int32_t)word;
            } else if (literal == 0x1fu) {
                /* NMIN is the sole permitted REAL5 encoding in an INTEGER
                 * assignment. Validate all five bytes before any mutation. */
                static const uint8_t nmin_real5[5] = {0u, 0u, 0u, 0u, 0x90u};
                if (!negative) {
                    return BE_BAD_SEQUENCE;
                }
                if (length - pos < sizeof(nmin_real5)) {
                    return BE_TRUNCATED;
                }
                if (memcmp(body + pos, nmin_real5, sizeof(nmin_real5)) != 0) {
                    return BE_BAD_SEQUENCE;
                }
                pos += sizeof(nmin_real5);
                magnitude = 32768; /* int32_t; negation is well-defined. */
            } else if (literal == 0x02u && !negative) {
                /* Preserve the separate reference + unsigned-byte path. */
                reference_rhs = 1;
                status = evaluate_integer_binary(body, length, pos - 1u,
                                                    variables, &pos,
                                                    &value.data.integer);
                if (status != BE_OK) {
                    return status;
                }
            } else {
                return BE_BAD_SEQUENCE;
            }
            if (!reference_rhs) {
                int32_t signed_value = negative ? -magnitude : magnitude;
                if (signed_value < INT16_MIN || signed_value > INT16_MAX) {
                    return BE_INTEGER_OVERFLOW;
                }
                value.data.integer = (int16_t)signed_value;
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
        } else if (token == 0x9eu) { /* FOR INTEGER */
            BasicVariableKey key;
            int16_t initial, limit, step;
            size_t body_cursor, body_statement, exit_cursor, exit_statement;
            BasicVariableValue value = {0};
            if (variables == NULL) return BE_UNSUPPORTED;
            if (executor->for_depth >= BE_FOR_STACK_CAPACITY)
                return BE_FOR_STACK_FULL;
            status = for_header(body, length, &pos, &key, &initial, &limit, &step);
            if (status != BE_OK) return status;
            /* Resolve paired NEXT before any PRINT in the loop is reached.
             * The sealed WRONG_VAR case requires this anticipatory check. */
            status = for_match(program, line, pos, &key,
                               &exit_cursor, &exit_statement);
            if (status != BE_OK) return status;
            if (pos < length) {
                body_cursor = line->offset;
                body_statement = for_next_continuation(body, length, pos);
            } else {
                body_cursor = line->next_offset;
                body_statement = 0u;
            }
            assignment->present = 1;
            assignment->key = key;
            value.type = (uint8_t)BVT_INTEGER;
            value.data.integer = initial;
            assignment->value = value;
            if ((step > 0 && initial > limit) ||
                (step < 0 && initial < limit)) {
                *next = exit_cursor;
                flow->next_statement = exit_statement;
                return BE_OK;
            }
            flow->for_action = BE_FOR_PUSH;
            flow->for_frame.key = key;
            flow->for_frame.limit = limit;
            flow->for_frame.step = step;
            flow->for_frame.loop_cursor = body_cursor;
            flow->for_frame.loop_statement = body_statement;
            flow->for_frame.after_cursor = exit_cursor;
            flow->for_frame.after_statement = exit_statement;
            *next = body_cursor;
            flow->next_statement = body_statement;
            return BE_OK;
        } else if (token == 0xb0u) { /* NEXT [INTEGER] */
            const BEForFrame *frame;
            BasicVariableValue value = {0};
            BasicVariableKey named;
            int32_t advanced;
            int keep_loop;
            size_t consumed = 0u;
            if (variables == NULL) return BE_UNSUPPORTED;
            if (executor->for_depth == 0u) return BE_NEXT_WITHOUT_FOR;
            frame = &executor->for_stack[executor->for_depth - 1u];
            skip_spaces(body, length, &pos);
            if (pos < length && body[pos] == 0x02u) {
                BVBStatus parsed = bvb_resolve_explicit(body, length, pos,
                                                          &named, &consumed);
                if (parsed != BVB_OK) return binding_error(parsed);
                if (named.type != (uint8_t)BVT_INTEGER) return BE_INVALID_TYPE;
                if (!for_same_key(&named, &frame->key))
                    return BE_NEXT_VARIABLE_MISMATCH;
                pos += consumed;
            }
            skip_spaces(body, length, &pos);
            if (pos < length && body[pos] != 0x01u)
                return unexpected(body[pos]);
            status = store_error(bvs_get(variables, &frame->key, &value));
            if (status != BE_OK) return status;
            if (value.type != (uint8_t)BVT_INTEGER) return BE_INVALID_TYPE;
            advanced = (int32_t)value.data.integer + (int32_t)frame->step;
            /* Host policy: fail rather than wrap if NEXT crosses int16.
             * No CPC equivalence claim for this unmeasured condition. */
            if (advanced < INT16_MIN || advanced > INT16_MAX)
                return BE_INTEGER_OVERFLOW;
            keep_loop = frame->step > 0 ? advanced <= frame->limit
                                        : advanced >= frame->limit;
            assignment->present = 1;
            assignment->key = frame->key;
            assignment->value.type = (uint8_t)BVT_INTEGER;
            assignment->value.data.integer = (int16_t)advanced;
            if (keep_loop) {
                *next = frame->loop_cursor;
                flow->next_statement = frame->loop_statement;
            } else {
                flow->for_action = BE_FOR_POP;
                if (pos < length) {
                    *next = line->offset;
                    flow->next_statement = for_next_continuation(body, length, pos);
                } else {
                    *next = line->next_offset;
                }
            }
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
        preceding_statement = 1;
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
    executor->statement_offset = 0u;
    executor->call_depth = 0u;
    memset(executor->call_stack, 0, sizeof(executor->call_stack));
    executor->for_depth = 0u;
    memset(executor->for_stack, 0, sizeof(executor->for_stack));
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
    BEFlow transition = {0}, second_transition = {0};
    BasicVariableStore *variables;
    size_t entry_bytes = 0u;
    BEEmitter writer;
    size_t next = 0u;
    size_t check_next = 0u;
    BPStatus bp_status;
    BEStatus status;
    size_t current;
    size_t start_pos;

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
    if (executor->for_depth > BE_FOR_STACK_CAPACITY) {
        return BE_BAD_PROGRAM;
    }
    if (executor->call_depth > BE_GOSUB_STACK_CAPACITY) {
        return BE_BAD_PROGRAM;
    }
    current = executor->cursor;
    start_pos = executor->statement_offset;
    bp_status = bp_next(program, &current, &line);
    if (bp_status == BP_END) {
        return BE_END;
    }
    if (bp_status != BP_OK) {
        return BE_BAD_PROGRAM;
    }
    if (start_pos >= line.body_length && start_pos != 0u) {
        return BE_BAD_PROGRAM;
    }
    status = execute_line(program, &line, start_pos, executor,
                          &probe, &next, &transition, variables, &assignment);
    if (status != BE_OK) {
        return status;
    }
    /* Before the output-writing pass, preflight the only possible store
     * commit failure (full entries). This also protects PRINT:FOR lines. */
    if (assignment.present) {
        size_t index;
        BVSStatus lookup = bvs_find(variables, &assignment.key, &index);
        if (lookup == BVS_NOT_FOUND && variables->count == variables->capacity)
            return BE_STORE_FULL;
        if (lookup != BVS_OK && lookup != BVS_NOT_FOUND)
            return store_error(lookup);
    }
    if (probe.length > output_capacity) {
        return BE_NO_SPACE;
    }
    writer.data = output;
    writer.length = 0u;
    status = execute_line(program, &line, start_pos, executor,
                          &writer, &check_next, &second_transition,
                          variables, &second);
    if (status != BE_OK || writer.length != probe.length || check_next != next ||
        transition.action != second_transition.action ||
        transition.next_statement != second_transition.next_statement ||
        transition.frame.cursor != second_transition.frame.cursor ||
        transition.frame.statement_offset != second_transition.frame.statement_offset ||
        transition.for_action != second_transition.for_action ||
        (transition.for_action == BE_FOR_PUSH &&
         (!for_same_key(&transition.for_frame.key, &second_transition.for_frame.key) ||
          transition.for_frame.limit != second_transition.for_frame.limit ||
          transition.for_frame.step != second_transition.for_frame.step ||
          transition.for_frame.loop_cursor != second_transition.for_frame.loop_cursor ||
          transition.for_frame.loop_statement != second_transition.for_frame.loop_statement ||
          transition.for_frame.after_cursor != second_transition.for_frame.after_cursor ||
          transition.for_frame.after_statement != second_transition.for_frame.after_statement)) ||
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
    /* One committed stack action, after both pure passes completed. */
    if (transition.action == BE_FLOW_PUSH) {
        executor->call_stack[executor->call_depth++] = transition.frame;
    } else if (transition.action == BE_FLOW_POP) {
        --executor->call_depth;
        memset(&executor->call_stack[executor->call_depth], 0,
               sizeof(executor->call_stack[0]));
    } else if (transition.action == BE_FLOW_CLEAR) {
        executor->call_depth = 0u;
        memset(executor->call_stack, 0, sizeof(executor->call_stack));
    }
    if (transition.for_action == BE_FOR_PUSH) {
        executor->for_stack[executor->for_depth++] = transition.for_frame;
    } else if (transition.for_action == BE_FOR_POP) {
        --executor->for_depth;
        memset(&executor->for_stack[executor->for_depth], 0,
               sizeof(executor->for_stack[0]));
    }
    if (transition.action == BE_FLOW_CLEAR) {
        executor->for_depth = 0u;
        memset(executor->for_stack, 0, sizeof(executor->for_stack));
    }
    *written = writer.length;
    executor->statement_offset = transition.next_statement;
    executor->cursor = next;
    return BE_OK;
}
