/* HW4-DIAG-A / SYNTAX-A: exact CPC wording with strictly bounded origins. */
#include "cpc_diag_policy.h"
#include "basic_variable_ref.h"
#include "basic_variable_binding.h"
#include <string.h>

static bool numbered_deletion(const uint8_t *source,size_t length)
{
    size_t i=0U;
    unsigned number=0U;
    if(source==NULL || length==0U || source[0]<'0' || source[0]>'9')
        return false;
    while(i<length && source[i]>='0' && source[i]<='9') {
        unsigned digit=(unsigned)(source[i]-'0');
        if(number>(65535U-digit)/10U) return false;
        number=number*10U+digit;
        ++i;
    }
    if(number==0U) return false;
    while(i<length && source[i]==' ') ++i;
    return i==length;
}

/* Direct syntax is selected from the typed CORE result only.
 * Do not reparse command names here: BS_UNSUPPORTED_DIRECT includes valid
 * non-executable CPC keywords and ambiguous input. */
CpcDiagCategory cpc_diag_policy_select(const uint8_t *source,size_t length,
                                       BSRResult result)
{
    if(result.status==BSR_SESSION_ERROR &&
       result.session.status==BS_NOT_FOUND &&
       result.session.tokenizer_status==BT_OK &&
       result.session.program_status==BP_OK &&
       result.session.listing_status==BL_OK &&
       numbered_deletion(source,length))
        return CPC_DIAG_LINE_DOES_NOT_EXIST;
    if(source!=NULL && length!=0U &&
       result.status==BSR_SESSION_ERROR &&
       result.session.status==BS_UNKNOWN_DIRECT &&
       result.session.tokenizer_status==BT_OK &&
       result.session.program_status==BP_OK &&
       result.session.listing_status==BL_OK)
        return CPC_DIAG_DIRECT_UNKNOWN_SYNTAX;
    return CPC_DIAG_HOST_GENERIC;
}

const char *cpc_diag_policy_category(CpcDiagCategory category)
{
    switch(category) {
        case CPC_DIAG_HOST_GENERIC: return "HOST_GENERIC";
        case CPC_DIAG_LINE_DOES_NOT_EXIST: return "NUMBERED_DELETE_ABSENT";
        case CPC_DIAG_PEN_IMPROPER_ARGUMENT: return "PEN_IMPROPER_ARGUMENT_CPC";
        case CPC_DIAG_GOSUB_MISSING_TARGET: return "GOSUB_MISSING_TARGET_CPC";
        case CPC_DIAG_RETURN_UNEXPECTED: return "RETURN_UNEXPECTED_CPC";
        case CPC_DIAG_NEXT_UNEXPECTED: return "NEXT_UNEXPECTED_CPC";
        case CPC_DIAG_DIVISION_INTEGER_ZERO: return "INTEGER_F9_DIVISION_BY_ZERO_CPC";
        case CPC_DIAG_GOTO_MISSING_TARGET: return "GOTO_MISSING_TARGET_CPC";
        case CPC_DIAG_IF_MISSING_TARGET: return "IF_TAKEN_MISSING_TARGET_CPC";
        case CPC_DIAG_DIRECT_UNKNOWN_SYNTAX: return "DIRECT_UNKNOWN_SYNTAX_CORE_LEXICAL";
        case CPC_DIAG_WEND_UNEXPECTED: return "WEND_UNEXPECTED_CPC";
        case CPC_DIAG_WHILE_WEND_MISSING: return "WHILE_WEND_MISSING_CPC";
        case CPC_DIAG_WHILE_OPERAND_MISSING: return "WHILE_OPERAND_MISSING_CPC";
        case CPC_DIAG_INTEGER_OVERFLOW: return "INTEGER_BINARY_OVERFLOW_CPC";
        case CPC_DIAG_MOD_ZERO: return "INTEGER_FB_DIVISION_BY_ZERO_CPC";
        case CPC_DIAG_INK_IMPROPER_ARGUMENT: return "INK_IMPROPER_ARGUMENT_CPC";
        case CPC_DIAG_PAPER_IMPROPER_ARGUMENT: return "PAPER_IMPROPER_ARGUMENT_CPC";
        case CPC_DIAG_LOCATE_IMPROPER_ARGUMENT: return "LOCATE_IMPROPER_ARGUMENT_CPC";
        case CPC_DIAG_BORDER_IMPROPER_ARGUMENT: return "BORDER_IMPROPER_ARGUMENT_CPC";
        case CPC_DIAG_BORDER_OPERAND_MISSING: return "BORDER_OPERAND_MISSING_CPC";
        case CPC_DIAG_COUNT: break;
    }
    return "INVALID_DIAGNOSTIC";
}

const char *cpc_diag_policy_message(CpcDiagCategory category)
{
    switch(category) {
        case CPC_DIAG_HOST_GENERIC: return "ERROR";
        case CPC_DIAG_LINE_DOES_NOT_EXIST: return "Line does not exist";
        case CPC_DIAG_PEN_IMPROPER_ARGUMENT: return "Improper argument";
        case CPC_DIAG_GOSUB_MISSING_TARGET: return "Line does not exist";
        case CPC_DIAG_RETURN_UNEXPECTED: return "Unexpected RETURN";
        case CPC_DIAG_NEXT_UNEXPECTED: return "Unexpected NEXT";
        case CPC_DIAG_DIVISION_INTEGER_ZERO: return "Division by zero";
        case CPC_DIAG_GOTO_MISSING_TARGET: return "Line does not exist";
        case CPC_DIAG_IF_MISSING_TARGET: return "Line does not exist";
        case CPC_DIAG_DIRECT_UNKNOWN_SYNTAX: return "Syntax error";
        case CPC_DIAG_WEND_UNEXPECTED: return "Unexpected WEND";
        case CPC_DIAG_WHILE_WEND_MISSING: return "WEND missing";
        case CPC_DIAG_WHILE_OPERAND_MISSING: return "Operand missing";
        case CPC_DIAG_INTEGER_OVERFLOW: return "Overflow";
        case CPC_DIAG_MOD_ZERO: return "Division by zero";
        case CPC_DIAG_INK_IMPROPER_ARGUMENT: return "Improper argument";
        case CPC_DIAG_PAPER_IMPROPER_ARGUMENT: return "Improper argument";
        case CPC_DIAG_LOCATE_IMPROPER_ARGUMENT: return "Improper argument";
        case CPC_DIAG_BORDER_IMPROPER_ARGUMENT: return "Improper argument";
        case CPC_DIAG_BORDER_OPERAND_MISSING: return "Operand missing";
        case CPC_DIAG_COUNT: break;
    }
    return "INVALID_DIAGNOSTIC";
}

