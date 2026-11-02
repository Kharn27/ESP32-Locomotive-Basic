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


/* Distinct from the authentic 24 CPC observations: structural and
 * transactional host-only negative tests. No new CPC claim is inferred. */
static int raw_step_failure(Fixture *f, BEStatus expected)
{
    BasicExecutor executor = f->executor;
    BasicVariableEntry entries[8];
    uint8_t data[1024], out[256];
    size_t original_count = f->store.count;
    memcpy(entries, f->entries, sizeof(entries));
    memcpy(data, f->storage, sizeof(data));
    memset(f->output, 0x5bu, sizeof(f->output));
    memcpy(out, f->output, sizeof(out));
    f->written = 741u;
    CHECK(be_step(&f->executor, f->output, sizeof(f->output),
                  &f->written) == expected);
    CHECK(memcmp(&f->executor, &executor, sizeof(executor)) == 0);
    CHECK(memcmp(f->entries, entries, sizeof(entries)) == 0);
    CHECK(memcmp(f->storage, data, sizeof(data)) == 0);
    CHECK(memcmp(f->output, out, sizeof(out)) == 0);
    CHECK(f->store.count == original_count && f->written == 741u);
    return 0;
}

static int imported_negative_and_types(void)
{
    Fixture f;
    size_t n = 0u, i, op = SIZE_MAX, rhs = SIZE_MAX;
    BasicVariableKey key;
    static const uint8_t empty[] = {0u};
    const char *source = "A%=1 AND 2";

    CHECK(init(&f)==0);
    CHECK(bt_tokenize((const uint8_t *)source, strlen(source), f.tokens,
                      sizeof(f.tokens), &n) == BT_OK);
    for (i=0u;i<n;++i)
        if (f.tokens[i]==0xfau) {op=i;break;}
    CHECK(op!=SIZE_MAX);
    /* Truncated after FA: not an empty successful expression. */
    CHECK(bp_put(&f.program,10u,f.tokens,op+1u)==BP_OK);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store)==BE_OK);
    CHECK(raw_step_failure(&f, BE_TRUNCATED)==0);
    /* A forged operator byte in an otherwise authentic token stream. */
    CHECK(init(&f)==0);
    CHECK(bt_tokenize((const uint8_t *)source,strlen(source),f.tokens,
                      sizeof(f.tokens),&n)==BT_OK);
    CHECK(op+2u<n);
    f.tokens[op+2u]=0xffu;
    CHECK(bp_put(&f.program,10u,f.tokens,n)==BP_OK);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store)==BE_OK);
    CHECK(raw_step_failure(&f,BE_UNKNOWN_TOKEN)==0);

    CHECK(init(&f)==0);
    CHECK(add(&f,10u,"A%=Q% AND 3")==0);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store)==BE_OK);
    CHECK(raw_step_failure(&f,BE_VARIABLE_NOT_FOUND)==0);

    /* Inject a syntactically correct STRING BVR into a native INTEGER
     * expression, with a real typed STRING entry present. */
    CHECK(init(&f)==0);
    CHECK(bt_tokenize((const uint8_t *)"A%=Q% AND 3",11u,
                      f.tokens,sizeof(f.tokens),&n)==BT_OK);
    for (i=1u;i<n;++i) if(f.tokens[i]==0x02u) { rhs=i; break; }
    CHECK(rhs!=SIZE_MAX);
    f.tokens[rhs]=0x03u;
    CHECK(bp_put(&f.program,10u,f.tokens,n)==BP_OK);
    key=integer_key("Q");
    key.type=(uint8_t)BVT_STRING;
    CHECK(bvs_assign_string(&f.store,&key,empty,0u)==BVS_OK);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store)==BE_OK);
    CHECK(raw_step_failure(&f,BE_INVALID_TYPE)==0);

    /* Full destination store: assignment must reject without side effects. */
    CHECK(init(&f)==0);
    CHECK(add(&f,10u,"A%=5 AND 3")==0);
    for(i=0u;i<8u;++i) {
        BasicVariableKey occupied=integer_key("Z");
        occupied.name[0]=(uint8_t)('B'+(uint8_t)i);
        CHECK(bvs_create(&f.store,&occupied,&n)==BVS_OK);
    }
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store)==BE_OK);
    CHECK(raw_step_failure(&f,BE_STORE_FULL)==0);

    /* Full executor or buffer overlap is rejected before any mutation. */
    CHECK(init(&f)==0);
    CHECK(add(&f,10u,"A%=NOT 5")==0);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store)==BE_OK);
    {
        BasicExecutor saved = f.executor;
        f.written=999u;
        CHECK(be_step(&f.executor,(uint8_t *)&f.executor,4u,
                      &f.written)==BE_OVERLAP);
        CHECK(memcmp(&f.executor,&saved,sizeof(saved))==0);
        CHECK(f.written==999u);
    }
    return 0;
}

