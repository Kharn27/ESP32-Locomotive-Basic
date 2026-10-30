#include "basic_tokenizer.h"
#include "basic_variable_ref.h"

#include <stdint.h>
#include <string.h>

typedef struct {
    uint8_t *destination; /* NULL during validation/size pass */
    size_t length;
} BTEmitter;

typedef enum {
    ST_PRINT, ST_LIST, ST_RUN, ST_NEW, ST_GOTO, ST_END, ST_REM, ST_APOSTROPHE,
    ST_ASSIGN, ST_IF, ST_GOSUB, ST_RETURN, ST_FOR, ST_NEXT, ST_PEN, ST_INK
} BTStatement;

typedef struct {
    const char *spelling;
    uint8_t token;
    BTStatement statement;
} BTKeyword;

/* CPC keyword codes checked against basic.asm: E54A, E5DB, E4FF, E5A6, E63A, E663. */
static const BTKeyword keywords[] = {
    {"PRINT", 0xbfu, ST_PRINT},
    {"PEN",   0xbbu, ST_PEN},
    {"INK",   0xa2u, ST_INK},
    {"LIST",  0xa7u, ST_LIST},
    {"RUN",   0xcau, ST_RUN},
    {"NEW",   0xb1u, ST_NEW},
    {"GOTO",  0xa0u, ST_GOTO},
    {"FOR",   0x9eu, ST_FOR},
    {"NEXT",  0xb0u, ST_NEXT},
    {"GOSUB", 0x9fu, ST_GOSUB},
    {"RETURN",0xc9u, ST_RETURN},
    {"IF",    0xa1u, ST_IF},
    {"END",   0x98u, ST_END},
    {"REM",   0xc5u, ST_REM},
    {"LET",   0xa5u, ST_ASSIGN}
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

/* INK A2: CPC numeric immediates only. No arithmetic or variables.
 * -1 is a separate unary F5 token followed by the CPC integer 1. */
static BTStatus ink_literal(const uint8_t *source, size_t length,
                            size_t *index, BTEmitter *out,
                            unsigned int maximum, int *value)
{
    BTStatus status;
    unsigned int n;
    if (*index < length && source[*index] == (uint8_t)'-') {
        ++*index;
        if (*index == length || source[*index] != (uint8_t)'1')
            return BT_UNSUPPORTED_CONSTRUCT;
        ++*index;
        *value = -1;
        status = emit(out, 0xf5u);
        if (status == BT_OK) status = emit(out, 0x0fu);
        return status;
    }
    status = decimal(source, length, index, maximum, &n);
    if (status != BT_OK) return status;
    *value = (int)n;
    status = emit(out, (uint8_t)(n < 10u ? 0x0eu + n : 0x19u));
    if (status == BT_OK && n >= 10u)
        status = emit(out, (uint8_t)n);
    return status;
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


/* Shared CPC encoder for explicit scalars. Assignment restricts type to INTEGER. */
static BTStatus explicit_variable(const uint8_t *source, size_t length,
                                        size_t *index, BTEmitter *out,
                                         BVRExplicitType required_type)
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
    case (uint8_t)'$': type = BVR_TYPE_STRING; break;
    case (uint8_t)'!': type = BVR_TYPE_REAL; break;
    default: return BT_UNSUPPORTED_CONSTRUCT;
    }
    if (required_type != BVR_TYPE_UNDETERMINED && type != required_type) {
        return BT_UNSUPPORTED_CONSTRUCT;
    }
    /* Never tokenise A%%, A%1, A%_ or any other proper prefix. */
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



/* J1.20-B1: only CPC-attested lexical ABS forms (FF 00). No RUN semantics.
 * Syntax-error witnesses are deliberately tokenizable, exactly as CPC RAM. */
static BTStatus abs_expression(const uint8_t *src, size_t n, size_t *at,
                               BTEmitter *out, int in_print)
{
    size_t matched = 0u, origin;
    BTStatus st;
    if (!keyword_matches(src, n, *at, "ABS", &matched))
        return BT_UNSUPPORTED_CONSTRUCT;
    *at += matched;
    if (*at == n || src[*at] != (uint8_t)'(')
        return BT_UNSUPPORTED_CONSTRUCT;
    st = emit(out, 0xffu);
    if (st == BT_OK) st = emit(out, 0u);
    if (st == BT_OK) st = emit(out, (uint8_t)'(');
    if (st != BT_OK) return st;
    ++*at;
    origin = *at;
    /* CPC B%=ABS(A%) is the sole sealed assignment: no B%=ABS(n). */
    if (!in_print &&
        !(n - *at >= 2u && ascii_upper(src[*at]) == (uint8_t)'A' &&
          src[*at + 1u] == (uint8_t)'%'))
        return BT_UNSUPPORTED_CONSTRUCT;
    if (*at == n) return BT_UNSUPPORTED_CONSTRUCT;
    if (src[*at] == (uint8_t)')') {
        if (!in_print) return BT_UNSUPPORTED_CONSTRUCT;
    } else if (src[*at] == (uint8_t)'"') {
        if (!in_print || n - *at < 3u ||
            src[*at + 1u] != (uint8_t)'X' ||
            src[*at + 2u] != (uint8_t)'"')
            return BT_UNSUPPORTED_CONSTRUCT;
        st = emit(out, (uint8_t)'"');
        if (st == BT_OK) st = emit(out, (uint8_t)'X');
        if (st == BT_OK) st = emit(out, (uint8_t)'"');
        *at += 3u;
    } else if (src[*at] == (uint8_t)'-') {
        if (n - *at >= 6u && memcmp(src + *at, "-32768", 6u) == 0) {
            static const uint8_t min_bits[] = {0xf5u,0x1fu,0u,0u,0u,0u,0x90u};
            size_t i;
            for (i = 0u; st == BT_OK && i < sizeof(min_bits); ++i)
                st = emit(out, min_bits[i]);
            *at += 6u;
        } else if (n - *at >= 2u && memcmp(src + *at, "-1", 2u) == 0) {
            st = emit(out, 0xf5u);
            if (st == BT_OK) st = emit(out, 0x0fu);
            *at += 2u;
        } else return BT_UNSUPPORTED_CONSTRUCT;
    } else if (src[*at] == (uint8_t)'0' || src[*at] == (uint8_t)'1') {
        uint8_t digit = src[(*at)++];
        st = emit(out, digit == (uint8_t)'0' ? 0x0eu : 0x0fu);
        if (st == BT_OK && *at < n && src[*at] == (uint8_t)',') {
            if (!in_print || digit != (uint8_t)'1' ||
                *at + 1u >= n || src[*at + 1u] != (uint8_t)'2')
                return BT_UNSUPPORTED_CONSTRUCT;
            st = emit(out, (uint8_t)',');
            if (st == BT_OK) st = emit(out, 0x10u);
            *at += 2u;
        }
    } else if (ascii_upper(src[*at]) == (uint8_t)'A' &&
               *at + 1u < n && src[*at + 1u] == (uint8_t)'%') {
        st = explicit_variable(src, n, at, out, BVR_TYPE_INTEGER);
    } else return BT_UNSUPPORTED_CONSTRUCT;
    if (st != BT_OK) return st;
    if (*at == n || src[*at] != (uint8_t)')' ||
        (*at == origin && !in_print))
        return BT_UNSUPPORTED_CONSTRUCT;
    st = emit(out, (uint8_t)')');
    ++*at;
    return st == BT_OK && *at == n ? BT_OK : BT_UNSUPPORTED_CONSTRUCT;
}

/* J1.12-B1: literal INTEGER operands of FOR, TO and STEP only.
 * The positive magnitude 32768 belongs to the exact CPC REAL5 -32768
 * path, never to an unsigned host-only 16-bit token. */
static BTStatus for_integer(const uint8_t *source, size_t length,
                             size_t *index, BTEmitter *out)
{
    unsigned int number;
    int negative = 0;
    BTStatus status;
    if (*index < length && source[*index] == (uint8_t)'-') {
        negative = 1;
        ++*index;
        status = emit(out, 0xf5u);
        if (status != BT_OK) return status;
    }
    status = decimal(source, length, index,
                     negative ? 32768u : 32767u, &number);
    if (status != BT_OK) return status;
    if (number == 32768u) {
        static const uint8_t real5[] = {0u, 0u, 0u, 0u, 0x90u};
        size_t i;
        status = emit(out, 0x1fu);
        for (i = 0u; status == BT_OK && i < sizeof(real5); ++i)
            status = emit(out, real5[i]);
    } else if (number < 10u) {
        status = emit(out, (uint8_t)(0x0eu + number));
    } else if (number <= 255u) {
        status = emit(out, 0x19u);
        if (status == BT_OK) status = emit(out, (uint8_t)number);
    } else {
        status = emit(out, 0x1au);
        if (status == BT_OK) status = emit(out, (uint8_t)(number & 0xffu));
        if (status == BT_OK) status = emit(out, (uint8_t)(number >> 8));
    }
    return status;
}

/* J1.14-B: only a single CPC INTEGER literal assignment inside IF.
 * No implicit LET token, no expression grammar, no side effects. */
static BTStatus inline_if_assignment(const uint8_t *source, size_t length,
                                      size_t *index, BTEmitter *out)
{
    unsigned int number;
    BTStatus status;
    if (*index == length || !ascii_letter(source[*index]))
        return BT_UNSUPPORTED_CONSTRUCT;
    status = explicit_variable(source, length, index, out, BVR_TYPE_INTEGER);
    if (status == BT_OK) status = spaces(source, length, index, out);
    if (status != BT_OK) return status;
    if (*index == length || source[*index] != (uint8_t)'=')
        return BT_UNSUPPORTED_CONSTRUCT;
    ++*index;
    status = emit(out, 0xefu);
    if (status == BT_OK) status = spaces(source, length, index, out);
    if (status == BT_OK) status = decimal(source, length, index, 255u, &number);
    if (status != BT_OK) return status;
    if (number < 10u) return emit(out, (uint8_t)(0x0eu + number));
    status = emit(out, 0x19u);
    return status == BT_OK ? emit(out, (uint8_t)number) : status;
}

/* A STRING assignment is only a quoted scalar literal, never a general
 * expression.  Locate the explicit suffix without changing the tokenizer's
 * INTEGER name grammar.  Invalid source still fails in the normal parser. */
static int string_lhs(const uint8_t *source, size_t length, size_t pos)
{
    if (pos == length || !ascii_letter(source[pos])) return 0;
    ++pos;
    while (pos < length && (ascii_letter(source[pos]) ||
           ascii_digit(source[pos]) || source[pos] == (uint8_t)'.')) ++pos;
    return pos < length && source[pos] == (uint8_t)'$';
}

static BTStatus scalar_string_assignment(const uint8_t *source, size_t length,
                                         size_t *pos, BTEmitter *out)
{
    BTStatus status;
    size_t start, end;
    status = explicit_variable(source, length, pos, out, BVR_TYPE_STRING);
    if (status == BT_OK) status = spaces(source, length, pos, out);
    if (status != BT_OK) return status;
    if (*pos == length || source[(*pos)++] != (uint8_t)'=')
        return BT_UNSUPPORTED_CONSTRUCT;
    status = emit(out, 0xefu);
    if (status == BT_OK) status = spaces(source, length, pos, out);
    if (status != BT_OK) return status;
    if (*pos == length || source[*pos] != (uint8_t)'"')
        return BT_UNSUPPORTED_CONSTRUCT;
    start = *pos;
    end = start + 1u;
    while (end < length && source[end] != (uint8_t)'"') {
        if (source[end] < 0x20u || source[end] > 0x7eu)
            return BT_MALFORMED_INPUT;
        ++end;
    }
    if (end == length) return BT_MALFORMED_INPUT;
    /* A scalar STRING assignment is autonomous. Validate past trailing
     * spaces before accepting anything. Otherwise A$="X" :PRINT A$
     * tokenizes but fails LIST/RUN. one_pass emits the spaces unchanged. */
    {
        size_t suffix = end + 1u;
        while (suffix < length && source[suffix] == (uint8_t)' ')
            ++suffix;
        if (suffix != length) return BT_UNSUPPORTED_CONSTRUCT;
    }
    while (start <= end) {
        status = emit(out, source[start++]);
        if (status != BT_OK) return status;
    }
    *pos = end + 1u;
    return BT_OK;
}

/* J1.16-B/C/D-B: three literal CPC records, not a REAL5 converter.
 * F5 is the lexical minus before the positive 0.5 literal. */
static BTStatus scalar_real_statement(BTEmitter *out, int assignment,
                                      unsigned int witness)
{
    static const uint8_t reference[] = {0x0du, 0u, 0u, 0xc1u};
    static const uint8_t literal[3][8] = {
        {0xefu, 0x1fu, 0u, 0u, 0u, 0u, 0x80u, 0u}, /* A=0.5 */
        {0xefu, 0x1fu, 0u, 0u, 0u, 0x20u, 0x81u, 0u}, /* A=1.25 */
        {0xefu, 0xf5u, 0x1fu, 0u, 0u, 0u, 0u, 0x80u} /* A=-0.5 */
    };
    size_t i, literal_length = witness == 2u ? 8u : 7u;
    BTStatus status;
    for (i = 0u; i < sizeof(reference); ++i) {
        status = emit(out, reference[i]);
        if (status != BT_OK) return status;
    }
    if (!assignment) return BT_OK; /* PRINT A: reference only. */
    for (i = 0u; i < literal_length; ++i) {
        status = emit(out, literal[witness][i]);
        if (status != BT_OK) return status;
    }
    return BT_OK;
}

static BTStatus one_pass(const uint8_t *source, size_t length,
                         BTEmitter *out)
{
    size_t index = 0;
    int expecting_statement = 1;
    int seen_statement = 0;
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
                /* An implicit LET begins with the CPC variable reference,
                 * not an inserted LET token. */
                if (!ascii_letter(source[index])) {
                    return BT_UNSUPPORTED_CONSTRUCT;
                }
                statement = ST_ASSIGN;
                status = BT_OK;
            } else {
                index += count;
                statement = keyword->statement;
                status = emit(out, keyword->token);
            }
        }
        if (status != BT_OK) {
            return status;
        }
        if (statement == ST_IF && seen_statement) {
            return BT_UNSUPPORTED_CONSTRUCT;
        }
        seen_statement = 1;

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
            int stream8 = 0;
            if (source[index] == (uint8_t)'#') {
                if (length - index < 3u ||
                    source[index + 1u] != (uint8_t)'8' ||
                    source[index + 2u] != (uint8_t)',')
                    return BT_UNSUPPORTED_CONSTRUCT;
                stream8 = 1;
                status = emit(out, (uint8_t)'#');
                if (status == BT_OK) status = emit(out, 0x16u);
                if (status == BT_OK) status = emit(out, (uint8_t)',');
                if (status != BT_OK) return status;
                index += 3u;
                if (index == length) return BT_UNSUPPORTED_CONSTRUCT;
            }
            if (stream8 && !keyword_matches(source, length, index, "ABS", &count) &&
                !(length - index == 2u && source[index] == (uint8_t)'B' &&
                  source[index + 1u] == (uint8_t)'%') &&
                !(length - index == 2u && source[index] == (uint8_t)'8' &&
                  source[index + 1u] == (uint8_t)'8'))
                return BT_UNSUPPORTED_CONSTRUCT;
            if (keyword_matches(source, length, index, "ABS", &count)) {
                status = abs_expression(source, length, &index, out, 1);
            } else if (source[index] == (uint8_t)'"') {
                status = quoted_string(source, length, &index, out);
            } else if (keyword != NULL && length == 7u && index == 6u &&
                       source[5] == (uint8_t)' ' &&
                       source[index] == (uint8_t)'A') {
                status = scalar_real_statement(out, 0, 0u);
                ++index;
            } else if (ascii_letter(source[index])) {
                status = explicit_variable(source, length, &index, out,
                                           BVR_TYPE_UNDETERMINED);
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
        } else if (statement == ST_INK) {
            int pen_index, colour, third;
            /* Only standalone literal A2 forms; the third literal is a
             * token/LIST witness, never a native blinking implementation. */
            status = ink_literal(source, length, &index, out, 16u, &pen_index);
            if (status != BT_OK) return status;
            if (index == length || source[index++] != (uint8_t)',')
                return BT_MALFORMED_INPUT;
            status = emit(out, (uint8_t)',');
            if (status != BT_OK) return status;
            status = ink_literal(source, length, &index, out, 32u, &colour);
            if (status != BT_OK) return status;
            if (index < length && source[index] == (uint8_t)',') {
                if (pen_index != 1 || colour != 26)
                    return BT_UNSUPPORTED_CONSTRUCT;
                ++index;
                status = emit(out, (uint8_t)',');
                if (status != BT_OK) return status;
                status = ink_literal(source, length, &index, out, 32u, &third);
                if (status != BT_OK) return status;
                if (third != 6) return BT_UNSUPPORTED_CONSTRUCT;
            }
        } else if (statement == ST_PEN) {
            /* J1.17-A CPC BB: numeric immediate only. Tokenising 5..14
             * does NOT assert CPC execution support for those unmeasured cases. */
            unsigned int pen;
            if (index == length || source[index] == (uint8_t)':')
                return BT_MALFORMED_INPUT;
            if (source[index] == (uint8_t)'-') {
                ++index;
                if (index == length || source[index] != (uint8_t)'1')
                    return BT_UNSUPPORTED_CONSTRUCT;
                ++index;
                status = emit(out, 0xf5u);
                if (status == BT_OK) status = emit(out, 0x0fu);
            } else {
                status = decimal(source, length, &index, 255u, &pen);
                if (status == BT_OK && pen > 16u)
                    return BT_UNSUPPORTED_CONSTRUCT;
                if (status == BT_OK) {
                    status = emit(out, (uint8_t)(pen < 10u ?
                                                 0x0eu + pen : 0x19u));
                    if (status == BT_OK && pen >= 10u)
                        status = emit(out, (uint8_t)pen);
                }
            }
        } else if (statement == ST_ASSIGN) {
            if (keyword == NULL && index == 0u &&
                ((length == 5u && memcmp(source, "A=0.5", 5u) == 0) ||
                 (length == 6u && memcmp(source, "A=1.25", 6u) == 0) ||
                 (length == 6u && memcmp(source, "A=-0.5", 6u) == 0))) {
                unsigned int witness = length == 5u ? 0u :
                    (source[2] == (uint8_t)'-' ? 2u : 1u);
                status = scalar_real_statement(out, 1, witness);
                index = length;
            } else if (string_lhs(source, length, index)) {
                status = scalar_string_assignment(source, length, &index, out);
            } else {
            unsigned int number;
            int reference_rhs = 0;
            int variable_rhs = 0;
            int negative_immediate = 0;
            uint8_t binary_operator = 0u;
            /* Limited solely to standalone signed numeric literals. */
            /* E03A-E0A4: explicit INTEGER variable 02, cache 00 00,
             * high-bit terminated name. E736: '=' is operator EF. */
            if (index == length || !ascii_letter(source[index])) {
                return BT_UNSUPPORTED_CONSTRUCT;
            }
            status = explicit_variable(source, length, &index, out,
                                       BVR_TYPE_INTEGER);
            if (status == BT_OK) {
                status = spaces(source, length, &index, out);
            }
            if (status != BT_OK) {
                return status;
            }
            if (index == length || source[index] != (uint8_t)'=') {
                return BT_UNSUPPORTED_CONSTRUCT;
            }
            status = emit(out, 0xefu);
            ++index;
            if (status == BT_OK) {
                status = spaces(source, length, &index, out);
            }
            if (status == BT_OK &&
                keyword_matches(source, length, index, "ABS", &count)) {
                /* Only B%=ABS(A%) is a sealed INTEGER assignment form. */
                if (length < 8u || source[0] != (uint8_t)'B' ||
                    source[1] != (uint8_t)'%' ||
                    source[2] != (uint8_t)'=')
                    return BT_UNSUPPORTED_CONSTRUCT;
                status = abs_expression(source, length, &index, out, 0);
            } else {
            /* One INTEGER reference, binary '+', '-', '*', '\\' or MOD, and an unsigned
             * byte constant. CPC encodes '-' with F5 in this context.
             * Shared BVR encoder preserves the historical CPC name format. */
            if (status == BT_OK && index < length &&
                ascii_letter(source[index])) {
                reference_rhs = 1;
                status = explicit_variable(source, length, &index, out,
                                           BVR_TYPE_INTEGER);
                if (status == BT_OK) {
                    status = spaces(source, length, &index, out);
                }
                if (status != BT_OK) {
                    return status;
                }
                if (index == length) {
                    return BT_UNSUPPORTED_CONSTRUCT;
                }
                if (keyword_matches(source, length, index, "MOD", &count)) {
                    /* CPC BASIC 1.1 MOD is the single FB token. This only
                     * matches a whole keyword after the explicit INTEGER
                     * reference, never a prefix of an identifier. */
                    binary_operator = 0xfbu;
                    status = emit(out, binary_operator);
                    index += count;
                } else {
                    uint8_t symbol = source[index];
                    if (symbol != (uint8_t)'+' &&
                        symbol != (uint8_t)'-' &&
                        symbol != (uint8_t)'*' &&
                        symbol != (uint8_t)'\\') {
                        return BT_UNSUPPORTED_CONSTRUCT;
                    }
                    binary_operator = symbol == (uint8_t)'+' ? 0xf4u :
                                      symbol == (uint8_t)'-' ? 0xf5u :
                                      symbol == (uint8_t)'*' ? 0xf6u : 0xf9u;
                    status = emit(out, binary_operator);
                    ++index;
                }
                if (status == BT_OK) {
                    status = spaces(source, length, &index, out);
                }
            }
            /* J1.9-B: all five binary operators permit a second explicit
             * INTEGER reference, while unary F5 remains numeric-only. */
            if (status == BT_OK && reference_rhs &&
                index < length && ascii_letter(source[index])) {
                status = explicit_variable(source, length, &index, out,
                                           BVR_TYPE_INTEGER);
                variable_rhs = 1;
            }
            /* CPC unary minus token F5, followed by an ordinary
             * positive numerical token. Never fold the sign into a
             * host-only signed literal or accept a second sign on the
             * binary RHS (A%- -1 and A%--1 remain unsupported). */
            if (status == BT_OK && index < length &&
                source[index] == (uint8_t)'-') {
                if (reference_rhs || index + 1u >= length ||
                    !ascii_digit(source[index + 1u])) {
                    return BT_UNSUPPORTED_CONSTRUCT;
                }
                ++index;
                negative_immediate = 1;
                status = emit(out, 0xf5u);
            }
            if (status == BT_OK && !variable_rhs) {
                /* Only a standalone INTEGER immediate can use CPC 1A.
                 * Existing variable + byte grammar stays capped at 255. */
                status = decimal(source, length, &index,
                                 reference_rhs ? 255u :
                                 (negative_immediate ? 32768u : 32767u),
                                 &number);
            }
            if (status == BT_OK && !variable_rhs) {
                if (number == 32768u) {
                    /* NMIN: CPC unary F5 is already emitted; the positive
                     * magnitude is the one permitted REAL5, never 1A 0080.
                     * Five exact bytes, no host float or endianness. */
                    static const uint8_t real5[] = {0u, 0u, 0u, 0u, 0x90u};
                    size_t i;
                    status = emit(out, 0x1fu);
                    for (i = 0u; status == BT_OK && i < sizeof(real5); ++i) {
                        status = emit(out, real5[i]);
                    }
                } else if (number < 10u) {
                    status = emit(out, (uint8_t)(0x0eu + number));
                } else if (number <= 255u) {
                    status = emit(out, 0x19u);
                    if (status == BT_OK) {
                        status = emit(out, (uint8_t)number);
                    }
                } else {
                    /* Explicit byte shifts: independent of host endianness. */
                    status = emit(out, 0x1au);
                    if (status == BT_OK) {
                        status = emit(out, (uint8_t)(number & 0xffu));
                    }
                    if (status == BT_OK) {
                        status = emit(out, (uint8_t)(number >> 8));
                    }
                }
            }
            } /* Preserve the existing INTEGER grammar unchanged. */
            } /* ABS RHS or existing INTEGER grammar. */
        } else if (statement == ST_FOR) {
            /* No runtime or loop stack is installed by B1. Preserve lexical
             * spaces and use the shared explicit INTEGER BVR cache convention. */
            if (index == length || !ascii_letter(source[index]))
                return BT_UNSUPPORTED_CONSTRUCT;
            status = explicit_variable(source, length, &index, out,
                                       BVR_TYPE_INTEGER);
            if (status == BT_OK) status = spaces(source, length, &index, out);
            if (status != BT_OK) return status;
            if (index == length || source[index] != (uint8_t)'=')
                return BT_UNSUPPORTED_CONSTRUCT;
            ++index;
            status = emit(out, 0xefu);
            if (status == BT_OK) status = spaces(source, length, &index, out);
            if (status == BT_OK) status = for_integer(source, length, &index, out);
            if (status == BT_OK) status = spaces(source, length, &index, out);
            if (status != BT_OK) return status;
            if (!keyword_matches(source, length, index, "TO", &count))
                return BT_UNSUPPORTED_CONSTRUCT;
            index += count;
            status = emit(out, 0xecu);
            if (status == BT_OK) status = spaces(source, length, &index, out);
            if (status == BT_OK) status = for_integer(source, length, &index, out);
            if (status == BT_OK) status = spaces(source, length, &index, out);
            if (status != BT_OK) return status;
            if (keyword_matches(source, length, index, "STEP", &count)) {
                index += count;
                status = emit(out, 0xe6u);
                if (status == BT_OK) status = spaces(source, length, &index, out);
                if (status == BT_OK) status = for_integer(source, length, &index, out);
            }
        } else if (statement == ST_NEXT) {
            /* NEXT without variable is a separate, observed CPC form. */
            if (index < length && ascii_letter(source[index]))
                status = explicit_variable(source, length, &index, out,
                                           BVR_TYPE_INTEGER);
        } else if (statement == ST_IF) {
            unsigned int line;
            if (index == length || !ascii_letter(source[index])) {
                return BT_UNSUPPORTED_CONSTRUCT;
            }
            status = explicit_variable(source, length, &index, out,
                                       BVR_TYPE_INTEGER);
            if (status == BT_OK) {
                status = spaces(source, length, &index, out);
            }
            if (status != BT_OK) {
                return status;
            }
            /* J1.13-B: longest symbols before prefixes, IF-only. */
            if (index < length &&
                (source[index] == (uint8_t)'<' ||
                 source[index] == (uint8_t)'>' ||
                 source[index] == (uint8_t)'=')) {
                uint8_t relation;
                uint8_t first = source[index++];
                if (first == (uint8_t)'<' && index < length &&
                    source[index] == (uint8_t)'>') {
                    relation = 0xf2u; /* <> */
                    ++index;
                } else if (first == (uint8_t)'<' && index < length &&
                           source[index] == (uint8_t)'=') {
                    relation = 0xf3u; /* <= */
                    ++index;
                } else if (first == (uint8_t)'>' && index < length &&
                           source[index] == (uint8_t)'=') {
                    relation = 0xf0u; /* >= */
                    ++index;
                } else if (first == (uint8_t)'<') {
                    relation = 0xf1u;
                } else if (first == (uint8_t)'>') {
                    relation = 0xeeu;
                } else {
                    relation = 0xefu;
                }
                status = emit(out, relation);
                if (status == BT_OK)
                    status = spaces(source, length, &index, out);
                if (status != BT_OK) return status;
                if (index == length || !ascii_letter(source[index]))
                    return BT_UNSUPPORTED_CONSTRUCT;
                status = explicit_variable(source, length, &index, out,
                                           BVR_TYPE_INTEGER);
                if (status == BT_OK)
                    status = spaces(source, length, &index, out);
                if (status != BT_OK) return status;
            }
            if (!keyword_matches(source, length, index, "THEN", &count)) {
                return BT_UNSUPPORTED_CONSTRUCT;
            }
            index += count;
            status = emit(out, 0xebu);
            if (status == BT_OK) {
                status = spaces(source, length, &index, out);
            }
            if (status != BT_OK) {
                return status;
            }
            if (index < length && ascii_letter(source[index])) {
                /* IF ... THEN C%=81 [ELSE C%=42]; 01 97 is a CPC
                 * lexical ELSE separator, not a colon supplied by source. */
                status = inline_if_assignment(source, length, &index, out);
                if (status != BT_OK) return status;
                status = spaces(source, length, &index, out);
                if (status != BT_OK) return status;
                if (keyword_matches(source, length, index, "ELSE", &count)) {
                    index += count;
                    status = emit(out, 0x01u);
                    if (status == BT_OK) status = emit(out, 0x97u);
                    if (status == BT_OK)
                        status = spaces(source, length, &index, out);
                    if (status == BT_OK)
                        status = inline_if_assignment(source, length, &index, out);
                }
            } else {
                /* Historical IF...THEN destination line stays unchanged. */
                status = decimal(source, length, &index, 65535u, &line);
                if (status == BT_OK && line == 0u)
                    status = BT_MALFORMED_INPUT;
                if (status == BT_OK) {
                    status = emit(out, 0x1eu);
                    if (status == BT_OK)
                        status = emit(out, (uint8_t)(line & 0xffu));
                    if (status == BT_OK)
                        status = emit(out, (uint8_t)(line >> 8));
                }
            }
        } else if (statement == ST_GOTO || statement == ST_GOSUB) {
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
        if (statement == ST_IF) {
            return BT_UNSUPPORTED_CONSTRUCT; /* Autonomous IF only. */
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
