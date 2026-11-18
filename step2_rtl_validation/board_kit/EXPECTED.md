# Expected results for the board kit

Cycles = clock cycles from run-enable to `halted` (RTL testbench `tb_core.v`; the board's cycle counter may differ by a constant of a few cycles depending on where it starts counting). a0 = FNV-1a hash of the kernel outputs (also shown on LEDG[2] as a0 != 0).

| Board | Kernel | MUL_FAST | IMEM/DMEM AW | code B | data B | RTL cycles | PQ-uArch cycles | retired | a0 (hex) |
|---|---|---|---|---|---|---|---|---|---|
| EP4CE6 | 1: SHAKE256, 1 KB | 0 | 11/11 | 6852 | 1292 | 143221 | 143221 | 123911 | 6842414c |
| EP4CE6 | 1: SHAKE256, 1 KB | 1 | 11/11 | 6852 | 1292 | 141175 | 141175 | 123911 | 6842414c |
| EP4CE6 | 2: ML-KEM NTT+INTT x2 | 0 | 11/11 | 1068 | 1284 | 796481 | 796481 | 144187 | 8ca179f7 |
| EP4CE6 | 2: ML-KEM NTT+INTT x2 | 1 | 11/11 | 1068 | 1284 | 240961 | 240961 | 144187 | 8ca179f7 |
| EP4CE6 | 3: ML-DSA NTT+INTT | 0 | 11/11 | 792 | 2052 | 436650 | 436650 | 68003 | c1c25f7d |
| EP4CE6 | 3: ML-DSA NTT+INTT | 1 | 11/11 | 792 | 2052 | 119210 | 119210 | 68003 | c1c25f7d |
| DE1-SoC | 1: SHAKE256, 1 KB | 0 | 14/15 | 6852 | 1292 | 143221 | 143221 | 123911 | 6842414c |
| DE1-SoC | 1: SHAKE256, 1 KB | 1 | 14/15 | 6852 | 1292 | 141175 | 141175 | 123911 | 6842414c |
| DE1-SoC | 2: ML-KEM NTT+INTT x2 | 0 | 14/15 | 1068 | 1284 | 796481 | 796481 | 144187 | 8ca179f7 |
| DE1-SoC | 2: ML-KEM NTT+INTT x2 | 1 | 14/15 | 1068 | 1284 | 240961 | 240961 | 144187 | 8ca179f7 |
| DE1-SoC | 3: ML-DSA NTT+INTT | 0 | 14/15 | 792 | 2052 | 436650 | 436650 | 68003 | c1c25f7d |
| DE1-SoC | 3: ML-DSA NTT+INTT | 1 | 14/15 | 792 | 2052 | 119210 | 119210 | 68003 | c1c25f7d |
| DE1-SoC | 4: ML-KEM-512 K+E+D | 0 | 14/15 | 17320 | 3732 | 6794835 | 6794835 | 2293424 | 9d2b4bde |
| DE1-SoC | 4: ML-KEM-512 K+E+D | 1 | 14/15 | 17320 | 3732 | 3119599 | 3119599 | 2293424 | 9d2b4bde |
| DE1-SoC | 5: ML-KEM-768 K+E+D | 0 | 14/15 | 17104 | 5204 | 10746226 | 10746226 | 3701996 | 0b44bdf1 |
| DE1-SoC | 5: ML-KEM-768 K+E+D | 1 | 14/15 | 17104 | 5204 | 5008963 | 5008963 | 3701996 | 0b44bdf1 |

## Steps
1. Copy `core_rtl/` into your Quartus project (or use your existing project).
2. Set the top-level parameters `IMEM_AW` and `DMEM_AW` to the values above (and `MUL_FAST`).
3. Copy `program.hex` and `data.hex` of one kernel into the project folder; compile; program the board.
4. Press run; when LEDG[3] (halted) is lit, read the cycle counter in the In-System Sources and Probes Editor
   and a0 in the In-System Memory Content Editor. Compare with the table. Report the difference in the paper.
