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

int main(void)
{
    CHECK(skipped_family("DATA 1")==0);
    CHECK(skipped_family("READ A%")==0);
    CHECK(skipped_family("RESTORE")==0);
    CHECK(eight_frames()==0);
    puts("J1.25-B2-C1 WHILE skipped DATA/READ/RESTORE and 8 frames PASS");
    return 0;
}
