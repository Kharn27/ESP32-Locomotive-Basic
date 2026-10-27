/* J1.2-C: sole CPC REAL5 NMIN INTEGER immediate, no floating evaluator. */
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_executor.h"
#include "basic_session_runtime.h"
#include "basic_variable_binding.h"
#include "basic_variable_store.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

typedef struct {
    BasicProgram program;
    uint8_t storage[512];
    BasicVariableStore store;
    BasicVariableEntry entries[4];
    BasicSessionRuntime runtime;
    uint8_t scratch[96];
    uint8_t output[128];
    size_t written;
} Harness;

static const uint8_t nmin_body[] = {
    2u,0u,0u,0xc2u,0xefu,0xf5u,0x1fu,0u,0u,0u,0u,0x90u
};
/* Independent CPC image is checked against its ORIGINAL SHA by Python.
 * This literal vector is for fast C99 regression only. */
static const uint8_t nmin_image[] = {
    0x11u,0u,10u,0u,2u,0u,0u,0xc2u,0xefu,0xf5u,0x1fu,
    0u,0u,0u,0u,0x90u,0u,
    0x0bu,0u,20u,0u,0xbfu,' ',2u,0u,0u,0xc2u,0u,
    6u,0u,30u,0u,0x98u,0u,0u,0u
};
static const char source[] = "10 B%=-32768\n20 PRINT B%\n30 END\n";

static int setup(Harness *h)
{
    memset(h, 0, sizeof(*h));
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(bvs_init(&h->store, h->entries, 4u) == BVS_OK);
    CHECK(bsr_init_with_store(&h->runtime, &h->program, &h->store).status == BSR_OK);
    return 0;
}

static int submit(Harness *h, const char *line)
{
    BSRResult result = bsr_submit(&h->runtime, (const uint8_t *)line,
        strlen(line), h->scratch, sizeof(h->scratch), h->output,
        sizeof(h->output), &h->written);
    CHECK(result.status == BSR_OK);
    return 0;
}

static void key_b(BasicVariableKey *key)
{
    memset(key, 0, sizeof(*key));
    key->type = (uint8_t)BVT_INTEGER;
    key->name_length = 1u;
    key->name[0] = (uint8_t)'B';
}

