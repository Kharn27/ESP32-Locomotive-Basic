/* HW4-READY-A: one explicit, portable C99 Ready transition policy. */
#include "cpc_ready_policy.h"
#include <stddef.h>
#include <stdint.h>

const char *cpc_ready_transition_name(CpcReadyTransition transition)
{
    switch(transition) {
        case CPC_READY_BOOT_ALREADY_PAINTED: return "BOOT_EXISTING";
        case CPC_READY_NUMBERED_STORED: return "NUMBERED_STORED";
        case CPC_READY_EMPTY_ENTER: return "EMPTY_ENTER";
        case CPC_READY_LIST_RETURN: return "LIST_RETURN";
        case CPC_READY_NEW_RETURN: return "NEW_RETURN";
        case CPC_READY_RUN_RETURN: return "RUN_RETURN";
        case CPC_READY_BASIC_DIAGNOSTIC: return "BASIC_DIAGNOSTIC";
        case CPC_READY_HOST_REJECTED: return "HOST_REJECTED";
        case CPC_READY_HOST_CLS: return "HOST_CLS";
        case CPC_READY_HOST_DEMO: return "HOST_DEMO";
        case CPC_READY_UNCHARACTERIZED_DIRECT: return "DIRECT_UNKNOWN";
        case CPC_READY_TRANSITION_COUNT: break;
    }
    return "INVALID_TRANSITION";
}

bool cpc_ready_policy_emit(CpcReadyTransition transition)
{
    switch(transition) {
        /* Observed on independent CPC6128 ROM screenshots A0-v2. */
        case CPC_READY_LIST_RETURN:
        case CPC_READY_NEW_RETURN:
        case CPC_READY_RUN_RETURN:
        case CPC_READY_BASIC_DIAGNOSTIC:
            return true;
        /* Host-only choices, NOT historical claims. The rejected input
         * keeps its existing ERROR + Ready behavior; !DEMO likewise.
         * !CLS clears without adding another banner. */
        case CPC_READY_HOST_REJECTED:
        case CPC_READY_HOST_DEMO:
            return true;
        case CPC_READY_BOOT_ALREADY_PAINTED:
        case CPC_READY_NUMBERED_STORED:
        case CPC_READY_EMPTY_ENTER:
        case CPC_READY_HOST_CLS:
        case CPC_READY_UNCHARACTERIZED_DIRECT:
        case CPC_READY_TRANSITION_COUNT:
            return false;
    }
    return false;
}

bool cpc_ready_policy_apply(CpcText *text, CpcReadyTransition transition,
                            bool *emitted_out)
{
    static const uint8_t ready[] = "Ready\n";
    if(text==NULL || (unsigned)transition >=
       (unsigned)CPC_READY_TRANSITION_COUNT) return false;
    const bool emit=cpc_ready_policy_emit(transition);
    if(emit && !cpc_text_write(text,ready,sizeof(ready)-1U)) return false;
    if(emitted_out!=NULL) *emitted_out=emit;
    return true;
}
