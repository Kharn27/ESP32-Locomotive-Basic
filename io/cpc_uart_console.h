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

/* HW4-EDIT-A: purely visual state, caller-owned, zero allocation. The
 * UartLine owns the ONLY editable source and cursor index. Painted cells
 * are on the existing 16000-byte MODE1 surface, never a second framebuffer.
 * Begin after prompt; sync after each decoded event. 'changed_from' is
 * the first modified byte, or line->length on a cursor-only event.
 * Returns false without touching VRAM for invalid arguments. */
#include "uart_line.h"
typedef struct {
    unsigned row, column; /* screen position of byte 0 */
    size_t painted;       /* previous visual length, <= 120 */
} CpcUartEditor;
bool cpc_uart_console_edit_begin(CpcText *text, CpcUartEditor *edit);
bool cpc_uart_console_edit(CpcText *text, CpcUartEditor *edit,
                           const UartLine *line, size_t changed_from);
#endif
