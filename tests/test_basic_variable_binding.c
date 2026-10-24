#include "basic_variable_binding.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); \
    return 1; } } while (0)

static int wire(const char *name, BVRExplicitType type,
                uint8_t *buffer, size_t capacity, size_t *bytes)
{
    CHECK(bvr_encode_explicit((const uint8_t *)name, strlen(name), type,
                              buffer, capacity, bytes) == BVR_OK);
    return 0;
}

static int resolve(const char *name, BVRExplicitType explicit_type,
                   uint8_t wanted_type, BasicVariableKey *key)
{
    uint8_t bytes[3u + BVT_MAX_NAME_LENGTH];
    size_t used, consumed = 0u;
    CHECK(wire(name, explicit_type, bytes, sizeof(bytes), &used) == 0);
    CHECK(bvb_resolve_explicit(bytes, used, 0u, key, &consumed) == BVB_OK);
    CHECK(consumed == used);
    CHECK(key->type == wanted_type);
    CHECK(key->name_length == strlen(name));
    return 0;
}

static int unchanged(const uint8_t *source, size_t length, size_t offset,
                     BVBStatus expected)
{
    BasicVariableKey key, before_key;
    size_t consumed = 0x1234u;
    size_t before_consumed = consumed;
    uint8_t before_source[128];
    CHECK(length <= sizeof(before_source));
    memcpy(before_source, source, length);
    memset(&key, 0xa5, sizeof(key));
    before_key = key;
    CHECK(bvb_resolve_explicit(source, length, offset, &key, &consumed) == expected);
    CHECK(memcmp(&key, &before_key, sizeof(key)) == 0);
    CHECK(consumed == before_consumed);
    CHECK(memcmp(source, before_source, length) == 0);
    return 0;
}

