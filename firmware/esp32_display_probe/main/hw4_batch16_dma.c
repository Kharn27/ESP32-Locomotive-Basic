/* HW4 A1-C0: 25 ordered logical bands -> 12x16px + 1x8px. MIT. */
#include "hw4_batch16_dma.h"
#include <stddef.h>

bool hw4_batch16_eligible(bool enabled, int video_mode,
                          unsigned orientation, uint32_t dirty)
{
    return enabled && video_mode == 1 && orientation == 10U &&
           dirty == HW4_BATCH16_FULL_DIRTY;
}

bool hw4_batch16_flush(uint32_t *dirty, Hw4Batch16Sender sender,
                       void *context, Hw4Batch16Stats *stats)
{
    if (dirty == NULL || sender == NULL || stats == NULL ||
        *dirty != HW4_BATCH16_FULL_DIRTY)
        return false;
    stats->logical_bands = 0U;
    stats->physical_transfers = 0U;
    stats->pixel_bytes = UINT64_C(0);
    for (unsigned first = 0U; first < 25U; first += 2U) {
        const unsigned count = first == 24U ? 1U : 2U;
        const unsigned pixels_high = count * 8U;
        const uint32_t ack = (count == 2U ? UINT32_C(3) : UINT32_C(1))
                             << first;
        if (!sender(context, first, pixels_high))
            return false; /* No dirty ACK, no second attempt, no next band. */
        *dirty &= ~ack;  /* DMA completed; only now acknowledge this group. */
        stats->logical_bands += count;
        ++stats->physical_transfers;
        stats->pixel_bytes += (uint64_t)count * HW4_BATCH16_BAND_BYTES;
    }
    return true;
}
