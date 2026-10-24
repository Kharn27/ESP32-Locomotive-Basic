#include "basic_session_runtime.h"

#include <stdio.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); \
    return 1; } } while (0)

typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    uint8_t storage[1024];
    uint8_t temporary[256];
    uint8_t output[1024];
    size_t written;
} Fixture;

typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    uint8_t storage[1024];
    uint8_t output[1024];
    size_t written;
} Snapshot;

static int setup(Fixture *f)
{
    memset(f, 0xa5, sizeof(*f));
    CHECK(bp_init(&f->program, f->storage, sizeof(f->storage)) == BP_OK);
    CHECK(bsr_init(&f->runtime, &f->program).status == BSR_OK);
    CHECK(f->runtime.state == BSR_IDLE);
    return 0;
}

static BSRResult submit_bytes(Fixture *f, const uint8_t *source, size_t len,
                               size_t temporary_capacity, size_t out_capacity)
{
    return bsr_submit(&f->runtime, source, len,
                      f->temporary, temporary_capacity,
                      f->output, out_capacity, &f->written);
}

static BSRResult submit(Fixture *f, const char *source)
{
    return submit_bytes(f, (const uint8_t *)source, strlen(source),
                        sizeof(f->temporary), sizeof(f->output));
}

static BSRResult advance(Fixture *f, size_t output_capacity)
{
    return bsr_step(&f->runtime, f->output, output_capacity, &f->written);
}

static void save(const Fixture *f, Snapshot *s)
{
    memcpy(&s->program, &f->program, sizeof(s->program));
    memcpy(&s->runtime, &f->runtime, sizeof(s->runtime));
    memcpy(s->storage, f->storage, sizeof(s->storage));
    memcpy(s->output, f->output, sizeof(s->output));
    s->written = f->written;
}

static int same(const Fixture *f, const Snapshot *s)
{
    CHECK(memcmp(&f->program, &s->program, sizeof(s->program)) == 0);
    CHECK(memcmp(&f->runtime, &s->runtime, sizeof(s->runtime)) == 0);
    CHECK(memcmp(f->storage, s->storage, sizeof(s->storage)) == 0);
    CHECK(memcmp(f->output, s->output, sizeof(s->output)) == 0);
    CHECK(f->written == s->written);
    return 0;
}

static int step_output(Fixture *f, const char *expected)
{
    size_t n = strlen(expected);
    memset(f->output, 0x73, sizeof(f->output));
    f->written = 99u;
    CHECK(advance(f, sizeof(f->output)).status == BSR_OK);
    CHECK(f->written == n);
    CHECK(memcmp(f->output, expected, n) == 0);
    CHECK(f->output[n] == 0x73u);
    return 0;
}

static int test_end_to_end(void)
{
    Fixture f;
    Snapshot before;
    const char *expected_listing =
        "10 PRINT \"HELLO\"\n20 GOTO 40\n"
        "30 PRINT \"NEVER\"\n40 PRINT 255\n";
    const char *lines[] = {
        "30 PRINT \"NEVER\"", "10 PRINT \"HELLO\"",
        "40 PRINT 255", "20 GOTO 40"
    };
    size_t i;
    BSRResult r;
    CHECK(setup(&f) == 0);
    for (i = 0u; i < sizeof(lines) / sizeof(lines[0]); ++i) {
        CHECK(submit(&f, lines[i]).status == BSR_OK);
        CHECK(f.written == 0u);
    }
    CHECK(submit(&f, "LIST").status == BSR_OK);
    CHECK(f.written == strlen(expected_listing));
    CHECK(memcmp(f.output, expected_listing, f.written) == 0);

    memset(f.output, 0x73, sizeof(f.output));
    f.written = 999u;
    r = submit(&f, " RuN ");
    CHECK(r.status == BSR_OK && r.session.status == BS_OK &&
          r.executor_status == BE_OK);
    CHECK(f.runtime.state == BSR_RUNNING);
    CHECK(f.runtime.executor.cursor == 0u); /* RUN did not call be_step. */
    CHECK(f.written == 0u && f.output[0] == 0x73u);
    CHECK(step_output(&f, "HELLO\n") == 0);
    CHECK(step_output(&f, "") == 0);
    CHECK(step_output(&f, "255\n") == 0);
    f.written = 123u;
    memset(f.output, 0x73, sizeof(f.output));
    save(&f, &before);
    r = advance(&f, sizeof(f.output));
    CHECK(r.status == BSR_END && r.executor_status == BE_END);
    CHECK(f.runtime.state == BSR_IDLE);
    CHECK(f.runtime.executor.cursor == before.runtime.executor.cursor);
    CHECK(f.written == before.written);
    CHECK(memcmp(f.output, before.output, sizeof(f.output)) == 0);
    save(&f, &before);
    CHECK(advance(&f, sizeof(f.output)).status == BSR_NOT_RUNNING);
    CHECK(same(&f, &before) == 0);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(f.runtime.executor.cursor == 0u);
    CHECK(step_output(&f, "HELLO\n") == 0);
    return 0;
}

