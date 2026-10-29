/* HW4-DIAG-A: narrow CPC diagnostic text adapter, not an error-number ABI. */
#ifndef CPC_DIAG_POLICY_H
#define CPC_DIAG_POLICY_H
#include "basic_session_runtime.h"
#include "cpc_text.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    CPC_DIAG_HOST_GENERIC = 0,
    CPC_DIAG_LINE_DOES_NOT_EXIST,
    CPC_DIAG_COUNT
} CpcDiagCategory;

/* Only a genuine numbered-line deletion BS_NOT_FOUND can select CPC text.
 * Other errors (including GOTO, LISTT, UART or executor failures) stay
 * generic. No BASIC semantics, status enums or Ready policy are altered. */
CpcDiagCategory cpc_diag_policy_select(const uint8_t *source, size_t length,
                                       BSRResult result);
const char *cpc_diag_policy_category(CpcDiagCategory category);
const char *cpc_diag_policy_message(CpcDiagCategory category);
/* Exactly one diagnostic plus LF, no Ready and no hidden allocation. */
bool cpc_diag_policy_write(CpcText *text, CpcDiagCategory category);
#endif
