/* HW4-DIAG-A: historical CPC wording only for missing numbered deletion. */
#include "cpc_diag_policy.h"
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

/* BE_INVALID_PEN is currently emitted ONLY by pen_argument() for the
 * independently observed PEN 16/-1. Its numeric value is not CPC ERR=5.
 * bsr_step_events() preserves the failed executor cursor and RUNNING state;
 * neither can be recovered reliably after bsr_stop(). */
CpcStepDiagnostic cpc_diag_policy_step(BSRResult result,
                                        const BasicSessionRuntime *runtime)
{
    CpcStepDiagnostic diagnostic={
        CPC_DIAG_HOST_GENERIC, CPC_DIAG_ORIGIN_HOST, 0U
    };
    BasicProgramLine line;
    size_t cursor;
    if(result.status!=BSR_EXECUTOR_ERROR ||
       result.executor_status!=BE_INVALID_PEN ||
       runtime==NULL || runtime->state!=BSR_RUNNING ||
       runtime->program==NULL || runtime->executor.program!=runtime->program)
        return diagnostic;

    cursor=runtime->executor.cursor;
    if(bp_next(runtime->program,&cursor,&line)!=BP_OK ||
       line.offset!=runtime->executor.cursor || line.number==0U ||
       runtime->executor.statement_offset>line.body_length)
        return diagnostic;
    diagnostic.category=CPC_DIAG_PEN_IMPROPER_ARGUMENT;
    diagnostic.origin=CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE;
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
    static const uint8_t prefix[]="Improper argument in ";
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
    if(diagnostic.category!=CPC_DIAG_PEN_IMPROPER_ARGUMENT ||
       diagnostic.origin!=CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE ||
       number==0U) return false;
    do {
        digits[count++]=(uint8_t)('0'+number%10U);
        number=(uint16_t)(number/10U);
    } while(number!=0U);
    n=(sizeof(prefix)-1U)+count+1U;
    if(capacity<n) return false;
    memcpy(output,prefix,sizeof(prefix)-1U);
    for(size_t i=0U;i<count;++i)
        output[sizeof(prefix)-1U+i]=digits[count-1U-i];
    output[n-1U]='\n';
    *written=n;
    return true;
}

bool cpc_diag_policy_write_step(CpcText *text, CpcStepDiagnostic diagnostic)
{
    uint8_t bytes[sizeof("Improper argument in 65535\n")];
    size_t written=0U;
    if(text==NULL || !cpc_diag_policy_format_step(diagnostic,bytes,
                                                 sizeof(bytes),&written))
        return false;
    return cpc_text_write(text,bytes,written);
}
