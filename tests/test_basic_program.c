#include "basic_program.h"

#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: failed: %s\n", __FILE__, __LINE__, #x); \
    return 1; \
} } while (0)
#define OK(x) CHECK((x) == BP_OK)

static const uint8_t print_a[] = {0xbf, 0x20, 0x22, 0x41, 0x22};
static const uint8_t print_2[] = {0xbf, 0x20, 0x10};
/* F3 from J0.2: deduced from disassembly; NOT independently CPC-validated. */
static const uint8_t j02_f3[] = {
    0x0a,0x00,0x0a,0x00,0xbf,0x20,0x22,0x41,0x22,0x00,
    0x08,0x00,0x14,0x00,0xbf,0x20,0x10,0x00,0x00,0x00
};
static const uint8_t j02_f4[] = {
    0x0a,0x00,0x1e,0x00,0xa0,0x20,0x1e,0x14,0x00,0x00,0x00,0x00
};
static const uint8_t j02_f1bis[] = {
    0x0a,0x00,0x0a,0x00,0xbf,0x20,0x22,0x48,0x49,0x00,0x00,0x00
};

static int invariants(const BasicProgram *p, const uint16_t *numbers, size_t count)
{
    size_t cursor = 0;
    BasicProgramLine line;
    size_t i;
    CHECK(bp_validate(p) == BP_OK);
    for (i = 0; i < count; ++i) {
        CHECK(bp_next(p, &cursor, &line) == BP_OK);
        CHECK(line.number == numbers[i]);
        CHECK(line.offset < line.next_offset);
        CHECK(line.body_offset == line.offset + 4);
        CHECK(line.next_offset - line.offset == line.body_length + 5);
        CHECK(p->data[line.next_offset - 1] == 0);
        CHECK(cursor == line.next_offset);
    }
    CHECK(bp_next(p, &cursor, &line) == BP_END);
    CHECK(cursor == p->size - 2);
    return 0;
}

static int exercise_mutations(void)
{
    uint8_t storage[100];
    BasicProgram p;
    BasicProgramLine line;
    uint16_t n1[] = {10};
    uint16_t n2[] = {10, 20};
    uint16_t n3[] = {10, 20, 30};
    uint16_t after_delete[] = {20, 30};
    uint16_t last[] = {20};
    const uint8_t longer[] = {0xbf,0x20,0x22,0x41,0,0x42,0x22};
    const uint8_t shorter[] = {0};
    const uint8_t empty[] = {0, 0};
    uint8_t exported[100];
    size_t written = 0;

    OK(bp_init(&p, storage, sizeof(storage)));
    CHECK(p.size == 2 && p.data[0] == 0 && p.data[1] == 0);
    CHECK(invariants(&p, NULL, 0) == 0);
    OK(bp_put(&p, 20, print_2, sizeof(print_2)));
    n1[0] = 20;
    CHECK(invariants(&p, n1, 1) == 0);
    OK(bp_put(&p, 10, print_a, sizeof(print_a)));
    CHECK(invariants(&p, n2, 2) == 0);
    CHECK(p.size == sizeof(j02_f3));
    CHECK(memcmp(p.data, j02_f3, sizeof(j02_f3)) == 0);
    OK(bp_put(&p, 30, print_2, sizeof(print_2)));
    CHECK(invariants(&p, n3, 3) == 0);
    OK(bp_find(&p, 20, &line));
    CHECK(line.offset == 10 && line.body_length == sizeof(print_2));
    CHECK(memcmp(p.data + line.body_offset, print_2, sizeof(print_2)) == 0);
    CHECK(bp_find(&p, 15, &line) == BP_NOT_FOUND);
    CHECK(bp_find(&p, 0, &line) == BP_INVALID_LINE_NUMBER);

    OK(bp_put(&p, 20, longer, sizeof(longer)));
    CHECK(invariants(&p, n3, 3) == 0);
    OK(bp_find(&p, 20, &line));
    CHECK(line.body_length == sizeof(longer));
    CHECK(memcmp(p.data + line.body_offset, longer, sizeof(longer)) == 0);
    OK(bp_put(&p, 20, shorter, sizeof(shorter)));
    CHECK(invariants(&p, n3, 3) == 0);
    OK(bp_find(&p, 20, &line));
    CHECK(line.body_length == 1 && p.data[line.body_offset] == 0);
    CHECK(p.data[line.next_offset - 1] == 0); /* different zero */

    OK(bp_export(&p, exported, sizeof(exported), &written));
    CHECK(written == p.size && memcmp(exported, p.data, written) == 0);
    OK(bp_delete(&p, 10));
    CHECK(invariants(&p, after_delete, 2) == 0);
    OK(bp_delete(&p, 30));
    CHECK(invariants(&p, last, 1) == 0);
    CHECK(bp_delete(&p, 30) == BP_NOT_FOUND);
    OK(bp_delete(&p, 20));
    CHECK(invariants(&p, NULL, 0) == 0);
    OK(bp_put(&p, 65535, empty, sizeof(empty)));
    OK(bp_find(&p, 65535, &line));
    CHECK(line.body_length == sizeof(empty));
    OK(bp_delete(&p, 65535));
    CHECK(p.size == 2);
    return 0;
}

