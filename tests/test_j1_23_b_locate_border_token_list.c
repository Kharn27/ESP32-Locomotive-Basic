/* J1.23-B: immutable CPC6128 original/repeat RAM and printer evidence.
 * Lexical-only: no native LOCATE/BORDER implementation or screen side effects.
 * Every expected image is loaded from the J1.23-A CPC archive, never encoded
 * from the native tokenizer or disassembly. */
#include "basic_tokenizer.h"
#include "basic_listing.h"
#include "basic_program.h"
#include "basic_session.h"
#include "basic_executor.h"
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "J1.23-B %s:%d: %s\n", __FILE__, __LINE__, #x); \
    return 1; } } while (0)

enum { CAP = 1024, MAX_FILE = 512 };
typedef struct {
    const char *id;
    const char *statement;
    uint8_t token;
} Case;
static const Case cases[] = {
    {"L_01_01", "LOCATE 1,1", 0xa9u},
    {"L_40_25", "LOCATE 40,25", 0xa9u},
    {"L_02_03", "LOCATE 2,3", 0xa9u},
    {"L_00_01", "LOCATE 0,1", 0xa9u},
    {"L_41_01", "LOCATE 41,1", 0xa9u},
    {"L_01_00", "LOCATE 1,0", 0xa9u},
    {"L_01_26", "LOCATE 1,26", 0xa9u},
    {"L_NEG_01", "LOCATE -1,1", 0xa9u},
    {"L_EXPR", "LOCATE 1+2,2+3", 0xa9u},
    {"L_MISSING", "LOCATE 1", 0xa9u},
    {"B_00", "BORDER 0", 0x82u},
    {"B_26", "BORDER 26", 0x82u},
    {"B_27", "BORDER 27", 0x82u},
    {"B_NEG", "BORDER -1", 0x82u},
    {"B_00_26", "BORDER 0,26", 0x82u},
    {"B_26_00", "BORDER 26,0", 0x82u},
    {"B_26_27", "BORDER 26,27", 0x82u},
    {"B_NEG_01", "BORDER -1,1", 0x82u},
    {"B_EXPR", "BORDER 1+2,3+4", 0x82u},
    {"B_MISSING", "BORDER 1,", 0x82u}
};

static int load(const char *root, const char *session, const char *id,
                const char *suffix, uint8_t *out, size_t cap, size_t *n)
{
    char path[512];
    FILE *fp;
    int c;
    int length = snprintf(path, sizeof(path),
        "%s/tests/fixtures/cpc6128/j1_23_a_locate_border/%s/%s/%s",
        root, session, id, suffix);
    if (length < 0 || (size_t)length >= sizeof(path)) return 1;
    fp = fopen(path, "rb");
    if (!fp) { fprintf(stderr, "J1.23-B MISSING %s\n", path); return 1; }
    *n = fread(out, 1u, cap, fp);
    c = fgetc(fp);
    if (*n == 0u || c != EOF || ferror(fp) || fclose(fp) != 0) return 1;
    return 0;
}
static int submit(BasicProgram *p, const char *source)
{
    uint8_t temporary[256], output[512];
    size_t written = 999u;
    BSResult r = bs_process_line(p, (const uint8_t *)source,
                                 strlen(source), temporary,
                                 sizeof(temporary), output,
                                 sizeof(output), &written);
    if (r.status != BS_OK) {
        fprintf(stderr, "J1.23-B source '%s' BS=%d BT=%d BP=%d\n",
                source, (int)r.status,
                (int)r.tokenizer_status, (int)r.program_status);
        return 1;
    }
    return 0;
}
static int make_program(BasicProgram *p, const Case *item)
{
    char line[128];
    int size = snprintf(line, sizeof(line), "10 %s", item->statement);
    CHECK(size > 0 && (size_t)size < sizeof(line));
    CHECK(submit(p, line) == 0);
    CHECK(submit(p, item->token == 0xa9u ?
                 "20 PRINT \"LBLOC\"" : "20 PRINT \"LBBOR\"") == 0);
    CHECK(submit(p, "30 END") == 0);
    return 0;
}
/* CPC printer emits CRLF; host BL emits LF. Everything else must be
 * byte-for-byte identical, including case, commas, source spacing. */
