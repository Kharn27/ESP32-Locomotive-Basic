/*
 * J0.25 first native Xtensa feasibility probe. No Z80, CPC ROM or display.
 * The only BASIC execution path is through the existing portable C99 APIs.
 * All significant caller-owned regions are static, not app_main stack locals.
 */
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
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
 * An actual Xtensa compiler emits these sizeof constants into the linked ELF.
 * CI extracts them from this symbol's ELF section, rather than using host ABI.
 * The first item is a layout revision; values are uint32_t in target endian.
 */
/* Volatile forces an actual referenced load: linker garbage collection must
 * not discard this record even under ESP-IDF's optimized release build. */
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

static void hardware_memory_snapshot(const char *phase)
{
    /* Only serial logs captured from a real ESP32 are on-device evidence. */
    printf("J0.25 DEVICE_MEMORY phase=%s heap8_free=%zu heap8_largest=%zu "
           "heap8_min=%zu stack_hwm_bytes=%u\n",
           phase,
           heap_caps_get_free_size(MALLOC_CAP_8BIT),
           heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
           heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT),
           (unsigned)uxTaskGetStackHighWaterMark(NULL));
    /* ESP-IDF FreeRTOS reports this high-water mark in BYTES, not words. */
}

static int fail(const char *phase, int status, int detail)
{
    printf("J0.25 ON_DEVICE_FAIL phase=%s status=%d detail=%d\n",
           phase, status, detail);
    return 0;
}

static int submit(const char *text)
{
    const size_t len = strlen(text);
    BSRResult result;
    if (len > sizeof(probe.source)) {
        return fail("source-too-long", (int)len, 0);
    }
    memcpy(probe.source, text, len);
    probe.written = 0u;
    result = bsr_submit(&probe.runtime,
                        probe.source, len,
                        probe.temporary, sizeof(probe.temporary),
                        probe.output, sizeof(probe.output),
                        &probe.written);
    if (result.status != BSR_OK || probe.written != 0u) {
        return fail("bsr_submit", (int)result.status, (int)result.session.status);
    }
    return 1;
}

static int check_value_five(void)
{
    BasicVariableKey key = {0};
    BasicVariableValue value = {0};
    BVSStatus status;
    key.type = (uint8_t)BVT_INTEGER;
    key.name_length = 1u;
    key.name[0] = (uint8_t)'B';
    status = bvs_get(&probe.store, &key, &value);
    if (status != BVS_OK || value.type != (uint8_t)BVT_INTEGER ||
        value.data.integer != 5) {
        return fail("B_value", (int)status,
                    status == BVS_OK ? (int)value.data.integer : -1);
    }
    return 1;
}

static int demo_run(void)
{
    static const char *const lines[] = {
        "10 A%=2", "20 B%=A%+3", "30 PRINT B%", "40 END"
    };
    size_t i;
    BSRResult result;

    if (bp_init(&probe.program, probe.program_bytes,
                sizeof(probe.program_bytes)) != BP_OK) {
        return fail("bp_init", -1, 0);
    }
    if (bvs_init(&probe.store, probe.entries,
                 PROBE_VARIABLE_CAPACITY) != BVS_OK) {
        return fail("bvs_init", -1, 0);
    }
    result = bsr_init_with_store(&probe.runtime, &probe.program, &probe.store);
    if (result.status != BSR_OK) {
        return fail("bsr_init_with_store", (int)result.status,
                    (int)result.executor_status);
    }
    for (i = 0u; i < sizeof(lines) / sizeof(lines[0]); ++i) {
        if (!submit(lines[i])) {
            return 0;
        }
    }
    if (!submit("RUN") || probe.runtime.state != BSR_RUNNING) {
        return fail("RUN_state", (int)probe.runtime.state, 0);
    }

    /* One statement per step in this test program. */
    for (i = 0u; i < 4u; ++i) {
        probe.written = 0u;
        result = bsr_step(&probe.runtime, probe.output,
                          sizeof(probe.output), &probe.written);
        if (result.status != BSR_OK) {
            return fail("bsr_step", (int)result.status,
                        (int)result.executor_status);
        }
        if (i == 2u) {
            if (probe.written != 2u ||
                memcmp(probe.output, "5\n", 2u) != 0) {
                return fail("PRINT_B", (int)probe.written, -1);
            }
            /* Publish the REAL interpreter's returned bytes, not a fake 5. */
            printf("J0.25 BASIC_OUTPUT: %.*s", (int)probe.written,
                   (const char *)probe.output);
        } else if (probe.written != 0u) {
            return fail("unexpected_output", (int)i, (int)probe.written);
        }
    }
    if (!check_value_five()) {
        return 0;
    }
    probe.written = 123u;
    result = bsr_step(&probe.runtime, probe.output,
                      sizeof(probe.output), &probe.written);
    if (result.status != BSR_END ||
        result.executor_status != BE_END ||
        probe.runtime.state != BSR_IDLE || probe.written != 123u) {
        return fail("END_stop", (int)result.status,
                    (int)result.executor_status);
    }
    return 1;
}

void app_main(void)
{
    int success;
    printf("J0.25 ESP_IDF=%s TARGET=esp32 STATE=ON_DEVICE_UNVERIFIED_IN_CI\n",
           esp_get_idf_version());
    printf("J0.25 STATIC_PROBE_BYTES=%zu ABI_POINTER_BYTES=%" PRIu32 "\n",
           sizeof(probe), loco_probe_abi_sizes[1]);
    hardware_memory_snapshot("before");
    success = demo_run();
    hardware_memory_snapshot("after");
    printf("J0.25 %s\n",
           success ? "ON_DEVICE_VERIFIED PASS" : "ON_DEVICE_VERIFIED FAIL");
}