static int exercise_imports(void)
{
    uint8_t storage[100] = {0};
    uint8_t exported[100] = {0};
    BasicProgram p;
    BasicProgramLine line;
    size_t written;
    static const uint8_t empty[] = {0, 0};
    uint16_t order[] = {10, 20};

    OK(bp_init(&p, storage, sizeof(storage)));
    OK(bp_import(&p, j02_f3, sizeof(j02_f3)));
    CHECK(invariants(&p, order, 2) == 0);
    OK(bp_export(&p, exported, sizeof(exported), &written));
    CHECK(written == sizeof(j02_f3));
    CHECK(memcmp(exported, j02_f3, written) == 0);
    OK(bp_import(&p, j02_f4, sizeof(j02_f4)));
    OK(bp_find(&p, 30, &line));
    CHECK(line.body_length == 5 && p.data[line.body_offset + 4] == 0);
    CHECK(bp_validate(&p) == BP_OK);
    OK(bp_import(&p, j02_f1bis, sizeof(j02_f1bis)));
    OK(bp_find(&p, 10, &line));
    CHECK(line.body_length == 5 && p.data[line.body_offset + 2] == 0x22);
    OK(bp_import(&p, empty, sizeof(empty)));
    CHECK(p.size == 2);
    return 0;
}

static int test_rejection(const uint8_t *image, size_t length)
{
    uint8_t storage[32] = {0};
    uint8_t snapshot[32];
    BasicProgram p;
    size_t old_size;
    BPStatus status;
    OK(bp_init(&p, storage, sizeof(storage)));
    OK(bp_put(&p, 10, print_2, sizeof(print_2)));
    memcpy(snapshot, storage, sizeof(storage));
    old_size = p.size;
    status = bp_import(&p, image, length);
    CHECK(status != BP_OK);
    CHECK(p.size == old_size);
    CHECK(memcmp(snapshot, storage, sizeof(storage)) == 0);
    CHECK(bp_validate(&p) == BP_OK);
    return 0;
}

static int exercise_malformed(void)
{
    const uint8_t tiny[] = {0};
    const uint8_t too_short[] = {4,0,10,0,0,0,0};
    const uint8_t overrun[] = {9,0,10,0,0,0,0};
    const uint8_t invalid_zero[] = {5,0,0,0,0,0,0};
    const uint8_t invalid_eol[] = {5,0,1,0,0x31,0,0};
    const uint8_t no_sentinel[] = {5,0,1,0,0};
    const uint8_t truncated_sentinel[] = {5,0,1,0,0,0};
    const uint8_t trailing[] = {0,0,7};
    const uint8_t duplicate[] = {5,0,10,0,0,5,0,10,0,0,0,0};
    const uint8_t unordered[] = {5,0,20,0,0,5,0,10,0,0,0,0};
    const uint8_t only_eol[] = {5,0,1,0,0,0,0};
    uint8_t bad_storage[8] = {0,0,0,0,0,0,0,0};
    BasicProgram p;
    size_t cursor = 0;
    BasicProgramLine line;

    CHECK(bp_validate_image(NULL, 0) == BP_INVALID_ARGUMENT);
    CHECK(bp_validate_image(tiny, sizeof(tiny)) == BP_TRUNCATED);
    CHECK(bp_validate_image(too_short, sizeof(too_short)) == BP_BAD_FORMAT);
    CHECK(bp_validate_image(overrun, sizeof(overrun)) == BP_TRUNCATED);
    CHECK(bp_validate_image(invalid_zero, sizeof(invalid_zero)) == BP_BAD_FORMAT);
    CHECK(bp_validate_image(invalid_eol, sizeof(invalid_eol)) == BP_BAD_FORMAT);
    CHECK(bp_validate_image(no_sentinel, sizeof(no_sentinel)) == BP_TRUNCATED);
    CHECK(bp_validate_image(truncated_sentinel, sizeof(truncated_sentinel)) == BP_TRUNCATED);
    CHECK(bp_validate_image(trailing, sizeof(trailing)) == BP_BAD_FORMAT);
    CHECK(bp_validate_image(duplicate, sizeof(duplicate)) == BP_BAD_FORMAT);
    CHECK(bp_validate_image(unordered, sizeof(unordered)) == BP_BAD_FORMAT);
    CHECK(bp_validate_image(only_eol, sizeof(only_eol)) == BP_OK);
    CHECK(test_rejection(too_short, sizeof(too_short)) == 0);
    CHECK(test_rejection(overrun, sizeof(overrun)) == 0);
    CHECK(test_rejection(invalid_zero, sizeof(invalid_zero)) == 0);
    CHECK(test_rejection(invalid_eol, sizeof(invalid_eol)) == 0);
    CHECK(test_rejection(no_sentinel, sizeof(no_sentinel)) == 0);
    CHECK(test_rejection(trailing, sizeof(trailing)) == 0);
    CHECK(test_rejection(duplicate, sizeof(duplicate)) == 0);
    CHECK(test_rejection(unordered, sizeof(unordered)) == 0);
    CHECK(bp_init(&p, bad_storage, 1) == BP_NO_SPACE);
    OK(bp_init(&p, bad_storage, sizeof(bad_storage)));
    CHECK(bp_next(&p, &cursor, &line) == BP_END);
    p.size = sizeof(bad_storage) + 1;
    CHECK(bp_validate(&p) == BP_BAD_FORMAT);
    CHECK(bp_next(&p, &cursor, &line) == BP_INVALID_ARGUMENT);
    return 0;
}

