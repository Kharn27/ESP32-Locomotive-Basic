/* HW4-C2 portable visual console controls: keeps BASIC bytes in cpc_text. */
#ifndef CPC_UART_CONSOLE_H
#define CPC_UART_CONSOLE_H
#include "cpc_text.h"
#include <stdbool.h>
#include <stdint.h>
/* MODE1 uses native scrolling rather than automatic page clearing.
 * reset_page is retained for old caller ABI and always set to false;
 * explicit !CLS is the only screen clear operation.
 */
bool cpc_uart_console_prompt(CpcText *text, bool *reset_page);
bool cpc_uart_console_append(CpcText *text, uint8_t ch);
bool cpc_uart_console_backspace(CpcText *text);
bool cpc_uart_console_end_line(CpcText *text);
bool cpc_uart_console_clear(CpcText *text); /* explicit host diagnostic !CLS */
#endif
