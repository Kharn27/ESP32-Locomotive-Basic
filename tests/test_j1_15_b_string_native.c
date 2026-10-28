/* J1.15-B: independent CPC partial-record comparison + bounded native STRING. */
#include "basic_session_runtime.h"
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"%s:%d %s\n",__FILE__,__LINE__,#x); return 1; } } while (0)

typedef struct {
    BasicProgram program, again;
    BasicSessionRuntime rt;
    BasicVariableEntry entries[3];
    BasicVariableStore vars;
    uint8_t data[2048], retokenized[2048], arena[384], temp[512], output[2048];
    size_t written;
} Fixture;

static int setup(Fixture *f, size_t slot) {
    memset(f,0xa5,sizeof(*f));
    CHECK(bp_init(&f->program,f->data,sizeof(f->data))==BP_OK);
    CHECK(bvs_init_with_arena(&f->vars,f->entries,3u,f->arena,slot*3u)==BVS_OK);
    CHECK(bsr_init_with_store(&f->rt,&f->program,&f->vars).status==BSR_OK);
    return 0;
}
static BSRResult submit(Fixture *f,const char *s) {
    return bsr_submit(&f->rt,(const uint8_t *)s,strlen(s),f->temp,sizeof(f->temp),
                      f->output,sizeof(f->output),&f->written);
}
static BSRResult step(Fixture *f,size_t capacity) {
    return bsr_step(&f->rt,f->output,capacity,&f->written);
}
static size_t u16(const uint8_t *p) {return (size_t)p[0] + ((size_t)p[1]<<8);}
static int partial_records(const BasicProgram *program,const char *source) {
    FILE *fp=fopen(source,"rb");
    uint8_t reference[2048];
    size_t n, cursor=0u, count=0u;
    BasicProgramLine line;
    CHECK(fp!=NULL);
    n=fread(reference,1u,sizeof(reference),fp);
    CHECK(ferror(fp)==0);
    CHECK(fclose(fp)==0);
    CHECK(n>=2u && reference[n-1u]==0u && reference[n-2u]==0u);
    while (bp_next(program,&cursor,&line)==BP_OK) {
        size_t p=0u;int found=0;
        while (p+4u<n && u16(reference+p)!=0u) {
            size_t len=u16(reference+p);
            CHECK(len>=5u && len<=n-p);
            if (u16(reference+p+2u)==line.number) {
                CHECK(line.next_offset-line.offset==len);
                CHECK(memcmp(program->data+line.offset,reference+p,len)==0);
                found=1;break;
            }
            p+=len;
        }
        CHECK(found);
        ++count;
    }
    CHECK(count>=3u);
    return 0;
}
static int roundtrip(Fixture *f) {
    size_t n=f->written,start=0u,write=0u;
    uint8_t sink[512];
    CHECK(bp_init(&f->again,f->retokenized,sizeof(f->retokenized))==BP_OK);
    while (start<n) {
        size_t end=start;
        BSResult res;
        while (end<n && f->output[end]!=(uint8_t)'\n') ++end;
        CHECK(end<n && end>start);
        res=bs_process_line(&f->again,f->output+start,end-start,
                            f->temp,sizeof(f->temp),
                            sink,sizeof(sink),&write);
        CHECK(res.status==BS_OK);
        start=end+1u;
    }
    CHECK(f->again.size==f->program.size);
    CHECK(memcmp(f->again.data,f->program.data,f->program.size)==0);
    return 0;
}
static int corpus(const char *sources,const char *archives) {
    struct {const char *id;const char *expect;} cases[]={
        {"s_empty",""}, {"s_one","X"},{"s_hello","BONJOUR"},
        {"s_digits","12345"},{"s_leading","  DEBUT"},{"s_trailing","FIN  "},
        {"s_colon","A:B:C"},{"s_reassign","APRES"},{"s_lowercase","minuscules"},
        {"s_let_spaces","ESPACES"},{"s_long_name","NOM LONG"},
        {"s_inner_space","UN DEUX TROIS"}
    };
    size_t i;
    for (i=0u;i<sizeof(cases)/sizeof(cases[0]);++i) {
        Fixture f;
        char path[512],line[512];
        FILE *fp;
        size_t expected_len=strlen(cases[i].expect);
        int prints=0,ends=0;
        CHECK(setup(&f,128u)==0);
        CHECK(snprintf(path,sizeof(path),"%s/%s.bas",sources,cases[i].id)>0);
        fp=fopen(path,"rb");
        CHECK(fp!=NULL);
        while (fgets(line,sizeof(line),fp)!=NULL) {
            size_t len=strlen(line);
            CHECK(len>0u && line[len-1u]=='\n');
            line[len-1u]='\0';
            if (strstr(line,"#8")!=NULL) continue; /* Source instrumentation is NOT native. */
            if (strstr(line,"END")!=NULL || strstr(line,"end")!=NULL) ++ends;
            if (strstr(line,"PRINT ")!=NULL || strstr(line,"print ")!=NULL) ++prints;
            CHECK(submit(&f,line).status==BSR_OK);
        }
        CHECK(fclose(fp)==0 && ends==1 && prints>=1);
        CHECK(snprintf(path,sizeof(path),"%s/original/S_%s/program.bin",archives,"")>0);
        /* Case names in original oracle archives are upper-case. */
        CHECK(snprintf(path,sizeof(path),"%s/original/",archives)>0);
        {
            size_t k=strlen(path),j;
            const char *name=cases[i].id;
            for(j=0u;name[j]&&k+2u<sizeof(path);++j) {
                char ch=name[j];
                path[k++]=(char)(ch>='a'&&ch<='z'?ch-'a'+'A':ch);
            }
            strcpy(path+k,"/program.bin");
        }
        CHECK(partial_records(&f.program,path)==0);
        CHECK(submit(&f,"LIST").status==BSR_OK);
        CHECK(roundtrip(&f)==0);
        CHECK(submit(&f,"RUN").status==BSR_OK);
        while (f.rt.state==BSR_RUNNING) {
            BSRResult r=step(&f,sizeof(f.output));
            CHECK(r.status==BSR_OK || r.status==BSR_END);
            if (r.status==BSR_END) break;
            if (f.written!=0u) {
                CHECK(f.written==expected_len+1u);
                CHECK(memcmp(f.output,cases[i].expect,expected_len)==0);
                CHECK(f.output[expected_len]=='\n');
            }
        }
        printf("J1.15-B %s PARTIAL_CPC_RECORD_MATCH LIST_ROUNDTRIP MATCH_SEMANTIC_VALUE\n",
               cases[i].id);
    }
    return 0;
}
static BasicVariableKey key(const char *name) {
    BasicVariableKey k;size_t i;
    memset(&k,0,sizeof(k));
    k.type=(uint8_t)BVT_STRING;
    k.name_length=(uint8_t)strlen(name);
    for(i=0u;i<k.name_length;++i)k.name[i]=(uint8_t)name[i];
    return k;
}
static int store_boundaries(void) {
    BasicVariableEntry e[2];BasicVariableStore s;
    uint8_t arena[18],copy[18],big[]="1234567890";
    BasicVariableKey a=key("A"),b=key("B");
    BasicVariableValue v;const uint8_t *span=(const uint8_t *)1;
    size_t n=555u,j;BasicVariableStore previous;
    CHECK(bvs_init(&s,e,2u)==BVS_OK);
    CHECK(bvs_can_assign_string(&s,&a,(const uint8_t *)"X",1u)==BVS_NO_STRING_SPACE);
    CHECK(bvs_assign_string(&s,&a,(const uint8_t *)"X",1u)==BVS_NO_STRING_SPACE);
    CHECK(s.count==0u);
    CHECK(bvs_assign_string(&s,&a,NULL,0u)==BVS_OK);
    CHECK(bvs_get(&s,&a,&v)==BVS_OK && v.data.string.length==0u);
    CHECK(bvs_init_with_arena(&s,e,2u,arena,sizeof(arena))==BVS_OK);
    CHECK(s.string_slot_bytes==9u);
    CHECK(bvs_assign_string(&s,&a,(const uint8_t *)"123456789",9u)==BVS_OK);
    CHECK(bvs_get(&s,&a,&v)==BVS_OK);
    CHECK(bvs_string_span(&s,&v.data.string,&span,&n)==BVS_OK);
    CHECK(n==9u && memcmp(span,"123456789",9u)==0);
    memcpy(copy,arena,sizeof(copy));previous=s;
    CHECK(bvs_assign_string(&s,&a,big,10u)==BVS_NO_STRING_SPACE);
    CHECK(memcmp(copy,arena,sizeof(copy))==0 && s.count==previous.count);
    CHECK(bvs_assign_string(&s,&a,arena,1u)==BVS_OVERLAPPING_MEMORY);
    CHECK(memcmp(copy,arena,sizeof(copy))==0);
    CHECK(bvs_assign_string(&s,&a,(const uint8_t *)"BAD\"QUOTE",9u)==BVS_INVALID_STRING);
    CHECK(bvs_assign_string(&s,&a,(const uint8_t *)"A\0B",3u)==BVS_INVALID_STRING);
    for(j=0u;j<100u;++j) {
        const uint8_t *str=j%2u?(const uint8_t *)"LAST":(const uint8_t *)"R";
        CHECK(bvs_assign_string(&s,&a,str,j%2u?4u:1u)==BVS_OK);
        CHECK(s.count==1u);
    }
    CHECK(bvs_assign_string(&s,&b,(const uint8_t *)"B",1u)==BVS_OK);
    CHECK(s.count==2u);
    {BasicVariableKey c=key("C");
     CHECK(bvs_assign_string(&s,&c,(const uint8_t *)"C",1u)==BVS_FULL);}
    CHECK(bvs_reset(&s)==BVS_OK && s.count==0u);
    for(j=0u;j<sizeof(arena);++j)CHECK(arena[j]==0u);
    CHECK(bvs_init_with_arena(&s,e,2u,arena,0u)==BVS_INVALID_ARGUMENT);
    return 0;
}
static int runtime_atomic(void) {
    Fixture f;BasicVariableStore before;BasicSessionRuntime rt;
    BasicVariableEntry entries[3];uint8_t arena[384],program[2048],output[2048];
    size_t saved;
    CHECK(setup(&f,128u)==0);
    CHECK(submit(&f,"10 A$=\"BONJOUR\"").status==BSR_OK);
    CHECK(submit(&f,"20 PRINT A$").status==BSR_OK);
    CHECK(submit(&f,"30 END").status==BSR_OK);
    CHECK(submit(&f,"RUN").status==BSR_OK);
    CHECK(step(&f,sizeof(f.output)).status==BSR_OK && f.vars.count==1u);
    before=f.vars;rt=f.rt;
    memcpy(entries,f.entries,sizeof(entries));memcpy(arena,f.arena,sizeof(arena));
    memcpy(program,f.data,sizeof(program));memcpy(output,f.output,sizeof(output));
    f.written=987u;saved=f.written;
    CHECK(step(&f,3u).status==BSR_EXECUTOR_ERROR);
    CHECK(f.written==saved && memcmp(entries,f.entries,sizeof(entries))==0);
    CHECK(memcmp(arena,f.arena,sizeof(arena))==0);
    CHECK(memcmp(program,f.data,sizeof(program))==0);
    CHECK(memcmp(output,f.output,sizeof(output))==0);
    CHECK(memcmp(&rt,&f.rt,sizeof(rt))==0 && memcmp(&before,&f.vars,sizeof(before))==0);
    CHECK(step(&f,sizeof(f.output)).status==BSR_OK);
    CHECK(f.written==8u && memcmp(f.output,"BONJOUR\n",8u)==0);
    CHECK(submit(&f,"RUN").status==BSR_OK && f.vars.count==0u);
    CHECK(step(&f,sizeof(f.output)).status==BSR_OK && f.vars.count==1u);
    CHECK(submit(&f,"NEW").status==BSR_OK && f.vars.count==0u);
    return 0;
}
static int invalid_grammar(void) {
    const char *bad[]={"A$=\"A\"\"B\"","A$=\"UNFINISHED","A$=\"A\"+\"B\"",
                       "A$=A$","A$=\"A\":PRINT A$","A$=\"A\"XYZ","A$=\"X\"\t"};
    uint8_t dest[80],saved[80];size_t written=88u,i;
    memset(dest,0xa5,sizeof(dest));memcpy(saved,dest,sizeof(dest));
    for(i=0u;i<sizeof(bad)/sizeof(bad[0]);++i) {
        CHECK(bt_tokenize((const uint8_t *)bad[i],strlen(bad[i]),
                          dest,sizeof(dest),&written)!=BT_OK);
        CHECK(written==88u && memcmp(dest,saved,sizeof(dest))==0);
    }
    {const uint8_t badnul[]={'A','$','=','"',0,'"'};
     CHECK(bt_tokenize(badnul,sizeof(badnul),dest,sizeof(dest),&written)!=BT_OK);}
    return 0;
}