static int independent_variable_names(void)
{
    Fixture f;
    BasicVariableValue value;
    BasicVariableKey key;
    CHECK(init(&f)==0);
    CHECK(add(&f,10u,"LONG%=5 AND 3")==0);
    CHECK(add(&f,20u,"OTHER%=LONG% XOR 2")==0);
    CHECK(be_init_with_store(&f.executor,&f.program,&f.store)==BE_OK);
    CHECK(be_step(&f.executor,f.output,sizeof(f.output),&f.written)==BE_OK);
    key=integer_key("LONG");
    CHECK(bvs_get(&f.store,&key,&value)==BVS_OK &&
          value.data.integer==1);
    CHECK(be_step(&f.executor,f.output,sizeof(f.output),&f.written)==BE_OK);
    key=integer_key("OTHER");
    CHECK(bvs_get(&f.store,&key,&value)==BVS_OK &&
          value.data.integer==3);
    return 0;
}


/* C1: internal native tokenize -> LIST -> RUN consistency regression.
 * These are deliberately NOT new independent CPC oracle observations.
 * Include classic IF paths and ensure THEN/ELSE arm text is not scanned as
 * a logical condition. The 24 CPC oracle entries above stay unchanged. */
typedef struct {
    const char *source;
    const char *expected_output;
    int a_value;
    int b_value;
    int supply_a;
    int supply_b;
    int poison_cache;
} IFDispatchCase;

static int c1_if_dispatch_case(const IFDispatchCase *c)
{
    Fixture f;
    BasicVariableKey key;
    BasicVariableValue value;
    BasicExecutor saved;
    BasicVariableEntry saved_entries[8];
    uint8_t saved_storage[1024], saved_output[256];
    char expected_list[512];
    size_t n = 0u, i, references = 0u;
    size_t saved_written, saved_count;
    CHECK(init(&f) == 0);
    CHECK(bt_tokenize((const uint8_t *)c->source, strlen(c->source),
                      f.tokens, sizeof(f.tokens), &n) == BT_OK);
    if (c->poison_cache) {
        /* Imported CPC reference caches are opaque, even if their
         * bytes look like logical opcodes. */
        for (i = 0u; i + 2u < n; ++i) {
            if (f.tokens[i] == 0x02u) {
                f.tokens[i + 1u] = 0xfau;
                f.tokens[i + 2u] = 0xfeu;
                ++references;
                i += 3u;
            }
        }
        CHECK(references == 2u);
    }
    CHECK(bp_put(&f.program, 10u, f.tokens, n) == BP_OK);
    CHECK(add(&f, 20u, "END") == 0);
    if (c->supply_a || c->supply_b) {
        memset(&value, 0, sizeof(value));
        value.type = (uint8_t)BVT_INTEGER;
        if (c->supply_a) {
            key = integer_key("A");
            value.data.integer = (int16_t)c->a_value;
            CHECK(bvs_assign(&f.store, &key, &value) == BVS_OK);
        }
        if (c->supply_b) {
            key = integer_key("B");
            value.data.integer = (int16_t)c->b_value;
            CHECK(bvs_assign(&f.store, &key, &value) == BVS_OK);
        }
    }
    CHECK(snprintf(expected_list, sizeof(expected_list),
                   "10 %s\n20 END\n", c->source) > 0);
    CHECK(bl_list_program(&f.program, f.listing, sizeof(f.listing),
                          &n) == BL_OK);
    CHECK(n == strlen(expected_list));
    CHECK(memcmp(f.listing, expected_list, n) == 0);
    CHECK(be_init_with_store(&f.executor, &f.program, &f.store) == BE_OK);
    saved = f.executor;
    memcpy(saved_entries, f.entries, sizeof(saved_entries));
    memcpy(saved_storage, f.storage, sizeof(saved_storage));
    saved_count = f.store.count;
    memset(f.output, 0x6bu, sizeof(f.output));
    memcpy(saved_output, f.output, sizeof(saved_output));
    f.written = 1234u;
    saved_written = f.written;
    /* Both the branch and its output must remain uncommitted on a
     * too-small output buffer. Test the entire buffer as a canary. */
    CHECK(be_step(&f.executor, f.output, 1u, &f.written) == BE_NO_SPACE);
    CHECK(memcmp(&f.executor, &saved, sizeof(saved)) == 0);
    CHECK(memcmp(f.entries, saved_entries, sizeof(saved_entries)) == 0);
    CHECK(memcmp(f.storage, saved_storage, sizeof(saved_storage)) == 0);
    CHECK(memcmp(f.output, saved_output, sizeof(saved_output)) == 0);
    CHECK(f.store.count == saved_count && f.written == saved_written);
    CHECK(be_step(&f.executor, f.output, sizeof(f.output),
                  &f.written) == BE_OK);
    CHECK(f.written == strlen(c->expected_output));
    CHECK(memcmp(f.output, c->expected_output, f.written) == 0);
    for (i = f.written; i < sizeof(f.output); ++i)
        CHECK(f.output[i] == 0x6bu);
    CHECK(f.store.count == saved_count);
    CHECK(memcmp(f.entries, saved_entries, sizeof(saved_entries)) == 0);
    CHECK(memcmp(f.storage, saved_storage, sizeof(saved_storage)) == 0);
    CHECK(bp_validate(&f.program) == BP_OK);
    return 0;
}

