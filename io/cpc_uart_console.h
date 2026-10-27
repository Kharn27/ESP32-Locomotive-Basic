/* HW4-C2 portable visual console controls: keeps BASIC bytes in cpc_text. */
#ifndef CPC_UART_CONSOLE_H
#define CPC_UART_CONSOLE_H
#include "cpc_text.h"
#include <stdbool.h>
#include <stdint.h>
/* No CPC scrolling in C2: start the next editor on a fresh logical page
 * whenever fewer than four lines remain. Existing BASIC store is untouched.
 * reset_page reports a diagnostic pagination event, not a BASIC command.
 */
bool cpc_uart_console_prompt(CpcText *text, bool *reset_page);
bool cpc_uart_console_append(CpcText *text, uint8_t ch);
bool cpc_uart_console_backspace(CpcText *text);
bool cpc_uart_console_end_line(CpcText *text);
bool cpc_uart_console_clear(CpcText *text); /* explicit host diagnostic !CLS */
#endif
