/* HW4-DIAG-A: historical CPC wording only for missing numbered deletion. */
#include "cpc_diag_policy.h"
#include "basic_variable_ref.h"
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
        case CPC_DIAG_COUNT: break;
    }
    return "INVALID_DIAGNOSTIC";
}

bool cpc_diag_policy_write(CpcText *text,CpcDiagCategory category)
{
    static const uint8_t generic[]="ERROR\n";
    static const uint8_t line_absent[]="Line does not exist\n";
    if(text==NULL) return false;
    if(category==CPC_DIAG_HOST_GENERIC)
        return cpc_text_write(text,generic,sizeof(generic)-1U);
    if(category==CPC_DIAG_LINE_DOES_NOT_EXIST)
        return cpc_text_write(text,line_absent,sizeof(line_absent)-1U);
    return false;
}

/* Identify the first potentially failing flow statement actually reached
 * from this executor's continuation. Do not search raw bytes for GOSUB:
 * CPC tokenised bodies contain quoted text, cached variable references and
 * numeric payloads that may themselves contain opcode/separator byte values.
 * A preceding IF/GOTO is an independent missing-target origin. On an
 * unrecognised/ambiguous prefix, return 0 (host diagnostic), not a CPC claim.
 * No execution, store lookup, allocation or mutation occurs here. */
static uint8_t reached_flow(const BasicProgram *program,
                            const BasicProgramLine *line, size_t at)
{
    const uint8_t *body=program->data+line->body_offset;
    const size_t length=line->body_length;
    while(at<length) {
        size_t p;
        bool quoted=false, separated=false;
        while(at<length && body[at]==' ') ++at;
        if(at==length) break;
        if(body[at]==0x9fu || body[at]==0xa0u ||
           body[at]==0xa1u || body[at]==0xc9u)
            return body[at]; /* GOSUB, GOTO, IF, RETURN respectively */
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
            if(token==0x02u || token==0x03u || token==0x04u ||
               token==0x0du) {
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
       result.executor_status!=BE_NEXT_VARIABLE_MISMATCH)
        return diagnostic;

    cursor=runtime->executor.cursor;
    if(bp_next(runtime->program,&cursor,&line)!=BP_OK ||
       line.offset!=runtime->executor.cursor || line.number==0U ||
       runtime->executor.statement_offset>=line.body_length)
        return diagnostic;
    if(result.executor_status==BE_NEXT_WITHOUT_FOR ||
       result.executor_status==BE_NEXT_VARIABLE_MISMATCH) {
        /* Reproduce the exact failed probe against the unchanged executor,
         * including for_match's real offending NEXT record. No guessing
         * from the FOR cursor, no raw token scan or status-only mapping. */
        if(!be_next_fault_line(&runtime->executor,
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
                          runtime->executor.statement_offset);
        if(result.executor_status==BE_MISSING_TARGET && flow==0x9fu) {
            diagnostic.category=CPC_DIAG_GOSUB_MISSING_TARGET;
            diagnostic.origin=CPC_DIAG_ORIGIN_NATIVE_GOSUB_CPC_ORACLE;
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
    } else if(diagnostic.category==CPC_DIAG_GOSUB_MISSING_TARGET &&
              diagnostic.origin==CPC_DIAG_ORIGIN_NATIVE_GOSUB_CPC_ORACLE) {
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
