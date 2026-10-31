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
    /* BE_MISSING_TARGET alone cannot prove GOSUB (GOTO and IF use it). */
    CHECK_CASE(goto_missing, 0U, BE_MISSING_TARGET, "ERROR\n", 0);
    CHECK_CASE(if_missing, 1U, BE_MISSING_TARGET, "ERROR\n", 0);
    CHECK_CASE(pen, 0U, BE_INVALID_PEN,
               "Improper argument in 10\n", 1);
#undef CHECK_CASE
}
int main(void)
{
    tests();
    puts("J1-DIAG-RETRO-A1a: GOSUB/RETURN CPC, renumber, negative origins, atomicity, Ready OK");
    return 0;
}
