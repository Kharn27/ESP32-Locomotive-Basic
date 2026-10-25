/* J0.9: Linux-only terminal adapter. The BASIC engine remains in core/. */
#include "basic_session_runtime.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define CLI_PROGRAM_CAPACITY 32768u
#define CLI_INPUT_CAPACITY 512u
#define CLI_TEMPORARY_CAPACITY 2048u
#define CLI_OUTPUT_CAPACITY 131072u
#define CLI_MAX_STEPS 100u
#define CLI_VARIABLE_CAPACITY 64u

typedef struct {
    BasicProgram program;
    BasicSessionRuntime runtime;
    BasicVariableStore variables;
    BasicVariableEntry variable_entries[CLI_VARIABLE_CAPACITY];
    uint8_t storage[CLI_PROGRAM_CAPACITY];
    uint8_t input[CLI_INPUT_CAPACITY];
    uint8_t temporary[CLI_TEMPORARY_CAPACITY];
    uint8_t output[CLI_OUTPUT_CAPACITY];
    size_t written;
} Cli;

typedef enum {
    INPUT_LINE,
    INPUT_EOF,
    INPUT_TOO_LONG,
    INPUT_ERROR
} InputStatus;

#define STATUS_CASE(value) case value: return #value

static const char *bsr_name(BSRStatus status)
{
    switch (status) {
        STATUS_CASE(BSR_OK);
        STATUS_CASE(BSR_END);
        STATUS_CASE(BSR_NOT_RUNNING);
        STATUS_CASE(BSR_BUSY);
        STATUS_CASE(BSR_INVALID_ARGUMENT);
        STATUS_CASE(BSR_OVERLAP);
        STATUS_CASE(BSR_SESSION_ERROR);
        STATUS_CASE(BSR_EXECUTOR_ERROR);
        default: return "BSR_UNKNOWN";
    }
}

static const char *bs_name(BSStatus status)
{
    switch (status) {
        STATUS_CASE(BS_OK);
        STATUS_CASE(BS_NOT_FOUND);
        STATUS_CASE(BS_INVALID_ARGUMENT);
        STATUS_CASE(BS_OVERLAP);
        STATUS_CASE(BS_INVALID_LINE_NUMBER);
        STATUS_CASE(BS_MALFORMED_INPUT);
        STATUS_CASE(BS_MULTIPLE_DIRECT);
        STATUS_CASE(BS_UNSUPPORTED_DIRECT);
        STATUS_CASE(BS_TOKENIZER_ERROR);
        STATUS_CASE(BS_PROGRAM_ERROR);
        STATUS_CASE(BS_LISTING_ERROR);
        default: return "BS_UNKNOWN";
    }
}

static const char *bt_name(BTStatus status)
{
    switch (status) {
        STATUS_CASE(BT_OK);
        STATUS_CASE(BT_INVALID_ARGUMENT);
        STATUS_CASE(BT_NO_SPACE);
        STATUS_CASE(BT_NUMBER_OUT_OF_RANGE);
        STATUS_CASE(BT_UNSUPPORTED_CONSTRUCT);
        STATUS_CASE(BT_MALFORMED_INPUT);
        default: return "BT_UNKNOWN";
    }
}

static const char *bp_name(BPStatus status)
{
    switch (status) {
        STATUS_CASE(BP_OK);
        STATUS_CASE(BP_END);
        STATUS_CASE(BP_NOT_FOUND);
        STATUS_CASE(BP_INVALID_ARGUMENT);
        STATUS_CASE(BP_INVALID_LINE_NUMBER);
        STATUS_CASE(BP_BAD_FORMAT);
        STATUS_CASE(BP_TRUNCATED);
        STATUS_CASE(BP_NO_SPACE);
        STATUS_CASE(BP_OVERFLOW);
        STATUS_CASE(BP_OVERLAP);
        default: return "BP_UNKNOWN";
    }
}

static const char *bl_name(BLStatus status)
{
    switch (status) {
        STATUS_CASE(BL_OK);
        STATUS_CASE(BL_INVALID_ARGUMENT);
        STATUS_CASE(BL_NO_SPACE);
        STATUS_CASE(BL_OVERFLOW);
        STATUS_CASE(BL_OVERLAP);
        STATUS_CASE(BL_UNKNOWN_TOKEN);
        STATUS_CASE(BL_TRUNCATED);
        STATUS_CASE(BL_BAD_SEQUENCE);
        STATUS_CASE(BL_BAD_PROGRAM);
        default: return "BL_UNKNOWN";
    }
}

