/* J1.20-B1: exact CPC RAM oracle + semantic LIST only, never RUN ABS.
 * Reads the two immutable J1.20-A acquisitions, no synthesized oracle. */
#include "basic_program.h"
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_session.h"
#include "basic_executor.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "ABS-B1 %s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

static const char *const names[] = {
    "a00","a01","an1","v07","vn7","vmax","vnmax","vmin",
    "b07","bn7","bmin","imin","l20","empty","string","multi"
};

static int load(const char *path, uint8_t *data, size_t cap, size_t *n)
{
    FILE *f = fopen(path, "rb");
    size_t count;
    int more;
    if (!f) { fprintf(stderr, "Missing sealed witness: %s\n", path); return 1; }
    count = fread(data, 1u, cap, f);
    more = fgetc(f);
    if (ferror(f) || more != EOF || count == 0u) {
        fclose(f); return 1;
    }
    fclose(f);
    *n = count;
    return 0;
}

/* A single genuine stored FF00 expression is fed to the unchanged executor,
 * with cursor/output/count and storage snapshot verified on failure. */
static int run_initial_abs(const BasicProgram *whole, const char *name)
{
    BasicProgram isolated;
    BasicExecutor executor, before;
    uint8_t storage[256], backup[256], output[64];
    size_t cursor = 0u, written = 71u;
    BasicProgramLine line;
    BPStatus ps;
    int found = 0;
    CHECK(bp_init(&isolated, storage, sizeof(storage)) == BP_OK);
    while ((ps = bp_next(whole, &cursor, &line)) == BP_OK) {
        const uint8_t *body = whole->data + line.body_offset;
        size_t i;
        for (i = 0; i + 1u < line.body_length; ++i) {
            if (body[i] == 0xffu && body[i + 1u] == 0x00u) {
                found = 1;
                CHECK(bp_put(&isolated, 10u, body, line.body_length) == BP_OK);
                break;
            }
        }
        if (found) break;
    }
    CHECK(found && ps == BP_OK);
    CHECK(be_init(&executor, &isolated) == BE_OK);
    before = executor;
    memcpy(backup, storage, sizeof(storage));
    memset(output, 0x6a, sizeof(output));
    {
        BEStatus result = be_step(&executor, output, sizeof(output), &written);
        size_t i;
        if (strcmp(name, "a00") == 0 || strcmp(name, "a01") == 0 ||
            strcmp(name, "an1") == 0) {
            /* B2a RED: first non-#8 PRINT ABS literal is now executable.
             * CPC LF differs from printer transport CRLF. */
            const char *want = strcmp(name, "a00") == 0 ? " 0 \n" : " 1 \n";
            CHECK(result == BE_OK);
            CHECK(written == 4u && memcmp(output, want, 4u) == 0);
            CHECK(executor.cursor != before.cursor);
            for (i = 4u; i < sizeof(output); ++i)
                CHECK(output[i] == 0x6au);
        } else {
            CHECK(result != BE_OK && result != BE_END);
            CHECK(result == BE_UNSUPPORTED || result == BE_UNKNOWN_TOKEN ||
                  result == BE_BAD_SEQUENCE || result == BE_TRUNCATED);
            CHECK(memcmp(&before, &executor, sizeof(executor)) == 0);
            CHECK(written == 71u);
            for (i = 0u; i < sizeof(output); ++i)
                CHECK(output[i] == 0x6au);
        }
        CHECK(memcmp(storage, backup, sizeof(storage)) == 0);
    }
    return 0;
}

