/* J1.25-B2-C1: RED/GREEN non-regression — a skipped DATA-family
 * statement must never change the previously accepted WHILE engine.
 * Independent of CPC oracle mutation and firmware. */
#include "basic_executor.h"
#include "basic_tokenizer.h"
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x); return 1; \
} } while (0)

typedef struct {
    uint8_t storage[2048], output[64];
    BasicProgram program;
    BasicExecutor executor;
    BasicVariableStore store;
    BasicVariableEntry entries[8];
} TestContext;

static int add(TestContext *t, uint16_t number, const char *source)
{
    uint8_t body[128];
    size_t n = 0u;
    CHECK(bt_tokenize((const uint8_t *)source,strlen(source),
                      body,sizeof(body),&n) == BT_OK);
    CHECK(bp_put(&t->program,number,body,n)==BP_OK);
    return 0;
}

static int run(TestContext *t, const char *expected,
               size_t expected_max_while)
{
    uint8_t captured[128];
    size_t total=0u, step, max_depth=0u;
    CHECK(bvs_init(&t->store,t->entries,8u)==BVS_OK);
    CHECK(be_init_with_store(&t->executor,&t->program,&t->store)==BE_OK);
    for(step=0u;step<120u;++step) {
        size_t written=919u;
        BEStatus st=be_step(&t->executor,t->output,
                            sizeof(t->output),&written);
        if(st==BE_END) {
            CHECK(written==919u);
            break;
        }
        if(st!=BE_OK) {
            fprintf(stderr,"WHILE C1 status=%d step=%zu cursor=%zu depth=%zu\n",
                    (int)st,step,t->executor.cursor,t->executor.while_depth);
            return 1;
        }
        CHECK(total+written<=sizeof(captured));
        memcpy(captured+total,t->output,written);
        total+=written;
        if(t->executor.while_depth>max_depth)
            max_depth=t->executor.while_depth;
    }
    CHECK(step<120u);
    CHECK(total==strlen(expected));
    CHECK(memcmp(captured,expected,total)==0);
    CHECK(max_depth==expected_max_while);
    CHECK(t->executor.while_depth==0u);
    CHECK(t->executor.while_stack[7].after_cursor==0u);
    CHECK(t->executor.while_stack[7].after_statement==0u);
    return 0;
}

/* On main B1, the GOTO skips the entire line 20. The otherwise identical
 * WHILE sequence is in J1.24-B2's sealed native corpus EQ_ONCE. */
static int skipped_family(const char *unreached)
{
    TestContext t;
    memset(&t,0,sizeof(t));
    CHECK(bp_init(&t.program,t.storage,sizeof(t.storage))==BP_OK);
    CHECK(add(&t,10u,"GOTO 30")==0);
    CHECK(add(&t,20u,unreached)==0);
    CHECK(add(&t,30u,"A%=1")==0);
    CHECK(add(&t,40u,"WHILE A%=1")==0);
    CHECK(add(&t,50u,"PRINT \"T\"")==0);
    CHECK(add(&t,60u,"A%=2")==0);
    CHECK(add(&t,70u,"WEND")==0);
    CHECK(add(&t,80u,"PRINT \"END\"")==0);
    CHECK(add(&t,90u,"END")==0);
    return run(&t,"T\nEND\n",1u);
}

/* Eight nested live WHILE frames; line 20 remains unreachable and must
 * not steal the last frame's after_* fields or constrain accepted depth. */
static int eight_frames(void)
{
    TestContext t;
    uint16_t number;
    memset(&t,0,sizeof(t));
    CHECK(bp_init(&t.program,t.storage,sizeof(t.storage))==BP_OK);
    CHECK(add(&t,10u,"GOTO 30")==0);
    CHECK(add(&t,20u,"DATA 1")==0);
    CHECK(add(&t,30u,"A%=1")==0);
    for(number=40u;number<=110u;number=(uint16_t)(number+10u))
        CHECK(add(&t,number,"WHILE A%=1")==0);
    CHECK(add(&t,120u,"A%=2")==0);
    for(number=130u;number<=200u;number=(uint16_t)(number+10u))
        CHECK(add(&t,number,"WEND")==0);
    CHECK(add(&t,210u,"PRINT \"END\"")==0);
    CHECK(add(&t,220u,"END")==0);
    return run(&t,"END\n",8u);
}


/* Fail-closed, byte-atomic cross-family attempts in the last live frame:
 * the B2 DATA offsets share two members of frame #8, so a READ/RESTORE
 * inside WHILE must never overwrite their WHILE continuation addresses. */
