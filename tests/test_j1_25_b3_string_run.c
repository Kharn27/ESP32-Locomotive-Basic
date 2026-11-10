/* J1.25-B3: native C99 bounded DATA/READ STRING and mixed INTEGER/STRING.
 * CPC captures are independent, immutable original/repeat observations.
 * BE statuses below are HOST causes, NEVER fabricated CPC ERR/ERL. */
#include "basic_session_runtime.h"
#include "basic_tokenizer.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "J1.25-B3 %s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)
enum { CAP = 2048 };
static const char *const names[3] = {"ONE_STRING","QUOTED_COMMA","MIXED_TYPES"};
static const char *const sessions[2] = {"original","repeat"};
static const char *const expected[3] = {"HELLO\n","A,B\n"," 3 \nZ\n"};

static int read_file(const char *path, uint8_t *dst, size_t capacity, size_t *length)
{
    FILE *f = fopen(path,"rb");
    size_t got;
    int tail;
    if (!f) { perror(path); return 1; }
    got = fread(dst,1u,capacity,f);
    tail = fgetc(f);
    if (ferror(f) || tail != EOF || fclose(f) != 0) return 1;
    *length = got;
    return 0;
}
static int store_program(const uint8_t *source, size_t length, BasicProgram *bp)
{
    size_t pos = 0u;
    while (pos < length) {
        size_t start = pos, index;
        unsigned int number = 0u;
        uint8_t tokens[CAP];
        size_t written = 0u;
        while (pos < length && source[pos] != (uint8_t)'\n') ++pos;
        if (pos == length) return 1;
        index = start;
        while (index < pos && source[index] >= (uint8_t)'0' &&
               source[index] <= (uint8_t)'9') {
            number = 10u * number + (unsigned int)(source[index++] - (uint8_t)'0');
            if (number > 65535u) return 1;
        }
        if (index >= pos || source[index++] != (uint8_t)' ' ||
            bt_tokenize(source + index, pos - index, tokens, sizeof(tokens),
                        &written) != BT_OK ||
            bp_put(bp, (uint16_t)number, tokens, written) != BP_OK) return 1;
        ++pos;
    }
    return 0;
}
static int sealed_prefix(const uint8_t *bytes, size_t length,
                         uint8_t *out, size_t capacity, size_t *written)
{
    static const char marker[] = "J125_DIAG_BEGIN\r\n";
    static const char diag[] = " 0 \r\n 0 \r\n";
    size_t stop = length, i, n = 0u;
    for (i = 0u; i + sizeof(marker)-1u <= length; ++i) {
        if (memcmp(bytes + i,marker,sizeof(marker)-1u) == 0) {
            stop = i;
            break;
        }
    }
    if (stop == length ||
        length - stop - (sizeof(marker)-1u) < sizeof(diag)-1u ||
        memcmp(bytes + stop + sizeof(marker)-1u,diag,sizeof(diag)-1u) != 0)
        return 1;
    for (i = 0u; i < stop; ++i) {
        if (bytes[i] == (uint8_t)'\r') {
            if (i+1u == stop || bytes[i+1u] != (uint8_t)'\n') return 1;
            continue;
        }
        if (n == capacity) return 1;
        out[n++] = bytes[i];
    }
    *written = n;
    return 0;
}
static int positive(const char *root, const char *name,
                    const char *session, const char *witness)
{
    char path[512];
    uint8_t source[CAP], oracle_raw[CAP], oracle[CAP], program_bytes[CAP];
    uint8_t arena[64], output[128], preview[128], scratch[128], native[CAP];
    BasicProgram bp;
    BasicVariableStore store;
    BasicVariableEntry entries[4];
    BasicSessionRuntime runtime;
    size_t source_len, raw_len, oracle_len, count = 0u, steps;
    size_t written = 999u;
    int n;
    BSRResult result;
    n=snprintf(path,sizeof(path),"%s/tests/oracles/inputs/j1_25_a/%s.bas",
               root,name);
    CHECK(n>0 && (size_t)n<sizeof(path));
    CHECK(read_file(path,source,sizeof(source),&source_len) == 0);
    n=snprintf(path,sizeof(path),
               "%s/tests/fixtures/cpc6128/j1_25_a_data_read_restore/%s/%s/run/printer.dat",
               root,session,name);
    CHECK(n>0 && (size_t)n<sizeof(path));
    CHECK(read_file(path,oracle_raw,sizeof(oracle_raw),&raw_len) == 0);
    CHECK(sealed_prefix(oracle_raw,raw_len,oracle,sizeof(oracle),&oracle_len) == 0);
    CHECK(strlen(witness)==oracle_len && memcmp(witness,oracle,oracle_len)==0);
    CHECK(bp_init(&bp,program_bytes,sizeof(program_bytes))==BP_OK);
    CHECK(store_program(source,source_len,&bp)==0);
    memset(entries,0xa5,sizeof(entries));
    CHECK(bvs_init_with_arena(&store,entries,4u,arena,sizeof(arena))==BVS_OK);
    CHECK(bsr_init_with_store(&runtime,&bp,&store).status==BSR_OK);
    result=bsr_submit(&runtime,(const uint8_t *)"RUN",3u,
                      scratch,sizeof(scratch),output,sizeof(output),&written);
    CHECK(result.status==BSR_OK && written==0u);
    for(steps=0u;steps<32u;++steps) {
        BasicSessionRuntime before=runtime;
        BasicVariableEntry frozen[4];
        uint8_t arena_copy[64];
        size_t p_written=777u, p_events=888u;
        BSRResult p;
        memcpy(frozen,entries,sizeof(entries));
        memcpy(arena_copy,arena,sizeof(arena));
        memset(preview,0xd2,sizeof(preview));
        p=bsr_preview_step_events(&runtime,preview,sizeof(preview),
                                  &p_written,NULL,0u,&p_events);
        CHECK(memcmp(&runtime,&before,sizeof(before))==0);
        CHECK(memcmp(entries,frozen,sizeof(entries))==0);
        CHECK(memcmp(arena,arena_copy,sizeof(arena))==0);
        if (p.status==BSR_END) {
            CHECK(p_written==777u && p_events==888u);
            break;
        }
        CHECK(p.status==BSR_OK && p_events==0u);
        written=999u;
        result=bsr_step(&runtime,output,sizeof(output),&written);
        CHECK(result.status==BSR_OK && p_written==written);
        CHECK(memcmp(preview,output,written)==0);
        CHECK(written<=sizeof(native)-count);
        memcpy(native+count,output,written);
        count+=written;
    }
    CHECK(steps<32u && count==oracle_len && memcmp(native,oracle,count)==0);
    if(strcmp(name,"MIXED_TYPES")==0) {
        CHECK(store.count==2u && entries[0].key.type==(uint8_t)BVT_INTEGER);
        CHECK(entries[0].value.data.integer==3);
        CHECK(entries[1].key.type==(uint8_t)BVT_STRING);
        CHECK(entries[1].value.data.string.length==1u);
        CHECK(arena[store.string_slot_bytes]=='Z');
    } else {
        size_t len=strlen(name[0]=='O' ? "HELLO" : "A,B");
        const char *word=name[0]=='O' ? "HELLO" : "A,B";
        CHECK(store.count==1u && entries[0].key.type==(uint8_t)BVT_STRING);
        CHECK(entries[0].value.data.string.length==len);
        CHECK(memcmp(arena,word,len)==0);
    }
    printf("B3 %-14s %-8s CPC_RUN_EXACT=%zu\n",name,session,count);
    return 0;
}
static int put_text(BasicProgram *bp, uint16_t line, const char *text)
{
    uint8_t tokens[256];
    size_t n=0u;
    if(bt_tokenize((const uint8_t *)text,strlen(text),tokens,sizeof(tokens),&n)
       != BT_OK) return 1;
    return bp_put(bp,line,tokens,n)!=BP_OK;
}
static BasicVariableKey key(char name, uint8_t type)
{
    BasicVariableKey k={0};
    k.type=type; k.name_length=1u; k.name[0]=(uint8_t)name;
    return k;
}
/* All metadata, arena bytes (including capacity tail), program bytes,
 * executor, print buffers and output counters must survive a refused READ. */
