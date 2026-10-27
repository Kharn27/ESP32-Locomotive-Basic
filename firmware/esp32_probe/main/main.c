/*
 * J1.2-HW2: native Locomotive BASIC 1.1 INTEGER boundary probe on ESP32 CYD.
 * No Z80, CPC ROM, REPL, TFT, touch, SD or new BASIC interpreter code.
 * All significant caller-owned regions stay static, as in J0.25.
 * An on-device PASS can be claimed only from an actual captured serial log.
 */
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include "esp_app_desc.h"
#include "esp_heap_caps.h"
#include "esp_idf_version.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum {
    PROBE_PROGRAM_BYTES = 8192,
    PROBE_VARIABLE_CAPACITY = 64,
    PROBE_SOURCE_BYTES = 512,
    PROBE_TEMP_BYTES = 2048,
    PROBE_OUTPUT_BYTES = 4096
};

typedef struct {
    BasicProgram program;
    BasicVariableStore store;
    BasicSessionRuntime runtime;
    uint8_t program_bytes[PROBE_PROGRAM_BYTES];
    BasicVariableEntry entries[PROBE_VARIABLE_CAPACITY];
    uint8_t source[PROBE_SOURCE_BYTES];
    uint8_t temporary[PROBE_TEMP_BYTES];
    uint8_t output[PROBE_OUTPUT_BYTES];
    size_t written;
} LocoProbeStorage;

static LocoProbeStorage probe;

/*
 * J0.25 ABI record: preserve the layout revision and all 16 fields.
 * CI extracts actual Xtensa sizeof values from the linked ELF, not host ABI.
 */
__attribute__((used))
const volatile uint32_t loco_probe_abi_sizes[] = {
    1u,
    (uint32_t)sizeof(void *),
    (uint32_t)sizeof(size_t),
    (uint32_t)sizeof(BasicProgram),
    (uint32_t)sizeof(BasicExecutor),
    (uint32_t)sizeof(BasicSessionRuntime),
    (uint32_t)sizeof(BasicVariableStore),
    (uint32_t)sizeof(BasicVariableEntry),
    (uint32_t)sizeof(BasicVariableKey),
    (uint32_t)sizeof(BasicVariableValue),
    (uint32_t)sizeof(LocoProbeStorage),
    (uint32_t)sizeof(probe.program_bytes),
    (uint32_t)sizeof(probe.entries),
    (uint32_t)sizeof(probe.source),
    (uint32_t)sizeof(probe.temporary),
    (uint32_t)sizeof(probe.output)
};

/* Original J1.2-A CPC6128 NMIN, SHA-256 of these 36 bytes independently
 * verified: dad9d7f1cff60feac8f16fed4374e4f50aac78d17bf5f342468841c0cce01a58.
 * Compare bytes, not a host-native int16 or REAL5 float conversion.
 */
static const uint8_t nmin_cpc_image[] = {
    0x11u, 0x00u, 10u, 0x00u, 0x02u, 0x00u, 0x00u, 0xc2u,
    0xefu, 0xf5u, 0x1fu, 0x00u, 0x00u, 0x00u, 0x00u, 0x90u,
    0x00u,
    0x0bu, 0x00u, 20u, 0x00u, 0xbfu, (uint8_t)' ', 0x02u,
    0x00u, 0x00u, 0xc2u, 0x00u,
    0x06u, 0x00u, 30u, 0x00u, 0x98u, 0x00u,
    0x00u, 0x00u
};

typedef struct {
    const char *name;
    const char *assignment;       /* Numbered line, no formatting at runtime. */
    int16_t integer;
    const char *print;            /* CPC numeric presentation + native LF. */
    int check_cpc_image;
} BoundaryCase;

static const BoundaryCase boundary_cases[] = {
    {"P255", "10 B%=255", 255, " 255 \n", 0},
    {"P256", "10 B%=256", 256, " 256 \n", 0},
    {"N256", "10 B%=-256", -256, "-256 \n", 0},
    {"PMAX", "10 B%=32767", INT16_MAX, " 32767 \n", 0},
    {"NMIN", "10 B%=-32768", INT16_MIN, "-32768 \n", 1}
};

