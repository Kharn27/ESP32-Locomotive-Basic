#include "basic_variable_store.h"

#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(e) do { if (!(e)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #e); return 1; } } while (0)

static BasicVariableKey key_of(const char *name, BasicVariableType type)
{
    BasicVariableKey key;
    size_t i, n = strlen(name);
    memset(&key, 0, sizeof(key));
    key.type = (uint8_t)type;
    key.name_length = (uint8_t)n;
    for (i = 0u; i < n && i < sizeof(key.name); ++i) {
        key.name[i] = (uint8_t)name[i];
    }
    return key;
}

static BasicVariableValue int_of(int16_t n)
{
    BasicVariableValue v;
    memset(&v, 0, sizeof(v));
    v.type = (uint8_t)BVT_INTEGER;
    v.data.integer = n;
    return v;
}

static BasicVariableValue real_of(const uint8_t data[5])
{
    BasicVariableValue v;
    memset(&v, 0, sizeof(v));
    v.type = (uint8_t)BVT_REAL;
    memcpy(v.data.real5, data, 5u);
    return v;
}

static BasicVariableValue str_of(uint32_t offset, uint32_t len)
{
    BasicVariableValue v;
    memset(&v, 0, sizeof(v));
    v.type = (uint8_t)BVT_STRING;
    v.data.string.offset = offset;
    v.data.string.length = len;
    return v;
}

static int empty_and_init(void)
{
    BasicVariableEntry entries[2];
    BasicVariableStore s;
    BasicVariableKey k = key_of("A", BVT_INTEGER);
    size_t i, pos = 987u;
    memset(entries, 0xa5, sizeof(entries));
    CHECK(bvs_init(&s, entries, 2u) == BVS_OK);
    CHECK(s.capacity == 2u && s.count == 0u && s.entries == entries);
    for (i = 0u; i < sizeof(entries); ++i) {
        CHECK(((const uint8_t *)entries)[i] == 0u);
    }
    CHECK(bvs_find(&s, &k, &pos) == BVS_NOT_FOUND);
    CHECK(pos == 987u && s.count == 0u);
    CHECK(bvs_init(&s, NULL, 0u) == BVS_OK);
    CHECK(bvs_find(&s, &k, &pos) == BVS_NOT_FOUND);
    CHECK(bvs_create(&s, &k, &pos) == BVS_FULL);
    CHECK(pos == 987u && s.count == 0u);
    CHECK(bvs_reset(&s) == BVS_OK);
    return 0;
}

static int identity_and_long_names(void)
{
    BasicVariableEntry entries[6];
    BasicVariableStore s;
    BasicVariableKey a = key_of("ABCDEFGH1234567890", BVT_INTEGER);
    BasicVariableKey b = key_of("ABCDEFGH1234567891", BVT_INTEGER);
    BasicVariableKey c = key_of("A.B", BVT_INTEGER);
    BasicVariableKey d = key_of("AB", BVT_INTEGER);
    BasicVariableKey e = key_of("ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMN", BVT_REAL);
    BasicVariableKey f = key_of("ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMO", BVT_REAL);
    BasicVariableValue v = int_of(79), read;
    size_t index = 777u;
    CHECK(e.name_length == 40u && f.name_length == 40u);
    CHECK(memcmp(e.name, f.name, 39u) == 0 && e.name[39] != f.name[39]);
    CHECK(bvs_init(&s, entries, 6u) == BVS_OK);
    CHECK(bvs_create(&s, &a, &index) == BVS_OK && index == 0u);
    CHECK(bvs_set(&s, &a, &v) == BVS_OK);
    index = 777u;
    CHECK(bvs_create(&s, &a, &index) == BVS_ALREADY_EXISTS);
    CHECK(index == 777u && s.count == 1u);
    CHECK(bvs_get(&s, &a, &read) == BVS_OK && read.data.integer == 79);
    CHECK(bvs_create(&s, &b, &index) == BVS_OK && index == 1u);
    CHECK(bvs_create(&s, &c, &index) == BVS_OK && index == 2u);
    CHECK(bvs_create(&s, &d, &index) == BVS_OK && index == 3u);
    CHECK(bvs_create(&s, &e, &index) == BVS_OK && index == 4u);
    CHECK(bvs_create(&s, &f, &index) == BVS_OK && index == 5u);
    CHECK(bvs_find(&s, &e, &index) == BVS_OK && index == 4u);
    CHECK(bvs_find(&s, &f, &index) == BVS_OK && index == 5u);
    CHECK(memcmp(entries[4].key.name, e.name, 40u) == 0);
    CHECK(memcmp(entries[5].key.name, f.name, 40u) == 0);
    CHECK(memcmp(entries[0].key.name, a.name, 18u) == 0);
    CHECK(entries[0].value.data.integer == 79 && entries[1].value.data.integer == 0);
    return 0;
}