static int each_oracle(const char *root, const char *name)
{
    char path[400];
    uint8_t source[1024], original[1024], repeat[1024];
    uint8_t storage[2048], tokens[1024], output[2048], rendered[2048];
    uint8_t import_storage[2048], snap[2048];
    size_t src_len, n_original, n_repeat, generated, listed, sent = 123u;
    BasicProgram program, imported;
    char *line, *end;
    CHECK(snprintf(path, sizeof(path), "%s/tests/oracles/inputs/j1_20_a/%s.bas",
                   root, name) > 0);
    CHECK(load(path, source, sizeof(source)-1u, &src_len) == 0);
    CHECK(source[src_len-1u] == '\n');
    source[src_len] = '\0';
    CHECK(bp_init(&program, storage, sizeof(storage)) == BP_OK);
    line = (char *)source;
    while (*line) {
        BSResult result;
        end = strchr(line, '\n');
        CHECK(end != NULL);
        CHECK(end > line);
        result = bs_process_line(&program, (const uint8_t *)line,
                                 (size_t)(end-line), tokens, sizeof(tokens),
                                 output, sizeof(output), &sent);
        if (result.status != BS_OK) {
            fprintf(stderr, "ABS B1 %s rejected: '%.*s' BS=%d BT=%d\n",
                    name, (int)(end-line), line, (int)result.status,
                    (int)result.tokenizer_status);
            return 1;
        }
        line = end+1;
    }
    CHECK(snprintf(path, sizeof(path),
                   "%s/tests/fixtures/cpc6128/j1_20_a_abs/original/%s/program.bin",
                   root, name) > 0);
    {
        size_t i;
        /* Oracle uses uppercase directory IDs, unlike lower-case filenames. */
        char *at = strstr(path, "/original/");
        CHECK(at != NULL);
        at += strlen("/original/");
        for (i = 0u; i < strlen(name); ++i)
            if (at[i] >= 'a' && at[i] <= 'z')
                at[i] = (char)(at[i] - 'a' + 'A');
    }
    CHECK(load(path, original, sizeof(original), &n_original) == 0);
    {
        char case_id[16];
        size_t i;
        CHECK(strlen(name) < sizeof(case_id));
        for (i = 0u; i < strlen(name); ++i) {
            char c=name[i];
            case_id[i]=(char)((c>='a' && c<='z') ? c-'a'+'A' : c);
        }
        case_id[strlen(name)]='\0';
        CHECK(snprintf(path, sizeof(path),
                       "%s/tests/fixtures/cpc6128/j1_20_a_abs/repeat/%s/program.bin",
                       root, case_id) > 0);
    }
    CHECK(load(path, repeat, sizeof(repeat), &n_repeat) == 0);
    CHECK(n_original == n_repeat && memcmp(original, repeat, n_original) == 0);
    CHECK(bp_export(&program, output, sizeof(output), &generated) == BP_OK);
    if (generated != n_original || memcmp(output, original, n_original) != 0) {
        size_t i;
        fprintf(stderr, "ABS B1 RAM DIFF: %s native=%lu CPC=%lu\n", name,
                (unsigned long)generated, (unsigned long)n_original);
        for (i=0u;i<generated && i<n_original;++i)
            if (output[i]!=original[i]) {
                fprintf(stderr," offset %lu: native=%02X CPC=%02X\n",
                        (unsigned long)i,output[i],original[i]); break;
            }
        return 1;
    }
    CHECK(bl_list_program(&program, rendered, sizeof(rendered), &listed) == BL_OK);
    CHECK(listed == src_len && memcmp(rendered, source, src_len) == 0);
    /* Imported original CPC image LIST should be equally semantic. */
    CHECK(bp_init(&imported, import_storage, sizeof(import_storage)) == BP_OK);
    CHECK(bp_import(&imported, original, n_original) == BP_OK);
    CHECK(bl_list_program(&imported, rendered, sizeof(rendered), &listed) == BL_OK);
    CHECK(listed == src_len && memcmp(rendered, source, src_len) == 0);
    /* Atomic listing on a buffer one byte too small; no sentinel corruption. */
    memset(rendered, 0x7cu, sizeof(rendered));
    sent = 112u;
    CHECK(bl_list_program(&program, rendered, src_len-1u, &sent) == BL_NO_SPACE);
    CHECK(sent == 112u);
    for (generated = 0u; generated < sizeof(rendered); ++generated)
        CHECK(rendered[generated] == 0x7cu);
    /* Imported RAM is immutable across unsupported RUN and repeat listing. */
    memcpy(snap, import_storage, sizeof(snap));
    CHECK(run_initial_abs(&imported, name) == 0);
    CHECK(memcmp(snap, import_storage, sizeof(snap)) == 0);
    printf("ABS-B1 %s MATCH_EXACT_RAM original+repeat MATCH_SEMANTIC_LIST "
           "RUN_HOST_UNSUPPORTED\n", name);
    return 0;
}

