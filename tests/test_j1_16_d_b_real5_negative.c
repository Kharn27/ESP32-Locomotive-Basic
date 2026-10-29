/* J1.16-D-B: independently witnessed signed REAL5 -0.5, no generic sign math. */
#include "basic_session_runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if(!(x)){fprintf(stderr,"%s:%d %s\n",__FILE__,__LINE__,#x);return 1;} } while(0)
typedef struct {
    BasicProgram program,again;
    BasicSessionRuntime runtime;
    BasicVariableStore store;
    BasicVariableEntry entries[3];
    uint8_t storage[1024], replay[1024], temp[256], output[256];
    size_t written;
} F;
static int init(F *f) {
    memset(f,0xa5,sizeof(*f));
    CHECK(bp_init(&f->program,f->storage,sizeof(f->storage))==BP_OK);
    CHECK(bvs_init(&f->store,f->entries,3u)==BVS_OK);
    CHECK(bsr_init_with_store(&f->runtime,&f->program,&f->store).status==BSR_OK);
    return 0;
}
static BSRResult send(F *f,const char *s) {
    return bsr_submit(&f->runtime,(const uint8_t *)s,strlen(s),
                      f->temp,sizeof(f->temp),f->output,sizeof(f->output),&f->written);
}
static BSRResult step(F *f,size_t n) {
    return bsr_step(&f->runtime,f->output,n,&f->written);
}
static int populate(F *f) {
    CHECK(send(f,"NEW").status==BSR_OK);
    CHECK(send(f,"10 A=-0.5").status==BSR_OK);
    CHECK(send(f,"20 PRINT A").status==BSR_OK);
    CHECK(send(f,"30 END").status==BSR_OK);
    return 0;
}
static BasicVariableKey akey(uint8_t type) {
    BasicVariableKey k;
    memset(&k,0,sizeof(k));k.type=type;k.name_length=1u;k.name[0]='A';
    return k;
}
/* Read the original J1.16-A tokenised images and CRLF printer bytes
 * without rewriting any historical evidence. The original was instrumented
 * with PRINT #8 at L30, so only L10/L20 match the native image exactly. */
static int oracle(F *f,const char *dir) {
    static const uint8_t l10[]={0x11,0,0x0a,0,0x0d,0,0,0xc1,0xef,0xf5,0x1f,0,0,0,0,0x80,0};
    static const uint8_t l20[]={0x0b,0,0x14,0,0xbf,0x20,0x0d,0,0,0xc1,0};
    static const uint8_t native_end[]={0x06,0,0x1e,0,0x98,0};
    static const uint8_t instrumented[]={0x0e,0,0x1e,0,0xbf,0x20,0x23,0x16,0x2c,0x0d,0,0,0xc1,0};
    static const uint8_t printer_expected[]={0x2d,0x30,0x2e,0x35,0x20,0x0d,0x0a};
    uint8_t bytes[512],printer[sizeof(printer_expected)];
    char path[512];FILE *fp;size_t n;
    CHECK(snprintf(path,sizeof(path),"%s/original/R_NEG_HALF/program.bin",dir)>0);
    fp=fopen(path,"rb");CHECK(fp!=NULL);n=fread(bytes,1u,sizeof(bytes),fp);
    CHECK(!ferror(fp) && fclose(fp)==0);
    CHECK(n>=sizeof(l10)+sizeof(l20)+sizeof(instrumented)+8u);
    CHECK(bytes[n-2u]==0 && bytes[n-1u]==0);
    CHECK(memcmp(bytes,l10,sizeof(l10))==0);
    CHECK(memcmp(bytes+sizeof(l10),l20,sizeof(l20))==0);
    CHECK(memcmp(bytes+sizeof(l10)+sizeof(l20),instrumented,sizeof(instrumented))==0);
    CHECK(bytes[sizeof(l10)+sizeof(l20)+sizeof(instrumented)+2u]==40u);
    CHECK(f->program.size==sizeof(l10)+sizeof(l20)+sizeof(native_end)+2u);
    CHECK(memcmp(f->storage,bytes,sizeof(l10)+sizeof(l20))==0);
    CHECK(memcmp(f->storage+sizeof(l10)+sizeof(l20),native_end,sizeof(native_end))==0);
    CHECK(f->storage[f->program.size-2u]==0 && f->storage[f->program.size-1u]==0);
    CHECK(f->program.size!=n);
    CHECK(snprintf(path,sizeof(path),"%s/original/R_NEG_HALF/run/printer.dat",dir)>0);
    fp=fopen(path,"rb");CHECK(fp!=NULL);
    CHECK(fread(printer,1u,sizeof(printer),fp)==sizeof(printer));
    CHECK(!ferror(fp) && fclose(fp)==0);
    CHECK(memcmp(printer,printer_expected,sizeof(printer))==0);
    puts("MATCH_EXACT_RECORD_10_20 DIFF_EXPECTED_INSTRUMENTATION MATCH_PRESENTATION");
    return 0;
}
/* Read both original/repeat CPC variable windows, including structural bytes
 * 00 00 C1 04. The 04 CPC type differs from BVT_REAL=05 in native storage.
 * The separate CTest j1_16_d_a_* anchors the independent SHA-256 seal. */
