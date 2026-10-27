/* Headless reproducible 320x240 RGB PPM previews for all 3 modes. */
#include "cpc_video.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint8_t vram[CPC_VIDEO_BYTES];
static uint16_t row[320];
static uint8_t demo_glyph(void *unused, uint8_t c, unsigned y)
{
    (void)unused;
    if (c == ' ') return 0;
    if (y == 0U || y == 7U) return 0x7e;
    return (uint8_t)(0x42U | ((unsigned)c << (y % 4U) & 0x18U));
}
int main(int argc, char **argv)
{
    const char *prefix = argc == 2 ? argv[1] : "cpc";
    CpcVideo video;
    for (unsigned mode=0; mode<3U; ++mode) {
        if (!cpc_video_init(&video,vram,sizeof vram,(CpcMode)mode)) return 1;
        unsigned w = cpc_video_width(&video), colours=cpc_video_colors(&video);
        for (unsigned y=0;y<200U;y++) {
            for (unsigned x=0;x<w;x++) {
                unsigned pen = ((x/16U)+(y/16U)) % colours;
                if (!cpc_video_put(&video,x,y,pen)) return 2;
            }
        }
        for (unsigned x=0;x<27U;x++)
            if (!cpc_video_set_ink(&video,x%colours,x)) return 3;
        if (!cpc_video_set_text_colors(&video,1,0)) return 4;
        for (unsigned x=0;x<cpc_video_columns(&video);x++)
            if (!cpc_video_put_cell(&video,x,2,(uint8_t)('A'+x%26U),demo_glyph,NULL)) return 5;
        if (!cpc_video_cursor(&video,1,4,true)) return 6;
        char path[512];
        int written=snprintf(path,sizeof path,"%s-mode%u.ppm",prefix,mode);
        if (written<0 || (size_t)written>=sizeof path) return 7;
        FILE *f=fopen(path,"wb");
        if (f==NULL) return 8;
        if (fprintf(f,"P6\n320 240\n255\n")<0) { fclose(f); return 9; }
        for (unsigned y=0;y<240U;y++) {
            if (!cpc_video_render_row(&video,y,row,320)) { fclose(f); return 10; }
            for (unsigned x=0;x<320U;x++) {
                /* Round RGB565 channels to 8 bits using bit replication. */
                uint16_t c=row[x];
                unsigned r=(c>>11U)&31U, g=(c>>5U)&63U, b=c&31U;
                uint8_t rgb[3]={(uint8_t)((r<<3U)|(r>>2U)),
                                (uint8_t)((g<<2U)|(g>>4U)),
                                (uint8_t)((b<<3U)|(b>>2U))};
                if (fwrite(rgb,1,sizeof rgb,f)!=sizeof rgb) { fclose(f); return 11; }
            }
        }
        if (fclose(f)!=0) return 12;
        printf("HW4 PPM mode=%u path=%s\n",mode,path);
    }
    return 0;
}
