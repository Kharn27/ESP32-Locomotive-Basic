#ifndef BASIC_PROGRAM_H
#define BASIC_PROGRAM_H

#include <stddef.h>
#include <stdint.h>

/* Borrowed caller-owned storage. Never free data while a BasicProgram uses it. */
typedef struct {
    uint8_t *data;
    size_t capacity;
    size_t size; /* includes final 00 00 sentinel */
} BasicProgram;

typedef enum {
    BP_OK = 0,
    BP_END,
    BP_NOT_FOUND,
    BP_INVALID_ARGUMENT,
    BP_INVALID_LINE_NUMBER,
    BP_BAD_FORMAT,
    BP_TRUNCATED,
    BP_NO_SPACE,
    BP_OVERFLOW,
    BP_OVERLAP
} BPStatus;

typedef struct {
    size_t offset;      /* record start, relative to program.data */
    size_t next_offset; /* next record or two-byte sentinel */
    size_t body_offset; /* relative to program.data */
    size_t body_length; /* excludes final 00 */
    uint16_t number;
} BasicProgramLine;

/* All APIs return a BPStatus; no hidden allocation or global state. */
BPStatus bp_init(BasicProgram *program, uint8_t *storage, size_t capacity);
BPStatus bp_validate_image(const uint8_t *image, size_t length);
BPStatus bp_validate(const BasicProgram *program);
BPStatus bp_import(BasicProgram *program, const uint8_t *image, size_t length);
BPStatus bp_export(const BasicProgram *program, uint8_t *dest,
                   size_t capacity, size_t *written);

/* Body is raw token payload WITHOUT the final 00, which is appended here.
 * On an existing line this replaces the record. Empty body is allowed.
 * The source body must not overlap any byte of program storage capacity.
 */
BPStatus bp_put(BasicProgram *program, uint16_t number,
                const uint8_t *body, size_t body_length);
BPStatus bp_delete(BasicProgram *program, uint16_t number);
BPStatus bp_find(const BasicProgram *program, uint16_t number,
                 BasicProgramLine *line);
/* Set *cursor=0 before the first call. BP_END means sentinel reached.
 * *cursor changes only when BP_OK is returned. Do not forge cursor values.
 */
BPStatus bp_next(const BasicProgram *program, size_t *cursor,
                 BasicProgramLine *line);

#endif
