/* HW4 A1-C0: pure C99 transaction plan, no LCD, VRAM or heap ownership. MIT. */
#ifndef HW4_BATCH16_DMA_H
#define HW4_BATCH16_DMA_H
#include <stdbool.h>
#include <stdint.h>
#define HW4_BATCH16_FULL_DIRTY UINT32_C(0x01ffffff)
#define HW4_BATCH16_BAND_BYTES 5120U
#define HW4_BATCH16_BUFFER_BYTES 10240U
typedef bool (*Hw4Batch16Sender)(void *context, unsigned first_band,
                                unsigned height_px);
typedef struct {
    unsigned logical_bands;
    unsigned physical_transfers;
    uint64_t pixel_bytes;
} Hw4Batch16Stats;
/* Only case10 is experimentally enabled. Other orientations use legacy 8px. */
bool hw4_batch16_eligible(bool enabled, int video_mode,
                          unsigned orientation, uint32_t dirty);
/* Caller must be sole owner of dirty and LCD. Each successful blocking send
 * releases exactly its own bit(s); failed and future bands stay dirty.
 * The callback must return true only after the physical DMA has completed.
 * No retries, rollback, VSCR or second screen buffer. */
bool hw4_batch16_flush(uint32_t *dirty, Hw4Batch16Sender sender,
                       void *context, Hw4Batch16Stats *stats);
#endif
