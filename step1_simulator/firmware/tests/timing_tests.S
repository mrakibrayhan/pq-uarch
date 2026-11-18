/* Micro-benchmarks with known cycle counts, used to verify the timing model.
 * Each test is wrapped in region markers (MMIO+8 begin, MMIO+12 end). */
    .macro BEG id
    li   t6, \id
    sw   t6, 8(s11)
    .endm
    .macro END id
    li   t6, \id
    sw   t6, 12(s11)
    .endm
    .section .text.start
    .globl _start
_start:
    li   s11, 0xFFFF0000
    li   sp, 0x01FFFFF0
    /* T1: 64 independent ALU ops -> 64 cycles */
    BEG 1
    .rept 64
    addi a0, a0, 1
    .endr
    END 1
    /* T2: 32 load->use pairs -> 32*(1+1+loaduse) cycles */
    BEG 2
    .rept 32
    lw   a1, 0(sp)
    addi a2, a1, 1
    .endr
    END 2
    /* T3: loop of 50 iterations (addi, bnez): taken 49x, not-taken 1x */
    li   a3, 50
    BEG 3
1:  addi a3, a3, -1
    bnez a3, 1b
    END 3
    /* T4: 16 dependent mul -> depends on mul model */
    li   a4, 3
    BEG 4
    .rept 16
    mul  a4, a4, a4
    .endr
    END 4
    /* T5: 8 divisions with small dividend (early divider is fast) */
    li   a5, 7
    li   a6, 3
    BEG 5
    .rept 8
    divu a7, a5, a6
    .endr
    END 5
    li   t0, 0xFFFF0004
    sw   zero, 0(t0)
2:  j 2b