static int negatives(void)
{
    static const char *const invalid[] = {
        "PRINT ABS(2)", "PRINT ABS(32768)", "PRINT ABS(-32769)",
        "?ABS(2)", "?ABS(ABS(1))", "?ABS(1)+1", "PRINTABS(1)",
        "PRINT ABS(A%+1)", "PRINT ABS(ABS(1))", "PRINT ABS(-32768+1)",
        "PRINT ABS(1,3)", "PRINT ABS(1,2,3)", "PRINT ABS(\"Y\")",
        "PRINT ABS(B%)", "PRINT SGN(1)", "PRINT SQR(1)",
        "PRINT #9,ABS(1)", "PRINT #8,3", "PRINT #8,AA%",
        "C%=ABS(A%)", "B%=ABS(-32768)", "B%=ABS()", "B%=ABS(\"X\")",
        "PRINT ABS(1):END", "PRINT ABS", "PRINT ABSX(1)",
        "PRINT ABS(A%):PRINT 1", "PRINT #8", "PRINT #8,ABS(0)+1"
    };
    size_t i;
    for (i=0u;i<sizeof(invalid)/sizeof(invalid[0]);++i) {
        uint8_t out[128], saved[128];
        size_t written=97u;
        memset(out,0xa5,sizeof(out));
        memcpy(saved,out,sizeof(out));
        if (bt_tokenize((const uint8_t *)invalid[i],strlen(invalid[i]),
                        out,sizeof(out),&written) == BT_OK) {
            fprintf(stderr, "Unsealed ABS lexical form accepted: %s\n", invalid[i]);
            return 1;
        }
        CHECK(written==97u && memcmp(out,saved,sizeof(out))==0);
    }
    {
        static const uint8_t valid[] = {
            0xbfu,' ',0xffu,0x00u,'(',0xf5u,0x1fu,0u,0u,0u,0u,0x90u,')'
        };
        uint8_t tokens[128], saved[128], list[128];
        size_t written=77u;
        size_t n=sizeof(valid);
        CHECK(bt_tokenize((const uint8_t *)"PRINT ABS(-32768)",17u,
                          tokens,n-1u,&written)==BT_NO_SPACE);
        CHECK(written==77u);
        memset(tokens,0x55,sizeof(tokens));
        memcpy(saved,tokens,sizeof(saved));
        CHECK(bt_tokenize((const uint8_t *)"PRINT ABS(-32768)",17u,
                          tokens,0u,&written)==BT_NO_SPACE);
        CHECK(written==77u && memcmp(tokens,saved,sizeof(tokens))==0);
        CHECK(bl_detokenize(valid,sizeof(valid),list,1u,&written)==BL_NO_SPACE);
        CHECK(written==77u);
        for (i=0u;i<sizeof(valid);++i) {
            uint8_t bad[sizeof(valid)];
            size_t len=77u;
            memcpy(bad,valid,sizeof(bad));
            if (i==0u || i==1u || i==3u || i==7u || i==11u)
                bad[i]^=0x01u;
            else continue;
            memset(list,0x59,sizeof(list));
            memcpy(saved,list,sizeof(list));
            CHECK(bl_detokenize(bad,sizeof(bad),list,sizeof(list),&len)!=BL_OK);
            CHECK(len==77u && memcmp(list,saved,sizeof(list))==0);
        }
        CHECK(n==13u);
    }
    return 0;
}

/* A failed line must never partially mutate the existing BASIC program,
 * its exported bytes, output region, nor the caller's count. */
static int program_atomicity(void)
{
    BasicProgram p, tiny;
    uint8_t storage[128], saved[128], tiny_storage[8], tiny_saved[8];
    uint8_t temporary[128], output[128], out_saved[128];
    size_t count = 74u;
    BSResult result;
    static const uint8_t body[] = {0xbfu,' ',0xffu,0u,'(',0x0fu,')'};
    static const char invalid[] = "20 PRINT ABS(2)";
    static const char valid[] = "10 PRINT ABS(1)";
    CHECK(bp_init(&p, storage, sizeof(storage)) == BP_OK);
    CHECK(bp_put(&p, 10u, body, sizeof(body)) == BP_OK);
    memcpy(saved, storage, sizeof(saved));
    memset(output, 0x5cu, sizeof(output));
    memcpy(out_saved, output, sizeof(output));
    result = bs_process_line(&p, (const uint8_t *)invalid, strlen(invalid),
                             temporary, sizeof(temporary), output,
                             sizeof(output), &count);
    CHECK(result.status == BS_TOKENIZER_ERROR);
    CHECK(count == 74u && p.size == sizeof(body)+7u);
    CHECK(memcmp(saved, storage, sizeof(saved)) == 0);
    CHECK(memcmp(output, out_saved, sizeof(output)) == 0);
    CHECK(bp_put(&p, 0u, body, sizeof(body)) == BP_INVALID_LINE_NUMBER);
    CHECK(memcmp(saved, storage, sizeof(saved)) == 0);

    CHECK(bp_init(&tiny, tiny_storage, sizeof(tiny_storage)) == BP_OK);
    memcpy(tiny_saved, tiny_storage, sizeof(tiny_saved));
    result = bs_process_line(&tiny, (const uint8_t *)valid, strlen(valid),
                             temporary, sizeof(temporary), output,
                             sizeof(output), &count);
    CHECK(result.status == BS_PROGRAM_ERROR &&
          result.program_status == BP_NO_SPACE);
    CHECK(tiny.size == 2u && memcmp(tiny_storage,tiny_saved,
                                    sizeof(tiny_storage)) == 0);
    CHECK(count == 74u && memcmp(output, out_saved, sizeof(output)) == 0);
    /* No truncation or magic wrapping of BASIC line numbers. */
    result = bs_process_line(&p,(const uint8_t *)"65536 PRINT ABS(1)",
                             strlen("65536 PRINT ABS(1)"),
                             temporary,sizeof(temporary),output,
                             sizeof(output),&count);
    CHECK(result.status != BS_OK);
    CHECK(memcmp(saved,storage,sizeof(saved)) == 0);
    CHECK(memcmp(output,out_saved,sizeof(output)) == 0 && count == 74u);
    return 0;
}