static void hardware_memory_snapshot(const char *phase)
{
    /* ESP-IDF FreeRTOS returns stack high-water mark in bytes, not words. */
    printf("J1.2-HW2 DEVICE_MEMORY phase=%s heap8_free=%zu heap8_largest=%zu "
           "heap8_min=%zu stack_hwm_bytes=%u\n",
           phase,
           heap_caps_get_free_size(MALLOC_CAP_8BIT),
           heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
           heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT),
           (unsigned)uxTaskGetStackHighWaterMark(NULL));
}

static void build_identity(void)
{
    static const char alphabet[] = "0123456789abcdef";
    const esp_app_desc_t *desc = esp_app_get_description();
    char sha[65];
    size_t i;
    /* Embedded application ELF identity. Compare with the exact ELF/flash
     * artifact used, not with a source-branch HEAD guessed from this text. */
    for (i = 0u; i < sizeof(desc->app_elf_sha256); ++i) {
        const uint8_t byte = desc->app_elf_sha256[i];
        sha[2u * i] = alphabet[byte >> 4];
        sha[2u * i + 1u] = alphabet[byte & 0x0fu];
    }
    sha[sizeof(sha) - 1u] = '\0';
    printf("J1.2-HW2 BUILD_IDENT project=%s version=%s elf_sha256=%s "
           "idf=%s target=esp32\n",
           desc->project_name, desc->version, sha, esp_get_idf_version());
}

static int fail(const char *name, const char *stage, int got, int expected)
{
    printf("J1.2-HW2 case=%s FAIL stage=%s got=%d expected=%d\n",
           name, stage, got, expected);
    return 0;
}

static int probe_init(const char *name)
{
    BSRResult result;
    BPStatus program_status;
    BVSStatus store_status;

    /* Each scenario has a fresh program, runtime, and variable store. */
    memset(&probe, 0, sizeof(probe));
    program_status = bp_init(&probe.program, probe.program_bytes,
                             sizeof(probe.program_bytes));
    if (program_status != BP_OK) {
        return fail(name, "bp_init", (int)program_status, (int)BP_OK);
    }
    store_status = bvs_init(&probe.store, probe.entries,
                            PROBE_VARIABLE_CAPACITY);
    if (store_status != BVS_OK) {
        return fail(name, "bvs_init", (int)store_status, (int)BVS_OK);
    }
    result = bsr_init_with_store(&probe.runtime, &probe.program, &probe.store);
    if (result.status != BSR_OK) {
        return fail(name, "bsr_init_with_store", (int)result.status, (int)BSR_OK);
    }
    return 1;
}

static int submit(const char *name, const char *text)
{
    const size_t length = strlen(text);
    BSRResult result;
    if (length > sizeof(probe.source)) {
        return fail(name, "source_capacity", (int)length, PROBE_SOURCE_BYTES);
    }
    memcpy(probe.source, text, length);
    probe.written = (size_t)-1;
    result = bsr_submit(&probe.runtime, probe.source, length,
                        probe.temporary, sizeof(probe.temporary),
                        probe.output, sizeof(probe.output), &probe.written);
    if (result.status != BSR_OK) {
        printf("J1.2-HW2 case=%s detail=BS_%d BT_%d BP_%d BL_%d\n",
               name, (int)result.session.status,
               (int)result.session.tokenizer_status,
               (int)result.session.program_status,
               (int)result.session.listing_status);
        return fail(name, "bsr_submit", (int)result.status, (int)BSR_OK);
    }
    if (probe.written != 0u) {
        return fail(name, "unexpected_submit_output", (int)probe.written, 0);
    }
    return 1;
}