CpcDirectDiagOrigin cpc_diag_policy_direct_origin(CpcDiagCategory category)
{
    return category==CPC_DIAG_DIRECT_UNKNOWN_SYNTAX
           ? CPC_DIRECT_DIAG_ORIGIN_CORE_UNKNOWN_LEXICAL : CPC_DIRECT_DIAG_ORIGIN_HOST;
}

/* Literal "Syntax error" is the CPC ROM error-table wording:
 * basic.asm CB49: LD A,$02; CD98: "Syntax" + compressed " error".
 * Only the CORE lexical flag selects this display category; it does NOT
 * independently prove the ROM's direct-command error path or ERR/ERL. */
bool cpc_diag_policy_format_direct(CpcDiagCategory category,
                                   uint8_t *output, size_t capacity,
                                   size_t *written)
{
    static const uint8_t generic[]="ERROR\n";
    static const uint8_t line_absent[]="Line does not exist\n";
    static const uint8_t syntax[]="Syntax error\n";
    const uint8_t *bytes;
    size_t n;
    if(output==NULL || written==NULL) return false;
    switch(category) {
        case CPC_DIAG_HOST_GENERIC:
            bytes=generic; n=sizeof(generic)-1U; break;
        case CPC_DIAG_LINE_DOES_NOT_EXIST:
            bytes=line_absent; n=sizeof(line_absent)-1U; break;
        case CPC_DIAG_DIRECT_UNKNOWN_SYNTAX:
            bytes=syntax; n=sizeof(syntax)-1U; break;
        default: return false;
    }
    if(capacity<n) return false;
    memcpy(output,bytes,n);
    *written=n;
    return true;
}

bool cpc_diag_policy_write(CpcText *text,CpcDiagCategory category)
{
    uint8_t bytes[sizeof("Line does not exist\n")];
    size_t n=0U;
    if(text==NULL ||
       !cpc_diag_policy_format_direct(category,bytes,sizeof(bytes),&n))
        return false;
    return cpc_text_write(text,bytes,n);
}

/* Identify the first potentially failing flow statement actually reached
 * from this executor's continuation. Do not search raw bytes for GOSUB:
 * CPC tokenised bodies contain quoted text, cached variable references and
 * numeric payloads that may themselves contain opcode/separator byte values.
 * A preceding IF/GOTO is an independent missing-target origin. On an
 * unrecognised/ambiguous prefix, return 0 (host diagnostic), not a CPC claim.
 * No execution, store lookup, allocation or mutation occurs here. */
static uint8_t reached_flow(const BasicProgram *program,
                            const BasicProgramLine *line, size_t at,
                            size_t *flow_at)
{
    const uint8_t *body=program->data+line->body_offset;
    const size_t length=line->body_length;
    while(at<length) {
        size_t p;
        bool quoted=false, separated=false;
        while(at<length && body[at]==' ') ++at;
        if(at==length) break;
        if(body[at]==0x9fu || body[at]==0xa0u ||
           body[at]==0xa1u || body[at]==0xc9u) {
            if(flow_at != NULL) *flow_at = at;
            return body[at]; /* GOSUB, GOTO, IF, RETURN respectively */
        }
        if(body[at]==0xc5u ||
           (body[at]==0x01u && at+1U<length && body[at+1U]==0xc0u))
            return 0U; /* REM or apostrophe */
        p=at;
        while(p<length) {
            const uint8_t token=body[p++];
            if(token==(uint8_t)'"') {
                quoted=!quoted;
                continue;
            }
            if(quoted) continue;
            if(token==0xc5u) return 0U;
            if(token==0x01u) {
                if(p<length && body[p]==0xc0u) return 0U;
                at=p;
                separated=true;
                break;
            }
            if((token>=0x02u && token<=0x04u) ||
               (token>=0x0bu && token<=0x0du)) {
                BasicVariableRef reference;
                if(bvr_decode(body,length,p-1U,&reference)!=BVR_OK ||
                   reference.consumed==0U ||
                   reference.consumed>length-(p-1U)) return 0U;
                p=p-1U+reference.consumed;
            } else {
                const size_t payload=token==0x19u ? 1U :
                    (token>=0x1au && token<=0x1eu) ? 2U :
                    token==0x1fu ? 5U : 0U;
                if(payload>length-p) return 0U;
                p+=payload;
            }
        }
        if(quoted || !separated) return 0U;
    }
    return 0U;
}

/* A1b fault-localisation is a read-only lexical consultation, intentionally
 * hosted in the diagnostic module. CI-ARCH prohibits a PR changing core/
 * and io/ together; the executor and its existing FOR/NEXT contract stay
 * untouched. No status-only mapping or search for raw B0 bytes is allowed.
 * This scanner mirrors for_match's statement-start, reference and literal
 * skipping. It cannot execute BASIC or change any referenced object. */

static void next_skip_spaces(const uint8_t *b, size_t n, size_t *at)
{
    while (*at < n && b[*at] == (uint8_t)' ') ++*at;
}

static bool next_key_equal(const BasicVariableKey *a,
                           const BasicVariableKey *b)
{
    return a->type == b->type && a->name_length == b->name_length &&
           memcmp(a->name, b->name, a->name_length) == 0;
}

static bool next_reference(const uint8_t *b, size_t n, size_t *at,
                           BasicVariableKey *key)
{
    size_t used = 0U;
    if (*at >= n ||
        bvb_resolve_explicit(b, n, *at, key, &used) != BVB_OK ||
        key->type != (uint8_t)BVT_INTEGER || used > n - *at)
        return false;
    *at += used;
    return true;
}

/* Advance past one statement's payload, stopping just after a true colon.
 * Quoted strings, comments, reference caches and numeric payloads are opaque;
 * a malformed sequence fails closed. A finished line returns pos == n. */
