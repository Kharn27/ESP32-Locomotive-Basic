/* J1.25-B2: CPC RUN printer oracle original/repeat, closed INTEGER scope.
 * Source and sealed captures are read-only. Native errors are HOST codes,
 * never inferred CPC ERR/ERL or TFT diagnostics. */
#include "basic_session_runtime.h"
#include "basic_tokenizer.h"
#include "basic_variable_binding.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)
enum { CAP = 2048 };
static const char *const positives[] = {
    "ONE_INTEGER", "TWO_INTEGERS", "NEXT_DATA_LINE",
    "JUMP_OVER_DATA", "RESTORE_BEGIN", "RESTORE_TARGET", "DATA_COLON"
};
static const char *const sessions[] = {"original", "repeat"};
static const char *const numeric_expected[] = {
    " 1 \\n", " 1 \\n 2 \\n", " 4 \\n 5 \\n",
    " 7 \\n", " 6 \\n 6 \\n", " 9 \\n", "BEFORE\\n 1 \\n"
};

static int file_bytes(const char *path, uint8_t *bytes, size_t cap,
                      size_t *length)
{
    FILE *f = fopen(path, "rb");
    int tail;
    size_t n;
    if (f == NULL) { perror(path); return 1; }
    n = fread(bytes, 1u, cap, f);
    tail = fgetc(f);
    if (ferror(f) || tail != EOF || fclose(f) != 0) return 1;
    *length = n;
    return 0;
}

static int fill_program(const uint8_t *source, size_t n, BasicProgram *program)
{
    size_t p = 0u;
    while (p < n) {
        size_t start = p, i;
        unsigned int line = 0u;
        uint8_t body[CAP];
        size_t body_n = 0u;
        while (p < n && source[p] != (uint8_t)'\\n') ++p;
        if (p == n) return 1;
        i = start;
        if (i == p) return 1;
        while (i < p && source[i] >= (uint8_t)'0' &&
               source[i] <= (uint8_t)'9') {
            line = line * 10u + (unsigned int)(source[i++] - (uint8_t)'0');
            if (line > 65535u) return 1;
        }
        if (i >= p || source[i++] != (uint8_t)' ') return 1;
        if (bt_tokenize(source + i, p - i, body, sizeof(body), &body_n)
            != BT_OK) return 1;
        if (bp_put(program, (uint16_t)line, body, body_n) != BP_OK) return 1;
        ++p;
    }
    return 0;
}

/* Keep all content and spacing, normalize only captured CPC CRLF -> LF.
 * The oracle RUN channel includes independently appended ERR/ERL and LIST
 * after J125_DIAG_BEGIN; these MUST NOT be treated as native RUN output. */
static int cpc_run_prefix(const uint8_t *src, size_t n,
                          uint8_t *out, size_t cap, size_t *len,
                          int exhausted)
{
    static const char marker[] = "J125_DIAG_BEGIN\\r\\n";
    size_t i, stop = n, k = 0u, diag;
    for (i = 0u; i + sizeof(marker)-1u <= n; ++i) {
        if (memcmp(src + i, marker, sizeof(marker)-1u) == 0) {
            stop = i;
            break;
        }
    }
    if (stop == n) return 1;
    diag = stop + sizeof(marker)-1u;
    if (exhausted) {
        static const char numbers[] = " 4 \\r\\n 40 \\r\\n";
        if (n - diag < sizeof(numbers)-1u ||
            memcmp(src + diag, numbers, sizeof(numbers)-1u) != 0)
            return 1;
    } else {
        static const char zeros[] = " 0 \\r\\n 0 \\r\\n";
        if (n - diag < sizeof(zeros)-1u ||
            memcmp(src + diag, zeros, sizeof(zeros)-1u) != 0)
            return 1;
    }
    for (i = 0u; i < stop; ++i) {
        if (src[i] == (uint8_t)'\\r') {
            if (i+1u == stop || src[i+1u] != (uint8_t)'\\n') return 1;
            continue;
        }
        if (k >= cap) return 1;
        out[k++] = src[i];
    }
    *len = k;
    return 0;
}