static int types_and_values(void)
{
    BasicVariableEntry entries[3];
    BasicVariableStore s;
    BasicVariableKey ik = key_of("A", BVT_INTEGER);
    BasicVariableKey rk = key_of("A", BVT_REAL);
    BasicVariableKey sk = key_of("A", BVT_STRING);
    BasicVariableValue v, read;
    static const uint8_t zero[5] = {0u,0u,0u,0u,0u};
    static const uint8_t raw[5] = {0x80u,0x01u,0x00u,0xffu,0x7fu};
    size_t pos;
    CHECK(bvs_init(&s, entries, 3u) == BVS_OK);
    CHECK(bvs_create(&s, &ik, &pos) == BVS_OK);
    CHECK(bvs_create(&s, &rk, &pos) == BVS_OK);
    CHECK(bvs_create(&s, &sk, &pos) == BVS_OK);
    CHECK(s.count == 3u);
    CHECK(bvs_get(&s, &ik, &read) == BVS_OK);
    CHECK(read.type == (uint8_t)BVT_INTEGER && read.data.integer == 0);
    CHECK(bvs_get(&s, &rk, &read) == BVS_OK);
    CHECK(read.type == (uint8_t)BVT_REAL && memcmp(read.data.real5, zero, 5u) == 0);
    CHECK(bvs_get(&s, &sk, &read) == BVS_OK);
    CHECK(read.type == (uint8_t)BVT_STRING && read.data.string.offset == 0u &&
          read.data.string.length == 0u);
    CHECK(entries[0].key.type == 2u && entries[1].key.type == 5u && entries[2].key.type == 3u);
    v = int_of(INT16_MIN);
    CHECK(bvs_set(&s, &ik, &v) == BVS_OK);
    CHECK(bvs_get(&s, &ik, &read) == BVS_OK && read.data.integer == INT16_MIN);
    CHECK(entries[0].value.data.integer == INT16_MIN);
    v = int_of(INT16_MAX);
    CHECK(bvs_set(&s, &ik, &v) == BVS_OK);
    CHECK(bvs_get(&s, &ik, &read) == BVS_OK && read.data.integer == INT16_MAX);
    CHECK(entries[0].value.data.integer == INT16_MAX);
    v = real_of(raw);
    CHECK(bvs_set(&s, &rk, &v) == BVS_OK);
    CHECK(bvs_get(&s, &rk, &read) == BVS_OK);
    CHECK(read.type == (uint8_t)BVT_REAL && memcmp(read.data.real5, raw, 5u) == 0);
    CHECK(memcmp(entries[1].value.data.real5, raw, 5u) == 0);
    return 0;
}

static int full_and_error_atomicity(void)
{
    BasicVariableEntry entries[1], saved[1];
    BasicVariableStore s;
    BasicVariableKey a = key_of("A", BVT_INTEGER), b = key_of("B", BVT_INTEGER);
    BasicVariableValue v = int_of(1234), wrong = str_of(0u, 0u), read, before;
    size_t pos = 444u;
    CHECK(bvs_init(&s, entries, 1u) == BVS_OK);
    CHECK(bvs_create(&s, &a, &pos) == BVS_OK);
    CHECK(bvs_set(&s, &a, &v) == BVS_OK);
    memcpy(saved, entries, sizeof(saved));
    pos = 444u;
    CHECK(bvs_create(&s, &b, &pos) == BVS_FULL);
    CHECK(pos == 444u && s.count == 1u && memcmp(entries, saved, sizeof(saved)) == 0);
    CHECK(bvs_create(&s, &a, &pos) == BVS_ALREADY_EXISTS);
    CHECK(memcmp(entries, saved, sizeof(saved)) == 0);
    CHECK(bvs_set(&s, &a, &wrong) == BVS_INVALID_TYPE);
    CHECK(bvs_set(&s, &b, &v) == BVS_NOT_FOUND);
    CHECK(memcmp(entries, saved, sizeof(saved)) == 0);
    memset(&read, 0xa5, sizeof(read));
    before = read;
    CHECK(bvs_get(&s, &b, &read) == BVS_NOT_FOUND);
    CHECK(memcmp(&read, &before, sizeof(read)) == 0);
    CHECK(bvs_get(&s, &a, &read) == BVS_OK && read.data.integer == 1234);
    return 0;
}