static int positive(void)
{
    Harness h;
    uint8_t bytes[64], source_back[64], export[64], snapshot[sizeof(nmin_image)];
    size_t n = 123u, m = 456u, e = 789u;
    BasicVariableKey key;
    BasicVariableValue value;
    size_t output_length = strlen("-32768 \n");
    CHECK(INT16_MIN == -32768);
    memset(bytes, 0xa1, sizeof(bytes));
    CHECK(bt_tokenize((const uint8_t *)"B%=-32768", 9u, bytes,
                      sizeof(nmin_body) - 1u, &n) == BT_NO_SPACE);
    CHECK(n == 123u && bytes[0] == 0xa1u);
    CHECK(bt_tokenize((const uint8_t *)"B%=-32768", 9u, bytes,
                      sizeof(nmin_body), &n) == BT_OK);
    CHECK(n == sizeof(nmin_body) && memcmp(bytes,nmin_body,n) == 0);
    memset(source_back,0x69,sizeof(source_back));
    CHECK(bl_detokenize(bytes,n,source_back,8u,&m) == BL_NO_SPACE);
    CHECK(m == 456u && source_back[0] == 0x69u);
    CHECK(bl_detokenize(bytes,n,source_back,9u,&m) == BL_OK);
    CHECK(m == 9u && memcmp(source_back,"B%=-32768",m) == 0);
    CHECK(setup(&h) == 0);
    CHECK(submit(&h, "10 B%=-32768") == 0);
    CHECK(submit(&h, "20 PRINT B%") == 0);
    CHECK(submit(&h, "30 END") == 0);
    CHECK(h.program.size == sizeof(nmin_image));
    CHECK(bp_export(&h.program, export, sizeof(nmin_image) - 1u,
                    &e) == BP_NO_SPACE);
    CHECK(e == 789u);
    CHECK(bp_export(&h.program, export, sizeof(nmin_image), &e) == BP_OK);
    CHECK(e == sizeof(nmin_image) && memcmp(export,nmin_image,e) == 0);
    memcpy(snapshot,h.storage,sizeof(snapshot));

    h.written = 1234u;
    memset(h.output,0x5a,sizeof(h.output));
    {
        BSRResult r = bsr_submit(&h.runtime,(const uint8_t *)"LIST",4u,
            h.scratch,sizeof(h.scratch),h.output,strlen(source)-1u,&h.written);
        CHECK(r.status == BSR_SESSION_ERROR &&
              r.session.listing_status == BL_NO_SPACE);
        CHECK(h.written == 1234u && h.output[0] == 0x5au);
        CHECK(memcmp(snapshot,h.storage,sizeof(snapshot)) == 0);
    }
    CHECK(submit(&h, "LIST") == 0);
    CHECK(h.written == strlen(source) &&
          memcmp(h.output,source,h.written) == 0);
    CHECK(submit(&h, "RUN") == 0 && h.store.count == 0u);
    CHECK(bsr_step(&h.runtime,h.output,sizeof(h.output),&h.written).status ==
          BSR_OK);
    CHECK(h.written == 0u && h.store.count == 1u);
    key_b(&key);
    CHECK(bvs_get(&h.store,&key,&value) == BVS_OK);
    CHECK(value.type == (uint8_t)BVT_INTEGER && value.data.integer == INT16_MIN);

    memset(h.output,0xb7,sizeof(h.output));
    h.written = 1425u;
    {
        size_t cursor = h.runtime.executor.cursor;
        BasicVariableEntry before[4];
        memcpy(before,h.entries,sizeof(before));
        CHECK(bsr_step(&h.runtime,h.output,output_length-1u,&h.written).status ==
              BSR_EXECUTOR_ERROR);
        CHECK(h.written == 1425u && h.output[0] == 0xb7u &&
              h.runtime.executor.cursor == cursor &&
              memcmp(before,h.entries,sizeof(before)) == 0);
    }
    CHECK(bsr_step(&h.runtime,h.output,output_length,&h.written).status ==
          BSR_OK);
    CHECK(h.written == output_length &&
          memcmp(h.output,"-32768 \n",output_length) == 0);
    CHECK(bsr_step(&h.runtime,h.output,sizeof(h.output),&h.written).status ==
          BSR_OK);
    CHECK(bsr_step(&h.runtime,h.output,sizeof(h.output),&h.written).status ==
          BSR_END);
    CHECK(submit(&h,"RUN") == 0 && h.store.count == 0u);
    CHECK(bsr_step(&h.runtime,h.output,sizeof(h.output),&h.written).status ==
          BSR_OK);
    CHECK(bvs_get(&h.store,&key,&value) == BVS_OK &&
          value.data.integer == INT16_MIN);
    CHECK(submit(&h,"NEW") == 0 && h.store.count == 0u &&
          h.program.size == 2u);
    CHECK(submit(&h,"10 B%=-32768") == 0);
    CHECK(submit(&h,"20 PRINT B%") == 0);
    CHECK(submit(&h,"30 END") == 0);
    CHECK(bp_export(&h.program,export,sizeof(export),&e) == BP_OK &&
          e == sizeof(nmin_image) && memcmp(export,nmin_image,e) == 0);
    return 0;
}

static int ascii_rejections(void)
{
    static const struct {
        const char *input;
        BTStatus error;
    } bad[] = {
        {"B%=32768",BT_NUMBER_OUT_OF_RANGE},
        {"B%=-32769",BT_NUMBER_OUT_OF_RANGE},
        {"B%=-65535",BT_NUMBER_OUT_OF_RANGE},
        {"B%=999999999999999999999",BT_NUMBER_OUT_OF_RANGE},
        {"B%=B%+256",BT_NUMBER_OUT_OF_RANGE},
        {"B%=--32768",BT_UNSUPPORTED_CONSTRUCT},
        {"B%=-B%",BT_UNSUPPORTED_CONSTRUCT},
        {"B%=1-32768",BT_UNSUPPORTED_CONSTRUCT}
    };
    size_t i,j;
    uint8_t bytes[64];
    memset(bytes,0x31,sizeof(bytes));
    for(i=0u;i<sizeof(bad)/sizeof(bad[0]);++i) {
        size_t n=1234u;
        CHECK(bt_tokenize((const uint8_t *)bad[i].input,
              strlen(bad[i].input),bytes,sizeof(bytes),&n) == bad[i].error);
        CHECK(n==1234u);
        for(j=0u;j<sizeof(bytes);++j) CHECK(bytes[j]==0x31u);
    }
    return 0;
}

