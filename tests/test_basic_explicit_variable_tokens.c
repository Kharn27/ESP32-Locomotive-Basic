#include "basic_variable_ref.h"
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_executor.h"
#include "basic_session_runtime.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

/* Synthetic ROM-derived vectors, not independently captured CPC bytes. */
static int test_encoder(void)
{
    static const struct {
        BVRExplicitType type;
        uint8_t marker;
    } cases[] = {
        { BVR_TYPE_INTEGER, 0x02u },
        { BVR_TYPE_STRING, 0x03u },
        { BVR_TYPE_REAL, 0x04u }
    };
    uint8_t encoded[64], snapshot[64];
    uint8_t name[40];
    size_t written, i, n;
    BasicVariableRef ref;

    for (i = 0u; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        static const uint8_t a[] = {'A'};
        memset(encoded, 0x5au, sizeof(encoded));
        written = 1111u;
        CHECK(bvr_encode_explicit(a, sizeof(a), cases[i].type,
                                  encoded, sizeof(encoded), &written) == BVR_OK);
        CHECK(written == 4u);
        CHECK(encoded[0] == cases[i].marker && encoded[1] == 0u &&
              encoded[2] == 0u && encoded[3] == 0xc1u && encoded[4] == 0x5au);
        CHECK(bvr_decode(encoded, written, 0u, &ref) == BVR_OK);
        CHECK(ref.explicit_type == cases[i].type && ref.name_length == 1u);
        CHECK(ref.cache_low == 0u && ref.cache_high == 0u);
        CHECK(ref.consumed == written);
    }
    for (i = 0u; i < sizeof(name); ++i) {
        name[i] = (uint8_t)('a' + (int)(i % 26u));
    }
    name[7] = (uint8_t)'3';
    name[8] = (uint8_t)'.';
    name[39] = (uint8_t)'Z';
    memcpy(snapshot, name, sizeof(name));
    memset(encoded, 0xaau, sizeof(encoded));
    written = 0u;
    CHECK(bvr_encode_explicit(name, sizeof(name), BVR_TYPE_REAL,
                              encoded, sizeof(encoded), &written) == BVR_OK);
    CHECK(written == 43u && encoded[0] == 4u);
    CHECK(encoded[1] == 0u && encoded[2] == 0u);
    for (i = 0u; i < 39u; ++i) {
        CHECK(encoded[3u + i] == name[i]);
        CHECK((encoded[3u + i] & 0x80u) == 0u);
    }
    CHECK(encoded[42] == (uint8_t)('Z' | 0x80));
    CHECK(encoded[43] == 0xaau);
    CHECK(memcmp(name, snapshot, sizeof(name)) == 0);
    CHECK(bvr_decode(encoded, written, 0u, &ref) == BVR_OK);
    CHECK(ref.name_length == 40u && ref.consumed == 43u);
    n = 0u;
    CHECK(bvr_encode_explicit((const uint8_t *)"a.2", 3u, BVR_TYPE_STRING,
                              encoded, sizeof(encoded), &n) == BVR_OK);
    CHECK(n == 6u && encoded[3] == 'a' && encoded[4] == '.' &&
          encoded[5] == (uint8_t)('2' | 0x80));
    return 0;
}

