#include "basic_variable_ref.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); \
    return 1; } } while (0)

static int valid(const uint8_t *data, size_t bytes, size_t start,
                 uint8_t marker, BVRFamily family, BVRExplicitType type,
                 uint8_t low, uint8_t high, size_t length, size_t consumed)
{
    BasicVariableRef result;
    uint8_t source_snapshot[128];
    CHECK(bytes <= sizeof(source_snapshot));
    memcpy(source_snapshot, data, bytes);
    memset(&result, 0xa5, sizeof(result));
    CHECK(bvr_decode(data, bytes, start, &result) == BVR_OK);
    CHECK(result.marker == marker);
    CHECK(result.family == family);
    CHECK(result.explicit_type == type);
    CHECK(result.cache_low == low && result.cache_high == high);
    CHECK(result.reference_offset == start);
    CHECK(result.name_offset == start + 3u);
    CHECK(result.name_length == length);
    CHECK(result.consumed == consumed);
    CHECK(memcmp(data, source_snapshot, bytes) == 0);
    return 0;
}

static int invalid(const uint8_t *data, size_t bytes, size_t offset,
                   BVRStatus expected)
{
    BasicVariableRef result, before;
    uint8_t source_snapshot[128];
    CHECK(bytes <= sizeof(source_snapshot));
    memcpy(source_snapshot, data, bytes);
    memset(&result, 0xa5, sizeof(result));
    memcpy(&before, &result, sizeof(result));
    CHECK(bvr_decode(data, bytes, offset, &result) == expected);
    CHECK(memcmp(&result, &before, sizeof(result)) == 0);
    CHECK(memcmp(data, source_snapshot, bytes) == 0);
    return 0;
}

static int test_valid_vectors(void)
{
    static const uint8_t int_a[] = {0x02u, 0x00u, 0x00u, 0xc1u};
    static const uint8_t str_name[] = {0x03u, 0x34u, 0x12u, 'm', 'i', 'x', 0xc5u};
    static const uint8_t real_lower[] = {0x04u, 0xffu, 0x01u, 0xe1u};
    static const uint8_t dotted[] = {0x02u, 0x12u, 0x34u, 'A', '.', '2', 0xe2u};
    static const uint8_t middle[] = {'X', 0x04u, 0x78u, 0x56u, 'a', '9', 0xaeu, 'Q'};
    static const uint8_t unsuffixed[][6] = {
        {0x0bu, 0x00u, 0x00u, 'a', 'b', 0xc3u},
        {0x0cu, 0x01u, 0x00u, 'a', 'b', 0xc3u},
        {0x0du, 0x00u, 0x80u, 'a', 'b', 0xc3u}
    };
    size_t i;
    CHECK(valid(int_a, sizeof(int_a), 0u, 0x02u,
                BVR_FAMILY_EXPLICIT, BVR_TYPE_INTEGER, 0u, 0u, 1u, 4u) == 0);
    CHECK(valid(str_name, sizeof(str_name), 0u, 0x03u,
                BVR_FAMILY_EXPLICIT, BVR_TYPE_STRING, 0x34u, 0x12u, 4u, 7u) == 0);
    CHECK(valid(real_lower, sizeof(real_lower), 0u, 0x04u,
                BVR_FAMILY_EXPLICIT, BVR_TYPE_REAL, 0xffu, 0x01u, 1u, 4u) == 0);
    CHECK(valid(dotted, sizeof(dotted), 0u, 0x02u,
                BVR_FAMILY_EXPLICIT, BVR_TYPE_INTEGER, 0x12u, 0x34u, 4u, 7u) == 0);
    CHECK(valid(middle, sizeof(middle), 1u, 0x04u,
                BVR_FAMILY_EXPLICIT, BVR_TYPE_REAL, 0x78u, 0x56u, 3u, 6u) == 0);
    for (i = 0u; i < sizeof(unsuffixed) / sizeof(unsuffixed[0]); ++i) {
        CHECK(valid(unsuffixed[i], sizeof(unsuffixed[i]), 0u,
                    unsuffixed[i][0], BVR_FAMILY_UNSUFFIXED_OR_RESOLVED,
                    BVR_TYPE_UNDETERMINED, unsuffixed[i][1],
                    unsuffixed[i][2], 3u, 6u) == 0);
    }
    return 0;
}

