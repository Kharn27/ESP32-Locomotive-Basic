/* J1.21-B1: CLS 8A is lexical only. J1.21-A CPC originals/repeats READ ONLY. */
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_program.h"
#include "basic_session.h"
#include "basic_executor.h"
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr,"CLS-B1 %s:%d: %s\n",__FILE__,__LINE__,#x); \
    return 1; } } while (0)

static int load(const char *path,uint8_t *data,size_t capacity,size_t *count)
{
    FILE *f=fopen(path,"rb");
    int extra;
    if(!f) { fprintf(stderr,"CLS-B1 missing oracle %s\n",path); return 1; }
    *count=fread(data,1u,capacity,f);
    extra=fgetc(f);
    if(ferror(f) || extra!=EOF || *count==0u) { fclose(f); return 1; }
    return fclose(f)!=0;
}
static int path_for(char *out,size_t cap,const char *root,
                    const char *session,const char *name,const char *suffix)
{
    int n=snprintf(out,cap,"%s/tests/fixtures/cpc6128/j1_21_a_cls/%s/%s/%s",
                   root,session,name,suffix);
    return n<0 || (size_t)n>=cap;
}
static int submit(BasicProgram *p,const char *line,
                  uint8_t *temporary,uint8_t *output)
{
    size_t written=57u;
    BSResult r=bs_process_line(p,(const uint8_t *)line,strlen(line),
                temporary,256u,output,512u,&written);
    if(r.status!=BS_OK) {
        fprintf(stderr,"CLS-B1 submit '%s': BS=%d BT=%d BP=%d\n",
                line,(int)r.status,(int)r.tokenizer_status,
                (int)r.program_status);
        return 1;
    }
    return 0;
}
static int build_source(BasicProgram *p,const uint8_t *source,size_t n,
                        uint8_t *tmp,uint8_t *out)
{
    size_t at=0u;
    while(at<n) {
        const uint8_t *end=memchr(source+at,'\n',n-at);
        char line[256];
        size_t len;
        CHECK(end!=NULL);
        len=(size_t)(end-(source+at));
        CHECK(len>0u && len<sizeof(line));
        memcpy(line,source+at,len);
        line[len]='\0';
        CHECK(submit(p,line,tmp,out)==0);
        at+=(len+1u);
    }
    return 0;
}
/* CPC LIST #8 produces CRLF. Native LIST uses LF; compare actual bytes
 * rather than silently accepting semantic/spelling differences. */