/* J1.20-B1-C1: reproduce the P2 alias without overwriting the CPC oracle.
 * '?' stores BF FF00, while the re-enterable PRINT ABS spelling stores
 * BF 20 FF00.  For aliases the semantic round-trip is exact but raw RAM
 * differs by one required separator.  This conflict is left to Pilotage. */
static int alias_list_roundtrip(void)
{
    static const struct {
        const char *source;
        const char *listed;
        int compact_alias;
    } cases[] = {
        {"10 ?ABS(1)",       "10 PRINT ABS(1)\n",       1},
        {"10 ?ABS(-1)",      "10 PRINT ABS(-1)\n",      1},
        {"10 ?ABS(A%)",      "10 PRINT ABS(A%)\n",      1},
        {"10 ?ABS(-32768)",  "10 PRINT ABS(-32768)\n",  1},
        {"10 ? ABS(1)",      "10 PRINT ABS(1)\n",       0},
        {"10 PRINT ABS(1)",  "10 PRINT ABS(1)\n",       0},
        {"10 PRINT  ABS(1)", "10 PRINT  ABS(1)\n",      0},
        {"10 PRINT #8,ABS(1)", "10 PRINT #8,ABS(1)\n",  0}
    };
    size_t i;
    for (i = 0u; i < sizeof(cases)/sizeof(cases[0]); ++i) {
        BasicProgram original, reentered, tiny;
        BasicProgramLine before, after;
        uint8_t store[256], restored[256], tiny_store[8], tiny_saved[8];
        uint8_t tokens[256], output[256], list[256], saved_list[256];
        uint8_t ram[256], roundtrip[256], saved_ram[256];
        size_t written = 77u, ram_len, restored_len, listed_len;
        size_t cur = 0u, cur2 = 0u, j;
        BSResult result;
        CHECK(bp_init(&original, store, sizeof(store)) == BP_OK);
        result = bs_process_line(&original, (const uint8_t *)cases[i].source,
                                 strlen(cases[i].source),
                                 tokens, sizeof(tokens), output,
                                 sizeof(output), &written);
        CHECK(result.status == BS_OK);
        CHECK(bp_export(&original, ram, sizeof(ram), &ram_len) == BP_OK);
        memcpy(saved_ram, ram, sizeof(ram));
        CHECK(bl_list_program(&original, list, sizeof(list), &listed_len) == BL_OK);
        if (listed_len != strlen(cases[i].listed) ||
            memcmp(list, cases[i].listed, listed_len) != 0) {
            fprintf(stderr, "C1 RED: source <%s> LIST got <%.*s> expected <%s>\n",
                    cases[i].source, (int)listed_len, list, cases[i].listed);
            return 1;
        }
        /* Two-pass atomic LIST, including a one-byte-short buffer. */
        memset(list, 0x7cu, sizeof(list));
        memcpy(saved_list, list, sizeof(list));
        written = 88u;
        CHECK(bl_list_program(&original, list, listed_len - 1u, &written) == BL_NO_SPACE);
        CHECK(written == 88u && memcmp(list, saved_list, sizeof(list)) == 0);
        CHECK(bl_list_program(&original, list, sizeof(list), &listed_len) == BL_OK);
        CHECK(bp_init(&reentered, restored, sizeof(restored)) == BP_OK);
        result = bs_process_line(&reentered, list, listed_len - 1u,
                                 tokens, sizeof(tokens), output,
                                 sizeof(output), &written);
        CHECK(result.status == BS_OK);
        CHECK(bp_export(&reentered, roundtrip, sizeof(roundtrip),
                        &restored_len) == BP_OK);
        CHECK(bp_next(&original, &cur, &before) == BP_OK);
        CHECK(bp_next(&reentered, &cur2, &after) == BP_OK);
        CHECK(before.number == after.number);
        if (cases[i].compact_alias) {
            /* Document the one-byte contradiction without altering CPC
             * image fixtures or tokenization of accepted PRINT witnesses. */
            const uint8_t *left = original.data + before.body_offset;
            const uint8_t *right = reentered.data + after.body_offset;
            CHECK(after.body_length == before.body_length + 1u);
            CHECK(left[0] == 0xbfu && left[1] == 0xffu && left[2] == 0u);
            CHECK(right[0] == 0xbfu && right[1] == (uint8_t)' ' &&
                  right[2] == 0xffu && right[3] == 0u);
            CHECK(memcmp(left + 1u, right + 2u, before.body_length - 1u) == 0);
            CHECK(restored_len == ram_len + 1u);
        } else {
            CHECK(restored_len == ram_len);
            CHECK(memcmp(ram, roundtrip, ram_len) == 0);
        }
        CHECK(memcmp(ram, saved_ram, sizeof(ram)) == 0);
        /* Storing in too-small BASIC RAM must preserve every byte. */
        CHECK(bp_init(&tiny, tiny_store, sizeof(tiny_store)) == BP_OK);
        memcpy(tiny_saved, tiny_store, sizeof(tiny_store));
        written = 99u;
        memset(output, 0x5cu, sizeof(output));
        result = bs_process_line(&tiny, (const uint8_t *)cases[i].source,
                                 strlen(cases[i].source), tokens, sizeof(tokens),
                                 output, sizeof(output), &written);
        CHECK(result.status == BS_PROGRAM_ERROR &&
              result.program_status == BP_NO_SPACE);
        CHECK(written == 99u &&
              memcmp(tiny_store, tiny_saved, sizeof(tiny_store)) == 0);
        for (j = 0u; j < sizeof(output); ++j)
            CHECK(output[j] == 0x5cu);
    }
    puts("C1 alias LIST re-enterable; exact raw-RAM delta=1 for compact '?' (Pilotage arbitration)");
    return 0;
}


