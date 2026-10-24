#include "basic_variable_types.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); \
    return 1; } } while (0)

static int canonical(const char *text, uint8_t marker, BasicVariableName *name)
{
    uint8_t source[3u + BVT_MAX_NAME_LENGTH];
    uint8_t before[sizeof(source)];
    size_t length = strlen(text);
    size_t i;
    CHECK(length >= 1u && length <= BVT_MAX_NAME_LENGTH);
    memset(source, 0, sizeof(source));
    source[0] = marker;
    source[1] = 0x34u;
    source[2] = 0x12u;
    for (i = 0u; i < length; ++i) {
        source[3u + i] = (uint8_t)text[i];
    }
    source[2u + length] |= 0x80u;
    memcpy(before, source, sizeof(source));
    CHECK(bvt_canonicalize(source, 3u + length, 0u, name) == BVT_OK);
    CHECK(memcmp(source, before, sizeof(source)) == 0);
    CHECK(name->length == length);
    for (i = length; i < BVT_MAX_NAME_LENGTH; ++i) {
        CHECK(name->bytes[i] == 0u);
    }
    return 0;
}

static int unchanged_canonical(const uint8_t *src, size_t n, size_t offset,
                               BVTStatus expected)
{
    BasicVariableName result, before;
    memset(&result, 0xa5, sizeof(result));
    memcpy(&before, &result, sizeof(result));
    CHECK(bvt_canonicalize(src, n, offset, &result) == expected);
    CHECK(memcmp(&result, &before, sizeof(result)) == 0);
    return 0;
}

static int test_defaults_and_ranges(void)
{
    BasicVariableTypes types;
    BasicVariableType value;
    size_t i;
    CHECK(sizeof(types) == 26u);
    CHECK(sizeof(BasicVariableName) == 41u);
    CHECK(sizeof(BasicVariableKey) == 42u);
    memset(&types, 0xa5, sizeof(types));
    CHECK(bvt_init(&types) == BVT_OK);
    for (i = 0u; i < 26u; ++i) {
        CHECK(types.types[i] == (uint8_t)BVT_REAL);
        value = BVT_INTEGER;
        CHECK(bvt_get_implicit(&types, (char)('A' + (int)i), &value) == BVT_OK);
        CHECK(value == BVT_REAL);
    }
    CHECK(bvt_set_range(&types, 'c', 'c', BVT_INTEGER) == BVT_OK);
    CHECK(types.types[1] == (uint8_t)BVT_REAL);
    CHECK(types.types[2] == (uint8_t)BVT_INTEGER);
    CHECK(types.types[3] == (uint8_t)BVT_REAL);
    CHECK(bvt_set_range(&types, 'b', 'D', BVT_STRING) == BVT_OK);
    CHECK(types.types[1] == (uint8_t)BVT_STRING);
    CHECK(types.types[2] == (uint8_t)BVT_STRING);
    CHECK(types.types[3] == (uint8_t)BVT_STRING);
    CHECK(bvt_set_range(&types, 'C', 'E', BVT_INTEGER) == BVT_OK);
    CHECK(types.types[1] == (uint8_t)BVT_STRING);
    CHECK(types.types[2] == (uint8_t)BVT_INTEGER);
    CHECK(types.types[4] == (uint8_t)BVT_INTEGER);
    CHECK(types.types[5] == (uint8_t)BVT_REAL);
    CHECK(bvt_get_implicit(&types, 'c', &value) == BVT_OK);
    CHECK(value == BVT_INTEGER);
    CHECK(bvt_set_range(&types, 'a', 'z', BVT_STRING) == BVT_OK);
    for (i = 0u; i < 26u; ++i) {
        CHECK(types.types[i] == (uint8_t)BVT_STRING);
    }
    CHECK(bvt_set_range(&types, 'A', 'Z', BVT_REAL) == BVT_OK);
    for (i = 0u; i < 26u; ++i) {
        CHECK(types.types[i] == (uint8_t)BVT_REAL);
    }
    return 0;
}

