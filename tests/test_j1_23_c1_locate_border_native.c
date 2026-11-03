/* J1.23-C1 — isolated C99 CORE-ONLY typed LOCATE/BORDER execution.
 * Read-only 20 CPC6128 programs, original/repeat. Native effects are
 * logical events, never a claim of matching TFT or CPC screen pixels. */
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "J1.23-C1 %s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

enum { IMAGE = 2048, ENTRIES = 8, ARENA = 256, OUT = 64, EVENT_CAP = 4 };
typedef struct {
    BasicProgram program;
    BasicVariableStore store;
    BasicVariableEntry entries[ENTRIES];
    BasicSessionRuntime runtime;
    uint8_t image[IMAGE], arena[ARENA], temporary[256], output[OUT];
    BEVideoEvent events[EVENT_CAP];
    size_t written, event_written;
} Fixture;
static Fixture f;
static Fixture before;

/* ERR/ERL here are values read independently from CPC printer bytes, never
 * inferred from BEStatus, which is a host diagnostic and not a CPC code. */
typedef struct {
    const char *id;
    int cpc_err, cpc_erl;
    BEStatus host;
    BEVideoEventType type;
    uint8_t first, second, second_present;
} Case;
static const Case cases[] = {
    {"L_01_01",  0, 0, BE_OK, BE_VIDEO_SET_TEXT_CURSOR, 1, 1, 0},
    {"L_40_25",  0, 0, BE_OK, BE_VIDEO_SET_TEXT_CURSOR, 40, 25, 0},
    {"L_02_03",  0, 0, BE_OK, BE_VIDEO_SET_TEXT_CURSOR, 2, 3, 0},
    {"L_00_01",  5,10, BE_INVALID_LOCATE, 0, 0, 0, 0},
    {"L_41_01",  0, 0, BE_OK, BE_VIDEO_SET_TEXT_CURSOR, 41, 1, 0},
    {"L_01_00",  5,10, BE_INVALID_LOCATE, 0, 0, 0, 0},
    {"L_01_26",  0, 0, BE_OK, BE_VIDEO_SET_TEXT_CURSOR, 1, 26, 0},
    {"L_NEG_01", 5,10, BE_INVALID_LOCATE, 0, 0, 0, 0},
    {"L_EXPR",   0, 0, BE_OK, BE_VIDEO_SET_TEXT_CURSOR, 3, 5, 0},
    /* CPC SCREEN is Syntax error in 10; printer ERR=0 is contradictory. */
    {"L_MISSING",0,10, BE_DIAG_CONTRADICTORY, 0, 0, 0, 0},
    {"B_00",     0, 0, BE_OK, BE_VIDEO_SET_BORDER, 0, 0, 0},
    {"B_26",     0, 0, BE_OK, BE_VIDEO_SET_BORDER, 26, 0, 0},
    {"B_27",     0, 0, BE_OK, BE_VIDEO_SET_BORDER, 27, 0, 0},
    {"B_NEG",    5,10, BE_INVALID_BORDER, 0, 0, 0, 0},
    {"B_00_26",  0, 0, BE_OK, BE_VIDEO_SET_BORDER, 0, 26, 1},
    {"B_26_00",  0, 0, BE_OK, BE_VIDEO_SET_BORDER, 26, 0, 1},
    {"B_26_27",  0, 0, BE_OK, BE_VIDEO_SET_BORDER, 26, 27, 1},
    {"B_NEG_01", 5,10, BE_INVALID_BORDER, 0, 0, 0, 0},
    {"B_EXPR",   0, 0, BE_OK, BE_VIDEO_SET_BORDER, 3, 7, 1},
    {"B_MISSING",22,10,BE_OPERAND_MISSING, 0, 0, 0, 0}
};

