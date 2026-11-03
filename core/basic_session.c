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

/* Source of positive recognition: Locomotive BASIC 1.1 ROM basic.asm,
 * E418 (A..Z buckets), keyword spellings E44C..E720. Includes functions,
 * operators, keywords absent from this project's limited C99 tokenizer,
 * and the built-in AUTO/MODE/PAPER/GOTO direct commands. This is a lexer
 * guard, NOT a second statement parser and NOT a CPC ERR classifier.
 *
 * The ROM also has multiword forms "ON SQ", "ON BREAK", "GO TO", "GO SUB",
 * and a few symbol tokens. Their leading words ON/GOTO/GOSUB are in this
 * positive list; multiword / punctuation forms remain unclassified below.
 * TAGOFF is the canonical token (the E493 table comment says TAFOFF). */
static const char cpc_rom_known_words[] =
    "ABS AFTER AND ASC ATN AUTO "
    "BIN$ BORDER "
    "CALL CAT CHAIN CHR$ CINT CLEAR CLG CLOSEIN CLOSEOUT CLS "
    "CONT COPYCHR$ COS CREAL CURSOR "
    "DATA DEC$ DEF DEFINT DEFREAL DEFSTR DEG DELETE DERR DI "
    "DIM DRAW DRAWR "
    "EDIT EI ELSE END ENT ENV EOF ERASE ERL ERR ERROR EVERY EXP "
    "FILL FIX FN FOR FRAME FRE "
    "GOSUB GOTO GRAPHICS "
    "HEX$ HIMEM "
    "IF INK INKEY INKEY$ INP INPUT INSTR INT "
    "JOY KEY "
    "LEFT$ LEN LET LINE LIST LOAD LOCATE LOG LOG10 LOWER$ "
    "MASK MAX MEMORY MERGE MID$ MIN MOD MODE MOVE MOVER "
    "NEW NEXT NOT "
    "ON OPENIN OPENOUT OR ORIGIN OUT "
    "PAPER PEEK PEN PI PLOT PLOTR POKE POS PRINT "
    "RAD RANDOMIZE READ RELEASE REM REMAIN RENUM RESTORE "
    "RESUME RETURN RIGHT$ RND ROUND RUN "
    "SAVE SGN SIN SOUND SPACE$ SPC SPEED SQ SQR STEP STOP "
    "STR$ STRING$ SWAP SYMBOL "
    "TAB TAG TAGOFF TAN TEST TESTR THEN TIME TO TROFF TRON "
    "UNT UPPER$ USING "
    "VAL VPOS "
    "WAIT WEND WHILE WIDTH WINDOW WRITE "
    "XOR XPOS YPOS ZONE";

/* Exact positive look-up, not prefix matching: "RUNN" must not acquire
 * the recognized RUN status. No temporary copies or mutable state. */
static int cpc_rom_word_known(const uint8_t *source, size_t length)
{
    const char *p=cpc_rom_known_words;
    while(*p!='\0') {
        size_t i=0u;
        int equal=1;
        while(p[i]!='\0' && p[i]!=' ') {
            if(i>=length || upper(source[i])!=(uint8_t)p[i]) equal=0;
            ++i;
        }
        if(equal && i==length) return 1;
        p+=i;
        if(*p==' ') ++p;
    }
    return 0;
}

/* Fail closed: classify ONLY a complete, isolated ASCII alphabetic
 * keyword-like direct word absent from the ROM lexicon. No arguments,
 * punctuation, quotations, digits, tabs, separators, variable suffix,
 * assignment or other grammar are inferred. A single letter can be a
 * variable name and remains ambiguous. All ambiguous forms retain the
 * historical BS_UNSUPPORTED_DIRECT. */
static int direct_word_proven_unknown(const uint8_t *source, size_t length)
{
    if(length<2u) return 0;
    for(size_t i=0u;i<length;++i) {
        const uint8_t c=source[i];
        if(!((c>='A' && c<='Z') || (c>='a' && c<='z')))
            return 0;
    }
    return !cpc_rom_word_known(source,length);
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
    if(direct_word_proven_unknown(source+cursor,i-cursor))
        return simple(BS_UNKNOWN_DIRECT);
    return simple(BS_UNSUPPORTED_DIRECT);
}
