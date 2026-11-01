/* J1-DIAG-RETRO-A1a: ROM-witnessed diagnostics, native failure context.
 * Historical wording and Ready: sealed J1-DIAG-RETRO-A0 PNGs (PR #224).
 * No hardware simulation, no ERR/ERL register inference. */
#include "basic_session_runtime.h"
#include "cpc_diag_policy.h"
#include "cpc_ready_policy.h"
#include "cpc_video.h"
#include "cpc_text.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum { PROGRAM_CAP = 4096, OUTPUT_CAP = 256, EVENT_CAP = 3 };
typedef struct {
    BasicProgram program;
    BasicVariableStore store;
    BasicSessionRuntime runtime;
    BasicVariableEntry entries[32];
    uint8_t storage[PROGRAM_CAP], temporary[512], output[OUTPUT_CAP];
    size_t written, event_written;
    BEVideoEvent events[EVENT_CAP];
    CpcVideo video;
    CpcText text;
    uint8_t vram[CPC_VIDEO_BYTES];
} Fixture;
static Fixture f;
static char painted[128];
static size_t painted_length;

static uint8_t glyph(void *context, uint8_t ch, unsigned row)
{
    (void)context;
    if (row == 0U) {
        assert(painted_length < sizeof(painted));
        painted[painted_length++] = (char)ch;
    }
    return ch == (uint8_t)' ' ? 0U : 0x80U;
}
static void setup(void)
{
    memset(&f, 0, sizeof f);
    painted_length = 0U;
    assert(bp_init(&f.program, f.storage, sizeof f.storage) == BP_OK);
    assert(bvs_init(&f.store, f.entries, 32U) == BVS_OK);
    assert(bsr_init_with_store(&f.runtime, &f.program, &f.store).status == BSR_OK);
    assert(cpc_video_init(&f.video, f.vram, sizeof f.vram, CPC_MODE_1));
    assert(cpc_text_init(&f.text, &f.video, glyph, NULL));
}
static void submit(const char *s)
{
    BSRResult r = bsr_submit(&f.runtime, (const uint8_t *)s, strlen(s),
                            f.temporary, sizeof f.temporary, f.output,
                            sizeof f.output, &f.written);
    assert(r.status == BSR_OK);
}
static BSRResult step(void)
{
    return bsr_step_events(&f.runtime, f.output, sizeof f.output, &f.written,
                           f.events, EVENT_CAP, &f.event_written);
}
static void expect_diagnostic(const char *const *sources, size_t count,
                              unsigned successes, BEStatus failure,
                              const char *expected, int historical)
{
    uint8_t saved_program[PROGRAM_CAP], saved_output[OUTPUT_CAP];
    BEVideoEvent saved_events[EVENT_CAP];
    BasicSessionRuntime before;
    BasicProgram before_program;
    BasicVariableStore before_store;
    BasicVariableEntry before_entries[32];
    CpcStepDiagnostic diag;
    BSRResult r;
    uint8_t formatted[80];
    size_t length = 123U;
    size_t bytes_before;
    bool ready = false;
    setup();
    for (size_t i = 0U; i < count; ++i) submit(sources[i]);
    submit("RUN");
    for (unsigned i = 0U; i < successes; ++i) {
        f.written = 0U;
        f.event_written = 0U;
        r = step();
        assert(r.status == BSR_OK && r.executor_status == BE_OK);
        if (f.written != 0U)
            assert(cpc_text_write(&f.text, f.output, f.written));
    }
    memcpy(saved_program, f.storage, sizeof saved_program);
    before_program = f.program;
    before_store = f.store;
    memcpy(before_entries, f.entries, sizeof before_entries);
    memset(f.output, 0x57, sizeof f.output);
    memset(f.events, 0x63, sizeof f.events);
    memcpy(saved_output, f.output, sizeof saved_output);
    memcpy(saved_events, f.events, sizeof saved_events);
    f.written = 71U;
    f.event_written = 73U;
    before = f.runtime;
    bytes_before = f.text.bytes_received;
    r = step();
    assert(r.status == BSR_EXECUTOR_ERROR && r.executor_status == failure);
    /* The failed step may not output PRINT (even an earlier statement),
     * mutate the executor/variable store/program or advance the cursor. */
    assert(memcmp(&before, &f.runtime, sizeof before) == 0);
    assert(memcmp(saved_output, f.output, sizeof saved_output) == 0);
    assert(memcmp(saved_events, f.events, sizeof saved_events) == 0);
    assert(memcmp(saved_program, f.storage, sizeof saved_program) == 0);
    assert(memcmp(&before_program, &f.program, sizeof before_program) == 0);
    assert(memcmp(&before_store, &f.store, sizeof before_store) == 0);
    assert(memcmp(before_entries, f.entries, sizeof before_entries) == 0);
    assert(f.written == 71U && f.event_written == 73U);
    assert(f.text.bytes_received == bytes_before);
    diag = cpc_diag_policy_step(r, &f.runtime); /* MUST precede stop */
    assert((diag.category != CPC_DIAG_HOST_GENERIC) == (historical != 0));
    assert(cpc_diag_policy_format_step(diag, formatted, sizeof formatted, &length));
    assert(length == strlen(expected));
    assert(memcmp(formatted, expected, length) == 0);
    /* Formatter is fail-closed/atomic for short buffers. */
    if (length != 0U) {
        uint8_t tiny[80];
        size_t unchanged = 456U;
        memset(tiny, 0xab, sizeof tiny);
        assert(!cpc_diag_policy_format_step(diag, tiny, length - 1U,
                                            &unchanged));
        assert(unchanged == 456U);
        for (size_t j = 0U; j < sizeof tiny; ++j) assert(tiny[j] == 0xab);
    }
    assert(bsr_stop(&f.runtime).status == BSR_OK);
    assert(f.runtime.state == BSR_IDLE);
    assert(cpc_diag_policy_write_step(&f.text, diag));
    assert(cpc_ready_policy_apply(&f.text, CPC_READY_RUN_RETURN, &ready));
    assert(ready);
    assert(f.text.bytes_received == bytes_before + length + sizeof("Ready\n") - 1U);
    assert(memcmp(saved_program, f.storage, sizeof saved_program) == 0);
    assert(memcmp(&before_program, &f.program, sizeof before_program) == 0);
    assert(memcmp(&before_store, &f.store, sizeof before_store) == 0);
    assert(memcmp(before_entries, f.entries, sizeof before_entries) == 0);
    /* Exactly one Ready, after one diagnostic. No post-error PRINT. */
    assert(painted_length < sizeof painted);
    painted[painted_length] = '\0';
    assert(strstr(painted, "Ready") != NULL);
    assert(strstr(strstr(painted, "Ready") + 5, "Ready") == NULL);
    assert(strstr(painted, "NEVER") == NULL);
}
static void tests(void)
{
    static const char *gosub10[] = {
        "10 GOSUB 999", "20 PRINT \"NEVER\""
    };
    static const char *gosub370[] = {
        "370 GOSUB 999", "400 PRINT \"NEVER\""
    };
    static const char *gosub65535[] = {
        "65535 GOSUB 999"
    };
    static const char *return10[] = {
        "10 RETURN", "20 PRINT \"NEVER\""
    };
    static const char *return620[] = {
        "600 RETURN", "620 PRINT \"NEVER\""
    };
    static const char *after_call[] = {
        "10 GOSUB 30", "20 RETURN", "30 RETURN", "40 PRINT \"NEVER\""
    };
    static const char *after_call_renum[] = {
        "510 GOSUB 530", "520 RETURN", "530 RETURN", "540 PRINT \"NEVER\""
    };
    static const char *colon_gosub[] = {
        "10 PRINT \"BEFORE\":GOSUB 999:PRINT \"NEVER\""
    };
    static const char *resume_colon[] = {
        "10 GOSUB 30:PRINT \"BEFORE\":GOSUB 999",
        "20 END", "30 RETURN", "40 PRINT \"NEVER\""
    };
    static const char *goto_missing[] = {
        "10 PRINT \"GOSUB RETURN\":GOTO 999", "20 PRINT \"NEVER\""
    };
    static const char *if_missing[] = {
        "10 A%=1", "20 IF A% THEN 999", "30 PRINT \"NEVER\""
    };
    static const char *pen[] = {
        "10 PEN 16", "20 PRINT \"NEVER\""
    };
#define CHECK_CASE(lines,steps,status,text,oracle) \
    expect_diagnostic(lines, sizeof(lines)/sizeof(lines[0]), \
                      steps, status, text, oracle)
    /* Three immutable A0 screen witnesses and new renumbered derivatives. */
    CHECK_CASE(gosub10, 0U, BE_MISSING_TARGET,
               "Line does not exist in 10\n", 1);
    CHECK_CASE(gosub370, 0U, BE_MISSING_TARGET,
               "Line does not exist in 370\n", 1);
    CHECK_CASE(gosub65535, 0U, BE_MISSING_TARGET,
               "Line does not exist in 65535\n", 1);
    CHECK_CASE(return10, 0U, BE_RETURN_WITHOUT_GOSUB,
               "Unexpected RETURN in 10\n", 1);
    CHECK_CASE(return620, 0U, BE_RETURN_WITHOUT_GOSUB,
               "Unexpected RETURN in 600\n", 1);
    CHECK_CASE(after_call, 2U, BE_RETURN_WITHOUT_GOSUB,
               "Unexpected RETURN in 20\n", 1);
    CHECK_CASE(after_call_renum, 2U, BE_RETURN_WITHOUT_GOSUB,
               "Unexpected RETURN in 520\n", 1);
    CHECK_CASE(colon_gosub, 0U, BE_MISSING_TARGET,
               "Line does not exist in 10\n", 1);
    CHECK_CASE(resume_colon, 2U, BE_MISSING_TARGET,
               "Line does not exist in 10\n", 1);
    /* O2-B: CPC ROM-backed target errors at actual numbered loci. */
    {
        static const char *goto10[] = {
            "10 GOTO 999", "20 PRINT \"NEVER\""
        };
        static const char *goto370[] = {
            "370 GOTO 999", "400 PRINT \"NEVER\""
        };
        static const char *if520[] = {
            "510 A%=1", "520 IF A% THEN 999", "530 PRINT \"NEVER\""
        };
        CHECK_CASE(goto10, 0U, BE_MISSING_TARGET,
                   "Line does not exist in 10\n", 1);
        CHECK_CASE(goto370, 0U, BE_MISSING_TARGET,
                   "Line does not exist in 370\n", 1);
        CHECK_CASE(if520, 1U, BE_MISSING_TARGET,
                   "Line does not exist in 520\n", 1);
    }
    CHECK_CASE(goto_missing, 0U, BE_MISSING_TARGET,
               "Line does not exist in 10\n", 1);
    CHECK_CASE(if_missing, 1U, BE_MISSING_TARGET,
               "Line does not exist in 20\n", 1);
    CHECK_CASE(pen, 0U, BE_INVALID_PEN,
               "Improper argument in 10\n", 1);
    /* A1b RED: original/repeat J1.12-A ROM-backed PNG text.
     * The wrong NEXT belongs to line 30 although FOR preflight is line 10. */
    {
        static const char *orphan[] = {
            "10 PRINT \"BEFORE\"", "20 NEXT I%", "30 PRINT \"NEVER\""
        };
        static const char *wrong[] = {
            "10 FOR I%=1 TO 2", "20 PRINT \"NEVER\"",
            "30 NEXT J%", "40 END"
        };
        CHECK_CASE(orphan, 1U, BE_NEXT_WITHOUT_FOR,
                   "Unexpected NEXT in 20\n", 1);
        CHECK_CASE(wrong, 0U, BE_NEXT_VARIABLE_MISMATCH,
                   "Unexpected NEXT in 30\n", 1);
    }
    {
        static const char *orphan_renumber[] = {
            "500 PRINT \"BEFORE\"", "620 NEXT I%", "700 PRINT \"NEVER\""
        };
        static const char *orphan_colon[] = {
            "550 PRINT \"BEFORE\":NEXT I%:PRINT \"NEVER\""
        };
        static const char *wrong_renumber[] = {
            "410 FOR I%=1 TO 2", "510 PRINT \"NEVER\"",
            "790 NEXT J%", "900 END"
        };
        static const char *wrong_colon[] = {
            "10 FOR I%=1 TO 2:PRINT \"NEVER\"",
            "20 NEXT J%:PRINT \"NEVER\"", "30 END"
        };
        static const char *wrong_quote_rem[] = {
            "10 FOR I%=1 TO 2",
            "20 PRINT \"NEXT J%: FOR K%\"",
            "25 REM NEXT I%", "30 NEXT J%", "40 END"
        };
        static const char *without_next[] = {
            "10 FOR I%=1 TO 2", "20 PRINT \"NEVER\""
        };
        static const char *overflow_next[] = {
            "10 FOR I%=32767 TO 32767", "20 NEXT I%", "30 END"
        };
        CHECK_CASE(orphan_renumber, 1U, BE_NEXT_WITHOUT_FOR,
                   "Unexpected NEXT in 620\n", 1);
        CHECK_CASE(orphan_colon, 0U, BE_NEXT_WITHOUT_FOR,
                   "Unexpected NEXT in 550\n", 1);
        CHECK_CASE(wrong_renumber, 0U, BE_NEXT_VARIABLE_MISMATCH,
                   "Unexpected NEXT in 790\n", 1);
        CHECK_CASE(wrong_colon, 0U, BE_NEXT_VARIABLE_MISMATCH,
                   "Unexpected NEXT in 20\n", 1);
        CHECK_CASE(wrong_quote_rem, 0U, BE_NEXT_VARIABLE_MISMATCH,
                   "Unexpected NEXT in 30\n", 1);
        CHECK_CASE(without_next, 0U, BE_FOR_WITHOUT_NEXT, "ERROR\n", 0);
        CHECK_CASE(overflow_next, 1U, BE_INTEGER_OVERFLOW, "ERROR\n", 0);
    }
#undef CHECK_CASE
}
/* Only the CPC-attested NEXT causes can be promoted.
 * A claimed status is insufficient without a read-only matching replay. */
