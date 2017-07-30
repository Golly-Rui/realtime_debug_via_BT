#include<stdio.h>
#include<string.h>
#include<stdint.h>

int16_t strrlen(char * buf,uint16_t size){
    printf("size:%d",sizeof(buf));
    uint16_t len = size;
    uint8_t * ptr = buf + size;
    while(!*(--ptr)){
        len--;
    }
    return len;
}


uint8_t * strnrchr(uint8_t * buf,uint8_t c, uint16_t size) {
    uint16_t len = size;
    uint8_t * ptr = buf + size;
    while (*(--ptr)!=c && ptr >= buf);
    return ptr;
}


int16_t strMatch(uint8_t src[], uint8_t match[], uint16_t srcSize,uint16_t matchSize) {
    uint8_t * ptr;
    for (ptr = src; ptr - src < srcSize; ptr++) {
        for(uint8_t indice=0;indice<matchSize;indice++){
            if(match[indice] != ptr[indice]){
                break;
            }
            if(indice == matchSize -1){
                return ptr - src;
            }
        }
    }
    return -1;
}

int main(){
    char a[100] = "miao\0\0\0\0miao233\0\0\0miao123\0";
    uint8_t arrayLen = sizeof(a) / sizeof(a[0]);
    /*printf("%d\n",strrlen(a,arrayLen));*/
    /*printf("%s\n",strnrchr(a,'i',strrlen(a,arrayLen)));*/
    /*printf("arrayLen:%d\n",sizeof(a));*/
    printf("Match:%d",strMatch(a,"iao2",sizeof(a)/sizeof(a[0]),4));
}
