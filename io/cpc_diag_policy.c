/* HW4-DIAG-A: historical CPC wording only for missing numbered deletion. */
#include "cpc_diag_policy.h"

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
        case CPC_DIAG_COUNT: break;
    }
    return "INVALID_DIAGNOSTIC";
}

const char *cpc_diag_policy_message(CpcDiagCategory category)
{
    switch(category) {
        case CPC_DIAG_HOST_GENERIC: return "ERROR";
        case CPC_DIAG_LINE_DOES_NOT_EXIST: return "Line does not exist";
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