static int test_encoder_errors(void)
{
    static const uint8_t bad[][3] = {
        {'1','A','B'}, {'A','_','B'}, {'A','%','B'},
        {'A',0u,'B'}, {'A',0xffu,'B'}, {'A','#','B'}
    };
    uint8_t dest[64], before[64], long_name[41];
    size_t written, i;
    union { size_t aligned; uint8_t bytes[64]; } shared;
    static const uint8_t good[] = {'A','1'};

    memset(dest, 0x77, sizeof(dest));
    memcpy(before, dest, sizeof(dest));
    written = 123u;
    for (i = 0u; i < sizeof(bad) / sizeof(bad[0]); ++i) {
        CHECK(bvr_encode_explicit(bad[i], sizeof(bad[i]), BVR_TYPE_INTEGER,
                                  dest, sizeof(dest), &written) == BVR_MALFORMED);
    }
    memset(long_name, 'A', sizeof(long_name));
    CHECK(bvr_encode_explicit(long_name, sizeof(long_name), BVR_TYPE_INTEGER,
                              dest, sizeof(dest), &written) == BVR_LIMIT_EXCEEDED);
    CHECK(bvr_encode_explicit(good, 0u, BVR_TYPE_INTEGER,
                              dest, sizeof(dest), &written) == BVR_MALFORMED);
    CHECK(bvr_encode_explicit(good, 2u, BVR_TYPE_UNDETERMINED,
                              dest, sizeof(dest), &written) == BVR_INVALID_ARGUMENT);
    CHECK(bvr_encode_explicit(good, 2u, (BVRExplicitType)99,
                              dest, sizeof(dest), &written) == BVR_INVALID_ARGUMENT);
    CHECK(bvr_encode_explicit(NULL, 1u, BVR_TYPE_INTEGER,
                              dest, sizeof(dest), &written) == BVR_INVALID_ARGUMENT);
    CHECK(bvr_encode_explicit(good, 2u, BVR_TYPE_INTEGER,
                              NULL, sizeof(dest), &written) == BVR_INVALID_ARGUMENT);
    CHECK(bvr_encode_explicit(good, 2u, BVR_TYPE_INTEGER,
                              dest, sizeof(dest), NULL) == BVR_INVALID_ARGUMENT);
    CHECK(bvr_encode_explicit(good, 2u, BVR_TYPE_INTEGER,
                              dest, 4u, &written) == BVR_LIMIT_EXCEEDED);
    CHECK(bvr_encode_explicit(good, 2u, BVR_TYPE_INTEGER,
                              dest, 0u, &written) == BVR_LIMIT_EXCEEDED);
    CHECK(bvr_encode_explicit(dest, 2u, BVR_TYPE_INTEGER,
                              dest, sizeof(dest), &written) == BVR_OVERLAPPING_MEMORY);
    /* A valid aligned written pointer within the destination is rejected. */
    CHECK(bvr_encode_explicit(good, 2u, BVR_TYPE_INTEGER,
                              shared.bytes, sizeof(shared.bytes),
                              &shared.aligned) == BVR_OVERLAPPING_MEMORY);
    CHECK(written == 123u && memcmp(dest, before, sizeof(dest)) == 0);
    return 0;
}

static int roundtrip(const char *text, const uint8_t *expected, size_t n)
{
    uint8_t tokens[128], decoded[128], again[128];
    size_t length = 0u, listed = 0u, repeated = 0u;
    memset(tokens, 0x44, sizeof(tokens));
    CHECK(bt_tokenize((const uint8_t *)text, strlen(text), tokens,
                      sizeof(tokens), &length) == BT_OK);
    CHECK(length == n && memcmp(tokens, expected, n) == 0);
    CHECK(tokens[n] == 0x44u);
    CHECK(bl_detokenize(tokens, length, decoded,
                        sizeof(decoded), &listed) == BL_OK);
    /* PRINT aliases and keyword case are canonically emitted as PRINT. */
    CHECK(listed == strlen(text) && memcmp(decoded, text, listed) == 0);
    CHECK(bt_tokenize(decoded, listed, again,
                      sizeof(again), &repeated) == BT_OK);
    CHECK(repeated == length && memcmp(again, tokens, length) == 0);
    return 0;
}