static int equal_printer(const uint8_t *native, size_t nn,
                         const uint8_t *cpc, size_t cn)
{
    size_t i, j = 0u;
    for (i = 0u; i < nn; ++i) {
        if (native[i] == (uint8_t)'\n') {
            if (j + 2u > cn || cpc[j] != (uint8_t)'\r' ||
                cpc[j + 1u] != (uint8_t)'\n') return 0;
            j += 2u;
        } else {
            if (j >= cn || cpc[j] != native[i]) return 0;
            ++j;
        }
    }
    return j == cn;
}
static int rebuild(BasicProgram *p, const uint8_t *listing, size_t count)
{
    size_t at = 0u;
    while (at < count) {
        const uint8_t *end = memchr(listing + at, '\n', count - at);
        char line[128];
        size_t size;
        CHECK(end != NULL);
        size = (size_t)(end - (listing + at));
        CHECK(size > 0u && size < sizeof(line));
        memcpy(line, listing + at, size);
        line[size] = '\0';
        CHECK(submit(p, line) == 0);
        at += size + 1u;
    }
    return 0;
}
static int compare_oracle(const char *root, const Case *item)
{
    const char *const sessions[] = {"original", "repeat"};
    uint8_t image[CAP], returned[CAP], listing[CAP], printer[MAX_FILE];
    uint8_t cpc_orig[MAX_FILE], original_list[MAX_FILE];
    uint8_t store[CAP], import_storage[CAP], reentered_storage[CAP];
    BasicProgram p, imported, reentered;
    BasicProgramLine line;
    size_t nimg, nprinter, nreturned, nlist, nreentered, first_img = 0u;
    size_t first_list = 0u, i;
    for (i = 0u; i < 2u; ++i) {
        CHECK(load(root, sessions[i], item->id, "program.bin",
                   image, sizeof(image), &nimg) == 0);
        CHECK(load(root, sessions[i], item->id, "list/printer.dat",
                   printer, sizeof(printer), &nprinter) == 0);
        if (i == 0u) {
            CHECK(nimg <= sizeof(cpc_orig));
            memcpy(cpc_orig, image, nimg);
            first_img = nimg;
            memcpy(original_list, printer, nprinter);
            first_list = nprinter;
        } else {
            CHECK(first_img == nimg && memcmp(cpc_orig, image, nimg) == 0);
            CHECK(first_list == nprinter &&
                  memcmp(original_list, printer, nprinter) == 0);
        }
        CHECK(bp_init(&p, store, sizeof(store)) == BP_OK);
        CHECK(bp_init(&imported, import_storage,
                      sizeof(import_storage)) == BP_OK);
        CHECK(bp_init(&reentered, reentered_storage,
                      sizeof(reentered_storage)) == BP_OK);
        CHECK(make_program(&p, item) == 0);
        CHECK(bp_export(&p, returned, sizeof(returned), &nreturned) == BP_OK);
        CHECK(nreturned == nimg && memcmp(returned, image, nimg) == 0);
        CHECK(bp_import(&imported, image, nimg) == BP_OK);
        CHECK(bp_find(&imported, 10u, &line) == BP_OK);
        CHECK(line.body_length > 1u);
        CHECK(imported.data[line.body_offset] == item->token);
        CHECK(bl_list_program(&p, listing, sizeof(listing), &nlist) == BL_OK);
        CHECK(equal_printer(listing, nlist, printer, nprinter));
        CHECK(bl_list_program(&imported, returned, sizeof(returned),
                              &nreturned) == BL_OK);
        CHECK(nreturned == nlist &&
              memcmp(returned, listing, nlist) == 0);
        CHECK(rebuild(&reentered, listing, nlist) == 0);
        CHECK(bp_export(&reentered, returned, sizeof(returned),
                        &nreentered) == BP_OK);
        CHECK(nreentered == nimg &&
              memcmp(returned, image, nimg) == 0);
    }
    printf("J1.23-B %s MATCH_EXACT_RAM original/repeat + LIST_PRINTER_EXACT\n",
           item->id);
    return 0;
}
static int lexical_neighbours(void)
{
    static const struct { const char *src, *list; uint8_t op; } positive[] = {
        {"locate 1,1", "LOCATE 1,1", 0xa9u},
        {"border 27", "BORDER 27", 0x82u},
        {"LOCATE 1,1:REM BORDER", "LOCATE 1,1:REM BORDER", 0xa9u},
        {"BORDER 0:REM LOCATE", "BORDER 0:REM LOCATE", 0x82u},
        {"PRINT \"LOCATE BORDER\":REM LOCATE",
         "PRINT \"LOCATE BORDER\":REM LOCATE", 0xbfu},
        {"BORDER 1,", "BORDER 1,", 0x82u},
        {"LOCATE 1", "LOCATE 1", 0xa9u}
    };
    size_t i;
    for (i = 0u; i < sizeof(positive)/sizeof(positive[0]); ++i) {
        uint8_t tokens[128], raw[128], listed[128];
        size_t n = 555u, decoded = 777u, round = 666u;
        CHECK(bt_tokenize((const uint8_t *)positive[i].src,
              strlen(positive[i].src), tokens, sizeof(tokens), &n) == BT_OK);
        CHECK(n > 0u && tokens[0] == positive[i].op);
        CHECK(bl_detokenize(tokens, n, listed,
                            sizeof(listed), &decoded) == BL_OK);
        CHECK(decoded == strlen(positive[i].list) &&
              memcmp(listed, positive[i].list, decoded) == 0);
        CHECK(bt_tokenize(listed, decoded, raw, sizeof(raw), &round) == BT_OK);
        CHECK(round == n && memcmp(raw, tokens, n) == 0);
    }
    return 0;
}
static int negatives(void)
{
    static const char *const invalid[] = {
        "LOCATE", "LOCATE 1,", "LOCATE 2", "LOCATE -2,1",
        "LOCATE 42,1", "LOCATE 1,42", "LOCATE 1+3,2+3",
        "LOCATE 1,2+4", "BORDER", "BORDER -2",
        "BORDER 28", "BORDER 0,28", "BORDER 26,",
        "BORDER 1+3,3+4", "BORDER 1,LOCATE",
        "LOCATE 1,1::REM X"
    };
    static const struct { uint8_t bytes[5]; size_t n; } corrupt[] = {
        {{0xa9u,' ',0x19u,0u,0u}, 3u}, /* Missing 8-bit literal payload. */
        {{0x82u,' ',0xf5u,0u,0u}, 3u}, /* Unary F5 without magnitude. */
        {{0x82u,' ',0x19u,26u,','}, 5u}, /* Not the sealed BORDER 1,. */
        {{0xa9u,' ',0x0fu,',',0xf4u}, 5u}, /* + token without expression lhs. */
        {{0xa9u,' ',0x0fu,',',0x0fu}, 5u} /* A valid statement, not corrupt. */
    };
    uint8_t dest[128], saved[128], storage[CAP], saved_store[CAP];
    uint8_t temp[256], output[128], saved_output[128];
    BasicProgram p;
    size_t written, i;
    BSResult result;
    for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        memset(dest, 0x7bu, sizeof(dest));
        memcpy(saved, dest, sizeof(saved));
        written = 654u;
        CHECK(bt_tokenize((const uint8_t *)invalid[i],strlen(invalid[i]),
                          dest,sizeof(dest),&written) != BT_OK);
        CHECK(written == 654u && memcmp(dest,saved,sizeof(dest)) == 0);
    }
    for (i = 0u; i < sizeof(corrupt)/sizeof(corrupt[0])-1u; ++i) {
        memset(dest, 0x47, sizeof(dest));
        memcpy(saved, dest, sizeof(saved));
        written = 654u;
        CHECK(bl_detokenize(corrupt[i].bytes,corrupt[i].n,dest,
                            sizeof(dest),&written) != BL_OK);
        CHECK(written == 654u && memcmp(dest,saved,sizeof(dest)) == 0);
    }
    memset(dest, 0x39, sizeof(dest));
    memcpy(saved, dest, sizeof(saved));
    written = 654u;
    CHECK(bt_tokenize((const uint8_t *)"LOCATE 1,1",10u,dest,2u,
                      &written) == BT_NO_SPACE);
    CHECK(written == 654u && memcmp(dest,saved,sizeof(dest)) == 0);
    CHECK(bt_tokenize(dest,5u,dest,sizeof(dest),&written)==BT_INVALID_ARGUMENT);
    CHECK(written == 654u && memcmp(dest,saved,sizeof(dest)) == 0);
    CHECK(bl_detokenize((const uint8_t[]){0x82u,' ',0x19u,27u},
          4u,dest,2u,&written) == BL_NO_SPACE);
    CHECK(written == 654u && memcmp(dest,saved,sizeof(dest)) == 0);
    CHECK(bl_detokenize(dest,3u,dest,sizeof(dest),&written)==BL_OVERLAP);
    CHECK(written == 654u && memcmp(dest,saved,sizeof(dest)) == 0);

    memset(storage,0x66,sizeof(storage));
    CHECK(bp_init(&p,storage,sizeof(storage)) == BP_OK);
    CHECK(submit(&p, "10 BORDER 27") == 0);
    memcpy(saved_store,storage,sizeof(storage));
    memset(output,0x77,sizeof(output));
    memcpy(saved_output,output,sizeof(output));
    written=654u;
    result=bs_process_line(&p,(const uint8_t *)"20 LOCATE 1,",
                           strlen("20 LOCATE 1,"),temp,sizeof(temp),
                           output,sizeof(output),&written);
    CHECK(result.status == BS_TOKENIZER_ERROR);
    CHECK(written==654u && memcmp(storage,saved_store,sizeof(storage))==0 &&
          memcmp(output,saved_output,sizeof(output))==0);
    CHECK(bl_list_program(&p,output,1u,&written) == BL_NO_SPACE);
    CHECK(written==654u && memcmp(output,saved_output,sizeof(output))==0);
    CHECK(bl_list_program(&p,storage,sizeof(storage),&written)==BL_OVERLAP);
    CHECK(written==654u && memcmp(storage,saved_store,sizeof(storage))==0);

    /* Native RUN must fail atomically for both not-yet-executable tokens. */
    for (i=0u;i<2u;++i) {
        BasicExecutor executor, before;
        CHECK(bp_init(&p,storage,sizeof(storage))==BP_OK);
        CHECK(submit(&p, i==0u ? "10 LOCATE 1,1" : "10 BORDER 0") == 0);
        memcpy(saved_store,storage,sizeof(storage));
        CHECK(be_init(&executor,&p) == BE_OK);
        before=executor;
        memset(output,0x77,sizeof(output));
        memcpy(saved_output,output,sizeof(output));
        written=654u;
        CHECK(be_step(&executor,output,sizeof(output),&written)==BE_UNKNOWN_TOKEN);
        CHECK(written==654u && memcmp(&executor,&before,sizeof(before))==0);
        CHECK(memcmp(output,saved_output,sizeof(output))==0 &&
              memcmp(storage,saved_store,sizeof(storage))==0);
    }
    return 0;
}
int main(int argc, char **argv)
{
    size_t i;
    CHECK(argc == 2);
    CHECK(lexical_neighbours() == 0);
    CHECK(negatives() == 0);
    for (i=0u;i<sizeof(cases)/sizeof(cases[0]);++i)
        CHECK(compare_oracle(argv[1], &cases[i]) == 0);
    puts("J1.23-B 20/20 CPC original+repeat RAM exact and LIST printer; "
         "atomic negative and RUN rejected — lexical only");
    return 0;
}
