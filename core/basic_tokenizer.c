#include "basic_tokenizer.h"
#include "basic_variable_ref.h"

#include <stdint.h>

typedef struct {
    uint8_t *destination; /* NULL during validation/size pass */
    size_t length;
} BTEmitter;

typedef enum {
    ST_PRINT, ST_LIST, ST_RUN, ST_NEW, ST_GOTO, ST_END, ST_REM, ST_APOSTROPHE
} BTStatement;

typedef struct {
    const char *spelling;
    uint8_t token;
    BTStatement statement;
} BTKeyword;

/* CPC keyword codes checked against basic.asm: E54A, E5DB, E4FF, E5A6, E63A, E663. */
static const BTKeyword keywords[] = {
    {"PRINT", 0xbfu, ST_PRINT},
    {"LIST",  0xa7u, ST_LIST},
    {"RUN",   0xcau, ST_RUN},
    {"NEW",   0xb1u, ST_NEW},
    {"GOTO",  0xa0u, ST_GOTO},
    {"END",   0x98u, ST_END},
    {"REM",   0xc5u, ST_REM}
};

static int ascii_letter(uint8_t c)
{
    return (c >= (uint8_t)'A' && c <= (uint8_t)'Z') ||
           (c >= (uint8_t)'a' && c <= (uint8_t)'z');
}

static int ascii_digit(uint8_t c)
{
    return c >= (uint8_t)'0' && c <= (uint8_t)'9';
}

/* FF9C tests a letter, digit or dot (basic.asm FF92-FFAA).
 * Additional identifier suffixes are conservatively rejected. */
static int identifier_continuation(uint8_t c)
{
    return ascii_letter(c) || ascii_digit(c) || c == (uint8_t)'.' ||
           c == (uint8_t)'_' || c == (uint8_t)'$' ||
           c == (uint8_t)'%' || c == (uint8_t)'!';
}

static uint8_t ascii_upper(uint8_t c)
{
    if (c >= (uint8_t)'a' && c <= (uint8_t)'z') {
        return (uint8_t)(c - (uint8_t)'a' + (uint8_t)'A');
    }
    return c;
}

static int overlaps(const void *a, size_t alen,
                    const void *b, size_t blen)
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
    return 0; /* ISO C99 fallback: disjointness is a caller precondition. */
#endif
}

static BTStatus emit(BTEmitter *out, uint8_t value)
{
    if (out->length == SIZE_MAX) {
        return BT_NO_SPACE;
    }
    if (out->destination) {
        out->destination[out->length] = value;
    }
    ++out->length;
    return BT_OK;
}

static BTStatus spaces(const uint8_t *source, size_t length,
                       size_t *index, BTEmitter *out)
{
    BTStatus status;
    while (*index < length && source[*index] == (uint8_t)' ') {
        status = emit(out, (uint8_t)' ');
        if (status != BT_OK) {
            return status;
        }
        ++*index;
    }
    return BT_OK;
}

static int keyword_matches(const uint8_t *source, size_t length,
                           size_t index, const char *word,
                           size_t *consumed)
{
    size_t n = 0;
    while (word[n] != '\0') {
        if (index + n >= length ||
            ascii_upper(source[index + n]) != (uint8_t)word[n]) {
            return 0;
        }
        ++n;
    }
    if (index + n < length && identifier_continuation(source[index + n])) {
        return 0;
    }
    *consumed = n;
    return 1;
}

static BTStatus decimal(const uint8_t *source, size_t length, size_t *index,
                        unsigned int maximum, unsigned int *value)
{
    unsigned int number = 0;
    if (*index >= length || !ascii_digit(source[*index])) {
        return BT_MALFORMED_INPUT;
    }
    while (*index < length && ascii_digit(source[*index])) {
        unsigned int digit = (unsigned int)(source[*index] - (uint8_t)'0');
        if (number > (maximum - digit) / 10u) {
            return BT_NUMBER_OUT_OF_RANGE;
        }
        number = number * 10u + digit;
        ++*index;
    }
    *value = number;
    return BT_OK;
}

static BTStatus quoted_string(const uint8_t *source, size_t length,
                              size_t *index, BTEmitter *out)
{
    BTStatus status;
    /* Includes opening quote, existing closing quote, or stops at EOL. */
    status = emit(out, (uint8_t)'"');
    if (status != BT_OK) {
        return status;
    }
    ++*index;
    while (*index < length) {
        uint8_t c = source[*index];
        status = emit(out, c);
        if (status != BT_OK) {
            return status;
        }
        ++*index;
        if (c == (uint8_t)'"') {
            break;
        }
    }
    return BT_OK;
}