static int start_run(const char *name)
{
    if (!submit(name, "RUN")) {
        return 0;
    }
    if (probe.runtime.state != BSR_RUNNING || probe.store.count != 0u) {
        return fail(name, "RUN_reset", (int)probe.runtime.state,
                    (int)BSR_RUNNING);
    }
    return 1;
}

static int step_expect(const char *name, const char *stage,
                       const char *expected_output)
{
    const size_t expected_length = strlen(expected_output);
    BSRResult result;
    probe.written = (size_t)-1;
    result = bsr_step(&probe.runtime, probe.output,
                      sizeof(probe.output), &probe.written);
    if (result.status != BSR_OK || result.executor_status != BE_OK) {
        printf("J1.2-HW2 case=%s detail=BE_%d\n",
               name, (int)result.executor_status);
        return fail(name, stage, (int)result.status, (int)BSR_OK);
    }
    if (probe.written != expected_length ||
        memcmp(probe.output, expected_output, expected_length) != 0) {
        /* No fake BASIC output: a printable step must match exactly. */
        return fail(name, stage, (int)probe.written, (int)expected_length);
    }
    return 1;
}

static int end_expect(const char *name)
{
    BSRResult result;
    probe.written = 12345u;
    probe.output[0] = 0x5au;
    result = bsr_step(&probe.runtime, probe.output,
                      sizeof(probe.output), &probe.written);
    if (result.status != BSR_END || result.executor_status != BE_END ||
        probe.runtime.state != BSR_IDLE || probe.written != 12345u ||
        probe.output[0] != 0x5au) {
        printf("J1.2-HW2 case=%s detail=BE_%d state=%d written=%zu\n",
               name, (int)result.executor_status,
               (int)probe.runtime.state, probe.written);
        return fail(name, "END_stop", (int)result.status, (int)BSR_END);
    }
    return 1;
}

static int check_value(const char *name, int16_t expected)
{
    BasicVariableKey key = {0};
    BasicVariableValue value = {0};
    BVSStatus status;
    key.type = (uint8_t)BVT_INTEGER;
    key.name_length = 1u;
    key.name[0] = (uint8_t)'B';
    status = bvs_get(&probe.store, &key, &value);
    if (status != BVS_OK || value.type != (uint8_t)BVT_INTEGER ||
        value.data.integer != expected) {
        printf("J1.2-HW2 case=%s detail=BVS_%d variable_type=%u\n",
               name, (int)status, (unsigned)value.type);
        return fail(name, "B_integer", status == BVS_OK ?
                    (int)value.data.integer : (int)status, (int)expected);
    }
    return 1;
}

static int check_nmin_image(void)
{
    size_t exported = 123u;
    BPStatus status = bp_export(&probe.program, probe.output,
                                sizeof(probe.output), &exported);
    if (status != BP_OK || exported != sizeof(nmin_cpc_image) ||
        memcmp(probe.output, nmin_cpc_image, sizeof(nmin_cpc_image)) != 0) {
        printf("J1.2-HW2 case=NMIN detail=BP_%d bytes=%zu\n",
               (int)status, exported);
        return fail("NMIN", "NMIN_CPC_IMAGE", (int)exported,
                    (int)sizeof(nmin_cpc_image));
    }
    printf("J1.2-HW2 case=NMIN IMAGE_MATCH_EXACT PASS bytes=%zu "
           "operand=F5-1F-00-00-00-00-90\n", exported);
    return 1;
}

static int demo_run(void)
{
    static const char *const lines[] = {
        "10 A%=2", "20 B%=A%+3", "30 PRINT B%", "40 END"
    };
    size_t i;
    if (!probe_init("J0_25_FIVE")) {
        return 0;
    }
    for (i = 0u; i < sizeof(lines) / sizeof(lines[0]); ++i) {
        if (!submit("J0_25_FIVE", lines[i])) {
            return 0;
        }
    }
    if (!start_run("J0_25_FIVE") ||
        !step_expect("J0_25_FIVE", "A_assign", "") ||
        !step_expect("J0_25_FIVE", "B_addition", "") ||
        !check_value("J0_25_FIVE", 5) ||
        !step_expect("J0_25_FIVE", "PRINT_B", " 5 \n")) {
        return 0;
    }
    /* Publish the REAL interpreter's four bytes, never a fabricated 5. */
    printf("J0.25 BASIC_OUTPUT: %.*s", (int)probe.written,
           (const char *)probe.output);
    if (!step_expect("J0_25_FIVE", "END_line", "") ||
        !end_expect("J0_25_FIVE")) {
        return 0;
    }
    printf("J1.2-HW2 case=J0_25_FIVE PASS stored=5 print_bytes=4 end=BE_END\n");
    return 1;
}

