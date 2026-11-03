/* J1.24-B2: native bounded WHILE/WEND executor with immutable CPC ROM
 * oracle. CPC PRINT #8 -> host PRINT is an in-memory TEST projection ONLY:
 * never a modification to archived program.bin, LIST or native CORE I/O. */
#include "basic_executor.h"
#include "basic_program.h"
#include "basic_session_runtime.h"
#include "basic_tokenizer.h"
#include "basic_variable_store.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if(!(x)){ \
  fprintf(stderr,"J1.24-B2 %s:%d: %s\n",__FILE__,__LINE__,#x);return 1;\
} }while(0)
enum{STORE=4096,FILE_CAP=8192,LINE=512,OUT_CAP=1024,STEP_LIMIT=512};
typedef struct {const char *id; BEStatus failure; uint16_t cpc_fault_line;} Case;
static const Case cases[]={
  {"ZERO_LITERAL",BE_OK,0u},
  {"FALSE_REL",BE_OK,0u},
  {"ONCE_LT",BE_OK,0u},
  {"THREE_LT",BE_OK,0u},
  {"GT_DECREMENT",BE_OK,0u},
  {"LE_BOUNDARY",BE_OK,0u},
  {"NE_EXIT",BE_OK,0u},
  {"EQ_FALSE",BE_OK,0u},
  {"EQ_ONCE",BE_OK,0u},
  {"GE_DECREMENT",BE_OK,0u},
  {"NEST_2X2",BE_OK,0u},
  {"NEST_SKIP_INNER",BE_OK,0u},
  {"COLON_SAME_LINE",BE_OK,0u},
  {"COLON_CROSS_LINE",BE_OK,0u},
  {"EMPTY_BODY",BE_OK,0u},
  {"WEND_ORPHAN",BE_WEND_WITHOUT_WHILE,10u},
  {"WHILE_UNCLOSED",BE_WHILE_WITHOUT_WEND,10u},
  {"WHILE_MISSING",BE_WHILE_OPERAND_MISSING,10u},
  {"WEND_OPERAND",BE_DIAG_CONTRADICTORY,20u},
  {"WHILE_BAD_REL",BE_WHILE_OPERAND_MISSING,20u},
};
typedef struct {
    uint8_t storage[STORE], print_output[OUT_CAP];
    uint8_t scratch[LINE];
    BasicProgram program;
    BasicVariableEntry entries[8];
    BasicVariableStore variables;
    BasicExecutor exec;
} Native;
static int load(const char *root,const char *session,const char *id,
                const char *suffix,uint8_t *out,size_t cap,size_t *length)
{
    char file[512];
    FILE *fp;
    int trailing;
    int n=snprintf(file,sizeof(file),
       "%s/tests/fixtures/cpc6128/j1_24_a_while_wend/%s/%s/%s",
       root,session,id,suffix);
    if(n<0||(size_t)n>=sizeof(file))return 1;
    fp=fopen(file,"rb");
    if(!fp){fprintf(stderr,"ABSENT %s\n",file);return 1;}
    *length=fread(out,1u,cap,fp);
    trailing=fgetc(fp);
    if(*length==0u||trailing!=EOF||ferror(fp)||fclose(fp)!=0)return 1;
    return 0;
}
/* Remove precisely the CPC stream-8 selector in TEST memory (BF ' ' #16,).
 * No other byte rewritten; original CPC program.bin stays read-only. */