static bool next_skip_statement(const uint8_t *b, size_t n, size_t *at)
{
    bool quoted = false;
    while (*at < n) {
        uint8_t token = b[*at];
        if (token == (uint8_t)'"') {
            quoted = !quoted;
            ++*at;
        } else if (quoted) {
            ++*at;
        } else if (token == 0xc5u ||
                   (token == 0x01u && *at + 1U < n && b[*at + 1U] == 0xc0u)) {
            *at = n;
            return true;
        } else if (token == 0x01u) {
            ++*at;
            return true;
        } else if ((token >= 0x02u && token <= 0x04u) ||
                   (token >= 0x0bu && token <= 0x0du)) {
            BasicVariableRef ref;
            if (bvr_decode(b, n, *at, &ref) != BVR_OK ||
                ref.consumed == 0U || ref.consumed > n - *at)
                return false;
            *at += ref.consumed;
        } else if (token == 0x19u || token == 0x1au ||
                   token == 0x1du || token == 0x1eu || token == 0x1fu) {
            size_t payload = token == 0x19u ? 1U : (token == 0x1fu ? 5U : 2U);
            if (n - *at <= payload) return false;
            *at += payload + 1U;
        } else {
            ++*at;
        }
    }
    return !quoted;
}

/* This is the same fixed-depth structural walk as core::for_match.
 * The offending NEXT's BasicProgramLine.number is returned when its
 * explicit variable contradicts the currently expected loop variable. */
static bool next_scan_from_for(const BasicProgram *program,
                               const BasicProgramLine *first,
                               size_t pos, const BasicVariableKey *wanted,
                               uint16_t *line_number)
{
    BasicVariableKey nested[BE_FOR_STACK_CAPACITY];
    size_t depth = 0U, cursor = first->offset;
    bool first_line = true;
    BasicProgramLine line;
    BPStatus status;
    const uint8_t *initial = program->data + first->body_offset;
    if (!next_skip_statement(initial, first->body_length, &pos)) return false;
    while ((status = bp_next(program, &cursor, &line)) == BP_OK) {
        const uint8_t *body = program->data + line.body_offset;
        size_t n = line.body_length;
        if (!first_line) pos = 0U;
        first_line = false;
        while (pos < n) {
            uint8_t token;
            next_skip_spaces(body, n, &pos);
            if (pos == n) break;
            token = body[pos++];
            if (token == 0xc5u) break;
            if (token == 0x01u) {
                if (pos < n && body[pos] == 0xc0u) break;
                continue;
            }
            if (token == 0x9eu) {
                if (depth == BE_FOR_STACK_CAPACITY) return false;
                next_skip_spaces(body, n, &pos);
                if (!next_reference(body, n, &pos, &nested[depth]))
                    return false;
                ++depth;
            } else if (token == 0xb0u) {
                BasicVariableKey key;
                const BasicVariableKey *expected =
                    depth == 0U ? wanted : &nested[depth - 1U];
                next_skip_spaces(body, n, &pos);
                if (pos < n && body[pos] == 0x02u) {
                    if (!next_reference(body, n, &pos, &key)) return false;
                    if (!next_key_equal(&key, expected)) {
                        *line_number = line.number;
                        return true;
                    }
                }
                next_skip_spaces(body, n, &pos);
                if (pos < n && body[pos] != 0x01u) return false;
                if (depth == 0U) return false; /* matching NEXT, not an error */
                --depth;
            }
            if (!next_skip_statement(body, n, &pos)) return false;
        }
    }
    return false; /* includes missing NEXT or malformed program */
}

bool cpc_diag_policy_next_locus(const BasicExecutor *executor, BEStatus reason,
                             uint16_t *line_number)
{
    const BasicProgram *program;
    BasicProgramLine line;
    size_t cursor, pos;
    const uint8_t *b;
    uint16_t fault = 0U;
    if (executor == NULL || line_number == NULL ||
        (reason != BE_NEXT_WITHOUT_FOR &&
         reason != BE_NEXT_VARIABLE_MISMATCH))
        return false;
    program = executor->program;
    if (program == NULL || bp_validate(program) != BP_OK ||
        executor->for_depth > BE_FOR_STACK_CAPACITY ||
        executor->call_depth > BE_GOSUB_STACK_CAPACITY)
        return false;
    cursor = executor->cursor;
    if (bp_next(program, &cursor, &line) != BP_OK ||
        line.offset != executor->cursor || line.number == 0U ||
        executor->statement_offset >= line.body_length)
        return false;
    pos = executor->statement_offset;
    b = program->data + line.body_offset;
    while (pos < line.body_length) {
        uint8_t token;
        next_skip_spaces(b, line.body_length, &pos);
        if (pos == line.body_length) break;
        token = b[pos++];
        if (token == 0xb0u) {
            if (reason == BE_NEXT_WITHOUT_FOR &&
                executor->for_depth == 0U) {
                /* The real executor has reported this exact orphan cause. */
                *line_number = line.number;
                return true;
            }
            if (reason == BE_NEXT_VARIABLE_MISMATCH &&
                executor->for_depth != 0U) {
                BasicVariableKey key;
                next_skip_spaces(b, line.body_length, &pos);
                if (pos < line.body_length && b[pos] == 0x02u &&
                    next_reference(b, line.body_length, &pos, &key) &&
                    !next_key_equal(&key,
                        &executor->for_stack[executor->for_depth - 1U].key)) {
                    *line_number = line.number;
                    return true;
                }
            }
            return false;
        }
        if (token == 0x9eu) {
            BasicVariableKey wanted;
            if (reason != BE_NEXT_VARIABLE_MISMATCH) return false;
            next_skip_spaces(b, line.body_length, &pos);
            if (!next_reference(b, line.body_length, &pos, &wanted))
                return false;
            if (next_scan_from_for(program, &line, pos, &wanted, &fault) &&
                fault != 0U) {
                *line_number = fault;
                return true;
            }
            return false;
        }
        if (token == 0xc5u || token == 0x9fu || token == 0xa0u ||
            token == 0xa1u || token == 0xc9u ||
            (token == 0x01u && pos < line.body_length && b[pos] == 0xc0u))
            return false;
        if (!next_skip_statement(b, line.body_length, &pos))
            return false;
    }
    return false;
}

/* A2: a narrow read-only corroboration of the actual reached, tokenised
 * INTEGER assignment. Both F9 (integer division) and FB (MOD) return
 * BE_DIVISION_BY_ZERO, so BEStatus alone cannot license a CPC message.
 * Only the historically witnessed RHS literal zero (canonical 0E) and
 * an existing INTEGER source variable are admitted. Colon continuations,
 * noncanonical encodings, fabricated status/payload and other operators
 * remain host diagnostics. No BASIC evaluation or state change here. */
