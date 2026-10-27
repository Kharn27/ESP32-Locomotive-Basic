/* Real native BASIC -> text adapter -> CPC VRAM; never synthesize PRINT. */
#include "basic_session_runtime.h"
#include "basic_variable_store.h"
#include "cpc_text.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint8_t program_memory[8192];
static uint8_t temporary[2048];
static uint8_t output[4096];
static BasicVariableEntry entries[64];
static uint8_t vram[CPC_VIDEO_BYTES];
static BasicProgram program;
static BasicVariableStore store;
static BasicSessionRuntime runtime;
static CpcVideo video;
static CpcText sink;
static size_t written;

static uint8_t glyph(void *ctx, uint8_t character, unsigned y)
{
    (void)ctx;
    return (character == (uint8_t)'5' && y == 0U) ? 0x80U : 0U;
}

static void submit(const char *source)
{
    BSRResult r = bsr_submit(&runtime, (const uint8_t *)source, strlen(source),
                             temporary, sizeof(temporary),
                             output, sizeof(output), &written);
    assert(r.status == BSR_OK);
    assert(written == 0U);
}

int main(void)
{
    static const char *const lines[] = {
        "10 A%=2", "20 B%=A%+3", "30 PRINT B%", "40 END"
    };
    static const uint8_t oracle[] = {' ', '5', ' ', '\n'};
    uint8_t collected[16] = {0};
    size_t count = 0U;
    assert(bp_init(&program, program_memory, sizeof(program_memory)) == BP_OK);
    assert(bvs_init(&store, entries, 64U) == BVS_OK);
    assert(bsr_init_with_store(&runtime, &program, &store).status == BSR_OK);
    assert(cpc_video_init(&video, vram, sizeof(vram), CPC_MODE_1));
    assert(cpc_video_set_ink(&video, 1U, 24U));
    assert(cpc_text_init(&sink, &video, glyph, NULL));
    for (size_t i = 0U; i < 4U; ++i) submit(lines[i]);
    submit("RUN");

    unsigned steps = 0U;
    for (;;) {
        BSRResult r = bsr_step(&runtime, output, sizeof(output), &written);
        if (r.status == BSR_END) break;
        assert(r.status == BSR_OK && r.executor_status == BE_OK);
        assert(++steps <= 4U);
        if (written > 0U) {
            assert(written <= sizeof(collected) - count);
            memcpy(collected + count, output, written);
            count += written;
            assert(cpc_text_write(&sink, output, written));
        }
    }
    assert(steps == 4U);
    assert(count == sizeof(oracle));
    assert(memcmp(collected, oracle, sizeof(oracle)) == 0);
    assert(sink.bytes_received == count && sink.glyphs_drawn == 3U);
    assert(sink.row == 1U && sink.column == 0U);
    {
        uint8_t p = 0U;
        assert(cpc_video_get(&video, 8U, 0U, &p) && p == 1U);
    }
    puts("HW4-C1 real bsr_step -> VRAM exact bytes PASS");
    return 0;
}