static int projection(const uint8_t *b,size_t n,uint8_t *out,size_t cap,
                      size_t *written)
{
    size_t i=0u,k=0u;
    while(i<n) {
        if(i+4u<n && b[i]==0xbfu && b[i+1u]==' ' &&
           b[i+2u]=='#' && b[i+3u]==0x16u && b[i+4u]==',') {
            if(cap-k<2u)return 1;
            out[k++]=0xbfu;
            out[k++]=' ';
            i+=5u;
        } else {
            if(k==cap)return 1;
            out[k++]=b[i++];
        }
    }
    *written=k;
    return 0;
}
static int prepare_oracle(Native *f,const uint8_t *image,size_t n)
{
    uint8_t source_storage[STORE],projected[LINE];
    BasicProgram original;
    BasicProgramLine line;
    size_t cursor=0u,length;
    BPStatus status;
    memset(f,0,sizeof(*f));
    CHECK(bp_init(&original,source_storage,sizeof(source_storage))==BP_OK);
    CHECK(bp_import(&original,image,n)==BP_OK);
    CHECK(bp_init(&f->program,f->storage,sizeof(f->storage))==BP_OK);
    while((status=bp_next(&original,&cursor,&line))==BP_OK) {
        CHECK(projection(original.data+line.body_offset,line.body_length,
                         projected,sizeof(projected),&length)==0);
        CHECK(bp_put(&f->program,line.number,projected,length)==BP_OK);
    }
    CHECK(status==BP_END);
    CHECK(bvs_init(&f->variables,f->entries,8u)==BVS_OK);
    CHECK(be_init_with_store(&f->exec,&f->program,&f->variables)==BE_OK);
    CHECK(f->exec.while_depth==0u);
    return 0;
}
/* Extract only actual CPC PRINT #8 bytes BEFORE the J124 diagnostic
 * marker; strips the two-byte CPC CRLF to one host LF, no other rewrite.
 * Explicitly NOT an exact byte-for-byte host serial reproduction. */
