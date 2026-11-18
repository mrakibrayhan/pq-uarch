# PQ-uArch: FIPS 203/204 Lattice Cryptography on Embedded In-Order RISC-V Pipelines

Cycle-level simulation study of **ML-KEM (FIPS 203)** and **ML-DSA (FIPS 204)** on a
parameterised single-issue, in-order, 5-stage RV32IM pipeline. It covers three questions:

1. **Performance:** where the cycles go, and which microarchitecture knobs matter (branch
   predictor, multiplier, divider, caches, return-address stack).
2. **ISA extensions:** what lightweight PQC custom instructions give for their area. The
   instructions are Montgomery/Barrett, packed NTT butterflies, an ML-DSA modmul, a
   fixed-latency multiply, and Keccak-f[1600] as a one-round-per-cycle unit or a lane-serial
   unit. All are RTL-verified and synthesised.
3. **Timing leakage as a microarchitecture property:** does "constant-time" PQClean code stay
   constant-time on cores with early-terminating dividers or multipliers, predictors and caches,
   with two compilers? This uses a TVLA Welch t-test with effect sizes, and locates each leak to
   the function that causes it.

The timing model is **validated cycle-exactly against the RTL** of the author's FPGA-proven
RV32IM 5-stage core.

Author: Md. Rakib Rayhan, MESIL Lab, Dept. of ECE, North South University.
Target venue: *Journal of Systems Architecture* (Elsevier).

---

## Step-by-step guide (do these in order)

### Step 0: Set up (about 3 min)
```bash
sudo apt install clang lld iverilog gcc-riscv64-unknown-elf
python3 -m pip install numpy pandas matplotlib yowasp-yosys
```
Versions used: clang 18.1.3, riscv64-unknown-elf-gcc 13.2.0, Icarus Verilog 12.0, Yosys 0.71.
The PQClean sources (commit `0586a824`) are already in `step1_simulator/pqclean/`.

### Step 1: Build and verify the simulator (about 5 min)
```bash
cd step1_simulator
python3 build.py          # rvsim + all RV32IM builds (clang and gcc) + native builds; bit-exact check
python3 verify_timing.py  # micro-benchmarks with hand-derived cycle counts
```
Output: `results/E0_functional_check.json`. Every build must say `match_native: true`.
It also records the number of division instructions per build, which is the compiler effect.

### Step 2: Validate the timing model against your core's RTL (about 30 min)
```bash
cd ../step2_rtl_validation
python3 run_rtl_validation.py A     # calibration: 13 micro-benchmarks, RTL vs simulator
python3 run_rtl_validation.py B     # held-out kernels incl. full ML-KEM/ML-DSA, clang + gcc, both multipliers
python3 make_board_kit.py           # optional: hex files + expected cycles for the FPGA boards
```
Output: `results/V1_calibration*.csv`, `results/V2_rtl_validation.csv`, `board_kit/`.
`core_rtl/` is your unmodified RV32IM pipelined core (commit in `SOURCE_COMMIT.txt`).

### Step 3: Run the experiments (about 45 min on 2 cores)
```bash
cd ../step3_experiments
python3 run_experiments.py              # all of E1–E6c
python3 run_experiments.py E4 E5        # or just some of them
```
| Exp. | What | Output |
|---|---|---|
| E1 | cycle profile by kernel (core C1-TB5) | `E1_profile.csv`, `E1_ops.csv` |
| E2 | microarchitecture DSE, 36 cores × 6 schemes | `E2_dse.csv` |
| E3 | I/D-cache size sweep 1–32 KB, base vs. extended code | `E3_cache.csv` |
| E4 | ISA-extension speed-ups on 4 reference cores; lane-serial Keccak; gcc builds | `E4_extensions.csv` |
| E5 | Keccak-unit latency 28–5000 cycles; modmul latency | `E5_unit_latency.csv` |
| E6 | TVLA leakage, all ML-KEM levels, 400 trials, 6 hardware × 5 code variants × 2 tests | `E6_leakage.csv` |
| E6b | which functions execute input-dependent mul/div latency | `E6b_leak_localisation.csv` |
| E6c | ML-KEM-768, 1000 trials, effect sizes, pre-2024 code and gcc builds | `E6c_leakage_long.csv` |