static void test_next_provenance(void)
{
    BSRResult result, fabricated;
    BasicProgramLine line;
    CpcStepDiagnostic diagnosis;
    BasicSessionRuntime saved_runtime;
    BasicVariableStore saved_store;
    BasicVariableEntry saved_entries[32];
    uint8_t saved_program[PROGRAM_CAP], saved_output[OUTPUT_CAP];
    BEVideoEvent saved_events[EVENT_CAP];
    uint16_t locus = 999U;
    uint8_t bytes[80];
    size_t written = 123U;
    setup();
    submit("10 FOR I%=1 TO 2");
    submit("20 PRINT \"NEVER\"");
    submit("30 NEXT J%");
    submit("40 END");
    submit("RUN");
    result = step();
    assert(result.status == BSR_EXECUTOR_ERROR &&
           result.executor_status == BE_NEXT_VARIABLE_MISMATCH);
    saved_runtime = f.runtime;
    saved_store = f.store;
    memcpy(saved_entries, f.entries, sizeof saved_entries);
    memcpy(saved_program, f.storage, sizeof saved_program);
    memcpy(saved_output, f.output, sizeof saved_output);
    memcpy(saved_events, f.events, sizeof saved_events);
    assert(cpc_diag_policy_next_locus(&f.runtime.executor,
                              result.executor_status, &locus));
    assert(locus == 30U);
    assert(memcmp(&saved_runtime, &f.runtime, sizeof saved_runtime) == 0);
    assert(memcmp(&saved_store, &f.store, sizeof saved_store) == 0);
    assert(memcmp(saved_entries, f.entries, sizeof saved_entries) == 0);
    assert(memcmp(saved_program, f.storage, sizeof saved_program) == 0);
    assert(memcmp(saved_output, f.output, sizeof saved_output) == 0);
    assert(memcmp(saved_events, f.events, sizeof saved_events) == 0);
    locus = 991U;
    assert(!cpc_diag_policy_next_locus(&f.runtime.executor, BE_MISSING_TARGET, &locus));
    assert(locus == 991U);
    fabricated = result;
    fabricated.executor_status = BE_NEXT_WITHOUT_FOR;
    diagnosis = cpc_diag_policy_step(fabricated, &f.runtime);
    assert(diagnosis.category == CPC_DIAG_HOST_GENERIC);
    fabricated.executor_status = BE_NO_EVENT_SPACE;
    diagnosis = cpc_diag_policy_step(fabricated, &f.runtime);
    assert(diagnosis.category == CPC_DIAG_HOST_GENERIC);
    fabricated.executor_status = BE_MISSING_TARGET;
    diagnosis = cpc_diag_policy_step(fabricated, &f.runtime);
    assert(diagnosis.category == CPC_DIAG_HOST_GENERIC);
    fabricated = result;
    fabricated.status = BSR_SESSION_ERROR;
    diagnosis = cpc_diag_policy_step(fabricated, &f.runtime);
    assert(diagnosis.category == CPC_DIAG_HOST_GENERIC);
    assert(bp_find(&f.program, 30U, &line) == BP_OK);
    assert(f.storage[line.body_offset] == 0xb0u);
    f.storage[line.body_offset] = 0x98u; /* forged NEXT replaced by END */
    diagnosis = cpc_diag_policy_step(result, &f.runtime);
    assert(diagnosis.category == CPC_DIAG_HOST_GENERIC);
    f.storage[line.body_offset] = 0xb0u;
    diagnosis = cpc_diag_policy_step(result, &f.runtime);
    assert(diagnosis.category == CPC_DIAG_NEXT_UNEXPECTED &&
           diagnosis.origin == CPC_DIAG_ORIGIN_NATIVE_NEXT_CPC_ORACLE &&
           diagnosis.line_number == 30U);
    diagnosis.origin = CPC_DIAG_ORIGIN_NATIVE_GOSUB_CPC_ORACLE;
    memset(bytes, 0x59, sizeof bytes);
    assert(!cpc_diag_policy_format_step(diagnosis, bytes, sizeof bytes, &written));
    assert(written == 123U);
    for(size_t i=0U;i<sizeof bytes;++i) assert(bytes[i]==0x59u);
    f.runtime.executor.cursor = f.program.size; /* forged invalid cursor */
    diagnosis = cpc_diag_policy_step(result, &f.runtime);
    assert(diagnosis.category == CPC_DIAG_HOST_GENERIC);
    f.runtime = saved_runtime;
    assert(memcmp(f.storage, saved_program, sizeof saved_program) == 0);
}