static int cpc_semantic_prefix(const uint8_t *b,size_t n,
                               uint8_t *expected,size_t cap,size_t *size)
{
    static const char mark[]="J124_DIAG_BEGIN\r\n";
    size_t i,j,limit=n;
    for(i=0u;i+sizeof(mark)-1u<=n;++i) {
        if(memcmp(b+i,mark,sizeof(mark)-1u)==0) {
            limit=i;break;
        }
    }
    if(limit==n)return 1;
    j=0u;
    for(i=0u;i<limit;++i) {
        if(j==cap)return 1;
        if(b[i]=='\r' && i+1u<limit && b[i+1u]=='\n') {
            expected[j++]='\n';++i;
        } else expected[j++]=b[i];
    }
    *size=j;
    return 0;
}
static int append_output(uint8_t *all,size_t *used,const uint8_t *step,size_t n)
{
    if(OUT_CAP-*used<n)return 1;
    memcpy(all+*used,step,n);*used+=n;return 0;
}
static int checked_success_step(Native *f,uint8_t *all,size_t *total)
{
    uint8_t preview[OUT_CAP],commit[OUT_CAP],store[STORE],saved_entries[sizeof(f->entries)];
    BasicExecutor state=f->exec;
    BasicVariableStore before_vars=f->variables;
    BEVideoEvent events[1],preview_events[1];
    size_t a=777u,b=888u,e=999u,pe=666u;
    BEStatus first,second;
    memcpy(store,f->storage,sizeof(store));
    memcpy(saved_entries,f->entries,sizeof(saved_entries));
    memset(preview,0xa3,sizeof(preview));
    memset(commit,0x71,sizeof(commit));
    memset(events,0x44,sizeof(events));
    memset(preview_events,0x45,sizeof(preview_events));
    first=be_preview_step_events(&f->exec,preview,sizeof(preview),&a,
                                 preview_events,1u,&pe);
    CHECK(memcmp(&f->exec,&state,sizeof(state))==0);
    CHECK(memcmp(&f->variables,&before_vars,sizeof(before_vars))==0);
    CHECK(memcmp(f->entries,saved_entries,sizeof(saved_entries))==0);
    CHECK(memcmp(f->storage,store,sizeof(store))==0);
    if(first==BE_END) {
        CHECK(a==777u && pe==666u);
        return 2;
    }
    if(first!=BE_OK) {
        fprintf(stderr,"B2 preview fail status=%d cursor=%zu offset=%zu\n",
                (int)first,f->exec.cursor,f->exec.statement_offset);
        return 1;
    }
    second=be_step_events(&f->exec,commit,sizeof(commit),&b,
                          events,1u,&e);
    CHECK(second==BE_OK);
    CHECK(a==b && pe==e && e==0u);
    CHECK(memcmp(preview,commit,a)==0);
    CHECK(append_output(all,total,commit,b)==0);
    return 0;
}
static int failure_snapshot(Native *f,BEStatus wanted)
{
    uint8_t out[128],old_out[128],store[STORE],entries[sizeof(f->entries)];
    BEVideoEvent events[2],old_events[2];
    BasicExecutor old=f->exec;
    BasicVariableStore old_vars=f->variables;
    size_t count=777u,event_count=888u;
    BEStatus a,b,c;
    memset(out,0x71,sizeof(out));memcpy(old_out,out,sizeof(out));
    memset(events,0x42,sizeof(events));memcpy(old_events,events,sizeof(events));
    memcpy(store,f->storage,sizeof(store));
    memcpy(entries,f->entries,sizeof(entries));
    a=be_preview_step_events(&f->exec,out,sizeof(out),&count,
                             events,2u,&event_count);
    CHECK(a==wanted);
    CHECK(memcmp(&f->exec,&old,sizeof(old))==0);
    CHECK(memcmp(&f->variables,&old_vars,sizeof(old_vars))==0);
    CHECK(memcmp(f->entries,entries,sizeof(entries))==0);
    CHECK(memcmp(f->storage,store,sizeof(store))==0);
    CHECK(count==777u && event_count==888u);
    CHECK(memcmp(out,old_out,sizeof(out))==0);
    CHECK(memcmp(events,old_events,sizeof(events))==0);
    b=be_step_events(&f->exec,out,sizeof(out),&count,
                     events,2u,&event_count);
    CHECK(b==wanted);
    CHECK(memcmp(&f->exec,&old,sizeof(old))==0);
    CHECK(memcmp(f->entries,entries,sizeof(entries))==0);
    CHECK(memcmp(f->storage,store,sizeof(store))==0);
    CHECK(count==777u && event_count==888u);
    CHECK(memcmp(out,old_out,sizeof(out))==0);
    CHECK(memcmp(events,old_events,sizeof(events))==0);
    c=be_step(&f->exec,out,sizeof(out),&count);
    CHECK(c==wanted);
    CHECK(memcmp(&f->exec,&old,sizeof(old))==0);
    CHECK(memcmp(&f->variables,&old_vars,sizeof(old_vars))==0);
    CHECK(memcmp(f->entries,entries,sizeof(entries))==0);
    CHECK(memcmp(f->storage,store,sizeof(store))==0);
    CHECK(count==777u && memcmp(out,old_out,sizeof(out))==0);
    return 0;
}
static int check_case(const char *root,const Case *item)
{
    static const char *const session[]={"original","repeat"};
    size_t s;
    for(s=0u;s<2u;++s) {
        Native f;
        uint8_t image[FILE_CAP],cpc_printer[FILE_CAP],expected[OUT_CAP],actual[OUT_CAP];
        size_t image_size=0u,printer_size=0u,expect_size=0u,used=0u;
        size_t steps;
        int failed=0,done=0;
        CHECK(load(root,session[s],item->id,"program.bin",
                   image,sizeof(image),&image_size)==0);
        CHECK(load(root,session[s],item->id,"run/printer.dat",
                   cpc_printer,sizeof(cpc_printer),&printer_size)==0);
        CHECK(prepare_oracle(&f,image,image_size)==0);
        CHECK(cpc_semantic_prefix(cpc_printer,printer_size,
                                  expected,sizeof(expected),&expect_size)==0);
        for(steps=0u;steps<STEP_LIMIT;++steps) {
            int succeeded=checked_success_step(&f,actual,&used);
            if(succeeded==2){done=1;break;}
            if(succeeded==1) {
                if(item->failure!=BE_OK) {
                    CHECK(failure_snapshot(&f,item->failure)==0);
                    { uint16_t actual_line=0u;
                      CHECK(be_while_diagnostic_line(&f.exec,item->failure,
                                                     &actual_line)==BE_OK);
                      CHECK(actual_line==item->cpc_fault_line);
                    }
                    failed=1;break;
                }
                return 1;
            }
        }
        CHECK(steps<STEP_LIMIT);
        if(item->failure==BE_OK) {
            if(!done || failed || used!=expect_size ||
               memcmp(actual,expected,used)!=0) {
                size_t i;
                fprintf(stderr,"B2 SEMANTIC_DIFF %s/%s steps=%zu got %zu exp %zu\n",
                        session[s],item->id,steps,used,expect_size);
                fprintf(stderr,"GOT:");
                for(i=0u;i<used;++i)fprintf(stderr," %02X",actual[i]);
                fprintf(stderr,"\nEXP:");
                for(i=0u;i<expect_size;++i)fprintf(stderr," %02X",expected[i]);
                fputc('\n',stderr);
                return 1;
            }
            CHECK(f.exec.while_depth==0u);
        } else {
            CHECK(failed && !done);
            /* Historical line is read from independent CPC archive
             * metadata, not manufactured as BEStatus -> CPC ERR. */
            { BasicProgramLine line;
              CHECK(bp_find(&f.program,item->cpc_fault_line,&line)==BP_OK);
              CHECK(line.number==item->cpc_fault_line);
            }
            CHECK(used==expect_size && memcmp(actual,expected,used)==0);
        }
        printf("J1.24-B2 %s %s %s steps=%zu output=%zu CPC_printer_normalized=%zu\n",
               item->id,session[s],
               item->failure==BE_OK?"MATCH_SEMANTIC":"HOST_TYPED_FAILURE",
               steps,used,expect_size);
    }
    return 0;
}
typedef struct {
    uint8_t data[STORE],buf[LINE],out[128];
    BasicProgram program;
    BasicVariableEntry entries[8];
    BasicVariableStore vars;
    BasicExecutor ex;
} Fixture;
static int setup(Fixture *f)
{
    memset(f,0,sizeof(*f));
    CHECK(bp_init(&f->program,f->data,sizeof(f->data))==BP_OK);
    CHECK(bvs_init(&f->vars,f->entries,8u)==BVS_OK);
    return 0;
}
static int put(Fixture *f,unsigned int line,const char *src)
{
    size_t n=999u;
    CHECK(bt_tokenize((const uint8_t*)src,strlen(src),
                      f->buf,sizeof(f->buf),&n)==BT_OK);
    CHECK(bp_put(&f->program,(uint16_t)line,f->buf,n)==BP_OK);
    return 0;
}
static int init(Fixture *f)
{
    CHECK(be_init_with_store(&f->ex,&f->program,&f->vars)==BE_OK);
    return 0;
}
static int success(Fixture *f)
{
    size_t n=999u;
    CHECK(be_step(&f->ex,f->out,sizeof(f->out),&n)==BE_OK);
    return 0;
}
/* Eight nested active frames work; the ninth refuses atomically.
 * Host capacity is NOT CPC ROM capacity. */
