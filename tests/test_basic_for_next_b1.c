/* J1.12-B1: C99 FOR/NEXT token/LIST tests. Execution deliberately unsupported. */
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_program.h"
#include "basic_executor.h"
#include "basic_session.h"
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); return 1; } } while (0)

typedef struct {
    BasicProgram program;
    uint8_t storage[2048];
    BasicVariableStore store;
    BasicVariableEntry entries[4];
    BasicExecutor executor;
    uint8_t out[128];
    size_t written;
} Fixture;

static int init(Fixture *f)
{
    memset(f, 0, sizeof(*f));
    CHECK(bp_init(&f->program, f->storage, sizeof(f->storage)) == BP_OK);
    CHECK(bvs_init(&f->store, f->entries, 4u) == BVS_OK);
    return 0;
}
static int put(Fixture *f, uint16_t line, const char *source)
{
    uint8_t tokens[160]; size_t length = 111u;
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source),
                      tokens, sizeof(tokens), &length) == BT_OK);
    CHECK(bp_put(&f->program, line, tokens, length) == BP_OK);
    return 0;
}
static int one_encoding(const char *source, const uint8_t *expected, size_t expected_n)
{
    uint8_t tokens[128], listed[128], again[128];
    size_t n = 0u, m = 0u, back = 0u;
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source), tokens,
                      sizeof(tokens), &n) == BT_OK);
    CHECK(n == expected_n && memcmp(tokens, expected, n) == 0);
    CHECK(bl_detokenize(tokens, n, listed, sizeof(listed), &m) == BL_OK);
    CHECK(m == strlen(source) && memcmp(listed, source, m) == 0);
    CHECK(bt_tokenize(listed, m, again, sizeof(again), &back) == BT_OK);
    CHECK(back == n && memcmp(again, tokens, n) == 0);
    return 0;
}
static int encodings(void)
{
    static const uint8_t for_one[] = {
        0x9e,0x20,0x02,0x00,0x00,0xc9,0xef,0x0f,0x20,0xec,0x20,0x0f
    };
    static const uint8_t for_step[] = {
        0x9e,0x20,0x02,0x00,0x00,0xc9,0xef,0x0f,0x20,0xec,0x20,0x13,
        0x20,0xe6,0x20,0x10
    };
    static const uint8_t for_neg[] = {
        0x9e,0x20,0x02,0x00,0x00,0xc9,0xef,0xf5,0x1f,0,0,0,0,0x90,
        0x20,0xec,0x20,0xf5,0x1a,0xfe,0x7f
    };
    static const uint8_t next_i[] = {0xb0,0x20,0x02,0,0,0xc9};
    static const uint8_t next_bare[] = {0xb0};
    static const uint8_t next_colon[] = {
        0xbf,0x20,0x02,0,0,0xc9,0x01,0xb0,0x20,0x02,0,0,0xc9
    };
    CHECK(one_encoding("FOR I%=1 TO 1",for_one,sizeof(for_one)) == 0);
    CHECK(one_encoding("FOR I%=1 TO 5 STEP 2",for_step,sizeof(for_step)) == 0);
    CHECK(one_encoding("FOR I%=-32768 TO -32766",for_neg,sizeof(for_neg)) == 0);
    CHECK(one_encoding("NEXT I%",next_i,sizeof(next_i)) == 0);
    CHECK(one_encoding("NEXT",next_bare,sizeof(next_bare)) == 0);
    CHECK(one_encoding("PRINT I%:NEXT I%",next_colon,sizeof(next_colon)) == 0);
    CHECK(one_encoding("FOR J%=32767 TO 32765 STEP -1",
                       (const uint8_t []){
                           0x9e,0x20,0x02,0,0,0xca,0xef,0x1a,0xff,0x7f,
                           0x20,0xec,0x20,0x1a,0xfd,0x7f,0x20,0xe6,0x20,
                           0xf5,0x0f}, 21u) == 0);
    return 0;
}
static int bad_inputs(void)
{
    static const char *invalid[] = {
        "FOR", "FOR I%=", "FOR I%=1", "FOR I%=1 STEP 2",
        "FOR I%=1 TO", "FOR I%=1 TO 2 STEP", "FOR I%=1 TO 2 STEP -",
        "FOR I$=1 TO 2", "FOR I!=1 TO 2", "FOR I%=1 TO 2+1",
        "FOR I%=32768 TO 1", "FOR I%=-32769 TO 1",
        "FOR I%=-1 TO 65536", "FOR I%=1 TO 2 STEP -32769",
        "FOR I%=1 TO 2 STEP 32768", "FOR I%=1 TO 2 STEP I%",
        "NEXT J$", "NEXT I%J", "NEXT 1", "NEXT I%,J%",
        "NEXT:", "FOR I%=1 TO 2:", "FOR I%=1 TO 2::NEXT",
        "FOR I%=1 TO 2:PRINT \"X\":NEXT J%_", "FOR I%=1 TO 2 STEP \"-1\"",
        "FOR A%=1 TO 1:'comment\nNEW", "FOR I%=1 TO 2:REM X\rEND"
    };
    size_t i;
    for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        uint8_t dest[128], old[128]; size_t written = 993u;
        memset(dest, 0x53, sizeof(dest)); memcpy(old, dest, sizeof(old));
        CHECK(bt_tokenize((const uint8_t *)invalid[i], strlen(invalid[i]),
                          dest, sizeof(dest), &written) != BT_OK);
        CHECK(written == 993u && memcmp(dest, old, sizeof(dest)) == 0);
    }
    {
        uint8_t dest[128], old[128]; size_t written = 99u;
        const char *src = "FOR I%=1 TO 2:REM \"NEXT I%:STEP\"";
        CHECK(bt_tokenize((const uint8_t *)src, strlen(src), dest,
                          sizeof(dest), &written) == BT_OK);
        CHECK(written > 18u);
        memset(dest, 0x53, sizeof(dest)); memcpy(old, dest, sizeof(old));
        written = 993u;
        CHECK(bt_tokenize((const uint8_t *)"FOR I%=1 TO 2", 13u,
                          dest, 1u, &written) == BT_NO_SPACE);
        CHECK(written == 993u && memcmp(dest, old, sizeof(dest)) == 0);
    }
    return 0;
}
static int listing_failures(void)
{
    static const uint8_t malformed[][12] = {
        {0x9e,0x20,0x02,0x00},  /* truncated variable */
        {0x9e,0x20,0x02,0,0,0xc9,0xef,0xf5}, /* truncated sign */
        {0x9e,0x20,0x02,0,0,0xc9,0xef,0x0f,0x20,0xec},
        {0x9e,0x20,0x02,0,0,0xc9,0xef,0x0f,0x20,0xec,0x20,0xe6},
        {0xb0,0x20,0x02,0,0,0x00}
    };
    static const size_t lengths[] = {4u,8u,10u,12u,6u};
    size_t i;
    for (i = 0u; i < sizeof(lengths)/sizeof(lengths[0]); ++i) {
        uint8_t dest[96], copy[96]; size_t written = 717u;
        memset(dest, 0xa7, sizeof(dest)); memcpy(copy, dest, sizeof(copy));
        CHECK(bl_detokenize(malformed[i], lengths[i], dest,
                            sizeof(dest), &written) != BL_OK);
        CHECK(written == 717u && memcmp(copy, dest, sizeof(dest)) == 0);
    }
    {
        static const uint8_t valid[] = {0x9e,0x20,0x02,0,0,0xc9,0xef,0x0f,0x20,0xec,0x20,0x0f};
        uint8_t dest[96], copy[96]; size_t n = 717u;
        memset(dest, 0xa7, sizeof(dest)); memcpy(copy, dest, sizeof(copy));
        CHECK(bl_detokenize(valid,sizeof(valid),dest,2u,&n) == BL_NO_SPACE);
        CHECK(n == 717u && memcmp(copy,dest,sizeof(dest)) == 0);
        /* CPC cache bytes can themselves look like a space or keyword. */
        {
            uint8_t cached[sizeof(valid)];
            uint8_t listed[96]; size_t m = 0u;
            memcpy(cached,valid,sizeof(valid));
            cached[3] = 0x20u; cached[4] = 0xecu;
            CHECK(bl_detokenize(cached,sizeof(cached),listed,sizeof(listed),&m) == BL_OK);
            CHECK(m == strlen("FOR I%=1 TO 1") &&
                  memcmp(listed,"FOR I%=1 TO 1",m) == 0);
        }
    }
    return 0;
}
static int rejected(Fixture *f, BEStatus expected)
{
    BasicExecutor before = f->executor;
    BasicVariableStore store = f->store;
    BasicVariableEntry entries[4];
    uint8_t output_before[sizeof(f->out)], program_before[sizeof(f->storage)];
    memcpy(entries,f->entries,sizeof(entries));
    memcpy(program_before,f->storage,sizeof(program_before));
    memset(f->out,0x6a,sizeof(f->out));
    memcpy(output_before,f->out,sizeof(output_before));
    f->written = 777u;
    CHECK(be_step(&f->executor,f->out,sizeof(f->out),&f->written) == expected);
    CHECK(memcmp(&before,&f->executor,sizeof(before)) == 0);
    CHECK(memcmp(&store,&f->store,sizeof(store)) == 0);
    CHECK(memcmp(entries,f->entries,sizeof(entries)) == 0);
    CHECK(memcmp(program_before,f->storage,sizeof(program_before)) == 0);
    CHECK(memcmp(output_before,f->out,sizeof(output_before)) == 0);
    CHECK(f->written == 777u);
    return 0;
}
static int no_loop_runtime(void)
{
    Fixture f;
    CHECK(init(&f) == 0);
    CHECK(put(&f,10u,"FOR I%=1 TO 2") == 0);
    CHECK(put(&f,20u,"NEXT I%") == 0);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store) == BE_OK);
    f.written = 9u;
    CHECK(be_step(&f.executor,f.out,sizeof(f.out),&f.written) == BE_OK);
    CHECK(f.executor.for_depth == 1u && f.store.count == 1u && f.written == 0u);
    CHECK(be_step(&f.executor,f.out,sizeof(f.out),&f.written) == BE_OK);
    CHECK(f.executor.for_depth == 1u);
    CHECK(be_step(&f.executor,f.out,sizeof(f.out),&f.written) == BE_OK);
    CHECK(f.executor.for_depth == 0u);
    CHECK(init(&f) == 0);
    CHECK(put(&f,10u,"NEXT") == 0);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store) == BE_OK);
    CHECK(rejected(&f, BE_NEXT_WITHOUT_FOR) == 0);
    CHECK(init(&f) == 0);
    CHECK(put(&f,10u,"PRINT 1:NEXT I%") == 0);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store) == BE_OK);
    CHECK(rejected(&f, BE_NEXT_WITHOUT_FOR) == 0);
    CHECK(init(&f) == 0);
    CHECK(put(&f,10u,"GOSUB 100") == 0);
    CHECK(put(&f,20u,"END") == 0);
    CHECK(put(&f,100u,"NEXT I%") == 0);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store) == BE_OK);
    f.written = 0u;
    CHECK(be_step(&f.executor,f.out,sizeof(f.out),&f.written) == BE_OK);
    CHECK(f.executor.call_depth == 1u);
    CHECK(rejected(&f, BE_NEXT_WITHOUT_FOR) == 0);
    return 0;
}
static int store_atomicity(void)
{
    Fixture f;
    uint8_t tmp[128],out[128],source[128],before[128];
    size_t written=99u,old_size; BSResult result;
    CHECK(init(&f) == 0);
    CHECK(put(&f,10u,"FOR I%=1 TO 2") == 0);
    old_size=f.program.size;
    memcpy(source,"20 FOR J$=1 TO 2",strlen("20 FOR J$=1 TO 2"));
    memset(out,0x63,sizeof(out)); memcpy(before,out,sizeof(out));
    result=bs_process_line(&f.program,source,strlen("20 FOR J$=1 TO 2"),tmp,sizeof(tmp),
                           out,sizeof(out),&written);
    CHECK(result.status != BS_OK);
    CHECK(written==99u && f.program.size==old_size &&
          memcmp(out,before,sizeof(out))==0);
    { BasicProgramLine missing;
      CHECK(bp_find(&f.program,20u,&missing) == BP_NOT_FOUND); }
    return 0;
}

