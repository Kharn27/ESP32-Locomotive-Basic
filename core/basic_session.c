#include "basic_session.h"

#include <stdint.h>

static BSResult result(BSStatus status, BTStatus bt, BPStatus bp, BLStatus bl)
{
    BSResult r = {status, bt, bp, bl};
    return r;
}

static BSResult simple(BSStatus status)
{
    return result(status, BT_OK, BP_OK, BL_OK);
}

static BSResult token_error(BTStatus status)
{
    return result(BS_TOKENIZER_ERROR, status, BP_OK, BL_OK);
}

static BSResult program_error(BPStatus status)
{
    return result(BS_PROGRAM_ERROR, BT_OK, status, BL_OK);
}

static BSResult listing_error(BLStatus status)
{
    return result(BS_LISTING_ERROR, BT_OK, BP_OK, status);
}

static int overlaps(const void *a, size_t alen, const void *b, size_t blen)
{
    if (alen == 0u || blen == 0u) {
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
    return 0; /* Documented caller precondition without uintptr_t. */
#endif
}

static int bad_alias(const BasicProgram *program,
                     const uint8_t *source, size_t source_length,
                     const uint8_t *temporary, size_t temporary_capacity,
                     const uint8_t *output, size_t output_capacity,
                     const size_t *written)
{
    const void *parts[6];
    size_t lengths[6];
    size_t i, j;
    parts[0] = program;
    lengths[0] = sizeof(*program);
    parts[1] = program->data;
    lengths[1] = program->capacity;
    parts[2] = source;
    lengths[2] = source_length;
    parts[3] = temporary;
    lengths[3] = temporary_capacity;
    parts[4] = output;
    lengths[4] = output_capacity;
    parts[5] = written;
    lengths[5] = sizeof(*written);
    for (i = 0u; i < 6u; ++i) {
        for (j = i + 1u; j < 6u; ++j) {
            if (overlaps(parts[i], lengths[i], parts[j], lengths[j])) {
                return 1;
            }
        }
    }
    return 0;
}

static int digit(uint8_t c)
{
    return c >= (uint8_t)'0' && c <= (uint8_t)'9';
}

static uint8_t upper(uint8_t c)
{
    return c >= (uint8_t)'a' && c <= (uint8_t)'z'
        ? (uint8_t)(c - (uint8_t)'a' + (uint8_t)'A') : c;
}

static int command_is(const uint8_t *s, size_t n, const char *literal)
{
    size_t i = 0u;
    while (literal[i] != '\0') {
        if (i >= n || upper(s[i]) != (uint8_t)literal[i]) {
            return 0;
        }
        ++i;
    }
    return i == n;
}

static int has_direct_separator(const uint8_t *s, size_t n)
{
    size_t i;
    int quoted = 0;
    for (i = 0u; i < n; ++i) {
        if (s[i] == (uint8_t)'"') {
            quoted = !quoted;
        } else if (!quoted && s[i] == (uint8_t)':') {
            return 1;
        }
    }
    return 0;
}

BSResult bs_process_line(BasicProgram *program,
                         const uint8_t *source, size_t source_length,
                         uint8_t *temporary, size_t temporary_capacity,
                         uint8_t *output, size_t output_capacity,
                         size_t *written)
{
    size_t i, cursor, body_length;
    BPStatus bp_status;
    BTStatus bt_status;
    BLStatus bl_status;
    unsigned int number = 0u;

    if (!program || !program->data || !source || !temporary || !output || !written) {
        return simple(BS_INVALID_ARGUMENT);
    }
    if (bad_alias(program, source, source_length, temporary,
                  temporary_capacity, output, output_capacity, written)) {
        return simple(BS_OVERLAP);
    }
    bp_status = bp_validate(program);
    if (bp_status != BP_OK) {
        return program_error(bp_status);
    }
    for (i = 0u; i < source_length; ++i) {
        if (source[i] == 0u || source[i] == (uint8_t)'\r' ||
            source[i] == (uint8_t)'\n') {
            return simple(BS_MALFORMED_INPUT);
        }
    }
    if (source_length != 0u && digit(source[0])) {
        cursor = 0u;
        do {
            unsigned int d = (unsigned int)(source[cursor] - (uint8_t)'0');
            if (number > (65535u - d) / 10u) {
                return simple(BS_INVALID_LINE_NUMBER);
            }
            number = number * 10u + d;
            ++cursor;
        } while (cursor < source_length && digit(source[cursor]));
        if (number == 0u) {
            return simple(BS_INVALID_LINE_NUMBER);
        }
        if (cursor < source_length && source[cursor] != (uint8_t)' ') {
            return simple(BS_MALFORMED_INPUT);
        }
        if (cursor < source_length) {
            ++cursor; /* Exactly one ASCII space is a separator. */
        }
        i = cursor;
        while (i < source_length && source[i] == (uint8_t)' ') {
            ++i;
        }
        if (i == source_length) {
            bp_status = bp_delete(program, (uint16_t)number);
            if (bp_status == BP_NOT_FOUND) {
                return simple(BS_NOT_FOUND);
            }
            if (bp_status != BP_OK) {
                return program_error(bp_status);
            }
            *written = 0u;
            return simple(BS_OK);
        }
        body_length = 0u;
        bt_status = bt_tokenize(source + cursor, source_length - cursor,
                                temporary, temporary_capacity, &body_length);
        if (bt_status != BT_OK) {
            return token_error(bt_status);
        }
        bp_status = bp_put(program, (uint16_t)number, temporary, body_length);
        if (bp_status != BP_OK) {
            return program_error(bp_status);
        }
        *written = 0u;
        return simple(BS_OK);
    }

    cursor = 0u;
    while (cursor < source_length && source[cursor] == (uint8_t)' ') {
        ++cursor;
    }
    i = source_length;
    while (i > cursor && source[i - 1u] == (uint8_t)' ') {
        --i;
    }
    if (i == cursor) {
        *written = 0u;
        return simple(BS_OK); /* Blank entry is a documented no-op. */
    }
    if (has_direct_separator(source + cursor, i - cursor)) {
        return simple(BS_MULTIPLE_DIRECT);
    }
    if (command_is(source + cursor, i - cursor, "LIST")) {
        bl_status = bl_list_program(program, output, output_capacity, written);
        return bl_status == BL_OK ? simple(BS_OK) : listing_error(bl_status);
    }
    if (command_is(source + cursor, i - cursor, "NEW")) {
        /* bp_validate and disjointness checked above, capacity >= 2. */
        bp_status = bp_init(program, program->data, program->capacity);
        if (bp_status != BP_OK) {
            return program_error(bp_status);
        }
        *written = 0u;
        return simple(BS_OK);
    }
    return simple(BS_UNSUPPORTED_DIRECT);
}