static void f9_skip_spaces(const uint8_t *body, size_t length, size_t *pos)
{
    while (*pos < length && body[*pos] == (uint8_t)' ') ++*pos;
}

static bool f9_zero_assignment(const BasicSessionRuntime *runtime,
                               const BasicProgramLine *line)
{
    const BasicExecutor *executor = &runtime->executor;
    const uint8_t *body = runtime->program->data + line->body_offset;
    const size_t length = line->body_length;
    size_t pos = 0U, used = 0U;
    BasicVariableKey key;
    BasicVariableValue value;
    if (executor->statement_offset != 0U ||
        runtime->variables == NULL ||
        executor->variables != runtime->variables ||
        bp_validate(runtime->program) != BP_OK)
        return false;
    f9_skip_spaces(body, length, &pos);
    if (pos < length && body[pos] == 0xa5u) { /* optional LET */
        ++pos;
        f9_skip_spaces(body, length, &pos);
    }
    if (pos >= length || body[pos] != 0x02u ||
        bvb_resolve_explicit(body, length, pos, &key, &used) != BVB_OK ||
        key.type != (uint8_t)BVT_INTEGER || used == 0U ||
        used > length - pos)
        return false;
    pos += used;
    f9_skip_spaces(body, length, &pos);
    if (pos >= length || body[pos++] != 0xefu) return false; /* = */
    f9_skip_spaces(body, length, &pos);
    if (pos >= length || body[pos] != 0x02u ||
        bvb_read_explicit(body, length, pos, runtime->variables,
                          &key, &used, &value) != BVB_OK ||
        key.type != (uint8_t)BVT_INTEGER ||
        value.type != (uint8_t)BVT_INTEGER ||
        used == 0U || used > length - pos)
        return false;
    pos += used;
    f9_skip_spaces(body, length, &pos);
    if (pos >= length || body[pos++] != 0xf9u) return false; /* NOT FB */
    f9_skip_spaces(body, length, &pos);
    if (pos >= length || body[pos++] != 0x0eu) return false; /* exact 0 */
    f9_skip_spaces(body, length, &pos);
    return pos == length; /* no second statement, comment, or payload */
}


/* A3: fail-closed, read-only corroboration of an actually failed native
 * assignment, limited to exact original CPC screen witnesses. The two
 * explicit references are decoded through BVR/BVB; caches are opaque to
 * the lexical decoder, but A3 admits only untouched zero-cache native
 * references (no speculative CPC cache semantics). Numeric operands are
 * interpreted only in canonical tokens accepted by the CORE executor.
 * No scan through comments, strings, colon continuations or payloads. */
static bool a3_binary_witness(const BasicSessionRuntime *runtime,
                               const BasicProgramLine *line, BEStatus cause)
{
    const BasicExecutor *executor = &runtime->executor;
    const uint8_t *body = runtime->program->data + line->body_offset;
    const size_t length = line->body_length;
    size_t pos = 0U, used = 0U;
    BasicVariableRef ref;
    BasicVariableKey key;
    BasicVariableValue value;
    int16_t lhs;
    int32_t rhs;
    uint8_t operation, token;
    uint8_t output[1] = {0U};
    BEVideoEvent event[1];
    size_t output_count = 0U, event_count = 0U;

    if ((cause != BE_INTEGER_OVERFLOW && cause != BE_DIVISION_BY_ZERO) ||
        executor->statement_offset != 0U || runtime->variables == NULL ||
        executor->variables != runtime->variables ||
        bp_validate(runtime->program) != BP_OK)
        return false;
    f9_skip_spaces(body, length, &pos);
    /* LET is not among the independent A3 RUN screen witnesses. */
    if (pos < length && body[pos] == 0xa5u) return false;
    if (pos >= length || body[pos] != 0x02u ||
        bvr_decode(body, length, pos, &ref) != BVR_OK ||
        ref.cache_low != 0U || ref.cache_high != 0U ||
        bvb_resolve_explicit(body, length, pos, &key, &used) != BVB_OK ||
        key.type != (uint8_t)BVT_INTEGER || key.name_length != 1U ||
        key.name[0] != (uint8_t)'B' || used == 0U ||
        used > length - pos)
        return false;
    pos += used;
    f9_skip_spaces(body, length, &pos);
    if (pos >= length || body[pos++] != 0xefu) return false; /* = */
    f9_skip_spaces(body, length, &pos);
    if (pos >= length || body[pos] != 0x02u ||
        bvr_decode(body, length, pos, &ref) != BVR_OK ||
        ref.cache_low != 0U || ref.cache_high != 0U ||
        bvb_read_explicit(body, length, pos, runtime->variables,
                          &key, &used, &value) != BVB_OK ||
        key.type != (uint8_t)BVT_INTEGER ||
        value.type != (uint8_t)BVT_INTEGER ||
        key.name_length != 1U || key.name[0] != (uint8_t)'A' ||
        used == 0U || used > length - pos)
        return false;
    lhs = value.data.integer;
    pos += used;
    f9_skip_spaces(body, length, &pos);
    if (pos >= length) return false;
    operation = body[pos++];
    if ((cause == BE_INTEGER_OVERFLOW &&
         operation != 0xf5u && operation != 0xf6u) ||
        (cause == BE_DIVISION_BY_ZERO && operation != 0xfbu))
        return false;
    f9_skip_spaces(body, length, &pos);
    if (pos >= length) return false;
    token = body[pos++];
    if (token >= 0x0eu && token <= 0x17u) {
        rhs = (int32_t)(token - 0x0eu);
    } else if (token == 0x19u && pos < length && body[pos] >= 10U) {
        rhs = (int32_t)body[pos++];
    } else {
        return false;
    }
    f9_skip_spaces(body, length, &pos);
    if (pos != length) return false;
    if (cause == BE_INTEGER_OVERFLOW) {
        if (!((operation == 0xf5u && lhs == INT16_MIN && rhs == 1) ||
              (operation == 0xf6u && lhs == INT16_MAX && rhs == 2) ||
              (operation == 0xf6u && lhs == 255 && rhs == 255)))
            return false;
    } else if (rhs != 0 || (lhs != 0 && lhs != 1)) {
        return false;
    }
    /* A fabricated status or a mutable store no longer matching the real
     * execution cannot promote a host failure to a ROM assertion. */
    return be_preview_step_events((BasicExecutor *)executor,
                output, sizeof output, &output_count,
                event, 1U, &event_count) == cause;
}

