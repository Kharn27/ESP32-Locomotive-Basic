#include "basic_executor.h"
#include "basic_listing.h"
#include "basic_tokenizer.h"
#include "basic_variable_store.h"
#include <stdio.h>
#include <string.h>

#define CHECK(e) do { if (!(e)) { \
  fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#e); return 1; \
} } while (0)

typedef struct {
    const char *id;
    const char *expression;
    const char *cpc_print;
    int16_t value;
    BEStatus error;
} Oracle;

/* Source of every expectation: archived original AND repeat CPC run,
 * docs/J1.22-A-integer-logical-expressions-cpc-oracle.md.
 * The native transport emits LF rather than CPC printer CRLF. */
static const Oracle oracle[] = {
    {"N00_ZERO","NOT 0","VALUE=-1 \n",-1,BE_OK},
    {"N01_MINUS1","NOT -1","VALUE= 0 \n",0,BE_OK},
    {"N02_POS","NOT 5","VALUE=-6 \n",-6,BE_OK},
    {"N03_MIN","NOT -32768","VALUE= 32767 \n",32767,BE_OK},
    {"A00_ZERO","0 AND -1","VALUE= 0 \n",0,BE_OK},
    {"A01_POS","5 AND 3","VALUE= 1 \n",1,BE_OK},
    {"A02_NEG","-5 AND 3","VALUE= 3 \n",3,BE_OK},
    {"A03_MIN","-32768 AND 32767","VALUE= 0 \n",0,BE_OK},
    {"O00_ZERO","0 OR 0","VALUE= 0 \n",0,BE_OK},
    {"O01_POS","5 OR 2","VALUE= 7 \n",7,BE_OK},
    {"O02_NEG","-2 OR 1","VALUE=-1 \n",-1,BE_OK},
    {"X00_ZERO","0 XOR 0","VALUE= 0 \n",0,BE_OK},
    {"X01_POS","5 XOR 3","VALUE= 6 \n",6,BE_OK},
    {"X02_NEG","-5 XOR 3","VALUE=-8 \n",-8,BE_OK},
    {"P01_ADD","1+2 AND 4","VALUE= 0 \n",0,BE_OK},
    {"P02_MULT","2*3 OR 1","VALUE= 7 \n",7,BE_OK},
    {"P03_IDIV","8\\2 XOR 1","VALUE= 5 \n",5,BE_OK},
    {"P04_MOD","10 MOD 4 AND 3","VALUE= 2 \n",2,BE_OK},
    {"P05_REL","(1<2) AND (2<3)","TAKEN\n",0,BE_OK},
    {"P06_IF_ELSE","(1<2) AND (2<1)","ELSE\n",0,BE_OK},
    {"P07_NESTED","((1+2) AND (4-1)) OR (NOT (2 AND 1))",
      "VALUE=-1 \n",-1,BE_OK},
    {"P08_UNARY","NOT (1 AND (2+3))","VALUE=-2 \n",-2,BE_OK},
    {"E01_DIV0","8 AND (4\\0)",NULL,0,BE_DIVISION_BY_ZERO},
    {"E02_OVERFLOW","(32767+1) AND 1",NULL,0,BE_INTEGER_OVERFLOW}
};

typedef struct {
    BasicProgram program;
    BasicExecutor executor;
    BasicVariableEntry entries[8];
    BasicVariableStore store;
    uint8_t storage[1024], tokens[512], listing[1024], output[256];
    size_t written;
} Fixture;

static int init(Fixture *f)
{
    memset(f,0xa5,sizeof(*f));
    CHECK(bp_init(&f->program,f->storage,sizeof(f->storage))==BP_OK);
    CHECK(bvs_init(&f->store,f->entries,8u)==BVS_OK);
    return 0;
}