static int test_tokenizer_and_listing(void)
{
    static const uint8_t intref[] = {0xbfu,' ',0x02u,0,0,0xc1u};
    static const uint8_t realref[] = {0xbfu,' ',0x04u,0,0,'x','y',0xfau};
    static const uint8_t implicit_half_a[] = {0xbfu,' ',0x0du,0,0,0xc1u};
    static const uint8_t strref[] = {0xbfu,' ',0x03u,0,0,'N','O','M','.','2'|0x80};
    static const uint8_t compound[] = {0xbfu,' ',0x02u,0,0,0xc1u,0x01u,0x98u};
    static const uint8_t string[] = {0xbfu,' ','"','A','%','"'};
    static const uint8_t rem[] = {0xc5u,' ','A','%',':','E','N','D'};
    static const uint8_t apostrophe[] = {0x01u,0xc0u,' ','A','%',':','E','N','D'};
    static const uint8_t spaces[] = {' ',0xbfu,' ',' ',0x02u,0,0,0xc1u,' '};
    static const char *invalid[] = {
        "PRINT 1A%", "PRINT A%%", "PRINT A%$",
        "PRINT A!!", "PRINT A%1", "PRINT A%ABC", "PRINT A%_",
        "PRINT A#","PRINT A_B%", "PRINT A..2%?", "PRINT %A",
        "PRINT ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNO%",
        "PRINT A%+1", "PRINT A%!","PRINT A%:","PRINT A%::END"
    };
    uint8_t dst[128], snapshot[128];
    size_t n, i;

    CHECK(roundtrip("PRINT A%", intref, sizeof(intref)) == 0);
    /* Pre-B rejection promoted only for this one implicit A reference. */
    CHECK(roundtrip("PRINT A", implicit_half_a, sizeof(implicit_half_a)) == 0);
    CHECK(roundtrip("PRINT xyz!", realref, sizeof(realref)) == 0);
    CHECK(roundtrip("PRINT NOM.2$", strref, sizeof(strref)) == 0);
    CHECK(roundtrip("PRINT A%:END", compound, sizeof(compound)) == 0);
    CHECK(roundtrip("PRINT \"A%\"", string, sizeof(string)) == 0);
    CHECK(roundtrip("REM A%:END", rem, sizeof(rem)) == 0);
    CHECK(roundtrip("' A%:END", apostrophe, sizeof(apostrophe)) == 0);
    CHECK(roundtrip(" PRINT  A% ", spaces, sizeof(spaces)) == 0);
    for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        memset(dst, 0x7au, sizeof(dst));
        memcpy(snapshot, dst, sizeof(dst));
        n = 333u;
        CHECK(bt_tokenize((const uint8_t *)invalid[i], strlen(invalid[i]),
                          dst, sizeof(dst), &n) != BT_OK);
        CHECK(n == 333u && memcmp(dst, snapshot, sizeof(dst)) == 0);
    }
    /* Exact 40-byte name + one explicit suffix in a PRINT body. */
    {
        uint8_t source[48], token[64], text[48];
        size_t t, listed;
        memcpy(source, "PRINT ", 6u);
        memset(source + 6u, 'Q', 40u);
        source[46] = '%';
        CHECK(bt_tokenize(source, 47u, token, sizeof(token), &t) == BT_OK);
        CHECK(t == 45u && token[2] == 0x02u && token[44] == (uint8_t)('Q'|0x80));
        CHECK(bl_detokenize(token, t, text, sizeof(text), &listed) == BL_OK);
        CHECK(listed == 47u && memcmp(text, source, 47u) == 0);
    }
    return 0;
}

