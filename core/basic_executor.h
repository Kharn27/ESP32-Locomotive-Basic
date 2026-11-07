#ifndef BASIC_EXECUTOR_H
#define BASIC_EXECUTOR_H

#include <stddef.h>
#include <stdint.h>
#include "basic_program.h"
#include "basic_variable_store.h"

/* J0.7 host diagnostics, not Locomotive BASIC error codes. */
typedef enum {
    BE_OK = 0,
    BE_END,
    BE_INVALID_ARGUMENT,
    BE_BAD_PROGRAM,
    BE_TRUNCATED,
    BE_BAD_SEQUENCE,
    BE_UNKNOWN_TOKEN,
    BE_UNSUPPORTED,
    BE_MISSING_TARGET,
    BE_NO_SPACE,
    BE_OVERLAP,
    BE_STORE_FULL,
    BE_INVALID_STORE,
    BE_INVALID_KEY,
    BE_INVALID_TYPE,
    BE_VARIABLE_NOT_FOUND, /* Internal diagnostic, not a CPC error code. */
    BE_INTEGER_OVERFLOW, /* Internal range error; not a CPC numeric code. */
    BE_DIVISION_BY_ZERO, /* Internal error, separate from CPC ERR=11. */
    BE_RETURN_WITHOUT_GOSUB, /* Host diagnostic, not CPC ERR=3. */
    BE_CALL_STACK_FULL, /* Bounded host stack, not a measured CPC limit. */
    BE_NEXT_WITHOUT_FOR,
    BE_NEXT_VARIABLE_MISMATCH,
    BE_FOR_STACK_FULL,
    BE_FOR_WITHOUT_NEXT,
    BE_INVALID_PEN, /* host policy for CPC 16/-1, never CPC ERR=5 */
    BE_EVENT_RECEIVER_REQUIRED,
    BE_NO_EVENT_SPACE,
    BE_INVALID_INK, /* only four measured CPC boundaries, host diagnostic */
    BE_INVALID_PAPER, /* J1.19-A: host cause, NOT CPC numeric ERR=5 */
    BE_INVALID_LOCATE, /* J1.23-A observed rejected 0/-1 coordinate, CPC ERR=5 */
    BE_INVALID_BORDER, /* J1.23-A rejected -1 ink, CPC ERR=5 */
    BE_OPERAND_MISSING, /* J1.23-A BORDER 1, observed CPC ERR=22 */
    BE_DIAG_CONTRADICTORY, /* CPC screen vs ERR probe contradict, WEND 1 too */
    BE_WEND_WITHOUT_WHILE, /* Host cause; CPC orphan WEND screen/ERR30 */
    BE_WHILE_WITHOUT_WEND, /* Host cause; CPC WEND missing screen/ERR29 */
    BE_WHILE_OPERAND_MISSING, /* Host cause; CPC operand missing screen/ERR22 */
    BE_WHILE_CONDITION_INVALID, /* B2 non-oracled INTEGER expression */
    BE_WHILE_STACK_FULL, /* Host capacity 8, NOT a CPC ROM limit */
    BE_DATA_EXHAUSTED /* J1.25-B2 host cause: no remaining INTEGER DATA; NOT CPC ERR=4 */
} BEStatus;

/* Typed, caller-owned video event, never encoded in PRINT.
 * print_offset counts PRINT bytes preceding the event within this step;
 * the caller can replay ordered PRINT slices and events.
 * pen is a logical CPC argument, NOT a MODE renderer palette index.
 * SET_TEXT_PAPER has a tagged, logical CPC index in the existing ink byte;
 * pen remains ZERO, so old PEN payloads are never reinterpreted.
 * The event type, not the payload field name, determines its semantics.
 * SET_INK changes logical palette mapping; the renderer may need to
 * recolour already-drawn pixels, not just future PRINT bytes.
 * CLS clears a video text domain at print_offset, never a PRINT escape.
 * No RGB table, colour rendering, or blinking is provided by core.
 * The three historical fields retain their offsets and initializer order.
 * Existing ABI remains unchanged: no new fields or shifted offsets.
 * The TEXT_PAPER type deliberately uses the existing logical-index payload;
 * HW4 consumers must reject unknown types during preflight.
 * J1.23-C1 payload contracts without ABI/offset changes:
 *   TEXT_CURSOR: pen=x (1-based), ink=y (1-based), colour=0.
 *   SET_BORDER: pen=border1 (CPC 0..27 in witnessed cases),
 *               ink=border2 if supplied, otherwise 0;
 *               colour=1 iff the second argument was supplied, else 0.
 * Only the tagged type determines these meanings; PEN/INK/PAPER/CLS
 * payloads and positional initializers remain unchanged. No TFT projection. */
