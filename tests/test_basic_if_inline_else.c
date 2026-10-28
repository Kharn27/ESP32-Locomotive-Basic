/* J1.14-B: closed IF INTEGER direct arms and lexical CPC ELSE. */
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_executor.h"
#include "basic_variable_binding.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "%s:%d: %s\\n", __FILE__, __LINE__, #x); return 1; \
} } while (0)

typedef struct {
    BasicProgram program;
    uint8_t storage[1024];
    BasicVariableStore store;
    BasicVariableEntry entries[5];
    BasicExecutor executor;
    uint8_t output[96];
    size_t written;
} Harness;

static int setup(Harness *h, size_t capacity)
{
    memset(h, 0, sizeof(*h));
    CHECK(bp_init(&h->program, h->storage, sizeof(h->storage)) == BP_OK);
    CHECK(bvs_init(&h->store, h->entries, capacity) == BVS_OK);
    return 0;
}
static BasicVariableKey key(uint8_t name)
{
    BasicVariableKey k = {0};
    k.type = (uint8_t)BVT_INTEGER;
    k.name_length = 1u;
    k.name[0] = name;
    return k;
}
static int set(Harness *h, uint8_t name, int16_t n)
{
    BasicVariableKey k = key(name);
    BasicVariableValue v = {0};
    v.type = (uint8_t)BVT_INTEGER;
    v.data.integer = n;
    CHECK(bvs_assign(&h->store, &k, &v) == BVS_OK);
    return 0;
}
static int get(Harness *h, uint8_t name, int16_t expected)
{
    BasicVariableKey k = key(name);
    BasicVariableValue v = {0};
    CHECK(bvs_get(&h->store, &k, &v) == BVS_OK);
    CHECK(v.type == (uint8_t)BVT_INTEGER && v.data.integer == expected);
    return 0;
}
static int put(Harness *h, uint16_t line, const char *text)
{
    uint8_t body[160];
    size_t n = 0u;
    CHECK(bt_tokenize((const uint8_t *)text, strlen(text),
                      body, sizeof(body), &n) == BT_OK);
    CHECK(bp_put(&h->program, line, body, n) == BP_OK);
    return 0;
}
static int rejects_without_mutation(Harness *h, BEStatus expected)
{
    BasicExecutor before_executor = h->executor;
    BasicProgram before_program = h->program;
    BasicVariableStore before_store = h->store;
    uint8_t before_storage[sizeof(h->storage)];
    BasicVariableEntry before_entries[sizeof(h->entries)/sizeof(h->entries[0])];
    uint8_t before_output[sizeof(h->output)];
    memcpy(before_storage, h->storage, sizeof(before_storage));
    memcpy(before_entries, h->entries, sizeof(before_entries));
    memset(h->output, 0x5au, sizeof(h->output));
    memcpy(before_output, h->output, sizeof(before_output));
    h->written = 999u;
    CHECK(be_step(&h->executor, h->output, sizeof(h->output),
                  &h->written) == expected);
    CHECK(h->written == 999u);
    CHECK(memcmp(&h->executor, &before_executor, sizeof(before_executor)) == 0);
    CHECK(memcmp(&h->program, &before_program, sizeof(before_program)) == 0);
    CHECK(memcmp(&h->store, &before_store, sizeof(before_store)) == 0);
    CHECK(memcmp(h->storage, before_storage, sizeof(before_storage)) == 0);
    CHECK(memcmp(h->entries, before_entries, sizeof(before_entries)) == 0);
    CHECK(memcmp(h->output, before_output, sizeof(before_output)) == 0);
    return 0;
}
static int relation(size_t i, int16_t a, int16_t b)
{
    switch(i) {
        case 0u: return a == b;
        case 1u: return a != b;
        case 2u: return a < b;
        case 3u: return a <= b;
        case 4u: return a > b;
        default: return a >= b;
    }
}
static int lines_and_signed_values(void)
{
    static const char *operators[] = {"=", "<>", "<", "<=", ">", ">="};
    static const int16_t pairs[][2] = {
        {0, 0}, {0, 1}, {1, 0}, {-1, 1}, {1, -1},
        {INT16_MIN, INT16_MAX}, {INT16_MAX, INT16_MIN},
        {INT16_MIN, INT16_MIN}
    };
    size_t i, j;
    for (i=0u; i<6u; ++i) for (j=0u; j<sizeof(pairs)/sizeof(pairs[0]); ++j) {
        Harness h;
        uint8_t token[128], listing[128], again[128];
        size_t n=0u, listed=0u, roundtrip=0u;
        char source[128];
        BasicProgramLine next;
        int t=relation(i,pairs[j][0],pairs[j][1]);
        CHECK(snprintf(source,sizeof(source),"IF A%%%sB%% THEN C%%=81 ELSE C%%=42",
                       operators[i]) > 0);
        CHECK(bt_tokenize((const uint8_t *)source,strlen(source),
                          token,sizeof(token),&n)==BT_OK);
        CHECK(n > 24u && token[0] == 0xa1u);
        CHECK(memchr(token, 0x97, n) != NULL);
        CHECK(bl_detokenize(token,n,listing,sizeof(listing),&listed)==BL_OK);
        CHECK(listed == strlen(source) && memcmp(listing,source,listed)==0);
        CHECK(bt_tokenize(listing,listed,again,sizeof(again),&roundtrip)==BT_OK);
        CHECK(roundtrip==n && memcmp(token,again,n)==0);
        CHECK(setup(&h,5u)==0);
        CHECK(bp_put(&h.program,10u,token,n)==BP_OK);
        CHECK(put(&h,20u,"PRINT C%")==0);
        CHECK(put(&h,30u,"END")==0);
        CHECK(set(&h,(uint8_t)'A',pairs[j][0])==0);
        CHECK(set(&h,(uint8_t)'B',pairs[j][1])==0);
        CHECK(set(&h,(uint8_t)'C',17)==0);
        CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
        CHECK(bp_find(&h.program,20u,&next)==BP_OK);
        CHECK(be_step(&h.executor,h.output,0u,&h.written)==BE_OK);
        CHECK(h.written==0u && h.executor.cursor==next.offset);
        CHECK(get(&h,(uint8_t)'C',t?81:42)==0);
        CHECK(be_step(&h.executor,h.output,sizeof(h.output),&h.written)==BE_OK);
        CHECK(h.written>=4u);
    }
    return 0;
}
static int scalar_and_missing_else(void)
{
    static const int16_t cases[] = {0,1,-1,INT16_MIN,INT16_MAX};
    size_t i;
    for (i=0u;i<5u;++i) {
        int with_else;
        for (with_else=0;with_else<=1;++with_else) {
            Harness h;
            uint8_t b[128], listed[128], again[128];
            size_t n=0u,l=0u,a=0u;
            const char *src=with_else?
               "IF A% THEN C%=81 ELSE C%=42":
               "IF A% THEN C%=81";
            CHECK(bt_tokenize((const uint8_t *)src,strlen(src),b,sizeof(b),&n)==BT_OK);
            CHECK(bl_detokenize(b,n,listed,sizeof(listed),&l)==BL_OK);
            CHECK(l==strlen(src) && memcmp(listed,src,l)==0);
            CHECK(bt_tokenize(listed,l,again,sizeof(again),&a)==BT_OK);
            CHECK(a==n && memcmp(again,b,n)==0);
            CHECK(setup(&h,5u)==0);
            CHECK(bp_put(&h.program,10u,b,n)==BP_OK);
            CHECK(put(&h,20u,"END")==0);
            CHECK(set(&h,(uint8_t)'A',cases[i])==0);
            CHECK(set(&h,(uint8_t)'C',17)==0);
            CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
            CHECK(be_step(&h.executor,h.output,0u,&h.written)==BE_OK);
            CHECK(get(&h,(uint8_t)'C',cases[i] ? 81 : (with_else ? 42 : 17))==0);
        }
    }
    return 0;
}
static int invalid_syntax_and_imports(void)
{
    static const char *bad[]={
        "IF A% THEN", "IF A% THEN ELSE C%=42",
        "IF A% THEN C%=81 ELSE", "IF A% THEN C%=81 ELSE ELSE C%=42",
        "IF A% THEN IF B% THEN C%=81 ELSE C%=42",
        "IF A% THEN GOTO 50", "IF A% THEN PRINT 81",
        "IF A% THEN C%=B%", "IF A% THEN C%=-1",
        "IF A% THEN C%=256", "IF A% THEN C%=",
        "IF A% THEN C! = 81", "IF A% THEN C%%=81",
        "IF A% THEN C%=81:PRINT 1 ELSE C%=42",
        "IF A%<1 THEN C%=81", "IF A%!B% THEN C%=81",
        "ELSE C%=42", "IF A% THEN C%=81 ELSE C%=42:END"
    };
    uint8_t body[128],listed[128],again[128];
    const char *src="IF A%<B% THEN C%=81 ELSE C%=42";
    size_t i,n=0u,l=0u,a=0u;
    CHECK(bt_tokenize((const uint8_t *)src,strlen(src),
                      body,sizeof(body),&n)==BT_OK);
    for(i=0u;i<sizeof(bad)/sizeof(bad[0]);++i) {
        uint8_t out[128],before[128];
        size_t sentinel=987u;
        memset(out,0x55,sizeof(out));
        memcpy(before,out,sizeof(out));
        CHECK(bt_tokenize((const uint8_t *)bad[i],strlen(bad[i]),
                          out,sizeof(out),&sentinel)!=BT_OK);
        CHECK(sentinel==987u && memcmp(out,before,sizeof(out))==0);
    }
    /* Caches in the IF condition and BOTH arms are opaque and may contain
     * separator-looking bytes, unlike the lexical 01 97 pair. */
    for(i=0u;i<n;++i) if(body[i]==0x02u && i+2u<n) {
        body[i+1u]=0x20u;
        body[i+2u]=0x97u;
    }
    CHECK(bl_detokenize(body,n,listed,sizeof(listed),&l)==BL_OK);
    CHECK(l==strlen(src) && memcmp(listed,src,l)==0);
    CHECK(bt_tokenize(listed,l,again,sizeof(again),&a)==BT_OK);
    CHECK(a==n && memcmp(again,body,n)!=0); /* cache normalization only */
    /* Invalid imported tokens must fail without any store/output mutation. */
    {
        Harness h;
        uint8_t damaged[128];
        size_t offset=0u;
        memcpy(damaged,body,n);
        while(offset<n && damaged[offset]!=0x01u) ++offset;
        CHECK(offset+1u<n && damaged[offset+1u]==0x97u);
        damaged[offset+1u]=0xa0u;
        CHECK(setup(&h,5u)==0);
        CHECK(bp_put(&h.program,10u,damaged,n)==BP_OK);
        CHECK(set(&h,(uint8_t)'A',0)==0);
        CHECK(set(&h,(uint8_t)'B',1)==0);
        CHECK(set(&h,(uint8_t)'C',17)==0);
        CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
        CHECK(rejects_without_mutation(&h,BE_BAD_SEQUENCE)==0);
        memcpy(damaged,body,n);
        CHECK(bp_put(&h.program,10u,damaged,n-1u)==BP_OK);
        CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
        CHECK(rejects_without_mutation(&h,BE_TRUNCATED)==0);
    }
    return 0;
}
static int capacity_and_untaken_arm(void)
{
    Harness h;
    BasicProgramLine next;
    /* Untaken THEN with no ELSE never looks up / creates C%. */
    CHECK(setup(&h,1u)==0);
    CHECK(put(&h,10u,"IF A% THEN C%=81")==0);
    CHECK(put(&h,20u,"END")==0);
    CHECK(set(&h,(uint8_t)'A',0)==0);
    CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
    CHECK(bp_find(&h.program,20u,&next)==BP_OK);
    CHECK(be_step(&h.executor,h.output,0u,&h.written)==BE_OK);
    CHECK(h.executor.cursor==next.offset && h.store.count==1u);
    /* Taken branch needs a slot, and preflight rejects FULL atomically. */
    CHECK(set(&h,(uint8_t)'A',1)==0);
    CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
    CHECK(rejects_without_mutation(&h,BE_STORE_FULL)==0);
    /* No-space on PRINT leaves output, store, cursor and stack unchanged. */
    CHECK(setup(&h,5u)==0);
    CHECK(put(&h,10u,"PRINT 81")==0);
    CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
    {
        uint8_t before[sizeof(h.output)];
        size_t sentinel=778u;
        memset(h.output,0x55,sizeof(h.output));
        memcpy(before,h.output,sizeof(before));
        CHECK(be_step(&h.executor,h.output,2u,&sentinel)==BE_NO_SPACE);
        CHECK(sentinel==778u && memcmp(before,h.output,sizeof(before))==0);
    }
    return 0;
}
int main(void)
{
    CHECK(lines_and_signed_values()==0);
    CHECK(scalar_and_missing_else()==0);
    CHECK(invalid_syntax_and_imports()==0);
    CHECK(capacity_and_untaken_arm()==0);
    puts("J1.14-B IF inline/ELSE: tokenize LIST signed branch atomic PASS");
    return 0;
}
