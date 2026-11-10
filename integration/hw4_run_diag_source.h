/* HW4-RUN-BREAK-B-C2: map already-authenticated CPC diagnostic origins
 * to stable UART provenance. Never classify by BEStatus alone.
 * This pure C99 helper is shared by CONSOLE and its true-BSR regression. */
#ifndef HW4_RUN_DIAG_SOURCE_H
#define HW4_RUN_DIAG_SOURCE_H

#include "cpc_diag_policy.h"

static inline const char *hw4_run_diag_source(CpcDiagOrigin origin)
{
    switch (origin) {
        case CPC_DIAG_ORIGIN_NATIVE_PEN_CPC_ORACLE:
            return "NATIVE_PEN_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_GOSUB_CPC_ORACLE:
            return "CPC_GOSUB_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_RETURN_CPC_ORACLE:
            return "CPC_RETURN_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_NEXT_CPC_ORACLE:
            return "CPC_NEXT_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_F9_ZERO_CPC_ORACLE:
            return "CPC_F9_ZERO_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_GOTO_CPC_ORACLE:
            return "CPC_GOTO_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_IF_CPC_ORACLE:
            return "CPC_IF_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_WHILE_WEND_CPC_ORACLE:
            return "NATIVE_WHILE_WEND_CPC_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_F5_F6_OVERFLOW_CPC_ORACLE:
            return "CPC_F5_F6_OVERFLOW_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_FB_ZERO_CPC_ORACLE:
            return "CPC_FB_ZERO_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_INK_CPC_ORACLE:
            return "CPC_INK_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_PAPER_CPC_ORACLE:
            return "CPC_PAPER_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_LOCATE_CPC_ORACLE:
            return "CPC_LOCATE_ORACLE";
        case CPC_DIAG_ORIGIN_NATIVE_BORDER_CPC_ORACLE:
            return "CPC_BORDER_ORACLE";
        case CPC_DIAG_ORIGIN_HOST:
            return "HOST";
    }
    return "HOST"; /* Unknown provenance must fail closed. */
}
#endif