static int strings_and_reset(void)
{
    BasicVariableEntry entries[2], saved[2];
    BasicVariableStore s;
    BasicVariableKey sk = key_of("S", BVT_STRING), ik = key_of("I", BVT_INTEGER);
    BasicVariableValue empty = str_of(0u,0u), nonempty, read;
    size_t pos, i;
    CHECK(bvs_init(&s, entries, 2u) == BVS_OK);
    CHECK(bvs_create(&s, &sk, &pos) == BVS_OK);
    CHECK(bvs_set(&s, &sk, &empty) == BVS_OK);
    memcpy(saved, entries, sizeof(saved));
    nonempty = str_of(4u,6u);
    CHECK(bvs_set(&s, &sk, &nonempty) == BVS_UNSUPPORTED_STRING);
    nonempty = str_of(0u,1u);
    CHECK(bvs_set(&s, &sk, &nonempty) == BVS_UNSUPPORTED_STRING);
    nonempty = str_of(1u,0u);
    CHECK(bvs_set(&s, &sk, &nonempty) == BVS_UNSUPPORTED_STRING);
    CHECK(memcmp(saved, entries, sizeof(saved)) == 0);
    CHECK(bvs_get(&s, &sk, &read) == BVS_OK);
    CHECK(read.type == (uint8_t)BVT_STRING &&
          read.data.string.offset == 0u && read.data.string.length == 0u);
    CHECK(bvs_create(&s, &ik, &pos) == BVS_OK);
    CHECK(bvs_reset(&s) == BVS_OK && s.count == 0u);
    for (i = 0u; i < sizeof(entries); ++i) {
        CHECK(((const uint8_t *)entries)[i] == 0u);
    }
    CHECK(bvs_find(&s, &sk, &pos) == BVS_NOT_FOUND);
    CHECK(bvs_create(&s, &ik, &pos) == BVS_OK && pos == 0u);
    CHECK(bvs_get(&s, &ik, &read) == BVS_OK && read.data.integer == 0);
    return 0;
}

static int invalid_and_corrupt(void)
{
    BasicVariableEntry entries[1], saved[1];
    BasicVariableStore s, old;
    BasicVariableKey k = key_of("A", BVT_INTEGER), bad;
    BasicVariableValue value = int_of(1);
    size_t pos = 333u;
    CHECK(bvs_init(&s, entries, 1u) == BVS_OK);
    CHECK(bvs_init(NULL, entries, 1u) == BVS_INVALID_ARGUMENT);
    CHECK(bvs_init(&s, NULL, 1u) == BVS_INVALID_ARGUMENT);
    CHECK(bvs_init(&s, entries, 0u) == BVS_INVALID_ARGUMENT);
    CHECK(bvs_init(&s, entries, SIZE_MAX) == BVS_INVALID_ARGUMENT);
    CHECK(s.count == 0u && s.capacity == 1u);
    CHECK(bvs_find(NULL, &k, &pos) == BVS_INVALID_ARGUMENT);
    CHECK(bvs_find(&s, NULL, &pos) == BVS_INVALID_ARGUMENT);
    CHECK(bvs_find(&s, &k, NULL) == BVS_INVALID_ARGUMENT);
    CHECK(bvs_create(&s, NULL, &pos) == BVS_INVALID_ARGUMENT);
    CHECK(bvs_get(&s, &k, NULL) == BVS_INVALID_ARGUMENT);
    CHECK(bvs_set(&s, &k, NULL) == BVS_INVALID_ARGUMENT);
    bad = k; bad.type = 4u;
    CHECK(bvs_create(&s, &bad, &pos) == BVS_INVALID_KEY);
    bad = k; bad.name_length = 41u;
    CHECK(bvs_create(&s, &bad, &pos) == BVS_INVALID_KEY);
    bad = k; bad.name[0] = (uint8_t)'a';
    CHECK(bvs_create(&s, &bad, &pos) == BVS_INVALID_KEY);
    bad = k; bad.name[1] = (uint8_t)'X';
    CHECK(bvs_create(&s, &bad, &pos) == BVS_INVALID_KEY);
    CHECK(s.count == 0u && pos == 333u);
    CHECK(bvs_create(&s, &k, &pos) == BVS_OK);
    old = s;
    memcpy(saved, entries, sizeof(saved));
    s.count = 2u;
    CHECK(bvs_get(&s, &k, &value) == BVS_INVALID_STORE);
    CHECK(bvs_reset(&s) == BVS_INVALID_STORE);
    s = old; s.capacity = SIZE_MAX;
    CHECK(bvs_find(&s, &k, &pos) == BVS_INVALID_STORE);
    s = old;
    entries[0].value.type = 4u;
    CHECK(bvs_get(&s, &k, &value) == BVS_INVALID_STORE);
    entries[0] = saved[0]; entries[0].key.name_length = 0u;
    CHECK(bvs_get(&s, &k, &value) == BVS_INVALID_STORE);
    entries[0] = saved[0]; entries[0].value.type = (uint8_t)BVT_REAL;
    CHECK(bvs_set(&s, &k, &value) == BVS_INVALID_STORE);
    entries[0] = saved[0];
    CHECK(bvs_get(&s, &k, &value) == BVS_OK && value.data.integer == 0);
    return 0;
}