static int boundary_run(const BoundaryCase *test)
{
    if (!probe_init(test->name) ||
        !submit(test->name, test->assignment) ||
        !submit(test->name, "20 PRINT B%") ||
        !submit(test->name, "30 END")) {
        return 0;
    }
    if (test->check_cpc_image && !check_nmin_image()) {
        return 0;
    }
    if (!start_run(test->name) ||
        !step_expect(test->name, "assign", "") ||
        !check_value(test->name, test->integer)) {
        return 0;
    }
    if (probe.store.count != 1u) {
        return fail(test->name, "variable_count", (int)probe.store.count, 1);
    }
    if (!step_expect(test->name, "PRINT_B", test->print) ||
        !step_expect(test->name, "END_line", "") ||
        !end_expect(test->name) ||
        !check_value(test->name, test->integer)) {
        return 0;
    }
    printf("J1.2-HW2 case=%s PASS stored=%d print_bytes=%zu end=BE_END\n",
           test->name, (int)test->integer, strlen(test->print));
    return 1;
}

/* Small allocation-free integrity probe: checks the entire statically
 * owned program, entries and output buffers, not only their used prefixes.
 * In addition the actual stored B% value and descriptor fields are checked. */
static uint32_t fingerprint(const void *memory, size_t size)
{
    const uint8_t *bytes = (const uint8_t *)memory;
    uint32_t value = UINT32_C(2166136261);
    size_t i;
    for (i = 0u; i < size; ++i) {
        value = (value ^ (uint32_t)bytes[i]) * UINT32_C(16777619);
    }
    return value;
}