/* Reject a forged continuation pointing into an opaque string/reference or
 * numeric payload. The executor itself only resumes at statement boundaries.
 * This lexical walk is read-only and bounded by the stored record. */
static bool o2b_statement_start(const BasicProgram *program,
                                const BasicProgramLine *line, size_t at)
{
    const uint8_t *body = program->data + line->body_offset;
    size_t pos = 0U;
    while (pos < line->body_length) {
        next_skip_spaces(body, line->body_length, &pos);
        if (pos == at) return true;
        if (pos > at || !next_skip_statement(body, line->body_length, &pos))
            return false;
    }
    return false;
}

/* Verify independently of the status enum that the reached instruction
 * actually refers to an absent line. For IF, consult only the existing
 * INTEGER values; never evaluate inline arms, run BASIC or alter the store.
 * This mirrors the already-implemented direct THEN line syntax. */
static bool o2b_missing_target(const BasicSessionRuntime *runtime,
                               const BasicProgramLine *line,
                               size_t at, uint8_t opcode)
{
    const BasicProgram *program = runtime->program;
    const uint8_t *body = program->data + line->body_offset;
    const size_t length = line->body_length;
    size_t pos = at + 1U;
    uint16_t destination;
    BasicProgramLine target;

    if (bp_validate(program) != BP_OK ||
        !o2b_statement_start(program, line, runtime->executor.statement_offset) ||
        at >= length || body[at] != opcode) return false;
    if (opcode == 0xa1u) {
        BasicVariableKey lhs_key;
        BasicVariableValue lhs_value;
        size_t used = 0U;
        int taken;
        if (runtime->variables == NULL ||
            runtime->executor.variables != runtime->variables) return false;
        /* IF cannot be reached after a preceding statement in this executor.
         * At a genuine continuation it must be the first executed token. */
        {
            size_t first = runtime->executor.statement_offset;
            next_skip_spaces(body, length, &first);
            if (first != at) return false;
        }
        next_skip_spaces(body, length, &pos);
        if (pos == length || body[pos] != 0x02u ||
            bvb_read_explicit(body, length, pos, runtime->variables,
                              &lhs_key, &used, &lhs_value) != BVB_OK ||
            lhs_key.type != (uint8_t)BVT_INTEGER ||
            lhs_value.type != (uint8_t)BVT_INTEGER ||
            used > length - pos) return false;
        pos += used;
        taken = lhs_value.data.integer != 0;
        next_skip_spaces(body, length, &pos);
        if (pos == length) return false;
        if (body[pos] == 0xefu || body[pos] == 0xf2u ||
            body[pos] == 0xf1u || body[pos] == 0xf3u ||
            body[pos] == 0xeeu || body[pos] == 0xf0u) {
            const uint8_t rel = body[pos++];
            BasicVariableKey rhs_key;
            BasicVariableValue rhs_value;
            size_t rhs_used = 0U;
            const int16_t lhs = lhs_value.data.integer;
            int16_t rhs;
            next_skip_spaces(body, length, &pos);
            if (pos == length || body[pos] != 0x02u ||
                bvb_read_explicit(body, length, pos, runtime->variables,
                                  &rhs_key, &rhs_used, &rhs_value) != BVB_OK ||
                rhs_key.type != (uint8_t)BVT_INTEGER ||
                rhs_value.type != (uint8_t)BVT_INTEGER ||
                rhs_used > length - pos) return false;
            rhs = rhs_value.data.integer;
            if (rel == 0xefu) taken = lhs == rhs;
            else if (rel == 0xf2u) taken = lhs != rhs;
            else if (rel == 0xf1u) taken = lhs < rhs;
            else if (rel == 0xf3u) taken = lhs <= rhs;
            else if (rel == 0xeeu) taken = lhs > rhs;
            else taken = lhs >= rhs;
            pos += rhs_used;
            next_skip_spaces(body, length, &pos);
        }
        if (!taken || pos == length || body[pos++] != 0xebu)
            return false; /* THEN */
    } else if (opcode != 0xa0u) {
        return false;
    }
    {
        const size_t argument_start = pos;
        next_skip_spaces(body, length, &pos);
        /* GOTO executor requires a space before 1E; IF does not. */
        if (pos == length || body[pos++] != 0x1eu ||
            (opcode == 0xa0u && pos - 1U == argument_start) ||
            length - pos < 2U) return false;
    }
    destination = (uint16_t)((uint16_t)body[pos] |
                  ((uint16_t)body[pos + 1U] << 8));
    pos += 2U;
    if (destination == 0U) return false;
    next_skip_spaces(body, length, &pos);
    if (opcode == 0xa1u) {
        if (pos != length) return false;
    } else if (pos < length && body[pos] != 0x01u) {
        return false;
    }
    return bp_find(program, destination, &target) == BP_NOT_FOUND;
}

/* J1.24-B3: corroborate an actual failed WHILE/WEND step without
 * converting a caller-supplied BEStatus into alleged CPC evidence.
 * The CORE preview API is read-only by contract, uses caller-owned tiny
 * staging buffers and never commits a BASIC step. WHILE/WEND fail before
 * emitting any output or video event. A future compound form requiring
 * staging capacity will fail closed as a HOST diagnostic instead.
 * The CORE helper supplies the real line, including prevalidated errors;
 * neither a raw token search nor a cursor-derived line is sufficient. */
static bool while_wend_locus(const BasicSessionRuntime *runtime,
                             const BasicProgramLine *line, BEStatus cause,
                             uint16_t *line_number)
{
    const BasicExecutor *executor = &runtime->executor;
    const uint8_t *body = runtime->program->data + line->body_offset;
    size_t at = executor->statement_offset;
    uint8_t output[1] = {0U};
    BEVideoEvent event[1];
    size_t output_count = 0U, event_count = 0U;
    uint8_t opcode;
    if (runtime->variables != executor->variables ||
        !o2b_statement_start(runtime->program, line, at))
        return false;
    next_skip_spaces(body, line->body_length, &at);
    if (at >= line->body_length) return false;
    opcode = cause == BE_WEND_WITHOUT_WHILE ? 0xd5u : 0xd6u;
    if (body[at] != opcode) return false;
    /* The historical signature is BasicExecutor* although the preview
     * itself leaves the executor, store and program byte-identical. */
    if (be_preview_step_events((BasicExecutor *)executor,
             output, sizeof output, &output_count,
             event, 1U, &event_count) != cause)
        return false;
    if (be_while_diagnostic_line(executor, cause, line_number) != BE_OK ||
        *line_number == 0U)
        return false;
    return true;
}


