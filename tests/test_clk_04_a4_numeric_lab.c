#include "../tools/clk_04_a4_numeric_lab.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static void encoding(uint64_t v, const uint8_t want[5]) {
    uint8_t got[5]={0x55,0x55,0x55,0x55,0x55};
    assert(a4_integer_to_real5(v,got)==A4_OK);
    assert(memcmp(got,want,5)==0);
}
static void negative_tests(void) {
    uint8_t buf[5]={7,7,7,7,7}, copy[5];
    uint8_t printable[20];
    int sign=99;size_t used=77;
    memcpy(copy,buf,5);
    assert(a4_integer_to_real5(UINT64_C(8589934591),buf)==A4_UNSUPPORTED);
    assert(memcmp(buf,copy,5)==0);
    assert(a4_integer_to_real5(UINT64_MAX,buf)==A4_UNSUPPORTED);
    assert(memcmp(buf,copy,5)==0);
    assert(a4_integer_to_real5(0,NULL)==A4_INVALID);
    assert(a4_ge_zero(1,NULL)==A4_INVALID);
    assert(a4_gt_32767(1,NULL)==A4_INVALID);
    assert(sign==99);
    memset(printable,'Z',sizeof printable);
    assert(a4_print_candidate(12,printable,3,&used)==A4_NO_SPACE);
    assert(used==77 && printable[0]=='Z');
    assert(a4_print_candidate(INT64_MAX,printable,sizeof printable,&used)==A4_UNSUPPORTED);
    assert(used==77 && printable[0]=='Z');
    assert(a4_print_candidate(1,NULL,100,&used)==A4_INVALID);
    assert(a4_print_candidate(-2,printable,sizeof printable,&used)==A4_UNSUPPORTED);
    assert(a4_print_candidate(1,printable,sizeof printable,NULL)==A4_INVALID);
}
static void test_all(void) {
    const uint32_t values[]={0,1,2,9,10,99,100,999,1000,5256,12934,14350,27664,
        32767,32768,33174,50376,65535,65536,65537,8388607,8388608,
        2147483647u,2147483648u,UINT32_MAX};
    uint8_t raw[5],raw2[5],out[24];uint64_t doubled;int ge,gt;size_t length=0;
    encoding(0,(const uint8_t[]){0,0,0,0,0});
    encoding(1,(const uint8_t[]){0,0,0,0,0x81});
    encoding(2,(const uint8_t[]){0,0,0,0,0x82});
    encoding(5256,(const uint8_t[]){0,0,0x40,0x24,0x8d});
    for(size_t i=0;i<sizeof values/sizeof values[0];i++){
        uint32_t v=values[i];
        assert(a4_integer_to_real5(v,raw)==A4_OK);
        assert(a4_times_two(v,&doubled)==A4_OK);
        assert(doubled==(uint64_t)v*2u);
        assert(a4_integer_to_real5(doubled,raw2)==A4_OK);
        if(v) {
            assert(raw2[4]==raw[4]+1u);
            assert(memcmp(raw2,raw,4)==0);
        }
        assert(a4_ge_zero(v,&ge)==A4_OK && ge==-1);
        assert(a4_gt_32767(v,&gt)==A4_OK && gt==(v>32767?-1:0));
    }
    assert(a4_print_candidate(0,out,sizeof out,&length)==A4_OK);
    assert(length==5 && memcmp(out," 0 \r\n",5)==0);
    assert(a4_print_candidate(-1,out,sizeof out,&length)==A4_OK);
    assert(length==5 && memcmp(out,"-1 \r\n",5)==0);
    assert(a4_print_candidate(999999,out,sizeof out,&length)==A4_OK);
    assert(length==10 && memcmp(out," 999999 \r\n",10)==0);
    assert(a4_print_candidate(1000000,out,sizeof out,&length)==A4_UNSUPPORTED);
}
int main(void){test_all();negative_tests();puts("A4 HOST C99 TESTS PASS (CANDIDATE_NOT_CPC)");return 0;}
