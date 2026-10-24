#include "basic_listing.h"

#include <stdint.h>

typedef struct {
    uint8_t *data; /* NULL during validation/measurement */
    size_t length;
} BLEmitter;

typedef enum {
    BL_ST_PRINT,
    BL_ST_GOTO,
    BL_ST_EMPTY
} BLStatement;

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
    return 0; /* Disjointness is the caller's precondition. */
#endif
}

static BLStatus append_byte(BLEmitter *out, uint8_t c)
{
    if (out->length == SIZE_MAX) {
        return BL_OVERFLOW;
    }
    if (out->data != NULL) {
        out->data[out->length] = c;
    }
    ++out->length;
    return BL_OK;
}

static BLStatus append_word(BLEmitter *out, const char *s)
{
    BLStatus status;
    while (*s != '\0') {
        status = append_byte(out, (uint8_t)*s);
        if (status != BL_OK) {
            return status;
        }
        ++s;
    }
    return BL_OK;
}

static BLStatus append_decimal(BLEmitter *out, unsigned int value)
{
    uint8_t digits[5]; /* max uint16_t is 65535 */
    size_t n = 0;
    BLStatus status;
    do {
        digits[n++] = (uint8_t)((uint8_t)'0' + (uint8_t)(value % 10u));
        value /= 10u;
    } while (value != 0u);
    while (n != 0) {
        status = append_byte(out, digits[--n]);
        if (status != BL_OK) {
            return status;
        }
    }
    return BL_OK;
}

static BLStatus append_spaces(const uint8_t *body, size_t length,
                               size_t *index, BLEmitter *out)
{
    BLStatus status;
    while (*index < length && body[*index] == (uint8_t)' ') {
        status = append_byte(out, (uint8_t)' ');
        if (status != BL_OK) {
            return status;
        }
        ++*index;
    }
    return BL_OK;
}

/* Copy raw bytes after a CPC comment marker, without interpreting token
 * values, colons, or quotes. Source-control bytes remain invalid. */
static BLStatus append_comment(const uint8_t *body, size_t length,
                               size_t pos, BLEmitter *out)
{
    while (pos < length) {
        uint8_t c = body[pos++];
        BLStatus status;
        if (c == 0u || c == (uint8_t)'\r' || c == (uint8_t)'\n') {
            return BL_BAD_SEQUENCE;
        }
        status = append_byte(out, c);
        if (status != BL_OK) {
            return status;
        }
    }
    return BL_OK;
}

/* A strict inverse of the representable J0.4 grammar, not a CPC parser.
 * The token bytes are unambiguous only outside quoted strings. */
static BLStatus decode(const uint8_t *body, size_t length, BLEmitter *out)
{
    size_t pos = 0;
    BLStatus status;

    while (pos < length) {
        BLStatement statement = BL_ST_EMPTY;
        size_t space_start;
        uint8_t token;

        status = append_spaces(body, length, &pos, out);
        if (status != BL_OK || pos == length) {
            return status;
        }
        token = body[pos++];
        /* E1BC emits 01 C0 for ', including at the beginning of a
         * line. The prefixed 01 is not an explicit source colon. */
        if (token == 0x01u && pos < length && body[pos] == 0xc0u) {
            ++pos;
            status = append_byte(out, (uint8_t)'\'');
            if (status != BL_OK) {
                return status;
            }
            return append_comment(body, length, pos, out);
        }
        if (token == 0xc5u) {
            status = append_word(out, "REM");
            if (status != BL_OK) {
                return status;
            }
            return append_comment(body, length, pos, out);
        }
        switch (token) {
        case 0xbfu: statement = BL_ST_PRINT; status = append_word(out, "PRINT"); break;
        case 0xa0u: statement = BL_ST_GOTO; status = append_word(out, "GOTO"); break;
        case 0x98u: status = append_word(out, "END"); break;
        case 0xa7u: status = append_word(out, "LIST"); break;
        case 0xcau: status = append_word(out, "RUN"); break;
        case 0xb1u: status = append_word(out, "NEW"); break;
        default:
            return token >= 0x80u || (token >= 0x0eu && token <= 0x1fu)
                    ? BL_UNKNOWN_TOKEN : BL_BAD_SEQUENCE;
        }
        if (status != BL_OK) {
            return status;
        }

        space_start = pos;
        status = append_spaces(body, length, &pos, out);
        if (status != BL_OK) {
            return status;
        }

        if (statement == BL_ST_PRINT && pos < length && body[pos] != 0x01u) {
            uint8_t t = body[pos++];
            if (t == (uint8_t)'"') {
                status = append_byte(out, t);
                if (status != BL_OK) {
                    return status;
                }
                /* No quote escaping in the J0.4 grammar: first closing quote
                 * or end of source. A final missing quote is kept missing. */
                while (pos < length) {
                    uint8_t c = body[pos++];
                    if (c == 0u || c == (uint8_t)'\r' || c == (uint8_t)'\n') {
                        return BL_BAD_SEQUENCE;
                    }
                    status = append_byte(out, c);
                    if (status != BL_OK) {
                        return status;
                    }
                    if (c == (uint8_t)'"') {
                        break;
                    }
                }
            } else if (t >= 0x0eu && t <= 0x17u) {
                if (space_start == pos - 1u) {
                    return BL_BAD_SEQUENCE; /* PRINT0 wouldn't retokenize */
                }
                status = append_decimal(out, (unsigned int)(t - 0x0eu));
            } else if (t == 0x19u) {
                if (pos == length) {
                    return BL_TRUNCATED;
                }
                if (space_start == pos - 1u || body[pos] < 10u) {
                    return BL_BAD_SEQUENCE; /* J0.4 emits small digits as 0E..17 */
                }
                status = append_decimal(out, (unsigned int)body[pos++]);
            } else {
                return t >= 0x80u || (t >= 0x0eu && t <= 0x1fu)
                        ? BL_UNKNOWN_TOKEN : BL_BAD_SEQUENCE;
            }
            if (status != BL_OK) {
                return status;
            }
        } else if (statement == BL_ST_GOTO) {
            unsigned int line;
            if (pos == length || body[pos] == 0x01u) {
                return BL_BAD_SEQUENCE; /* Mandatory reference */
            }
            if (body[pos] != 0x1eu) {
                return body[pos] >= 0x80u ? BL_UNKNOWN_TOKEN : BL_BAD_SEQUENCE;
            }
            ++pos;
            if (length - pos < 2u) {
                return BL_TRUNCATED;
            }
            line = (unsigned int)body[pos] | ((unsigned int)body[pos + 1u] << 8);
            pos += 2u;
            if (line == 0u || pos - 3u == space_start) {
                return BL_BAD_SEQUENCE;
            }
            status = append_decimal(out, line);
            if (status != BL_OK) {
                return status;
            }
        }

        status = append_spaces(body, length, &pos, out);
        if (status != BL_OK || pos == length) {
            return status;
        }
        if (body[pos] != 0x01u) {
            return body[pos] >= 0x80u || (body[pos] >= 0x0eu && body[pos] <= 0x1fu)
                    ? BL_UNKNOWN_TOKEN : BL_BAD_SEQUENCE;
        }
        if (pos + 1u < length && body[pos + 1u] == 0xc0u) {
            /* Implicit 01 belonging to an apostrophe, not a colon. */
            continue;
        }
        ++pos;
        status = append_byte(out, (uint8_t)':');
        if (status != BL_OK) {
            return status;
        }
        space_start = pos;
        while (space_start < length && body[space_start] == (uint8_t)' ') {
            ++space_start;
        }
        if (space_start == length ||
            (body[space_start] == 0x01u &&
             (space_start + 1u == length ||
              body[space_start + 1u] != 0xc0u))) {
            return BL_BAD_SEQUENCE;
        }
    }
    return BL_OK;
}