static int add(Fixture *f, uint16_t line, const char *source)
{
    size_t n=333u;
    CHECK(bt_tokenize((const uint8_t *)source,strlen(source),
                      f->tokens,sizeof(f->tokens),&n)==BT_OK);
    CHECK(bp_put(&f->program,line,f->tokens,n)==BP_OK);
    return 0;
}

static BasicVariableKey integer_key(const char *name)
{
    BasicVariableKey key;
    size_t n=strlen(name),i;
    memset(&key,0,sizeof(key));
    key.type=(uint8_t)BVT_INTEGER;
    key.name_length=(uint8_t)n;
    for(i=0u;i<n && i<sizeof(key.name);++i)
        key.name[i]=(uint8_t)name[i];
    return key;
}

static int test_case(const Oracle *c)
{
    Fixture f;
    char stmt[256],expected_list[512];
    size_t n,i;
    BasicVariableKey key=integer_key("A");
    BasicVariableValue value;
    BasicExecutor saved;
    BasicVariableEntry entries[8];
    uint8_t saved_storage[1024],output_before[256];
    size_t saved_count;
    int is_if=c->id[0]=='P' && (c->id[1]=='0') &&
              (c->id[2]=='5' || c->id[2]=='6');

    CHECK(init(&f)==0);
    if(is_if) {
        CHECK(snprintf(stmt,sizeof(stmt),
            c->id[2]=='5' ?
            "IF %s THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"" :
            "IF %s THEN PRINT #8,\"BAD\" ELSE PRINT #8,\"ELSE\"",
            c->expression)>0);
        CHECK(add(&f,10u,stmt)==0);
        CHECK(add(&f,20u,"END")==0);
    } else {
        CHECK(snprintf(stmt,sizeof(stmt),"A%%=%s",c->expression)>0);
        CHECK(add(&f,10u,stmt)==0);
        CHECK(add(&f,20u,"PRINT #8,\"VALUE=\";A%")==0);
        CHECK(add(&f,30u,"END")==0);
    }
    /* Round-trip exact source spelling: keywords, spaces and CPC reference
     * caches survive LIST; source and listed channel are independently
     * tested and NEVER used to compute the expected CPC numeric values. */
    CHECK(bl_list_program(&f.program,f.listing,sizeof(f.listing),&n)==BL_OK);
    if(is_if) {
        CHECK(snprintf(expected_list,sizeof(expected_list),
                 "10 %s\n20 END\n",stmt)>0);
    } else {
        CHECK(snprintf(expected_list,sizeof(expected_list),
                 "10 %s\n20 PRINT #8,\"VALUE=\";A%%\n30 END\n",stmt)>0);
    }
    CHECK(n==strlen(expected_list));
    CHECK(memcmp(f.listing,expected_list,n)==0);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store)==BE_OK);
    memset(f.output,0x71,sizeof(f.output));f.written=777u;
    if(c->error!=BE_OK) {
        saved=f.executor;
        memcpy(entries,f.entries,sizeof(entries));
        memcpy(saved_storage,f.storage,sizeof(saved_storage));
        memcpy(output_before,f.output,sizeof(output_before));
        saved_count=f.store.count;
        CHECK(be_step(&f.executor,f.output,sizeof(f.output),
                      &f.written)==c->error);
        CHECK(memcmp(&f.executor,&saved,sizeof(saved))==0);
        CHECK(memcmp(entries,f.entries,sizeof(entries))==0);
        CHECK(memcmp(saved_storage,f.storage,sizeof(saved_storage))==0);
        CHECK(memcmp(output_before,f.output,sizeof(output_before))==0);
        CHECK(f.store.count==saved_count && f.written==777u);
        return 0;
    }
    {
        BEStatus got = be_step(&f.executor,f.output,sizeof(f.output),&f.written);
        if (got != BE_OK) fprintf(stderr,"%s: first step BEStatus=%d\n",c->id,(int)got);
        CHECK(got == BE_OK);
    }
    if(!is_if) {
        CHECK(f.written==0u);
        CHECK(bvs_get(&f.store,&key,&value)==BVS_OK);
        CHECK(value.type==(uint8_t)BVT_INTEGER);
        if(value.data.integer!=c->value)
            fprintf(stderr,"%s: actual=%d expected=%d\n",c->id,
                    (int)value.data.integer,(int)c->value);
        CHECK(value.data.integer==c->value);
        memset(f.output,0x71,sizeof(f.output));f.written=777u;
        CHECK(be_step(&f.executor,f.output,sizeof(f.output),&f.written)==BE_OK);
    } else CHECK(f.store.count==0u);
    CHECK(f.written==strlen(c->cpc_print));
    CHECK(memcmp(f.output,c->cpc_print,f.written)==0);
    for (i=f.written;i<sizeof(f.output);++i) CHECK(f.output[i]==0x71u);
    return 0;
}

