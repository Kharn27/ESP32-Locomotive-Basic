/* Amstrad CPC firmware colour numbers (not gate-array hardware codes).
 * Nominal 0/128/255 intensity per channel. A deterministic digital model,
 * not a colorimeter-derived physical ILI9341 calibration. MIT.
 */
#include "cpc_video.h"
static const uint8_t colours[27][3] = {
    {0,0,0}, {0,0,128}, {0,0,255}, {128,0,0}, {128,0,128},
    {128,0,255}, {255,0,0}, {255,0,128}, {255,0,255},
    {0,128,0}, {0,128,128}, {0,128,255}, {128,128,0},
    {128,128,128}, {128,128,255}, {255,128,0}, {255,128,128},
    {255,128,255}, {0,255,0}, {0,255,128}, {0,255,255},
    {128,255,0}, {128,255,128}, {128,255,255},
    {255,255,0}, {255,255,128}, {255,255,255}
};
void cpc_video_palette_rgb888(unsigned colour, uint8_t rgb[3])
{
    if (rgb == NULL) return;
    for (unsigned i = 0; i < 3U; ++i)
        rgb[i] = colour < 27U ? colours[colour][i] : 0U;
}
uint16_t cpc_video_palette_rgb565(unsigned colour)
{
    if (colour >= 27U) return UINT16_MAX;
    const uint8_t *rgb = colours[colour];
    return (uint16_t)((((uint16_t)rgb[0] >> 3U) << 11U) |
                      (((uint16_t)rgb[1] >> 2U) << 5U) |
                      ((uint16_t)rgb[2] >> 3U));
}