static int depth_tests(void)
{
    Fixture f;
    size_t i;
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"A%=0")==0);
    for(i=0u;i<8u;++i)CHECK(put(&f,(unsigned int)(20u+i*10u),"WHILE A%<1")==0);
    CHECK(put(&f,100u,"A%=1")==0);
    for(i=0u;i<8u;++i)CHECK(put(&f,(unsigned int)(110u+i*10u),"WEND")==0);
    CHECK(put(&f,190u,"END")==0);
    CHECK(init(&f)==0);
    for(i=0u;i<9u;++i) CHECK(success(&f)==0);
    CHECK(f.ex.while_depth==8u);
    CHECK(success(&f)==0); /* A%=1 */
    for(i=0u;i<16u;++i)CHECK(success(&f)==0);
    CHECK(f.ex.while_depth==0u);
    CHECK(success(&f)==0); /* END */
    CHECK(f.ex.while_depth==0u);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"A%=0")==0);
    for(i=0u;i<9u;++i)CHECK(put(&f,(unsigned int)(20u+i*10u),"WHILE A%<1")==0);
    CHECK(put(&f,110u,"A%=1")==0);
    for(i=0u;i<9u;++i)CHECK(put(&f,(unsigned int)(120u+i*10u),"WEND")==0);
    CHECK(put(&f,220u,"END")==0);
    CHECK(init(&f)==0);
    for(i=0u;i<9u;++i)CHECK(success(&f)==0);
    CHECK(f.ex.while_depth==8u);
    { BasicExecutor before=f.ex;size_t n=666u;
      memset(f.out,0x3a,sizeof(f.out));
      CHECK(be_step(&f.ex,f.out,sizeof(f.out),&n)==BE_WHILE_STACK_FULL);
      CHECK(memcmp(&before,&f.ex,sizeof(before))==0 && n==666u);
      for(i=0u;i<sizeof(f.out);++i)CHECK(f.out[i]==0x3au);
    }
    return 0;
}
static int low_capacity(void)
{
    Fixture f;
    uint8_t output[64],saved[64];
    size_t n=999u,events_n=888u;
    BEVideoEvent ev[1];
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"A%=0")==0);
    CHECK(put(&f,20u,"WHILE A%<1")==0);
    CHECK(put(&f,30u,"PRINT \"T\"")==0);
    CHECK(put(&f,40u,"A%=1")==0);
    CHECK(put(&f,50u,"WEND")==0);
    CHECK(put(&f,60u,"END")==0);
    CHECK(init(&f)==0);
    CHECK(success(&f)==0);
    CHECK(success(&f)==0);
    memset(output,0x44,sizeof(output));memcpy(saved,output,sizeof(saved));
    CHECK(be_step_events(&f.ex,output,0u,&n,ev,1u,&events_n)==BE_NO_SPACE);
    CHECK(n==999u && events_n==888u);
    CHECK(memcmp(output,saved,sizeof(output))==0);
    CHECK(be_step_events(&f.ex,output,1u,&n,ev,1u,&events_n)==BE_NO_SPACE);
    CHECK(n==999u && events_n==888u);
    CHECK(memcmp(output,saved,sizeof(output))==0);
    CHECK(be_step_events(&f.ex,NULL,sizeof(output),&n,ev,1u,&events_n)
          ==BE_INVALID_ARGUMENT);
    CHECK(be_step_events(&f.ex,output,sizeof(output),&n,NULL,1u,&events_n)
          ==BE_INVALID_ARGUMENT);
    CHECK(be_step_events(&f.ex,(uint8_t*)&f.ex,sizeof(f.ex),&n,ev,1u,
                         &events_n)==BE_OVERLAP);
    CHECK(success(&f)==0);
    return 0;
}