static int test_bad_listing_and_capacity(void)
{
    static const uint8_t missing_cache[] = {0xbfu,' ',0x02u,0x00u};
    static const uint8_t missing_name[] = {0xbfu,' ',0x02u,0x00u,0x00u};
    static const uint8_t no_terminal[] = {0xbfu,' ',0x02u,0x00u,0x00u,'A'};
    static const uint8_t invalid_name[] = {0xbfu,' ',0x03u,0x00u,0x00u,0xbfu};
    static const uint8_t unsuffixed[] = {0xbfu,' ',0x0bu,0x00u,0x00u,0xc1u};
    static const uint8_t valid[] = {0xbfu,' ',0x02u,0x00u,0x00u,0xc1u};
    uint8_t too_long[46], output[64], before[64];
    size_t n = 777u, i;

    memset(output, 0x55u, sizeof(output));
    memcpy(before, output, sizeof(output));
    CHECK(bl_detokenize(missing_cache, sizeof(missing_cache), output,
                        sizeof(output), &n) == BL_TRUNCATED);
    CHECK(bl_detokenize(missing_name, sizeof(missing_name), output,
                        sizeof(output), &n) == BL_TRUNCATED);
    CHECK(bl_detokenize(no_terminal, sizeof(no_terminal), output,
                        sizeof(output), &n) == BL_TRUNCATED);
    CHECK(bl_detokenize(invalid_name, sizeof(invalid_name), output,
                        sizeof(output), &n) == BL_BAD_SEQUENCE);
    CHECK(bl_detokenize(unsuffixed, sizeof(unsuffixed), output,
                        sizeof(output), &n) == BL_BAD_SEQUENCE);
    too_long[0] = 0xbfu;
    too_long[1] = ' ';
    too_long[2] = 0x02u;
    too_long[3] = 0u;
    too_long[4] = 0u;
    for (i = 0u; i < 41u; ++i) {
        too_long[5u + i] = 'A';
    }
    too_long[45] |= 0x80u;
    CHECK(bl_detokenize(too_long, sizeof(too_long), output,
                        sizeof(output), &n) == BL_BAD_SEQUENCE);
    CHECK(bl_detokenize(valid, sizeof(valid), output,
                        7u, &n) == BL_NO_SPACE); /* PRINT A% = 8 chars */
    CHECK(bl_detokenize(valid, sizeof(valid), (uint8_t *)(void *)valid,
                        sizeof(valid), &n) == BL_OVERLAP);
    CHECK(n == 777u && memcmp(output, before, sizeof(output)) == 0);
    CHECK(bt_tokenize((const uint8_t *)"PRINT A%", 8u, output,
                      5u, &n) == BT_NO_SPACE);
    CHECK(n == 777u && memcmp(output, before, sizeof(output)) == 0);
    return 0;
}

