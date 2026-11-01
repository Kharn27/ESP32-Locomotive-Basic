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
    CPC_DIAG_PEN_IMPROPER_ARGUMENT,
    CPC_DIAG_GOSUB_MISSING_TARGET,
    CPC_DIAG_RETURN_UNEXPECTED,
    CPC_DIAG_NEXT_UNEXPECTED,
    CPC_DIAG_COUNT
} CpcDiagCategory;

/* This is display provenance, NOT a CPC ERR/ERL register or host status code. */
typedef enum {
    CPC_DIAG_ORIGIN_HOST = 0,
    CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE,
    CPC_DIAG_ORIGIN_NATIVE_GOSUB_CPC_ORACLE,
    CPC_DIAG_ORIGIN_NATIVE_RETURN_CPC_ORACLE,
    CPC_DIAG_ORIGIN_NATIVE_NEXT_CPC_ORACLE
} CpcDiagOrigin;

typedef struct {
    CpcDiagCategory category;
    CpcDiagOrigin origin;
    uint16_t line_number; /* 0 for host diagnostics; never a fixed L10. */
} CpcStepDiagnostic;

/* A failed, still-running native PEN step keeps its executor cursor. Resolve
 * the real stored line BEFORE bsr_stop(). A standalone BEStatus or a renderer
 * rejection is never sufficient evidence for a CPC diagnostic.
 * Only PEN 16 and PEN -1 have an independent CPC error witness. */
/* Read-only provenance query, no BASIC execution/ERR state mutation.
 * On failure *line_number is unchanged. Bounded lexical FOR/NEXT scan. */
bool cpc_diag_policy_next_locus(const BasicExecutor *executor, BEStatus reason,
                                 uint16_t *line_number);
CpcStepDiagnostic cpc_diag_policy_step(BSRResult result,
                                        const BasicSessionRuntime *runtime);
/* One LF-terminated diagnostic. Host fallback is ERROR\n, with no fabricated
 * line number; invalid fabricated CPC contexts fail closed, writing nothing.
 * format_step is also a byte-exact regression seam, without heap or printf. */
bool cpc_diag_policy_format_step(CpcStepDiagnostic diagnostic,
                                  uint8_t *output, size_t capacity,
                                  size_t *written);
bool cpc_diag_policy_write_step(CpcText *text, CpcStepDiagnostic diagnostic);

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