/* The only new lexical operand: an explicitly suffixed CPC scalar in PRINT.
 * Its bytes are assembled by the J0.13/J0.16 shared reference codec. */
static BTStatus explicit_print_variable(const uint8_t *source, size_t length,
                                        size_t *index, BTEmitter *out)
{
    size_t start = *index;
    size_t end = start + 1u;
    size_t encoded_length = 0u;
    size_t i;
    uint8_t encoded[3u + BVR_MAX_NAME_LENGTH];
    BVRExplicitType type;
    BVRStatus ref_status;
    while (end < length &&
           (ascii_letter(source[end]) || ascii_digit(source[end]) ||
            source[end] == (uint8_t)'.')) {
        ++end;
    }
    if (end == length || end - start > BVR_MAX_NAME_LENGTH) {
        return BT_UNSUPPORTED_CONSTRUCT;
    }
    switch (source[end]) {
    case (uint8_t)'%': type = BVR_TYPE_INTEGER; break;
    case (uint8_t)'const uint8_t *source, size_t length,
                         BTEmitter *out)
{
    size_t index = 0;
    int expecting_statement = 1;
    BTStatus status;

    while (index < length) {
        size_t k, count = 0;
        const BTKeyword *keyword = NULL;
        BTStatement statement;

        status = spaces(source, length, &index, out);
        if (status != BT_OK || index == length) {
            return status;
        }
        if (source[index] == (uint8_t)':') {
            return BT_MALFORMED_INPUT; /* Empty/doubled statement. */
        }
        if (!expecting_statement) {
            return BT_MALFORMED_INPUT;
        }
        /* E1BC-E1C3: CPC inserts 01 C0 for apostrophe comments. */
        if (source[index] == (uint8_t)'\'') {
            statement = ST_APOSTROPHE;
            ++index;
            status = emit(out, 0x01u);
            if (status == BT_OK) {
                status = emit(out, 0xc0u);
            }
        } else if (source[index] == (uint8_t)'?') {
            statement = ST_PRINT;
            ++index;
            status = emit(out, 0xbfu);
        } else {
            for (k = 0; k < sizeof(keywords) / sizeof(keywords[0]); ++k) {
                if (keyword_matches(source, length, index,
                                    keywords[k].spelling, &count)) {
                    keyword = &keywords[k];
                    break;
                }
            }
            if (!keyword) {
                return BT_UNSUPPORTED_CONSTRUCT;
            }
            index += count;
            statement = keyword->statement;
            status = emit(out, keyword->token);
        }
        if (status != BT_OK) {
            return status;
        }

        /* DFF0-E1C3: after REM or ', the remainder is opaque source
         * bytes. In particular colons, quotes and keyword spellings
         * are not scanned again. Input control bytes were prechecked. */
        if (statement == ST_REM || statement == ST_APOSTROPHE) {
            while (index < length) {
                status = emit(out, source[index++]);
                if (status != BT_OK) {
                    return status;
                }
            }
            return BT_OK;
        }

        status = spaces(source, length, &index, out);
        if (status != BT_OK) {
            return status;
        }
        if (statement == ST_PRINT && index < length &&
            source[index] != (uint8_t)':' &&
            source[index] != (uint8_t)'\'') {
            if (source[index] == (uint8_t)'"') {
                status = quoted_string(source, length, &index, out);
            } else if (ascii_letter(source[index])) {
                status = explicit_print_variable(source, length, &index, out);
            } else if (ascii_digit(source[index])) {
                unsigned int number;
                status = decimal(source, length, &index, 255u, &number);
                if (status == BT_OK) {
                    if (number < 10u) {
                        status = emit(out, (uint8_t)(0x0eu + number));
                    } else {
                        status = emit(out, 0x19u);
                        if (status == BT_OK) {
                            status = emit(out, (uint8_t)number);
                        }
                    }
                }
            } else {
                return BT_UNSUPPORTED_CONSTRUCT;
            }
        } else if (statement == ST_GOTO) {
            unsigned int line;
            status = decimal(source, length, &index, 65535u, &line);
            if (status == BT_OK && line == 0u) {
                status = BT_MALFORMED_INPUT;
            }
            if (status == BT_OK) {
                status = emit(out, 0x1eu);
                if (status == BT_OK) {
                    status = emit(out, (uint8_t)(line & 0xffu));
                }
                if (status == BT_OK) {
                    status = emit(out, (uint8_t)(line >> 8));
                }
            }
        } else {
            status = BT_OK; /* LIST, RUN, NEW, END: no arguments in this subset. */
        }
        if (status != BT_OK) {
            return status;
        }

        status = spaces(source, length, &index, out);
        if (status != BT_OK) {
            return status;
        }
        if (index == length) {
            return BT_OK;
        }
        /* An apostrophe also carries its own statement separator in
         * the CPC encoding; unlike REM it needs no explicit colon. */
        if (source[index] == (uint8_t)'\'') {
            continue;
        }
        if (source[index] != (uint8_t)':') {
            return BT_UNSUPPORTED_CONSTRUCT;
        }
        status = emit(out, 0x01u);
        if (status != BT_OK) {
            return status;
        }
        ++index;
        expecting_statement = 1;
        /* An empty statement after ':' is outside the subset. */
        {
            size_t next = index;
            while (next < length && source[next] == (uint8_t)' ') {
                ++next;
            }
            if (next == length || source[next] == (uint8_t)':') {
                return BT_MALFORMED_INPUT;
            }
        }
    }
    return BT_OK;
}

BTStatus bt_tokenize(const uint8_t *source, size_t source_length,
                     uint8_t *destination, size_t destination_capacity,
                     size_t *written)
{
    BTEmitter probe = {NULL, 0};
    BTEmitter writer;
    BTStatus status;
    size_t i;

    if (!source || !destination || !written) {
        return BT_INVALID_ARGUMENT;
    }
    if (overlaps(source, source_length, destination, destination_capacity) ||
        overlaps(written, sizeof(*written), destination, destination_capacity) ||
        overlaps(written, sizeof(*written), source, source_length)) {
        return BT_INVALID_ARGUMENT;
    }
    for (i = 0; i < source_length; ++i) {
        if (source[i] == 0u || source[i] == (uint8_t)'\r' ||
            source[i] == (uint8_t)'\n') {
            return BT_MALFORMED_INPUT;
        }
    }
    status = one_pass(source, source_length, &probe);
    if (status != BT_OK) {
        return status;
    }
    if (probe.length > destination_capacity) {
        return BT_NO_SPACE;
    }
    writer.destination = destination;
    writer.length = 0;
    status = one_pass(source, source_length, &writer);
    if (status != BT_OK) {
        return status; /* Same immutable input: should never be reached. */
    }
    *written = writer.length;
    return BT_OK;
}
: type = BVR_TYPE_STRING; break;
    case (uint8_t)'!': type = BVR_TYPE_REAL; break;
    default: return BT_UNSUPPORTED_CONSTRUCT;
    }
    /* Reject A%%, A%1, A%_ etc. rather than tokenizing a prefix. */
    if (end + 1u < length && identifier_continuation(source[end + 1u])) {
        return BT_UNSUPPORTED_CONSTRUCT;
    }
    ref_status = bvr_encode_explicit(source + start, end - start, type,
                                      encoded, sizeof(encoded), &encoded_length);
    if (ref_status != BVR_OK) {
        return BT_UNSUPPORTED_CONSTRUCT;
    }
    for (i = 0u; i < encoded_length; ++i) {
        BTStatus status = emit(out, encoded[i]);
        if (status != BT_OK) {
            return status;
        }
    }
    *index = end + 1u;
    return BT_OK;
}