static void test_next_success(void)
{
    BSRResult result;
    CpcStepDiagnostic diagnosis;
    setup();
    submit("10 FOR I%=1 TO 2");
    submit("20 PRINT \"NEXT J% is just a string\"");
    submit("25 REM NEXT K%");
    submit("30 NEXT I%");
    submit("40 END");
    submit("RUN");
    for(unsigned i=0U;i<10U;++i) {
        result = step();
        if(result.status == BSR_END) break;
        assert(result.status == BSR_OK && result.executor_status == BE_OK);
    }
    assert(result.status == BSR_END);
    result.executor_status = BE_NEXT_VARIABLE_MISMATCH;
    result.status = BSR_EXECUTOR_ERROR;
    diagnosis = cpc_diag_policy_step(result, &f.runtime);
    assert(diagnosis.category == CPC_DIAG_HOST_GENERIC);
}


/* O2-B fail-closed: a synthetic host status alone is never CPC evidence. */
static void test_o2b_false_and_forged(void)
{
    BSRResult r, spoof;
    CpcStepDiagnostic diag;
    BasicProgramLine line;
    size_t cursor;
    uint8_t bytes[64];
    size_t written = 55U;
    setup();
    submit("10 A%=0");
    submit("20 IF A% THEN 999");
    submit("30 PRINT \"AFTER\"");
    submit("RUN");
    assert(step().status == BSR_OK);
    r = step();
    assert(r.status == BSR_OK && f.written == 0U);
    /* IF false has no missing-target failure, even with an absent THEN line. */
    spoof = r;
    spoof.status = BSR_EXECUTOR_ERROR;
    spoof.executor_status = BE_MISSING_TARGET;
    assert(bp_find(&f.program, 20U, &line) == BP_OK);
    f.runtime.executor.cursor = line.offset;
    f.runtime.executor.statement_offset = 0U;
    diag = cpc_diag_policy_step(spoof, &f.runtime);
    assert(diag.category == CPC_DIAG_HOST_GENERIC);
    f.runtime.executor.cursor = line.next_offset;
    r = step();
    assert(r.status == BSR_OK && f.written == sizeof("AFTER\n") - 1U);
    assert(memcmp(f.output, "AFTER\n", f.written) == 0);
    assert(step().status == BSR_END);

    setup();
    submit("10 PRINT \"GOTO 999\"");
    submit("20 GOTO 30");
    submit("30 END");
    submit("RUN");
    r = step();
    assert(r.status == BSR_OK);
    spoof = r;
    spoof.status = BSR_EXECUTOR_ERROR;
    spoof.executor_status = BE_MISSING_TARGET;
    diag = cpc_diag_policy_step(spoof, &f.runtime);
    assert(diag.category == CPC_DIAG_HOST_GENERIC); /* existing target */
    f.runtime.executor.cursor = 0U;
    diag = cpc_diag_policy_step(spoof, &f.runtime);
    assert(diag.category == CPC_DIAG_HOST_GENERIC); /* PRINT not flow */
    cursor = 0U;
    assert(bp_next(&f.program, &cursor, &line) == BP_OK);
    /* A token-like byte within a quoted string is not a statement. */
    f.storage[line.body_offset + 8U] = 0xa0U;
    f.runtime.executor.statement_offset = 8U;
    diag = cpc_diag_policy_step(spoof, &f.runtime);
    assert(diag.category == CPC_DIAG_HOST_GENERIC);
    f.runtime.executor.statement_offset = line.body_length;
    diag = cpc_diag_policy_step(spoof, &f.runtime);
    assert(diag.category == CPC_DIAG_HOST_GENERIC);
    f.runtime.executor.statement_offset = 0U;
    f.runtime.executor.cursor = f.program.size;
    diag = cpc_diag_policy_step(spoof, &f.runtime);
    assert(diag.category == CPC_DIAG_HOST_GENERIC);
    f.runtime.executor.cursor = 0U;
    f.runtime.state = BSR_IDLE;
    diag = cpc_diag_policy_step(spoof, &f.runtime);
    assert(diag.category == CPC_DIAG_HOST_GENERIC);
    f.runtime.state = BSR_RUNNING;
    spoof.status = BSR_SESSION_ERROR;
    diag = cpc_diag_policy_step(spoof, &f.runtime);
    assert(diag.category == CPC_DIAG_HOST_GENERIC);

    /* Unknown category/origin pairing never partially writes diagnostics. */
    diag.category = CPC_DIAG_GOSUB_MISSING_TARGET;
    diag.origin = CPC_DIAG_ORIGIN_NATIVE_RETURN_CPC_ORACLE;
    diag.line_number = 370U;
    memset(bytes, 0xa9, sizeof bytes);
    assert(!cpc_diag_policy_format_step(diag, bytes, sizeof bytes, &written));
    assert(written == 55U);
    for(size_t i=0U;i<sizeof bytes;++i) assert(bytes[i] == 0xa9U);
}