/* J1.20-B2a: existing ABS CTest, no new build registration or oracle edits.
 * A%-sourced values ±7/±32767 are the only currently tokenized forms.
 * No PRINT #8 emulation and no CPC diagnostic equivalence claim. */
typedef struct {
    BasicProgram program;
    uint8_t program_bytes[256];
    BasicVariableStore store;
    BasicVariableEntry entries[2];
    BasicExecutor executor;
    uint8_t output[64];
    size_t written;
} AbsHarness;

static int abs_prepare(AbsHarness *h, const char *statement, size_t capacity)
{
    uint8_t body[128];
    size_t n=0u;
    memset(h, 0, sizeof(*h));
    CHECK(bp_init(&h->program,h->program_bytes,sizeof(h->program_bytes))==BP_OK);
    CHECK(bt_tokenize((const uint8_t *)statement,strlen(statement),
                      body,sizeof(body),&n)==BT_OK);
    CHECK(bp_put(&h->program,10u,body,n)==BP_OK);
    CHECK(capacity<=2u);
    CHECK(bvs_init(&h->store,capacity ? h->entries : NULL,capacity)==BVS_OK);
    CHECK(be_init_with_store(&h->executor,&h->program,&h->store)==BE_OK);
    return 0;
}

static int abs_seed(AbsHarness *h, const char *name, int16_t v)
{
    BasicVariableKey key={0};
    BasicVariableValue value={0};
    key.type=(uint8_t)BVT_INTEGER;
    key.name_length=(uint8_t)strlen(name);
    CHECK(key.name_length==1u);
    key.name[0]=(uint8_t)name[0];
    value.type=(uint8_t)BVT_INTEGER;
    value.data.integer=v;
    CHECK(bvs_assign(&h->store,&key,&value)==BVS_OK);
    return 0;
}

static int abs_assert_b(AbsHarness *h, int16_t expected)
{
    BasicVariableKey key={0};
    BasicVariableValue value={0};
    key.type=(uint8_t)BVT_INTEGER;
    key.name_length=1u;
    key.name[0]=(uint8_t)'B';
    CHECK(bvs_get(&h->store,&key,&value)==BVS_OK);
    CHECK(value.type==(uint8_t)BVT_INTEGER);
    CHECK(value.data.integer==expected);
    return 0;
}