static int test_program_cache_and_run(void)
{
    uint8_t storage[1024], body[128], listing[1024], image[1024];
    uint8_t run_out[128], saved_out[128];
    BasicProgram program;
    BasicExecutor executor;
    uint8_t imported[] = {0xbfu,' ',0x03u,0x34u,0x12u,'S'|0x80};
    static const char *lines[] = {"PRINT A%", "PRINT B!", "PRINT S$", "END"};
    static const char *expected = "10 PRINT A%\n20 PRINT B!\n30 PRINT S$\n40 END\n50 PRINT S$\n";
    size_t n, w, i;
    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    for (i = 0u; i < 4u; ++i) {
        CHECK(bt_tokenize((const uint8_t *)lines[i], strlen(lines[i]),
                          body, sizeof(body), &n) == BT_OK);
        CHECK(bp_put(&program, (uint16_t)((i+1u)*10u), body, n) == BP_OK);
    }
    CHECK(bp_put(&program, 50u, imported, sizeof(imported)) == BP_OK);
    memset(image, 0, sizeof(image));
    CHECK(bp_export(&program, image, sizeof(image), &w) == BP_OK);
    CHECK(bl_list_program(&program, listing, sizeof(listing), &n) == BL_OK);
    CHECK(n == strlen(expected) && memcmp(listing, expected, n) == 0);
    /* Genuine tokenize -> numbered program -> LIST -> tokenize roundtrip. */
    {
        size_t offset = 0u;
        for (i = 0u; i < 4u; ++i) {
            size_t end = offset;
            size_t again = 0u;
            BasicProgramLine line;
            while (end < n && listing[end] != (uint8_t)'\n') {
                ++end;
            }
            CHECK(end < n && end >= offset + 3u);
            CHECK(bt_tokenize(listing + offset + 3u,
                              end - offset - 3u, body,
                              sizeof(body), &again) == BT_OK);
            CHECK(bp_find(&program, (uint16_t)((i + 1u) * 10u), &line) == BP_OK);
            CHECK(again == line.body_length);
            CHECK(memcmp(body, program.data + line.body_offset, again) == 0);
            offset = end + 1u;
        }
    }
    /* Program-wide LIST errors must be atomic even after valid lines. */
    {
        const uint8_t broken[] = {0xbfu, ' ', 0x02u, 0u, 0u, 'A'};
        uint8_t before[sizeof(listing)];
        size_t failed_written = 556u;
        CHECK(bp_put(&program, 60u, broken, sizeof(broken)) == BP_OK);
        memset(listing, 0x39, sizeof(listing));
        memcpy(before, listing, sizeof(listing));
        CHECK(bl_list_program(&program, listing, sizeof(listing),
                              &failed_written) == BL_TRUNCATED);
        CHECK(failed_written == 556u);
        CHECK(memcmp(listing, before, sizeof(listing)) == 0);
        CHECK(bp_delete(&program, 60u) == BP_OK);
    }
    {
        uint8_t after[1024];
        size_t a;
        CHECK(bp_export(&program, after, sizeof(after), &a) == BP_OK);
        CHECK(a == w && memcmp(after, image, w) == 0);
    }
    /* A nonzero CPC cache survives LIST and decoding unmodified. */
    {
        BasicProgramLine line;
        CHECK(bp_find(&program, 50u, &line) == BP_OK);
        CHECK(memcmp(program.data + line.body_offset, imported,
                     sizeof(imported)) == 0);
    }
    CHECK(be_init(&executor, &program) == BE_OK);
    memset(run_out, 0x78, sizeof(run_out));
    memcpy(saved_out, run_out, sizeof(run_out));
    n = 987u;
    CHECK(be_step(&executor, run_out, sizeof(run_out), &n) == BE_UNSUPPORTED);
    CHECK(n == 987u && executor.cursor == 0u);
    CHECK(memcmp(run_out, saved_out, sizeof(run_out)) == 0);

    /* An earlier PRINT on the same numbered line is not partly committed. */
    CHECK(bt_tokenize((const uint8_t *)"PRINT \"OK\":PRINT A%", 19u,
                      body, sizeof(body), &w) == BT_OK);
    CHECK(bp_put(&program, 10u, body, w) == BP_OK);
    CHECK(be_init(&executor, &program) == BE_OK);
    CHECK(be_step(&executor, run_out, sizeof(run_out), &n) == BE_UNSUPPORTED);
    CHECK(n == 987u && executor.cursor == 0u);
    CHECK(memcmp(run_out, saved_out, sizeof(run_out)) == 0);
    /* No implicit run-time rewrite of variable cache bytes. */
    CHECK(bp_find(&program, 50u, &(BasicProgramLine){0}) == BP_OK);
    return 0;
}

static int test_session_integration(void)
{
    uint8_t storage[1024], scratch[256], out[512];
    BasicProgram program;
    BasicSessionRuntime runtime;
    BSRResult r;
    size_t written = 0u;
    const char *listed = "10 PRINT A%\n20 PRINT B!\n30 PRINT S$\n40 END\n";
    const char *input[] = {"10 PRINT A%", "20 PRINT B!", "30 PRINT S$", "40 END"};
    size_t i;

    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    CHECK(bsr_init(&runtime, &program).status == BSR_OK);
    for (i = 0u; i < 4u; ++i) {
        CHECK(bsr_submit(&runtime, (const uint8_t *)input[i],
                         strlen(input[i]), scratch, sizeof(scratch),
                         out, sizeof(out), &written).status == BSR_OK);
    }
    r = bsr_submit(&runtime, (const uint8_t *)"LIST", 4u,
                   scratch, sizeof(scratch), out, sizeof(out), &written);
    CHECK(r.status == BSR_OK);
    CHECK(written == strlen(listed) && memcmp(out, listed, written) == 0);
    CHECK(bsr_submit(&runtime, (const uint8_t *)"RUN", 3u,
                     scratch, sizeof(scratch), out, sizeof(out), &written).status == BSR_OK);
    written = 223u;
    memset(out, 0x33, sizeof(out));
    r = bsr_step(&runtime, out, sizeof(out), &written);
    CHECK(r.status == BSR_EXECUTOR_ERROR && r.executor_status == BE_UNSUPPORTED);
    CHECK(written == 223u && out[0] == 0x33u);
    return 0;
}


