/* Candidate driver: numeric ASCII results only, never used to acquire CPC. */
#include "../tools/clk_04_a4_numeric_lab.h"
#include <stdint.h>
#include <stdio.h>
static int decimal(const char *text,uint32_t *result){
    uint32_t n=0u;
    if(!text || !*text || !result) return 0;
    for(const unsigned char *p=(const unsigned char*)text;*p;p++){
        uint32_t digit;
        if(*p<'0'||*p>'9')return 0;
        digit=(uint32_t)(*p-'0');
        if(n>(UINT32_MAX-digit)/10u)return 0;
        n=n*10u+digit;
    }
    *result=n;return 1;
}
static void hexout(const uint8_t *p,size_t len){
    static const char digits[]="0123456789ABCDEF";
    for(size_t i=0u;i<len;i++){putchar(digits[p[i]>>4u]);putchar(digits[p[i]&0xfu]);}
}
static void print_candidate(int64_t v){
    uint8_t tmp[32];size_t used=0;
    if(a4_print_candidate(v,tmp,sizeof tmp,&used)!=A4_OK){fputs("UNSUPPORTED",stdout);return;}
    hexout(tmp,used);
}
int main(int argc,char **argv){
    if(argc<2||argc>65){fputs("usage: candidate numeric... (max 64)\n",stderr);return 2;}
    for(int i=1;i<argc;i++){
        uint32_t n;uint8_t input[5],twice_raw[5];uint64_t twice;int ge,gt;
        if(!decimal(argv[i],&n)){fputs("INVALID_UINT32_DECIMAL\n",stderr);return 2;}
        if(a4_integer_to_real5(n,input)!=A4_OK||
           a4_times_two(n,&twice)!=A4_OK||
           a4_integer_to_real5(twice,twice_raw)!=A4_OK||
           a4_ge_zero(n,&ge)!=A4_OK||
           a4_gt_32767(n,&gt)!=A4_OK){
            fputs("CANDIDATE_OUT_OF_DOMAIN\n",stderr);return 2;
        }
        printf("%u\t",(unsigned)n);hexout(input,5);
        printf("\t%llu\t",(unsigned long long)twice);hexout(twice_raw,5);
        printf("\t%d\t%d\t",ge,gt);
        print_candidate(n);putchar('\t');
        print_candidate((int64_t)twice);putchar('\t');
        print_candidate(ge);putchar('\t');
        print_candidate(gt);putchar('\n');
    }
    return 0;
}