/* The failed RUN must not damage stored BASIC; LIST remains byte-exact. */
static void test_o2b_list_preserved(void)
{
    static const char expected[] =
        "370 GOTO 999\n400 PRINT \"NEVER\"\n";
    BasicProgram before_program;
    uint8_t before_bytes[PROGRAM_CAP];
    BSRResult result;
    CpcStepDiagnostic diag;
    setup();
    submit("370 GOTO 999");
    submit("400 PRINT \"NEVER\"");
    submit("RUN");
    before_program = f.program;
    memcpy(before_bytes, f.storage, sizeof before_bytes);
    result = step();
    assert(result.status == BSR_EXECUTOR_ERROR &&
           result.executor_status == BE_MISSING_TARGET);
    diag = cpc_diag_policy_step(result, &f.runtime);
    assert(diag.category == CPC_DIAG_GOTO_MISSING_TARGET &&
           diag.origin == CPC_DIAG_ORIGIN_NATIVE_GOTO_CPC_ORACLE &&
           diag.line_number == 370U);
    assert(bsr_stop(&f.runtime).status == BSR_OK);
    assert(memcmp(&before_program, &f.program, sizeof f.program) == 0);
    assert(memcmp(before_bytes, f.storage, sizeof before_bytes) == 0);
    submit("LIST");
    assert(f.written == sizeof(expected) - 1U);
    assert(memcmp(f.output, expected, f.written) == 0);
}