static int test_direct_commands_and_restart(void)
{
    Fixture f;
    Snapshot s;
    size_t i;
    static const char *runs[] = {"RUN", "run", "RuN", "  run  "};
    static const char *rejected[] = {
        "RUN 10", "RUN:LIST", "RUN : LIST", " RUN:NEW ", "RUN\t", "RUNA"
    };
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "10 PRINT 9").status == BSR_OK);
    for (i = 0u; i < sizeof(runs)/sizeof(runs[0]); ++i) {
        f.written = 97u;
        CHECK(submit(&f, runs[i]).status == BSR_OK);
        CHECK(f.runtime.state == BSR_RUNNING);
        CHECK(f.runtime.executor.cursor == 0u);
        CHECK(f.written == 0u);
        CHECK(step_output(&f, "9\n") == 0);
        CHECK(submit(&f, "RUN").status == BSR_OK); /* Restart mid-run. */
        CHECK(step_output(&f, "9\n") == 0);
    }
    for (i = 0u; i < sizeof(rejected)/sizeof(rejected[0]); ++i) {
        BSRResult r;
        save(&f, &s);
        r = submit(&f, rejected[i]);
        CHECK(r.status == BSR_SESSION_ERROR);
        CHECK(r.session.status == (i == 1u || i == 2u || i == 3u
                                  ? BS_MULTIPLE_DIRECT : BS_UNSUPPORTED_DIRECT));
        CHECK(r.executor_status == BE_OK);
        CHECK(same(&f, &s) == 0);
    }
    save(&f, &s);
    CHECK(submit(&f, "10 PRINT 1").status == BSR_BUSY);
    CHECK(same(&f, &s) == 0);
    CHECK(submit(&f, "10").status == BSR_BUSY);
    CHECK(same(&f, &s) == 0);
    CHECK(submit(&f, "25 PRINT 5").status == BSR_BUSY);
    CHECK(same(&f, &s) == 0);
    CHECK(submit(&f, " ").status == BSR_OK);
    CHECK(f.runtime.state == BSR_RUNNING && f.written == 0u);
    CHECK(submit(&f, "LIST").status == BSR_OK);
    CHECK(f.written == strlen("10 PRINT 9\n"));
    CHECK(f.runtime.executor.cursor == s.runtime.executor.cursor);
    save(&f, &s);
    CHECK(advance(&f, sizeof(f.output)).status == BSR_END);
    CHECK(f.runtime.state == BSR_IDLE);
    CHECK(f.written == s.written &&
          memcmp(f.output, s.output, sizeof(f.output)) == 0);
    return 0;
}

static int test_list_and_new_while_running(void)
{
    Fixture f;
    Snapshot s;
    size_t cursor;
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "10 PRINT 1").status == BSR_OK);
    CHECK(submit(&f, "20 PRINT 2").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(step_output(&f, "1\n") == 0);
    cursor = f.runtime.executor.cursor;
    CHECK(submit(&f, " LiSt ").status == BSR_OK);
    CHECK(f.written == strlen("10 PRINT 1\n20 PRINT 2\n"));
    CHECK(f.runtime.state == BSR_RUNNING && f.runtime.executor.cursor == cursor);
    CHECK(step_output(&f, "2\n") == 0);
    save(&f, &s);
    CHECK(bsr_submit(&f.runtime, (const uint8_t *)"NEW", 3u,
                     f.temporary, sizeof(f.temporary),
                     f.storage, sizeof(f.storage), &f.written).status == BSR_OVERLAP);
    CHECK(same(&f, &s) == 0);
    CHECK(submit(&f, " nEw ").status == BSR_OK);
    CHECK(f.runtime.state == BSR_IDLE);
    CHECK(f.program.size == 2u && f.storage[0] == 0u && f.storage[1] == 0u);
    CHECK(submit(&f, "LIST").status == BSR_OK && f.written == 0u);
    save(&f, &s);
    CHECK(advance(&f, sizeof(f.output)).status == BSR_NOT_RUNNING);
    CHECK(same(&f, &s) == 0);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    f.written = 301u;
    memset(f.output, 0x5c, sizeof(f.output));
    CHECK(advance(&f, sizeof(f.output)).status == BSR_END);
    CHECK(f.runtime.state == BSR_IDLE && f.written == 301u);
    CHECK(f.output[0] == 0x5cu);
    return 0;
}

