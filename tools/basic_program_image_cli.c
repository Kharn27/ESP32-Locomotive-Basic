/* J0.24 Linux-only image exporter. Not a CPC oracle or firmware component. */
#include "basic_session.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define PROGRAM_CAPACITY 32768u
#define SOURCE_CAPACITY 512u
#define TEMPORARY_CAPACITY 2048u
#define OUTPUT_CAPACITY 32768u

typedef struct {
    BasicProgram program;
    uint8_t storage[PROGRAM_CAPACITY];
    uint8_t source[SOURCE_CAPACITY];
    uint8_t temporary[TEMPORARY_CAPACITY];
    uint8_t output[OUTPUT_CAPACITY];
    size_t written;
} DumpContext;

static int input_line(uint8_t *buffer, size_t capacity, size_t *length)
{
    int ch;
    int seen = 0;
    size_t n = 0u;
    while ((ch = fgetc(stdin)) != EOF) {
        seen = 1;
        if (ch == '\n') {
            break;
        }
        if (n == capacity) {
            fputs("image-cli: input line too long\n", stderr);
            return -1;
        }
        buffer[n++] = (uint8_t)ch;
    }
    if (ferror(stdin)) {
        fputs("image-cli: stdin I/O error\n", stderr);
        return -1;
    }
    if (!seen && ch == EOF) {
        return 0;
    }
    if (n != 0u && buffer[n - 1u] == (uint8_t)'\r') {
        --n;
    }
    *length = n;
    return 1;
}

int main(void)
{
    static DumpContext ctx; /* Large host buffers must not consume task stack. */
    int rc;
    size_t length = 0u;
    if (bp_init(&ctx.program, ctx.storage, sizeof(ctx.storage)) != BP_OK) {
        fputs("image-cli: bp_init failed\n", stderr);
        return 1;
    }
    while ((rc = input_line(ctx.source, sizeof(ctx.source), &length)) > 0) {
        BSResult result;
        if (length == 0u) {
            continue;
        }
        result = bs_process_line(&ctx.program, ctx.source, length,
                                 ctx.temporary, sizeof(ctx.temporary),
                                 ctx.output, sizeof(ctx.output), &ctx.written);
        if (result.status != BS_OK) {
            fprintf(stderr, "image-cli: input rejected: BS=%d BT=%d BP=%d BL=%d\n",
                    (int)result.status, (int)result.tokenizer_status,
                    (int)result.program_status, (int)result.listing_status);
            return 2;
        }
    }
    if (rc < 0) {
        return 1;
    }
    if (bp_export(&ctx.program, ctx.output, sizeof(ctx.output),
                  &ctx.written) != BP_OK) {
        fputs("image-cli: bp_export failed\n", stderr);
        return 1;
    }
    if (fwrite(ctx.output, 1u, ctx.written, stdout) != ctx.written ||
        fflush(stdout) != 0) {
        fputs("image-cli: stdout I/O error\n", stderr);
        return 1;
    }
    return 0;
}