static int verify_case(const char *root, const char *name,
                       const char *session, const char *expected,
                       int exhausted)
{
    char path[512];
    uint8_t source[CAP], cpc_raw[CAP], cpc_out[CAP];
    uint8_t mem[CAP], output[128], scratch[128], native[CAP];
    BasicProgram bp;
    BasicSessionRuntime runtime;
    BasicVariableStore store;
    BasicVariableEntry entries[4];
    size_t source_n, cpc_n, cpc_out_n, native_n = 0u;
    size_t written = 818u, steps = 0u;
    int n, error_seen = 0;
    BSRResult result;
    n = snprintf(path, sizeof(path), "%s/tests/oracles/inputs/j1_25_a/%s.bas",
                 root, name);
    CHECK(n > 0 && (size_t)n < sizeof(path));
    CHECK(file_bytes(path, source, sizeof(source), &source_n) == 0);
    n = snprintf(path, sizeof(path),
                 "%s/tests/fixtures/cpc6128/j1_25_a_data_read_restore/%s/%s/run/printer.dat",
                 root, session, name);
    CHECK(n > 0 && (size_t)n < sizeof(path));
    CHECK(file_bytes(path, cpc_raw, sizeof(cpc_raw), &cpc_n) == 0);
    CHECK(cpc_run_prefix(cpc_raw, cpc_n, cpc_out, sizeof(cpc_out),
                         &cpc_out_n, exhausted) == 0);
    CHECK(strlen(expected) == cpc_out_n &&
          memcmp(expected, cpc_out, cpc_out_n) == 0);
    CHECK(bp_init(&bp, mem, sizeof(mem)) == BP_OK);
    CHECK(fill_program(source, source_n, &bp) == 0);
    memset(entries, 0, sizeof(entries));
    CHECK(bvs_init(&store, entries, 4u) == BVS_OK);
    CHECK(bsr_init_with_store(&runtime, &bp, &store).status == BSR_OK);
    result = bsr_submit(&runtime, (const uint8_t *)"RUN", 3u,
                        scratch, sizeof(scratch), output, sizeof(output),
                        &written);
    CHECK(result.status == BSR_OK && written == 0u);
    while (steps++ < 40u) {
        BasicSessionRuntime old_runtime;
        BasicVariableEntry old_entries[4];
        uint8_t frozen[128];
        size_t old_written;
        memset(output, 0xa5, sizeof(output));
        memcpy(frozen, output, sizeof(frozen));
        written = 818u;
        old_written = written;
        old_runtime = runtime;
        memcpy(old_entries, entries, sizeof(entries));
        result = bsr_step(&runtime, output, sizeof(output), &written);
        if (result.status == BSR_END) {
            CHECK(!exhausted);
            CHECK(memcmp(output, frozen, sizeof(output)) == 0);
            break;
        }
        if (result.status == BSR_EXECUTOR_ERROR) {
            size_t cursor;
            BasicProgramLine line;
            CHECK(exhausted && !error_seen);
            CHECK(result.executor_status == BE_DATA_EXHAUSTED);
            CHECK(runtime.state == BSR_RUNNING);
            CHECK(memcmp(&runtime, &old_runtime, sizeof(runtime)) == 0);
            CHECK(memcmp(entries, old_entries, sizeof(entries)) == 0);
            CHECK(memcmp(output, frozen, sizeof(output)) == 0);
            CHECK(written == old_written);
            cursor = runtime.executor.cursor;
            CHECK(bp_next(&bp, &cursor, &line) == BP_OK);
            CHECK(line.number == 40u); /* host cause location, not CPC ERL */
            error_seen = 1;
            /* Deterministic retry: no output, cursor or variable mutation. */
            result = bsr_step(&runtime, output, sizeof(output), &written);
            CHECK(result.status == BSR_EXECUTOR_ERROR &&
                  result.executor_status == BE_DATA_EXHAUSTED);
            CHECK(memcmp(&runtime, &old_runtime, sizeof(runtime)) == 0);
            CHECK(memcmp(entries, old_entries, sizeof(entries)) == 0);
            CHECK(written == old_written);
            CHECK(memcmp(output, frozen, sizeof(output)) == 0);
            break;
        }
        CHECK(result.status == BSR_OK);
        CHECK(native_n + written <= sizeof(native));
        memcpy(native + native_n, output, written);
        native_n += written;
    }
    CHECK(steps < 40u && error_seen == exhausted);
    CHECK(native_n == cpc_out_n);
    CHECK(memcmp(native, cpc_out, native_n) == 0);
    if (exhausted) {
        CHECK(store.count == 1u && entries[0].value.data.integer == 1);
        CHECK(bsr_stop(&runtime).status == BSR_OK);
        CHECK(runtime.executor.data_cursor == 0u &&
              runtime.executor.data_item_offset == 0u);
    } else {
        CHECK(store.count >= 1u);
    }
    printf("B2 %-16s %-8s CPC_RUN_MATCH=%zu ERROR=%d\\n",
           name, session, native_n, error_seen);
    return 0;
}