/* J0.16-C1: the '?' alias can store a reference immediately after BF.
 * LIST must be total on that accepted subset, and its canonical text
 * must retokenize into a stable wire representation. */
static int c1_roundtrip(const char *input, const char *listed,
                        const uint8_t *raw, size_t raw_len,
                        const uint8_t *canonical, size_t canonical_len)
{
    uint8_t body[96], saved[96], text[96], again[96], stable[96];
    uint8_t failed[96], before_failure[96];
    size_t body_len = 123u, text_len = 234u, again_len = 345u;
    size_t stable_len = 456u;
    size_t failure_len = 789u;
    CHECK(strlen(listed) <= sizeof(text));
    memset(body, 0x42, sizeof(body));
    CHECK(bt_tokenize((const uint8_t *)input, strlen(input),
                      body, sizeof(body), &body_len) == BT_OK);
    CHECK(body_len == raw_len && memcmp(body, raw, raw_len) == 0);
    memcpy(saved, body, sizeof(body));
    CHECK(bl_detokenize(body, body_len, text, sizeof(text), &text_len) == BL_OK);
    CHECK(text_len == strlen(listed) && memcmp(text, listed, text_len) == 0);
    CHECK(memcmp(body, saved, sizeof(body)) == 0);
    CHECK(bt_tokenize(text, text_len, again, sizeof(again), &again_len) == BT_OK);
    CHECK(again_len == canonical_len &&
          memcmp(again, canonical, canonical_len) == 0);
    CHECK(bl_detokenize(again, again_len, stable,
                        sizeof(stable), &stable_len) == BL_OK);
    CHECK(stable_len == text_len && memcmp(stable, text, text_len) == 0);
    memset(failed, 0x5a, sizeof(failed));
    memcpy(before_failure, failed, sizeof(failed));
    CHECK(bl_detokenize(body, body_len, failed,
                        text_len - 1u, &failure_len) == BL_NO_SPACE);
    CHECK(failure_len == 789u &&
          memcmp(failed, before_failure, sizeof(failed)) == 0);
    CHECK(memcmp(body, saved, sizeof(body)) == 0);
    return 0;
}

