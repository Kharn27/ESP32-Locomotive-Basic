/* J1.15-C: exercise the exact CYD arena initializer via portable runtime.
 * No ESP-IDF dependency: same header, entry count, arithmetics and slot quota.
 */
#include "basic_session_runtime.h"
#include "j1_15_c_string_arena.h"
#include <stdio.h>
#include <string.h>
#define CHECK(e) do { if (!(e)) { fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#e); return 1; } } while (0)

typedef struct {
    BasicProgram program;
    BasicVariableStore store;
    BasicSessionRuntime runtime;
    BasicVariableEntry entries[J115C_VARIABLES_CAPACITY];
    uint8_t arena[J115C_STRING_ARENA_CAPACITY];
    uint8_t program_bytes[8192];
    uint8_t temporary[2048];
    uint8_t output[4096];
    size_t written;
} CydFixture;
static CydFixture f; /* Like static firmware BasicStorage: no 4096-byte stack. */

static int setup(void)
{
    memset(&f,0,sizeof(f));
    CHECK(bp_init(&f.program,f.program_bytes,sizeof(f.program_bytes))==BP_OK);
    CHECK(j115c_init_store(&f.store,f.entries,J115C_VARIABLES_CAPACITY,
                           f.arena,sizeof(f.arena))==BVS_OK);
    CHECK(f.store.string_slot_bytes==J115C_STRING_SLOT_BYTES);
    CHECK(f.store.string_capacity==4096u);
    CHECK(bsr_init_with_store(&f.runtime,&f.program,&f.store).status==BSR_OK);
    return 0;
}
static BSRResult submit(const char *s)
{
    return bsr_submit(&f.runtime,(const uint8_t *)s,strlen(s),
                      f.temporary,sizeof(f.temporary),
                      f.output,sizeof(f.output),&f.written);
}
static int all_zero_arena(void)
{
    size_t i;
    for(i=0u;i<sizeof(f.arena);++i)
        if(f.arena[i]!=0u) return 0;
    return 1;
}
static int run_print(const char *expected)
{
    size_t event_count=0u,step;
    int saw_end=0;
    CHECK(submit("RUN").status==BSR_OK);
    CHECK(f.store.count==0u && all_zero_arena());
    for(step=0u;step<64u;++step) {
        BSRResult r=bsr_step(&f.runtime,f.output,sizeof(f.output),&f.written);
        if(r.status==BSR_END) {saw_end=1;break;}
        CHECK(r.status==BSR_OK && r.executor_status==BE_OK);
        if(f.written) {
            ++event_count;
            CHECK(event_count==1u);
            CHECK(f.written==strlen(expected)+1u);
            CHECK(memcmp(f.output,expected,strlen(expected))==0);
            CHECK(f.output[f.written-1u]=='\n');
        }
    }
    CHECK(saw_end && f.runtime.state==BSR_IDLE && event_count==1u);
    return 0;
}
static int bad_init_is_atomic(void)
{
    BasicVariableStore before;
    uint8_t old_entries[sizeof(f.entries)];
    uint8_t old_arena[sizeof(f.arena)];
    CHECK(setup()==0);
    before=f.store;
    memcpy(old_entries,f.entries,sizeof(old_entries));
    memcpy(old_arena,f.arena,sizeof(old_arena));
    CHECK(j115c_init_store(&f.store,f.entries,J115C_VARIABLES_CAPACITY,
                           f.arena,sizeof(f.arena)-1u)==BVS_INVALID_ARGUMENT);
    CHECK(j115c_init_store(&f.store,f.entries,J115C_VARIABLES_CAPACITY-1u,
                           f.arena,sizeof(f.arena))==BVS_INVALID_ARGUMENT);
    CHECK(memcmp(&before,&f.store,sizeof(before))==0);
    CHECK(memcmp(old_entries,f.entries,sizeof(old_entries))==0);
    CHECK(memcmp(old_arena,f.arena,sizeof(old_arena))==0);
    return 0;
}
static int hello_and_reassign(void)
{
    CHECK(setup()==0);
    CHECK(submit("10 A$=\"BONJOUR\"").status==BSR_OK);
    CHECK(submit("20 PRINT A$").status==BSR_OK);
    CHECK(submit("30 END").status==BSR_OK);
    CHECK(submit("LIST").status==BSR_OK);
    CHECK(f.written>0u);
    CHECK(run_print("BONJOUR")==0);
    CHECK(run_print("BONJOUR")==0); /* same store, no cumulative allocation */
    CHECK(submit("10 A$=\"SALUT\"").status==BSR_OK);
    CHECK(run_print("SALUT")==0);
    CHECK(submit("10 A$=\"\"").status==BSR_OK);
    CHECK(run_print("")==0); /* exactly one raw LF */
    CHECK(submit("10 A$=\"NOUVEAU\"").status==BSR_OK);
    CHECK(run_print("NOUVEAU")==0);
    CHECK(submit("NEW").status==BSR_OK);
    CHECK(f.store.count==0u && all_zero_arena());
    CHECK(submit("LIST").status==BSR_OK && f.written==0u);
    return 0;
}
static int slot_edges_and_error(void)
{
    char str[66],line[96];
    BasicVariableStore snapshot;
    size_t i;
    CHECK(setup()==0);
    for(i=0u;i<65u;++i)str[i]='X';
    str[64]='\0';
    CHECK(snprintf(line,sizeof(line),"10 A$=\"%s\"",str)>0);
    CHECK(submit(line).status==BSR_OK);
    CHECK(submit("20 PRINT A$").status==BSR_OK);
    CHECK(submit("30 END").status==BSR_OK);
    CHECK(run_print(str)==0);
    CHECK(submit("NEW").status==BSR_OK && all_zero_arena());
    str[64]='X';str[65]='\0';
    CHECK(snprintf(line,sizeof(line),"10 A$=\"%s\"",str)>0);
    CHECK(strlen(line)<120u); /* source UART editor capacity */
    CHECK(submit(line).status==BSR_OK);
    CHECK(submit("20 PRINT A$").status==BSR_OK);
    CHECK(submit("30 END").status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    snapshot=f.store;
    f.written=777u;
    {
        BSRResult r=bsr_step(&f.runtime,f.output,sizeof(f.output),&f.written);
        CHECK(r.status==BSR_EXECUTOR_ERROR && r.executor_status==BE_STORE_FULL);
    }
    CHECK(f.written==777u && f.store.count==0u && all_zero_arena());
    CHECK(memcmp(&snapshot,&f.store,sizeof(snapshot))==0);
    return 0;
}
static int integer_regression(void)
{
    size_t step,events=0u;
    int ended=0;
    CHECK(setup()==0);
    CHECK(submit("10 A%=1").status==BSR_OK);
    CHECK(submit("20 PRINT A%").status==BSR_OK);
    CHECK(submit("30 END").status==BSR_OK);
    CHECK(submit("RUN").status==BSR_OK);
    for(step=0u;step<16u;++step) {
        BSRResult r=bsr_step(&f.runtime,f.output,sizeof(f.output),&f.written);
        if(r.status==BSR_END){ended=1;break;}
        CHECK(r.status==BSR_OK && r.executor_status==BE_OK);
        if(f.written) {
            ++events;
            CHECK(memchr(f.output,'1',f.written)!=NULL);
            CHECK(f.output[f.written-1u]=='\n');
        }
    }
    CHECK(ended && events==1u && f.runtime.state==BSR_IDLE);
    return 0;
}
int main(void)
{
    CHECK(bad_init_is_atomic()==0);
    CHECK(hello_and_reassign()==0);
    CHECK(slot_edges_and_error()==0);
    CHECK(integer_regression()==0);
    printf("J1.15-C CYD_CONSOLE_ARENA=PASS slots=%d slot_bytes=%d arena_bytes=%d "
           "S64_PASS S65_ATOMIC_REJECT RUN_NEW_RESET EMPTY_REASSIGN INTEGER_PASS\n",
           J115C_VARIABLES_CAPACITY,J115C_STRING_SLOT_BYTES,
           J115C_STRING_ARENA_CAPACITY);
    return 0;
}