/* Rejected steps, including PREVIEW, preserve all owners and public outputs.
 * The program capacity and unoccupied store entries are compared too. */
static int abs_rejected(AbsHarness *h, BEStatus expected, size_t capacity)
{
    BasicProgram p=h->program;
    BasicVariableStore v=h->store;
    BasicExecutor e=h->executor;
    BasicVariableEntry entries[2];
    uint8_t bytes[sizeof(h->program_bytes)];
    uint8_t old_output[sizeof(h->output)];
    size_t n=797u, event_count=799u;
    memcpy(entries,h->entries,sizeof(entries));
    memcpy(bytes,h->program_bytes,sizeof(bytes));
    memset(h->output,0x71,sizeof(h->output));
    memcpy(old_output,h->output,sizeof(old_output));
    CHECK(be_preview_step_events(&h->executor,h->output,capacity,
                                  &n,NULL,0u,&event_count)==expected);
    CHECK(n==797u && event_count==799u);
    CHECK(memcmp(&p,&h->program,sizeof(p))==0);
    CHECK(memcmp(&v,&h->store,sizeof(v))==0);
    CHECK(memcmp(&e,&h->executor,sizeof(e))==0);
    CHECK(memcmp(entries,h->entries,sizeof(entries))==0);
    CHECK(memcmp(bytes,h->program_bytes,sizeof(bytes))==0);
    CHECK(memcmp(old_output,h->output,sizeof(old_output))==0);
    CHECK(be_step(&h->executor,h->output,capacity,&n)==expected);
    CHECK(n==797u);
    CHECK(memcmp(&p,&h->program,sizeof(p))==0);
    CHECK(memcmp(&v,&h->store,sizeof(v))==0);
    CHECK(memcmp(&e,&h->executor,sizeof(e))==0);
    CHECK(memcmp(entries,h->entries,sizeof(entries))==0);
    CHECK(memcmp(bytes,h->program_bytes,sizeof(bytes))==0);
    CHECK(memcmp(old_output,h->output,sizeof(old_output))==0);
    return 0;
}

static int abs_native_green(void)
{
    static const struct {
        const char *source;
        int with_a, assignment;
        int16_t a, value;
        const char *print;
    } cases[]={
        {"PRINT ABS(0)",0,0,0,0," 0 \n"},
        {"PRINT ABS(1)",0,0,0,1," 1 \n"},
        {"PRINT ABS(-1)",0,0,0,1," 1 \n"},
        {"PRINT ABS(A%)",1,0,0,0," 0 \n"},
        {"PRINT ABS(A%)",1,0,7,7," 7 \n"},
        {"PRINT ABS(A%)",1,0,-7,7," 7 \n"},
        {"PRINT ABS(A%)",1,0,32767,32767," 32767 \n"},
        {"PRINT ABS(A%)",1,0,-32767,32767," 32767 \n"},
        {"B%=ABS(A%)",1,1,7,7,""},
        {"B%=ABS(A%)",1,1,-7,7,""}
    };
    size_t i;
    for (i=0u;i<sizeof(cases)/sizeof(cases[0]);++i) {
        AbsHarness h;
        BasicExecutor initial;
        BasicVariableStore prior_store;
        BasicVariableEntry prior_entries[2];
        uint8_t initial_program[sizeof(h.program_bytes)];
        uint8_t preview[64], committed[64];
        size_t n=211u, event_count=213u;
        size_t want=strlen(cases[i].print);
        CHECK(abs_prepare(&h,cases[i].source,2u)==0);
        if (cases[i].with_a) CHECK(abs_seed(&h,"A",cases[i].a)==0);
        initial=h.executor;
        prior_store=h.store;
        memcpy(prior_entries,h.entries,sizeof(prior_entries));
        memcpy(initial_program,h.program_bytes,sizeof(initial_program));
        memset(preview,0x55,sizeof(preview));
        CHECK(be_preview_step_events(&h.executor,preview,sizeof(preview),
                                     &n,NULL,0u,&event_count)==BE_OK);
        CHECK(n==want && event_count==0u);
        CHECK(memcmp(preview,cases[i].print,want)==0);
        CHECK(memcmp(&h.executor,&initial,sizeof(initial))==0);
        CHECK(memcmp(&h.store,&prior_store,sizeof(prior_store))==0);
        CHECK(memcmp(h.entries,prior_entries,sizeof(prior_entries))==0);
        CHECK(memcmp(h.program_bytes,initial_program,sizeof(initial_program))==0);
        memset(committed,0x66,sizeof(committed));
        n=214u;
        CHECK(be_step(&h.executor,committed,sizeof(committed),&n)==BE_OK);
        CHECK(n==want && memcmp(committed,cases[i].print,want)==0);
        CHECK(memcmp(committed,preview,want)==0);
        CHECK(h.executor.cursor!=initial.cursor);
        CHECK(memcmp(h.program_bytes,initial_program,sizeof(initial_program))==0);
        if (cases[i].assignment) CHECK(abs_assert_b(&h,cases[i].value)==0);
        else CHECK(memcmp(h.entries,prior_entries,sizeof(prior_entries))==0);
    }
    return 0;
}

