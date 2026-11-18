/* Calibration micro-benchmarks: N repetitions of one pattern (PATTERN, N set by -D).
 * Per-pattern cost = (cycles(N=64) - cycles(N=0)) / 64, measured on the RTL and the simulator. */
    .section .text.start
    .globl _start
_start:
    li   sp, 0x0001FFF0
    li   s0, 0x10000
    li   a1, 1234567
    li   a2, 89
    li   a3, -5
    sw   a1, 0(s0)
    .rept N
#if PATTERN == 1      /* independent ALU */
    addi a0, a0, 1
#elif PATTERN == 2    /* load + dependent use (load-use) */
    lw   a4, 0(s0)
    add  a0, a0, a4
#elif PATTERN == 3    /* store + independent load */
    sw   a0, 4(s0)
    lw   a4, 0(s0)
#elif PATTERN == 4    /* taken forward branch over nothing */
    beq  zero, zero, 1f
1:
#elif PATTERN == 5    /* not-taken branch */
    bne  zero, zero, 1f
1:
#elif PATTERN == 6    /* jal to next instruction */
    jal  zero, 1f
1:
#elif PATTERN == 7    /* call + return (jal + jalr) */
    jal  ra, 2f
    j    3f
2:  ret
3:
#elif PATTERN == 8    /* mul */
    mul  a4, a1, a2
#elif PATTERN == 9    /* mulh */
    mulh a4, a1, a3
#elif PATTERN == 10   /* mulhu */
    mulhu a4, a1, a2
#elif PATTERN == 11   /* div */
    div  a4, a1, a2
#elif PATTERN == 12   /* remu */
    remu a4, a1, a2
#elif PATTERN == 13   /* mul followed by dependent add */
    mul  a4, a1, a2
    add  a0, a0, a4
#endif
    .endr
    li   a0, 0
9:  j 9b
