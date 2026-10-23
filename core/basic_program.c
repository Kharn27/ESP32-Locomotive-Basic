#include "basic_program.h"

#include <string.h>

#define BP_MIN_RECORD_SIZE ((size_t)5)
#define BP_MAX_RECORD_SIZE ((size_t)UINT16_MAX)

static uint16_t read_le16(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static void write_le16(uint8_t *p, uint16_t value)
{
    p[0] = (uint8_t)(value & 0xffu);
    p[1] = (uint8_t)(value >> 8);
}

/* Address comparison of distinct objects is not defined in ISO C; uintptr_t
 * provides a bounded range check on our Linux/ESP32 targets. Else the caller
 * must respect the documented no-overlap precondition. */
static int overlaps(const void *a, size_t alen, const void *b, size_t blen)
{
    if (alen == 0 || blen == 0) {
        return 0;
    }
#if defined(UINTPTR_MAX)
    {
        uintptr_t x = (uintptr_t)a;
        uintptr_t y = (uintptr_t)b;
        return x <= y ? y - x < alen : x - y < blen;
    }
#else
    (void)a;
    (void)b;
    return 0;
#endif
}

BPStatus bp_validate_image(const uint8_t *image, size_t length)
{
    size_t offset = 0;
    uint16_t previous = 0;

    if (!image) {
        return BP_INVALID_ARGUMENT;
    }
    for (;;) {
        uint16_t record_length;
        uint16_t number;
        size_t remaining = length - offset;

        if (remaining < 2) {
            return BP_TRUNCATED;
        }
        record_length = read_le16(image + offset);
        if (record_length == 0) {
            return remaining == 2 ? BP_OK : BP_BAD_FORMAT;
        }
        if (record_length < BP_MIN_RECORD_SIZE) {
            return BP_BAD_FORMAT;
        }
        if (record_length > remaining) {
            return BP_TRUNCATED;
        }
        number = read_le16(image + offset + 2);
        if (number == 0 || number <= previous ||
            image[offset + record_length - 1] != 0) {
            return BP_BAD_FORMAT;
        }
        previous = number;
        offset += record_length;
    }
}

BPStatus bp_validate(const BasicProgram *program)
{
    if (!program || !program->data) {
        return BP_INVALID_ARGUMENT;
    }
    if (program->size > program->capacity) {
        return BP_BAD_FORMAT;
    }
    return bp_validate_image(program->data, program->size);
}

BPStatus bp_init(BasicProgram *program, uint8_t *storage, size_t capacity)
{
    if (!program || !storage) {
        return BP_INVALID_ARGUMENT;
    }
    if (capacity < 2) {
        return BP_NO_SPACE;
    }
    storage[0] = 0;
    storage[1] = 0;
    program->data = storage;
    program->capacity = capacity;
    program->size = 2;
    return BP_OK;
}

BPStatus bp_import(BasicProgram *program, const uint8_t *image, size_t length)
{
    BPStatus status;
    if (!program || !program->data || !image) {
        return BP_INVALID_ARGUMENT;
    }
    status = bp_validate_image(image, length);
    if (status != BP_OK) {
        return status;
    }
    if (length > program->capacity) {
        return BP_NO_SPACE;
    }
    if (overlaps(image, length, program->data, program->capacity)) {
        return BP_OVERLAP;
    }
    memcpy(program->data, image, length);
    program->size = length;
    return BP_OK;
}

BPStatus bp_export(const BasicProgram *program, uint8_t *dest,
                   size_t capacity, size_t *written)
{
    BPStatus status = bp_validate(program);
    if (status != BP_OK) {
        return status;
    }
    if (!dest || !written) {
        return BP_INVALID_ARGUMENT;
    }
    if (capacity < program->size) {
        return BP_NO_SPACE;
    }
    if (overlaps(dest, program->size, program->data, program->capacity)) {
        return BP_OVERLAP;
    }
    memcpy(dest, program->data, program->size);
    *written = program->size;
    return BP_OK;
}

BPStatus bp_next(const BasicProgram *program, size_t *cursor,
                 BasicProgramLine *line)
{
    size_t remaining;
    uint16_t record_length;
    BPStatus status;
    if (!cursor || !line) {
        return BP_INVALID_ARGUMENT;
    }
    if (!program || !program->data || program->size > program->capacity) {
        return BP_INVALID_ARGUMENT;
    }
    if (*cursor > program->size) {
        return BP_BAD_FORMAT;
    }
    remaining = program->size - *cursor;
    if (remaining < 2) {
        return BP_TRUNCATED;
    }
    record_length = read_le16(program->data + *cursor);
    if (record_length == 0) {
        return remaining == 2 ? BP_END : BP_BAD_FORMAT;
    }
    if (record_length < BP_MIN_RECORD_SIZE) {
        return BP_BAD_FORMAT;
    }
    if (record_length > remaining) {
        return BP_TRUNCATED;
    }
    if (program->data[*cursor + record_length - 1] != 0) {
        return BP_BAD_FORMAT;
    }
    status = read_le16(program->data + *cursor + 2) == 0
                 ? BP_BAD_FORMAT : BP_OK;
    if (status != BP_OK) {
        return status;
    }
    line->offset = *cursor;
    line->next_offset = *cursor + record_length;
    line->body_offset = *cursor + 4;
    line->body_length = (size_t)record_length - BP_MIN_RECORD_SIZE;
    line->number = read_le16(program->data + *cursor + 2);
    *cursor = line->next_offset;
    return BP_OK;
}

BPStatus bp_find(const BasicProgram *program, uint16_t number,
                 BasicProgramLine *line)
{
    size_t cursor = 0;
    BPStatus status;
    BasicProgramLine current;
    if (!line) {
        return BP_INVALID_ARGUMENT;
    }
    if (!number) {
        return BP_INVALID_LINE_NUMBER;
    }
    status = bp_validate(program);
    if (status != BP_OK) {
        return status;
    }
    while ((status = bp_next(program, &cursor, &current)) == BP_OK) {
        if (current.number >= number) {
            if (current.number == number) {
                *line = current;
                return BP_OK;
            }
            return BP_NOT_FOUND;
        }
    }
    return status == BP_END ? BP_NOT_FOUND : status;
}

static void seek_line(const BasicProgram *program, uint16_t number,
                      size_t *offset, size_t *old_length)
{
    size_t at = 0;
    for (;;) {
        uint16_t length = read_le16(program->data + at);
        if (!length || read_le16(program->data + at + 2) >= number) {
            *offset = at;
            *old_length = length &&
                read_le16(program->data + at + 2) == number ? length : 0;
            return;
        }
        at += length;
    }
}

BPStatus bp_put(BasicProgram *program, uint16_t number,
                const uint8_t *body, size_t body_length)
{
    size_t offset, old_length, new_length, suffix_start, suffix_length, base;
    BPStatus status;
    if (!number) {
        return BP_INVALID_LINE_NUMBER;
    }
    if (body_length && !body) {
        return BP_INVALID_ARGUMENT;
    }
    if (body_length > BP_MAX_RECORD_SIZE - BP_MIN_RECORD_SIZE) {
        return BP_OVERFLOW;
    }
    status = bp_validate(program);
    if (status != BP_OK) {
        return status;
    }
    if (overlaps(body, body_length, program->data, program->capacity)) {
        return BP_OVERLAP;
    }
    seek_line(program, number, &offset, &old_length);
    new_length = BP_MIN_RECORD_SIZE + body_length;
    base = program->size - old_length;
    if (new_length > program->capacity - base) {
        return BP_NO_SPACE;
    }
    suffix_start = offset + old_length;
    suffix_length = program->size - suffix_start;
    memmove(program->data + offset + new_length,
            program->data + suffix_start, suffix_length);
    write_le16(program->data + offset, (uint16_t)new_length);
    write_le16(program->data + offset + 2, number);
    if (body_length) {
        memcpy(program->data + offset + 4, body, body_length);
    }
    program->data[offset + new_length - 1] = 0;
    program->size = base + new_length;
    return BP_OK;
}

BPStatus bp_delete(BasicProgram *program, uint16_t number)
{
    size_t offset, old_length;
    BPStatus status;
    if (!number) {
        return BP_INVALID_LINE_NUMBER;
    }
    status = bp_validate(program);
    if (status != BP_OK) {
        return status;
    }
    seek_line(program, number, &offset, &old_length);
    if (!old_length) {
        return BP_NOT_FOUND;
    }
    memmove(program->data + offset, program->data + offset + old_length,
            program->size - offset - old_length);
    program->size -= old_length;
    return BP_OK;
}