static int test_stop_and_infinite_loop(void)
{
    Fixture f;
    size_t i;
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "10 GOTO 10").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    for (i = 0u; i < 1000u; ++i) {
        CHECK(step_output(&f, "") == 0);
        CHECK(f.runtime.state == BSR_RUNNING && f.runtime.executor.cursor == 0u);
    }
    CHECK(bsr_stop(&f.runtime).status == BSR_OK);
    CHECK(bsr_stop(&f.runtime).status == BSR_OK);
    CHECK(f.runtime.state == BSR_IDLE);
    CHECK(advance(&f, sizeof(f.output)).status == BSR_NOT_RUNNING);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(step_output(&f, "") == 0);
    CHECK(bsr_stop(&f.runtime).status == BSR_OK);
    CHECK(bp_validate(&f.program) == BP_OK);
    return 0;
}

static int test_executor_errors(void)
{
    Fixture f;
    Snapshot s;
    BSRResult r;
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "10 GOTO 999").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    memset(f.output, 0x55, sizeof(f.output));
    f.written = 919u;
    save(&f, &s);
    r = advance(&f, sizeof(f.output));
    CHECK(r.status == BSR_EXECUTOR_ERROR &&
          r.executor_status == BE_MISSING_TARGET);
    CHECK(r.session.status == BS_OK);
    CHECK(same(&f, &s) == 0);
    CHECK(bsr_stop(&f.runtime).status == BSR_OK);
    CHECK(submit(&f, "10 PRINT \"YES\"").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    f.written = 828u;
    save(&f, &s);
    r = advance(&f, 3u);
    CHECK(r.status == BSR_EXECUTOR_ERROR && r.executor_status == BE_NO_SPACE);
    CHECK(same(&f, &s) == 0);
    CHECK(step_output(&f, "YES\n") == 0);
    return 0;
}