static int fixture_failure(Fixture *f, BEStatus status)
{
    BasicExecutor before=f->ex;
    BasicVariableStore var_before=f->vars;
    uint8_t bytes[STORE],old_entries[sizeof(f->entries)],output[128],copy[128];
    BEVideoEvent events[1],evcopy[1];
    size_t n=999u,m=888u;
    memcpy(bytes,f->data,sizeof(bytes));
    memcpy(old_entries,f->entries,sizeof(old_entries));
    memset(output,0x79,sizeof(output));memcpy(copy,output,sizeof(copy));
    memset(events,0x64,sizeof(events));memcpy(evcopy,events,sizeof(events));
    CHECK(be_preview_step_events(&f->ex,output,sizeof(output),&n,
                                 events,1u,&m)==status);
    CHECK(memcmp(&f->ex,&before,sizeof(before))==0);
    CHECK(memcmp(&f->vars,&var_before,sizeof(var_before))==0);
    CHECK(memcmp(f->data,bytes,sizeof(bytes))==0);
    CHECK(memcmp(f->entries,old_entries,sizeof(old_entries))==0);
    CHECK(n==999u&&m==888u&&memcmp(output,copy,sizeof(output))==0);
    CHECK(memcmp(events,evcopy,sizeof(events))==0);
    CHECK(be_step_events(&f->ex,output,sizeof(output),&n,
                         events,1u,&m)==status);
    CHECK(memcmp(&f->ex,&before,sizeof(before))==0);
    CHECK(memcmp(f->data,bytes,sizeof(bytes))==0);
    CHECK(memcmp(f->entries,old_entries,sizeof(old_entries))==0);
    CHECK(n==999u&&m==888u&&memcmp(output,copy,sizeof(output))==0);
    CHECK(memcmp(events,evcopy,sizeof(events))==0);
    CHECK(be_step(&f->ex,output,sizeof(output),&n)==status);
    CHECK(memcmp(&f->ex,&before,sizeof(before))==0);
    CHECK(memcmp(f->data,bytes,sizeof(bytes))==0);
    CHECK(memcmp(f->entries,old_entries,sizeof(old_entries))==0);
    CHECK(n==999u&&memcmp(output,copy,sizeof(output))==0);
    return 0;
}
static int unsupported_and_malformed(void)
{
    Fixture f;
    static const uint8_t incomplete_ref[] = {0xd6u,' ',0x02u,0u};
    static const uint8_t bad_wend[] = {0xd5u,' ',0x19u,2u};
    size_t i,n=999u,aggregate=0u;
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"WHILE 1")==0);
    CHECK(put(&f,20u,"WEND")==0);
    CHECK(init(&f)==0);
    CHECK(fixture_failure(&f,BE_WHILE_CONDITION_INVALID)==0);
    CHECK(setup(&f)==0);
    CHECK(bp_put(&f.program,10u,incomplete_ref,sizeof(incomplete_ref))==BP_OK);
    CHECK(put(&f,20u,"WEND")==0);
    CHECK(init(&f)==0);
    CHECK(fixture_failure(&f,BE_TRUNCATED)==0);
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"WHILE 0")==0);
    CHECK(bp_put(&f.program,20u,bad_wend,sizeof(bad_wend))==BP_OK);
    CHECK(init(&f)==0);
    CHECK(fixture_failure(&f,BE_BAD_SEQUENCE)==0);
    /* The string "WEND:WHILE" must not end the false branch. */
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"WHILE 0")==0);
    CHECK(put(&f,20u,"PRINT \"WEND:WHILE\"")==0);
    CHECK(put(&f,30u,"WEND")==0);
    CHECK(put(&f,40u,"PRINT \"OK\"")==0);
    CHECK(put(&f,50u,"END")==0);
    CHECK(init(&f)==0);
    for(i=0u;i<3u;++i) {
        CHECK(be_step(&f.ex,f.out,sizeof(f.out),&n)==BE_OK);
        if(n!=0u) {CHECK(n==3u&&memcmp(f.out,"OK\n",3u)==0);++aggregate;}
    }
    CHECK(aggregate==1u);
    CHECK(f.ex.while_depth==0u);
    /* Already committed output persists after a later failed step. */
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"PRINT \"BEFORE\"")==0);
    CHECK(put(&f,20u,"WEND")==0);
    CHECK(init(&f)==0);
    n=999u;
    CHECK(be_step(&f.ex,f.out,sizeof(f.out),&n)==BE_OK);
    CHECK(n==7u&&memcmp(f.out,"BEFORE\n",7u)==0);
    CHECK(fixture_failure(&f,BE_WEND_WITHOUT_WHILE)==0);
    CHECK(memcmp(f.out,"BEFORE\n",7u)==0);
    return 0;
}

