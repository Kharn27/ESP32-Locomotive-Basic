/* HW4-EDIT-B1-A: E1 screen routing, independent of E2 cells and E3 source. */
#ifndef LOCO_CPC_SCREEN_NAV_H
#define LOCO_CPC_SCREEN_NAV_H
#include "cpc_uart_console.h"
#include <stdbool.h>
typedef struct {
    bool anchor_valid; /* the complete E3 painting is still on screen */
} CpcScreenNavigation;
void cpc_screen_nav_init(CpcScreenNavigation *nav);
bool cpc_screen_nav_move(CpcScreenNavigation *nav, CpcText *text,
                         CpcUartEditor *edit, const UartLine *line,
                         UartLineEvent event);
/* Return on E1 ENTER: CR to the next row of the *physical E1 cursor*.
 * E3 is never submitted; E2 is never parsed as a BASIC line. */
bool cpc_screen_nav_resume(CpcScreenNavigation *nav, CpcText *text,
                           CpcUartEditor *edit, const UartLine *line);
/* HOME keeps B1-A's original explicit E3 anchor refocus (no CR). */
bool cpc_screen_nav_home(CpcScreenNavigation *nav, CpcText *text,
                         CpcUartEditor *edit, const UartLine *line);
#endif
