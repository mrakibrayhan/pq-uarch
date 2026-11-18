#!/usr/bin/env python3
"""Step 2 (optional): FPGA board kit for measuring the same kernels on real hardware.

Builds size-optimised kernels (-ffunction-sections, --gc-sections), writes program.hex /
data.hex sized for the chosen board, and runs the RTL testbench with the same memory sizes
to record the EXPECTED cycle count and a0 hash. On the board, read the cycle counter with the
In-System Sources and Probes Editor after the core halts and compare with EXPECTED.md.
  EP4CE6  (RZ-EasyFPGA A2.2, Cyclone IV, 30 M9K): kernels 1-3, IMEM_AW = 11, DMEM_AW = 11
  DE1-SoC (Cyclone V 5CSEMA5, 397 M10K):           kernels 1-5, IMEM_AW = 14, DMEM_AW = 15
Data addresses are linked at 0x10000 and the stack at 0x1FFF0; the core's data RAM indexes
addr[DMEM_AW+1:2], so with a small RAM these alias into the RAM without overlap as long as
data + stack fit (checked below).
Author: Md. Rakib Rayhan
"""
import os, re, subprocess, sys
import run_rtl_validation as V

BOARDS = {"EP4CE6": dict(imem=11, dmem=11, kernels=[1, 2, 3]),
          "DE1-SoC": dict(imem=14, dmem=15, kernels=[1, 2, 3, 4, 5])}
KIT = os.path.join(V.H, "board_kit")


def build(k, board):
    scheme = V.KERNELS[k][1]; src = os.path.join(V.PQ, scheme)
    d = os.path.join(KIT, board, f"kernel{k}"); os.makedirs(d, exist_ok=True)
    cfiles = [os.path.join(src, f) for f in sorted(os.listdir(src)) if f.endswith(".c")] + [os.path.join(V.PQ, "common", "fips202.c")]
    inc = [f"-I{src}", f"-I{os.path.join(V.PQ, 'common')}", f"-I{os.path.join(V.FW1, 'include')}", f"-I{V.FW1}"]
    elf = os.path.join(d, "prog.elf")
    V.sh([*V.CC["clang"], "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections", f"-DKERNEL={k}",
          f"-DNS={V.NS[scheme]}", *inc, "-T", os.path.join(V.H, "fw", "link_rtl.ld"), os.path.join(V.H, "fw", "start_rtl.S"),
          os.path.join(V.FW1, "libc_min.c"), os.path.join(V.FW1, "rng.c"), os.path.join(V.H, "fw", "kernels.c"), *cfiles, "-o", elf])
    return d, elf


def main():
    rows = []
    for board, cfg in BOARDS.items():
        V.IMEM_AW, V.DMEM_AW = cfg["imem"], cfg["dmem"]
        for k in cfg["kernels"]:
            d, elf = build(k, board)
            sz = V.sh(["llvm-size", "-A", elf])
            text = sum(int(m) for m in re.findall(r"^\.text\s+(\d+)", sz, re.M))
            data = sum(int(m) for s_ in (".rodata", ".data", ".bss") for m in re.findall(rf"^\{s_}\s+(\d+)", sz, re.M))
            if text > (4 << cfg["imem"]) or data + 4096 > (4 << cfg["dmem"]):
                print(f"  {board} kernel {k}: does not fit (text {text} B, data {data} B)"); continue
            V.elf_to_hex(elf, d)
            for mf in (0, 1):
                out = os.path.join(V.B, f"tb_{board}_mf{mf}.vvp")
                if not os.path.exists(out):
                    core = [os.path.join(V.H, "core_rtl", f) for f in sorted(os.listdir(os.path.join(V.H, "core_rtl"))) if f.endswith((".v", ".sv"))]
                    V.sh(["iverilog", "-g2012", "-o", out, f"-Ptb_core.MUL_FAST={mf}", f"-Ptb_core.IMEM_AW={cfg['imem']}",
                          f"-Ptb_core.DMEM_AW={cfg['dmem']}", os.path.join(V.H, "tb_core.v"), *core])
                o = V.sh(["vvp", "-n", out], cwd=d)
                m = re.search(r"RESULT cycles=(\d+) retired=(\d+) a0=(\d+)", o)
                sim = V.run_sim(d, mf)
                rows.append((board, k, V.KERNELS[k][0], mf, text, data, int(m.group(1)), int(m.group(2)),
                             int(m.group(3)) & 0xffffffff, sim["cycles"]))
                print("  ", rows[-1])
    with open(os.path.join(KIT, "EXPECTED.md"), "w") as f:
        f.write("# Expected results for the board kit\n\nCycles = clock cycles from run-enable to `halted` "
                "(RTL testbench `tb_core.v`; the board's cycle counter may differ by a constant of a few cycles "
                "depending on where it starts counting). a0 = FNV-1a hash of the kernel outputs (also shown on LEDG[2] as a0 != 0).\n\n"
                "| Board | Kernel | MUL_FAST | IMEM/DMEM AW | code B | data B | RTL cycles | PQ-uArch cycles | retired | a0 (hex) |\n|---|---|---|---|---|---|---|---|---|---|\n")
        for b, k, name, mf, t, dt, cyc, ret, a0, sc in rows:
            f.write(f"| {b} | {k}: {name} | {mf} | {BOARDS[b]['imem']}/{BOARDS[b]['dmem']} | {t} | {dt} | {cyc} | {sc} | {ret} | {a0:08x} |\n")
        f.write("\n## Steps\n1. Copy `core_rtl/` into your Quartus project (or use your existing project).\n"
                "2. Set the top-level parameters `IMEM_AW` and `DMEM_AW` to the values above (and `MUL_FAST`).\n"
                "3. Copy `program.hex` and `data.hex` of one kernel into the project folder; compile; program the board.\n"
                "4. Press run; when LEDG[3] (halted) is lit, read the cycle counter in the In-System Sources and Probes Editor\n"
                "   and a0 in the In-System Memory Content Editor. Compare with the table. Report the difference in the paper.\n")
    print("wrote board_kit/EXPECTED.md")


if __name__ == "__main__":
    main()