/* C2 falsification: colon presence near a loop never admits arbitrary
 * compound statements. Each rejected *reached* step is byte-exact on
 * preview, eventful commit and simple commit (including the active frame). */
static int colon_boundaries(void)
{
    Fixture f;
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"A%=0:B%=1:WHILE 0")==0);
    CHECK(put(&f,20u,"WEND")==0);
    CHECK(put(&f,30u,"PRINT B%")==0);
    CHECK(init(&f)==0);
    CHECK(fixture_failure(&f,BE_UNSUPPORTED)==0);

    /* A second assignment before WHILE is not a permitted setup. */
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"A%=0:B%=1:WHILE A%<1:PRINT \"C\":A%=1:WEND")==0);
    CHECK(init(&f)==0);
    CHECK(fixture_failure(&f,BE_UNSUPPORTED)==0);

    /* A false WHILE must not silently skip an unmeasured suffix. */
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"WHILE 0:PRINT \"BAD\":PRINT \"EXTRA\":WEND")==0);
    CHECK(init(&f)==0);
    CHECK(fixture_failure(&f,BE_UNSUPPORTED)==0);

    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"A%=0")==0);
    CHECK(put(&f,20u,"WHILE A%<1:PRINT \"X\":PRINT \"Y\":WEND")==0);
    CHECK(init(&f)==0);
    CHECK(success(&f)==0); /* setup already committed, not rolled back */
    CHECK(fixture_failure(&f,BE_UNSUPPORTED)==0);

    /* Active loop: PRINT:assignment:WEND and two assignments:WEND
     * are not the cross-record assignment:WEND form. */
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"A%=0")==0);
    CHECK(put(&f,20u,"WHILE A%<1")==0);
    CHECK(put(&f,30u,"PRINT \"X\":A%=1:WEND")==0);
    CHECK(init(&f)==0);
    CHECK(success(&f)==0);
    CHECK(success(&f)==0);
    CHECK(f.ex.while_depth==1u);
    CHECK(fixture_failure(&f,BE_UNSUPPORTED)==0);
    CHECK(f.ex.while_depth==1u);

    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"A%=0")==0);
    CHECK(put(&f,20u,"WHILE A%<1")==0);
    CHECK(put(&f,30u,"A%=1:B%=2:WEND")==0);
    CHECK(init(&f)==0);
    CHECK(success(&f)==0);
    CHECK(success(&f)==0);
    CHECK(f.ex.while_depth==1u);
    CHECK(fixture_failure(&f,BE_UNSUPPORTED)==0);
    CHECK(f.ex.while_depth==1u);

    /* WEND does not authorize an additional statement in its record. */
    CHECK(setup(&f)==0);
    CHECK(put(&f,10u,"A%=0:WHILE A%<1:PRINT \"C\":A%=1:WEND:PRINT \"TAIL\"")==0);
    CHECK(init(&f)==0);
    CHECK(fixture_failure(&f,BE_UNSUPPORTED)==0);
    puts("J1.24-B2-C2 colon boundary: 7 non-oracled records atomically refused");
    return 0;
}