static int test_invalid_ranges_atomic(void)
{
    BasicVariableTypes types, before;
    BasicVariableType output, prior;
    const char bad[] = {'0', '.', '[', '@', '{', ' ', (char)0xff};
    size_t i;
    CHECK(bvt_init(&types) == BVT_OK);
    CHECK(bvt_set_range(&types, 'D', 'F', BVT_INTEGER) == BVT_OK);
    before = types;
    CHECK(bvt_set_range(&types, 'Z', 'A', BVT_STRING) == BVT_INVALID_RANGE);
    CHECK(bvt_set_range(&types, 'b', 'A', BVT_STRING) == BVT_INVALID_RANGE);
    CHECK(bvt_set_range(&types, 'A', 'Z', (BasicVariableType)4) == BVT_INVALID_TYPE);
    CHECK(bvt_set_range(&types, 'A', 'Z', (BasicVariableType)-1) == BVT_INVALID_TYPE);
    CHECK(bvt_set_range(NULL, 'A', 'Z', BVT_INTEGER) == BVT_INVALID_ARGUMENT);
    CHECK(bvt_init(NULL) == BVT_INVALID_ARGUMENT);
    for (i = 0u; i < sizeof(bad); ++i) {
        CHECK(bvt_set_range(&types, bad[i], 'Z', BVT_STRING) == BVT_INVALID_LETTER);
        CHECK(bvt_set_range(&types, 'A', bad[i], BVT_STRING) == BVT_INVALID_LETTER);
    }
    CHECK(memcmp(&types, &before, sizeof(types)) == 0);
    output = BVT_STRING;
    prior = output;
    CHECK(bvt_get_implicit(NULL, 'A', &output) == BVT_INVALID_ARGUMENT);
    CHECK(bvt_get_implicit(&types, 'A', NULL) == BVT_INVALID_ARGUMENT);
    for (i = 0u; i < sizeof(bad); ++i) {
        CHECK(bvt_get_implicit(&types, bad[i], &output) == BVT_INVALID_LETTER);
        CHECK(output == prior);
    }
    types.types[0] = 0u; /* Invalid caller-owned table state is detected. */
    CHECK(bvt_get_implicit(&types, 'a', &output) == BVT_INVALID_TYPE);
    CHECK(output == prior);
    return 0;
}

static int test_canonical_names(void)
{
    BasicVariableName lower, upper, dotted, plain, long_a, long_b;
    static const uint8_t middle[] = {0xffu, 0x0cu, 0x12u, 0x34u, 'a', '.', '3', 0xe2u, 0x55u};
    BasicVariableName middle_name;
    CHECK(canonical("abc", 0x0bu, &lower) == 0);
    CHECK(canonical("ABC", 0x0du, &upper) == 0);
    CHECK(memcmp(&lower, &upper, sizeof(lower)) == 0);
    CHECK(canonical("a", 0x02u, &lower) == 0);
    CHECK(lower.length == 1u && lower.bytes[0] == (uint8_t)'A');
    CHECK(canonical("A.B", 0x03u, &dotted) == 0);
    CHECK(canonical("AB", 0x04u, &plain) == 0);
    CHECK(dotted.length == 3u && plain.length == 2u);
    CHECK(memcmp(&dotted, &plain, sizeof(plain)) != 0);
    CHECK(canonical("a1.2b", 0x0cu, &dotted) == 0);
    CHECK(memcmp(dotted.bytes, "A1.2B", 5u) == 0);
    CHECK(canonical("ABCDEFGHI", 0x02u, &dotted) == 0);
    CHECK(canonical("ABCDEFGHJ", 0x02u, &plain) == 0);
    CHECK(memcmp(&dotted, &plain, sizeof(plain)) != 0);
    CHECK(canonical("ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMN", 0x0bu, &long_a) == 0);
    CHECK(canonical("ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMO", 0x0du, &long_b) == 0);
    CHECK(long_a.length == 40u && long_b.length == 40u);
    CHECK(memcmp(long_a.bytes, long_b.bytes, 39u) == 0);
    CHECK(long_a.bytes[39] != long_b.bytes[39]);
    CHECK(bvt_canonicalize(middle, sizeof(middle), 1u, &middle_name) == BVT_OK);
    CHECK(middle_name.length == 4u);
    CHECK(memcmp(middle_name.bytes, "A.3B", 4u) == 0);
    return 0;
}