static int test_types_case_and_identity(void)
{
    BasicVariableKey lower, upper, string_key, real_key, names[5];
    BasicVariableName canonical;
    BasicVariableKey independent;
    uint8_t raw[] = {0x02u, 0x34u, 0x12u, 'a', 'b', 0xc3u};
    size_t n = 99u;
    size_t i;
    char long_name[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMN";
    char changed_name[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMO";
    static const char *const words[] = {"ABC", "ABD", "A.2", "ABC.", "ABCD"};

    CHECK(resolve("a", BVR_TYPE_INTEGER, BVT_INTEGER, &lower) == 0);
    CHECK(resolve("A", BVR_TYPE_INTEGER, BVT_INTEGER, &upper) == 0);
    CHECK(memcmp(&lower, &upper, sizeof(lower)) == 0);
    CHECK(resolve("a", BVR_TYPE_STRING, BVT_STRING, &string_key) == 0);
    CHECK(resolve("a", BVR_TYPE_REAL, BVT_REAL, &real_key) == 0);
    CHECK(real_key.type == 0x05u); /* CPC 04 is NOT a runtime type 04. */
    CHECK(lower.type == 0x02u && string_key.type == 0x03u);
    CHECK(memcmp(&lower, &string_key, sizeof(lower)) != 0);
    CHECK(memcmp(&lower, &real_key, sizeof(lower)) != 0);
    CHECK(memcmp(&string_key, &real_key, sizeof(lower)) != 0);

    CHECK(bvt_canonicalize(raw, sizeof(raw), 0u, &canonical) == BVT_OK);
    CHECK(bvt_build_key(&canonical, BVT_INTEGER, &independent) == BVT_OK);
    CHECK(bvb_resolve_explicit(raw, sizeof(raw), 0u, &upper, &n) == BVB_OK);
    CHECK(n == sizeof(raw) && memcmp(&upper, &independent, sizeof(upper)) == 0);
    CHECK(memcmp(raw, (uint8_t[]){0x02u, 0x34u, 0x12u, 'a', 'b', 0xc3u},
                 sizeof(raw)) == 0);

    for (i = 0u; i < sizeof(words) / sizeof(words[0]); ++i) {
        CHECK(resolve(words[i], BVR_TYPE_INTEGER, BVT_INTEGER, &names[i]) == 0);
    }
    for (i = 0u; i < sizeof(words) / sizeof(words[0]); ++i) {
        size_t j;
        for (j = i + 1u; j < sizeof(words) / sizeof(words[0]); ++j) {
            CHECK(memcmp(&names[i], &names[j], sizeof(names[i])) != 0);
        }
    }
    CHECK(strlen(long_name) == 40u && strlen(changed_name) == 40u);
    CHECK(resolve(long_name, BVR_TYPE_INTEGER, BVT_INTEGER, &lower) == 0);
    CHECK(resolve(changed_name, BVR_TYPE_INTEGER, BVT_INTEGER, &upper) == 0);
    CHECK(lower.name_length == 40u);
    CHECK(memcmp(lower.name, long_name, 40u) == 0);
    CHECK(memcmp(lower.name, upper.name, 39u) == 0);
    CHECK(lower.name[39] != upper.name[39]);
    return 0;
}

static int test_print_offset_and_cache(void)
{
    uint8_t source[60] = {0xbfu, 0x20u};
    uint8_t before[sizeof(source)];
    size_t used, consumed = 0u;
    BasicVariableKey key;
    CHECK(wire("MiX.2", BVR_TYPE_REAL, source + 2u,
               sizeof(source) - 2u, &used) == 0);
    source[3] = 0xdeu;
    source[4] = 0xadu;
    source[2u + used] = ':';
    memcpy(before, source, sizeof(source));
    CHECK(bvb_resolve_explicit(source, 3u + used, 2u, &key, &consumed) == BVB_OK);
    CHECK(consumed == used);
    CHECK(key.type == BVT_REAL && key.name_length == 5u);
    CHECK(memcmp(key.name, "MIX.2", 5u) == 0);
    CHECK(memcmp(source, before, sizeof(source)) == 0);
    CHECK(source[3] == 0xdeu && source[4] == 0xadu);
    return 0;
}

static int test_values_and_missing(void)
{
    BasicVariableStore store;
    BasicVariableEntry entries[4];
    BasicVariableEntry snapshot[4];
    BasicVariableStore store_copy;
    BasicVariableKey kint, kreal, kstr, output_key, old_key, absent;
    BasicVariableValue input, output, before;
    uint8_t source[50] = {0xbfu};
    uint8_t source_before[50];
    size_t used, consumed, index;
    size_t old_consumed;
    const uint8_t real_bytes[5] = {0x81u, 0x01u, 0x23u, 0x45u, 0x67u};

    CHECK(bvs_init(&store, entries, 4u) == BVS_OK);
    CHECK(resolve("A", BVR_TYPE_INTEGER, BVT_INTEGER, &kint) == 0);
    CHECK(resolve("A", BVR_TYPE_REAL, BVT_REAL, &kreal) == 0);
    CHECK(resolve("A", BVR_TYPE_STRING, BVT_STRING, &kstr) == 0);
    CHECK(resolve("Z", BVR_TYPE_INTEGER, BVT_INTEGER, &absent) == 0);
    CHECK(bvs_create(&store, &kint, &index) == BVS_OK && index == 0u);
    CHECK(bvs_create(&store, &kreal, &index) == BVS_OK && index == 1u);
    CHECK(bvs_create(&store, &kstr, &index) == BVS_OK && index == 2u);

    memset(&input, 0, sizeof(input));
    input.type = BVT_INTEGER;
    input.data.integer = INT16_MIN;
    CHECK(bvs_set(&store, &kint, &input) == BVS_OK);
    memset(&input, 0, sizeof(input));
    input.type = BVT_REAL;
    memcpy(input.data.real5, real_bytes, sizeof(real_bytes));
    CHECK(bvs_set(&store, &kreal, &input) == BVS_OK);
    memset(&input, 0, sizeof(input));
    input.type = BVT_STRING;
    CHECK(bvs_set(&store, &kstr, &input) == BVS_OK);

    /* All three types use the same source offset following PRINT. */
    CHECK(wire("a", BVR_TYPE_INTEGER, source + 1u,
               sizeof(source) - 1u, &used) == 0);
    memcpy(source_before, source, sizeof(source));
    memcpy(snapshot, entries, sizeof(entries));
    store_copy = store;
    consumed = 0u;
    CHECK(bvb_read_explicit(source, used + 1u, 1u, &store,
                            &output_key, &consumed, &output) == BVB_OK);
    CHECK(consumed == used);
    CHECK(memcmp(&output_key, &kint, sizeof(kint)) == 0);
    CHECK(output.type == BVT_INTEGER && output.data.integer == INT16_MIN);
    CHECK(memcmp(entries, snapshot, sizeof(entries)) == 0);
    CHECK(memcmp(&store, &store_copy, sizeof(store)) == 0);
    CHECK(memcmp(source, source_before, sizeof(source)) == 0);

    CHECK(wire("a", BVR_TYPE_REAL, source + 1u,
               sizeof(source) - 1u, &used) == 0);
    source[2] = 0xaau;
    source[3] = 0x55u;
    memcpy(source_before, source, sizeof(source));
    CHECK(bvb_read_explicit(source, used + 1u, 1u, &store,
                            &output_key, &consumed, &output) == BVB_OK);
    CHECK(output_key.type == BVT_REAL && output.type == BVT_REAL);
    CHECK(memcmp(output.data.real5, real_bytes, 5u) == 0);
    CHECK(source[2] == 0xaau && source[3] == 0x55u);
    CHECK(memcmp(source, source_before, sizeof(source)) == 0);
    CHECK(memcmp(entries, snapshot, sizeof(entries)) == 0);

    CHECK(wire("A", BVR_TYPE_STRING, source + 1u,
               sizeof(source) - 1u, &used) == 0);
    CHECK(bvb_read_explicit(source, used + 1u, 1u, &store,
                            &output_key, &consumed, &output) == BVB_OK);
    CHECK(output.type == BVT_STRING && output.data.string.offset == 0u);
    CHECK(output.data.string.length == 0u);
    CHECK(memcmp(entries, snapshot, sizeof(entries)) == 0);

    CHECK(wire("Z", BVR_TYPE_INTEGER, source + 1u,
               sizeof(source) - 1u, &used) == 0);
    memset(&output_key, 0x5a, sizeof(output_key));
    old_key = output_key;
    memset(&output, 0xa5, sizeof(output));
    before = output;
    consumed = 0xabcdefu;
    old_consumed = consumed;
    CHECK(bvb_read_explicit(source, used + 1u, 1u, &store,
                            &output_key, &consumed, &output) == BVB_NOT_FOUND);
    CHECK(memcmp(&output_key, &old_key, sizeof(old_key)) == 0);
    CHECK(memcmp(&output, &before, sizeof(output)) == 0);
    CHECK(consumed == old_consumed);
    CHECK(store.count == 3u && memcmp(entries, snapshot, sizeof(entries)) == 0);
    CHECK(bvs_find(&store, &absent, &index) == BVS_NOT_FOUND);
    return 0;
}

static int test_invalid_references(void)
{
    static const uint8_t short_ref[] = {0x02u, 0u, 0u};
    static const uint8_t no_end[] = {0x03u, 0u, 0u, 'a', 'b'};
    static const uint8_t bad_start[] = {0x04u, 0u, 0u, 0xb1u};
    static const uint8_t bad_tail[] = {0x02u, 0u, 0u, 'A', 0xdfu};
    static const uint8_t unknown[] = {0x01u, 0u, 0u, 0xc1u};
    uint8_t too_long[3u + 41u];
    uint8_t upper_prefix[6] = {0xbfu, 0x20u, 0x02u, 0u, 0u, 0xc1u};
    size_t i, n;
    BasicVariableKey key;
    CHECK(unchanged(short_ref, sizeof(short_ref), 0u, BVB_TRUNCATED) == 0);
    CHECK(unchanged(no_end, sizeof(no_end), 0u, BVB_TRUNCATED) == 0);
    CHECK(unchanged(bad_start, sizeof(bad_start), 0u, BVB_MALFORMED) == 0);
    CHECK(unchanged(bad_tail, sizeof(bad_tail), 0u, BVB_MALFORMED) == 0);
    CHECK(unchanged(unknown, sizeof(unknown), 0u, BVB_UNRECOGNIZED_MARKER) == 0);
    CHECK(unchanged(upper_prefix, sizeof(upper_prefix), 5u,
                    BVB_UNRECOGNIZED_MARKER) == 0);
    CHECK(unchanged(upper_prefix, sizeof(upper_prefix), 6u,
                    BVB_INVALID_ARGUMENT) == 0);
    CHECK(unchanged(upper_prefix, sizeof(upper_prefix), SIZE_MAX,
                    BVB_INVALID_ARGUMENT) == 0);
    for (i = 0u; i < 3u; ++i) {
        uint8_t unsuffixed[] = {0x0bu, 0x42u, 0xf0u, 0xc1u};
        unsuffixed[0] = (uint8_t)(0x0bu + i);
        CHECK(unchanged(unsuffixed, sizeof(unsuffixed), 0u,
                        BVB_UNSUPPORTED_FAMILY) == 0);
    }
    memset(too_long, 'A', sizeof(too_long));
    too_long[0] = 0x02u;
    too_long[1] = 0u;
    too_long[2] = 0u;
    too_long[sizeof(too_long) - 1u] |= 0x80u;
    CHECK(unchanged(too_long, sizeof(too_long), 0u,
                    BVB_LIMIT_EXCEEDED) == 0);
    CHECK(unchanged(too_long, sizeof(too_long) - 1u, 0u,
                    BVB_TRUNCATED) == 0);
    n = 17u;
    CHECK(bvb_resolve_explicit(NULL, 1u, 0u, &key, &n) == BVB_INVALID_ARGUMENT);
    CHECK(bvb_resolve_explicit(short_ref, sizeof(short_ref), 0u, NULL, &n)
          == BVB_INVALID_ARGUMENT);
    CHECK(bvb_resolve_explicit(short_ref, sizeof(short_ref), 0u, &key, NULL)
          == BVB_INVALID_ARGUMENT);
    CHECK(n == 17u);
    return 0;
}

static int test_overlap_and_invalid_store(void)
{
    const uint8_t wire_a[] = {0x02u, 0u, 0u, 0xc1u};
    BasicVariableStore store, bad;
    BasicVariableEntry entries[2];
    BasicVariableKey key, before_key;
    BasicVariableValue value, before_value;
    size_t n = 19u;
    union {
        BasicVariableKey key;
        size_t consumed;
    } same_output;
    union {
        BasicVariableKey key;
        uint8_t bytes[sizeof(BasicVariableKey)];
    } alias;
    uint8_t snapshot[sizeof(alias)];
    size_t saved_n;

    CHECK(bvs_init(&store, entries, 2u) == BVS_OK);
    CHECK(resolve("A", BVR_TYPE_INTEGER, BVT_INTEGER, &key) == 0);
    CHECK(bvs_create(&store, &key, &n) == BVS_OK);
    CHECK(n == 0u);
    memset(&alias, 0x5au, sizeof(alias));
    memcpy(alias.bytes, wire_a, sizeof(wire_a));
    memcpy(snapshot, alias.bytes, sizeof(snapshot));
    CHECK(bvb_resolve_explicit(alias.bytes, sizeof(alias.bytes), 0u,
                               &alias.key, &n) == BVB_OVERLAPPING_MEMORY);
    CHECK(memcmp(alias.bytes, snapshot, sizeof(snapshot)) == 0);
    CHECK(bvb_resolve_explicit(wire_a, sizeof(wire_a), 0u,
                               &same_output.key, &same_output.consumed)
          == BVB_OVERLAPPING_MEMORY);

    memset(&value, 0xa5, sizeof(value));
    before_value = value;
    memset(&key, 0x5a, sizeof(key));
    before_key = key;
    n = 77u;
    saved_n = n;
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, &store,
                            &key, &n, &value) == BVB_OK);
    CHECK(n == 4u);
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, &store,
                            &entries[0].key, &n, &value)
          == BVB_OVERLAPPING_MEMORY);
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, &store,
                            &key, &n, &entries[0].value)
          == BVB_OVERLAPPING_MEMORY);
    CHECK(bvb_read_explicit((const uint8_t *)&entries[1], sizeof(wire_a),
                            0u, &store, &key, &n, &value)
          == BVB_OVERLAPPING_MEMORY);
    CHECK(bvb_read_explicit((const uint8_t *)&store, sizeof(wire_a),
                            0u, &store, &key, &n, &value)
          == BVB_OVERLAPPING_MEMORY);
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, &store,
                            &same_output.key, &same_output.consumed, &value)
          == BVB_OVERLAPPING_MEMORY);
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, &store,
                            &key, &n, (BasicVariableValue *)&key)
          == BVB_OVERLAPPING_MEMORY);
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, &store,
                            &key, &n, (BasicVariableValue *)&n)
          == BVB_OVERLAPPING_MEMORY);

    bad = store;
    bad.count = bad.capacity + 1u;
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, &bad,
                            &key, &n, &value) == BVB_INVALID_STORE);
    bad = store;
    bad.capacity = SIZE_MAX;
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, &bad,
                            &key, &n, &value) == BVB_INVALID_STORE);
    bad = store;
    bad.entries = NULL;
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, &bad,
                            &key, &n, &value) == BVB_INVALID_STORE);
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, NULL,
                            &key, &n, &value) == BVB_INVALID_ARGUMENT);
    CHECK(bvb_read_explicit(wire_a, sizeof(wire_a), 0u, &store,
                            &key, &n, NULL) == BVB_INVALID_ARGUMENT);

    /* A failure with *fully disjoint* caller outputs must be atomic too. */
    key = before_key;
    value = before_value;
    n = saved_n;
    CHECK(bvb_read_explicit(wire_a, 3u, 0u, &store,
                            &key, &n, &value) == BVB_TRUNCATED);
    CHECK(memcmp(&key, &before_key, sizeof(key)) == 0);
    CHECK(memcmp(&value, &before_value, sizeof(value)) == 0);
    CHECK(n == saved_n);
    return 0;
}

int main(void)
{
    CHECK(test_types_case_and_identity() == 0);
    CHECK(test_print_offset_and_cache() == 0);
    CHECK(test_values_and_missing() == 0);
    CHECK(test_invalid_references() == 0);
    CHECK(test_overlap_and_invalid_store() == 0);
    puts("basic_variable_binding: OK");
    return 0;
}
