    .section .text.start
    .globl _start
_start:
    li   sp, 0x01FFFFF0
    la   t0, __bss_start
    la   t1, __bss_end
1:  bgeu t0, t1, 2f
    sw   zero, 0(t0)
    addi t0, t0, 4
    j    1b
2:  call main
    li   t0, 0xFFFF0004
    sw   a0, 0(t0)
3:  j 3b