static int same_printer(const uint8_t *listed,size_t n,
                        const uint8_t *printer,size_t pn)
{
    size_t i,j=0u;
    for(i=0u;i<n;i++) {
        if(listed[i]=='\n') {
            if(j+2u>pn || printer[j++]!='\r' || printer[j++]!='\n')
                return 0;
        } else if(j>=pn || printer[j++]!=listed[i]) return 0;
    }
    return j==pn;
}
static int oracle_case(const char *root,const char *name,int paper)
{
    uint8_t source[512],original[512],repeat[512],printer[512];
    uint8_t storage[1024],import_storage[1024],reentry_storage[1024];
    uint8_t temporary[256],out[512],exported[512],listed[512],roundtrip[512];
    size_t ns,no,nr,np,native_length,list_length,reentry_length;
    BasicProgram p,imported,reentry;
    char path[512],lower[32];
    size_t letter, name_length=strlen(name);
    CHECK(name_length<sizeof(lower));
    for(letter=0u;letter<name_length;++letter)
        lower[letter]=(char)(name[letter]>='A' && name[letter]<='Z' ?
                    name[letter]-'A'+'a' : name[letter]);
    lower[name_length]='\0';
    CHECK(snprintf(path,sizeof(path),"%s/tests/oracles/inputs/j1_21_a/%s.bas",
                   root,lower)>0);
    CHECK(load(path,source,sizeof(source),&ns)==0);
    CHECK(path_for(path,sizeof(path),root,"original",name,"program.bin")==0);
    CHECK(load(path,original,sizeof(original),&no)==0);
    CHECK(path_for(path,sizeof(path),root,"repeat",name,"program.bin")==0);
    CHECK(load(path,repeat,sizeof(repeat),&nr)==0);
    CHECK(no==nr && memcmp(original,repeat,no)==0);
    CHECK(path_for(path,sizeof(path),root,"original",name,"list/printer.dat")==0);
    CHECK(load(path,printer,sizeof(printer),&np)==0);

    CHECK(bp_init(&p,storage,sizeof(storage))==BP_OK);
    CHECK(bp_init(&imported,import_storage,sizeof(import_storage))==BP_OK);
    CHECK(bp_import(&imported,original,no)==BP_OK);
    if(!paper) {
        CHECK(build_source(&p,source,ns,temporary,out)==0);
        CHECK(bp_export(&p,exported,sizeof(exported),&native_length)==BP_OK);
        CHECK(native_length==no && memcmp(exported,original,no)==0);
        CHECK(bl_list_program(&p,listed,sizeof(listed),&list_length)==BL_OK);
        CHECK(list_length==ns && memcmp(listed,source,ns)==0);
        CHECK(same_printer(listed,list_length,printer,np));
        CHECK(bl_list_program(&imported,listed,sizeof(listed),&list_length)==BL_OK);
        CHECK(list_length==ns && memcmp(listed,source,ns)==0);
        CHECK(bp_init(&reentry,reentry_storage,sizeof(reentry_storage))==BP_OK);
        CHECK(build_source(&reentry,listed,list_length,temporary,out)==0);
        CHECK(bp_export(&reentry,roundtrip,sizeof(roundtrip),&reentry_length)==BP_OK);
        CHECK(reentry_length==no && memcmp(roundtrip,original,no)==0);
    } else {
        /* N_PAPER: PAPER 2 is outside B1. Validate only its independent
         * 20 CLS record; do NOT claim full native PAPER RAM/LIST support. */
        BasicProgramLine record;
        static const uint8_t cls[]={0x8au};
        uint8_t word[16];
        size_t size=0u;
        CHECK(bp_find(&imported,20u,&record)==BP_OK);
        CHECK(record.body_length==sizeof(cls));
        CHECK(memcmp(imported.data+record.body_offset,cls,sizeof(cls))==0);
        CHECK(bl_detokenize(cls,sizeof(cls),word,sizeof(word),&size)==BL_OK);
        CHECK(size==3u && memcmp(word,"CLS",size)==0);
        CHECK(submit(&p,"20 CLS",temporary,out)==0);
        CHECK(bp_find(&p,20u,&record)==BP_OK);
        CHECK(record.body_length==sizeof(cls) &&
              p.data[record.body_offset]==0x8au);
        /* Independently acquired printer still matches immutable source. */
        CHECK(same_printer(source,ns,printer,np));
    }
    printf("CLS-B1 %s original+repeat CPC RAM exact%s; LIST #8 bytes PASS\n",
           name,paper?" (CLS record only)":"");
    return 0;
}
static int lexical_cases(void)
{
    const struct {
        const char *input;
        const uint8_t *expected;
        size_t count;
    } valid[]={
        {"CLS",(const uint8_t[]){0x8au},1u},
        {"cls:CLS",(const uint8_t[]){0x8au,0x01u,0x8au},3u},
        {"CLS:CLS",(const uint8_t[]){0x8au,0x01u,0x8au},3u},
        {" CLS ",(const uint8_t[]){' ',0x8au,' '},3u},
        {"PRINT \"CLS\"",(const uint8_t[]){0xbfu,' ','\"','C','L','S','\"'},7u},
        {"REM CLS:CLS",(const uint8_t[]){0xc5u,' ','C','L','S',':','C','L','S'},9u},
        {"CLS:REM CLS",(const uint8_t[]){0x8au,0x01u,0xc5u,' ','C','L','S'},7u},
        {"CLS%=1",(const uint8_t[]){0x02u,0u,0u,'C','L',0xd3u,0xefu,0x0fu},8u}
    };
    static const char *const rejected[]={
        "CLSX","CLS1","CLS_","CLS#0","CLS#7","CLS#8",
        "CLS::CLS","CLS:","CLS PRINT \"X\"","CLS:CLSX"
    };
    size_t i;
    for(i=0u;i<sizeof(valid)/sizeof(valid[0]);++i) {
        uint8_t tokens[128],listed[128],again[128];
        size_t n=19u,decoded=23u,n2=7u;
        CHECK(bt_tokenize((const uint8_t *)valid[i].input,
            strlen(valid[i].input),tokens,sizeof(tokens),&n)==BT_OK);
        CHECK(n==valid[i].count &&
              memcmp(tokens,valid[i].expected,n)==0);
        CHECK(bl_detokenize(tokens,n,listed,sizeof(listed),&decoded)==BL_OK);
        CHECK(bt_tokenize(listed,decoded,again,sizeof(again),&n2)==BT_OK);
        CHECK(n2==n && memcmp(again,tokens,n)==0);
    }
    for(i=0u;i<sizeof(rejected)/sizeof(rejected[0]);++i) {
        uint8_t dest[128],saved[128];
        size_t written=71u;
        memset(dest,0xa5,sizeof(dest));
        memcpy(saved,dest,sizeof(dest));
        CHECK(bt_tokenize((const uint8_t *)rejected[i],strlen(rejected[i]),
                          dest,sizeof(dest),&written)!=BT_OK);
        CHECK(written==71u && memcmp(dest,saved,sizeof(dest))==0);
    }
    return 0;
}
static int rollback_and_run(void)
{
    static const uint8_t cls2[]={0x8au,0x01u,0x8au};
    static const uint8_t bad[]={0x8au,0x01u};
    uint8_t bytes[256],saved[256],out[512],out_saved[512],temporary[256];
    uint8_t storage[128],stored[128],tiny_storage[8];
    BasicProgram p,tiny;
    BasicExecutor executor,before;
    size_t count=67u;
    BSResult result;
    memset(bytes,0x6b,sizeof(bytes));
    memcpy(saved,bytes,sizeof(saved));
    CHECK(bt_tokenize((const uint8_t *)"CLS:CLS",7u,bytes,2u,&count)==BT_NO_SPACE);
    CHECK(count==67u && memcmp(bytes,saved,sizeof(bytes))==0);
    CHECK(bt_tokenize(bytes,3u,bytes,sizeof(bytes),&count)==BT_INVALID_ARGUMENT);
    CHECK(count==67u && memcmp(bytes,saved,sizeof(bytes))==0);
    CHECK(bt_tokenize((const uint8_t *)"CLS",3u,bytes,sizeof(bytes),
                      (size_t *)(void *)bytes)==BT_INVALID_ARGUMENT);
    CHECK(memcmp(bytes,saved,sizeof(bytes))==0);
    CHECK(bl_detokenize(cls2,sizeof(cls2),bytes,6u,&count)==BL_NO_SPACE);
    CHECK(count==67u && memcmp(bytes,saved,sizeof(bytes))==0);
    CHECK(bl_detokenize(bad,sizeof(bad),bytes,sizeof(bytes),&count)!=BL_OK);
    CHECK(count==67u && memcmp(bytes,saved,sizeof(bytes))==0);
    CHECK(bl_detokenize(cls2,sizeof(cls2),bytes,sizeof(bytes),
                        (size_t *)(void *)bytes)==BL_OVERLAP);
    CHECK(memcmp(bytes,saved,sizeof(bytes))==0);

    CHECK(bp_init(&p,storage,sizeof(storage))==BP_OK);
    memset(out,0x49,sizeof(out));
    CHECK(submit(&p,"10 CLS",temporary,out)==0);
    memcpy(stored,storage,sizeof(stored));
    memcpy(out_saved,out,sizeof(out_saved));
    result=bs_process_line(&p,(const uint8_t *)"20 CLS::CLS",11u,
                           temporary,sizeof(temporary),out,sizeof(out),&count);
    CHECK(result.status==BS_TOKENIZER_ERROR);
    CHECK(count==67u && memcmp(stored,storage,sizeof(stored))==0 &&
          memcmp(out,out_saved,sizeof(out))==0);
    CHECK(bp_init(&tiny,tiny_storage,sizeof(tiny_storage))==BP_OK);
    result=bs_process_line(&tiny,(const uint8_t *)"10 CLS:CLS",10u,
                           temporary,sizeof(temporary),out,sizeof(out),&count);
    CHECK(result.status==BS_PROGRAM_ERROR && result.program_status==BP_NO_SPACE);
    CHECK(count==67u && memcmp(out,out_saved,sizeof(out))==0);
    memset(bytes,0x6b,sizeof(bytes));
    memcpy(saved,bytes,sizeof(saved));
    CHECK(bl_list_program(&p,bytes,1u,&count)==BL_NO_SPACE);
    CHECK(count==67u && memcmp(bytes,saved,sizeof(bytes))==0);
    CHECK(bl_list_program(&p,storage,sizeof(storage),&count)==BL_OVERLAP);
    CHECK(count==67u && memcmp(stored,storage,sizeof(stored))==0);

    CHECK(be_init(&executor,&p)==BE_OK);
    before=executor;
    memset(out,0x41,sizeof(out));
    memcpy(out_saved,out,sizeof(out_saved));
    CHECK(be_step(&executor,out,sizeof(out),&count)==BE_UNKNOWN_TOKEN);
    /* BE_UNKNOWN_TOKEN is the existing host-only unsupported path for 8A;
     * no executor CLS dispatch, output, counter, program or video events. */
    CHECK(count==67u && memcmp(&executor,&before,sizeof(before))==0);
    CHECK(memcmp(out,out_saved,sizeof(out))==0);
    CHECK(memcmp(storage,stored,sizeof(stored))==0);
    return 0;
}
int main(int argc,char **argv)
{
    static const char *const cases[]={
        "N_FULL","N_DOUBLE","N_WINDOW","N_MODE0",
        "N_MODE2","N_CURSOR","N_PAPER"
    };
    size_t i;
    CHECK(argc==2);
    CHECK(lexical_cases()==0);
    CHECK(rollback_and_run()==0);
    for(i=0u;i<sizeof(cases)/sizeof(cases[0]);++i)
        CHECK(oracle_case(argv[1],cases[i],i==6u)==0);
    puts("CLS-B1 token 8A / CPC RAM original+repeat / LIST / rollback / RUN unsupported PASS");
    return 0;
}