static const char *be_name(BEStatus status)
{
    switch (status) {
        STATUS_CASE(BE_OK);
        STATUS_CASE(BE_END);
        STATUS_CASE(BE_INVALID_ARGUMENT);
        STATUS_CASE(BE_BAD_PROGRAM);
        STATUS_CASE(BE_TRUNCATED);
        STATUS_CASE(BE_BAD_SEQUENCE);
        STATUS_CASE(BE_UNKNOWN_TOKEN);
        STATUS_CASE(BE_UNSUPPORTED);
        STATUS_CASE(BE_MISSING_TARGET);
        STATUS_CASE(BE_NO_SPACE);
        STATUS_CASE(BE_OVERLAP);
        STATUS_CASE(BE_STORE_FULL);
        STATUS_CASE(BE_INVALID_STORE);
        STATUS_CASE(BE_INVALID_KEY);
        STATUS_CASE(BE_INVALID_TYPE);
        STATUS_CASE(BE_VARIABLE_NOT_FOUND);
        STATUS_CASE(BE_INTEGER_OVERFLOW);
        default: return "BE_UNKNOWN";
    }
}

#undef STATUS_CASE

static void report_error(BSRResult result)
{
    fprintf(stderr, "[cli:error] %s %s %s %s %s %s\n",
            bsr_name(result.status), bs_name(result.session.status),
            bt_name(result.session.tokenizer_status),
            bp_name(result.session.program_status),
            bl_name(result.session.listing_status),
            be_name(result.executor_status));
}

/* Read one complete physical line, draining excess bytes before returning.
 * No truncated prefix is ever submitted to BASIC. */
static InputStatus read_input(uint8_t *buffer, size_t capacity, size_t *length)
{
    size_t count = 0u;
    int saw_byte = 0;
    int overflow = 0;
    int c;

    for (;;) {
        c = fgetc(stdin);
        if (c == EOF) {
            if (ferror(stdin)) {
                return INPUT_ERROR;
            }
            if (!saw_byte) {
                return INPUT_EOF;
            }
            break; /* Last unterminated line at EOF is still processed. */
        }
        saw_byte = 1;
        if (c == '\n') {
            break;
        }
        if (count < capacity) {
            buffer[count++] = (uint8_t)c;
        } else {
            overflow = 1;
        }
    }
    if (overflow) {
        return INPUT_TOO_LONG;
    }
    if (count != 0u && buffer[count - 1u] == (uint8_t)'\r') {
        --count; /* Accept CRLF, but never pass CR into the core. */
    }
    *length = count;
    return INPUT_LINE;
}

static uint8_t upper_ascii(uint8_t c)
{
    if (c >= (uint8_t)'a' && c <= (uint8_t)'z') {
        return (uint8_t)(c - (uint8_t)'a' + (uint8_t)'A');
    }
    return c;
}

static void trim_spaces(const uint8_t *text, size_t *begin, size_t *end)
{
    while (*begin < *end && text[*begin] == (uint8_t)' ') {
        ++*begin;
    }
    while (*end > *begin && text[*end - 1u] == (uint8_t)' ') {
        --*end;
    }
}

static int is_basic_command(const uint8_t *text, size_t length,
                            const char *command)
{
    size_t begin = 0u, end = length, i;
    trim_spaces(text, &begin, &end);
    for (i = 0u; command[i] != '\0'; ++i) {
        if (begin + i >= end ||
            upper_ascii(text[begin + i]) != (uint8_t)command[i]) {
            return 0;
        }
    }
    return begin + i == end;
}

static int is_meta(const uint8_t *text, size_t length, const char *command)
{
    size_t size = strlen(command);
    return length == size && memcmp(text, command, size) == 0;
}

/* Strict unsigned decimal with a fixed bound: no wrap on long inputs.
 * A missing argument means one step, as specified by :step. */
static int parse_step_count(const uint8_t *text, size_t length, size_t *count)
{
    size_t i = 5u;
    size_t value = 0u;
    int saw_digit = 0;

    if (length < 5u || memcmp(text, ":step", 5u) != 0) {
        return 0;
    }
    if (length == 5u) {
        *count = 1u;
        return 1;
    }
    if (text[i] != (uint8_t)' ') {
        return 0;
    }
    while (i < length && text[i] == (uint8_t)' ') {
        ++i;
    }
    while (i < length && text[i] >= (uint8_t)'0' &&
           text[i] <= (uint8_t)'9') {
        size_t digit = (size_t)(text[i] - (uint8_t)'0');
        if (value > (CLI_MAX_STEPS - digit) / 10u) {
            return 0;
        }
        value = value * 10u + digit;
        saw_digit = 1;
        ++i;
    }
    while (i < length && text[i] == (uint8_t)' ') {
        ++i;
    }
    if (!saw_digit || i != length || value == 0u) {
        return 0;
    }
    *count = value;
    return 1;
}

static int emit_basic(const Cli *cli)
{
    if (cli->written != 0u &&
        fwrite(cli->output, 1u, cli->written, stdout) != cli->written) {
        fputs("[cli:error] OUTPUT_IO\n", stderr);
        return 1;
    }
    if (fflush(stdout) != 0) {
        fputs("[cli:error] OUTPUT_IO\n", stderr);
        return 1;
    }
    return 0;
}

