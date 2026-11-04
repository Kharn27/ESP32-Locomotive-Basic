/* HW4-DISP-RENDER-A: frozen generic renderer oracle, host-only.
 * Source algorithm: main@21e95a7197413923bb5976067a0419bc729c20c1
 * video/cpc_video.c (sampled_pen + cpc_video_render_row).
 * This file MUST NOT call the optimized cpc_video_render_row().
 */
#ifndef HW4_RENDER_A_REFERENCE_H
#define HW4_RENDER_A_REFERENCE_H
#include "cpc_video.h"
bool hw4_render_a_reference(const CpcVideo *video, unsigned y,
                           uint16_t *rgb565, size_t pixel_capacity);
#endif
