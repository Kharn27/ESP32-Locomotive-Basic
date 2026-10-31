/* HW4-SHOT-A: portable, bounded UART ASCII v1 screenshot emitter. MIT.
 * The caller owns the video renderer and UART; no heap or framebuffer.
 * Exactly one 320-pixel RGB565 scanline plus a 1024-byte ASCII buffer.
 */
#ifndef HW4_SHOT_UART_H
#define HW4_SHOT_UART_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HW4_SHOT_WIDTH 320u
#define HW4_SHOT_HEIGHT 240u
#define HW4_SHOT_LINE_BYTES 640u
#define HW4_SHOT_TEXT_CAPACITY 1024u

typedef bool (*Hw4ShotRenderRow)(void *context, unsigned y,
                                uint16_t *rgb565, size_t pixels);
typedef bool (*Hw4ShotSendText)(void *context, const char *bytes, size_t length);
typedef void (*Hw4ShotYield)(void *context);

typedef enum {
    HW4_SHOT_OK = 0,
    HW4_SHOT_BAD_ARGUMENT,
    HW4_SHOT_RENDER_ERROR,
    HW4_SHOT_TRANSPORT_ERROR
} Hw4ShotStatus;

/* id, orient, fw and sha are already validated against the strict P0 grammar.
 * All callbacks share context and execute sequentially in the LCD owner task.
 * The sender must return true only after delivering ALL bytes. A transport
 * failure may truncate even ABORT: the P0 decoder rejects incomplete streams.
 * yield is called after each successful ROW for FreeRTOS/watchdog service.
 * No video state or application edit/program is modified.
 */
Hw4ShotStatus hw4_shot_emit(void *context, Hw4ShotRenderRow render,
                            Hw4ShotSendText send, Hw4ShotYield yield,
                            const char *id, uint32_t seq, const char *orient,
                            const char *fw, const char *sha);
#endif