/* A4: the entire reached CPC statement must be exactly a sealed original
 * AND repeat screen witness. This is not an opcode/ERR lookup: it disallows
 * forged cache words, a colon continuation, REM/quoted tokens, extra
 * operands, different values, and direct input. A noncommitting native
 * preview additionally checks that the reported BE cause is genuine. */
typedef struct {
    const uint8_t *record;
    size_t length;
    BEStatus cause;
    CpcDiagCategory category;
    CpcDiagOrigin origin;
} A4GraphicWitness;

static bool a4_graphic_witness(const BasicSessionRuntime *runtime,
                               const BasicProgramLine *line, BEStatus cause,
                               CpcStepDiagnostic *diagnostic)
{
    static const uint8_t i1626[] = {0xa2u,0x20u,0x19u,0x10u,0x2cu,0x19u,0x1au};
    static const uint8_t in126[] = {0xa2u,0x20u,0xf5u,0x0fu,0x2cu,0x19u,0x1au};
    static const uint8_t i132[] = {0xa2u,0x20u,0x0fu,0x2cu,0x19u,0x20u};
    static const uint8_t i1n1[] = {0xa2u,0x20u,0x0fu,0x2cu,0xf5u,0x0fu};
    static const uint8_t p16[] = {0xbau,0x20u,0x19u,0x10u};
    static const uint8_t pn1[] = {0xbau,0x20u,0xf5u,0x0fu};
    static const uint8_t l001[] = {0xa9u,0x20u,0x0eu,0x2cu,0x0fu};
    static const uint8_t l010[] = {0xa9u,0x20u,0x0fu,0x2cu,0x0eu};
    static const uint8_t ln11[] = {0xa9u,0x20u,0xf5u,0x0fu,0x2cu,0x0fu};
    static const uint8_t bn[] = {0x82u,0x20u,0xf5u,0x0fu};
    static const uint8_t bn1[] = {0x82u,0x20u,0xf5u,0x0fu,0x2cu,0x0fu};
    static const uint8_t bm[] = {0x82u,0x20u,0x0fu,0x2cu};
#define A4W(bytes, reason, kind, source) \
    {bytes, sizeof(bytes), reason, kind, source}
    static const A4GraphicWitness verified[] = {
        A4W(i1626, BE_INVALID_INK, CPC_DIAG_INK_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_INK_CPC_ORACLE),
        A4W(in126, BE_INVALID_INK, CPC_DIAG_INK_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_INK_CPC_ORACLE),
        A4W(i132, BE_INVALID_INK, CPC_DIAG_INK_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_INK_CPC_ORACLE),
        A4W(i1n1, BE_INVALID_INK, CPC_DIAG_INK_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_INK_CPC_ORACLE),
        A4W(p16, BE_INVALID_PAPER, CPC_DIAG_PAPER_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_PAPER_CPC_ORACLE),
        A4W(pn1, BE_INVALID_PAPER, CPC_DIAG_PAPER_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_PAPER_CPC_ORACLE),
        A4W(l001, BE_INVALID_LOCATE, CPC_DIAG_LOCATE_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_LOCATE_CPC_ORACLE),
        A4W(l010, BE_INVALID_LOCATE, CPC_DIAG_LOCATE_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_LOCATE_CPC_ORACLE),
        A4W(ln11, BE_INVALID_LOCATE, CPC_DIAG_LOCATE_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_LOCATE_CPC_ORACLE),
        A4W(bn, BE_INVALID_BORDER, CPC_DIAG_BORDER_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_BORDER_CPC_ORACLE),
        A4W(bn1, BE_INVALID_BORDER, CPC_DIAG_BORDER_IMPROPER_ARGUMENT,
            CPC_DIAG_ORIGIN_NATIVE_BORDER_CPC_ORACLE),
        A4W(bm, BE_OPERAND_MISSING, CPC_DIAG_BORDER_OPERAND_MISSING,
            CPC_DIAG_ORIGIN_NATIVE_BORDER_CPC_ORACLE)
    };
#undef A4W
    const uint8_t *body;
    const BasicExecutor *executor;
    uint8_t output[1] = {0u};
    BEVideoEvent event[1];
    size_t output_count = 0u, event_count = 0u;
    size_t i;

    if (runtime == NULL || line == NULL || diagnostic == NULL ||
        runtime->program == NULL || runtime->executor.program != runtime->program ||
        runtime->executor.statement_offset != 0u ||
        runtime->executor.variables != runtime->variables ||
        bp_validate(runtime->program) != BP_OK)
        return false;
    executor = &runtime->executor;
    body = runtime->program->data + line->body_offset;
    for (i = 0u; i < sizeof(verified) / sizeof(verified[0]); ++i) {
        const A4GraphicWitness *w = &verified[i];
        if (cause == w->cause && line->body_length == w->length &&
            memcmp(body, w->record, w->length) == 0) {
            if (be_preview_step_events((BasicExecutor *)executor,
                        output, sizeof output, &output_count,
                        event, 1u, &event_count) != cause)
                return false;
            diagnostic->category = w->category;
            diagnostic->origin = w->origin;
            diagnostic->line_number = line->number;
            return true;
        }
    }
    return false;
}

/* bsr_step_events() preserves failed cursor, output and RUNNING state.
 * Resolve from the real stored record BEFORE bsr_stop(), with no side
 * effects. Status numbers are host enums, never historical CPC ERR codes. */