static int sealed_store_windows(const char *dir) {
    static const uint8_t windows[2][9]={
        {0,0,0xc1,0x04,0,0,0,0,0x80},
        {0,0,0xc1,0x04,0,0,0,0x80,0x80}
    };
    static const char *const names[2]={"R_HALF","R_NEG_HALF"};
    static const char *const sessions[2]={"original","repeat"};
    size_t i,j;
    for(i=0u;i<2u;++i) for(j=0u;j<2u;++j) {
        char path[512];uint8_t window[10];FILE *fp;size_t n;
        CHECK(snprintf(path,sizeof(path),"%s/%s/%s/window.bin",
                       dir,sessions[j],names[i])>0);
        fp=fopen(path,"rb");CHECK(fp!=NULL);
        n=fread(window,1u,sizeof(window),fp);
        CHECK(!ferror(fp) && fclose(fp)==0);
        CHECK(n==sizeof(windows[0]));
        CHECK(memcmp(window,windows[i],sizeof(windows[i]))==0);
    }
    puts("SEALED_D_A_WINDOWS 4/4 READ_ONLY (SHA pin via permanent CTest)");
    return 0;
}
static int list_roundtrip(F *f) {
    static const char expected[]="10 A=-0.5\n20 PRINT A\n30 END\n";
    uint8_t sink[64];size_t pos=0u,n,used=0u;
    CHECK(send(f,"LIST").status==BSR_OK);
    n=f->written;
    CHECK(n==sizeof(expected)-1u && memcmp(f->output,expected,n)==0);
    CHECK(bp_init(&f->again,f->replay,sizeof(f->replay))==BP_OK);
    while(pos<n) {
        size_t end=pos;BSResult r;
        while(end<n && f->output[end]!='\n')++end;
        CHECK(end<n && end>pos);
        r=bs_process_line(&f->again,f->output+pos,end-pos,f->temp,sizeof(f->temp),
                          sink,sizeof(sink),&used);
        CHECK(r.status==BS_OK);
        pos=end+1u;
    }
    CHECK(f->again.size==f->program.size);
    CHECK(memcmp(f->again.data,f->program.data,f->program.size)==0);
    CHECK(f->store.count==0u);
    puts("NATIVE_LIST_RETOKENIZATION_MATCH_EXACT");
    return 0;
}
static int run(F *f) {
    static const uint8_t negative[]={0,0,0,0x80,0x80};
    BasicVariableKey key=akey((uint8_t)BVT_REAL);BasicVariableValue v;
    size_t repeat;
    for(repeat=0;repeat<2u;++repeat) {
        uint8_t program_snapshot[sizeof(f->storage)];
        BSRResult r;size_t events=0u;
        CHECK(send(f,"RUN").status==BSR_OK && f->store.count==0u);
        CHECK(f->runtime.state==BSR_RUNNING);
        memcpy(program_snapshot,f->storage,sizeof(program_snapshot));
        f->written=512u;r=step(f,sizeof(f->output));
        CHECK(r.status==BSR_OK && f->written==0u && f->store.count==1u);
        CHECK(bvs_get(&f->store,&key,&v)==BVS_OK);
        CHECK(v.type==(uint8_t)BVT_REAL && memcmp(v.data.real5,negative,5u)==0);
        memset(f->output,0x77,sizeof(f->output));f->written=512u;
        r=step(f,sizeof(f->output));
        CHECK(r.status==BSR_OK && f->written==6u);
        CHECK(memcmp(f->output,"-0.5 \n",6u)==0 && f->output[6]==0x77);
        ++events;
        f->written=313u;r=step(f,sizeof(f->output));
        CHECK(r.status==BSR_OK && f->written==0u); /* silent END */
        f->written=313u;r=step(f,sizeof(f->output));
        CHECK(r.status==BSR_END && r.executor_status==BE_END);
        CHECK(f->written==313u && f->runtime.state==BSR_IDLE);
        CHECK(step(f,sizeof(f->output)).status==BSR_NOT_RUNNING);
        CHECK(events==1u && memcmp(program_snapshot,f->storage,sizeof(program_snapshot))==0);
    }
    CHECK(send(f,"NEW").status==BSR_OK && f->store.count==0u);
    CHECK(send(f,"LIST").status==BSR_OK && f->written==0u);
    puts("RUN_REPEAT ONE_NEG_REAL_PRINT_EVENT written=6 END IDLE NEW_EMPTY");
    return 0;
}
static int source_negative(void) {
    static const char *bad[]={"A=0.1","A=1.20","A=-1.25","A=0","A=1.250",
        "A=-0.50","A=-0.5 ","A=-0.5X","A= -0.5","A =-0.5",
        "LET A=-0.5","B=-0.5","a=-0.5","A!=-0.5","A=--0.5",
        "A!=1.5","A!=1.25","A=1.25:PRINT A","A=1.25 : END",
        "LET A=1.25","B=1.25","a=1.25","A=1.25X","A=1.25 ",
        "PRINT B","PRINT A:PRINT A","PRINTA","? A",
        "PRINT  A"," PRINT A","PRINT A "};
    uint8_t dest[64],saved[64];size_t written=888u,i;
    memset(dest,0x5a,sizeof(dest));memcpy(saved,dest,sizeof(dest));
    for(i=0u;i<sizeof(bad)/sizeof(bad[0]);++i){
        CHECK(bt_tokenize((const uint8_t *)bad[i],strlen(bad[i]),
                          dest,sizeof(dest),&written)!=BT_OK);
        CHECK(written==888u && memcmp(dest,saved,sizeof(dest))==0);
    }
    CHECK(bt_tokenize((const uint8_t *)"PRINT A!",8u,
                      dest,sizeof(dest),&written)==BT_OK);
    /* Signed CPC statement is 12 bytes, so 11 bytes is atomic rejection. */
    memset(dest,0x5a,sizeof(dest));
    written=2026u;
    CHECK(bt_tokenize((const uint8_t *)"A=-0.5",6u,
                      dest,11u,&written)==BT_NO_SPACE);
    CHECK(written==2026u && memcmp(dest,saved,sizeof(dest))==0);
    return 0;
}
static int submit_negative(void) {
    static const char *bad[]={"10 A=0.1","10 A=-1.25","10 A=1.20",
       "10 A=-0.5X","10 A=-0.50","10 A=-0.5:PRINT A",
       "10 LET A=-0.5","10 B=-0.5","10 a=-0.5",
       "10 A=1.25:PRINT A","20 PRINT A:PRINT A","10 A!=1.5",
       "10 B=1.25","10 a=1.25"};
    F f;size_t i;CHECK(init(&f)==0 && populate(&f)==0);
    for(i=0u;i<sizeof(bad)/sizeof(bad[0]);++i){
        uint8_t program[sizeof(f.storage)],output[sizeof(f.output)];
        BasicVariableEntry entries[3];
        BasicSessionRuntime runtime=f.runtime;BasicVariableStore store=f.store;
        f.written=919u;
        memcpy(program,f.storage,sizeof(program));memcpy(output,f.output,sizeof(output));
        memcpy(entries,f.entries,sizeof(entries));
        CHECK(send(&f,bad[i]).status==BSR_SESSION_ERROR);
        CHECK(f.written==919u && memcmp(f.storage,program,sizeof(program))==0);
        CHECK(memcmp(f.output,output,sizeof(output))==0);
        CHECK(memcmp(&f.runtime,&runtime,sizeof(runtime))==0);
        CHECK(memcmp(&f.store,&store,sizeof(store))==0);
        CHECK(memcmp(f.entries,entries,sizeof(entries))==0);
    }
    return 0;
}
static int fail(F *f,BEStatus expect,size_t capacity) {
    uint8_t program[sizeof(f->storage)],output[sizeof(f->output)];
    BasicVariableEntry entries[3];BasicVariableStore store=f->store;
    BasicExecutor exec=f->runtime.executor;BSRState state=f->runtime.state;
    BSRResult r;
    memcpy(program,f->storage,sizeof(program));memcpy(entries,f->entries,sizeof(entries));
    memset(f->output,0xc7,sizeof(f->output));memcpy(output,f->output,sizeof(output));
    f->written=1717u;r=step(f,capacity);
    CHECK(r.status==BSR_EXECUTOR_ERROR && r.executor_status==expect);
    CHECK(f->written==1717u && memcmp(f->output,output,sizeof(output))==0);
    CHECK(memcmp(f->storage,program,sizeof(program))==0);
    CHECK(memcmp(f->entries,entries,sizeof(entries))==0);
    CHECK(memcmp(&f->store,&store,sizeof(store))==0);
    CHECK(memcmp(&f->runtime.executor,&exec,sizeof(exec))==0);
    CHECK(f->runtime.state==state);
    return 0;
}
/* Falsify each part of the complete signed record without changing the
 * store, cursor, output, program or written on failure. */
