/* HW4-C3-A: portable HW3 boot layout; no LCD, dynamic RAM or ROM. */
#include "cpc_boot.h"
#include <string.h>
bool cpc_boot_line(unsigned index,bool cyd_heading,CpcBootLine *out)
{
    static const unsigned rows[CPC_BOOT_LINES]={3U,5U,7U,10U,12U};
    static const char *const strings[CPC_BOOT_LINES]={
        "Amstrad 128K Microcomputer (v3)",
        "\x7f" "1985 Amstrad Consumer Electronics plc",
        "and Locomotive Software Ltd.",
        "BASIC 1.1",
        "Ready"
    };
    if(out==NULL || index>=CPC_BOOT_LINES) return false;
    const char *s=index==0U && cyd_heading
        ? "ESP32 CYD 128K Microcomputer (v3)" : strings[index];
    size_t n=strlen(s);
    if(n>40U) return false;
    out->row=rows[index];
    out->column=index<3U ? (40U-(unsigned)n)/2U : index==3U ? 1U : 0U;
    out->text=s;
    return true;
}
bool cpc_boot_console(CpcText *text,bool cyd_heading)
{
    if(text==NULL || text->video==NULL || text->glyph==NULL ||
       text->video->pixels==NULL || text->video->mode!=CPC_MODE_1 ||
       cpc_video_columns(text->video)!=40U ||
       text->row!=0U || text->column!=0U) return false;
    for(unsigned i=0U;i<CPC_BOOT_LINES;++i) {
        CpcBootLine line;
        if(!cpc_boot_line(i,cyd_heading,&line)) return false;
        for(unsigned j=0U;line.text[j]!='\0';++j)
            if(!cpc_video_put_cell(text->video,line.column+j,line.row,
                                   (uint8_t)(unsigned char)line.text[j],
                                   text->glyph,text->glyph_context))
                return false;
    }
    /* Startup is not BASIC output: do not mutate counters or input digest. */
    text->row=CPC_BOOT_INPUT_ROW;
    text->column=0U;
    return cpc_video_cursor(text->video,0U,CPC_BOOT_INPUT_ROW,true);
}
