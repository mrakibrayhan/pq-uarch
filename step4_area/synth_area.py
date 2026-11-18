#!/usr/bin/env python3
"""Step 3: area of the PQC custom units and of a baseline RV32IM 5-stage core.

Flow: Yosys (yowasp-yosys) generic synthesis, two metrics from the same flow:
  * GE  : gates mapped by ABC to a simple cell set, weighted by a NAND2-equivalent
          table (approximate; see GE_WEIGHT) -- technology independent estimate
  * LUT4: generic 4-input LUT mapping (FPGA-style estimate)
It also checks the combinational units against Python models of the
simulator's semantics (random vectors via Yosys 'eval').
Writes ../results/E7_area.csv
Author: Md. Rakib Rayhan
"""
import csv, os, random, re, subprocess, sys

H = os.path.dirname(os.path.abspath(__file__))
RTL = "rtl"
RES = os.path.join(os.path.dirname(H), "results")
YOSYS = ["yowasp-yosys"]
# NAND2-equivalent weights (typical standard-cell ratios; approximate)
GE_WEIGHT = {"$_NOT_": 0.67, "$_AND_": 1.33, "$_NAND_": 1.0, "$_OR_": 1.33, "$_NOR_": 1.0, "$_XOR_": 2.33,
             "$_XNOR_": 2.33, "$_ANDNOT_": 1.33, "$_ORNOT_": 1.33, "$_MUX_": 2.33, "$_DFF_P_": 4.67,
             "$_SDFF_PP0_": 5.33, "$_SDFFE_PP0P_": 6.0, "$_DFFE_PP_": 5.67, "$_SDFFE_PP0N_": 6.0,
             "$_SDFF_PN0_": 5.33, "$_DFFE_PN_": 5.67, "$_SDFFCE_PP0P_": 6.0, "$_SDFFE_PN0P_": 6.0}


def yosys(script):
    r = subprocess.run(YOSYS + ["-p", script], capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-3000:], r.stderr[-3000:]); sys.exit(1)
    return r.stdout


def cells(stat):
    out = {}
    for m in re.finditer(r"^\s+(\d+)\s+.*?(\$_\w+_)\s*$", stat, re.M):
        out[m.group(2)] = out.get(m.group(2), 0) + int(m.group(1))
    if not out:  # older stat format: "  $_AND_   123"
        for m in re.finditer(r"^\s+(\$_\w+_)\s+(\d+)\s*$", stat, re.M):
            out[m.group(1)] = out.get(m.group(1), 0) + int(m.group(2))
    return out


def lut_count(stat):
    m = re.findall(r"^\s+(\d+)\s+.*\$lut\s*$", stat, re.M) or re.findall(r"^\s+\$lut\s+(\d+)\s*$", stat, re.M)
    return sum(int(x) for x in m)


def area(files, top, pre="", keep_mem=False):
    rd = " ".join(f"read_verilog -sv {f};" for f in files)
    if keep_mem:   # RAM arrays stay as memories: logic is counted in GE/LUT4, RAM reported in bits
        flow = f"{rd} {pre} hierarchy -top {top}; proc; flatten; opt; memory -nomap; opt; techmap; opt"
        yosys(f"{flow}; abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX; opt_clean; tee -q -o _st1.txt stat")
        s1 = open("_st1.txt").read(); os.remove("_st1.txt")
        yosys(f"{flow}; abc -lut 4; opt_clean; tee -q -o _st2.txt stat")
        s2 = open("_st2.txt").read(); os.remove("_st2.txt")
        c = cells(s1); ge = sum(GE_WEIGHT.get(k, 5.5) * n for k, n in c.items())
        ff = sum(n for k, n in c.items() if "DFF" in k)
        return dict(ge=round(ge), ff=ff, lut4=lut_count(s2), cells=sum(c.values()),
                    unknown=";".join(k for k in c if k not in GE_WEIGHT), ram_bits=3200)
    yosys(f"{rd} {pre} synth -flatten -top {top}; abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX; opt_clean; tee -q -o _st1.txt stat")
    s1 = open("_st1.txt").read(); os.remove("_st1.txt")
    c = cells(s1)
    unknown = [k for k in c if k not in GE_WEIGHT]
    ge = sum(GE_WEIGHT.get(k, 5.5) * n for k, n in c.items())
    ff = sum(n for k, n in c.items() if "DFF" in k)
    yosys(f"{rd} {pre} synth -flatten -top {top} -lut 4; tee -q -o _st2.txt stat")
    s2 = open("_st2.txt").read(); os.remove("_st2.txt")
    return dict(ge=round(ge), ff=ff, lut4=lut_count(s2), cells=sum(c.values()), unknown=";".join(unknown), ram_bits=0)


# ---------------------------------------------------------------- functional check
def s16(v): v &= 0xffff; return v - 0x10000 if v & 0x8000 else v
def s32(v): v &= 0xffffffff; return v - (1 << 32) if v & 0x80000000 else v
def kmred(a): t = s16(s16(a) * -3327); return s16((a - t * 3329) >> 16)
def kbar(a): t = s16((20159 * a + (1 << 25)) >> 26); return s16(a - s16(t * 3329))
def dmred(a): t = s32(a * 58728449); return s32((a - t * 8380417) >> 32)


