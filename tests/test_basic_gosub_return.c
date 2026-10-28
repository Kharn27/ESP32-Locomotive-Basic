/* J1.11-B C99 portable control-flow regression, not a CPC ROM test. */
#include "basic_executor.h"
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_session_runtime.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x); return 1; } } while (0)
typedef struct {
    BasicProgram program; uint8_t storage[2048];
    BasicExecutor exec; uint8_t out[64]; size_t written;
} Fixture;
static int setup(Fixture *f) {
    memset(f,0,sizeof(*f));
    CHECK(bp_init(&f->program,f->storage,sizeof(f->storage))==BP_OK);
    return 0;
}
static int put(Fixture *f,uint16_t num,const char *src) {
    uint8_t t[160]; size_t n=0u;
    CHECK(bt_tokenize((const uint8_t*)src,strlen(src),t,sizeof(t),&n)==BT_OK);
    CHECK(bp_put(&f->program,num,t,n)==BP_OK);
    return 0;
}
static int success(Fixture *f,const char *expected) {
    size_t n=strlen(expected); f->written=999u;
    CHECK(be_step(&f->exec,f->out,sizeof(f->out),&f->written)==BE_OK);
    CHECK(f->written==n && memcmp(f->out,expected,n)==0);
    return 0;
}
static int failure(Fixture *f,BEStatus want,size_t cap) {
    BasicExecutor old=f->exec;
    uint8_t before[sizeof(f->out)], program_before[sizeof(f->storage)];
    memset(f->out,0x59,sizeof(f->out));
    memcpy(before,f->out,sizeof(before));
    memcpy(program_before,f->storage,sizeof(program_before));
    f->written=871u;
    CHECK(be_step(&f->exec,f->out,cap,&f->written)==want);
    CHECK(f->written==871u && memcmp(&old,&f->exec,sizeof(old))==0);
    CHECK(memcmp(before,f->out,sizeof(before))==0);
    CHECK(memcmp(program_before,f->storage,sizeof(program_before))==0);
    return 0;
}
static int encoding(void) {
    static const uint8_t expected[]={0x9f,0x20,0x1e,0x64,0x00};
    static const char *invalid[]={"GOSUB","GOSUB 0","GOSUB 65536","GOSUB A%",
        "GOSUB 100+1","RETURN 1","GOSUB 100:","GOSUB :PRINT 2"};
    uint8_t t[96],out[96],again[96],before[96]; size_t n=0u,m=0u,k=0u,i;
    CHECK(bt_tokenize((const uint8_t*)"GOSUB 100",9,t,sizeof(t),&n)==BT_OK);
    CHECK(n==sizeof(expected) && memcmp(t,expected,n)==0);
    CHECK(bl_detokenize(t,n,out,sizeof(out),&m)==BL_OK);
    CHECK(m==9 && memcmp(out,"GOSUB 100",m)==0);
    CHECK(bt_tokenize(out,m,again,sizeof(again),&k)==BT_OK);
    CHECK(k==n && memcmp(t,again,k)==0);
    CHECK(bt_tokenize((const uint8_t*)"RETURN",6,t,sizeof(t),&n)==BT_OK);
    CHECK(n==1 && t[0]==0xc9u);
    CHECK(bl_detokenize(t,n,out,sizeof(out),&m)==BL_OK);
    CHECK(m==6 && memcmp(out,"RETURN",m)==0);
    CHECK(bt_tokenize((const uint8_t*)"GOSUB 100:PRINT 22",18,t,sizeof(t),&n)==BT_OK);
    CHECK(bl_detokenize(t,n,out,sizeof(out),&m)==BL_OK);
    CHECK(m==18 && memcmp(out,"GOSUB 100:PRINT 22",m)==0);
    for(i=0;i<sizeof(invalid)/sizeof(invalid[0]);++i) {
        memset(t,0x55,sizeof(t)); memcpy(before,t,sizeof(t)); n=919u;
        CHECK(bt_tokenize((const uint8_t*)invalid[i],strlen(invalid[i]),
                          t,sizeof(t),&n)!=BT_OK);
        CHECK(n==919u && memcmp(t,before,sizeof(t))==0);
    }
    { static const uint8_t broken[]={0x9fu,0x20u,0x1eu,0x64u};
      m=888u;
      CHECK(bl_detokenize(broken,sizeof(broken),out,sizeof(out),&m)==BL_TRUNCATED);
      CHECK(m==888u);
    }
    return 0;
}
static int nested(void) {
    Fixture f;
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"GOSUB 100")==0);
    CHECK(put(&f,20,"PRINT 21")==0);
    CHECK(put(&f,30,"END")==0);
    CHECK(put(&f,100,"PRINT 101")==0);
    CHECK(put(&f,110,"GOSUB 200")==0);
    CHECK(put(&f,120,"PRINT 121")==0);
    CHECK(put(&f,130,"RETURN")==0);
    CHECK(put(&f,200,"PRINT 201")==0);
    CHECK(put(&f,210,"RETURN")==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK);
    CHECK(success(&f,"")==0 && f.exec.call_depth==1u);
    CHECK(success(&f,"101\n")==0);
    CHECK(success(&f,"")==0 && f.exec.call_depth==2u);
    CHECK(success(&f,"201\n")==0);
    CHECK(success(&f,"")==0 && f.exec.call_depth==1u);
    CHECK(success(&f,"121\n")==0);
    CHECK(success(&f,"")==0 && f.exec.call_depth==0u);
    CHECK(success(&f,"21\n")==0);
    CHECK(success(&f,"")==0);
    CHECK(failure(&f,BE_END,sizeof(f.out))==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK && f.exec.call_depth==0u);
    return 0;
}
static int continuation(void) {
    Fixture f;
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"GOSUB 100:PRINT 22")==0);
    CHECK(put(&f,20,"END")==0);
    CHECK(put(&f,100,"PRINT 101")==0);
    CHECK(put(&f,110,"RETURN")==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK);
    CHECK(success(&f,"")==0 && f.exec.call_depth==1u);
    CHECK(success(&f,"101\n")==0);
    CHECK(success(&f,"")==0 && f.exec.statement_offset!=0u);
    CHECK(success(&f,"22\n")==0 && f.exec.statement_offset==0u);
    CHECK(success(&f,"")==0);
    CHECK(failure(&f,BE_END,sizeof(f.out))==0);
    return 0;
}
static int errors(void) {
    Fixture f; size_t i;
    static const uint8_t trunc[]={0x9fu,0x20u,0x1eu,0x64u};
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"PRINT 1:GOSUB 999")==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK);
    CHECK(failure(&f,BE_MISSING_TARGET,sizeof(f.out))==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"RETURN")==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK);
    CHECK(failure(&f,BE_RETURN_WITHOUT_GOSUB,sizeof(f.out))==0);
    CHECK(setup(&f)==0);
    CHECK(bp_put(&f.program,10,trunc,sizeof(trunc))==BP_OK);
    CHECK(be_init(&f.exec,&f.program)==BE_OK);
    CHECK(failure(&f,BE_TRUNCATED,sizeof(f.out))==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"GOSUB 10")==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK);
    for(i=0u;i<BE_GOSUB_STACK_CAPACITY;++i) {
        CHECK(success(&f,"")==0 && f.exec.call_depth==i+1u);
    }
    CHECK(failure(&f,BE_CALL_STACK_FULL,sizeof(f.out))==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK && f.exec.call_depth==0u);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"GOSUB 100")==0);
    CHECK(put(&f,20,"END")==0);
    CHECK(put(&f,100,"PRINT 101")==0);
    CHECK(put(&f,110,"RETURN")==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK);
    CHECK(success(&f,"")==0 && f.exec.call_depth==1u);
    CHECK(failure(&f,BE_NO_SPACE,0u)==0);
    CHECK(success(&f,"101\n")==0 && f.exec.call_depth==1u);
    /* An emitting PRINT before RETURN must not POP when output is too small. */
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"GOSUB 100")==0);
    CHECK(put(&f,20,"END")==0);
    CHECK(put(&f,100,"PRINT 2:RETURN")==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK);
    CHECK(success(&f,"")==0 && f.exec.call_depth==1u);
    CHECK(failure(&f,BE_NO_SPACE,0u)==0);
    CHECK(success(&f,"2\n")==0 && f.exec.call_depth==0u);
    /* An END reached inside a subroutine clears abandoned return frames. */
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"GOSUB 100")==0);
    CHECK(put(&f,20,"PRINT 3")==0);
    CHECK(put(&f,100,"END")==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK);
    CHECK(success(&f,"")==0 && f.exec.call_depth==1u);
    CHECK(success(&f,"")==0 && f.exec.call_depth==0u);
    CHECK(failure(&f,BE_END,sizeof(f.out))==0);
    return 0;
}
static int lifecycle(void) {
    Fixture f; BasicExecutor other; BasicSessionRuntime runtime;
    uint8_t out[64],tmp[160]; size_t n=0u;
    static const uint8_t run[]="RUN",new_cmd[]="NEW";
    CHECK(setup(&f)==0);
    CHECK(put(&f,10,"GOSUB 100")==0);
    CHECK(put(&f,20,"END")==0);
    CHECK(put(&f,100,"RETURN")==0);
    CHECK(be_init(&f.exec,&f.program)==BE_OK);
    CHECK(be_init(&other,&f.program)==BE_OK);
    CHECK(success(&f,"")==0 && f.exec.call_depth==1u);
    CHECK(other.call_depth==0u && other.cursor==0u);
    CHECK(be_step(&other,out,sizeof(out),&n)==BE_OK && other.call_depth==1u);
    CHECK(success(&f,"")==0 && f.exec.call_depth==0u && other.call_depth==1u);
    CHECK(bsr_init(&runtime,&f.program).status==BSR_OK);
    CHECK(bsr_submit(&runtime,run,3u,tmp,sizeof(tmp),out,sizeof(out),&n).status==BSR_OK);
    CHECK(bsr_step(&runtime,out,sizeof(out),&n).status==BSR_OK);
    CHECK(runtime.executor.call_depth==1u);
    CHECK(bsr_stop(&runtime).status==BSR_OK && runtime.executor.call_depth==0u);
    CHECK(bsr_submit(&runtime,run,3u,tmp,sizeof(tmp),out,sizeof(out),&n).status==BSR_OK);
    CHECK(runtime.executor.call_depth==0u);
    CHECK(bsr_step(&runtime,out,sizeof(out),&n).status==BSR_OK);
    CHECK(runtime.executor.call_depth==1u);
    CHECK(bsr_stop(&runtime).status==BSR_OK);
    CHECK(bsr_submit(&runtime,new_cmd,3u,tmp,sizeof(tmp),out,sizeof(out),&n).status==BSR_OK);
    CHECK(runtime.executor.call_depth==0u && f.program.size==2u);
    return 0;
}
int main(void) {
    CHECK(encoding()==0);
    CHECK(nested()==0);
    CHECK(continuation()==0);
    CHECK(errors()==0);
    CHECK(lifecycle()==0);
    puts("PASS J1.11-B control flow, atomic failures, bounded stack and lifecycle");
    return 0;
}