static int reject_positive_32768(void)
{
    static const char attempt[] = "10 B%=32768";
    static const char *const old_lines[] = {
        "10 B%=255", "20 PRINT B%", "30 END"
    };
    BasicProgram old_program;
    BasicVariableStore old_store;
    BasicVariableEntry old_b_entry;
    BasicVariableKey key = {0};
    BSRState old_state;
    size_t old_cursor;
    uint32_t old_program_hash, old_entries_hash, old_output_hash;
    BSRResult result;
    size_t i;
    const char *name = "P32768_REJECT";

    if (!probe_init(name)) {
        return 0;
    }
    for (i = 0u; i < sizeof(old_lines) / sizeof(old_lines[0]); ++i) {
        if (!submit(name, old_lines[i])) {
            return 0;
        }
    }
    /* A live value and an existing program must both survive the refusal.
     * STOP (not RUN) preserves B%=255 and makes the numbered edit eligible. */
    if (!start_run(name) || !step_expect(name, "seed_assign", "") ||
        !check_value(name, 255)) {
        return 0;
    }
    result = bsr_stop(&probe.runtime);
    if (result.status != BSR_OK || probe.runtime.state != BSR_IDLE) {
        return fail(name, "STOP", (int)result.status, (int)BSR_OK);
    }
    key.type = (uint8_t)BVT_INTEGER;
    key.name_length = 1u;
    key.name[0] = (uint8_t)'B';
    if (probe.store.count != 1u) {
        return fail(name, "seed_count", (int)probe.store.count, 1);
    }
    old_b_entry = probe.entries[0];
    old_program = probe.program;
    old_store = probe.store;
    old_state = probe.runtime.state;
    old_cursor = probe.runtime.executor.cursor;
    old_program_hash = fingerprint(probe.program_bytes, sizeof(probe.program_bytes));
    old_entries_hash = fingerprint(probe.entries, sizeof(probe.entries));

    memset(probe.output, 0xa5, sizeof(probe.output));
    old_output_hash = fingerprint(probe.output, sizeof(probe.output));
    probe.written = 12345u;
    memcpy(probe.source, attempt, sizeof(attempt) - 1u);
    result = bsr_submit(&probe.runtime, probe.source, sizeof(attempt) - 1u,
                        probe.temporary, sizeof(probe.temporary),
                        probe.output, sizeof(probe.output), &probe.written);
    if (result.status != BSR_SESSION_ERROR ||
        result.session.status != BS_TOKENIZER_ERROR ||
        result.session.tokenizer_status != BT_NUMBER_OUT_OF_RANGE) {
        printf("J1.2-HW2 case=%s unexpected_rejection BSR=%d BS=%d BT=%d\n",
               name, (int)result.status, (int)result.session.status,
               (int)result.session.tokenizer_status);
        return fail(name, "positive_32768_tokenizer", (int)result.status,
                    (int)BSR_SESSION_ERROR);
    }
    if (probe.written != 12345u ||
        fingerprint(probe.output, sizeof(probe.output)) != old_output_hash ||
        probe.program.size != old_program.size ||
        probe.program.capacity != old_program.capacity ||
        probe.program.data != old_program.data ||
        fingerprint(probe.program_bytes, sizeof(probe.program_bytes)) != old_program_hash ||
        probe.store.count != old_store.count ||
        probe.store.capacity != old_store.capacity ||
        probe.store.entries != old_store.entries ||
        fingerprint(probe.entries, sizeof(probe.entries)) != old_entries_hash ||
        memcmp(&probe.entries[0], &old_b_entry, sizeof(old_b_entry)) != 0 ||
        probe.runtime.state != old_state ||
        probe.runtime.executor.cursor != old_cursor ||
        !check_value(name, 255)) {
        return fail(name, "reject_atomicity", (int)probe.written, 12345);
    }
    /* The preserved program remains executable after the rejected edit. */
    if (!start_run(name) ||
        !step_expect(name, "preserved_assign", "") ||
        !check_value(name, 255) ||
        !step_expect(name, "preserved_PRINT", " 255 \n") ||
        !step_expect(name, "preserved_END", "") ||
        !end_expect(name)) {
        return 0;
    }
    printf("J1.2-HW2 case=%s PASS tokenizer=BT_NUMBER_OUT_OF_RANGE "
           "program_unchanged=1 store_unchanged=1 output_unchanged=1 "
           "cursor_unchanged=1 preserved_run=END\n", name);
    return 1;
}

void app_main(void)
{
    int all_passed = 1;
    size_t i;

    printf("J1.2-HW2 START state=ON_DEVICE_UNVERIFIED_IN_CI\n");
    build_identity();
    printf("J1.2-HW2 STATIC_PROBE_BYTES=%zu ABI_POINTER_BYTES=%" PRIu32 "\n",
           sizeof(probe), loco_probe_abi_sizes[1]);
    hardware_memory_snapshot("before");

    if (!demo_run()) {
        all_passed = 0;
    }
    hardware_memory_snapshot("after_J0_25_FIVE");
    for (i = 0u; i < sizeof(boundary_cases) / sizeof(boundary_cases[0]); ++i) {
        if (!boundary_run(&boundary_cases[i])) {
            all_passed = 0;
        }
        hardware_memory_snapshot(boundary_cases[i].name);
    }
    if (!reject_positive_32768()) {
        all_passed = 0;
    }
    hardware_memory_snapshot("after");

    /* Exactly one terminal marker; only the actual device UART log can
     * establish real hardware verification (not a green CI compilation). */
    printf("J1.2-HW2 %s\n",
           all_passed ? "ON_DEVICE_TEST_PASS" : "ON_DEVICE_TEST_FAIL");
}
