/* Shared hardware ILI9341 transport. ESP-IDF only, MIT. */
#ifndef CYD_ILI9341_H
#define CYD_ILI9341_H
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#define CYD_LCD_DMA_BYTES 5120U
typedef struct {
    bool initialized, dma_fault;
    unsigned orientation, width, height, transfer_count, timeout_count;
    unsigned heap8_free, heap8_largest, heap8_min, stack_margin_bytes;
    esp_err_t last_error;
} CydLcdDiagnostics;
esp_err_t cyd_lcd_init(void);
uint8_t *cyd_lcd_band(void);
esp_err_t cyd_lcd_send(int x, int y, int width, int height);
esp_err_t cyd_lcd_orientation(unsigned index, uint16_t clear_rgb565);
unsigned cyd_lcd_current_orientation(void);
esp_err_t cyd_lcd_backlight(bool enabled);
bool cyd_lcd_diagnostics(CydLcdDiagnostics *out);
#endif