/* Return 1 only for a fatal host I/O error. */
static int do_steps(Cli *cli, size_t limit)
{
    size_t completed = 0u;
    while (completed < limit) {
        BSRResult r = bsr_step(&cli->runtime, cli->output,
                               sizeof(cli->output), &cli->written);
        if (r.status != BSR_OK) {
            if (completed != 0u) {
                fprintf(stderr, "[cli] STEPPED %zu\n", completed);
            }
            if (r.status == BSR_END) {
                fputs("[cli] END\n", stderr);
            } else {
                report_error(r);
            }
            return 0;
        }
        ++completed;
        /* BE_END and failures retain stale written; only BSR_OK emits. */
        if (emit_basic(cli) != 0) {
            return 1;
        }
    }
    fprintf(stderr, "[cli] STEPPED %zu\n", completed);
    return 0;
}

static int handle_meta(Cli *cli, const uint8_t *text, size_t length,
                       int *quit)
{
    size_t count = 0u;

    if (is_meta(text, length, ":help")) {
        fputs("[cli] :help :step [N=1..100] :stop :quit\n"
              "[cli] BASIC: numbered lines, LIST, NEW, RUN\n"
              "[cli] stdout=BASIC bytes; stderr=host messages\n", stderr);
    } else if (is_meta(text, length, ":quit")) {
        BSRResult r = bsr_stop(&cli->runtime);
        if (r.status != BSR_OK) {
            report_error(r);
            return 1;
        }
        fputs("[cli] BYE\n", stderr);
        *quit = 1;
    } else if (is_meta(text, length, ":stop")) {
        BSRResult r = bsr_stop(&cli->runtime);
        if (r.status != BSR_OK) {
            report_error(r);
        } else {
            fputs("[cli] STOPPED\n", stderr);
        }
    } else if (length >= 5u && memcmp(text, ":step", 5u) == 0 &&
               (length == 5u || text[5] == (uint8_t)' ')) {
        if (!parse_step_count(text, length, &count)) {
            fputs("[cli:error] INVALID_STEP (expected 1..100)\n", stderr);
            return 0;
        }
        return do_steps(cli, count);
    } else {
        fputs("[cli:error] UNKNOWN_META\n", stderr);
    }
    return 0;
}

int main(void)
{
    Cli cli;
    BPStatus initialized = bp_init(&cli.program, cli.storage,
                                   sizeof(cli.storage));
    int interactive = isatty(STDIN_FILENO) && isatty(STDOUT_FILENO);
    int quit = 0;

    if (initialized != BP_OK) {
        fprintf(stderr, "[cli:error] INIT %s\n", bp_name(initialized));
        return 1;
    }
    if (bvs_init(&cli.variables, cli.variable_entries,
                 CLI_VARIABLE_CAPACITY) != BVS_OK) {
        fputs("[cli:error] VARIABLE_INIT\n", stderr);
        return 1;
    }
    {
        BSRResult r = bsr_init_with_store(&cli.runtime, &cli.program,
                                           &cli.variables);
        if (r.status != BSR_OK) {
            report_error(r);
            return 1;
        }
    }
    fputs("[cli] J0.9 host CLI (:help)\n", stderr);

    while (!quit) {
        size_t length = 0u;
        size_t begin = 0u;
        size_t end;
        InputStatus input_status;

        if (interactive) {
            fputs("basic> ", stderr);
            fflush(stderr);
        }
        input_status = read_input(cli.input, sizeof(cli.input), &length);
        if (input_status == INPUT_EOF) {
            (void)bsr_stop(&cli.runtime);
            fputs("[cli] EOF\n", stderr);
            break;
        }
        if (input_status == INPUT_ERROR) {
            fputs("[cli:error] INPUT_IO\n", stderr);
            return 1;
        }
        if (input_status == INPUT_TOO_LONG) {
            fputs("[cli:error] INPUT_TOO_LONG\n", stderr);
            continue;
        }
        end = length;
        trim_spaces(cli.input, &begin, &end);
        if (begin < end && cli.input[begin] == (uint8_t)':') {
            if (handle_meta(&cli, cli.input + begin, end - begin, &quit) != 0) {
                return 1;
            }
        } else {
            BSRResult r = bsr_submit(&cli.runtime, cli.input, length,
                                     cli.temporary, sizeof(cli.temporary),
                                     cli.output, sizeof(cli.output),
                                     &cli.written);
            if (r.status != BSR_OK) {
                report_error(r);
                continue;
            }
            if (emit_basic(&cli) != 0) {
                return 1;
            }
            if (is_basic_command(cli.input, length, "RUN")) {
                fputs("[cli] RUNNING\n", stderr);
            } else if (is_basic_command(cli.input, length, "LIST")) {
                fputs("[cli] LIST\n", stderr);
            } else {
                fputs("[cli] OK\n", stderr);
            }
        }
    }
    return 0;
}