static int negative_scenarios(void)
{
    Fixture f;
    size_t n=999u;
    uint8_t canary[16];
    BasicExecutor saved;
    BasicVariableEntry entries[8];
    uint8_t before[256];
    static const char *const bad[]={
        "A%=NOT", "A%=(1 AND 2", "A%=1 AND", "A%=1 AND )",
        "A%=1 XOR (2 OR )", "A%=1 OR \"ABC\"",
        "A%=1 AND B$", "A%=NOT 32768", "A%=1/2 AND 3"
    };
    size_t i;
    for (i=0u;i<sizeof(bad)/sizeof(bad[0]);++i) {
        CHECK(init(&f)==0);
        memset(canary,0x61,sizeof(canary));n=999u;
        CHECK(bt_tokenize((const uint8_t *)bad[i],strlen(bad[i]),
                          canary,sizeof(canary),&n)!=BT_OK);
        CHECK(n==999u);
        CHECK(memcmp(canary,"aaaaaaaaaaaaaaaa",16u)==0);
    }
    CHECK(init(&f)==0);
    CHECK(add(&f,10u,"A%=NOT 5")==0);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store)==BE_OK);
    saved=f.executor;
    memcpy(entries,f.entries,sizeof(entries));
    memset(f.output,0x81,sizeof(f.output));memcpy(before,f.output,sizeof(before));
    f.written=888u;
    CHECK(be_step(&f.executor,f.output,0u,&f.written)==BE_OK);
    /* Zero-output assignment is legal with zero output capacity. */
    CHECK(f.written==0u);
    CHECK(f.executor.cursor!=saved.cursor);

    CHECK(init(&f)==0);
    CHECK(add(&f,10u,"A%=NOT 5")==0);
    CHECK(add(&f,20u,"PRINT #8,\"VALUE=\";A%")==0);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store)==BE_OK);
    CHECK(be_step(&f.executor,f.output,sizeof(f.output),&f.written)==BE_OK);
    saved=f.executor;memcpy(entries,f.entries,sizeof(entries));
    memset(f.output,0x81,sizeof(f.output));memcpy(before,f.output,sizeof(before));
    f.written=888u;
    CHECK(be_step(&f.executor,f.output,1u,&f.written)==BE_NO_SPACE);
    CHECK(memcmp(&saved,&f.executor,sizeof(saved))==0);
    CHECK(memcmp(entries,f.entries,sizeof(entries))==0);
    CHECK(memcmp(before,f.output,sizeof(before))==0);
    CHECK(f.written==888u);
    return 0;
}

int main(void)
{
    size_t i;
    /* RED/GREEN baseline: first four are the NOT witnesses. */
    for(i=0u;i<sizeof(oracle)/sizeof(oracle[0]);++i) {
        if(test_case(&oracle[i])!=0) {
            fprintf(stderr,"J1.22-B case %s FAILED\n",oracle[i].id);
            return 1;
        }
    }
    CHECK(negative_scenarios()==0);
    printf("J1.22-B native: 24 oracle scenarios + negative gates PASS\n");
    return 0;
}
