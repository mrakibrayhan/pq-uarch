#!/usr/bin/env python3
"""Step 2: validate the PQ-uArch timing model against the RTL of a real FPGA-proven core.

The author's RV32IM 5-stage pipelined core (core_rtl/, unmodified, tested on a Cyclone IV
board) is simulated cycle by cycle with Icarus Verilog. The same ELF binaries run on the
PQ-uArch simulator configured to match that core ("C-RTL" config). Steps:
  A. calibration: 13 micro-benchmark patterns -> per-instruction costs on RTL vs simulator
  B. held-out validation: PQC kernels and full ML-KEM / ML-DSA runs, clang and gcc builds,
     both multiplier options of the core (MUL_FAST = 0 serial, 1 embedded multiplier)
     -> cycle error and bit-exact a0 hash (RTL vs simulator vs native x86)
Writes ../results/V1_calibration.csv, ../results/V2_rtl_validation.csv
Author: Md. Rakib Rayhan
"""
import csv, json, os, re, shutil, subprocess, sys, time
from multiprocessing import Pool

H = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(H)
SIM = os.path.join(ROOT, "step1_simulator", "build", "rvsim")
PQ = os.path.join(ROOT, "step1_simulator", "pqclean"); FW1 = os.path.join(ROOT, "step1_simulator", "firmware")
B = os.path.join(H, "build"); RES = os.path.join(ROOT, "results")
IMEM_AW, DMEM_AW = 14, 15
# simulator configuration that matches the RTL core (calibrated in step A, see README)
def crtl(mul_fast):
    return dict(bp="nt", brpen=2, jalpen=2, ras=0, loaduse=1, mul="iter", div="iter",
                mul_it=(4 if mul_fast else 35), mul_hix=0, div_it=39)  # EX occupancy measured in step A

CC = {"clang": ["clang", "--target=riscv32", "-march=rv32im", "-mabi=ilp32", "-O2", "-ffreestanding", "-nostdlib",
                "-fno-builtin", "-fuse-ld=lld", "-mno-relax", "-Wno-unused-command-line-argument"],
      "gcc": ["riscv64-unknown-elf-gcc", "-march=rv32im", "-mabi=ilp32", "-O2", "-ffreestanding", "-nostdlib",
              "-fno-builtin", "-mno-relax", "-Wl,--no-relax"]}
KERNELS = {1: ("SHAKE256, 1 KB", "ml-kem-512"), 2: ("ML-KEM NTT+INTT x2", "ml-kem-512"),
           3: ("ML-DSA NTT+INTT", "ml-dsa-44"), 4: ("ML-KEM-512 K+E+D", "ml-kem-512"),
           5: ("ML-KEM-768 K+E+D", "ml-kem-768"), 6: ("ML-DSA-44 K+S+V", "ml-dsa-44")}
NS = {"ml-kem-512": "PQCLEAN_MLKEM512_CLEAN", "ml-kem-768": "PQCLEAN_MLKEM768_CLEAN", "ml-dsa-44": "PQCLEAN_MLDSA44_CLEAN"}
PATTERNS = {1: "ALU (addi)", 2: "load + dependent use", 3: "store + load", 4: "taken branch", 5: "not-taken branch",
            6: "jal", 7: "call + return", 8: "mul", 9: "mulh", 10: "mulhu", 11: "div", 12: "remu", 13: "mul + dependent add"}


