/* Shared original HW3 layout / HW4-C3-A native boot; MIT, C99. */
#ifndef CPC_BOOT_H
#define CPC_BOOT_H
#include "cpc_text.h"
enum { CPC_BOOT_LINES=5U, CPC_BOOT_INPUT_ROW=13U };
typedef struct { unsigned row; unsigned column; const char *text; } CpcBootLine;
bool cpc_boot_line(unsigned index,bool cyd_heading,CpcBootLine *out);
bool cpc_boot_console(CpcText *text,bool cyd_heading);
#endif