/* A missing-target status with REM, an unknown source, or another phase is
 * host only. Direct (non-numbered) GOTO isn't a witnessed O2-B RUN locus. */
static void test_o2b_other_origins(void)
{
    BSRResult r;
    CpcStepDiagnostic diag;
    setup();
    submit("10 REM GOTO 999");
    submit("20 PRINT \"AFTER\"");
    submit("RUN");
    r = step();
    assert(r.status == BSR_OK);
    r.status = BSR_EXECUTOR_ERROR;
    r.executor_status = BE_MISSING_TARGET;
    f.runtime.executor.cursor = 0U;
    diag = cpc_diag_policy_step(r, &f.runtime);
    assert(diag.category == CPC_DIAG_HOST_GENERIC);
    f.runtime.executor.program = NULL;
    diag = cpc_diag_policy_step(r, &f.runtime);
    assert(diag.category == CPC_DIAG_HOST_GENERIC);
    /* No CPC sentence is inferred from a direct input/source selection. */
    diag.category = cpc_diag_policy_select(
        (const uint8_t *)"GOTO 999", sizeof("GOTO 999") - 1U, r);
    assert(diag.category == CPC_DIAG_HOST_GENERIC);
}

int main(void)
{
    test_o2b_list_preserved();
    test_o2b_other_origins();
    test_o2b_false_and_forged();
    tests();
    test_next_provenance();
    test_next_success();
    puts("J1-DIAG-RETRO-A1a: GOSUB/RETURN CPC, renumber, negative origins, atomicity, Ready OK");
    return 0;
}
