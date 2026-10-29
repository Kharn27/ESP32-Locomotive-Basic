/* HW4-READY-A: CPC-observed Ready transitions; host diagnostics explicit. */
#ifndef CPC_READY_POLICY_H
#define CPC_READY_POLICY_H
#include "cpc_text.h"
#include <stdbool.h>

/* This enum is not a BASIC grammar or a runtime status.
 * Only transitions supported by the actual console call this interface.
 * The initial boot Ready is already present in video/cpc_boot.c. */
typedef enum {
    CPC_READY_BOOT_ALREADY_PAINTED = 0,
    CPC_READY_NUMBERED_STORED,
    CPC_READY_EMPTY_ENTER,
    CPC_READY_LIST_RETURN,
    CPC_READY_NEW_RETURN,
    CPC_READY_RUN_RETURN,
    CPC_READY_BASIC_DIAGNOSTIC,
    CPC_READY_HOST_REJECTED,
    CPC_READY_HOST_CLS,
    CPC_READY_HOST_DEMO,
    CPC_READY_UNCHARACTERIZED_DIRECT,
    CPC_READY_TRANSITION_COUNT
} CpcReadyTransition;

const char *cpc_ready_transition_name(CpcReadyTransition transition);
bool cpc_ready_policy_emit(CpcReadyTransition transition);
/* Apply the exact production text emission to the caller-owned CPC screen.
 * Failure is atomic for invalid parameters; no allocation and no prompt.
 * emitted_out is optional and informs UART READY_POLICY instrumentation. */
bool cpc_ready_policy_apply(CpcText *text, CpcReadyTransition transition,
                            bool *emitted_out);
#endif
