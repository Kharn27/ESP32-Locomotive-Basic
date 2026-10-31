#include "hw4_shot_uart.h"
#include <stdio.h>
#include <string.h>

static const char base64[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static uint32_t crc_byte(uint32_t crc, uint8_t b)
{
    crc ^= b;
    for (unsigned i = 0u; i < 8u; ++i)
        crc = (crc >> 1u) ^ ((crc & 1u) ? UINT32_C(0xedb88320) : 0u);
    return crc;
}
static bool char_in(char c, const char *allowed)
{
    return strchr(allowed, c) != NULL;
}
static bool token(const char *s, size_t min, size_t max, const char *allowed)
{
    size_t n = 0u;
    if (s == NULL) return false;
    while (s[n] != 0) {
        if (n >= max || !char_in(s[n], allowed)) return false;
        ++n;
    }
    return n >= min;
}
static bool sha_token(const char *sha)
{
    return token(sha, 7u, 40u, "0123456789abcdef");
}
static bool send_line(void *ctx, Hw4ShotSendText send, const char *line, int n)
{
    return n > 0 && n < (int)HW4_SHOT_TEXT_CAPACITY &&
           send(ctx, line, (size_t)n);
}
static void abort_capture(void *ctx, Hw4ShotSendText send, char *line,
                          const char *id, const char *reason)
{
    const int n = snprintf(line, HW4_SHOT_TEXT_CAPACITY,
                           "@CYDSHOT:1|ABORT|id=%s|reason=%s\n", id, reason);
    (void)send_line(ctx, send, line, n); /* best-effort; EOF is also fatal */
}

/* Byte-for-byte RGB565LE, not the big-endian LCD DMA wire order. */
static size_t encoded_row(const uint16_t *pixels, char *encoded)
{
    uint32_t bits = 0u;
    unsigned count = 0u;
    size_t out = 0u;
    for (unsigned x = 0u; x < HW4_SHOT_WIDTH; ++x) {
        for (unsigned part = 0u; part < 2u; ++part) {
            const uint8_t byte = part ? (uint8_t)(pixels[x] >> 8u) :
                                        (uint8_t)pixels[x];
            bits = (bits << 8u) | byte;
            count += 8u;
            while (count >= 6u) {
                count -= 6u;
                encoded[out++] = base64[(bits >> count) & 63u];
            }
            bits &= (UINT32_C(1) << count) - 1u;
        }
    }
    if (count) encoded[out++] = base64[(bits << (6u - count)) & 63u];
    while ((out & 3u) != 0u) encoded[out++] = '=';
    return out; /* 856 bytes for 640 input bytes */
}
Hw4ShotStatus hw4_shot_emit(void *ctx, Hw4ShotRenderRow render,
                            Hw4ShotSendText send, Hw4ShotYield yield,
                            const char *id, uint32_t seq, const char *orient,
                            const char *fw, const char *sha)
{
    /* One row and one wire line, no frame allocation or dynamic memory. */
    uint16_t scan[HW4_SHOT_WIDTH];
    char line[HW4_SHOT_TEXT_CAPACITY];
    uint32_t global = UINT32_C(0xffffffff);
    const char *const id_chars =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";
    const char *const fw_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-";
    int n;
    if (render == NULL || send == NULL ||
        !token(id, 1u, 32u, id_chars) ||
        !token(orient, 1u, 24u, id_chars) ||
        !token(fw, 1u, 48u, fw_chars) || !sha_token(sha))
        return HW4_SHOT_BAD_ARGUMENT;
    n = snprintf(line, sizeof(line),
                 "@CYDSHOT:1|BEGIN|id=%s|seq=%lu|w=320|h=240|"
                 "pix=RGB565LE|orient=%s|fw=%s|sha=%s\n",
                 id, (unsigned long)seq, orient, fw, sha);
    if (!send_line(ctx, send, line, n)) return HW4_SHOT_TRANSPORT_ERROR;
    for (unsigned y = 0u; y < HW4_SHOT_HEIGHT; ++y) {
        uint32_t row = UINT32_C(0xffffffff);
        size_t prefix, encoded;
        if (!render(ctx, y, scan, HW4_SHOT_WIDTH)) {
            abort_capture(ctx, send, line, id, "RENDER_ERROR");
            return HW4_SHOT_RENDER_ERROR;
        }
        for (unsigned x = 0u; x < HW4_SHOT_WIDTH; ++x) {
            const uint8_t lo = (uint8_t)scan[x];
            const uint8_t hi = (uint8_t)(scan[x] >> 8u);
            row = crc_byte(crc_byte(row, lo), hi);
            global = crc_byte(crc_byte(global, lo), hi);
        }
        n = snprintf(line, sizeof(line),
                     "@CYDSHOT:1|ROW|id=%s|n=%u|crc=%08lX|b64=",
                     id, y, (unsigned long)(row ^ UINT32_C(0xffffffff)));
        if (n < 1 || n > (int)sizeof(line) - 858) {
            abort_capture(ctx, send, line, id, "ENCODE_ERROR");
            return HW4_SHOT_BAD_ARGUMENT;
        }
        prefix = (size_t)n;
        encoded = encoded_row(scan, line + prefix);
        if (encoded != 856u || prefix + encoded + 1u > sizeof(line)) {
            abort_capture(ctx, send, line, id, "ENCODE_ERROR");
            return HW4_SHOT_BAD_ARGUMENT;
        }
        line[prefix + encoded] = '\n';
        if (!send(ctx, line, prefix + encoded + 1u)) {
            abort_capture(ctx, send, line, id, "UART_TIMEOUT");
            return HW4_SHOT_TRANSPORT_ERROR;
        }
        if (yield != NULL) yield(ctx);
    }
    n = snprintf(line, sizeof(line),
                 "@CYDSHOT:1|DONE|id=%s|crc=%08lX\n",
                 id, (unsigned long)(global ^ UINT32_C(0xffffffff)));
    if (!send_line(ctx, send, line, n)) {
        abort_capture(ctx, send, line, id, "UART_TIMEOUT");
        return HW4_SHOT_TRANSPORT_ERROR;
    }
    return HW4_SHOT_OK;
}