static BTStatus one_pass(const uint8_t *source, size_t length,
                         BTEmitter *out)
{
    size_t index = 0;
    int expecting_statement = 1;
    BTStatus status;

    while (index < length) {
        size_t k, count = 0;
        const BTKeyword *keyword = NULL;
        BTStatement statement;

        status = spaces(source, length, &index, out);
        if (status != BT_OK || index == length) {
            return status;
        }
        if (source[index] == (uint8_t)':') {
            return BT_MALFORMED_INPUT; /* Empty/doubled statement. */
        }
        if (!expecting_statement) {
            return BT_MALFORMED_INPUT;
        }
        /* E1BC-E1C3: CPC inserts 01 C0 for apostrophe comments. */
        if (source[index] == (uint8_t)'\'') {
            statement = ST_APOSTROPHE;
            ++index;
            status = emit(out, 0x01u);
            if (status == BT_OK) {
                status = emit(out, 0xc0u);
            }
        } else if (source[index] == (uint8_t)'?') {
            statement = ST_PRINT;
            ++index;
            status = emit(out, 0xbfu);
        } else {
            for (k = 0; k < sizeof(keywords) / sizeof(keywords[0]); ++k) {
                if (keyword_matches(source, length, index,
                                    keywords[k].spelling, &count)) {
                    keyword = &keywords[k];
                    break;
                }
            }
            if (!keyword) {
                return BT_UNSUPPORTED_CONSTRUCT;
            }
            index += count;
            statement = keyword->statement;
            status = emit(out, keyword->token);
        }
        if (status != BT_OK) {
            return status;
        }

        /* DFF0-E1C3: after REM or ', the remainder is opaque source
         * bytes. In particular colons, quotes and keyword spellings
         * are not scanned again. Input control bytes were prechecked. */
        if (statement == ST_REM || statement == ST_APOSTROPHE) {
            while (index < length) {
                status = emit(out, source[index++]);
                if (status != BT_OK) {
                    return status;
                }
            }
            return BT_OK;
        }

        status = spaces(source, length, &index, out);
        if (status != BT_OK) {
            return status;
        }
        if (statement == ST_PRINT && index < length &&
            source[index] != (uint8_t)':' &&
            source[index] != (uint8_t)'\'') {
            if (source[index] == (uint8_t)'"') {
                status = quoted_string(source, length, &index, out);
            } else if (ascii_digit(source[index])) {
                unsigned int number;
                status = decimal(source, length, &index, 255u, &number);
                if (status == BT_OK) {
                    if (number < 10u) {
                        status = emit(out, (uint8_t)(0x0eu + number));
                    } else {
                        status = emit(out, 0x19u);
                        if (status == BT_OK) {
                            status = emit(out, (uint8_t)number);
                        }
                    }
                }
            } else {
                return BT_UNSUPPORTED_CONSTRUCT;
            }
        } else if (statement == ST_GOTO) {
            unsigned int line;
            status = decimal(source, length, &index, 65535u, &line);
            if (status == BT_OK && line == 0u) {
                status = BT_MALFORMED_INPUT;
            }
            if (status == BT_OK) {
                status = emit(out, 0x1eu);
                if (status == BT_OK) {
                    status = emit(out, (uint8_t)(line & 0xffu));
                }
                if (status == BT_OK) {
                    status = emit(out, (uint8_t)(line >> 8));
                }
            }
        } else {
            status = BT_OK; /* LIST, RUN, NEW, END: no arguments in this subset. */
        }
        if (status != BT_OK) {
            return status;
        }

        status = spaces(source, length, &index, out);
        if (status != BT_OK) {
            return status;
        }
        if (index == length) {
            return BT_OK;
        }
        /* An apostrophe also carries its own statement separator in
         * the CPC encoding; unlike REM it needs no explicit colon. */
        if (source[index] == (uint8_t)'\'') {
            continue;
        }
        if (source[index] != (uint8_t)':') {
            return BT_UNSUPPORTED_CONSTRUCT;
        }
        status = emit(out, 0x01u);
        if (status != BT_OK) {
            return status;
        }
        ++index;
        expecting_statement = 1;
        /* An empty statement after ':' is outside the subset. */
        {
            size_t next = index;
            while (next < length && source[next] == (uint8_t)' ') {
                ++next;
            }
            if (next == length || source[next] == (uint8_t)':') {
                return BT_MALFORMED_INPUT;
            }
        }
    }
    return BT_OK;
}

