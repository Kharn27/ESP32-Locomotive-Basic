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
    CPC_DIAG_DIVISION_INTEGER_ZERO,
    CPC_DIAG_GOTO_MISSING_TARGET,
    CPC_DIAG_IF_MISSING_TARGET,
    CPC_DIAG_DIRECT_UNKNOWN_SYNTAX, /* CORE-typed bare unknown command */
    CPC_DIAG_WEND_UNEXPECTED, /* J1.24-A WEND_ORPHAN */
    CPC_DIAG_WHILE_WEND_MISSING, /* J1.24-A WHILE_UNCLOSED */
    CPC_DIAG_WHILE_OPERAND_MISSING, /* J1.24-A two witnesses */
    CPC_DIAG_COUNT
} CpcDiagCategory;

/* This is display provenance, NOT a CPC ERR/ERL register or host status code. */
typedef enum {
    CPC_DIAG_ORIGIN_HOST = 0,
    CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE,
    CPC_DIAG_ORIGIN_NATIVE_GOSUB_CPC_ORACLE,
    CPC_DIAG_ORIGIN_NATIVE_RETURN_CPC_ORACLE,
    CPC_DIAG_ORIGIN_NATIVE_NEXT_CPC_ORACLE,
    CPC_DIAG_ORIGIN_NATIVE_F9_ZERO_CPC_ORACLE,
    CPC_DIAG_ORIGIN_NATIVE_GOTO_CPC_ORACLE,
    CPC_DIAG_ORIGIN_NATIVE_IF_CPC_ORACLE,
    CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE
} CpcDiagOrigin;

typedef struct {
    CpcDiagCategory category;
    CpcDiagOrigin origin;
    uint16_t line_number; /* 0 for host diagnostics; never a fixed L10. */
} CpcStepDiagnostic;

/* A failed, still-running native executor step keeps its cursor. Resolve
 * the real stored line BEFORE bsr_stop(). A standalone BEStatus or a renderer
 * rejection is never sufficient evidence for a CPC diagnostic.
 * For O2-B GOTO/IF require reached tokens, absent target and taken IF. */
/* Read-only provenance query, no BASIC execution/ERR state mutation.
 * On failure *line_number is unchanged. Bounded lexical FOR/NEXT scan. */
bool cpc_diag_policy_next_locus(const BasicExecutor *executor, BEStatus reason,
                                 uint16_t *line_number);
CpcStepDiagnostic cpc_diag_policy_step(BSRResult result,
                                        const BasicSessionRuntime *runtime);
/* A2: tokenised F9 INTEGER literal-zero only; FB/MOD keeps host fallback. */
/* One LF-terminated diagnostic. Host fallback is ERROR\n, with no fabricated
 * line number; invalid fabricated CPC contexts fail closed, writing nothing.
 * format_step is also a byte-exact regression seam, without heap or printf. */
bool cpc_diag_policy_format_step(CpcStepDiagnostic diagnostic,
                                  uint8_t *output, size_t capacity,
                                  size_t *written);
bool cpc_diag_policy_write_step(CpcText *text, CpcStepDiagnostic diagnostic);

/* Direct input classification is bounded to CORE's BS_UNKNOWN_DIRECT,
 * plus the existing missing numbered-line deletion mapping. A generic
 * BS_UNSUPPORTED_DIRECT is NOT a syntax signal (GOTO, MODE, etc.).
 * The CORE lexical flag is host provenance, not a proven CPC ERR/ERL.
 * No CORE semantics or Ready policy are altered here. */
CpcDiagCategory cpc_diag_policy_select(const uint8_t *source, size_t length,
                                       BSRResult result);
const char *cpc_diag_policy_category(CpcDiagCategory category);
const char *cpc_diag_policy_message(CpcDiagCategory category);
/* Separate provenance domain: keep CpcDiagOrigin (RUN consumers) untouched.
 * This distinguishes a CORE lexical classification from a CPC ROM oracle.
 * ROM CB49 supplies the message wording, not a direct-input CPC witness. */
typedef enum {
    CPC_DIRECT_DIAG_ORIGIN_HOST = 0,
    CPC_DIRECT_DIAG_ORIGIN_CORE_UNKNOWN_LEXICAL
} CpcDirectDiagOrigin;
CpcDirectDiagOrigin cpc_diag_policy_direct_origin(CpcDiagCategory category);
/* Byte-exact formatter; insufficient capacity and rejected categories preserve
 * the ENTIRE buffer and count. No Ready; caller applies existing Ready policy. */
bool cpc_diag_policy_format_direct(CpcDiagCategory category,
                                   uint8_t *output, size_t capacity,
                                   size_t *written);
/* Exactly one diagnostic plus LF, no Ready and no hidden allocation. */
bool cpc_diag_policy_write(CpcText *text, CpcDiagCategory category);
#endif