static int malformed_imports(void)
{
    static const uint8_t no_f5[] = {2,0,0,0xc2,0xef,0x1f,0,0,0,0,0x90};
    static const uint8_t double_f5[] = {2,0,0,0xc2,0xef,0xf5,0xf5,0x1f,0,0,0,0,0x90};
    static const uint8_t bad_exp_low[] = {2,0,0,0xc2,0xef,0xf5,0x1f,0,0,0,0,0x8f};
    static const uint8_t bad_exp_high[] = {2,0,0,0xc2,0xef,0xf5,0x1f,0,0,0,0,0x91};
    static const uint8_t bad_mantissa[] = {2,0,0,0xc2,0xef,0xf5,0x1f,1,0,0,0,0x90};
    static const uint8_t fake_1a[] = {2,0,0,0xc2,0xef,0xf5,0x1a,0,0x80};
    static const uint8_t trailing[] = {2,0,0,0xc2,0xef,0xf5,0x1f,0,0,0,0,0x90,0x98};
    static const uint8_t addition[] = {2,0,0,0xc2,0xef,2,0,0,0xc2,0xf4,0x1f,0,0,0,0,0x90};
    static const struct {
        const uint8_t *bytes; size_t length;
        BLStatus listed; BEStatus executed;
    } bad[] = {
        {nmin_body,7u,BL_TRUNCATED,BE_TRUNCATED},
        {nmin_body,8u,BL_TRUNCATED,BE_TRUNCATED},
        {nmin_body,9u,BL_TRUNCATED,BE_TRUNCATED},
        {nmin_body,10u,BL_TRUNCATED,BE_TRUNCATED},
        {nmin_body,11u,BL_TRUNCATED,BE_TRUNCATED},
        {no_f5,sizeof(no_f5),BL_BAD_SEQUENCE,BE_BAD_SEQUENCE},
        {double_f5,sizeof(double_f5),BL_UNKNOWN_TOKEN,BE_BAD_SEQUENCE},
        {bad_exp_low,sizeof(bad_exp_low),BL_BAD_SEQUENCE,BE_BAD_SEQUENCE},
        {bad_exp_high,sizeof(bad_exp_high),BL_BAD_SEQUENCE,BE_BAD_SEQUENCE},
        {bad_mantissa,sizeof(bad_mantissa),BL_BAD_SEQUENCE,BE_BAD_SEQUENCE},
        {fake_1a,sizeof(fake_1a),BL_BAD_SEQUENCE,BE_INTEGER_OVERFLOW},
        {trailing,sizeof(trailing),BL_UNKNOWN_TOKEN,BE_BAD_SEQUENCE},
        {addition,sizeof(addition),BL_BAD_SEQUENCE,BE_BAD_SEQUENCE}
    };
    size_t i;
    for(i=0u;i<sizeof(bad)/sizeof(bad[0]);++i) {
        Harness h;
        BasicExecutor exe;
        BasicVariableKey key;
        BasicVariableValue value={0};
        BasicVariableEntry entry_before[4];
        uint8_t storage_before[512], output[96];
        size_t written=12345u, cursor_before, j;
        CHECK(setup(&h) == 0);
        CHECK(bp_put(&h.program,10u,bad[i].bytes,bad[i].length) == BP_OK);
        memcpy(storage_before,h.storage,sizeof(storage_before));
        memset(output,0x4eu,sizeof(output));
        CHECK(bl_detokenize(bad[i].bytes,bad[i].length,output,
                            sizeof(output),&written) == bad[i].listed);
        CHECK(written==12345u);
        for(j=0u;j<sizeof(output);++j) CHECK(output[j]==0x4eu);
        CHECK(bl_list_program(&h.program,output,sizeof(output),&written) ==
              bad[i].listed);
        CHECK(written==12345u && output[0]==0x4eu);
        key_b(&key);
        value.type=(uint8_t)BVT_INTEGER;
        value.data.integer=42;
        CHECK(bvs_assign(&h.store,&key,&value)==BVS_OK);
        memcpy(entry_before,h.entries,sizeof(entry_before));
        CHECK(be_init_with_store(&exe,&h.program,&h.store)==BE_OK);
        cursor_before=exe.cursor;
        CHECK(be_step(&exe,output,sizeof(output),&written)==bad[i].executed);
        CHECK(exe.cursor==cursor_before && written==12345u &&
              h.store.count==1u &&
              memcmp(h.entries,entry_before,sizeof(entry_before))==0 &&
              memcmp(h.storage,storage_before,sizeof(storage_before))==0);
        for(j=0u;j<sizeof(output);++j) CHECK(output[j]==0x4eu);
        CHECK(bvs_get(&h.store,&key,&value)==BVS_OK &&
              value.data.integer==42);
    }
    return 0;
}

int main(void)
{
    CHECK(positive()==0);
    CHECK(ascii_rejections()==0);
    CHECK(malformed_imports()==0);
    puts("J1.2-C: NMIN exact tokens/image/LIST/RUN and negative atomicity PASS");
    return 0;
}
