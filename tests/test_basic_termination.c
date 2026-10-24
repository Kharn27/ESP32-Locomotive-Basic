#include "basic_session_runtime.h"
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", \
    __FILE__, __LINE__, #x); return 1; } } while (0)

typedef struct {
    BasicProgram p;
    BasicSessionRuntime r;
    uint8_t storage[2048], temp[512], out[2048];
    size_t written;
} Fixture;

static int setup(Fixture *f)
{
    memset(f, 0xa5, sizeof(*f));
    CHECK(bp_init(&f->p, f->storage, sizeof(f->storage)) == BP_OK);
    CHECK(bsr_init(&f->r, &f->p).status == BSR_OK);
    return 0;
}

static BSRResult submit(Fixture *f, const char *s)
{
    return bsr_submit(&f->r, (const uint8_t *)s, strlen(s),
                      f->temp, sizeof(f->temp), f->out, sizeof(f->out),
                      &f->written);
}

static int encode(const char *s, const uint8_t *expected, size_t n)
{
    uint8_t body[256], listing[256], again[256];
    size_t len = 987u, textlen = 876u, roundlen = 765u;
    memset(body, 0x44, sizeof(body));
    CHECK(bt_tokenize((const uint8_t *)s, strlen(s),
                      body, sizeof(body), &len) == BT_OK);
    CHECK(len == n && memcmp(body, expected, n) == 0);
    CHECK(body[n] == 0x44u);
    CHECK(bl_detokenize(body, len, listing,
                        sizeof(listing), &textlen) == BL_OK);
    CHECK(bt_tokenize(listing, textlen, again,
                      sizeof(again), &roundlen) == BT_OK);
    CHECK(roundlen == len && memcmp(body, again, len) == 0);
    return 0;
}

static int test_tokens(void)
{
    static const uint8_t end[] = {0x98u};
    static const uint8_t spaced[] = {' ', 0x98u, ' ', ' '};
    static const uint8_t colon[] = {0x98u, 0x01u, 0xbfu, ' ', '"', 'X', '"'};
    static const uint8_t print[] = {0xbfu, ' ', '"', 'E', 'N', 'D', '"'};
    static const uint8_t rem[] = {0xc5u, ' ', 'E', 'N', 'D', ':', 'X'};
    static const uint8_t ap[] = {0x01u, 0xc0u, ' ', 'E', 'N', 'D'};
    static const char *invalid[] = {
        "ENDLESS", "END0", "END.", "END_", "END$", "END!",
        "END 1", "END PRINT", "END:", "END::PRINT 1"
    };
    uint8_t raw[] = {'P','R','I','N','T',' ','"',0x98u,'"'};
    uint8_t body[64], text[64], again[64];
    size_t n, t, a, i;
    CHECK(encode("END", end, sizeof(end)) == 0);
    CHECK(encode("end", end, sizeof(end)) == 0);
    CHECK(encode("EnD", end, sizeof(end)) == 0);
    CHECK(encode(" END  ", spaced, sizeof(spaced)) == 0);
    CHECK(encode("END:PRINT \"X\"", colon, sizeof(colon)) == 0);
    CHECK(encode("PRINT \"END\"", print, sizeof(print)) == 0);
    CHECK(encode("REM END:X", rem, sizeof(rem)) == 0);
    CHECK(encode("' END", ap, sizeof(ap)) == 0);
    CHECK(encode("PRINT \"X\":END",
          (const uint8_t[]){0xbfu,' ','"','X','"',0x01u,0x98u}, 7u) == 0);
    CHECK(bt_tokenize(raw, sizeof(raw), body, sizeof(body), &n) == BT_OK);
    CHECK(n == 5u && body[3] == 0x98u);
    CHECK(bl_detokenize(body, n, text, sizeof(text), &t) == BL_OK);
    CHECK(bt_tokenize(text, t, again, sizeof(again), &a) == BT_OK);
    CHECK(a == n && memcmp(body, again, n) == 0);
    for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        n = 777u;
        memset(body, 0x77, sizeof(body));
        CHECK(bt_tokenize((const uint8_t *)invalid[i], strlen(invalid[i]),
                          body, sizeof(body), &n) != BT_OK);
        CHECK(n == 777u && body[0] == 0x77u);
    }
    return 0;
}

static int step(Fixture *f, const char *expected, size_t capacity)
{
    size_t n = strlen(expected);
    memset(f->out, 0x77, sizeof(f->out));
    f->written = 777u;
    CHECK(bsr_step(&f->r, f->out, capacity, &f->written).status == BSR_OK);
    CHECK(f->written == n && memcmp(f->out, expected, n) == 0);
    CHECK(f->out[n] == 0x77u);
    return 0;
}

static int ended(Fixture *f)
{
    size_t pos = f->r.executor.cursor;
    BSRResult result;
    CHECK(pos == f->p.size - 2u && f->r.state == BSR_RUNNING);
    f->written = 999u;
    memset(f->out, 0x66, sizeof(f->out));
    result = bsr_step(&f->r, f->out, sizeof(f->out), &f->written);
    CHECK(result.status == BSR_END && result.executor_status == BE_END);
    CHECK(f->r.state == BSR_IDLE && f->r.executor.cursor == pos);
    CHECK(f->written == 999u && f->out[0] == 0x66u);
    CHECK(bsr_step(&f->r, f->out, sizeof(f->out),
                   &f->written).status == BSR_NOT_RUNNING);
    return 0;
}