static int test_typed_keys(void)
{
    BasicVariableName name, other;
    BasicVariableKey i, r, s, identical, other_key;
    BasicVariableKey saved;
    CHECK(canonical("a", 0x02u, &name) == 0);
    CHECK(bvt_build_key(&name, BVT_INTEGER, &i) == BVT_OK);
    CHECK(bvt_build_key(&name, BVT_REAL, &r) == BVT_OK);
    CHECK(bvt_build_key(&name, BVT_STRING, &s) == BVT_OK);
    CHECK(i.type == 2u && r.type == 5u && s.type == 3u);
    CHECK(memcmp(&i, &r, sizeof(i)) != 0);
    CHECK(memcmp(&i, &s, sizeof(i)) != 0);
    CHECK(memcmp(&r, &s, sizeof(i)) != 0);
    CHECK(canonical("A", 0x03u, &other) == 0);
    CHECK(bvt_build_key(&other, BVT_INTEGER, &identical) == BVT_OK);
    CHECK(memcmp(&i, &identical, sizeof(i)) == 0);
    CHECK(canonical("A.B", 0x04u, &other) == 0);
    CHECK(bvt_build_key(&other, BVT_INTEGER, &other_key) == BVT_OK);
    CHECK(memcmp(&i, &other_key, sizeof(i)) != 0);
    CHECK(canonical("a", 0x04u, &name) == 0);
    saved = i;
    CHECK(bvt_build_key(&name, (BasicVariableType)0x0bu, &i) == BVT_INVALID_TYPE);
    CHECK(memcmp(&i, &saved, sizeof(i)) == 0);
    CHECK(bvt_build_key(NULL, BVT_INTEGER, &i) == BVT_INVALID_ARGUMENT);
    CHECK(bvt_build_key(&name, BVT_INTEGER, NULL) == BVT_INVALID_ARGUMENT);
    CHECK(memcmp(&i, &saved, sizeof(i)) == 0);
    /* Caller-built or corrupted name records cannot silently yield keys. */
    name.length = 0u;
    CHECK(bvt_build_key(&name, BVT_INTEGER, &i) == BVT_INVALID_NAME);
    name.length = 41u;
    CHECK(bvt_build_key(&name, BVT_INTEGER, &i) == BVT_INVALID_NAME);
    name.length = 1u;
    name.bytes[0] = (uint8_t)'a';
    CHECK(bvt_build_key(&name, BVT_INTEGER, &i) == BVT_INVALID_NAME);
    name.bytes[0] = (uint8_t)'A';
    name.bytes[1] = (uint8_t)'X';
    CHECK(bvt_build_key(&name, BVT_INTEGER, &i) == BVT_INVALID_NAME);
    name.bytes[1] = 0u;
    name.length = 2u;
    CHECK(bvt_build_key(&name, BVT_INTEGER, &i) == BVT_INVALID_NAME);
    CHECK(memcmp(&i, &saved, sizeof(i)) == 0);
    CHECK(canonical("ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMN", 0x0bu, &name) == 0);
    CHECK(canonical("ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMO", 0x0du, &other) == 0);
    CHECK(bvt_build_key(&name, BVT_REAL, &r) == BVT_OK);
    CHECK(bvt_build_key(&other, BVT_REAL, &other_key) == BVT_OK);
    CHECK(memcmp(&r, &other_key, sizeof(r)) != 0);
    return 0;
}

