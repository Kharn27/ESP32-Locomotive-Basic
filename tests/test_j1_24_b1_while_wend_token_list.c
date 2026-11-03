/* J1.24-B1: native WHILE=D6 / WEND=D5, strictly lexical only.
 * Immutable CPC J1.24-A original/repeat RAM + PRE-RUN printer LIST. */
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_program.h"
#include "basic_session.h"
#include "basic_executor.h"
#include "basic_variable_store.h"
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if(!(x)) { \
    fprintf(stderr,"J1.24-B1 %s:%d CHECK(%s)\n",__FILE__,__LINE__,#x); \
    return 1; } } while(0)
enum { CAP=2048, LINE=256 };
typedef struct {const char *id,*text;} Witness;
static const Witness witnesses[]={
  {"ZERO_LITERAL",
   "10 WHILE 0\n"
   "20 PRINT #8,\"BAD\"\n"
   "30 WEND\n"
   "40 PRINT #8,\"ZERO\"\n"
   "50 END\n"},
  {"FALSE_REL",
   "10 A%=0\n"
   "20 WHILE A%<0\n"
   "30 PRINT #8,\"BAD\"\n"
   "40 A%=A%+1\n"
   "50 WEND\n"
   "60 PRINT #8,\"FALSE\"\n"
   "70 END\n"},
  {"ONCE_LT",
   "10 A%=0\n"
   "20 WHILE A%<1\n"
   "30 PRINT #8,\"T\"\n"
   "40 A%=A%+1\n"
   "50 WEND\n"
   "60 PRINT #8,\"END\"\n"
   "70 END\n"},
  {"THREE_LT",
   "10 A%=0\n"
   "20 WHILE A%<3\n"
   "30 PRINT #8,\"T\"\n"
   "40 A%=A%+1\n"
   "50 WEND\n"
   "60 PRINT #8,\"END\"\n"
   "70 END\n"},
  {"GT_DECREMENT",
   "10 A%=3\n"
   "20 WHILE A%>0\n"
   "30 PRINT #8,A%\n"
   "40 A%=A%-1\n"
   "50 WEND\n"
   "60 PRINT #8,\"END\"\n"
   "70 END\n"},
  {"LE_BOUNDARY",
   "10 A%=0\n"
   "20 WHILE A%<=2\n"
   "30 PRINT #8,A%\n"
   "40 A%=A%+1\n"
   "50 WEND\n"
   "60 PRINT #8,\"END\"\n"
   "70 END\n"},
  {"NE_EXIT",
   "10 A%=0\n"
   "20 WHILE A%<>2\n"
   "30 PRINT #8,A%\n"
   "40 A%=A%+1\n"
   "50 WEND\n"
   "60 PRINT #8,\"END\"\n"
   "70 END\n"},
  {"EQ_FALSE",
   "10 A%=1\n"
   "20 WHILE A%=0\n"
   "30 PRINT #8,\"BAD\"\n"
   "40 A%=A%+1\n"
   "50 WEND\n"
   "60 PRINT #8,\"END\"\n"
   "70 END\n"},
  {"EQ_ONCE",
   "10 A%=1\n"
   "20 WHILE A%=1\n"
   "30 PRINT #8,\"T\"\n"
   "40 A%=2\n"
   "50 WEND\n"
   "60 PRINT #8,\"END\"\n"
   "70 END\n"},
  {"GE_DECREMENT",
   "10 A%=2\n"
   "20 WHILE A%>=0\n"
   "30 PRINT #8,A%\n"
   "40 A%=A%-1\n"
   "50 WEND\n"
   "60 PRINT #8,\"END\"\n"
   "70 END\n"},
  {"NEST_2X2",
   "10 A%=0\n"
   "20 WHILE A%<2\n"
   "30 B%=0\n"
   "40 WHILE B%<2\n"
   "50 PRINT #8,\"I\"\n"
   "60 B%=B%+1\n"
   "70 WEND\n"
   "80 A%=A%+1\n"
   "90 WEND\n"
   "100 PRINT #8,\"END\"\n"
   "110 END\n"},
  {"NEST_SKIP_INNER",
   "10 A%=0\n"
   "20 WHILE A%<2\n"
   "30 B%=0\n"
   "40 WHILE B%<0\n"
   "50 PRINT #8,\"BAD\"\n"
   "60 B%=B%+1\n"
   "70 WEND\n"
   "80 PRINT #8,\"OUTER\"\n"
   "90 A%=A%+1\n"
   "100 WEND\n"
   "110 PRINT #8,\"END\"\n"
   "120 END\n"},
  {"WEND_ORPHAN",
   "10 WEND\n"
   "20 PRINT #8,\"AFTER\"\n"
   "30 END\n"},
  {"WHILE_UNCLOSED",
   "10 WHILE 0\n"
   "20 PRINT #8,\"AFTER\"\n"
   "30 END\n"},
  {"WHILE_MISSING",
   "10 WHILE\n"
   "20 PRINT #8,\"AFTER\"\n"
   "30 WEND\n"
   "40 END\n"},
  {"WEND_OPERAND",
   "10 WHILE 0\n"
   "20 WEND 1\n"
   "30 PRINT #8,\"AFTER\"\n"
   "40 END\n"},
  {"WHILE_BAD_REL",
   "10 A%=0\n"
   "20 WHILE A%<\n"
   "30 PRINT #8,\"AFTER\"\n"
   "40 WEND\n"
   "50 END\n"},
  {"COLON_SAME_LINE",
   "10 A%=0:WHILE A%<2:PRINT #8,\"C\":A%=A%+1:WEND\n"
   "20 PRINT #8,\"END\"\n"
   "30 END\n"},
  {"COLON_CROSS_LINE",
   "10 A%=0\n"
   "20 WHILE A%<2:PRINT #8,\"C\"\n"
   "30 A%=A%+1:WEND\n"
   "40 PRINT #8,\"END\"\n"
   "50 END\n"},
  {"EMPTY_BODY",
   "10 A%=0\n"
   "20 WHILE A%<0\n"
   "30 WEND\n"
   "40 PRINT #8,\"END\"\n"
   "50 END\n"},
};
static int load(const char *root,const char *session,const char *id,
                const char *suffix,uint8_t *data,size_t cap,size_t *n)
{
    char path[512];
    FILE *fp;
    int c,k=snprintf(path,sizeof(path),
       "%s/tests/fixtures/cpc6128/j1_24_a_while_wend/%s/%s/%s",
       root,session,id,suffix);
    if(k<0||(size_t)k>=sizeof(path)) return 1;
    fp=fopen(path,"rb");
    if(!fp){fprintf(stderr,"MISSING %s\n",path);return 1;}
    *n=fread(data,1u,cap,fp);
    c=fgetc(fp);
    if(*n==0u||c!=EOF||ferror(fp)||fclose(fp)!=0)return 1;
    return 0;
}
static int cpc_list_matches(const char *src,const uint8_t *list,size_t n)
{
    size_t i,j=0u;
    for(i=0u;src[i];++i) {
        if(src[i]=='\n') {
            if(j+2u>n||list[j]!='\r'||list[j+1u]!='\n')return 0;
            j+=2u;
        } else {
            if(j>=n||list[j]!=(uint8_t)src[i])return 0;
            ++j;
        }
    }
    return j==n;
}
static int exact_line(const BasicProgram *cpc,unsigned int num,
                      const char *source,const char *id,const char *sess)
{
    BasicProgram one;
    BasicProgramLine a,b;
    uint8_t tokens[LINE],again[LINE],listing[LINE],memory[CAP];
    size_t n=987u,m=765u,k=543u,s=strlen(source);
    CHECK(bp_find(cpc,(uint16_t)num,&a)==BP_OK);
    CHECK(bt_tokenize((const uint8_t*)source,s,tokens,sizeof(tokens),&n)==BT_OK);
    if(n!=a.body_length||memcmp(tokens,cpc->data+a.body_offset,n)!=0) {
        size_t i;
        fprintf(stderr,"J1.24-B1 RAM_DIFF %s/%s line %u expected=",sess,id,num);
        for(i=0u;i<a.body_length;++i)fprintf(stderr,"%02X",cpc->data[a.body_offset+i]);
        fprintf(stderr," native=");
        for(i=0u;i<n;++i)fprintf(stderr,"%02X",tokens[i]);
        fputc('\n',stderr);
        return 1;
    }
    CHECK(bp_init(&one,memory,sizeof(memory))==BP_OK);
    CHECK(bp_put(&one,(uint16_t)num,tokens,n)==BP_OK);
    CHECK(bp_find(&one,(uint16_t)num,&b)==BP_OK);
    CHECK(a.next_offset-a.offset==b.next_offset-b.offset);
    CHECK(memcmp(cpc->data+a.offset,one.data+b.offset,
                 a.next_offset-a.offset)==0);
    CHECK(bl_detokenize(cpc->data+a.body_offset,a.body_length,
                        listing,sizeof(listing),&m)==BL_OK);
    if(m!=s||memcmp(listing,source,s)!=0) {
        fprintf(stderr,"J1.24-B1 LIST_DIFF %s/%s line %u\n",sess,id,num);
        return 1;
    }
    CHECK(bt_tokenize(listing,m,again,sizeof(again),&k)==BT_OK);
    CHECK(k==n&&memcmp(again,tokens,n)==0);
    return 0;
}
static int compare_witness(const char *root,const Witness *w)
{
    static const char *const session[2]={"original","repeat"};
    uint8_t first_image[CAP],first_list[CAP];
    size_t first_n=0u,first_l=0u,s,matched=0u,ignored=0u;
    for(s=0u;s<2u;++s) {
        uint8_t raw[CAP],printer[CAP],store[CAP];
        BasicProgram cpc;
        size_t n=0u,l=0u;
        const char *p=w->text;
        CHECK(load(root,session[s],w->id,"program.bin",
                   raw,sizeof(raw),&n)==0);
        CHECK(load(root,session[s],w->id,"list/printer.dat",
                   printer,sizeof(printer),&l)==0);
        CHECK(cpc_list_matches(w->text,printer,l)); /* PRE-RUN only */
        if(!s){memcpy(first_image,raw,n);first_n=n;
               memcpy(first_list,printer,l);first_l=l;}
        else{CHECK(n==first_n&&memcmp(first_image,raw,n)==0);
             CHECK(l==first_l&&memcmp(first_list,printer,l)==0);}
        CHECK(bp_init(&cpc,store,sizeof(store))==BP_OK);
        CHECK(bp_import(&cpc,raw,n)==BP_OK);
        while(*p) {
            const char *end=strchr(p,'\n');
            char line[LINE];
            size_t len;
            unsigned int number=0u;
            int shift=0;
            CHECK(end!=NULL);
            len=(size_t)(end-p);
            CHECK(len>0u&&len<sizeof(line));
            memcpy(line,p,len);line[len]='\0';
            CHECK(sscanf(line,"%u %n",&number,&shift)==1);
            CHECK(shift>0&&number>0u&&number<65536u);
            if(strstr(line+shift,"WHILE")||strstr(line+shift,"WEND")) {
                CHECK(exact_line(&cpc,number,line+shift,w->id,session[s])==0);
                ++matched;
            } else ++ignored; /* PRINT #8 is not a new B1 grammar. */
            p=end+1;
        }
    }
    CHECK(matched>0u);
    printf("J1.24-B1 %s MATCH_EXACT original/repeat %zu records; "
           "%zu non-WHILE/WEND lines excluded\n",w->id,matched,ignored);
    return 0;
}
static int negatives(void)
{
    static const char *const bad[]={
      "WHILE 0::WEND","WHILE 0:","WHILE !","WHILE \"X\"",
      "WHILE A%<<2","WHILE A%<+","WEND 2","WEND 12",
      "WEND X%","WHILE A%%<1","WHILEX 0","WEND_1",
      "WHILE 0\nWEND"
    };
    static const uint8_t truncs[][8]={
       {0xd6u,' ',0x02u,0u,0u,0xc1u,0xf1u,0xffu},
       {0xd6u,' ',0x19u},
       {0xd6u,' ',0x02u,0u},
       {0xd5u,' ',0xf4u},
       {0xd5u,' ',0x19u,2u}
    };
    static const size_t trunc_n[]={8u,3u,4u,3u,4u};
    uint8_t buf[256],saved[256],store[CAP],old_store[CAP],temp[256],out[256],old_out[256];
    BasicProgram p;
    BSResult bs;
    size_t i,n;
    for(i=0u;i<sizeof(bad)/sizeof(bad[0]);++i) {
        memset(buf,0x75,sizeof(buf));memcpy(saved,buf,sizeof(buf));n=777u;
        CHECK(bt_tokenize((const uint8_t*)bad[i],strlen(bad[i]),
                         buf,sizeof(buf),&n)!=BT_OK);
        CHECK(n==777u&&memcmp(buf,saved,sizeof(buf))==0);
    }
    for(i=0u;i<sizeof(trunc_n)/sizeof(trunc_n[0]);++i) {
        memset(buf,0x75,sizeof(buf));memcpy(saved,buf,sizeof(buf));n=777u;
        CHECK(bl_detokenize(truncs[i],trunc_n[i],buf,sizeof(buf),&n)!=BL_OK);
        CHECK(n==777u&&memcmp(buf,saved,sizeof(buf))==0);
    }
    memset(buf,0x75,sizeof(buf));memcpy(saved,buf,sizeof(buf));n=777u;
    CHECK(bt_tokenize((const uint8_t*)"WHILE A%<2",10u,
                      buf,2u,&n)==BT_NO_SPACE);
    CHECK(n==777u&&memcmp(buf,saved,sizeof(buf))==0);
    CHECK(bt_tokenize(NULL,0u,buf,sizeof(buf),&n)==BT_INVALID_ARGUMENT);
    CHECK(bt_tokenize(buf,5u,buf,sizeof(buf),&n)==BT_INVALID_ARGUMENT);
    CHECK(bl_detokenize((const uint8_t[]){0xd6u,' ',0x0eu},
                        3u,buf,2u,&n)==BL_NO_SPACE);
    CHECK(bl_detokenize(buf,5u,buf,sizeof(buf),&n)==BL_OVERLAP);
    CHECK(n==777u&&memcmp(buf,saved,sizeof(buf))==0);
    CHECK(bp_init(&p,store,sizeof(store))==BP_OK);
    n=777u;
    CHECK(bt_tokenize((const uint8_t*)"WHILE 0",7u,temp,sizeof(temp),&n)==BT_OK);
    CHECK(bp_put(&p,10u,temp,n)==BP_OK);
    memcpy(old_store,store,sizeof(store));
    memset(out,0x33,sizeof(out));memcpy(old_out,out,sizeof(out));n=888u;
    bs=bs_process_line(&p,(const uint8_t*)"20 WHILE 0:",
                       strlen("20 WHILE 0:"),temp,sizeof(temp),out,sizeof(out),&n);
    CHECK(bs.status==BS_TOKENIZER_ERROR&&n==888u);
    CHECK(memcmp(store,old_store,sizeof(store))==0);
    CHECK(memcmp(out,old_out,sizeof(out))==0);
    CHECK(bl_list_program(&p,out,1u,&n)==BL_NO_SPACE&&n==888u);
    {uint8_t tiny[8],saved_tiny[8];BasicProgram small;
     memset(tiny,0x55,sizeof(tiny));
     CHECK(bp_init(&small,tiny,sizeof(tiny))==BP_OK);
     memcpy(saved_tiny,tiny,sizeof(tiny));n=888u;
     bs=bs_process_line(&small,(const uint8_t*)"10 WHILE 0",
                        10u,temp,sizeof(temp),out,sizeof(out),&n);
     CHECK(bs.status==BS_PROGRAM_ERROR&&bs.program_status==BP_NO_SPACE);
     CHECK(n==888u&&memcmp(tiny,saved_tiny,sizeof(tiny))==0);}
    return 0;
}
static int no_run(void)
{
    static const char *const commands[]={
        "WHILE 0","WEND","WHILE A%<2","WHILE","WHILE A%<","WEND 1",
        "A%=0:WHILE A%<2:PRINT #8,\"C\":A%=A%+1:WEND"
    };
    size_t i;
    for(i=0u;i<sizeof(commands)/sizeof(commands[0]);++i) {
        uint8_t data[CAP],before_data[CAP],tok[256],out[64],old_out[64];
        BEVideoEvent events[2],old_events[2];
        BasicProgram p;
        BasicVariableEntry entries[4],old_entries[4];
        BasicVariableStore store,old_store;
        BasicExecutor ex,old_ex;
        size_t n=777u,written=888u,event_written=999u;
        BEStatus st;
        CHECK(bp_init(&p,data,sizeof(data))==BP_OK);
        CHECK(bt_tokenize((const uint8_t*)commands[i],strlen(commands[i]),
                          tok,sizeof(tok),&n)==BT_OK);
        CHECK(bp_put(&p,10u,tok,n)==BP_OK);
        CHECK(bvs_init(&store,entries,4u)==BVS_OK);
        CHECK(be_init_with_store(&ex,&p,&store)==BE_OK);
        old_ex=ex;old_store=store;
        memcpy(old_entries,entries,sizeof(entries));
        memcpy(before_data,data,sizeof(data));
        memset(out,0x5a,sizeof(out));memcpy(old_out,out,sizeof(out));
        memset(events,0x6b,sizeof(events));memcpy(old_events,events,sizeof(events));
        st=be_step_events(&ex,out,sizeof(out),&written,events,2u,&event_written);
        CHECK(st==BE_UNKNOWN_TOKEN||st==BE_UNSUPPORTED);
        CHECK(memcmp(&ex,&old_ex,sizeof(ex))==0);
        CHECK(memcmp(&store,&old_store,sizeof(store))==0);
        CHECK(memcmp(entries,old_entries,sizeof(entries))==0);
        CHECK(memcmp(data,before_data,sizeof(data))==0);
        CHECK(memcmp(out,old_out,sizeof(out))==0&&written==888u);
        CHECK(memcmp(events,old_events,sizeof(events))==0&&event_written==999u);
        st=be_preview_step_events(&ex,out,sizeof(out),&written,events,2u,&event_written);
        CHECK(st==BE_UNKNOWN_TOKEN||st==BE_UNSUPPORTED);
        CHECK(memcmp(&ex,&old_ex,sizeof(ex))==0);
        CHECK(memcmp(entries,old_entries,sizeof(entries))==0);
        CHECK(memcmp(out,old_out,sizeof(out))==0&&written==888u);
        st=be_step(&ex,out,sizeof(out),&written);
        CHECK(st==BE_UNKNOWN_TOKEN||st==BE_UNSUPPORTED);
        CHECK(memcmp(&ex,&old_ex,sizeof(ex))==0);
        CHECK(memcmp(entries,old_entries,sizeof(entries))==0);
        CHECK(memcmp(out,old_out,sizeof(out))==0&&written==888u);
    }
    return 0;
}
int main(int argc,char **argv)
{
    size_t i;
    CHECK(argc==2);
    CHECK(negatives()==0);
    CHECK(no_run()==0);
    for(i=0u;i<sizeof(witnesses)/sizeof(witnesses[0]);++i)
        CHECK(compare_witness(argv[1],&witnesses[i])==0);
    puts("J1.24-B1 20_CASES 40_SESSIONS records WHILE/WEND matched; "
         "PRE_RUN_LIST only; no native RUN");
    return 0;
}