static int refusal(const char *data, const char *read,
                   size_t entries_cap, size_t arena_bytes,
                   int preload, BEStatus expected_status)
{
    uint8_t program_mem[512], arena[64], output[32], copy[32];
    BasicProgram bp;
    BasicExecutor ex, snapshot;
    BasicVariableStore store, store_copy;
    BasicVariableEntry entries[2], entries_copy[2];
    uint8_t arena_copy[64], program_copy[512];
    size_t written=973u, events=947u;
    BEStatus status;
    CHECK(bp_init(&bp,program_mem,sizeof(program_mem))==BP_OK);
    CHECK(put_text(&bp,10u,data)==0 && put_text(&bp,20u,read)==0);
    memset(arena,0xd3,sizeof(arena));
    CHECK(bvs_init_with_arena(&store,entries,entries_cap,arena,arena_bytes)
          ==BVS_OK);
    if (preload==1) {
        BasicVariableKey k=key('A',(uint8_t)BVT_INTEGER);
        BasicVariableValue v={0};
        v.type=(uint8_t)BVT_INTEGER; v.data.integer=9;
        CHECK(bvs_assign(&store,&k,&v)==BVS_OK);
    } else if (preload==2) {
        BasicVariableKey k=key('A',(uint8_t)BVT_STRING);
        CHECK(bvs_assign_string(&store,&k,(const uint8_t *)"OLD",3u)==BVS_OK);
    }
    CHECK(be_init_with_store(&ex,&bp,&store)==BE_OK);
    written=973u;
    CHECK(be_step(&ex,output,sizeof(output),&written)==BE_OK);
    snapshot=ex; store_copy=store;
    memcpy(entries_copy,entries,sizeof(entries));
    memcpy(arena_copy,arena,sizeof(arena));
    memcpy(program_copy,program_mem,sizeof(program_mem));
    memset(output,0x6a,sizeof(output));
    memcpy(copy,output,sizeof(copy));
    written=973u;
    status=be_preview_step_events(&ex,output,sizeof(output),&written,
                                  NULL,0u,&events);
    CHECK(status==expected_status);
    CHECK(events==947u && written==973u);
    CHECK(memcmp(&ex,&snapshot,sizeof(ex))==0 &&
          memcmp(&store,&store_copy,sizeof(store))==0 &&
          memcmp(entries,entries_copy,sizeof(entries))==0 &&
          memcmp(arena,arena_copy,sizeof(arena))==0 &&
          memcmp(program_mem,program_copy,sizeof(program_mem))==0 &&
          memcmp(output,copy,sizeof(copy))==0);
    status=be_step(&ex,output,sizeof(output),&written);
    CHECK(status==expected_status && written==973u);
    CHECK(memcmp(&ex,&snapshot,sizeof(ex))==0 &&
          memcmp(&store,&store_copy,sizeof(store))==0 &&
          memcmp(entries,entries_copy,sizeof(entries))==0 &&
          memcmp(arena,arena_copy,sizeof(arena))==0 &&
          memcmp(program_mem,program_copy,sizeof(program_mem))==0 &&
          memcmp(output,copy,sizeof(copy))==0);
    return 0;
}
static int special_refusals(void)
{
    uint8_t program_mem[512],arena[16],output[32],frozen[32],raw[16];
    BasicProgram bp;
    BasicExecutor ex,before;
    BasicVariableStore store;
    BasicVariableEntry entries[2],snapshot[2];
    size_t written=71u, events=76u;
    static const uint8_t open_quote[]={0x8cu,' ','"','O','P','E','N'};
    /* Tokenizer-independent truncated quote, no mutation even in DATA step. */
    CHECK(bp_init(&bp,program_mem,sizeof(program_mem))==BP_OK);
    CHECK(bp_put(&bp,10u,open_quote,sizeof(open_quote))==BP_OK);
    CHECK(bvs_init_with_arena(&store,entries,2u,arena,sizeof(arena))==BVS_OK);
    CHECK(be_init_with_store(&ex,&bp,&store)==BE_OK);
    before=ex; memcpy(snapshot,entries,sizeof(entries));
    memcpy(raw,arena,sizeof(raw));
    memset(output,0x19,sizeof(output)); memcpy(frozen,output,sizeof(output));
    CHECK(be_step(&ex,output,sizeof(output),&written)==BE_TRUNCATED);
    CHECK(memcmp(&ex,&before,sizeof(ex))==0 &&
          memcmp(entries,snapshot,sizeof(entries))==0 &&
          memcmp(arena,raw,sizeof(raw))==0 &&
          memcmp(output,frozen,sizeof(output))==0 && written==71u);
    /* Successful READ, then undersized PRINT: text and cursor unchanged. */
    CHECK(bp_init(&bp,program_mem,sizeof(program_mem))==BP_OK);
    CHECK(put_text(&bp,10u,"DATA 3,\"Z\"")==0);
    CHECK(put_text(&bp,20u,"READ A%,B$")==0);
    CHECK(put_text(&bp,30u,"PRINT #8,B$")==0);
    CHECK(bvs_init_with_arena(&store,entries,2u,arena,sizeof(arena))==BVS_OK);
    CHECK(be_init_with_store(&ex,&bp,&store)==BE_OK);
    CHECK(be_step(&ex,output,sizeof(output),&written)==BE_OK);
    CHECK(be_step(&ex,output,sizeof(output),&written)==BE_OK);
    before=ex; memcpy(snapshot,entries,sizeof(entries));
    memcpy(raw,arena,sizeof(raw));
    memset(output,0x33,sizeof(output));
    CHECK(be_step(&ex,output,1u,&written)==BE_NO_SPACE);
    CHECK(memcmp(&ex,&before,sizeof(ex))==0 &&
          memcmp(entries,snapshot,sizeof(entries))==0 &&
          memcmp(arena,raw,sizeof(raw))==0 &&
          output[0]==0x33);
    /* Source/program/store/output alias attempts fail before any write. */
    CHECK(bp_init(&bp,program_mem,sizeof(program_mem))==BP_OK);
    CHECK(put_text(&bp,10u,"DATA \"Z\"")==0);
    CHECK(put_text(&bp,20u,"READ A$")==0);
    CHECK(bvs_init_with_arena(&store,entries,2u,arena,sizeof(arena))==BVS_OK);
    CHECK(be_init_with_store(&ex,&bp,&store)==BE_OK);
    CHECK(be_step(&ex,output,sizeof(output),&written)==BE_OK);
    before=ex; memcpy(snapshot,entries,sizeof(entries));
    memcpy(raw,arena,sizeof(raw));
    written=71u; events=76u;
    CHECK(be_preview_step_events(&ex,arena,sizeof(arena),&written,
                                 NULL,0u,&events)==BE_OVERLAP);
    CHECK(be_step(&ex,arena,sizeof(arena),&written)==BE_OVERLAP);
    CHECK(written==71u && events==76u &&
          memcmp(&ex,&before,sizeof(ex))==0 &&
          memcmp(entries,snapshot,sizeof(entries))==0 &&
          memcmp(arena,raw,sizeof(raw))==0);
    return 0;
}
static int negatives(void)
{
    CHECK(refusal("DATA 3,\"TOOLONG\"","READ A%,B$",2u,8u,1,BE_STORE_FULL)==0);
    CHECK(refusal("DATA 3,\"Z\"","READ A%,B$",1u,8u,1,BE_STORE_FULL)==0);
    CHECK(refusal("DATA 3","READ A%,B$",2u,16u,1,BE_DATA_EXHAUSTED)==0);
    CHECK(refusal("DATA 3,4","READ A%,B$",2u,16u,1,BE_UNSUPPORTED)==0);
    CHECK(refusal("DATA \"Z\"","READ A%",2u,16u,0,BE_UNSUPPORTED)==0);
    CHECK(refusal("DATA 3","READ A$",2u,16u,2,BE_UNSUPPORTED)==0);
    CHECK(refusal("DATA \"TOOLONG\"","READ A$",2u,8u,2,BE_STORE_FULL)==0);
    CHECK(refusal("DATA 1,2","READ A%,A%",2u,16u,1,BE_UNSUPPORTED)==0);
    CHECK(refusal("DATA \"X\",2","READ A$,B%",2u,16u,2,BE_UNSUPPORTED)==0);
    CHECK(refusal("DATA \"X\",\"Y\"","READ A$,B$",2u,16u,2,BE_UNSUPPORTED)==0);
    CHECK(refusal("DATA \"Z\"","READ B$",2u,16u,0,BE_UNSUPPORTED)==0);
    CHECK(special_refusals()==0);
    puts("B3 atomic negatives: capacity/arena/type/exhaustion/quotes/alias/output PASS");
    return 0;
}
int main(int argc,char **argv)
{
    size_t i,j;
    CHECK(argc==2);
    CHECK(negatives()==0);
    for(i=0u;i<3u;++i)
        for(j=0u;j<2u;++j)
            CHECK(positive(argv[1],names[i],sessions[j],expected[i])==0);
    puts("J1.25-B3 3/3 original/repeat CPC RUN EXACT");
    return 0;
}