### Step 4: Area of the custom units (about 30 min, mostly the Keccak units)
```bash
cd ../step4_area
CORE_RTL=rtl_core python3 synth_area.py
```
It checks the modmul and butterfly RTL against the simulator semantics (48 vectors). It checks
both Keccak units in Icarus Verilog against a Python reference. It then runs Yosys area for
every unit and for your core. Output: `results/E7_area.csv`. Results are cached in
`area_cache.json`; delete that file to re-synthesise.

### Step 5: Figures and tables (about 15 s)
```bash
cd ../step5_figures
python3 make_figures.py   # figures/fig2..fig8 (.pdf + .png), tables/*.tex/*.csv
```

### Step 6: Paper skeleton (about 5 s)
```bash
cd ../step6_paper
python3 make_facts.py     # facts.tex (every number as a LaTeX macro), leak_facts.tex, tables
```
Compile `main.tex` on Overleaf with Elsevier's `elsarticle` template.
`skeleton_preview.pdf` is a preview built with a stand-in class.
**The prose is yours to write.** Every `[AUTHOR TO WRITE]` box has a FACTS list under it with
numbers taken straight from the results. Anything marked `[CHECK WITH AUTHOR]` is unverified.

---

## Repository layout
| Path | Contents |
|---|---|
| `step1_simulator/sim/rvsim.c` | RV32IM ISS + cycle-level timing model + custom-0 PQC instructions |
| `step1_simulator/firmware/` | start-up code, minimal libc, harness, intrinsics (`pqext.h`), timing tests |
| `step1_simulator/pqclean/` | PQClean clean ML-KEM/ML-DSA sources (unmodified; variants are patched copies in `build/src`) |
| `step1_simulator/build.py` | patcher + cross-compilers + native cross-check |
| `step2_rtl_validation/` | RTL testbench, author's core RTL, validation kernels, board kit |
| `step3_experiments/` | experiment driver (`run_experiments.py`, `common.py`) |
| `step4_area/` | unit RTL (`rtl/`), Keccak testbench (`tb/`), baseline core RTL (`rtl_core/`), Yosys flow |
| `step5_figures/` | figure and table generation |
| `step6_paper/` | `main.tex`, `references.bib`, `make_facts.py`, preview PDF |
| `results/`, `figures/`, `tables/` | generated outputs |

## Code variants
| Variant | Meaning |
|---|---|
| `base` | unmodified PQClean clean code, clang -O2 |
| `Os` | same code, clang -Os |
| `prefix` | ML-KEM pre-2024 reference code: `/ KYBER_Q` in C in `poly_tomsg` and `poly(vec)_compress` (the code KyberSlash attacked) |
| `kslash` | ML-KEM `poly_tomsg` with a division the compiler cannot remove |
| `m` | modular-arithmetic instructions (pq.kmul/kmred/kbar, pq.dmul) |
| `mb` | `m` + packed NTT butterflies (ML-KEM) |
| `k` / `k-ls` | Keccak-f[1600] instruction, one-round-per-cycle unit (124 cycles) / lane-serial unit (2500 cycles) |
| `all` / `all-ls` | `mb` + `k` / `mb` + `k-ls` |
| `allz` | `all` + compress/`tomsg` constant multiplies on the fixed-latency `pq.cmul` (ML-KEM) |
| `*-gccO2`, `*-gccOs` | same source built with riscv64-unknown-elf-gcc 13 |

## Simulator options (`build/rvsim prog.elf key=value ...`)
`bp=nt|btfn|bimodal|gshare bpbits=9 brpen=2 jalpen=1 ras=1 mul=1|3p|iter|early|earlyany
mul_it=32 mul_hix=1 div=iter|early div_it=34 loaduse=1 ic_kb=0 ic_ways=2 dc_kb=0 dc_ways=2 line=32
memlat=10 lat_kmul=1 lat_kbfly=2 lat_dmul=2 lat_keccak=124 profile=1 latmap=0 out=file.json`

To model the author's FPGA core, use `bp=nt brpen=2 jalpen=2 ras=0 loaduse=1 mul=iter mul_it=35
mul_hix=0 div=iter div_it=39` (serial multiplier) or `mul_it=4` (embedded multiplier). See Step 2.

## Licence
MIT for the PQ-uArch code and the author's core RTL. PQClean code keeps its own licences
(see each `LICENSE`).