BLStatus bl_detokenize(const uint8_t *body, size_t body_length,
                       uint8_t *destination, size_t destination_capacity,
                       size_t *written)
{
    BLEmitter count = {NULL, 0};
    BLEmitter output;
    BLStatus status;
    if (!body || !destination || !written) {
        return BL_INVALID_ARGUMENT;
    }
    if (overlaps(body, body_length, destination, destination_capacity) ||
        overlaps(written, sizeof(*written), destination, destination_capacity) ||
        overlaps(written, sizeof(*written), body, body_length)) {
        return BL_OVERLAP;
    }
    status = decode(body, body_length, &count);
    if (status != BL_OK) {
        return status;
    }
    if (count.length > destination_capacity) {
        return BL_NO_SPACE;
    }
    output.data = destination;
    output.length = 0;
    status = decode(body, body_length, &output);
    if (status != BL_OK) {
        return status; /* Input must remain unchanged between passes. */
    }
    *written = output.length;
    return BL_OK;
}

static BLStatus render(const BasicProgram *program, BLEmitter *out)
{
    size_t cursor = 0;
    BPStatus bp_status;
    BasicProgramLine line;
    BLStatus status;

    while ((bp_status = bp_next(program, &cursor, &line)) == BP_OK) {
        BLEmitter chunk = {NULL, 0};
        status = append_decimal(out, (unsigned int)line.number);
        if (status != BL_OK) return status;
        status = append_byte(out, (uint8_t)' ');
        if (status != BL_OK) return status;
        /* Validate/measure the body separately on each pass, without a VLA. */
        status = decode(program->data + line.body_offset, line.body_length, &chunk);
        if (status != BL_OK) return status;
        if (chunk.length > SIZE_MAX - out->length) return BL_OVERFLOW;
        if (out->data != NULL) {
            BLEmitter direct = {out->data + out->length, 0};
            status = decode(program->data + line.body_offset, line.body_length, &direct);
            if (status != BL_OK) return status;
        }
        out->length += chunk.length;
        status = append_byte(out, (uint8_t)'\n');
        if (status != BL_OK) return status;
    }
    return bp_status == BP_END ? BL_OK : BL_BAD_PROGRAM;
}

BLStatus bl_list_program(const BasicProgram *program,
                         uint8_t *destination, size_t destination_capacity,
                         size_t *written)
{
    BLEmitter count = {NULL, 0};
    BLEmitter output;
    BLStatus status;
    if (!program || !destination || !written) {
        return BL_INVALID_ARGUMENT;
    }
    if (bp_validate(program) != BP_OK) {
        return BL_BAD_PROGRAM;
    }
    if (overlaps(written, sizeof(*written), destination, destination_capacity) ||
        overlaps(program, sizeof(*program), destination, destination_capacity) ||
        overlaps(program, sizeof(*program), written, sizeof(*written)) ||
        overlaps(program->data, program->capacity, destination, destination_capacity) ||
        overlaps(program->data, program->capacity, written, sizeof(*written))) {
        return BL_OVERLAP;
    }
    status = render(program, &count);
    if (status != BL_OK) return status;
    if (count.length > destination_capacity) return BL_NO_SPACE;
    output.data = destination;
    output.length = 0;
    status = render(program, &output);
    if (status != BL_OK) return status; /* Caller keeps input immutable. */
    *written = output.length;
    return BL_OK;
}