typedef enum {
    BE_VIDEO_SET_TEXT_PEN = 1,
    BE_VIDEO_SET_INK = 2,
    BE_VIDEO_CLEAR_TEXT = 3, /* CLS 8A: text clear; no PRINT bytes */
    BE_VIDEO_SET_TEXT_PAPER = 4, /* PAPER BA: logical CPC text background */
    BE_VIDEO_SET_TEXT_CURSOR = 5, /* LOCATE A9: logical CPC 1-based x,y */
    BE_VIDEO_SET_BORDER = 6 /* BORDER 82: logical CPC ink(s), no RGB */
} BEVideoEventType;
typedef struct {
    BEVideoEventType type;
    uint8_t pen; /* historical PEN argument; zero for SET_INK */
    size_t print_offset; /* original third field: preserve positional initializers */
    uint8_t ink; /* SET_INK: palette index; SET_TEXT_PAPER: logical paper */
    uint8_t colour; /* CPC colour code, NOT an RGB or renderer value */
} BEVideoEvent;

/* J1.11-B: fixed per-executor call stack, no heap and no C recursion.
 * Eight nested GOSUB frames are supported; this is NOT a CPC ROM limit.
 * cursor is a program record offset; statement_offset is a body-relative
 * continuation after CPC token 01 (colon), or zero at a new line. */
#define BE_GOSUB_STACK_CAPACITY 8u
typedef struct {
    size_t cursor;
    size_t statement_offset;
} BECallFrame;

/* J1.12-B2: bounded FOR/NEXT INTEGER execution, 8 per-executor frames,
 * separate from GOSUB's 8 frames. Never assume this is a CPC ROM depth.
 * The NEXT structure is prechecked at FOR, before loop-body output, for the
 * specific sealed CPC mismatch case. STEP 0 is unsupported. NEXT arithmetic
 * widens to int32 and fails atomically with BE_INTEGER_OVERFLOW if the new
 * value leaves int16; this is host policy, not observed CPC semantics.
 * Cursor/stack/variable/output changes commit only after step prevalidation. */
#define BE_FOR_STACK_CAPACITY 8u
typedef struct {
    BasicVariableKey key;
    int16_t limit;
    int16_t step;
    size_t loop_cursor;
    size_t loop_statement;
    size_t after_cursor;
    size_t after_statement;
} BEForFrame;

/* B2: eight WHILE/WEND frames independent of GOSUB and FOR. The header
 * and closing WEND are statement addresses inside immutable CPC records.
 * Capacity 8 is an explicit caller-owned host bound, not a CPC ROM fact. */
#define BE_WHILE_STACK_CAPACITY 8u
typedef struct {
    size_t header_cursor;
    size_t header_statement;
    size_t wend_cursor;
    size_t wend_statement;
    size_t after_cursor;
    size_t after_statement;
} BEWhileFrame;

typedef struct {
    const BasicProgram *program; /* Borrowed; immutable through execution. */
    size_t cursor;               /* Offset of next record (or sentinel). */
    size_t statement_offset;     /* Position inside the current line body. */
    size_t call_depth;
    BECallFrame call_stack[BE_GOSUB_STACK_CAPACITY];
    size_t for_depth;
    BEForFrame for_stack[BE_FOR_STACK_CAPACITY];
    size_t while_depth;
    BEWhileFrame while_stack[BE_WHILE_STACK_CAPACITY];
    BasicVariableStore *variables; /* Optional borrowed caller-owned store. */
    /* J1.25-B2 retains this ABI layout. On the closed INTEGER DATA corpus,
     * the final WHILE frame's after_cursor/after_statement are the DATA
     * record/item offsets. DATA and WHILE are rejected in the same program;
     * WHILE-only programs retain all 8 frame slots and prior semantics.
     * No pointer into editable program storage is retained. */
} BasicExecutor;

/* Validate a program and reset execution to its first line.
 * On failure executor remains unmodified. Executor, program metadata and
 * program storage must be disjoint, including unused storage capacity.
 */
BEStatus be_init(BasicExecutor *executor, const BasicProgram *program);
/* Explicit store variant. Does not clear the store; legacy be_init has no
 * store and continues returning BE_UNSUPPORTED for INTEGER assignment. */
BEStatus be_init_with_store(BasicExecutor *executor, const BasicProgram *program,
                            BasicVariableStore *variables);

