#ifndef BASIC_SESSION_H
#define BASIC_SESSION_H

#include <stddef.h>
#include <stdint.h>
#include "basic_program.h"
#include "basic_tokenizer.h"
#include "basic_listing.h"

/* Host-side diagnostics, not CPC error numbers. The underlying detail field
 * is set only for BS_TOKENIZER_ERROR, BS_PROGRAM_ERROR or BS_LISTING_ERROR;
 * the other two detail fields are BT_OK/BP_OK/BL_OK respectively. */
typedef enum {
    BS_OK = 0,
    BS_NOT_FOUND,
    BS_INVALID_ARGUMENT,
    BS_OVERLAP,
    BS_INVALID_LINE_NUMBER,
    BS_MALFORMED_INPUT,
    BS_MULTIPLE_DIRECT,
    BS_UNSUPPORTED_DIRECT,
    BS_TOKENIZER_ERROR,
    BS_PROGRAM_ERROR,
    BS_LISTING_ERROR
} BSStatus;

typedef struct {
    BSStatus status;
    BTStatus tokenizer_status;
    BPStatus program_status;
    BLStatus listing_status;
} BSResult;

/* Dispatch exactly source_length bytes. On BS_OK, *written is 0 for edits,
 * NEW and blank input, or the LIST length; no trailing NUL is appended.
 * On ANY other status, program, output (all output_capacity bytes) and
 * *written are unchanged. The temporary token buffer may be modified.
 *
 * All five memory regions (program descriptor, entire program storage
 * capacity, source extent, entire temporary capacity, entire output
 * capacity), plus *written, must be pairwise disjoint. Non-NULL arguments
 * are required even when a length/capacity is zero. Inputs must remain
 * valid and immutable throughout the operation (except the program itself).
 * Aliasing is detected on platforms with uintptr_t (Linux/ESP32), and is
 * otherwise a caller precondition. No allocation or retained pointers.
 */
BSResult bs_process_line(BasicProgram *program,
                         const uint8_t *source, size_t source_length,
                         uint8_t *temporary, size_t temporary_capacity,
                         uint8_t *output, size_t output_capacity,
                         size_t *written);

#endif