static int test_c1_alias_roundtrips(void)
{
    static const uint8_t unspaced_int[] = {0xbfu,0x02u,0,0,0xc1u};
    static const uint8_t spaced_int[] = {0xbfu,' ',0x02u,0,0,0xc1u};
    static const uint8_t unspaced_real[] = {0xbfu,0x04u,0,0,0xc2u};
    static const uint8_t spaced_real[] = {0xbfu,' ',0x04u,0,0,0xc2u};
    static const uint8_t unspaced_string[] = {0xbfu,0x03u,0,0,0xd3u};
    static const uint8_t spaced_string[] = {0xbfu,' ',0x03u,0,0,0xd3u};
    static const uint8_t two_spaces[] = {0xbfu,' ',' ',0x02u,0,0,0xc1u};
    static const uint8_t unspaced_colon[] = {0xbfu,0x02u,0,0,0xc1u,0x01u,0x98u};
    static const uint8_t spaced_colon[] = {0xbfu,' ',0x02u,0,0,0xc1u,0x01u,0x98u};
    static const uint8_t short_number[] = {0xbfu,0x13u};
    static const uint8_t spaced_short[] = {0xbfu,' ',0x13u};
    static const uint8_t long_number[] = {0xbfu,0x19u,0x2au};
    static const uint8_t spaced_long[] = {0xbfu,' ',0x19u,0x2au};
    static const uint8_t short_colon[] = {0xbfu,0x13u,0x01u,0x98u};
    static const uint8_t spaced_short_colon[] = {0xbfu,' ',0x13u,0x01u,0x98u};
    static const uint8_t quote[] = {0xbfu,'"','A','%','"'};
    static const uint8_t quote_space[] = {0xbfu,' ','"','A','%','"'};
    static const uint8_t invalid_import[] = {0xbfu,0x02u,0,0,'1'|0x80};
    uint8_t dest[96], before[96];
    size_t n = 4321u;

    CHECK(c1_roundtrip("?A%", "PRINT A%",
          unspaced_int, sizeof(unspaced_int),
          spaced_int, sizeof(spaced_int)) == 0);
    CHECK(c1_roundtrip("?B!", "PRINT B!",
          unspaced_real, sizeof(unspaced_real),
          spaced_real, sizeof(spaced_real)) == 0);
    CHECK(c1_roundtrip("?S$", "PRINT S$",
          unspaced_string, sizeof(unspaced_string),
          spaced_string, sizeof(spaced_string)) == 0);
    CHECK(c1_roundtrip("PRINT A%", "PRINT A%",
          spaced_int, sizeof(spaced_int),
          spaced_int, sizeof(spaced_int)) == 0);
    CHECK(c1_roundtrip("? A%", "PRINT A%",
          spaced_int, sizeof(spaced_int),
          spaced_int, sizeof(spaced_int)) == 0);
    CHECK(c1_roundtrip("PRINT  A%", "PRINT  A%",
          two_spaces, sizeof(two_spaces),
          two_spaces, sizeof(two_spaces)) == 0);
    CHECK(c1_roundtrip("?A%:END", "PRINT A%:END",
          unspaced_colon, sizeof(unspaced_colon),
          spaced_colon, sizeof(spaced_colon)) == 0);
    CHECK(c1_roundtrip("PRINT A%:END", "PRINT A%:END",
          spaced_colon, sizeof(spaced_colon),
          spaced_colon, sizeof(spaced_colon)) == 0);
    CHECK(c1_roundtrip("?5", "PRINT 5",
          short_number, sizeof(short_number),
          spaced_short, sizeof(spaced_short)) == 0);
    CHECK(c1_roundtrip("?42", "PRINT 42",
          long_number, sizeof(long_number),
          spaced_long, sizeof(spaced_long)) == 0);
    CHECK(c1_roundtrip("?5:END", "PRINT 5:END",
          short_colon, sizeof(short_colon),
          spaced_short_colon, sizeof(spaced_short_colon)) == 0);
    CHECK(c1_roundtrip("?\"A%\"", "PRINT\"A%\"",
          quote, sizeof(quote), quote, sizeof(quote)) == 0);
    CHECK(c1_roundtrip("? \"A%\"", "PRINT \"A%\"",
          quote_space, sizeof(quote_space),
          quote_space, sizeof(quote_space)) == 0);

    /* PRINTA% must never become a recognized keyword (or prefix). */
    memset(dest, 0x39, sizeof(dest));
    memcpy(before, dest, sizeof(dest));
    CHECK(bt_tokenize((const uint8_t *)"PRINTA%", 7u, dest,
                      sizeof(dest), &n) == BT_UNSUPPORTED_CONSTRUCT);
    CHECK(n == 4321u && memcmp(dest, before, sizeof(dest)) == 0);
    /* Import-time malformed references still fail atomically. */
    CHECK(bl_detokenize(invalid_import, sizeof(invalid_import),
                        dest, sizeof(dest), &n) == BL_BAD_SEQUENCE);
    CHECK(n == 4321u && memcmp(dest, before, sizeof(dest)) == 0);
    return 0;
}