def ev(o):
    m = re.search(r"\\y = (?:32'([01]+)|(\d+))", o)
    return int(m.group(1), 2) if m.group(1) else int(m.group(2))


def check():
    random.seed(1)
    n_ok = 0
    for _ in range(12):
        a, b = random.randint(-3328, 3328), random.randint(-3328, 3328)
        A, B = a & 0xffffffff, b & 0xffffffff
        o = yosys(f"read_verilog -sv {RTL}/pq_kmont.v; prep -top pq_kmont; eval -set op 1 -set a 32'b{A:032b} -set b 32'b{B:032b} -show y")
        y = ev(o)
        assert s32(y) == kmred(a * b), ("kmul", a, b, s32(y), kmred(a * b)); n_ok += 1
        lo, hi = random.randint(-3328, 3328), random.randint(-3328, 3328)
        P = (lo & 0xffff) | ((hi & 0xffff) << 16)
        for gs in (0, 1):
            o = yosys(f"read_verilog -sv {RTL}/pq_kbfly.v; prep -top pq_kbfly; eval -set gs {gs} -set a 32'b{P:032b} -set b 32'b{B:032b} -show y")
            y = ev(o)
            if gs == 0:
                t = kmred(s16(b) * hi); exp = (s16(lo + t) & 0xffff) | ((s16(lo - t) & 0xffff) << 16)
            else:
                exp = (kbar(s16(lo + hi)) & 0xffff) | ((kmred(s16(b) * s16(hi - lo)) & 0xffff) << 16)
            assert y == exp, ("kbfly", gs, lo, hi, b, hex(y), hex(exp)); n_ok += 1
        a, b = random.randint(-(1 << 31), (1 << 31) - 1), random.randint(-8380416, 8380416)
        o = yosys(f"read_verilog -sv {RTL}/pq_dmont.v; prep -top pq_dmont; eval -set a 32'b{a & 0xffffffff:032b} -set b 32'b{b & 0xffffffff:032b} -show y")
        y = ev(o)
        assert s32(y) == dmred(a * b), ("dmul", a, b); n_ok += 1
    print(f"RTL functional check: {n_ok} vectors OK (kmul, kct, kgs, dmul)")
    # Keccak units: RTL simulation against the Python reference (tb/)
    subprocess.run(["python3", "keccak_ref.py", "1", "4"], cwd="tb", check=True)
    for top in ("pq_keccak", "pq_keccak_ls"):
        subprocess.run(["iverilog", "-g2012", f"-DDUT={top}", "-o", f"tb/_{top}", "tb/tb_keccak.v", f"rtl/{top}.v"], check=True)
        o = subprocess.run(["vvp", "-n", f"_{top}"], cwd="tb", capture_output=True, text=True).stdout
        assert "KECCAK_CHECK errors=0" in o, o
        print(f"{top}: 4 Keccak-f[1600] vectors OK; " + re.findall(r"permutation cycles=\d+", o)[-1])
        os.remove(f"tb/_{top}")


def main():
    os.chdir(H)  # yowasp (WASI) can only write inside the working folder
    check()
    rows = []
    units = [("pq.kmul/kmred/kbar (ML-KEM modmul)", ["pq_kmont.v"], "pq_kmont"),
             ("pq.kct/kgs (ML-KEM packed butterfly)", ["pq_kbfly.v"], "pq_kbfly"),
             ("pq.dmul (ML-DSA modmul)", ["pq_dmont.v"], "pq_dmont"),
             ("pq.keccak (Keccak-f[1600], 1 round/cycle)", ["pq_keccak.v"], "pq_keccak"),
             ("pq.keccak-ls (lane-serial, state in 2x25x64-bit RAM)", ["pq_keccak_ls.v"], "pq_keccak_ls"),
             ("RV32M 32x32 single-cycle multiplier (reference)", ["rv32m_mul.v"], "rv32m_mul")]
    import json
    cache_p = "area_cache.json"
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    for name, fs, top in units:
        if top not in cache:
            cache[top] = area([os.path.join(RTL, f) for f in fs], top, keep_mem=(top == "pq_keccak_ls"))
            json.dump(cache, open(cache_p, "w"), indent=1)
        a = dict(cache[top]); a.setdefault("ram_bits", 0)
        rows.append(dict(block=name, **a)); print(rows[-1])
    core = os.environ.get("CORE_RTL")
    if core and os.path.isdir(core):
        fs = [os.path.join(core, f) for f in sorted(os.listdir(core)) if f.endswith((".v", ".sv"))
              and not f.startswith(("top_", "debounce", "snapshot", "imem", "dmem"))]
        bb = "".join(f"read_verilog -sv -lib {os.path.join(core, f)}; " for f in os.listdir(core)
                     if f.startswith(("imem", "dmem", "snapshot")))
        a = area(fs, "cpu_top_pipe_riscv", pre=bb)
        rows.append(dict(block="Baseline RV32IM 5-stage core (author's FPGA core, no imem/dmem)", **a)); print(rows[-1])
    os.makedirs(RES, exist_ok=True)
    with open(os.path.join(RES, "E7_area.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("wrote E7_area.csv")


if __name__ == "__main__":
    main()