static int reset(void)
{
    memset(&f, 0, sizeof(f));
    CHECK(bp_init(&f.program, f.image, sizeof(f.image)) == BP_OK);
    CHECK(bvs_init_with_arena(&f.store, f.entries, ENTRIES,
                              f.arena, sizeof(f.arena)) == BVS_OK);
    CHECK(bsr_init_with_store(&f.runtime, &f.program, &f.store).status == BSR_OK);
    return 0;
}
static BSRResult submit(const char *source)
{
    return bsr_submit(&f.runtime, (const uint8_t *)source, strlen(source),
                      f.temporary, sizeof(f.temporary), f.output,
                      sizeof(f.output), &f.written);
}
static void canaries(void)
{
    memset(f.output, 0xa5, sizeof(f.output));
    memset(f.events, 0x5a, sizeof(f.events));
    f.written = 771u;
    f.event_written = 772u;
}
static void snapshot(void) { memcpy(&before, &f, sizeof(f)); }
static int state_unchanged(void)
{
    CHECK(memcmp(&f.program, &before.program, sizeof(f.program)) == 0);
    CHECK(memcmp(&f.runtime, &before.runtime, sizeof(f.runtime)) == 0);
    CHECK(memcmp(&f.store, &before.store, sizeof(f.store)) == 0);
    CHECK(memcmp(f.image, before.image, sizeof(f.image)) == 0);
    CHECK(memcmp(f.entries, before.entries, sizeof(f.entries)) == 0);
    CHECK(memcmp(f.arena, before.arena, sizeof(f.arena)) == 0);
    return 0;
}
static int fully_unchanged(void)
{
    CHECK(memcmp(&f, &before, sizeof(f)) == 0);
    return 0;
}
static int load(const char *root, const char *session, const char *id,
                const char *leaf, uint8_t *data, size_t cap, size_t *length)
{
    char path[512];
    FILE *fp;
    int count = snprintf(path, sizeof(path),
        "%s/tests/fixtures/cpc6128/j1_23_a_locate_border/%s/%s/%s",
        root, session, id, leaf);
    CHECK(count > 0 && (size_t)count < sizeof(path));
    fp = fopen(path, "rb");
    CHECK(fp != NULL);
    *length = fread(data, 1u, cap, fp);
    CHECK(*length > 0u && *length < cap);
    CHECK(fgetc(fp) == EOF && !ferror(fp));
    CHECK(fclose(fp) == 0);
    return 0;
}
static int prepare_oracle(const char *root, const char *session,
                          const Case *item)
{
    uint8_t program_image[IMAGE], printer[512];
    size_t program_length, printer_length;
    int err = -1, erl = -1;
    CHECK(reset() == 0);
    CHECK(load(root, session, item->id, "program.bin",
               program_image, sizeof(program_image), &program_length) == 0);
    CHECK(load(root, session, item->id, "run/printer.dat",
               printer, sizeof(printer), &printer_length) == 0);
    /* CPC printer format: decimal ERR CRLF, decimal ERL CRLF, then LIST.
     * Never treat L_MISSING ERR=0 as a successful native execution. */
    printer[printer_length] = 0u;
    CHECK(sscanf((const char *)printer, "%d %d", &err, &erl) == 2);
    CHECK(err == item->cpc_err && erl == item->cpc_erl);
    CHECK(bp_import(&f.program, program_image, program_length) == BP_OK);
    CHECK(submit("RUN").status == BSR_OK);
    CHECK(f.runtime.state == BSR_RUNNING);
    canaries();
    return 0;
}
static int positive(const Case *item)
{
    uint8_t repeated_output[OUT];
    BEVideoEvent repeated_events[EVENT_CAP], expected;
    size_t repeated_written = 999u, repeated_count = 998u;
    BSRResult r;
    CHECK(item->host == BE_OK);
    snapshot();
    /* Frozen J1.23-B legacy API stays intentionally fail-closed/unknown. */
    r = bsr_step(&f.runtime, f.output, OUT, &f.written);
    CHECK(r.status == BSR_EXECUTOR_ERROR &&
          r.executor_status == BE_UNKNOWN_TOKEN);
    CHECK(fully_unchanged() == 0);
    r = bsr_step_events(&f.runtime, f.output, OUT, &f.written,
                        NULL, 0u, &f.event_written);
    CHECK(r.status == BSR_EXECUTOR_ERROR &&
          r.executor_status == BE_EVENT_RECEIVER_REQUIRED);
    CHECK(fully_unchanged() == 0);
    r = bsr_preview_step_events(&f.runtime, f.output, OUT, &f.written,
                                f.events, EVENT_CAP, &f.event_written);
    CHECK(r.status == BSR_OK);
    CHECK(f.written == 0u && f.event_written == 1u);
    CHECK(state_unchanged() == 0);
    CHECK(memcmp(f.output, before.output, sizeof(f.output)) == 0);
    CHECK(f.events[0].type == item->type);
    CHECK(f.events[0].pen == item->first);
    CHECK(f.events[0].ink == item->second);
    CHECK(f.events[0].print_offset == 0u);
    CHECK(f.events[0].colour == item->second_present);
    CHECK(memcmp(f.events + 1u, before.events + 1u,
                 sizeof(f.events) - sizeof(f.events[0])) == 0);
    memcpy(repeated_output, before.output, sizeof(repeated_output));
    memcpy(repeated_events, before.events, sizeof(repeated_events));
    r = bsr_preview_step_events(&f.runtime, repeated_output,
                sizeof(repeated_output), &repeated_written, repeated_events,
                EVENT_CAP, &repeated_count);
    CHECK(r.status == BSR_OK && repeated_written == 0u && repeated_count == 1u);
    CHECK(memcmp(repeated_output, f.output, OUT) == 0);
    CHECK(memcmp(repeated_events, f.events, sizeof(f.events)) == 0);
    CHECK(state_unchanged() == 0);
    expected = f.events[0];
    memset(f.events, 0x5a, sizeof(f.events));
    f.written = 773u;
    f.event_written = 774u;
    r = bsr_step_events(&f.runtime, f.output, OUT, &f.written,
                        f.events, EVENT_CAP, &f.event_written);
    CHECK(r.status == BSR_OK && f.written == 0u && f.event_written == 1u);
    CHECK(memcmp(&f.events[0], &expected, sizeof(expected)) == 0);
    CHECK(f.runtime.executor.cursor != before.runtime.executor.cursor);
    CHECK(f.runtime.state == BSR_RUNNING);
    CHECK(memcmp(&f.program, &before.program, sizeof(f.program)) == 0);
    CHECK(memcmp(f.image, before.image, sizeof(f.image)) == 0);
    CHECK(memcmp(&f.store, &before.store, sizeof(f.store)) == 0);
    CHECK(memcmp(f.entries, before.entries, sizeof(f.entries)) == 0);
    CHECK(memcmp(f.arena, before.arena, sizeof(f.arena)) == 0);
    CHECK(memcmp(f.output, before.output, sizeof(f.output)) == 0);
    return 0;
}
static int negative(BEStatus expected)
{
    BSRResult r;
    snapshot();
    r = bsr_preview_step_events(&f.runtime, f.output, OUT, &f.written,
                                f.events, EVENT_CAP, &f.event_written);
    CHECK(r.status == BSR_EXECUTOR_ERROR && r.executor_status == expected);
    CHECK(fully_unchanged() == 0);
    r = bsr_step_events(&f.runtime, f.output, OUT, &f.written,
                        f.events, EVENT_CAP, &f.event_written);
    CHECK(r.status == BSR_EXECUTOR_ERROR && r.executor_status == expected);
    CHECK(fully_unchanged() == 0);
    r = bsr_step(&f.runtime, f.output, OUT, &f.written);
    CHECK(r.status == BSR_EXECUTOR_ERROR && r.executor_status == expected);
    CHECK(fully_unchanged() == 0);
    return 0;
}
static int all_oracle_cases(const char *root)
{
    static const char *const sessions[] = {"original", "repeat"};
    size_t i, j, positive_count = 0u, negative_count = 0u;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        for (j = 0u; j < 2u; ++j) {
            CHECK(prepare_oracle(root, sessions[j], &cases[i]) == 0);
            if (cases[i].host == BE_OK) {
                CHECK(positive(&cases[i]) == 0);
                ++positive_count;
            } else {
                CHECK(negative(cases[i].host) == 0);
                ++negative_count;
            }
        }
        printf("%s: CPC ERR=%d ERL=%d, host=%d (original/repeat)\n",
               cases[i].id, cases[i].cpc_err, cases[i].cpc_erl,
               (int)cases[i].host);
    }
    CHECK(positive_count == 26u && negative_count == 14u);
    return 0;
}
static int capacity_and_offsets(void)
{
    static const uint8_t mixed[] = {
        0xbfu,' ','"','A','"',0x01u,
        0xa9u,' ',0x0fu,',',0x0fu,0x01u,
        0xbfu,' ','"','B','"',0x01u,
        0x82u,' ',0x0eu,',',0x19u,26u
    };
    BSRResult r;
    CHECK(reset() == 0);
    CHECK(bp_put(&f.program, 10u, mixed, sizeof(mixed)) == BP_OK);
    CHECK(submit("RUN").status == BSR_OK);
    canaries();
    snapshot();
    r = bsr_step_events(&f.runtime, f.output, OUT, &f.written,
                        f.events, 0u, &f.event_written);
    CHECK(r.status == BSR_EXECUTOR_ERROR &&
          r.executor_status == BE_NO_EVENT_SPACE);
    CHECK(fully_unchanged() == 0);
    r = bsr_preview_step_events(&f.runtime, f.output, OUT, &f.written,
                                f.events, 1u, &f.event_written);
    CHECK(r.status == BSR_EXECUTOR_ERROR &&
          r.executor_status == BE_NO_EVENT_SPACE);
    CHECK(fully_unchanged() == 0);
    r = bsr_step_events(&f.runtime, f.output, OUT, &f.written,
                        f.events, 1u, &f.event_written);
    CHECK(r.status == BSR_EXECUTOR_ERROR &&
          r.executor_status == BE_NO_EVENT_SPACE);
    CHECK(fully_unchanged() == 0);
    r = bsr_step(&f.runtime, f.output, OUT, &f.written);
    CHECK(r.status == BSR_EXECUTOR_ERROR &&
          r.executor_status == BE_EVENT_RECEIVER_REQUIRED);
    CHECK(fully_unchanged() == 0);
    r = bsr_step_events(&f.runtime, f.output, 3u, &f.written,
                        f.events, 2u, &f.event_written);
    CHECK(r.status == BSR_EXECUTOR_ERROR && r.executor_status == BE_NO_SPACE);
    CHECK(fully_unchanged() == 0);
    r = bsr_preview_step_events(&f.runtime, f.output, OUT, &f.written,
                                f.events, 2u, &f.event_written);
    CHECK(r.status == BSR_OK);
    CHECK(state_unchanged() == 0);
    CHECK(f.written == 4u && f.event_written == 2u);
    CHECK(memcmp(f.output, "A\nB\n", 4u) == 0 && f.output[4] == 0xa5u);
    CHECK(f.events[0].type == BE_VIDEO_SET_TEXT_CURSOR);
    CHECK(f.events[0].pen == 1u && f.events[0].ink == 1u);
    CHECK(f.events[0].colour == 0u && f.events[0].print_offset == 2u);
    CHECK(f.events[1].type == BE_VIDEO_SET_BORDER);
    CHECK(f.events[1].pen == 0u && f.events[1].ink == 26u);
    CHECK(f.events[1].colour == 1u && f.events[1].print_offset == 4u);
    /* No event may leak into legacy PRINT bytes. */
    CHECK(memcmp(f.output + 4u, before.output + 4u, OUT - 4u) == 0);
    return 0;
}
static int malformed_and_unmeasured(void)
{
    static const uint8_t truncated_l[] = {0xa9u,' ',0x0fu,',',0x19u};
    static const uint8_t truncated_b[] = {0x82u,' ',0xf5u};
    static const uint8_t unmeasured_l[] = {0xa9u,' ',0x11u,',',0x13u};
    static const uint8_t unmeasured_b[] = {0x82u,' ',0x0fu};
    static const uint8_t invalid_b[] = {0x82u,' ',0x19u,28u};
    static const struct {const uint8_t *body;size_t len;BEStatus status;} bad[] = {
        {truncated_l,sizeof(truncated_l),BE_TRUNCATED},
        {truncated_b,sizeof(truncated_b),BE_TRUNCATED},
        {unmeasured_l,sizeof(unmeasured_l),BE_UNSUPPORTED},
        {unmeasured_b,sizeof(unmeasured_b),BE_UNSUPPORTED},
        {invalid_b,sizeof(invalid_b),BE_BAD_SEQUENCE}
    };
    size_t i;
    for (i=0u;i<sizeof(bad)/sizeof(bad[0]);++i) {
        CHECK(reset() == 0);
        CHECK(bp_put(&f.program, 10u, bad[i].body, bad[i].len) == BP_OK);
        CHECK(submit("RUN").status == BSR_OK);
        canaries();
        CHECK(negative(bad[i].status) == 0);
    }
    return 0;
}
static int abi(void)
{
    CHECK(BE_VIDEO_SET_TEXT_PEN == 1 && BE_VIDEO_SET_INK == 2);
    CHECK(BE_VIDEO_CLEAR_TEXT == 3 && BE_VIDEO_SET_TEXT_PAPER == 4);
    CHECK(BE_VIDEO_SET_TEXT_CURSOR == 5 && BE_VIDEO_SET_BORDER == 6);
    CHECK(offsetof(BEVideoEvent, print_offset) == 8u);
    CHECK(offsetof(BEVideoEvent, ink) == (sizeof(size_t) == 4u ? 12u : 16u));
    CHECK(offsetof(BEVideoEvent, colour) == (sizeof(size_t) == 4u ? 13u : 17u));
    CHECK(sizeof(BEVideoEvent) == (sizeof(size_t) == 4u ? 16u : 24u));
    return 0;
}
int main(int argc, char **argv)
{
    CHECK(argc == 2);
    CHECK(abi() == 0);
    CHECK(all_oracle_cases(argv[1]) == 0);
    CHECK(capacity_and_offsets() == 0);
    CHECK(malformed_and_unmeasured() == 0);
    puts("J1.23-C1 20/20 CPC original/repeat logical events/diagnostics; "
         "atomicity/preview/offset/capacity/legacy/ABI PASS (no TFT)");
    return 0;
}