def sh(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode:
        raise RuntimeError(" ".join(cmd) + "\n" + r.stdout[-2000:] + r.stderr[-2000:])
    return r.stdout


def elf_to_hex(elf, d):
    """imem image (exec segment) -> program.hex, everything else -> data.hex (word per line)."""
    e = open(elf, "rb").read()
    u32 = lambda o: int.from_bytes(e[o:o + 4], "little")
    phoff, phnum = u32(28), int.from_bytes(e[44:46], "little")
    imem = bytearray(4 << IMEM_AW); dmem = bytearray(4 << DMEM_AW)
    for i in range(phnum):
        p = phoff + 32 * i
        if u32(p) != 1: continue
        off, va, fs, ms, fl = u32(p + 4), u32(p + 8), u32(p + 16), u32(p + 20), u32(p + 24)
        seg = e[off:off + fs] + bytes(ms - fs)
        if fl & 1:
            assert va + ms <= len(imem), "code does not fit IMEM"; imem[va:va + ms] = seg
        else:   # the core indexes addr[DMEM_AW+1:2]: data linked at 0x10000 aliases to the RAM start
            a = va % len(dmem); assert a + ms <= len(dmem), "data does not fit DMEM"; dmem[a:a + ms] = seg
    for name, mem in (("program.hex", imem), ("data.hex", dmem)):
        with open(os.path.join(d, name), "w") as f:
            for k in range(0, len(mem), 4):
                f.write(f"{int.from_bytes(mem[k:k + 4], 'little'):08x}\n")


def build_kernel(k, cc):
    scheme = KERNELS[k][1]; src = os.path.join(PQ, scheme)
    d = os.path.join(B, f"k{k}_{cc}"); os.makedirs(d, exist_ok=True)
    cfiles = [os.path.join(src, f) for f in sorted(os.listdir(src)) if f.endswith(".c")] + [os.path.join(PQ, "common", "fips202.c")]
    inc = [f"-I{src}", f"-I{os.path.join(PQ, 'common')}", f"-I{os.path.join(FW1, 'include')}", f"-I{FW1}"]
    elf = os.path.join(d, "prog.elf")
    sh([*CC[cc], f"-DKERNEL={k}", f"-DNS={NS[scheme]}", *inc, "-T", os.path.join(H, "fw", "link_rtl.ld"),
        os.path.join(H, "fw", "start_rtl.S"), os.path.join(FW1, "libc_min.c"), os.path.join(FW1, "rng.c"),
        os.path.join(H, "fw", "kernels.c"), *cfiles, "-o", elf] + (["-lgcc"] if cc == "gcc" else []))
    nat = os.path.join(d, "native")
    sh(["gcc", "-O2", f"-DKERNEL={k}", f"-DNS={NS[scheme]}", f"-I{src}", f"-I{os.path.join(PQ, 'common')}", f"-I{FW1}",
        "-Dmain=kmain", os.path.join(H, "fw", "kernels.c"), os.path.join(FW1, "rng.c"), *cfiles,
        os.path.join(H, "fw", "native_main.c"), "-o", nat])
    elf_to_hex(elf, d)
    return d


def build_calib(pat, n):
    d = os.path.join(B, f"c{pat}_{n}"); os.makedirs(d, exist_ok=True)
    elf = os.path.join(d, "prog.elf")
    sh([*CC["clang"], f"-DPATTERN={pat}", f"-DN={n}", "-T", os.path.join(H, "fw", "link_rtl.ld"),
        os.path.join(H, "fw", "calib.S"), "-o", elf])
    elf_to_hex(elf, d)
    return d


def vvp_bin(mf):
    out = os.path.join(B, f"tb_mf{mf}.vvp")
    if not os.path.exists(out):
        core = [os.path.join(H, "core_rtl", f) for f in sorted(os.listdir(os.path.join(H, "core_rtl"))) if f.endswith((".v", ".sv"))]
        sh(["iverilog", "-g2012", "-o", out, f"-Ptb_core.MUL_FAST={mf}", f"-Ptb_core.IMEM_AW={IMEM_AW}",
            f"-Ptb_core.DMEM_AW={DMEM_AW}", os.path.join(H, "tb_core.v"), *core])
    return out


def run_rtl(d, mf):
    t0 = time.time()
    o = sh(["vvp", "-n", vvp_bin(mf)], cwd=d)
    m = re.search(r"RESULT cycles=(\d+) retired=(\d+) a0=(\d+) halted=(\d) fault=(\d)", o)
    if not m:
        print(o[-1500:]); sys.exit(1)
    return dict(cycles=int(m.group(1)), retired=int(m.group(2)), a0=int(m.group(3)) & 0xffffffff,
                halted=int(m.group(4)), fault=int(m.group(5)), wall_s=round(time.time() - t0, 1))


def run_sim(d, mf):
    o = json.loads(sh([SIM, os.path.join(d, "prog.elf"), "profile=0", *[f"{k}={v}" for k, v in crtl(mf).items()]]))
    return dict(cycles=o["cycles"], retired=o["instret"], a0=o["a0"] & 0xffffffff)


def _calib(a):
    pat, mf = a
    r = {}
    for n in (0, 64):
        d = build_calib(pat, n); r[n] = (run_rtl(d, mf), run_sim(d, mf))
    rtl = (r[64][0]["cycles"] - r[0][0]["cycles"]) / 64; sim = (r[64][1]["cycles"] - r[0][1]["cycles"]) / 64
    return dict(pattern=PATTERNS[pat], mul_fast=mf, rtl_cyc_per_pattern=round(rtl, 3), sim_cyc_per_pattern=round(sim, 3),
                match=int(abs(rtl - sim) < 1e-9), rtl_offset=r[0][0]["cycles"], sim_offset=r[0][1]["cycles"])


def _kernel(a):
    k, cc, mf = a
    d = os.path.join(B, f"k{k}_{cc}")
    rtl, sim = run_rtl(d, mf), run_sim(d, mf)
    nat = int(sh([os.path.join(d, "native")]).strip()) & 0xffffffff
    err = (sim["cycles"] - rtl["cycles"]) / rtl["cycles"] * 100
    return dict(kernel=KERNELS[k][0], compiler=cc, mul_fast=mf, rtl_cycles=rtl["cycles"], sim_cycles=sim["cycles"],
                error_pct=round(err, 4), rtl_retired=rtl["retired"], sim_retired=sim["retired"],
                hash_rtl=rtl["a0"], hash_sim=sim["a0"], hash_native=nat,
                bit_exact=int(rtl["a0"] == sim["a0"] == nat and not rtl["fault"]), rtl_wall_s=rtl["wall_s"])


def wcsv(name, rows):
    with open(os.path.join(RES, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("  wrote", name)


if __name__ == "__main__":
    os.makedirs(B, exist_ok=True); os.makedirs(RES, exist_ok=True)
    nproc = os.cpu_count() or 1
    vvp_bin(0); vvp_bin(1)
    which = sys.argv[1:] or ["A", "B"]
    if "A" in which:
        print("[A] calibration micro-benchmarks")
        with Pool(nproc) as p:
            rows = p.map(_calib, [(pt, mf) for mf in (0, 1) for pt in PATTERNS], chunksize=1)
        for r in rows: print("  ", r)
        wcsv("V1_calibration.csv", rows)
    if "B" in which:
        print("[B] held-out kernels")
        ks = [int(x) for x in os.environ.get("KERNELS", "1,2,3,4,5,6").split(",")]
        for k in ks:
            for cc in CC: build_kernel(k, cc)
        jobs = [(k, cc, mf) for k in ks for cc in CC for mf in (0, 1)]
        with Pool(nproc) as p:
            rows = p.map(_kernel, jobs, chunksize=1)
        for r in rows: print("  ", r)
        wcsv("V2_rtl_validation.csv", rows)