static int session_resets(void)
{
    Fixture f;
    BasicSessionRuntime runtime;
    uint8_t temp[LINE],output[128];
    size_t n=999u,i;
    static const char *const code[]={
      "A%=0","WHILE A%<1","A%=1","WEND","END"
    };
    CHECK(setup(&f)==0);
    for(i=0u;i<5u;++i)CHECK(put(&f,(unsigned int)(10u+i*10u),code[i])==0);
    CHECK(bsr_init_with_store(&runtime,&f.program,&f.vars).status==BSR_OK);
    CHECK(bsr_submit(&runtime,(const uint8_t*)"RUN",3u,
                     temp,sizeof(temp),output,sizeof(output),&n).status==BSR_OK);
    CHECK(runtime.executor.while_depth==0u);
    for(i=0u;i<2u;++i)
        CHECK(bsr_step(&runtime,output,sizeof(output),&n).status==BSR_OK);
    CHECK(runtime.executor.while_depth==1u);
    CHECK(bsr_stop(&runtime).status==BSR_OK);
    CHECK(runtime.executor.while_depth==0u);
    { size_t j;
      const uint8_t *p=(const uint8_t*)runtime.executor.while_stack;
      for(j=0u;j<sizeof(runtime.executor.while_stack);++j)CHECK(p[j]==0u);
    }
    CHECK(bsr_submit(&runtime,(const uint8_t*)"RUN",3u,
                     temp,sizeof(temp),output,sizeof(output),&n).status==BSR_OK);
    for(i=0u;i<2u;++i)
        CHECK(bsr_step(&runtime,output,sizeof(output),&n).status==BSR_OK);
    CHECK(runtime.executor.while_depth==1u);
    CHECK(bsr_submit(&runtime,(const uint8_t*)"NEW",3u,
                     temp,sizeof(temp),output,sizeof(output),&n).status==BSR_OK);
    CHECK(runtime.state==BSR_IDLE && runtime.executor.while_depth==0u);
    for(i=0u;i<5u;++i)CHECK(put(&f,(unsigned int)(10u+i*10u),code[i])==0);
    CHECK(bsr_submit(&runtime,(const uint8_t*)"RUN",3u,
                     temp,sizeof(temp),output,sizeof(output),&n).status==BSR_OK);
    for(i=0u;i<6u;++i)
        CHECK(bsr_step(&runtime,output,sizeof(output),&n).status==BSR_OK);
    CHECK(bsr_step(&runtime,output,sizeof(output),&n).status==BSR_END);
    CHECK(runtime.state==BSR_IDLE && runtime.executor.while_depth==0u);
    return 0;
}
int main(int argc,char **argv)
{
    size_t i;
    CHECK(argc==2);
    CHECK(depth_tests()==0);
    CHECK(low_capacity()==0);
    CHECK(unsupported_and_malformed()==0);
    CHECK(colon_boundaries()==0);
    CHECK(session_resets()==0);
    for(i=0u;i<sizeof(cases)/sizeof(cases[0]);++i)
        CHECK(check_case(argv[1],&cases[i])==0);
    puts("J1.24-B2 20_CASES original+repeat; positive SEMANTIC only; "
         "5 typed failures incl DIAG_CONTRADICTORY; B1 lexical unchanged");
    return 0;
}
