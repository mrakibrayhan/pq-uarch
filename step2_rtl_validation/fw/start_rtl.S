/* Bare-metal start for the RTL core (Harvard: code in imem from 0, data in dmem). Ends with
 * "j ." which the core treats as a halt; a0 holds main's return value. */
    .section .text.start
    .globl _start
_start:
    li   sp, 0x0001FFF0
    la   t0, __bss_start
    la   t1, __bss_end
1:  bgeu t0, t1, 2f
    sw   zero, 0(t0)
    addi t0, t0, 4
    j    1b
2:  call main
3:  j 3b