static int session_list_and_run(void)
{
    Fixture f;
    BasicSessionRuntime runtime;
    BSRResult result;
    uint8_t temporary[256],output[256];
    size_t written = 0u;
    const char *expected = "10 FOR I%=1 TO 2\\n20 NEXT I%\\n";
    CHECK(init(&f) == 0);
    CHECK(put(&f,10u,"FOR I%=1 TO 2") == 0);
    CHECK(put(&f,20u,"NEXT I%") == 0);
    result = bsr_init_with_store(&runtime,&f.program,&f.store);
    CHECK(result.status == BSR_OK);
    result = bsr_submit(&runtime,(const uint8_t *)"LIST",4u,
                        temporary,sizeof(temporary),output,sizeof(output),&written);
    CHECK(result.status == BSR_OK);
    CHECK(written == strlen(expected) && memcmp(output,expected,written) == 0);
    result = bsr_submit(&runtime,(const uint8_t *)"RUN",3u,
                        temporary,sizeof(temporary),output,sizeof(output),&written);
    CHECK(result.status == BSR_OK && runtime.state == BSR_RUNNING);
    result = bsr_step(&runtime,output,sizeof(output),&written);
    CHECK(result.status == BSR_OK && runtime.executor.for_depth == 1u);
    return 0;
}
int main(void)
{
    CHECK(encodings() == 0);
    CHECK(bad_inputs() == 0);
    CHECK(listing_failures() == 0);
    CHECK(no_loop_runtime() == 0);
    CHECK(store_atomicity() == 0);
    CHECK(session_list_and_run() == 0);
    puts("PASS J1.12-B1 tokens/LIST + J1.12-B2 runtime regression");
    return 0;
}