static int forged_cache_and_missing_arena(void) {
    Fixture f;
    BasicVariableStore legacy;
    BasicVariableEntry e[1];
    uint8_t tok[128], saved[128], scratch[16];
    size_t n = 0u, listed = 719u;
    BasicExecutor before;
    BasicVariableEntry original;
    BasicProgramLine line;
    CHECK(bt_tokenize((const uint8_t *)"A$=\"X\"",6u,
                      tok,sizeof(tok),&n)==BT_OK);
    CHECK(n==8u && tok[0]==0x03u && tok[1]==0u && tok[2]==0u);
    memcpy(saved,tok,n);
    tok[1]=0x12u; /* Cache byte is opaque in ROM, but newly encoded
                    * standalone assignment must use 00 00. */
    memset(scratch,0xa5,sizeof(scratch));
    CHECK(bl_detokenize(tok,n,scratch,sizeof(scratch),&listed)==BL_BAD_SEQUENCE);
    CHECK(listed==719u && scratch[0]==0xa5u);
    CHECK(setup(&f,128u)==0);
    CHECK(bp_put(&f.program,10u,tok,n)==BP_OK);
    CHECK(bp_put(&f.program,20u,(const uint8_t *)"\x98",1u)==BP_OK);
    CHECK(be_init_with_store(&f.rt.executor,&f.program,&f.vars)==BE_OK);
    f.rt.state=BSR_RUNNING;
    before=f.rt.executor;original=f.entries[0];
    CHECK(step(&f,sizeof(f.output)).executor_status==BE_BAD_SEQUENCE);
    CHECK(memcmp(&f.rt.executor,&before,sizeof(before))==0);
    CHECK(memcmp(&f.entries[0],&original,sizeof(original))==0);
    CHECK(f.vars.count==0u && memcmp(tok,saved,n)!=0);
    /* Legacy store remains valid, but cannot allocate a nonempty value. */
    CHECK(bvs_init(&legacy,e,1u)==BVS_OK);
    CHECK(bp_put(&f.program,10u,saved,n)==BP_OK);
    CHECK(be_init_with_store(&f.rt.executor,&f.program,&legacy)==BE_OK);
    f.rt.executor.cursor=0u;before=f.rt.executor;
    CHECK(be_step(&f.rt.executor,f.output,sizeof(f.output),&f.written)==BE_STORE_FULL);
    CHECK(memcmp(&f.rt.executor,&before,sizeof(before))==0 && legacy.count==0u);
    /* Every input region, not just the live length, must avoid arena alias. */
    CHECK(bsr_init_with_store(&f.rt,&f.program,&f.vars).status==BSR_OK);
    CHECK(submit(&f,"RUN").status==BSR_OK);
    CHECK(bsr_step(&f.rt,f.arena,8u,&f.written).status==BSR_OVERLAP);
    CHECK(f.vars.count==0u);
    CHECK(bp_find(&f.program,10u,&line)==BP_OK);
    return 0;
}

int main(int argc,char **argv) {
    CHECK(argc==3);
    CHECK(store_boundaries()==0);
    CHECK(forged_cache_and_missing_arena()==0);
    CHECK(invalid_grammar()==0);
    CHECK(runtime_atomic()==0);
    CHECK(corpus(argv[1],argv[2])==0);
    puts("PASS J1.15-B bounded scalar STRING");
    return 0;
}