CpcStepDiagnostic cpc_diag_policy_step(BSRResult result,
                                        const BasicSessionRuntime *runtime)
{
    CpcStepDiagnostic diagnostic={
        CPC_DIAG_HOST_GENERIC, CPC_DIAG_ORIGIN_HOST, 0U
    };
    BasicProgramLine line;
    size_t cursor;
    uint8_t flow;
    size_t flow_at = 0U;
    uint16_t next_line = 0u;
    if(result.status!=BSR_EXECUTOR_ERROR ||
       runtime==NULL || runtime->state!=BSR_RUNNING ||
       runtime->program==NULL || runtime->executor.program!=runtime->program)
        return diagnostic;
    /* Never treat an arbitrary executor rejection as a ROM diagnostic. */
    if(result.executor_status!=BE_INVALID_PEN &&
       result.executor_status!=BE_MISSING_TARGET &&
       result.executor_status!=BE_RETURN_WITHOUT_GOSUB &&
       result.executor_status!=BE_NEXT_WITHOUT_FOR &&
       result.executor_status!=BE_NEXT_VARIABLE_MISMATCH &&
       result.executor_status!=BE_DIVISION_BY_ZERO &&
       result.executor_status!=BE_INTEGER_OVERFLOW &&
       result.executor_status!=BE_WEND_WITHOUT_WHILE &&
       result.executor_status!=BE_WHILE_WITHOUT_WEND &&
       result.executor_status!=BE_WHILE_OPERAND_MISSING &&
       result.executor_status!=BE_INVALID_INK &&
       result.executor_status!=BE_INVALID_PAPER &&
       result.executor_status!=BE_INVALID_LOCATE &&
       result.executor_status!=BE_INVALID_BORDER &&
       result.executor_status!=BE_OPERAND_MISSING)
        return diagnostic;

    cursor=runtime->executor.cursor;
    if(bp_next(runtime->program,&cursor,&line)!=BP_OK ||
       line.offset!=runtime->executor.cursor || line.number==0U ||
       runtime->executor.statement_offset>=line.body_length)
        return diagnostic;
    if (result.executor_status == BE_INVALID_INK ||
        result.executor_status == BE_INVALID_PAPER ||
        result.executor_status == BE_INVALID_LOCATE ||
        result.executor_status == BE_INVALID_BORDER ||
        result.executor_status == BE_OPERAND_MISSING) {
        /* Host origin unless the identical native failed step, token
         * stream, actual numbered line and original/repeat CPC witness
         * all agree. No direct-source or renderer status is accepted. */
        (void)a4_graphic_witness(runtime, &line,
                                 result.executor_status, &diagnostic);
        return diagnostic;
    }
    if (result.executor_status == BE_WEND_WITHOUT_WHILE ||
        result.executor_status == BE_WHILE_WITHOUT_WEND ||
        result.executor_status == BE_WHILE_OPERAND_MISSING) {
        uint16_t real_line = 0U;
        if (!while_wend_locus(runtime, &line,
                             result.executor_status, &real_line))
            return diagnostic;
        diagnostic.category =
            result.executor_status == BE_WEND_WITHOUT_WHILE ?
                CPC_DIAG_WEND_UNEXPECTED :
            result.executor_status == BE_WHILE_WITHOUT_WEND ?
                CPC_DIAG_WHILE_WEND_MISSING :
                CPC_DIAG_WHILE_OPERAND_MISSING;
        diagnostic.origin = CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE;
        diagnostic.line_number = real_line;
        return diagnostic;
    }
    if(result.executor_status==BE_DIVISION_BY_ZERO) {
        if (f9_zero_assignment(runtime,&line)) {
            diagnostic.category=CPC_DIAG_DIVISION_INTEGER_ZERO;
            diagnostic.origin=CPC_DIAG_ORIGIN_NATIVE_F9_ZERO_CPC_ORACLE;
        } else if (a3_binary_witness(runtime,&line,BE_DIVISION_BY_ZERO)) {
            diagnostic.category=CPC_DIAG_MOD_ZERO;
            diagnostic.origin=CPC_DIAG_ORIGIN_NATIVE_FB_ZERO_CPC_ORACLE;
        } else {
            return diagnostic;
        }
        diagnostic.line_number=line.number;
        return diagnostic;
    }
    if (result.executor_status==BE_INTEGER_OVERFLOW) {
        if (!a3_binary_witness(runtime,&line,BE_INTEGER_OVERFLOW))
            return diagnostic;
        diagnostic.category=CPC_DIAG_INTEGER_OVERFLOW;
        diagnostic.origin=CPC_DIAG_ORIGIN_NATIVE_F5_F6_OVERFLOW_CPC_ORACLE;
        diagnostic.line_number=line.number;
        return diagnostic;
    }
    if(result.executor_status==BE_NEXT_WITHOUT_FOR ||
       result.executor_status==BE_NEXT_VARIABLE_MISMATCH) {
        /* Reproduce the exact failed probe against the unchanged executor,
         * including for_match's real offending NEXT record. No guessing
         * from the FOR cursor, no raw token scan or status-only mapping. */
        if(!cpc_diag_policy_next_locus(&runtime->executor,
                             result.executor_status,&next_line))
            return diagnostic;
        diagnostic.category=CPC_DIAG_NEXT_UNEXPECTED;
        diagnostic.origin=CPC_DIAG_ORIGIN_NATIVE_NEXT_CPC_ORACLE;
        diagnostic.line_number=next_line;
        return diagnostic;
    }
    if(result.executor_status==BE_INVALID_PEN) {
        diagnostic.category=CPC_DIAG_PEN_IMPROPER_ARGUMENT;
        diagnostic.origin=CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE;
    } else {
        flow=reached_flow(runtime->program,&line,
                          runtime->executor.statement_offset,&flow_at);
        if(result.executor_status==BE_MISSING_TARGET && flow==0x9fu) {
            diagnostic.category=CPC_DIAG_GOSUB_MISSING_TARGET;
            diagnostic.origin=CPC_DIAG_ORIGIN_NATIVE_GOSUB_CPC_ORACLE;
        } else if(result.executor_status==BE_MISSING_TARGET &&
                  (flow==0xa0u || flow==0xa1u) &&
                  o2b_missing_target(runtime,&line,flow_at,flow)) {
            diagnostic.category=flow==0xa0u ?
                CPC_DIAG_GOTO_MISSING_TARGET : CPC_DIAG_IF_MISSING_TARGET;
            diagnostic.origin=flow==0xa0u ?
                CPC_DIAG_ORIGIN_NATIVE_GOTO_CPC_ORACLE :
                CPC_DIAG_ORIGIN_NATIVE_IF_CPC_ORACLE;
        } else if(result.executor_status==BE_RETURN_WITHOUT_GOSUB &&
                  flow==0xc9u) {
            diagnostic.category=CPC_DIAG_RETURN_UNEXPECTED;
            diagnostic.origin=CPC_DIAG_ORIGIN_NATIVE_RETURN_CPC_ORACLE;
        } else {
            return diagnostic;
        }
    }
    diagnostic.line_number=line.number;
    return diagnostic;
}