static int exercise_atomicity(void)
{
    uint8_t storage[16];
    uint8_t before[16];
    uint8_t dest[16];
    BasicProgram p;
    size_t original;
    size_t written = 123;
    const uint8_t larger[] = {1,2,3,4,5,6,7,8,9,10};
    OK(bp_init(&p, storage, sizeof(storage)));
    OK(bp_put(&p, 10, print_2, sizeof(print_2)));
    original = p.size;
    memcpy(before, storage, sizeof(storage));
    CHECK(bp_put(&p, 20, larger, sizeof(larger)) == BP_NO_SPACE);
    CHECK(bp_put(&p, 10, larger, sizeof(larger)) == BP_NO_SPACE);
    CHECK(bp_put(&p, 30, larger, 65531) == BP_OVERFLOW);
    CHECK(bp_put(&p, 0, print_2, sizeof(print_2)) == BP_INVALID_LINE_NUMBER);
    CHECK(bp_put(&p, 10, NULL, 1) == BP_INVALID_ARGUMENT);
    CHECK(bp_put(&p, 20, p.data + 4, 2) == BP_OVERLAP);
    CHECK(bp_import(&p, p.data, p.size) == BP_OVERLAP);
    CHECK(bp_export(&p, p.data, p.capacity, &written) == BP_OVERLAP);
    CHECK(bp_export(&p, dest, 3, &written) == BP_NO_SPACE);
    CHECK(written == 123);
    CHECK(bp_delete(&p, 0) == BP_INVALID_LINE_NUMBER);
    CHECK(bp_delete(&p, 99) == BP_NOT_FOUND);
    CHECK(p.size == original && memcmp(before, storage, sizeof(storage)) == 0);
    CHECK(bp_validate(&p) == BP_OK);
    return 0;
}

/* Deterministic mutation stress: validates sorted offsets and image on every
 * operation, including replacement by shorter / longer raw binary payloads. */
static int exercise_stress(void)
{
    uint8_t storage[4096];
    uint8_t payload[17];
    BasicProgram p;
    uint16_t expected[64];
    size_t count = 0;
    unsigned int seed = 0x12345678u;
    size_t step;
    OK(bp_init(&p, storage, sizeof(storage)));
    for (step = 0; step < 500; ++step) {
        uint16_t number;
        size_t length, pos = 0, i;
        int delete_line;
        seed = seed * 1664525u + 1013904223u;
        number = (uint16_t)(1u + seed % 64u);
        seed = seed * 1664525u + 1013904223u;
        length = (size_t)(seed % 18u);
        delete_line = (seed & 8u) != 0u;
        for (i = 0; i < length; ++i) {
            payload[i] = (uint8_t)((i % 2u) == 0u ? 0u : (seed >> (i % 24u)));
        }
        while (pos < count && expected[pos] < number) {
            ++pos;
        }
        if (delete_line) {
            BPStatus status = bp_delete(&p, number);
            CHECK(status == (pos < count && expected[pos] == number ? BP_OK : BP_NOT_FOUND));
            if (status == BP_OK) {
                memmove(expected + pos, expected + pos + 1,
                        (count - pos - 1) * sizeof(expected[0]));
                --count;
            }
        } else {
            OK(bp_put(&p, number, payload, length));
            if (pos == count || expected[pos] != number) {
                memmove(expected + pos + 1, expected + pos,
                        (count - pos) * sizeof(expected[0]));
                expected[pos] = number;
                ++count;
            }
        }
        CHECK(invariants(&p, expected, count) == 0);
    }
    return 0;
}

int main(void)
{
    CHECK(exercise_mutations() == 0);
    CHECK(exercise_imports() == 0);
    CHECK(exercise_malformed() == 0);
    CHECK(exercise_atomicity() == 0);
    CHECK(exercise_stress() == 0);
    puts("basic_program: all tests passed");
    return 0;
}
