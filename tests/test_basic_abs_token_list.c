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
static int run_stays_host_unsupported(const BasicProgram *whole)
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
        CHECK(result != BE_OK && result != BE_END);
        CHECK(result == BE_UNSUPPORTED || result == BE_UNKNOWN_TOKEN ||
              result == BE_BAD_SEQUENCE || result == BE_TRUNCATED);
        CHECK(memcmp(&before, &executor, sizeof(executor)) == 0);
        CHECK(memcmp(storage, backup, sizeof(storage)) == 0);
        CHECK(written == 71u);
        for (i = 0u; i < sizeof(output); ++i) CHECK(output[i] == 0x6au);
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
        char *at = strstr(path, "/original/");
        CHECK(at != NULL);
        memcpy(at+1, "repeat  ", 8u); /* Replace original/ by repeat/ + slash. */
        /* Rebuild path instead, to avoid silently accepting a bad separator. */
    }
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
    CHECK(run_stays_host_unsupported(&imported) == 0);
    CHECK(memcmp(snap, import_storage, sizeof(snap)) == 0);
    printf("ABS-B1 %s MATCH_EXACT_RAM original+repeat MATCH_SEMANTIC_LIST "
           "RUN_HOST_UNSUPPORTED\n", name);
    return 0;
}

static int negatives(void)
{
    static const char *const invalid[] = {
        "PRINT ABS(2)", "PRINT ABS(32768)", "PRINT ABS(-32769)",
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
        CHECK(bt_tokenize((const uint8_t *)invalid[i],strlen(invalid[i]),
                          out,sizeof(out),&written) != BT_OK);
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

int main(int argc, char **argv)
{
    size_t i;
    CHECK(argc==2);
    for (i=0u;i<sizeof(names)/sizeof(names[0]);++i)
        CHECK(each_oracle(argv[1],names[i])==0);
    CHECK(negatives()==0);
    puts("J1.20-B1 16/16 MATCH_EXACT_RAM, LIST source-semantic, RUN unsupported");
    return 0;
}
