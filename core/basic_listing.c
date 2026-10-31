#include "basic_listing.h"
#include "basic_variable_ref.h"

#include <stdint.h>
#include <string.h>

typedef struct {
    uint8_t *data; /* NULL during validation/measurement */
    size_t length;
} BLEmitter;

typedef enum {
    BL_ST_PRINT,
    BL_ST_GOTO,
    BL_ST_GOSUB,
    BL_ST_ASSIGN,
    BL_ST_IF,
    BL_ST_FOR,
    BL_ST_NEXT,
    BL_ST_PEN,
    BL_ST_INK,
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

/* Decode only CPC FOR/TO/STEP INTEGER constants, no generic expression
 * interpreter. The cache bytes of references are intentionally opaque. */
static BLStatus for_number(const uint8_t *body, size_t length,
                           size_t *pos, BLEmitter *out)
{
    unsigned int magnitude;
    int negative = 0;
    uint8_t token;
    BLStatus status;
    if (*pos >= length) return BL_TRUNCATED;
    token = body[(*pos)++];
    if (token == 0xf5u) {
        negative = 1;
        status = append_byte(out, (uint8_t)'-');
        if (status != BL_OK) return status;
        if (*pos >= length) return BL_TRUNCATED;
        token = body[(*pos)++];
    }
    if (token >= 0x0eu && token <= 0x17u) {
        magnitude = (unsigned int)(token - 0x0eu);
    } else if (token == 0x19u) {
        if (*pos == length) return BL_TRUNCATED;
        magnitude = (unsigned int)body[(*pos)++];
        if (magnitude < 10u) return BL_BAD_SEQUENCE;
    } else if (token == 0x1au) {
        if (length - *pos < 2u) return BL_TRUNCATED;
        magnitude = (unsigned int)body[*pos] |
                    ((unsigned int)body[*pos + 1u] << 8);
        *pos += 2u;
        if (magnitude < 256u || magnitude > 32767u)
            return BL_BAD_SEQUENCE;
    } else if (token == 0x1fu && negative) {
        static const uint8_t real5[] = {0u, 0u, 0u, 0u, 0x90u};
        size_t i;
        if (length - *pos < sizeof(real5)) return BL_TRUNCATED;
        for (i = 0u; i < sizeof(real5); ++i)
            if (body[*pos + i] != real5[i]) return BL_BAD_SEQUENCE;
        *pos += sizeof(real5);
        magnitude = 32768u;
    } else {
        return token >= 0x80u || (token >= 0x0eu && token <= 0x1fu)
             ? BL_UNKNOWN_TOKEN : BL_BAD_SEQUENCE;
    }
    return append_decimal(out, magnitude);
}

/* Both FOR and NEXT use 02 [opaque cache low/high] variable name; never
 * treat cache bytes as source whitespace or CPC opcodes. */
static BLStatus for_reference(const uint8_t *body, size_t length,
                              size_t *pos, BLEmitter *out)
{
    BasicVariableRef ref;
    BVRStatus decoded;
    size_t i;
    BLStatus status;
    if (*pos >= length) return BL_TRUNCATED;
    if (body[*pos] != 0x02u) return BL_BAD_SEQUENCE;
    decoded = bvr_decode(body, length, *pos, &ref);
    if (decoded == BVR_TRUNCATED) return BL_TRUNCATED;
    if (decoded != BVR_OK || ref.family != BVR_FAMILY_EXPLICIT ||
        ref.explicit_type != BVR_TYPE_INTEGER) return BL_BAD_SEQUENCE;
    for (i = 0u; i < ref.name_length; ++i) {
        status = append_byte(out, (uint8_t)(body[ref.name_offset + i] & 0x7fu));
        if (status != BL_OK) return status;
    }
    status = append_byte(out, (uint8_t)'%');
    *pos = ref.reference_offset + ref.consumed;
    return status;
}

/* The one inline IF arm is exactly: INTEGER BVR EF byte literal.
 * CPC cache words are opaque; never interpret them as lexical text. */
static BLStatus inline_if_assignment(const uint8_t *body, size_t length,
                                     size_t *pos, BLEmitter *out)
{
    BLStatus status;
    unsigned int number;
    uint8_t token;
    status = for_reference(body, length, pos, out);
    if (status != BL_OK) return status;
    status = append_spaces(body, length, pos, out);
    if (status != BL_OK) return status;
    if (*pos == length || body[(*pos)++] != 0xefu)
        return BL_BAD_SEQUENCE;
    status = append_byte(out, (uint8_t)'=');
    if (status == BL_OK) status = append_spaces(body, length, pos, out);
    if (status != BL_OK) return status;
    if (*pos == length) return BL_TRUNCATED;
    token = body[(*pos)++];
    if (token >= 0x0eu && token <= 0x17u) {
        number = (unsigned int)(token - 0x0eu);
    } else if (token == 0x19u) {
        if (*pos == length) return BL_TRUNCATED;
        number = (unsigned int)body[(*pos)++];
        if (number < 10u) return BL_BAD_SEQUENCE;
    } else {
        return BL_BAD_SEQUENCE;
    }
    return append_decimal(out, number);
}

/* Strict inverse of the CPC A2 numeric immediate encodings.
 * The decoder preserves the measured -1 (F5 0F) syntax without inferring
 * arithmetic, blinking, or broader palette semantics. */
static BLStatus ink_literal(const uint8_t *body, size_t length,
                            size_t *pos, BLEmitter *out,
                            unsigned int maximum, int *value)
{
    uint8_t token;
    unsigned int n;
    BLStatus status;
    if (*pos == length) return BL_TRUNCATED;
    token = body[(*pos)++];
    if (token == 0xf5u) {
        if (*pos == length) return BL_TRUNCATED;
        if (body[(*pos)++] != 0x0fu) return BL_BAD_SEQUENCE;
        *value = -1;
        status = append_byte(out, (uint8_t)'-');
        if (status != BL_OK) return status;
        return append_byte(out, (uint8_t)'1');
    }
    if (token >= 0x0eu && token <= 0x17u)
        n = (unsigned int)(token - 0x0eu);
    else if (token == 0x19u) {
        if (*pos == length) return BL_TRUNCATED;
        n = (unsigned int)body[(*pos)++];
        if (n < 10u) return BL_BAD_SEQUENCE;
    } else
        return token >= 0x80u || (token >= 0x0eu && token <= 0x1fu) ?
               BL_UNKNOWN_TOKEN : BL_BAD_SEQUENCE;
    if (n > maximum) return BL_BAD_SEQUENCE;
    *value = (int)n;
    return append_decimal(out, n);
}


/* Only the sealed J1.20-A FF 00 ABS operands, without RUN decoding. */
static BLStatus abs_expression(const uint8_t *b, size_t len,
                               size_t *at, BLEmitter *out, int in_print)
{
    BLStatus st;
    uint8_t token;
    if (len - *at < 4u) return BL_TRUNCATED;
    if (b[*at] != 0xffu || b[*at + 1u] != 0u ||
        b[*at + 2u] != (uint8_t)'(')
        return BL_BAD_SEQUENCE;
    *at += 3u;
    st = append_word(out, "ABS(");
    if (st != BL_OK) return st;
    if (*at == len) return BL_TRUNCATED;
    /* The assignment witness has only a CPC explicit A% argument. */
    if (!in_print && b[*at] != 0x02u) return BL_BAD_SEQUENCE;
    token = b[(*at)++];
    if (token == (uint8_t)')') {
        if (!in_print) return BL_BAD_SEQUENCE;
        return append_byte(out, (uint8_t)')');
    }
    if (token == 0x0eu || token == 0x0fu) {
        st = append_decimal(out, (unsigned int)(token - 0x0eu));
        if (st != BL_OK) return st;
        if (*at < len && b[*at] == (uint8_t)',') {
            if (!in_print || token != 0x0fu) return BL_BAD_SEQUENCE;
            ++*at;
            if (*at >= len) return BL_TRUNCATED;
            if (b[(*at)++] != 0x10u) return BL_BAD_SEQUENCE;
            st = append_word(out, ",2");
        }
    } else if (token == 0xf5u) {
        if (*at == len) return BL_TRUNCATED;
        token = b[(*at)++];
        if (token == 0x0fu) {
            st = append_word(out, "-1");
        } else if (token == 0x1fu) {
            static const uint8_t min_bits[5] = {0u,0u,0u,0u,0x90u};
            if (len - *at < sizeof(min_bits)) return BL_TRUNCATED;
            if (memcmp(b + *at, min_bits, sizeof(min_bits)) != 0)
                return BL_BAD_SEQUENCE;
            *at += sizeof(min_bits);
            st = append_word(out, "-32768");
        } else return BL_BAD_SEQUENCE;
    } else if (token == 0x02u) {
        BasicVariableRef ref;
        BVRStatus status = bvr_decode(b, len, *at - 1u, &ref);
        if (status == BVR_TRUNCATED) return BL_TRUNCATED;
        if (status != BVR_OK || ref.family != BVR_FAMILY_EXPLICIT ||
            ref.explicit_type != BVR_TYPE_INTEGER ||
            ref.name_length != 1u || b[ref.name_offset] != 0xc1u)
            return BL_BAD_SEQUENCE;
        *at = ref.reference_offset + ref.consumed;
        st = append_word(out, "A%");
    } else if (token == (uint8_t)'"') {
        if (!in_print || len - *at < 2u) return BL_BAD_SEQUENCE;
        if (b[*at] != (uint8_t)'X' ||
            b[*at + 1u] != (uint8_t)'"')
            return BL_BAD_SEQUENCE;
        *at += 2u;
        st = append_word(out, "\"X\"");
    } else return BL_BAD_SEQUENCE;
    if (st != BL_OK) return st;
    if (*at == len) return BL_TRUNCATED;
    if (b[(*at)++] != (uint8_t)')') return BL_BAD_SEQUENCE;
    return append_byte(out, (uint8_t)')');
}

static BLStatus decode(const uint8_t *body, size_t length, BLEmitter *out)
{
    size_t pos = 0;
    int seen_statement = 0;
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
        /* Three CPC-attested complete scalar records only. Cache bits
         * and REAL5 payloads must match; no sign arithmetic or decoding. */
        if (token == 0x0du) {
            static const uint8_t real_line[3][12] = {
                {0x0du, 0u, 0u, 0xc1u, 0xefu, 0x1fu,
                 0u, 0u, 0u, 0u, 0x80u, 0u},
                {0x0du, 0u, 0u, 0xc1u, 0xefu, 0x1fu,
                 0u, 0u, 0u, 0x20u, 0x81u, 0u},
                {0x0du, 0u, 0u, 0xc1u, 0xefu, 0xf5u,
                 0x1fu, 0u, 0u, 0u, 0u, 0x80u}
            };
            static const size_t lengths[3] = {11u, 11u, 12u};
            static const char *const texts[3] = {"A=0.5", "A=1.25", "A=-0.5"};
            size_t i;
            if (pos != 1u) return BL_BAD_SEQUENCE;
            for (i = 0u; i < 3u; ++i)
                if (length == lengths[i] &&
                    memcmp(body, real_line[i], lengths[i]) == 0)
                    return append_word(out, texts[i]);
            return BL_BAD_SEQUENCE;
        }
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
        case 0x02u: case 0x03u: statement = BL_ST_ASSIGN; status = BL_OK; break;
        case 0xa5u: statement = BL_ST_ASSIGN; status = append_word(out, "LET"); break;
        case 0xbfu: statement = BL_ST_PRINT; status = append_word(out, "PRINT"); break;
        case 0xbbu: statement = BL_ST_PEN; status = append_word(out, "PEN"); break;
        case 0xa2u: statement = BL_ST_INK; status = append_word(out, "INK"); break;
        case 0xa0u: statement = BL_ST_GOTO; status = append_word(out, "GOTO"); break;
        case 0x9fu: statement = BL_ST_GOSUB; status = append_word(out, "GOSUB"); break;
        case 0xc9u: status = append_word(out, "RETURN"); break;
        case 0xa1u: statement = BL_ST_IF; status = append_word(out, "IF"); break;
        case 0x9eu: statement = BL_ST_FOR; status = append_word(out, "FOR"); break;
        case 0xb0u: statement = BL_ST_NEXT; status = append_word(out, "NEXT"); break;
        case 0x8au: status = append_word(out, "CLS"); break; /* J1.21-B1 */
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
        if (statement == BL_ST_IF && seen_statement) {
            return BL_BAD_SEQUENCE;
        }
        seen_statement = 1;

        space_start = pos;
        /* For implicit LET the initial 02 is already consumed. The next
         * bytes are opaque CPC caches, NOT lexical spaces (even if 0x20). */
        if (statement != BL_ST_ASSIGN || (token != 0x02u && token != 0x03u)) {
            status = append_spaces(body, length, &pos, out);
            if (status != BL_OK) {
                return status;
            }
        }

        if (statement == BL_ST_ASSIGN) {
            BasicVariableRef ref;
            BVRStatus ref_status;
            size_t ref_start = token == 0x02u || token == 0x03u ? pos - 1u : pos;
            size_t i;
            uint8_t t;
            unsigned int number = 0u;
            int reference_operation = 0;
            int negative = 0;
            int reference_pair = 0;
            /* A5 is explicit LET, 02 begins implicit LET; both reuse the
             * CPC explicit INTEGER reference decoder, ignoring cache values. */
            if (ref_start >= length) {
                return BL_TRUNCATED;
            }
            if (body[ref_start] != 0x02u && body[ref_start] != 0x03u) {
                return body[ref_start] >= 0x80u ?
                       BL_UNKNOWN_TOKEN : BL_BAD_SEQUENCE;
            }
            ref_status = bvr_decode(body, length, ref_start, &ref);
            if (ref_status == BVR_TRUNCATED) {
                return BL_TRUNCATED;
            }
            if (ref_status != BVR_OK ||
                ref.family != BVR_FAMILY_EXPLICIT ||
                (ref.explicit_type != BVR_TYPE_INTEGER &&
                 ref.explicit_type != BVR_TYPE_STRING)) {
                return BL_BAD_SEQUENCE;
            }
            if (ref.explicit_type == BVR_TYPE_STRING &&
                (ref.cache_low != 0u || ref.cache_high != 0u))
                return BL_BAD_SEQUENCE;
            /* A5 02 without an intervening space is valid imported binary;
             * spelling LET A% makes the listing retokenisable. */
            if (token == 0xa5u && ref_start == space_start) {
                status = append_byte(out, (uint8_t)' ');
                if (status != BL_OK) {
                    return status;
                }
            }
            for (i = 0u; i < ref.name_length; ++i) {
                status = append_byte(out,
                    (uint8_t)(body[ref.name_offset + i] & 0x7fu));
                if (status != BL_OK) {
                    return status;
                }
            }
            status = append_byte(out, ref.explicit_type == BVR_TYPE_STRING ?
                                 (uint8_t)'$' : (uint8_t)'%');
            if (status != BL_OK) {
                return status;
            }
            pos = ref.reference_offset + ref.consumed;
            status = append_spaces(body, length, &pos, out);
            if (status != BL_OK) {
                return status;
            }
            if (pos >= length) {
                return BL_BAD_SEQUENCE;
            }
            if (body[pos++] != 0xefu) {
                return BL_BAD_SEQUENCE;
            }
            status = append_byte(out, (uint8_t)'=');
            if (status != BL_OK) {
                return status;
            }
            status = append_spaces(body, length, &pos, out);
            if (status != BL_OK) {
                return status;
            }
            if (pos >= length) {
                return BL_TRUNCATED;
            }
            t = body[pos++];
            if (ref.explicit_type == BVR_TYPE_STRING) {
                size_t opening;
                if (t != (uint8_t)'"') return BL_BAD_SEQUENCE;
                opening = pos;
                status = append_byte(out, t);
                if (status != BL_OK) return status;
                while (pos < length && body[pos] != (uint8_t)'"') {
                    uint8_t ch = body[pos++];
                    if (ch < 0x20u || ch > 0x7eu) return BL_BAD_SEQUENCE;
                    status = append_byte(out, ch);
                    if (status != BL_OK) return status;
                }
                if (pos == length || pos < opening) return BL_TRUNCATED;
                status = append_byte(out, body[pos++]);
                if (status != BL_OK) return status;
                status = append_spaces(body, length, &pos, out);
                if (status != BL_OK) return status;
                if (pos != length) return BL_BAD_SEQUENCE;
                return BL_OK; /* Autonomous STRING line: no suffix. */
            }
            if (t == 0xffu) {
                /* B%=ABS(A%) is the only sealed ABS assignment stream. */
                if (ref.name_length != 1u ||
                    body[ref.name_offset] != 0xc2u)
                    return BL_BAD_SEQUENCE;
                --pos;
                status = abs_expression(body, length, &pos, out, 0);
                if (status != BL_OK) return status;
                return pos == length ? BL_OK : BL_BAD_SEQUENCE;
            }
            if (t == 0xf5u) {
                negative = 1;
                /* CPC unary minus is an operator before the magnitude;
                 * only a literal operand is in the native J1.1 subset. */
                status = append_byte(out, (uint8_t)'-');
                if (status != BL_OK) {
                    return status;
                }
                if (pos >= length) {
                    return BL_TRUNCATED;
                }
                t = body[pos++];
                if (t == 0x02u) {
                    return BL_BAD_SEQUENCE;
                }
            }
            if (t == 0x02u) {
                reference_operation = 1;
                /* RHS CPC cache bytes remain opaque (20, EF, F4 included). */
                BasicVariableRef rhs;
                size_t rhs_start = pos - 1u;
                ref_status = bvr_decode(body, length, rhs_start, &rhs);
                if (ref_status == BVR_TRUNCATED) {
                    return BL_TRUNCATED;
                }
                if (ref_status != BVR_OK ||
                    rhs.family != BVR_FAMILY_EXPLICIT ||
                    rhs.explicit_type != BVR_TYPE_INTEGER) {
                    return BL_BAD_SEQUENCE;
                }
                for (i = 0u; i < rhs.name_length; ++i) {
                    status = append_byte(out,
                        (uint8_t)(body[rhs.name_offset + i] & 0x7fu));
                    if (status != BL_OK) {
                        return status;
                    }
                }
                status = append_byte(out, (uint8_t)'%');
                if (status != BL_OK) {
                    return status;
                }
                pos = rhs.reference_offset + rhs.consumed;
                status = append_spaces(body, length, &pos, out);
                if (status != BL_OK) {
                    return status;
                }
                if (pos >= length) {
                    return BL_TRUNCATED;
                }
                /* F5 is a binary minus ONLY after an INTEGER reference;
                 * the earlier F5 path remains the unary literal sign. */
                t = body[pos++];
                if (t != 0xf4u && t != 0xf5u && t != 0xf6u && t != 0xf9u && t != 0xfbu) {
                    return BL_BAD_SEQUENCE;
                }
                reference_pair = 1;
                if (t == 0xfbu) {
                    status = append_word(out, "MOD");
                } else {
                    status = append_byte(out, t == 0xf4u ? (uint8_t)'+' :
                                               t == 0xf5u ? (uint8_t)'-' :
                                               t == 0xf6u ? (uint8_t)'*' : (uint8_t)'\\');
                }
                if (status != BL_OK) {
                    return status;
                }
                status = append_spaces(body, length, &pos, out);
                if (status != BL_OK) {
                    return status;
                }
                if (pos >= length) {
                    return BL_TRUNCATED;
                }
                t = body[pos++];
            }
            if (reference_operation && t == 0x02u) {
                if (!reference_pair) {
                    return BL_BAD_SEQUENCE;
                }
                /* F4/F5/F6/F9/FB are the authorized two-reference INTEGER forms.
                 * BVR cache bytes are opaque, even if they look like tokens. */
                BasicVariableRef second;
                size_t right_start = pos - 1u;
                 ref_status = bvr_decode(body, length, right_start, &second);
                if (ref_status == BVR_TRUNCATED) {
                    return BL_TRUNCATED;
                }
                if (ref_status != BVR_OK ||
                    second.family != BVR_FAMILY_EXPLICIT ||
                    second.explicit_type != BVR_TYPE_INTEGER) {
                    return BL_BAD_SEQUENCE;
                }
                for (i = 0u; i < second.name_length; ++i) {
                    status = append_byte(out,
                        (uint8_t)(body[second.name_offset + i] & 0x7fu));
                    if (status != BL_OK) {
                        return status;
                    }
                }
                status = append_byte(out, (uint8_t)'%');
                pos = second.reference_offset + second.consumed;
            } else if (t >= 0x0eu && t <= 0x17u) {
                number = (unsigned int)(t - 0x0eu);
            } else if (t == 0x19u) {
                if (pos == length) {
                    return BL_TRUNCATED;
                }
                number = (unsigned int)body[pos++];
                if (number < 10u) {
                    return BL_BAD_SEQUENCE;
                }
            } else if (t == 0x1au) {
                /* Binary INTEGER RHS remains restricted to an 8-bit operand. A 1A
                 * here is not a LIST-representable native expression. */
                if (reference_operation) {
                    return BL_BAD_SEQUENCE;
                }
                if (length - pos < 2u) {
                    return BL_TRUNCATED;
                }
                number = (unsigned int)body[pos] |
                         ((unsigned int)body[pos + 1u] << 8);
                pos += 2u;
                /* CPC 1A is canonical only for magnitudes 256..32767
                 * in this explicitly INTEGER assignment subset. */
                if (number < 256u || number > 32767u) {
                    return BL_BAD_SEQUENCE;
                }
            } else if (t == 0x1fu) {
                /* Only the archived negative INTEGER immediate NMIN is
                 * representable here. This is NOT a REAL5 decoder. */
                if (!negative || reference_operation) {
                    return BL_BAD_SEQUENCE;
                }
                if (length - pos < 5u) {
                    return BL_TRUNCATED;
                }
                if (body[pos] != 0u || body[pos + 1u] != 0u ||
                    body[pos + 2u] != 0u || body[pos + 3u] != 0u ||
                    body[pos + 4u] != 0x90u) {
                    return BL_BAD_SEQUENCE;
                }
                pos += 5u;
                number = 32768u;
            } else {
                return t >= 0x80u || (t >= 0x0eu && t <= 0x1fu)
                        ? BL_UNKNOWN_TOKEN : BL_BAD_SEQUENCE;
            }
            if (!reference_operation || t != 0x02u) {
                status = append_decimal(out, number);
            }
            if (status != BL_OK) {
                return status;
            }
        } else if (statement == BL_ST_PRINT && pos < length && body[pos] != 0x01u) {
            uint8_t t;
            int stream8 = 0;
            if (body[pos] == (uint8_t)'#') {
                if (length - pos < 4u) return BL_TRUNCATED;
                if (body[pos + 1u] != 0x16u ||
                    body[pos + 2u] != (uint8_t)',')
                    return BL_BAD_SEQUENCE;
                status = append_word(out, "#8,");
                if (status != BL_OK) return status;
                stream8 = 1;
                pos += 3u;
            }
            if (pos == length) return BL_TRUNCATED;
            t = body[pos++];
            if (t == 0xffu) {
                /* '?' can encode BF FF00 with no separating space.
                 * LIST expands BF to PRINT: emit the same operand boundary
                 * used for numeric and explicit-variable PRINT operands.
                 * #8,ABS and already-spaced PRINT must stay unchanged. */
                if (space_start == pos - 1u) {
                    status = append_byte(out, (uint8_t)' ');
                    if (status != BL_OK) return status;
                }
                --pos;
                status = abs_expression(body, length, &pos, out, 1);
                if (status != BL_OK) return status;
                if (pos != length) return BL_BAD_SEQUENCE;
            } else if (stream8 && !(t == 0x02u || t == 0x19u))
                return BL_BAD_SEQUENCE;
            else if (t == (uint8_t)'"') {
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
            } else if (t == 0x0du) {
                static const uint8_t scalar_print[] = {
                    0xbfu, (uint8_t)' ', 0x0du, 0u, 0u, 0xc1u
                };
                if (length != sizeof(scalar_print) ||
                    memcmp(body, scalar_print, sizeof(scalar_print)) != 0)
                    return BL_BAD_SEQUENCE;
                status = append_byte(out, (uint8_t)'A');
                pos = length;
            } else if (t >= 0x02u && t <= 0x04u) {
                BasicVariableRef ref;
                BVRStatus ref_status = bvr_decode(body, length, pos - 1u, &ref);
                size_t i;
                uint8_t suffix;
                if (ref_status == BVR_TRUNCATED) {
                    return BL_TRUNCATED;
                }
                if (ref_status != BVR_OK || ref.family != BVR_FAMILY_EXPLICIT) {
                    return BL_BAD_SEQUENCE;
                }
                /* Legacy PRINT references may have CPC-populated opaque
                 * nonzero caches.  J1.15-B only constrains new assignments. */
                switch (ref.explicit_type) {
                case BVR_TYPE_INTEGER: suffix = (uint8_t)'%'; break;
                case BVR_TYPE_STRING: suffix = (uint8_t)'$'; break;
                case BVR_TYPE_REAL: suffix = (uint8_t)'!'; break;
                default: return BL_BAD_SEQUENCE;
                }
                /* The '?' alias can store BF 02/03/04 with no separating
                 * space. LIST writes PRINT, so make its textual operand
                 * boundary unambiguous without rewriting the CPC bytes. */
                if (space_start == pos - 1u) {
                    status = append_byte(out, (uint8_t)' ');
                    if (status != BL_OK) {
                        return status;
                    }
                }
                /* The two CPC cache bytes are not pointers; LIST never changes them. */
                for (i = 0u; i < ref.name_length; ++i) {
                    status = append_byte(out,
                        (uint8_t)(body[ref.name_offset + i] & 0x7fu));
                    if (status != BL_OK) {
                        return status;
                    }
                }
                status = append_byte(out, suffix);
                pos = ref.reference_offset + ref.consumed;
            } else if (t >= 0x0eu && t <= 0x17u) {
                /* As for explicit variables, ?0..9 need a printable
                 * separator after LIST expands the alias to PRINT. */
                if (space_start == pos - 1u) {
                    status = append_byte(out, (uint8_t)' ');
                    if (status != BL_OK) {
                        return status;
                    }
                }
                status = append_decimal(out, (unsigned int)(t - 0x0eu));
            } else if (t == 0x19u) {
                if (pos == length) {
                    return BL_TRUNCATED;
                }
                if (body[pos] < 10u) {
                    return BL_BAD_SEQUENCE; /* J0.4 emits small digits as 0E..17 */
                }
                if (space_start == pos - 1u) {
                    status = append_byte(out, (uint8_t)' ');
                    if (status != BL_OK) {
                        return status;
                    }
                }
                status = append_decimal(out, (unsigned int)body[pos++]);
            } else {
                return t >= 0x80u || (t >= 0x0eu && t <= 0x1fu)
                        ? BL_UNKNOWN_TOKEN : BL_BAD_SEQUENCE;
            }
            if (status != BL_OK) {
                return status;
            }

        } else if (statement == BL_ST_FOR) {
            /* B1 grammar: FOR INTEGER%=literal TO literal [STEP literal].
             * LIST is textual; raw CPC reference caches remain unchanged. */
            if (pos >= length) return BL_TRUNCATED;
            if (pos == space_start) {
                status = append_byte(out, (uint8_t)' ');
                if (status != BL_OK) return status;
            }
            status = for_reference(body, length, &pos, out);
            if (status != BL_OK) return status;
            status = append_spaces(body, length, &pos, out);
            if (status != BL_OK) return status;
            if (pos >= length) return BL_TRUNCATED;
            if (body[pos++] != 0xefu) return BL_BAD_SEQUENCE;
            status = append_byte(out, (uint8_t)'=');
            if (status == BL_OK) status = append_spaces(body, length, &pos, out);
            if (status == BL_OK) status = for_number(body, length, &pos, out);
            if (status != BL_OK) return status;
            space_start = pos;
            status = append_spaces(body, length, &pos, out);
            if (status != BL_OK) return status;
            if (pos == length) return BL_TRUNCATED;
            if (body[pos++] != 0xecu) return BL_BAD_SEQUENCE;
            if (pos - 1u == space_start) {
                status = append_byte(out, (uint8_t)' ');
                if (status != BL_OK) return status;
            }
            status = append_word(out, "TO");
            if (status != BL_OK) return status;
            space_start = pos;
            status = append_spaces(body, length, &pos, out);
            if (status != BL_OK) return status;
            if (pos == space_start) {
                status = append_byte(out, (uint8_t)' ');
                if (status != BL_OK) return status;
            }
            status = for_number(body, length, &pos, out);
            if (status != BL_OK) return status;
            space_start = pos;
            status = append_spaces(body, length, &pos, out);
            if (status != BL_OK) return status;
            if (pos < length && body[pos] == 0xe6u) {
                if (pos == space_start) {
                    status = append_byte(out, (uint8_t)' ');
                    if (status != BL_OK) return status;
                }
                ++pos;
                status = append_word(out, "STEP");
                if (status != BL_OK) return status;
                space_start = pos;
                status = append_spaces(body, length, &pos, out);
                if (status != BL_OK) return status;
                if (pos == space_start) {
                    status = append_byte(out, (uint8_t)' ');
                    if (status != BL_OK) return status;
                }
                status = for_number(body, length, &pos, out);
                if (status != BL_OK) return status;
            }
        } else if (statement == BL_ST_NEXT) {
            if (pos < length && body[pos] == 0x02u) {
                if (pos == space_start) {
                    status = append_byte(out, (uint8_t)' ');
                    if (status != BL_OK) return status;
                }
                status = for_reference(body, length, &pos, out);
                if (status != BL_OK) return status;
            }
        } else if (statement == BL_ST_IF) {
            BasicVariableRef reference;
            BVRStatus decoded;
            size_t i;
            unsigned int line;
            if (pos == length) {
                return BL_TRUNCATED;
            }
            decoded = bvr_decode(body, length, pos, &reference);
            if (decoded == BVR_TRUNCATED) {
                return BL_TRUNCATED;
            }
            if (decoded != BVR_OK ||
                reference.family != BVR_FAMILY_EXPLICIT ||
                reference.explicit_type != BVR_TYPE_INTEGER) {
                return BL_BAD_SEQUENCE;
            }
            /* Imported IF may omit lexical separators even though the
             * token stream is executable. The BVR cache bytes at pos+1/2
             * are opaque and never count as source spaces. */
            if (pos == space_start) {
                status = append_byte(out, (uint8_t)' ');
                if (status != BL_OK) {
                    return status;
                }
            }
            for (i = 0u; i < reference.name_length; ++i) {
                status = append_byte(out,
                    (uint8_t)(body[reference.name_offset + i] & 0x7fu));
                if (status != BL_OK) {
                    return status;
                }
            }
            status = append_byte(out, (uint8_t)'%');
            if (status != BL_OK) {
                return status;
            }
            pos = reference.reference_offset + reference.consumed;
            space_start = pos;
            status = append_spaces(body, length, &pos, out);
            if (status != BL_OK) {
                return status;
            }
            if (pos < length &&
                (body[pos] == 0xefu || body[pos] == 0xf2u ||
                 body[pos] == 0xf1u || body[pos] == 0xf3u ||
                 body[pos] == 0xeeu || body[pos] == 0xf0u)) {
                const char *spelling;
                switch (body[pos++]) {
                case 0xefu: spelling = "="; break;
                case 0xf2u: spelling = "<>"; break;
                case 0xf1u: spelling = "<"; break;
                case 0xf3u: spelling = "<="; break;
                case 0xeeu: spelling = ">"; break;
                default: spelling = ">="; break;
                }
                status = append_word(out, spelling);
                if (status != BL_OK) return status;
                status = append_spaces(body, length, &pos, out);
                if (status != BL_OK) return status;
                /* The 02 two-byte cache is opaque even if it contains a
                 * space or an operator token. */
                status = for_reference(body, length, &pos, out);
                if (status != BL_OK) return status;
                space_start = pos;
                status = append_spaces(body, length, &pos, out);
                if (status != BL_OK) return status;
            }
            if (pos == length || body[pos] != 0xebu) {
                return BL_BAD_SEQUENCE;
            }
            if (pos == space_start) {
                /* B%THEN or A%THEN needs a lexical separator to retokenize. */
                status = append_byte(out, (uint8_t)' ');
                if (status != BL_OK) {
                    return status;
                }
            }
            ++pos;
            status = append_word(out, "THEN");
            if (status != BL_OK) {
                return status;
            }
            space_start = pos;
            status = append_spaces(body, length, &pos, out);
            if (status != BL_OK) {
                return status;
            }
            if (pos == length) {
                return BL_TRUNCATED;
            }
            if (body[pos] == 0x02u) {
                /* THEN with one INTEGER arm, optionally followed by
                 * the ROM's 01 97 lexical ELSE (never a source colon). */
                if (pos == space_start) {
                    status = append_byte(out, (uint8_t)' ');
                    if (status != BL_OK) return status;
                }
                status = inline_if_assignment(body, length, &pos, out);
                if (status != BL_OK) return status;
                space_start = pos;
                status = append_spaces(body, length, &pos, out);
                if (status != BL_OK) return status;
                if (pos < length && body[pos] == 0x01u &&
                    pos + 1u < length && body[pos + 1u] == 0x97u) {
                    if (pos == space_start) {
                        status = append_byte(out, (uint8_t)' ');
                        if (status != BL_OK) return status;
                    }
                    pos += 2u;
                    status = append_word(out, "ELSE");
                    if (status != BL_OK) return status;
                    space_start = pos;
                    status = append_spaces(body, length, &pos, out);
                    if (status != BL_OK) return status;
                    if (pos == length) return BL_TRUNCATED;
                    if (pos == space_start) {
                        status = append_byte(out, (uint8_t)' ');
                        if (status != BL_OK) return status;
                    }
                    status = inline_if_assignment(body, length, &pos, out);
                    if (status != BL_OK) return status;
                }
            } else if (body[pos] == 0x1eu) {
                if (pos == space_start) {
                    /* THEN60 needs a separator for retokenisation. */
                    status = append_byte(out, (uint8_t)' ');
                    if (status != BL_OK) return status;
                }
                ++pos;
                if (length - pos < 2u) return BL_TRUNCATED;
                line = (unsigned int)body[pos] |
                       ((unsigned int)body[pos + 1u] << 8);
                pos += 2u;
                if (line == 0u) return BL_BAD_SEQUENCE;
                status = append_decimal(out, line);
                if (status != BL_OK) return status;
            } else {
                return BL_BAD_SEQUENCE;
            }
        } else if (statement == BL_ST_INK) {
            int pen_index, colour, third;
            if (pos == length || body[pos] == 0x01u)
                return BL_BAD_SEQUENCE;
            if (pos == space_start) {
                status = append_byte(out, (uint8_t)' ');
                if (status != BL_OK) return status;
            }
            status = ink_literal(body, length, &pos, out, 16u, &pen_index);
            if (status != BL_OK) return status;
            if (pos == length || body[pos++] != (uint8_t)',')
                return BL_BAD_SEQUENCE;
            status = append_byte(out, (uint8_t)',');
            if (status != BL_OK) return status;
            status = ink_literal(body, length, &pos, out, 32u, &colour);
            if (status != BL_OK) return status;
            if (pos < length && body[pos] == (uint8_t)',') {
                if (pen_index != 1 || colour != 26) return BL_BAD_SEQUENCE;
                ++pos;
                status = append_byte(out, (uint8_t)',');
                if (status != BL_OK) return status;
                status = ink_literal(body, length, &pos, out, 32u, &third);
                if (status != BL_OK) return status;
                if (third != 6) return BL_BAD_SEQUENCE;
            }
        } else if (statement == BL_ST_PEN) {
            unsigned int pen;
            uint8_t literal;
            if (pos == length || body[pos] == 0x01u)
                return BL_BAD_SEQUENCE;
            if (pos == space_start) {
                status = append_byte(out, (uint8_t)' ');
                if (status != BL_OK) return status;
            }
            literal = body[pos++];
            if (literal >= 0x0eu && literal <= 0x17u) {
                pen = (unsigned int)(literal - 0x0eu);
            } else if (literal == 0x19u) {
                if (pos == length) return BL_TRUNCATED;
                pen = (unsigned int)body[pos++];
                if (pen < 10u || pen > 16u) return BL_BAD_SEQUENCE;
            } else if (literal == 0xf5u) {
                if (pos == length) return BL_TRUNCATED;
                if (body[pos++] != 0x0fu) return BL_BAD_SEQUENCE;
                status = append_byte(out, (uint8_t)'-');
                if (status != BL_OK) return status;
                pen = 1u;
            } else {
                return literal >= 0x80u || (literal >= 0x0eu && literal <= 0x1fu)
                     ? BL_UNKNOWN_TOKEN : BL_BAD_SEQUENCE;
            }
            status = append_decimal(out, pen);
            if (status != BL_OK) return status;
        } else if (statement == BL_ST_GOTO || statement == BL_ST_GOSUB) {
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
        if (statement == BL_ST_IF) {
            return BL_BAD_SEQUENCE; /* No suffix or colon. */
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