static int c1_if_dispatch(void)
{
    static const IFDispatchCase cases[] = {
        {"IF NOT 0 THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"",
         "TAKEN\n", 0, 0, 0, 0, 0},
        {"IF 1 AND 1 THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"",
         "TAKEN\n", 0, 0, 0, 0, 0},
        {"IF 0 AND 1 THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"",
         "BAD\n", 0, 0, 0, 0, 0},
        {"IF A% AND 1 THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"",
         "TAKEN\n", 1, 0, 1, 0, 0},
        {"IF A% THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"",
         "TAKEN\n", 1, 0, 1, 0, 0},
        {"IF A% THEN PRINT #8,\"AND\" ELSE PRINT #8,\"XOR\"",
         "AND\n", 1, 0, 1, 0, 0},
        {"IF A%<B% THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"",
         "TAKEN\n", 0, 1, 1, 1, 0},
        {"IF A%<B% THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"",
         "BAD\n", 2, 1, 1, 1, 0},
        {"IF A%<B% THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"",
         "TAKEN\n", 0, 1, 1, 1, 1}
    };
    Fixture f;
    size_t i;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        CHECK(c1_if_dispatch_case(&cases[i]) == 0);
    }
    /* Error in an unparenthesized logical IF: no branch, store or
     * output may change. No CPC ERR number is inferred. */
    CHECK(init(&f) == 0);
    CHECK(add(&f, 10u,
        "IF 1 AND (4\\0) THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"") == 0);
    CHECK(be_init_with_store(&f.executor, &f.program, &f.store) == BE_OK);
    CHECK(raw_step_failure(&f, BE_DIVISION_BY_ZERO) == 0);
    CHECK(init(&f) == 0);
    CHECK(add(&f, 10u,
        "IF (32767+1) AND 1 THEN PRINT #8,\"TAKEN\" ELSE PRINT #8,\"BAD\"") == 0);
    CHECK(be_init_with_store(&f.executor, &f.program, &f.store) == BE_OK);
    CHECK(raw_step_failure(&f, BE_INTEGER_OVERFLOW) == 0);
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
    CHECK(imported_negative_and_types()==0);
    CHECK(independent_variable_names()==0);
    CHECK(c1_if_dispatch()==0);
    printf("J1.22-B native: 24 oracle scenarios + negative gates PASS\n");
    return 0;
}