BTStatus bt_tokenize(const uint8_t *source, size_t source_length,
                     uint8_t *destination, size_t destination_capacity,
                     size_t *written)
{
    BTEmitter probe = {NULL, 0};
    BTEmitter writer;
    BTStatus status;
    size_t i;

    if (!source || !destination || !written) {
        return BT_INVALID_ARGUMENT;
    }
    if (overlaps(source, source_length, destination, destination_capacity) ||
        overlaps(written, sizeof(*written), destination, destination_capacity) ||
        overlaps(written, sizeof(*written), source, source_length)) {
        return BT_INVALID_ARGUMENT;
    }
    for (i = 0; i < source_length; ++i) {
        if (source[i] == 0u || source[i] == (uint8_t)'\r' ||
            source[i] == (uint8_t)'\n') {
            return BT_MALFORMED_INPUT;
        }
    }
    status = one_pass(source, source_length, &probe);
    if (status != BT_OK) {
        return status;
    }
    if (probe.length > destination_capacity) {
        return BT_NO_SPACE;
    }
    writer.destination = destination;
    writer.length = 0;
    status = one_pass(source, source_length, &writer);
    if (status != BT_OK) {
        return status; /* Same immutable input: should never be reached. */
    }
    *written = writer.length;
    return BT_OK;
}