static int test_c1_program_list_and_imported_cache(void)
{
    BasicProgram program;
    uint8_t store[2048], body[96], out[1024], snapshot[1024];
    uint8_t exported[2048], exported_again[2048];
    static const struct {
        uint16_t line;
        const char *text;
    } cases[] = {
        {10u,"?A%"}, {20u,"?B!"}, {30u,"?S$"},
        {40u,"PRINT A%"}, {50u,"?A%:END"},
        {60u,"?5"}, {70u,"?42"}, {80u,"?\"Q\""}
    };
    static const uint8_t imported[] = {0xbfu,0x03u,0x56u,0x34u,0xd3u};
    static const char *expected =
        "10 PRINT A%\n20 PRINT B!\n30 PRINT S$\n40 PRINT A%\n"
        "50 PRINT A%:END\n60 PRINT 5\n70 PRINT 42\n"
        "80 PRINT\"Q\"\n90 PRINT S$\n";
    static const uint8_t malformed[] = {0xbfu,0x02u,0u,0u,'A'};
    size_t n, before_n, after_n, i;
    BasicProgramLine line;
    BasicVariableRef ref;
    size_t bad_written = 555u;

    CHECK(bp_init(&program, store, sizeof(store)) == BP_OK);
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        CHECK(bt_tokenize((const uint8_t *)cases[i].text,
                          strlen(cases[i].text), body, sizeof(body), &n) == BT_OK);
        CHECK(bp_put(&program, cases[i].line, body, n) == BP_OK);
    }
    CHECK(bp_put(&program, 90u, imported, sizeof(imported)) == BP_OK);
    CHECK(bp_export(&program, exported, sizeof(exported), &before_n) == BP_OK);
    CHECK(bl_list_program(&program, out, sizeof(out), &n) == BL_OK);
    CHECK(n == strlen(expected) && memcmp(out, expected, n) == 0);
    CHECK(bp_export(&program, exported_again, sizeof(exported_again),
                    &after_n) == BP_OK);
    CHECK(before_n == after_n && memcmp(exported, exported_again, before_n) == 0);
    CHECK(bp_find(&program, 90u, &line) == BP_OK);
    CHECK(memcmp(program.data + line.body_offset, imported, sizeof(imported)) == 0);
    CHECK(bvr_decode(program.data + line.body_offset, line.body_length,
                     1u, &ref) == BVR_OK);
    CHECK(ref.cache_low == 0x56u && ref.cache_high == 0x34u);

    /* A later malformed line invalidates the entire LIST atomically. */
    CHECK(bp_put(&program, 100u, malformed, sizeof(malformed)) == BP_OK);
    memset(out, 0x74, sizeof(out));
    memcpy(snapshot, out, sizeof(out));
    CHECK(bl_list_program(&program, out, sizeof(out),
                          &bad_written) == BL_TRUNCATED);
    CHECK(bad_written == 555u && memcmp(out, snapshot, sizeof(out)) == 0);
    CHECK(bp_delete(&program, 100u) == BP_OK);
    CHECK(bp_export(&program, exported_again, sizeof(exported_again),
                    &after_n) == BP_OK);
    CHECK(before_n == after_n && memcmp(exported, exported_again, before_n) == 0);
    return 0;
}

int main(void)
{
    CHECK(test_c1_alias_roundtrips() == 0);
    CHECK(test_c1_program_list_and_imported_cache() == 0);
    CHECK(test_encoder() == 0);
    CHECK(test_encoder_errors() == 0);
    CHECK(test_tokenizer_and_listing() == 0);
    CHECK(test_bad_listing_and_capacity() == 0);
    CHECK(test_program_cache_and_run() == 0);
    CHECK(test_session_integration() == 0);
    puts("J0.16 explicit variable tokenization: OK (synthetic ROM-derived vectors)");
    return 0;
}