static int test_bad_vectors(void)
{
    static const uint8_t token[] = {0x02u};
    static const uint8_t cache[] = {0x03u, 0x12u};
    static const uint8_t absent_name[] = {0x04u, 0x12u, 0x34u};
    static const uint8_t unclosed[] = {0x02u, 0u, 0u, 'A', 'B'};
    static const uint8_t unknown[] = {0x01u, 0u, 0u, 0xc1u};
    static const uint8_t digit_first[] = {0x02u, 0u, 0u, 0xb1u};
    static const uint8_t dot_first[] = {0x02u, 0u, 0u, 0xaeu};
    static const uint8_t underscore[] = {0x02u, 0u, 0u, 'A', 0xdfu};
    static const uint8_t space[] = {0x02u, 0u, 0u, 'A', 0xa0u};
    static const uint8_t null_char[] = {0x02u, 0u, 0u, 0x80u};
    static const uint8_t unicode[] = {0x02u, 0u, 0u, 'A', 0xe9u};
    CHECK(invalid(token, sizeof(token), 0u, BVR_TRUNCATED) == 0);
    CHECK(invalid(cache, sizeof(cache), 0u, BVR_TRUNCATED) == 0);
    CHECK(invalid(absent_name, sizeof(absent_name), 0u, BVR_TRUNCATED) == 0);
    CHECK(invalid(unclosed, sizeof(unclosed), 0u, BVR_TRUNCATED) == 0);
    CHECK(invalid(unknown, sizeof(unknown), 0u, BVR_UNRECOGNIZED_MARKER) == 0);
    CHECK(invalid(digit_first, sizeof(digit_first), 0u, BVR_MALFORMED) == 0);
    CHECK(invalid(dot_first, sizeof(dot_first), 0u, BVR_MALFORMED) == 0);
    CHECK(invalid(underscore, sizeof(underscore), 0u, BVR_MALFORMED) == 0);
    CHECK(invalid(space, sizeof(space), 0u, BVR_MALFORMED) == 0);
    CHECK(invalid(null_char, sizeof(null_char), 0u, BVR_MALFORMED) == 0);
    /* High bit terminates; 0xE9 decodes to ASCII 'i' and is admissible. */
    CHECK(valid(unicode, sizeof(unicode), 0u, 0x02u,
                BVR_FAMILY_EXPLICIT, BVR_TYPE_INTEGER, 0u, 0u, 2u, 5u) == 0);
    CHECK(invalid(token, sizeof(token), 1u, BVR_INVALID_ARGUMENT) == 0);
    CHECK(invalid(token, sizeof(token), SIZE_MAX, BVR_INVALID_ARGUMENT) == 0);
    CHECK(invalid(token, sizeof(token), SIZE_MAX - 1u, BVR_INVALID_ARGUMENT) == 0);
    return 0;
}

static int test_name_limits(void)
{
    uint8_t buffer[3u + BVR_MAX_NAME_LENGTH + 2u];
    size_t i;
    memset(buffer, 'A', sizeof(buffer));
    buffer[0] = 0x0bu;
    buffer[1] = 0xffu;
    buffer[2] = 0xffu;
    for (i = 3u; i < 3u + BVR_MAX_NAME_LENGTH; ++i) {
        buffer[i] = 'a';
    }
    buffer[3u + BVR_MAX_NAME_LENGTH - 1u] = 0xe1u;
    CHECK(valid(buffer, 3u + BVR_MAX_NAME_LENGTH, 0u, 0x0bu,
                BVR_FAMILY_UNSUFFIXED_OR_RESOLVED, BVR_TYPE_UNDETERMINED,
                0xffu, 0xffu, BVR_MAX_NAME_LENGTH,
                3u + BVR_MAX_NAME_LENGTH) == 0);
    buffer[3u + BVR_MAX_NAME_LENGTH - 1u] = 'a';
    CHECK(invalid(buffer, 3u + BVR_MAX_NAME_LENGTH, 0u, BVR_TRUNCATED) == 0);
    buffer[3u + BVR_MAX_NAME_LENGTH] = 0xe1u;
    CHECK(invalid(buffer, 4u + BVR_MAX_NAME_LENGTH, 0u, BVR_LIMIT_EXCEEDED) == 0);
    buffer[3u + BVR_MAX_NAME_LENGTH] = 'a';
    CHECK(invalid(buffer, sizeof(buffer), 0u, BVR_LIMIT_EXCEEDED) == 0);
    return 0;
}

static int test_arguments_and_overlap(void)
{
    uint8_t source[] = {0x02u, 0u, 0u, 0xc1u};
    BasicVariableRef result, previous;
    union {
        BasicVariableRef aligned;
        uint8_t bytes[sizeof(BasicVariableRef)];
    } aliased;
    uint8_t snapshot[sizeof(aliased.bytes)];
    memset(&result, 0x5a, sizeof(result));
    memcpy(&previous, &result, sizeof(result));
    CHECK(bvr_decode(NULL, sizeof(source), 0u, &result) == BVR_INVALID_ARGUMENT);
    CHECK(bvr_decode(source, sizeof(source), 0u, NULL) == BVR_INVALID_ARGUMENT);
    CHECK(memcmp(&result, &previous, sizeof(result)) == 0);
    CHECK(bvr_decode(source, 0u, 0u, &result) == BVR_INVALID_ARGUMENT);
    CHECK(bvr_decode(source, sizeof(source), SIZE_MAX, &result) == BVR_INVALID_ARGUMENT);
    CHECK(memcmp(&result, &previous, sizeof(result)) == 0);
    memset(&aliased, 0xa5, sizeof(aliased));
    memcpy(aliased.bytes, source, sizeof(source));
    memcpy(snapshot, aliased.bytes, sizeof(snapshot));
    CHECK(bvr_decode(aliased.bytes, sizeof(aliased.bytes), 0u,
                     &aliased.aligned) == BVR_OVERLAPPING_MEMORY);
    CHECK(memcmp(aliased.bytes, snapshot, sizeof(snapshot)) == 0);
    return 0;
}

int main(void)
{
    CHECK(test_valid_vectors() == 0);
    CHECK(test_bad_vectors() == 0);
    CHECK(test_name_limits() == 0);
    CHECK(test_arguments_and_overlap() == 0);
    puts("basic_variable_ref: OK");
    return 0;
}