/* Format exactly the witnessed CPC spelling, including ASCII decimal line
 * and LF. An invalid provenance/line cannot silently become a CPC claim. */
bool cpc_diag_policy_format_step(CpcStepDiagnostic diagnostic,
                                  uint8_t *output, size_t capacity,
                                  size_t *written)
{
    static const uint8_t generic[]="ERROR\n";
    static const uint8_t pen_prefix[]="Improper argument in ";
    static const uint8_t gosub_prefix[]="Line does not exist in ";
    static const uint8_t return_prefix[]="Unexpected RETURN in ";
    static const uint8_t next_prefix[]="Unexpected NEXT in ";
    static const uint8_t f9_prefix[]="Division by zero in ";
    static const uint8_t overflow_prefix[]="Overflow in ";
    static const uint8_t wend_prefix[]="Unexpected WEND in ";
    static const uint8_t missing_wend_prefix[]="WEND missing in ";
    static const uint8_t operand_prefix[]="Operand missing in ";
    const uint8_t *prefix=NULL;
    size_t prefix_length=0U;
    uint8_t digits[5];
    size_t count=0U, n=0U;
    uint16_t number=diagnostic.line_number;
    if(output==NULL || written==NULL) return false;
    if(diagnostic.category==CPC_DIAG_HOST_GENERIC &&
       diagnostic.origin==CPC_DIAG_ORIGIN_HOST &&
       diagnostic.line_number==0U) {
        if(capacity<sizeof(generic)-1U) return false;
        memcpy(output,generic,sizeof(generic)-1U);
        *written=sizeof(generic)-1U;
        return true;
    }
    if(number==0U) return false;
    if(diagnostic.category==CPC_DIAG_PEN_IMPROPER_ARGUMENT &&
       diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE) {
        prefix=pen_prefix;
        prefix_length=sizeof(pen_prefix)-1U;
    } else if((diagnostic.category==CPC_DIAG_GOSUB_MISSING_TARGET &&
               diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_GOSUB_CPC_ORACLE) ||
              (diagnostic.category==CPC_DIAG_GOTO_MISSING_TARGET &&
               diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_GOTO_CPC_ORACLE) ||
              (diagnostic.category==CPC_DIAG_IF_MISSING_TARGET &&
               diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_IF_CPC_ORACLE)) {
        prefix=gosub_prefix;
        prefix_length=sizeof(gosub_prefix)-1U;
    } else if(diagnostic.category==CPC_DIAG_RETURN_UNEXPECTED &&
              diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_RETURN_CPC_ORACLE) {
        prefix=return_prefix;
        prefix_length=sizeof(return_prefix)-1U;
    } else if(diagnostic.category==CPC_DIAG_NEXT_UNEXPECTED &&
              diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_NEXT_CPC_ORACLE) {
        prefix=next_prefix;
        prefix_length=sizeof(next_prefix)-1U;
    } else if(diagnostic.category==CPC_DIAG_DIVISION_INTEGER_ZERO &&
              diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_F9_ZERO_CPC_ORACLE) {
        prefix=f9_prefix;
        prefix_length=sizeof(f9_prefix)-1U;
    } else if(diagnostic.category==CPC_DIAG_MOD_ZERO &&
              diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_FB_ZERO_CPC_ORACLE) {
        prefix=f9_prefix;
        prefix_length=sizeof(f9_prefix)-1U;
    } else if(diagnostic.category==CPC_DIAG_INTEGER_OVERFLOW &&
              diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_F5_F6_OVERFLOW_CPC_ORACLE) {
        prefix=overflow_prefix;
        prefix_length=sizeof(overflow_prefix)-1U;
    } else if(((diagnostic.category==CPC_DIAG_INK_IMPROPER_ARGUMENT &&
                diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_INK_CPC_ORACLE) ||
               (diagnostic.category==CPC_DIAG_PAPER_IMPROPER_ARGUMENT &&
                diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_PAPER_CPC_ORACLE) ||
               (diagnostic.category==CPC_DIAG_LOCATE_IMPROPER_ARGUMENT &&
                diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_LOCATE_CPC_ORACLE) ||
               (diagnostic.category==CPC_DIAG_BORDER_IMPROPER_ARGUMENT &&
                diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_BORDER_CPC_ORACLE))) {
        prefix=pen_prefix;
        prefix_length=sizeof(pen_prefix)-1U;
    } else if(diagnostic.category==CPC_DIAG_BORDER_OPERAND_MISSING &&
              diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_BORDER_CPC_ORACLE) {
        prefix=operand_prefix;
        prefix_length=sizeof(operand_prefix)-1U;
    } else if(diagnostic.category==CPC_DIAG_WEND_UNEXPECTED &&
              diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE) {
        prefix=wend_prefix;
        prefix_length=sizeof(wend_prefix)-1U;
    } else if(diagnostic.category==CPC_DIAG_WHILE_WEND_MISSING &&
              diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE) {
        prefix=missing_wend_prefix;
        prefix_length=sizeof(missing_wend_prefix)-1U;
    } else if(diagnostic.category==CPC_DIAG_WHILE_OPERAND_MISSING &&
              diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE) {
        prefix=operand_prefix;
        prefix_length=sizeof(operand_prefix)-1U;
    } else {
        return false;
    }
    do {
        digits[count++]=(uint8_t)('0'+number%10U);
        number=(uint16_t)(number/10U);
    } while(number!=0U);
    n=prefix_length+count+1U;
    if(capacity<n) return false;
    memcpy(output,prefix,prefix_length);
    for(size_t i=0U;i<count;++i)
        output[prefix_length+i]=digits[count-1U-i];
    output[n-1U]='\n';
    *written=n;
    return true;
}

bool cpc_diag_policy_write_step(CpcText *text, CpcStepDiagnostic diagnostic)
{
    uint8_t bytes[sizeof("Line does not exist in 65535\n")];
    size_t written=0U;
    if(text==NULL || !cpc_diag_policy_format_step(diagnostic,bytes,
                                                 sizeof(bytes),&written))
        return false;
    return cpc_text_write(text,bytes,written);
}