static int mutated_records(void) {
    static const uint8_t exact[]={0x0d,0,0,0xc1,0xef,0xf5,0x1f,0,0,0,0,0x80};
    static const struct {size_t p;uint8_t v;} flips[]={
        {0u,0x04u},{1u,0x20u},{2u,0x01u},{3u,0xc2u},
        {4u,0xf4u},{5u,0x1fu},{6u,0x1au},{7u,0x01u},
        {8u,0x01u},{9u,0x01u},{10u,0x80u},{11u,0x81u}};
    size_t i;
    for(i=0u;i<sizeof(flips)/sizeof(flips[0])+3u;++i){
        F f;uint8_t body[sizeof(exact)+1u];size_t n=sizeof(exact);
        CHECK(init(&f)==0);memcpy(body,exact,sizeof(exact));
        if(i<sizeof(flips)/sizeof(flips[0]))body[flips[i].p]=flips[i].v;
        else if(i==sizeof(flips)/sizeof(flips[0]))--n;
        else if(i==sizeof(flips)/sizeof(flips[0])+1u)body[n++]=0x01u;
        else {
            body[5]=0x1fu;body[6]=0xf5u; /* moved sign */
        }
        CHECK(bp_put(&f.program,10u,body,n)==BP_OK);
        CHECK(send(&f,"RUN").status==BSR_OK);
        CHECK(fail(&f,BE_BAD_SEQUENCE,sizeof(f.output))==0);
    }
    /* Removing the sign produces the ALREADY SUPPORTED positive record.
     * It must not be rejected, but must store +0.5, never -0.5. */
    {
        static const uint8_t half_body[]={
            0x0d,0,0,0xc1,0xef,0x1f,0,0,0,0,0x80
        };
        static const uint8_t half_store[]={0,0,0,0,0x80};
        F f;BasicVariableKey key=akey((uint8_t)BVT_REAL);
        BasicVariableValue v;
        CHECK(init(&f)==0);
        CHECK(bp_put(&f.program,10u,half_body,sizeof(half_body))==BP_OK);
        CHECK(send(&f,"RUN").status==BSR_OK);
        CHECK(step(&f,sizeof(f.output)).status==BSR_OK);
        CHECK(bvs_get(&f.store,&key,&v)==BVS_OK);
        CHECK(memcmp(v.data.real5,half_store,sizeof(half_store))==0);
    }
    return 0;
}
static int print_negative(void) {
    F f;BasicVariableKey key=akey((uint8_t)BVT_REAL);
    BasicVariableValue value={0};size_t nochange=111u;
    CHECK(init(&f)==0);
    CHECK(send(&f,"10 PRINT A").status==BSR_OK);
    CHECK(send(&f,"RUN").status==BSR_OK);
    CHECK(fail(&f,BE_VARIABLE_NOT_FOUND,sizeof(f.output))==0);
    value.type=(uint8_t)BVT_REAL;value.data.real5[4]=0x81u;
    CHECK(bvs_assign(&f.store,&key,&value)==BVS_OK);
    CHECK(fail(&f,BE_UNSUPPORTED,sizeof(f.output))==0);
    value.data.real5[3]=0x20u;value.data.real5[4]=0x81u;
    CHECK(bvs_assign(&f.store,&key,&value)==BVS_OK);
    CHECK(fail(&f,BE_NO_SPACE,6u)==0);
    CHECK(step(&f,sizeof(f.output)).status==BSR_OK);
    CHECK(f.written==7u && memcmp(f.output," 1.25 \n",7u)==0);
    CHECK(init(&f)==0);
    CHECK(send(&f,"10 PRINT A!").status==BSR_OK);
    CHECK(send(&f,"RUN").status==BSR_OK);
    CHECK(fail(&f,BE_UNSUPPORTED,sizeof(f.output))==0);
    CHECK(init(&f)==0);
    CHECK(send(&f,"10 PRINT A").status==BSR_OK);
    CHECK(send(&f,"RUN").status==BSR_OK);
    key.type=(uint8_t)BVT_INTEGER;value.type=(uint8_t)BVT_INTEGER;
    value.data.integer=42;
    CHECK(bvs_assign(&f.store,&key,&value)==BVS_OK);
    CHECK(fail(&f,BE_VARIABLE_NOT_FOUND,sizeof(f.output))==0);
    CHECK(bsr_step(&f.runtime,(uint8_t *)(void *)f.entries,1u,
                   &nochange).status==BSR_OVERLAP);
    CHECK(nochange==111u);
    CHECK(init(&f)==0);
    CHECK(send(&f,"10 PRINT A").status==BSR_OK);
    CHECK(bsr_init(&f.runtime,&f.program).status==BSR_OK);
    CHECK(send(&f,"RUN").status==BSR_OK);
    CHECK(fail(&f,BE_UNSUPPORTED,sizeof(f.output))==0); /* No store. */
    CHECK(init(&f)==0);
    CHECK(send(&f,"10 A=-0.5").status==BSR_OK);
    CHECK(send(&f,"RUN").status==BSR_OK);
    {
        size_t j;
        for(j=0u;j<3u;++j){
            BasicVariableKey other=akey((uint8_t)BVT_INTEGER);
            other.name[0]=(uint8_t)('B'+(int)j);
            value.type=(uint8_t)BVT_INTEGER;value.data.integer=1;
            CHECK(bvs_assign(&f.store,&other,&value)==BVS_OK);
        }
        CHECK(fail(&f,BE_STORE_FULL,sizeof(f.output))==0);
    }
    return 0;
}