static int abs_negative_green(void)
{
    static const char *const malformed[]={
        "PRINT ABS()", "PRINT ABS(\"X\")", "PRINT ABS(1,2)"
    };
    size_t i;
    for(i=0u;i<sizeof(malformed)/sizeof(malformed[0]);++i) {
        AbsHarness h;
        CHECK(abs_prepare(&h,malformed[i],2u)==0);
        CHECK(abs_rejected(&h,BE_UNSUPPORTED,sizeof(h.output))==0);
    }
    {
        AbsHarness h;
        CHECK(abs_prepare(&h,"PRINT ABS(-32768)",2u)==0);
        CHECK(abs_rejected(&h,BE_UNSUPPORTED,sizeof(h.output))==0);
        CHECK(abs_prepare(&h,"PRINT ABS(A%)",2u)==0);
        CHECK(abs_seed(&h,"A",INT16_MIN)==0);
        CHECK(abs_rejected(&h,BE_UNSUPPORTED,sizeof(h.output))==0);
        CHECK(abs_prepare(&h,"B%=ABS(A%)",2u)==0);
        CHECK(abs_seed(&h,"A",INT16_MIN)==0);
        CHECK(abs_rejected(&h,BE_UNSUPPORTED,sizeof(h.output))==0);
        CHECK(abs_prepare(&h,"PRINT ABS(A%)",2u)==0);
        CHECK(abs_rejected(&h,BE_VARIABLE_NOT_FOUND,sizeof(h.output))==0);
        CHECK(abs_prepare(&h,"PRINT ABS(1)",2u)==0);
        CHECK(abs_rejected(&h,BE_NO_SPACE,3u)==0);
        CHECK(abs_prepare(&h,"B%=ABS(A%)",1u)==0);
        CHECK(abs_seed(&h,"A",7)==0);
        CHECK(abs_rejected(&h,BE_STORE_FULL,sizeof(h.output))==0);
    }
    /* Raw, forged token sequences bypass the tokenizer on purpose. */
    {
        static const uint8_t raw[][13]={
            {0xbfu,' ',0xffu,0x00u,'(',0x0fu}, /* missing ')' */
            {0xbfu,' ',0xffu,0x00u,'(',0x0fu,')',0x0fu}, /* suffix */
            {0xbfu,' ',0xffu,0x00u,'(',0x1au,0xffu} /* truncated 1A word */
        };
        const size_t lengths[]={6u,8u,7u};
        for(i=0u;i<3u;++i) {
            AbsHarness h;
            BEStatus actual;
            uint8_t saved[sizeof(h.output)];
            BasicExecutor before;
            size_t n=123u;
            CHECK(abs_prepare(&h,"PRINT ABS(1)",2u)==0);
            CHECK(bp_put(&h.program,10u,raw[i],lengths[i])==BP_OK);
            CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
            before=h.executor;
            memset(h.output,0x5au,sizeof(h.output));
            memcpy(saved,h.output,sizeof(saved));
            actual=be_step(&h.executor,h.output,sizeof(h.output),&n);
            CHECK(actual!=BE_OK && actual!=BE_END);
            CHECK(n==123u && memcmp(&h.executor,&before,sizeof(before))==0);
            CHECK(memcmp(h.output,saved,sizeof(saved))==0);
        }
    }
    /* FF 00 inside REM, quote and numeric payload must never be
     * interpreted as the reached ABS function (opaque-token probes). */
    {
        static const uint8_t opaque[][7]={
            {0xc5u,' ',0xffu,0x00u},
            {0xbfu,' ','"',0xffu,0x00u,'"'},
            {0xbfu,' ',0x19u,0xffu,0x00u}
        };
        const size_t sizes[]={4u,6u,5u};
        for(i=0u;i<3u;++i) {
            AbsHarness h;
            CHECK(abs_prepare(&h,"PRINT ABS(1)",2u)==0);
            CHECK(bp_put(&h.program,10u,opaque[i],sizes[i])==BP_OK);
            CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
            CHECK(abs_rejected(&h,BE_BAD_SEQUENCE,sizeof(h.output))==0);
        }
    }
    return 0;
}