static int test_invalid_refs_and_bounds(void)
{
    static const uint8_t tiny[] = {0x02u};
    static const uint8_t unknown[] = {0x01u, 0u, 0u, 0xc1u};
    static const uint8_t no_name[] = {0x02u, 0u, 0u};
    static const uint8_t bad_first[] = {0x02u, 0u, 0u, 0xb1u};
    static const uint8_t bad_inner[] = {0x02u, 0u, 0u, 'A', 0xdfu};
    static const uint8_t no_end[] = {0x02u, 0u, 0u, 'A'};
    uint8_t long_ref[3u + 41u];
    BasicVariableName name;
    uint8_t before[sizeof(long_ref)];
    memset(long_ref, 'A', sizeof(long_ref));
    long_ref[0] = 0x0bu;
    long_ref[1] = 0u;
    long_ref[2] = 0u;
    long_ref[43] = 0xc1u;
    memcpy(before, long_ref, sizeof(before));
    CHECK(unchanged_canonical(NULL, 0u, 0u, BVT_INVALID_ARGUMENT) == 0);
    CHECK(unchanged_canonical(tiny, 0u, 0u, BVT_INVALID_ARGUMENT) == 0);
    CHECK(unchanged_canonical(tiny, sizeof(tiny), 1u, BVT_INVALID_ARGUMENT) == 0);
    CHECK(unchanged_canonical(tiny, sizeof(tiny), SIZE_MAX, BVT_INVALID_ARGUMENT) == 0);
    CHECK(unchanged_canonical(tiny, sizeof(tiny), SIZE_MAX - 1u, BVT_INVALID_ARGUMENT) == 0);
    CHECK(unchanged_canonical(tiny, sizeof(tiny), 0u, BVT_INVALID_REFERENCE) == 0);
    CHECK(unchanged_canonical(unknown, sizeof(unknown), 0u, BVT_INVALID_REFERENCE) == 0);
    CHECK(unchanged_canonical(no_name, sizeof(no_name), 0u, BVT_INVALID_REFERENCE) == 0);
    CHECK(unchanged_canonical(bad_first, sizeof(bad_first), 0u, BVT_INVALID_REFERENCE) == 0);
    CHECK(unchanged_canonical(bad_inner, sizeof(bad_inner), 0u, BVT_INVALID_REFERENCE) == 0);
    CHECK(unchanged_canonical(no_end, sizeof(no_end), 0u, BVT_INVALID_REFERENCE) == 0);
    CHECK(unchanged_canonical(long_ref, sizeof(long_ref), 0u, BVT_INVALID_REFERENCE) == 0);
    CHECK(memcmp(long_ref, before, sizeof(long_ref)) == 0);
    memset(&name, 0xa5, sizeof(name));
    CHECK(bvt_canonicalize(tiny, sizeof(tiny), 0u, NULL) == BVT_INVALID_ARGUMENT);
    CHECK(bvt_canonicalize(NULL, 4u, 0u, &name) == BVT_INVALID_ARGUMENT);
    CHECK(name.length == 0xa5u);
    return 0;
}

static int test_overlaps(void)
{
    union {
        BasicVariableName name;
        uint8_t source[sizeof(BasicVariableName)];
    } src_alias;
    union {
        BasicVariableKey key;
        BasicVariableName name;
    } key_alias;
    union {
        BasicVariableTypes table;
        BasicVariableType type;
    } type_alias;
    uint8_t snapshot[sizeof(src_alias)];
    BasicVariableKey key_copy;
    BasicVariableTypes type_copy;
    memset(&src_alias, 0xa5, sizeof(src_alias));
    src_alias.source[0] = 0x02u;
    src_alias.source[1] = 0u;
    src_alias.source[2] = 0u;
    src_alias.source[3] = 0xc1u;
    memcpy(snapshot, &src_alias, sizeof(src_alias));
    CHECK(bvt_canonicalize(src_alias.source, 4u, 0u, &src_alias.name) ==
          BVT_OVERLAPPING_MEMORY);
    CHECK(memcmp(&src_alias, snapshot, sizeof(src_alias)) == 0);
    memset(&key_alias, 0xa5, sizeof(key_alias));
    memcpy(&key_copy, &key_alias.key, sizeof(key_copy));
    CHECK(bvt_build_key(&key_alias.name, BVT_REAL, &key_alias.key) ==
          BVT_OVERLAPPING_MEMORY);
    CHECK(memcmp(&key_alias.key, &key_copy, sizeof(key_copy)) == 0);
    memset(&type_alias, 0xa5, sizeof(type_alias));
    type_copy = type_alias.table;
    CHECK(bvt_get_implicit(&type_alias.table, 'A', &type_alias.type) ==
          BVT_OVERLAPPING_MEMORY);
    CHECK(memcmp(&type_alias.table, &type_copy, sizeof(type_copy)) == 0);
    return 0;
}

int main(void)
{
    CHECK(test_defaults_and_ranges() == 0);
    CHECK(test_invalid_ranges_atomic() == 0);
    CHECK(test_canonical_names() == 0);
    CHECK(test_typed_keys() == 0);
    CHECK(test_invalid_refs_and_bounds() == 0);
    CHECK(test_overlaps() == 0);
    puts("basic_variable_types: OK (synthetic fixtures, not CPC captures)");
    return 0;
}