static int source_integrity_and_overlaps(void)
{
    static const uint8_t program[] = {0x06u,0x00u,0x0au,0x00u,0x02u,0x00u,0x00u,0xc1u,0x00u};
    uint8_t copy[sizeof(program)];
    BasicVariableEntry entries[2], saved[2];
    BasicVariableStore s;
    BasicVariableKey k = key_of("A", BVT_INTEGER), old = k;
    BasicVariableValue v = int_of(-10), read;
    size_t pos;
    union { BasicVariableStore s; BasicVariableEntry entries[2]; } alias;
    memcpy(copy, program, sizeof(copy));
    CHECK(bvs_init(&alias.s, alias.entries, 2u) == BVS_OVERLAPPING_MEMORY);
    CHECK(bvs_init(&s, entries, 2u) == BVS_OK);
    CHECK(bvs_create(&s, &k, &pos) == BVS_OK);
    CHECK(bvs_set(&s, &k, &v) == BVS_OK);
    CHECK(memcmp(&k, &old, sizeof(k)) == 0);
    CHECK(memcmp(copy, program, sizeof(program)) == 0);
    CHECK(memcmp(&entries[0].key, &k, sizeof(k)) == 0);
    memcpy(saved, entries, sizeof(saved));
    CHECK(bvs_set(&s, &entries[0].key, &v) == BVS_OVERLAPPING_MEMORY);
    CHECK(bvs_set(&s, &k, &entries[0].value) == BVS_OVERLAPPING_MEMORY);
    CHECK(bvs_get(&s, &k, &entries[0].value) == BVS_OVERLAPPING_MEMORY);
    CHECK(bvs_find(&s, &k, (size_t *)(void *)entries) == BVS_OVERLAPPING_MEMORY);
    CHECK(bvs_create(&s, &k, (size_t *)(void *)entries) == BVS_OVERLAPPING_MEMORY);
    CHECK(bvs_find(&s, (BasicVariableKey *)(void *)&s, &pos) ==
          BVS_OVERLAPPING_MEMORY);
    CHECK(bvs_get(&s, &k, (BasicVariableValue *)(void *)&s) ==
          BVS_OVERLAPPING_MEMORY);
    CHECK(memcmp(entries, saved, sizeof(saved)) == 0 && s.count == 1u);
    CHECK(bvs_get(&s, &k, &read) == BVS_OK && read.data.integer == -10);
    return 0;
}

int main(void)
{
    CHECK(empty_and_init() == 0);
    CHECK(identity_and_long_names() == 0);
    CHECK(types_and_values() == 0);
    CHECK(full_and_error_atomicity() == 0);
    CHECK(strings_and_reset() == 0);
    CHECK(invalid_and_corrupt() == 0);
    CHECK(source_integrity_and_overlaps() == 0);
    printf("basic_variable_store: OK (synthetic fixtures; entry=%zu, value=%zu, store=%zu)\n",
           sizeof(BasicVariableEntry), sizeof(BasicVariableValue),
           sizeof(BasicVariableStore));
    return 0;
}