static int test_stop_and_list(void)
{
    Fixture f;
    const char *list = "10 PRINT \"AVANT\"\n20 END\n30 PRINT \"INTERDIT\"\n";
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "30 PRINT \"INTERDIT\"").status == BSR_OK);
    CHECK(submit(&f, "20 eNd").status == BSR_OK);
    CHECK(submit(&f, "10 PRINT \"AVANT\"").status == BSR_OK);
    CHECK(submit(&f, "LIST").status == BSR_OK);
    CHECK(f.written == strlen(list) && memcmp(f.out, list, f.written) == 0);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(step(&f, "AVANT\n", sizeof(f.out)) == 0);
    CHECK(step(&f, "", 0u) == 0);
    CHECK(ended(&f) == 0);
    CHECK(submit(&f, "LIST").status == BSR_OK);
    CHECK(f.written == strlen(list) && memcmp(f.out, list, f.written) == 0);
    CHECK(submit(&f, "END").status == BSR_SESSION_ERROR);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(step(&f, "AVANT\n", sizeof(f.out)) == 0);
    CHECK(step(&f, "", 0u) == 0);
    CHECK(ended(&f) == 0);
    return 0;
}

static int test_same_line(void)
{
    Fixture f;
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "10 PRINT \"A\":END:PRINT \"B\"").status == BSR_OK);
    CHECK(submit(&f, "20 PRINT \"C\"").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(step(&f, "A\n", 2u) == 0);
    CHECK(ended(&f) == 0);
    CHECK(submit(&f, "NEW").status == BSR_OK);
    CHECK(submit(&f, "10 END:PRINT \"INVISIBLE\"").status == BSR_OK);
    CHECK(submit(&f, "20 PRINT \"HIDDEN\"").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(step(&f, "", 0u) == 0);
    CHECK(ended(&f) == 0);
    CHECK(submit(&f, "NEW").status == BSR_OK);
    CHECK(submit(&f, "10   END  ").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(step(&f, "", 0u) == 0);
    CHECK(ended(&f) == 0);
    return 0;
}

static int test_goto_and_comments(void)
{
    Fixture f;
    CHECK(setup(&f) == 0);
    CHECK(submit(&f, "10 GOTO 30:END").status == BSR_OK);
    CHECK(submit(&f, "20 PRINT \"SKIP\"").status == BSR_OK);
    CHECK(submit(&f, "30 PRINT \"END\":REM END:PRINT \"HIDDEN\"").status == BSR_OK);
    CHECK(submit(&f, "40 ' END:PRINT \"HIDDEN\"").status == BSR_OK);
    CHECK(submit(&f, "50 END").status == BSR_OK);
    CHECK(submit(&f, "60 PRINT \"SKIP\"").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(step(&f, "", 0u) == 0); /* GOTO bypasses END. */
    CHECK(step(&f, "END\n", sizeof(f.out)) == 0);
    CHECK(step(&f, "", 0u) == 0); /* Apostrophe comment. */
    CHECK(step(&f, "", 0u) == 0);
    CHECK(ended(&f) == 0);
    return 0;
}

static int test_atomicity(void)
{
    Fixture f;
    BasicSessionRuntime before;
    BSRResult result;
    uint8_t buf[64], snapshot[64];
    uint8_t bad[] = {0x98u, 'X'}, good[] = {0x98u};
    size_t n = 1001u;
    CHECK(setup(&f) == 0);
    memset(buf, 0x55, sizeof(buf));
    memcpy(snapshot, buf, sizeof(snapshot));
    CHECK(bt_tokenize((const uint8_t *)"END", 3u, buf, 0u, &n) == BT_NO_SPACE);
    CHECK(bl_detokenize(good, sizeof(good), buf, 2u, &n) == BL_NO_SPACE);
    CHECK(n == 1001u && memcmp(buf, snapshot, sizeof(buf)) == 0);
    CHECK(submit(&f, "10 PRINT \"AB\":END").status == BSR_OK);
    CHECK(submit(&f, "20 PRINT \"NO\"").status == BSR_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    before = f.r;
    memset(f.out, 0x33, sizeof(f.out));
    f.written = 789u;
    result = bsr_step(&f.r, f.out, 1u, &f.written);
    CHECK(result.status == BSR_EXECUTOR_ERROR &&
          result.executor_status == BE_NO_SPACE);
    CHECK(memcmp(&before, &f.r, sizeof(before)) == 0);
    CHECK(f.written == 789u && f.out[0] == 0x33u);
    CHECK(step(&f, "AB\n", sizeof(f.out)) == 0);
    CHECK(ended(&f) == 0);
    CHECK(setup(&f) == 0);
    CHECK(bp_put(&f.p, 10u, bad, sizeof(bad)) == BP_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    before = f.r;
    memset(f.out, 0x31, sizeof(f.out));
    f.written = 109u;
    result = bsr_step(&f.r, f.out, sizeof(f.out), &f.written);
    CHECK(result.status == BSR_EXECUTOR_ERROR &&
          result.executor_status == BE_BAD_SEQUENCE);
    CHECK(memcmp(&before, &f.r, sizeof(before)) == 0);
    CHECK(f.written == 109u && f.out[0] == 0x31u);
    CHECK(bl_list_program(&f.p, f.out, sizeof(f.out),
                          &f.written) == BL_BAD_SEQUENCE);
    CHECK(f.written == 109u && f.out[0] == 0x31u);
    CHECK(bp_put(&f.p, 10u, good, sizeof(good)) == BP_OK);
    CHECK(submit(&f, "RUN").status == BSR_OK);
    CHECK(step(&f, "", 0u) == 0);
    CHECK(ended(&f) == 0);
    return 0;
}

int main(void)
{
    CHECK(test_tokens() == 0);
    CHECK(test_stop_and_list() == 0);
    CHECK(test_same_line() == 0);
    CHECK(test_goto_and_comments() == 0);
    CHECK(test_atomicity() == 0);
    puts("J0.11 termination: OK");
    return 0;
}
