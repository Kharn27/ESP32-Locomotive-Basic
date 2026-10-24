#ifndef BASIC_VARIABLE_TYPES_H
#define BASIC_VARIABLE_TYPES_H

#include <stddef.h>
#include <stdint.h>

#include "basic_variable_ref.h"

/* J0.14 internal API statuses; these are not CPC error codes. */
typedef enum {
    BVT_OK = 0,
    BVT_INVALID_ARGUMENT,
    BVT_INVALID_LETTER,
    BVT_INVALID_RANGE,
    BVT_INVALID_TYPE,
    BVT_INVALID_NAME,
    BVT_INVALID_REFERENCE,
    BVT_OVERLAPPING_MEMORY
} BVTStatus;

/* Historical runtime type codes used by the DEF table at D638-D67D.
 * Not variable-reference markers (in particular BVR marker 04 is REAL). */
typedef enum {
    BVT_INTEGER = 0x02,
    BVT_STRING = 0x03,
    BVT_REAL = 0x05
} BasicVariableType;

#define BVT_ALPHABET_SIZE 26u
#define BVT_MAX_NAME_LENGTH BVR_MAX_NAME_LENGTH

/* Caller-owned 26-byte implicit type table, indexed by normalized A..Z. */
typedef struct {
    uint8_t types[BVT_ALPHABET_SIZE];
} BasicVariableTypes;

/* No pointer or terminator; unused name bytes are always zero after success. */
typedef struct {
    uint8_t length; /* 1..40 */
    uint8_t bytes[BVT_MAX_NAME_LENGTH]; /* uppercase ASCII, digits, dots */
} BasicVariableName;

/* Typed identity is (all significant name bytes, effective type).
 * The effective type is supplied by the caller, NEVER inferred from 0B/0C/0D.
 * No padding-dependent equality: compare type, length, then length bytes.
 */
typedef struct {
    uint8_t type; /* a validated BasicVariableType value */
    uint8_t name_length;
    uint8_t name[BVT_MAX_NAME_LENGTH]; /* zero-filled unused tail */
} BasicVariableKey;

/* Initialize 26 entries to REAL (ROM code 05). NULL: no change. */
BVTStatus bvt_init(BasicVariableTypes *table);

/* Read one letter's current implicit type. Accepts ASCII a..z and A..Z.
 * Invalid arguments/type, or overlapping table and output: no writes.
 */
BVTStatus bvt_get_implicit(const BasicVariableTypes *table, char initial,
                           BasicVariableType *out_type);

/* Change an inclusive A..Z range. A reversed or invalid range and an
 * unsupported type change no entries (atomic validation before commit).
 */
BVTStatus bvt_set_range(BasicVariableTypes *table, char first, char last,
                         BasicVariableType type);

/* Decode using J0.13 bvr_decode, then copy and canonicalize the full name.
 * source_length describes a real accessible buffer; offset is an index into it.
 * The source buffer and output object MUST NOT overlap. Invalid/truncated
 * reference or insufficient bytes leave output and source unchanged.
 */
BVTStatus bvt_canonicalize(const uint8_t *source, size_t source_length,
                            size_t offset, BasicVariableName *out_name);

/* Build a 42-byte key using a previously canonicalized, valid name and an
 * EXPLICITLY supplied effective type. The input and output must not overlap.
 * Rejects forged/noncanonical name structures, including nonzero tail bytes.
 * Every failure leaves the output and input objects unchanged.
 */
BVTStatus bvt_build_key(const BasicVariableName *name,
                         BasicVariableType effective_type,
                         BasicVariableKey *out_key);

#endif