/* End-to-end numbered BASIC: assignment A%, PRINT ABS(A%), assignment
 * B%=ABS(A%), PRINT B%. No injected A% and no printer transport. */
static int abs_program_green(void)
{
    static const struct {
        const char *assignment;
        const char *expected;
        int16_t value;
    } cases[]={
        {"A%=0"," 0 \n",0},
        {"A%=7"," 7 \n",7},
        {"A%=-7"," 7 \n",7},
        {"A%=32767"," 32767 \n",32767},
        {"A%=-32767"," 32767 \n",32767}
    };
    size_t i;
    for(i=0u;i<sizeof(cases)/sizeof(cases[0]);++i) {
        AbsHarness h;
        BasicVariableKey key={0};
        BasicVariableValue v={0};
        const char *lines[]={"PRINT ABS(A%)","B%=ABS(A%)","PRINT B%"};
        uint8_t body[128];
        size_t j,n;
        CHECK(abs_prepare(&h,cases[i].assignment,2u)==0);
        for(j=0u;j<3u;++j) {
            n=0u;
            CHECK(bt_tokenize((const uint8_t *)lines[j],strlen(lines[j]),
                              body,sizeof(body),&n)==BT_OK);
            CHECK(bp_put(&h.program,(uint16_t)(20u+j*10u),body,n)==BP_OK);
        }
        CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
        n=77u;
        CHECK(be_step(&h.executor,h.output,sizeof(h.output),&n)==BE_OK);
        CHECK(n==0u);
        key.type=(uint8_t)BVT_INTEGER;
        key.name_length=1u;
        key.name[0]=(uint8_t)'A';
        CHECK(bvs_get(&h.store,&key,&v)==BVS_OK);
        CHECK(v.data.integer==(cases[i].assignment[3]=='-' ?
                  (int16_t)(-cases[i].value) : cases[i].value));
        n=77u;
        CHECK(be_step(&h.executor,h.output,sizeof(h.output),&n)==BE_OK);
        CHECK(n==strlen(cases[i].expected));
        CHECK(memcmp(h.output,cases[i].expected,n)==0);
        n=77u;
        CHECK(be_step(&h.executor,h.output,sizeof(h.output),&n)==BE_OK);
        CHECK(n==0u && abs_assert_b(&h,cases[i].value)==0);
        n=77u;
        CHECK(be_step(&h.executor,h.output,sizeof(h.output),&n)==BE_OK);
        CHECK(n==strlen(cases[i].expected));
        CHECK(memcmp(h.output,cases[i].expected,n)==0);
        CHECK(be_step(&h.executor,h.output,sizeof(h.output),&n)==BE_END);
    }
    /* The real A%=-32768 assignment is legal; its ABS use is not. */
    {
        AbsHarness h;
        uint8_t body[128];
        size_t n=0u;
        CHECK(abs_prepare(&h,"A%=-32768",2u)==0);
        CHECK(bt_tokenize((const uint8_t *)"PRINT ABS(A%)",
                          strlen("PRINT ABS(A%)"),
                          body,sizeof(body),&n)==BT_OK);
        CHECK(bp_put(&h.program,20u,body,n)==BP_OK);
        CHECK(be_init_with_store(&h.executor,&h.program,&h.store)==BE_OK);
        n=23u;
        CHECK(be_step(&h.executor,h.output,sizeof(h.output),&n)==BE_OK);
        CHECK(n==0u);
        CHECK(abs_rejected(&h,BE_UNSUPPORTED,sizeof(h.output))==0);
    }
    return 0;
}

int main(int argc, char **argv)
{
    size_t i;
    CHECK(argc==2);
    for (i=0u;i<sizeof(names)/sizeof(names[0]);++i)
        CHECK(each_oracle(argv[1],names[i])==0);
    CHECK(negatives()==0);
    CHECK(program_atomicity()==0);
    CHECK(alias_list_roundtrip()==0);
    CHECK(abs_native_green()==0);
    CHECK(abs_negative_green()==0);
    CHECK(abs_program_green()==0);
    puts("J1.20-B1 16/16 MATCH_EXACT_RAM, LIST source-semantic, RUN unsupported");
    return 0;
}