static int denied_in_eight_frames(const char *statement)
{
    TestContext t;
    BasicExecutor before;
    BasicVariableEntry entries_before[8];
    uint8_t before_output[sizeof(t.output)];
    size_t count, n;
    BEStatus status;
    uint16_t number;
    memset(&t,0,sizeof(t));
    CHECK(bp_init(&t.program,t.storage,sizeof(t.storage))==BP_OK);
    CHECK(add(&t,10u,"GOTO 30")==0);
    CHECK(add(&t,20u,"DATA 1")==0);
    CHECK(add(&t,30u,"A%=1")==0);
    for(number=40u;number<=110u;number=(uint16_t)(number+10u))
        CHECK(add(&t,number,"WHILE A%=1")==0);
    CHECK(add(&t,120u,statement)==0);
    for(number=130u;number<=200u;number=(uint16_t)(number+10u))
        CHECK(add(&t,number,"WEND")==0);
    CHECK(add(&t,210u,"END")==0);
    CHECK(bvs_init(&t.store,t.entries,8u)==BVS_OK);
    CHECK(be_init_with_store(&t.executor,&t.program,&t.store)==BE_OK);
    for(n=0u;n<10u;++n) {
        size_t written=901u;
        status=be_step(&t.executor,t.output,sizeof(t.output),&written);
        CHECK(status==BE_OK && written==0u);
    }
    CHECK(t.executor.while_depth==8u);
    CHECK(t.executor.while_stack[7].header_cursor!=0u);
    before=t.executor;
    memcpy(entries_before,t.entries,sizeof(entries_before));
    memset(t.output,0x69,sizeof(t.output));
    memcpy(before_output,t.output,sizeof(t.output));
    count=994u;
    status=be_step(&t.executor,t.output,sizeof(t.output),&count);
    CHECK(status==BE_UNSUPPORTED);
    CHECK(count==994u);
    CHECK(memcmp(&t.executor,&before,sizeof(before))==0);
    CHECK(memcmp(t.entries,entries_before,sizeof(entries_before))==0);
    CHECK(memcmp(t.output,before_output,sizeof(t.output))==0);
    CHECK(t.executor.while_depth==8u);
    return 0;
}

/* The opposite order is also outside the sealed B2 corpus: a consumed
 * READ cursor cannot be converted into an active WHILE frame. */
static int denied_while_after_read(void)
{
    TestContext t;
    BasicExecutor before;
    BasicVariableEntry entries_before[8];
    uint8_t before_output[sizeof(t.output)];
    size_t n, count=994u;
    BEStatus status;
    memset(&t,0,sizeof(t));
    CHECK(bp_init(&t.program,t.storage,sizeof(t.storage))==BP_OK);
    CHECK(add(&t,10u,"DATA 1")==0);
    CHECK(add(&t,20u,"READ A%")==0);
    CHECK(add(&t,30u,"WHILE A%=1")==0);
    CHECK(add(&t,40u,"WEND")==0);
    CHECK(add(&t,50u,"END")==0);
    CHECK(bvs_init(&t.store,t.entries,8u)==BVS_OK);
    CHECK(be_init_with_store(&t.executor,&t.program,&t.store)==BE_OK);
    for(n=0u;n<2u;++n) {
        size_t written=994u;
        CHECK(be_step(&t.executor,t.output,sizeof(t.output),&written)==BE_OK);
        CHECK(written==0u);
    }
    CHECK(t.store.count==1u && t.entries[0].value.data.integer==1);
    CHECK(t.executor.while_depth==0u);
    CHECK(t.executor.while_stack[7].after_cursor!=0u);
    before=t.executor;
    memcpy(entries_before,t.entries,sizeof(entries_before));
    memset(t.output,0x69,sizeof(t.output));
    memcpy(before_output,t.output,sizeof(t.output));
    status=be_step(&t.executor,t.output,sizeof(t.output),&count);
    CHECK(status==BE_UNSUPPORTED);
    CHECK(count==994u);
    CHECK(memcmp(&t.executor,&before,sizeof(before))==0);
    CHECK(memcmp(t.entries,entries_before,sizeof(entries_before))==0);
    CHECK(memcmp(t.output,before_output,sizeof(t.output))==0);
    return 0;
}

int main(void)
{
    CHECK(skipped_family("DATA 1")==0);
    CHECK(skipped_family("READ A%")==0);
    CHECK(skipped_family("RESTORE")==0);
    CHECK(eight_frames()==0);
    CHECK(denied_in_eight_frames("DATA 1")==0);
    CHECK(denied_in_eight_frames("READ B%")==0);
    CHECK(denied_in_eight_frames("RESTORE")==0);
    CHECK(denied_while_after_read()==0);
    puts("J1.25-B2-C1 WHILE skipped DATA/READ/RESTORE and 8 frames PASS");
    return 0;
}