/* With a store, standalone INTEGER assignments accept a 0..32767
 * immediate (CPC 0E..17, 19, 1A), with optional CPC unary-minus F5,
 * plus only -32768 via exact F5 1F 00 00 00 00 90 (REAL5 payload),
 * or exactly one explicit INTEGER source reference followed by binary
 * CPC F4 (+), F5 (-), F6 (*), F9 (\\) or FB (MOD), then one unsigned
 * decimal byte literal (0..255). J1.7-B additionally permits
 * F4 (+), J1.8-B binary F5 (-), and J1.9-B F6/F9/FB followed
 * by a SECOND explicit INTEGER reference; both sources are read and the
 * result is checked in int32_t before a single successful commit.
 * Unary F5 and binary F5 are distinguished by operand context.
 * A non-representable sum, difference or product returns BE_INTEGER_OVERFLOW.
 * F9 division truncates toward zero; a zero divisor returns the separate
 * BE_DIVISION_BY_ZERO before any division or mutation of the destination.
  * FB MOD uses the C99 int32_t remainder (dividend sign), with the same
  * zero-divisor guard; no floating point and no generic expressions.
 * These are internal status names, NOT historic CPC ERR numeric codes.
 *
 * With a store, PRINT reads existing explicit INTEGER (%) scalars only.
 * Missing variables return BE_VARIABLE_NOT_FOUND; without a store the
 * legacy API still returns BE_UNSUPPORTED. Numeric output is prototype
 * signed decimal + LF, not CPC PRINT formatting.
 *
 * One line can also contain PRINT:I%...:NEXT I%; successful FOR and NEXT
 * move the cursor to a continuation (possibly in the same stored line).
 * A FOR prechecks the matching NEXT before permitting body output, so a
 * structurally mismatched variable cannot partially print prior iterations.
 * Execute at most ONE numbered line. END commits the reached prefix's output
 * and moves the cursor to the program sentinel; the NEXT be_step returns
 * BE_END. This is the host step protocol, not CPC console timing.
 * BE_OK commits its output, cursor and (when applicable) one stack transition.
 * Output is raw bytes, no NUL, one LF per PRINT. On BE_OK *written is the
 * number of bytes emitted (possibly zero). BE_END and every error preserve
 * the entire output buffer, *written and executor, including the cursor.
 * All pointers are required, even for zero output capacity. Output (its full
 * capacity), written, executor, program and program storage must be disjoint.
 * The program must remain immutable from be_init through every be_step.
 */
BEStatus be_step(BasicExecutor *executor, uint8_t *output,
                 size_t output_capacity, size_t *written);

/* Exactly one stored BASIC line per call. Explicit ordered video side channel,
 * fixed caller-owned capacity; no allocation or hardware dependency.
 * events=NULL is allowed only for capacity=0; reached video commands return
 * BE_EVENT_RECEIVER_REQUIRED without consuming anything.
 * On BE_OK *written and *event_written report counts (including zeros).
 * On all errors and BE_END neither count, buffer, cursor nor store changes.
 * All regions, including entire event capacity, must be disjoint. */
BEStatus be_step_events(BasicExecutor *executor, uint8_t *output,
                        size_t output_capacity, size_t *written,
                        BEVideoEvent *events, size_t event_capacity,
                        size_t *event_written);

/* J1.21-B2a non-committing preview of exactly the next numbered BASIC
 * step, using the SAME executor verification and output/event emitter as
 * be_step_events. On BE_OK, only caller-owned staging output, events and
 * their counts change; executor cursor/statement, stacks, store and BASIC
 * program (all capacities) remain byte-identical. BE_END and all failures
 * leave staging buffers, counters and all BASIC state unchanged.
 * No heap or global scratch; the caller supplies separate staging regions.
 * A subsequent commit is coherent only when executor, program, store,
 * buffers/capacities and all borrowed inputs stay stable between calls.
 * For changed inputs, preview again. Does not reserve a transaction or
 * protect against concurrent external changes; caller must serialize.
 * No future step is previewed and no event is consumed by this call. */
BEStatus be_preview_step_events(BasicExecutor *executor, uint8_t *output,
                                size_t output_capacity, size_t *written,
                                BEVideoEvent *events, size_t event_capacity,
                                size_t *event_written);

/* B2: pure cause/location helper. Because a WHILE can prevalidate a future
 * malformed WEND, the offending CPC line may differ from executor->cursor.
 * No state or out-param mutation on error. Returns the actual numbered
 * BASIC line for a typed WHILE/WEND diagnostic, not a CPC ERR code. */
BEStatus be_while_diagnostic_line(const BasicExecutor *executor,
                                  BEStatus cause, uint16_t *line_number);

#endif
