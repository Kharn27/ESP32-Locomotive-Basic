/* J1.16-E-B: exact CPC scalar witnesses, not a REAL5 converter. */
#include "basic_session_runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x); return 1; } } while (0)
typedef struct {
    const char *name, *source, *printed;
    const uint8_t *l10, *stored;
    size_t l10_size, printed_size;
} Witness;
static const uint8_t zero_l10[]={0x0b,0,0x0a,0,0x0d,0,0,0xc1,0xef,0x0e,0};
static const uint8_t one_l10[]={0x0b,0,0x0a,0,0x0d,0,0,0xc1,0xef,0x0f,0};
static const uint8_t neg_l10[]={0x0c,0,0x0a,0,0x0d,0,0,0xc1,0xef,0xf5,0x0f,0};
static const uint8_t half_l10[]={0x10,0,0x0a,0,0x0d,0,0,0xc1,0xef,0x1f,0,0,0,0,0x80,0};
static const uint8_t quarter_l10[]={0x10,0,0x0a,0,0x0d,0,0,0xc1,0xef,0x1f,0,0,0,0x20,0x81,0};
static const uint8_t neg_half_l10[]={0x11,0,0x0a,0,0x0d,0,0,0xc1,0xef,0xf5,0x1f,0,0,0,0,0x80,0};
static const uint8_t zero_bits[]={0,0,0,0,0};
static const uint8_t one_bits[]={0,0,0,0,0x81};
static const uint8_t neg_bits[]={0,0,0,0x80,0x81};
static const uint8_t half_bits[]={0,0,0,0,0x80};
static const uint8_t quarter_bits[]={0,0,0,0x20,0x81};
static const uint8_t neg_half_bits[]={0,0,0,0x80,0x80};
static const Witness cases[]={
    {"R_ZERO","A=0"," 0 \n",zero_l10,zero_bits,sizeof(zero_l10),4u},
    {"R_ONE","A=1"," 1 \n",one_l10,one_bits,sizeof(one_l10),4u},
    {"R_NEG_ONE","A=-1","-1 \n",neg_l10,neg_bits,sizeof(neg_l10),4u},
    {"R_HALF","A=0.5"," 0.5 \n",half_l10,half_bits,sizeof(half_l10),6u},
    {"R_QUARTER","A=1.25"," 1.25 \n",quarter_l10,quarter_bits,sizeof(quarter_l10),7u},
    {"R_NEG_HALF","A=-0.5","-0.5 \n",neg_half_l10,neg_half_bits,sizeof(neg_half_l10),6u}
};
static const uint8_t l20[]={0x0b,0,0x14,0,0xbf,0x20,0x0d,0,0,0xc1,0};
static const uint8_t l30[]={0x06,0,0x1e,0,0x98,0};
static const uint8_t instrumented[]={0x0e,0,0x1e,0,0xbf,0x20,0x23,0x16,0x2c,0x0d,0,0,0xc1,0};
typedef struct {
    BasicProgram program, replay_program;
    BasicSessionRuntime runtime;
    BasicVariableStore store;
    BasicVariableEntry entries[3];
    uint8_t storage[512], replay[512], temp[256], output[256];
    size_t written;
} F;
static int setup(F *f) {
    memset(f,0xa5,sizeof(*f));
    CHECK(bp_init(&f->program,f->storage,sizeof(f->storage))==BP_OK);
    CHECK(bvs_init(&f->store,f->entries,3u)==BVS_OK);
    CHECK(bsr_init_with_store(&f->runtime,&f->program,&f->store).status==BSR_OK);
    return 0;
}
static BSRResult submit(F *f, const char *line) {
    return bsr_submit(&f->runtime,(const uint8_t *)line,strlen(line),
                      f->temp,sizeof(f->temp),f->output,sizeof(f->output),&f->written);
}
static BasicVariableKey scalar_key(void) {
    BasicVariableKey k;
    memset(&k,0,sizeof(k));
    k.type=(uint8_t)BVT_REAL;k.name_length=1u;k.name[0]='A';
    return k;
}
static int read_file(const char *path, uint8_t *dst, size_t cap, size_t *n) {
    FILE *fp=fopen(path,"rb");
    CHECK(fp!=NULL);
    *n=fread(dst,1u,cap,fp);
    CHECK(!ferror(fp) && fclose(fp)==0);
    return 0;
}
static int record_match(const uint8_t *buf,size_t n,const Witness *w) {
    return n>=w->l10_size+sizeof(l20)+sizeof(instrumented)+8u &&
        memcmp(buf,w->l10,w->l10_size)==0 &&
        memcmp(buf+w->l10_size,l20,sizeof(l20))==0 &&
        memcmp(buf+w->l10_size+sizeof(l20),instrumented,sizeof(instrumented))==0;
}
static int archive(const char *dir,const Witness *w) {
    static const char *const sessions[]={"original","repeat"};
    size_t j;
    for(j=0;j<2u;++j) {
        char path[512];uint8_t buf[512],bad[512];size_t n;
        CHECK(snprintf(path,sizeof(path),"%s/%s/%s/program.bin",dir,sessions[j],w->name)>0);
        CHECK(read_file(path,buf,sizeof(buf),&n)==0);
        CHECK(record_match(buf,n,w));
        CHECK(buf[n-2u]==0 && buf[n-1u]==0);
        CHECK(buf[w->l10_size+sizeof(l20)+sizeof(instrumented)+2u]==40u);
        memcpy(bad,buf,n);
        bad[7]^=0x01u;
        CHECK(!record_match(bad,n,w)); /* deliberate one-byte falsification */
        CHECK(snprintf(path,sizeof(path),"%s/%s/%s/run/printer.dat",dir,sessions[j],w->name)>0);
        CHECK(read_file(path,buf,sizeof(buf),&n)==0);
        CHECK(n>=w->printed_size+1u);
        CHECK(memcmp(buf,w->printed,w->printed_size-1u)==0);
        CHECK(buf[w->printed_size-1u]=='\r' && buf[w->printed_size]=='\n');
    }
    return 0;
}
static int windows(const char *dir,const Witness *w) {
    static const char *const sessions[]={"original","repeat"};
    size_t j;
    for(j=0;j<2u;++j) {
        char path[512];uint8_t data[16],expected[9]={0,0,0xc1,0x04,0,0,0,0,0};
        size_t n;
        memcpy(expected+4u,w->stored,5u);
        CHECK(snprintf(path,sizeof(path),"%s/%s/%s/window.bin",dir,sessions[j],w->name)>0);
        CHECK(read_file(path,data,sizeof(data),&n)==0);
        CHECK(n==sizeof(expected) && memcmp(data,expected,sizeof(expected))==0);
        expected[8]^=0x01u;
        CHECK(memcmp(data,expected,sizeof(expected))!=0);
    }
    return 0;
}
static int native_case(const Witness *w) {
    F f;char line[64],listed[128];size_t i,listed_length,pos;
    BasicVariableKey key=scalar_key();
    CHECK(setup(&f)==0);
    CHECK(submit(&f,"NEW").status==BSR_OK);
    CHECK(snprintf(line,sizeof(line),"10 %s",w->source)>0);
    CHECK(submit(&f,line).status==BSR_OK);
    CHECK(submit(&f,"20 PRINT A").status==BSR_OK);
    CHECK(submit(&f,"30 END").status==BSR_OK);
    CHECK(f.program.size==w->l10_size+sizeof(l20)+sizeof(l30)+2u);
    CHECK(memcmp(f.storage,w->l10,w->l10_size)==0);
    CHECK(memcmp(f.storage+w->l10_size,l20,sizeof(l20))==0);
    CHECK(memcmp(f.storage+w->l10_size+sizeof(l20),l30,sizeof(l30))==0);
    CHECK(f.storage[f.program.size-2u]==0 && f.storage[f.program.size-1u]==0);
    CHECK(submit(&f,"LIST").status==BSR_OK);
    CHECK(snprintf(listed,sizeof(listed),"10 %s\n20 PRINT A\n30 END\n",w->source)>0);
    listed_length=strlen(listed);
    CHECK(f.written==listed_length && memcmp(f.output,listed,listed_length)==0);
    CHECK(bp_init(&f.replay_program,f.replay,sizeof(f.replay))==BP_OK);
    pos=0u;
    while(pos<listed_length) {
        size_t end=pos,used=313u;uint8_t sink[128];
        while(end<listed_length && listed[end]!='\n')++end;
        CHECK(end<listed_length && end>pos);
        CHECK(bs_process_line(&f.replay_program,(const uint8_t *)listed+pos,end-pos,
              f.temp,sizeof(f.temp),sink,sizeof(sink),&used).status==BS_OK);
        pos=end+1u;
    }
    CHECK(f.replay_program.size==f.program.size);
    CHECK(memcmp(f.replay,f.storage,f.program.size)==0);
    for(i=0;i<2u;++i) {
        BSRResult result;BasicVariableValue value;uint8_t saved[sizeof(f.storage)];
        CHECK(submit(&f,"RUN").status==BSR_OK && f.store.count==0u);
        memcpy(saved,f.storage,sizeof(saved));
        f.written=777u;result=bsr_step(&f.runtime,f.output,sizeof(f.output),&f.written);
        CHECK(result.status==BSR_OK && f.written==0u && f.store.count==1u);
        CHECK(bvs_get(&f.store,&key,&value)==BVS_OK);
        CHECK(value.type==(uint8_t)BVT_REAL);
        CHECK(memcmp(value.data.real5,w->stored,5u)==0);
        memset(f.output,0x77,sizeof(f.output));
        f.written=777u;result=bsr_step(&f.runtime,f.output,sizeof(f.output),&f.written);
        CHECK(result.status==BSR_OK && f.written==w->printed_size);
        CHECK(memcmp(f.output,w->printed,w->printed_size)==0 && f.output[w->printed_size]==0x77);
        f.written=313u;result=bsr_step(&f.runtime,f.output,sizeof(f.output),&f.written);
        CHECK(result.status==BSR_OK && f.written==0u);
        f.written=313u;result=bsr_step(&f.runtime,f.output,sizeof(f.output),&f.written);
        CHECK(result.status==BSR_END && result.executor_status==BE_END);
        CHECK(f.written==313u && f.runtime.state==BSR_IDLE);
        CHECK(memcmp(f.storage,saved,sizeof(saved))==0);
    }
    CHECK(submit(&f,"NEW").status==BSR_OK && f.store.count==0u);
    CHECK(submit(&f,"LIST").status==BSR_OK && f.written==0u);
    printf("%s MATCH_EXACT_RECORD_10_20 MATCH_PRESENTATION_CRLF_TO_LF STORE_5_BYTES RUN_TWICE_NEW\n",w->name);
    return 0;
}
static int negatives(void) {
    static const char *const bad[]={"A=0.1","A=1.0","A=-1.0","A=1.250","A=-0.50",
        "A=0X","A=-1X","A= 0","A =1","LET A=-1","a=-1",
        "PRINT  A","PRINT A ","A=-1:PRINT A","A=0:END"};
    size_t i;F f;
    CHECK(setup(&f)==0);
    CHECK(submit(&f,"10 A=0").status==BSR_OK);
    for(i=0;i<sizeof(bad)/sizeof(bad[0]);++i) {
        uint8_t dst[64],before[64],program[sizeof(f.storage)],out[sizeof(f.output)];
        BasicSessionRuntime runtime=f.runtime;BasicVariableStore store=f.store;
        BasicVariableEntry entries[3];size_t written=818u;
        memset(dst,0x5a,sizeof(dst));memcpy(before,dst,sizeof(dst));
        CHECK(bt_tokenize((const uint8_t *)bad[i],strlen(bad[i]),
              dst,sizeof(dst),&written)!=BT_OK);
        CHECK(written==818u && memcmp(dst,before,sizeof(dst))==0);
        memcpy(program,f.storage,sizeof(program));
        memcpy(out,f.output,sizeof(out));memcpy(entries,f.entries,sizeof(entries));
        f.written=919u;
        CHECK(submit(&f,bad[i]).status==BSR_SESSION_ERROR);
        CHECK(f.written==919u && memcmp(f.storage,program,sizeof(program))==0);
        CHECK(memcmp(f.output,out,sizeof(out))==0);
        CHECK(memcmp(&f.runtime,&runtime,sizeof(runtime))==0);
        CHECK(memcmp(&f.store,&store,sizeof(store))==0);
        CHECK(memcmp(f.entries,entries,sizeof(entries))==0);
    }
    return 0;
}
static int mutated(const Witness *w) {
    size_t i,n=w->l10_size-5u;
    for(i=0;i<n+1u;++i) {
        F f;uint8_t body[20],saved[sizeof(f.storage)],out[sizeof(f.output)];
        BasicVariableStore store;BasicVariableEntry entries[3];
        BasicExecutor executor;BSRResult r;size_t len=n;
        CHECK(setup(&f)==0);
        memcpy(body,w->l10+4u,n);
        if(i<n)body[i]=0xffu; else --len; /* invalid prefix/cache/op/literal/truncated */
        CHECK(bp_put(&f.program,10u,body,len)==BP_OK);
        CHECK(submit(&f,"RUN").status==BSR_OK);
        store=f.store;executor=f.runtime.executor;
        memcpy(entries,f.entries,sizeof(entries));
        memcpy(saved,f.storage,sizeof(saved));
        memset(f.output,0x77,sizeof(f.output));memcpy(out,f.output,sizeof(out));
        f.written=515u;
        r=bsr_step(&f.runtime,f.output,sizeof(f.output),&f.written);
        CHECK(r.status==BSR_EXECUTOR_ERROR);
        CHECK(f.written==515u && memcmp(f.output,out,sizeof(out))==0);
        CHECK(memcmp(f.storage,saved,sizeof(saved))==0);
        CHECK(memcmp(f.entries,entries,sizeof(entries))==0);
        CHECK(memcmp(&f.store,&store,sizeof(store))==0);
        CHECK(memcmp(&f.runtime.executor,&executor,sizeof(executor))==0);
    }
    return 0;
}
int main(int argc,char **argv) {
    size_t i;
    CHECK(argc==3);
    for(i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
        CHECK(archive(argv[1],&cases[i])==0);
        if(i<3u) CHECK(windows(argv[2],&cases[i])==0);
        CHECK(native_case(&cases[i])==0);
        if(i<3u) CHECK(mutated(&cases[i])==0);
    }
    CHECK(negatives()==0);
    puts("J1.16-E-B SIX_WITNESSES 3_NEW 3_HISTORIC FALSIFICATION_ATOMIC PASS");
    return 0;
}