static int negative_case(const uint8_t *data, size_t data_length,
                         const uint8_t *read, size_t read_length,
                         BEStatus expected, size_t capacity, int first_line)
{
    uint8_t storage[256], output[32], frozen[32];
    uint8_t canary[2] = {0x63u, 0x91u};
    BasicProgram program;
    BasicExecutor executor, before;
    BasicVariableStore store;
    BasicVariableEntry entries[2], snapshot[2];
    size_t written = 901u;
    BEStatus status;
    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    CHECK(bp_put(&program, 10u, data, data_length) == BP_OK);
    if (read != NULL)
        CHECK(bp_put(&program, 20u, read, read_length) == BP_OK);
    memset(entries, 0xa6, sizeof(entries));
    CHECK(bvs_init(&store, entries, capacity) == BVS_OK);
    CHECK(be_init_with_store(&executor, &program, &store) == BE_OK);
    if (!first_line) {
        CHECK(be_step(&executor, output, sizeof(output), &written) == BE_OK);
    }
    before = executor;
    memcpy(snapshot, entries, sizeof(entries));
    memset(output, 0x5c, sizeof(output));
    memcpy(frozen, output, sizeof(output));
    written = 901u;
    status = be_step(&executor, output, sizeof(output), &written);
    CHECK(status == expected);
    CHECK(memcmp(&executor, &before, sizeof(executor)) == 0);
    CHECK(memcmp(entries, snapshot, sizeof(entries)) == 0);
    CHECK(memcmp(output, frozen, sizeof(output)) == 0);
    CHECK(written == 901u);
    CHECK(canary[0] == 0x63u && canary[1] == 0x91u);
    return 0;
}

static int negatives(void)
{
    uint8_t body[80], read[80], bad[80];
    size_t n = 0u, r = 0u;
    static const uint8_t malformed[] = {0x8cu, (uint8_t)' ',
                                         (uint8_t)'1', (uint8_t)','};
    CHECK(bt_tokenize((const uint8_t *)"DATA 1,2", 8u,
                      body, sizeof(body), &n) == BT_OK);
    CHECK(bt_tokenize((const uint8_t *)"READ A%,B%", 10u,
                      read, sizeof(read), &r) == BT_OK);
    CHECK(negative_case(body, n, read, r, BE_STORE_FULL, 1u, 0) == 0);
    CHECK(negative_case(malformed, sizeof(malformed), NULL, 0u,
                        BE_BAD_SEQUENCE, 2u, 1) == 0);
    /* READ without a preceding DATA: explicit host exhaustion. */
    CHECK(bt_tokenize((const uint8_t *)"READ A%", 7u,
                      body, sizeof(body), &n) == BT_OK);
    CHECK(negative_case(body, n, NULL, 0u, BE_DATA_EXHAUSTED,
                        2u, 1) == 0);
    /* REAL/STRING refs do not silently become INTEGER data targets. */
    memcpy(bad, body, n);
    bad[2] = 0x03u;
    CHECK(negative_case(bad, n, NULL, 0u, BE_UNSUPPORTED,
                        2u, 1) == 0);
    CHECK(bt_tokenize((const uint8_t *)"RESTORE 100", 11u,
                      body, sizeof(body), &n) == BT_OK);
    CHECK(negative_case(body, n, NULL, 0u, BE_MISSING_TARGET,
                        2u, 1) == 0);
    return 0;
}

int main(int argc, char **argv)
{
    size_t i, j;
    CHECK(argc == 2);
    CHECK(negatives() == 0);
    for (i = 0u; i < sizeof(positives)/sizeof(positives[0]); ++i) {
        for (j = 0u; j < sizeof(sessions)/sizeof(sessions[0]); ++j) {
            CHECK(verify_case(argv[1], positives[i], sessions[j],
                              numeric_expected[i], 0) == 0);
        }
    }
    for (j = 0u; j < sizeof(sessions)/sizeof(sessions[0]); ++j) {
        CHECK(verify_case(argv[1], "DATA_EXHAUSTED", sessions[j],
                          " 1 \\n", 1) == 0);
    }
    puts("J1.25-B2 7/7 positive x2 and DATA_EXHAUSTED x2 CPC RUN MATCH");
    return 0;
}