/* PRINT A formats the actual BVT_REAL store, independently of the
 * last BASIC assignment source. A mismatched hybrid never prints. */
static int stored_value_separation(void) {
    static const uint8_t values[3][5] = {
        {0u,0u,0u,0u,0x80u},
        {0u,0u,0u,0x20u,0x81u},
        {0u,0u,0u,0x80u,0x80u}
    };
    static const char *const output[3] = {" 0.5 \n", " 1.25 \n", "-0.5 \n"};
    F f;BasicVariableKey key=akey((uint8_t)BVT_REAL);
    BasicVariableValue v={0};size_t i;
    for(i=0u;i<3u;++i) {
        CHECK(init(&f)==0);
        CHECK(send(&f,"10 PRINT A").status==BSR_OK);
        CHECK(send(&f,"RUN").status==BSR_OK);
        v.type=(uint8_t)BVT_REAL;
        memcpy(v.data.real5,values[i],5u);
        CHECK(bvs_assign(&f.store,&key,&v)==BVS_OK);
        if (i==2u) CHECK(fail(&f,BE_NO_SPACE,5u)==0);
        CHECK(step(&f,sizeof(f.output)).status==BSR_OK);
        CHECK(f.written==strlen(output[i]));
        CHECK(memcmp(f.output,output[i],f.written)==0);
    }
    /* All three values are recognized solely by comparing the real store. */
    CHECK(init(&f)==0);
    CHECK(send(&f,"10 PRINT A").status==BSR_OK);
    CHECK(send(&f,"RUN").status==BSR_OK);
    v.type=(uint8_t)BVT_REAL;
    memcpy(v.data.real5,values[2],5u);
    v.data.real5[4]=0x81u; /* hybrid negative/sign/exponent */
    CHECK(bvs_assign(&f.store,&key,&v)==BVS_OK);
    CHECK(fail(&f,BE_UNSUPPORTED,sizeof(f.output))==0);
    return 0;
}
static int nmin(void) {
    F f;BasicVariableValue value;BasicVariableKey key=akey((uint8_t)BVT_INTEGER);
    CHECK(init(&f)==0);
    CHECK(send(&f,"10 A%=-32768").status==BSR_OK);
    CHECK(send(&f,"20 PRINT A%").status==BSR_OK);
    CHECK(send(&f,"30 END").status==BSR_OK);
    CHECK(send(&f,"RUN").status==BSR_OK);
    CHECK(step(&f,sizeof(f.output)).status==BSR_OK && f.written==0u);
    CHECK(bvs_get(&f.store,&key,&value)==BVS_OK);
    CHECK(value.type==(uint8_t)BVT_INTEGER && value.data.integer==INT16_MIN);
    CHECK(step(&f,sizeof(f.output)).status==BSR_OK);
    CHECK(f.written==8u && memcmp(f.output,"-32768 \n",8u)==0);
    CHECK(step(&f,sizeof(f.output)).status==BSR_OK);
    CHECK(step(&f,sizeof(f.output)).status==BSR_END);
    return 0;
}
int main(int argc,char **argv) {
    F f;CHECK(argc==3);
    CHECK(init(&f)==0 && populate(&f)==0);
    CHECK(oracle(&f,argv[1])==0);
    CHECK(argc==3);
    CHECK(sealed_store_windows(argv[2])==0);
    CHECK(list_roundtrip(&f)==0);
    CHECK(run(&f)==0);
    CHECK(source_negative()==0);
    CHECK(submit_negative()==0);
    /* Restore the native three-line witness after NEW before rechecking
     * the untouched CPC original ahead of the mutation campaign. */
    CHECK(populate(&f)==0);
    CHECK(oracle(&f,argv[1])==0);
    CHECK(mutated_records()==0);
    CHECK(print_negative()==0);
    CHECK(stored_value_separation()==0);
    CHECK(nmin()==0);
    puts("J1.16-D-B HOST_VERIFIED signed-store + sealed read-only CPC, run, atomic negatives, NMIN PASS");
    return 0;
}