static int test_invalid_arguments_and_aliasing(void)
{
    Fixture f;
    Snapshot s;
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "10 PRINT 1").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    f.written = 341u;
    save(&f, &s);
    CHECK(bsr_init(NULL, &f.program).status == BSR_INVALID_ARGUMENT);
    CHECK(bsr_init(&f.runtime, NULL).status == BSR_INVALID_ARGUMENT);
    CHECK(bsr_init((BasicSessionRuntime *)(void *)f.storage,
                   &f.program).status == BSR_OVERLAP);
    CHECK(bsr_init((BasicSessionRuntime *)(void *)&f.program,
                   &f.program).status == BSR_OVERLAP);
    CHECK(bsr_submit(NULL, (const uint8_t *)"RUN", 3u,
                     f.temporary, sizeof(f.temporary),
                     f.output, sizeof(f.output), &f.written).status == BSR_INVALID_ARGUMENT);
    CHECK(bsr_submit(&f.runtime, NULL, 0u,
                     f.temporary, sizeof(f.temporary),
                     f.output, sizeof(f.output), &f.written).status == BSR_INVALID_ARGUMENT);
    CHECK(bsr_submit(&f.runtime, (const uint8_t *)"RUN", 3u,
                     NULL, 0u, f.output, sizeof(f.output),
                     &f.written).status == BSR_INVALID_ARGUMENT);
    CHECK(bsr_submit(&f.runtime, (const uint8_t *)"RUN", 3u,
                     f.temporary, sizeof(f.temporary), NULL, 0u,
                     &f.written).status == BSR_INVALID_ARGUMENT);
    CHECK(bsr_submit(&f.runtime, (const uint8_t *)"RUN", 3u,
                     f.temporary, sizeof(f.temporary),
                     f.output, sizeof(f.output), NULL).status == BSR_INVALID_ARGUMENT);
    CHECK(bsr_submit(&f.runtime, f.storage, 2u,
                     f.temporary, sizeof(f.temporary),
                     f.output, sizeof(f.output), &f.written).status == BSR_OVERLAP);
    CHECK(bsr_submit(&f.runtime, (const uint8_t *)"RUN", 3u,
                     f.storage, sizeof(f.storage),
                     f.output, sizeof(f.output), &f.written).status == BSR_OVERLAP);
    CHECK(bsr_submit(&f.runtime, (const uint8_t *)"RUN", 3u,
                     f.temporary, sizeof(f.temporary),
                     (uint8_t *)(void *)&f.runtime,
                     sizeof(f.runtime), &f.written).status == BSR_OVERLAP);
    CHECK(bsr_submit(&f.runtime, (const uint8_t *)"RUN", 3u,
                     f.temporary, sizeof(f.temporary),
                     f.output, sizeof(f.output),
                     &f.runtime.executor.cursor).status == BSR_OVERLAP);
    CHECK(bsr_step(NULL, f.output, sizeof(f.output),
                   &f.written).status == BSR_INVALID_ARGUMENT);
    CHECK(bsr_step(&f.runtime, NULL, 0u,
                   &f.written).status == BSR_INVALID_ARGUMENT);
    CHECK(bsr_step(&f.runtime, f.output, sizeof(f.output),
                   NULL).status == BSR_INVALID_ARGUMENT);
    CHECK(bsr_step(&f.runtime, f.storage, sizeof(f.storage),
                   &f.written).status == BSR_OVERLAP);
    CHECK(bsr_step(&f.runtime, (uint8_t *)(void *)&f.runtime,
                   sizeof(f.runtime), &f.written).status == BSR_OVERLAP);
    CHECK(bsr_step(&f.runtime, f.output, sizeof(f.output),
                   &f.runtime.executor.cursor).status == BSR_OVERLAP);
    CHECK(bsr_stop(NULL).status == BSR_INVALID_ARGUMENT);
    CHECK(same(&f, &s) == 0);

    CHECK(bsr_stop(&f.runtime).status == BSR_OK);
    CHECK(submit(&f, "NEW").status == BSR_OK);
    CHECK(f.runtime.state == BSR_IDLE);
    return 0;
}

static int test_preserved_session_error(void)
{
    Fixture f;
    Snapshot s;
    BSRResult r;
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "10 PRINT 1").status == BSR_OK);
    save(&f, &s);
    r = submit_bytes(&f, (const uint8_t *)"20 PRINT 256",
                     strlen("20 PRINT 256"), sizeof(f.temporary),
                     sizeof(f.output));
    CHECK(r.status == BSR_SESSION_ERROR);
    CHECK(r.session.status == BS_TOKENIZER_ERROR &&
          r.session.tokenizer_status == BT_NUMBER_OUT_OF_RANGE);
    CHECK(same(&f, &s) == 0);
    r = submit_bytes(&f, (const uint8_t *)"LIST", 4u,
                     sizeof(f.temporary), 1u);
    CHECK(r.status == BSR_SESSION_ERROR);
    CHECK(r.session.status == BS_LISTING_ERROR &&
          r.session.listing_status == BL_NO_SPACE);
    CHECK(same(&f, &s) == 0);

    f.storage[0] = 1u;
    CHECK(bsr_init(&f.runtime, &f.program).status == BSR_EXECUTOR_ERROR);
    CHECK(f.runtime.state == BSR_IDLE);
    f.storage[0] = s.storage[0];
    return 0;
}

int main(void)
{
    CHECK(test_end_to_end() == 0);
    CHECK(test_direct_commands_and_restart() == 0);
    CHECK(test_list_and_new_while_running() == 0);
    CHECK(test_stop_and_infinite_loop() == 0);
    CHECK(test_executor_errors() == 0);
    CHECK(test_invalid_arguments_and_aliasing() == 0);
    CHECK(test_preserved_session_error() == 0);
    puts("basic_session_runtime: OK");
    return 0;
}
