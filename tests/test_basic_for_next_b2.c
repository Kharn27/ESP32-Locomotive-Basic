/* J1.12-B2 C99 host runtime: bounded loops, safety, rollback, interactions. */
#include "basic_executor.h"
#include "basic_program.h"
#include "basic_tokenizer.h"
#include "basic_variable_store.h"
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x);return 1;} } while(0)
typedef struct {
    BasicProgram program;
    uint8_t storage[4096];
    BasicVariableStore store;
    BasicVariableEntry entries[16];
    BasicExecutor executor;
    uint8_t output[256];
    size_t written;
} Fixture;

static int setup(Fixture *f) {
    memset(f,0,sizeof(*f));
    CHECK(bp_init(&f->program,f->storage,sizeof(f->storage))==BP_OK);
    CHECK(bvs_init(&f->store,f->entries,16u)==BVS_OK);
    return 0;
}
static int put(Fixture *f,unsigned line,const char *source) {
    uint8_t tokens[256];
    size_t length=0u;
    CHECK(bt_tokenize((const uint8_t *)source,strlen(source),
                      tokens,sizeof(tokens),&length)==BT_OK);
    CHECK(bp_put(&f->program,(uint16_t)line,tokens,length)==BP_OK);
    return 0;
}
static int start(Fixture *f) {
    CHECK(be_init_with_store(&f->executor,&f->program,&f->store)==BE_OK);
    return 0;
}
static int check_run(Fixture *f,const char *expected) {
    char all[2048];
    size_t total=0u,iterations;
    memset(all,0,sizeof(all));
    for(iterations=0u; iterations<200u; ++iterations) {
        BEStatus status;
        f->written=1234u;
        status=be_step(&f->executor,f->output,sizeof(f->output),&f->written);
        if(status==BE_END) break;
        CHECK(status==BE_OK);
        CHECK(f->written<=sizeof(f->output));
        CHECK(total+f->written<sizeof(all));
        memcpy(all+total,f->output,f->written);
        total+=f->written;
    }
    CHECK(iterations<200u);
    CHECK(total==strlen(expected) && memcmp(all,expected,total)==0);
    CHECK(f->executor.for_depth==0u && f->executor.call_depth==0u);
    return 0;
}
static int rollback(Fixture *f,BEStatus expected,size_t capacity) {
    BasicExecutor prior=f->executor;
    BasicVariableStore vars=f->store;
    BasicVariableEntry entries[16];
    uint8_t program[4096],before[256];
    size_t old_written=731u;
    memcpy(entries,f->entries,sizeof(entries));
    memcpy(program,f->storage,sizeof(program));
    memset(f->output,0x6b,sizeof(f->output));
    memcpy(before,f->output,sizeof(before));
    f->written=old_written;
    CHECK(be_step(&f->executor,f->output,capacity,&f->written)==expected);
    CHECK(memcmp(&prior,&f->executor,sizeof(prior))==0);
    CHECK(memcmp(&vars,&f->store,sizeof(vars))==0);
    CHECK(memcmp(entries,f->entries,sizeof(entries))==0);
    CHECK(memcmp(program,f->storage,sizeof(program))==0);
    CHECK(memcmp(before,f->output,sizeof(before))==0);
    CHECK(f->written==old_written);
    return 0;
}
static int cases(void) {
    Fixture f;
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 3")==0);
    CHECK(put(&f,20,"PRINT I%")==0);
    CHECK(put(&f,30,"NEXT I%")==0);
    CHECK(put(&f,40,"END")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f," 1 \n 2 \n 3 \n")==0);
    CHECK(start(&f)==0); /* same store, reset executor, no pending frames */
    CHECK(check_run(&f," 1 \n 2 \n 3 \n")==0);

    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 5 STEP 2")==0);
    CHECK(put(&f,20,"PRINT I%")==0);
    CHECK(put(&f,30,"NEXT")==0);
    CHECK(put(&f,40,"END")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f," 1 \n 3 \n 5 \n")==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=3 TO 1 STEP -1")==0);
    CHECK(put(&f,20,"PRINT I%")==0);
    CHECK(put(&f,30,"NEXT I%")==0);
    CHECK(put(&f,40,"END")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f," 3 \n 2 \n 1 \n")==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=3 TO 1")==0);
    CHECK(put(&f,20,"PRINT I%")==0);
    CHECK(put(&f,30,"NEXT I%")==0);
    CHECK(put(&f,40,"PRINT 8")==0);
    CHECK(put(&f,50,"END")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f,"8\n")==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=-32768 TO -32768")==0);
    CHECK(put(&f,20,"PRINT I%")==0);
    CHECK(put(&f,30,"NEXT I%")==0);
    CHECK(put(&f,40,"END")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f,"-32768 \n")==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=32766 TO 32766")==0);
    CHECK(put(&f,20,"PRINT I%")==0);
    CHECK(put(&f,30,"NEXT I%")==0);
    CHECK(put(&f,40,"END")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f," 32766 \n")==0);
    return 0;
}
static int nested_and_flow(void) {
    Fixture f;
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 2")==0);
    CHECK(put(&f,20,"FOR J%=3 TO 4")==0);
    CHECK(put(&f,30,"PRINT I%")==0);
    CHECK(put(&f,40,"PRINT J%")==0);
    CHECK(put(&f,50,"NEXT J%")==0);
    CHECK(put(&f,60,"NEXT I%")==0);
    CHECK(put(&f,70,"END")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f," 1 \n 3 \n 1 \n 4 \n 2 \n 3 \n 2 \n 4 \n")==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 2")==0);
    CHECK(put(&f,20,"PRINT I%:NEXT I%")==0);
    CHECK(put(&f,30,"END")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f," 1 \n 2 \n")==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 3")==0);
    CHECK(put(&f,20,"PRINT I%")==0);
    CHECK(put(&f,30,"GOTO 50")==0);
    CHECK(put(&f,40,"NEXT I%")==0);
    CHECK(put(&f,50,"PRINT 99")==0);
    CHECK(put(&f,60,"END")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f," 1 \n99\n")==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 3")==0);
    CHECK(put(&f,20,"PRINT I%")==0);
    CHECK(put(&f,30,"END")==0);
    CHECK(put(&f,40,"NEXT I%")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f," 1 \n")==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 2")==0);
    CHECK(put(&f,20,"PRINT I%:'NEXT J%")==0);
    CHECK(put(&f,30,"NEXT I%")==0);
    CHECK(put(&f,40,"END")==0);
    CHECK(start(&f)==0);
    CHECK(check_run(&f," 1 \n 2 \n")==0);
    return 0;
}
static int faults(void) {
    Fixture f;
    unsigned i;
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"NEXT I%")==0);
    CHECK(start(&f)==0);
    CHECK(rollback(&f,BE_NEXT_WITHOUT_FOR,sizeof(f.output))==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 2")==0);
    CHECK(put(&f,20,"PRINT I%")==0);
    CHECK(put(&f,30,"NEXT J%")==0);
    CHECK(start(&f)==0);
    CHECK(rollback(&f,BE_NEXT_VARIABLE_MISMATCH,sizeof(f.output))==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 2")==0);
    CHECK(start(&f)==0);
    CHECK(rollback(&f,BE_FOR_WITHOUT_NEXT,sizeof(f.output))==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 2")==0);
    CHECK(put(&f,20,"PRINT I%")==0);
    CHECK(put(&f,30,"NEXT I%")==0);
    CHECK(start(&f)==0);
    CHECK(be_step(&f.executor,f.output,sizeof(f.output),&f.written)==BE_OK);
    CHECK(rollback(&f,BE_NO_SPACE,1u)==0); /* PRINT needs >1 */
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=32767 TO 32767")==0);
    CHECK(put(&f,20,"NEXT I%")==0);
    CHECK(start(&f)==0);
    CHECK(be_step(&f.executor,f.output,sizeof(f.output),&f.written)==BE_OK);
    CHECK(rollback(&f,BE_INTEGER_OVERFLOW,sizeof(f.output))==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 2 STEP 0")==0);
    CHECK(put(&f,20,"NEXT I%")==0);
    CHECK(start(&f)==0);
    CHECK(rollback(&f,BE_UNSUPPORTED,sizeof(f.output))==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"FOR I%=1 TO 2")==0);
    CHECK(put(&f,20,"NEXT I%")==0);
    CHECK(bvs_init(&f.store,NULL,0u)==BVS_OK);
    CHECK(start(&f)==0);
    CHECK(rollback(&f,BE_STORE_FULL,sizeof(f.output))==0);
    CHECK(setup(&f)==0);
    for(i=0u;i<9u;++i) CHECK(put(&f,10u+i*10u,"FOR I%=1 TO 1")==0);
    for(i=0u;i<9u;++i) CHECK(put(&f,100u+i*10u,"NEXT I%")==0);
    CHECK(start(&f)==0);
    for(i=0u;i<8u;++i)
        CHECK(be_step(&f.executor,f.output,sizeof(f.output),&f.written)==BE_OK);
    CHECK(rollback(&f,BE_FOR_STACK_FULL,sizeof(f.output))==0);
    return 0;
}
static int isolation_and_calls(void) {
    Fixture a,b;
    BasicExecutor before;
    CHECK(setup(&a)==0 && setup(&b)==0);
    CHECK(put(&a,10,"FOR I%=1 TO 2")==0);
    CHECK(put(&a,20,"GOSUB 100")==0);
    CHECK(put(&a,30,"NEXT I%")==0);
    CHECK(put(&a,40,"END")==0);
    CHECK(put(&a,100,"PRINT I%")==0);
    CHECK(put(&a,110,"RETURN")==0);
    CHECK(start(&a)==0);
    CHECK(check_run(&a," 1 \n 2 \n")==0);
    CHECK(put(&b,10,"FOR J%=1 TO 1")==0);
    CHECK(put(&b,20,"PRINT J%")==0);
    CHECK(put(&b,30,"NEXT J%")==0);
    CHECK(put(&b,40,"END")==0);
    CHECK(start(&b)==0);
    CHECK(be_step(&b.executor,b.output,sizeof(b.output),&b.written)==BE_OK);
    CHECK(b.executor.for_depth==1u && a.executor.for_depth==0u);
    before=b.executor;
    CHECK(be_step(&b.executor,(uint8_t *)&b.executor,sizeof(b.executor),
                  &b.written)==BE_OVERLAP);
    CHECK(memcmp(&before,&b.executor,sizeof(before))==0);
    CHECK(check_run(&b," 1 \n")==0);
    return 0;
}
int main(void) {
    CHECK(cases()==0);
    CHECK(nested_and_flow()==0);
    CHECK(faults()==0);
    CHECK(isolation_and_calls()==0);
    puts("PASS J1.12-B2 native C99 FOR/NEXT regression, rollback, 16-bit boundaries");
    return 0;
}
