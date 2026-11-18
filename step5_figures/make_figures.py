#!/usr/bin/env python3
"""Step 4: figures (PDF + PNG) and LaTeX tables from ../results/*.csv.
Author: Md. Rakib Rayhan
"""
import json, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

H = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(os.path.dirname(H), "results")
FIG = os.path.join(os.path.dirname(H), "figures")
TAB = os.path.join(os.path.dirname(H), "tables")
os.makedirs(FIG, exist_ok=True); os.makedirs(TAB, exist_ok=True)

# validated categorical palette (fixed order), text inks, sequential blue ramp
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
SEQ = LinearSegmentedColormap.from_list("seq", ["#f2f6fc", "#a9c7ef", "#2a78d6", "#123a6b"])
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
                     "legend.frameon": False, "savefig.bbox": "tight", "savefig.dpi": 300})
KEMS = ["ml-kem-512", "ml-kem-768", "ml-kem-1024"]; DSAS = ["ml-dsa-44", "ml-dsa-65", "ml-dsa-87"]
LBL = {s: s.upper().replace("ML-KEM-", "ML-KEM-").replace("ML-DSA-", "ML-DSA-") for s in KEMS + DSAS}
gm = lambda x: float(np.exp(np.log(np.asarray(x, float)).mean()))


def save(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(FIG, f"{name}.{ext}"))
    plt.close(fig); print("  ", name)


def rd(name, **kw):
    return pd.read_csv(os.path.join(RES, name), **kw)


# ------------------------------------------------------------------ Fig 2: profile
def fig_profile():
    d = rd("E1_profile.csv")
    order = ["Keccak-f[1600]", "SHAKE/SHA3 glue", "NTT / INTT", "Pointwise / basemul", "Modular reduction",
             "Sampling", "Pack / compress / round", "Poly add/sub/shift"]
    d["cat"] = d.category.where(d.category.isin(order), "Other")
    cats = order + ["Other"]
    cols = CAT + ["#b9b8b2"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9), sharey=True)
    for ax, group in zip(axes, [KEMS, DSAS]):
        sub = d[d.scheme.isin(group)]
        piv = sub.pivot_table(index=["scheme", "op"], columns="cat", values="share", aggfunc="sum").fillna(0)
        piv = piv.reindex(columns=cats, fill_value=0)
        opord = ["KeyGen", "Encaps", "Decaps", "Sign", "Verify"]
        piv = piv.loc[[(s, o) for s in group for o in sorted(piv.loc[s].index, key=opord.index)]]
        x = np.arange(len(piv)); bottom = np.zeros(len(piv))
        for c, col in zip(cats, cols):
            v = piv[c].values * 100
            ax.bar(x, v, bottom=bottom, color=col, width=0.72, edgecolor="white", linewidth=0.8, label=c)
            bottom += v
        ax.set_xticks(x); ax.set_xticklabels([f"{o[0]}\n{s.split('-')[-1]}" for s, o in piv.index], fontsize=6.5)
        ax.set_title("ML-KEM: K = KeyGen, E = Encaps, D = Decaps" if group == KEMS else "ML-DSA: K = KeyGen, S = Sign, V = Verify", fontsize=8, color=INK)
        ax.set_ylim(0, 100); ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Share of cycles (%)")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, ncol=5, loc="upper center", bbox_to_anchor=(0.5, 1.13), fontsize=6.8)
    save(fig, "fig2_cycle_profile")


# ------------------------------------------------------------------ Fig 3: DSE heatmap
def fig_dse():
    d = rd("E2_dse.csv", dtype={"mul": str}); d["key"] = d.scheme + d.op
    ref = d[(d.bp == "nt") & (d["mul"] == "iter") & (d.mem == "sram")].set_index("key").cycles
    d["sp"] = d.key.map(ref) / d.cycles
    bps = ["nt", "btfn", "bimodal", "gshare"]; muls = ["iter", "3p", "1"]; mems = ["sram", "c16k", "c4k"]
    mlab = {"iter": "iter-32", "3p": "pipe-3", "1": "1-cycle"}
    memlab = {"sram": "1-cycle SRAM", "c16k": "16 KB I-/D-cache", "c4k": "4 KB I-/D-cache"}
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 3.9), sharex=True, sharey=True)
    rows = []
    for i, (nm, grp) in enumerate([("ML-KEM", KEMS), ("ML-DSA", DSAS)]):
        for j, mem in enumerate(mems):
            sub = d[d.scheme.isin(grp) & (d.mem == mem)]
            M = np.array([[gm(sub[(sub.bp == b) & (sub["mul"] == m)].sp) for m in muls] for b in bps])
            ax = axes[i, j]; ax.grid(False)
            ax.imshow(M, cmap=SEQ, vmin=0.75, vmax=2.4, aspect="auto")
            for a in range(len(bps)):
                for b in range(len(muls)):
                    ax.text(b, a, f"{M[a, b]:.2f}", ha="center", va="center", fontsize=7,
                            color="white" if M[a, b] > 1.75 else INK)
                    rows.append(dict(family=nm, mem=mem, bp=bps[a], mul=muls[b], speedup=round(M[a, b], 3)))
            ax.set_xticks(range(3)); ax.set_xticklabels([mlab[m] for m in muls])
            ax.set_yticks(range(4)); ax.set_yticklabels(bps)
            if i == 0: ax.set_title(memlab[mem], fontsize=8, color=INK)
            if j == 0: ax.set_ylabel(f"{nm}\nbranch predictor")
            if i == 1: ax.set_xlabel("multiplier")
    pd.DataFrame(rows).to_csv(os.path.join(TAB, "dse_speedup_geomean.csv"), index=False)
    fig.suptitle("Speed-up over the minimal core (static-NT, iterative multiplier, SRAM); geometric mean over levels and operations",
                 fontsize=7.5, color=INK2, y=1.0)
    save(fig, "fig3_dse_heatmap")


# ------------------------------------------------------------------ Fig 4: cache sensitivity
def fig_cache():
    d = rd("E3_cache.csv")
    e4 = rd("E4_extensions.csv"); sram = e4[e4.core == "C2-Emb"].set_index(["scheme", "variant", "op"]).cycles
    d["slow"] = [c / sram[(s, v, o)] for s, v, o, c in zip(d.scheme, d.variant, d.op, d.cycles)]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.5))
    kbs = sorted(d.cache_kb.unique())
    for k, (nm, grp) in enumerate([("ML-KEM", KEMS), ("ML-DSA", DSAS)]):
        for v, col, lab in [("base", CAT[0], "PQClean C (base)"), ("all", CAT[1], "with PQC instructions (all)")]:
            y = [gm(d[(d.cache_kb == kb) & (d.variant == v) & d.scheme.isin(grp)].slow) for kb in kbs]
            axes[0].plot(kbs, y, marker="o" if k == 0 else "s", ms=4, lw=2, color=col, ls="-" if k == 0 else "--",
                         label=f"{nm}, {lab}")
            ic = [d[(d.cache_kb == kb) & (d.variant == v) & d.scheme.isin(grp)].ic_miss.mean() * 100 for kb in kbs]
            axes[1].plot(kbs, ic, marker="o" if k == 0 else "s", ms=4, lw=2, color=col, ls="-" if k == 0 else "--")
    for ax in axes: ax.set_xscale("log", base=2); ax.set_xticks(kbs); ax.set_xticklabels([f"{k}" for k in kbs]); ax.set_xlabel("I-cache = D-cache size (KB); 2-way, 32-B lines, 20-cycle memory")
    axes[0].axhline(1, color=INK2, lw=0.8); axes[0].set_ylabel("Cycles / cycles with 1-cycle SRAM")
    axes[1].set_ylabel("I-cache miss rate (%)")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, ncol=4, fontsize=6.5, loc="upper center", bbox_to_anchor=(0.5, 1.08))
    save(fig, "fig4_cache_sensitivity")


# ------------------------------------------------------------------ Fig 5: extension speedups
def fig_ext():
    d = rd("E4_extensions.csv")
    base = d[d.variant == "base"].set_index(["scheme", "core", "op"]).cycles
    d["sp"] = [base[(s, c, o)] / y for s, c, o, y in zip(d.scheme, d.core, d.op, d.cycles)]
    vs = [("m", "modmul"), ("mb", "modmul + butterfly"), ("k", "Keccak"), ("all", "all"), ("allz", "all + fixed-lat. compress mul")]
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    schemes = KEMS + DSAS; w = 0.16; x = np.arange(len(schemes))
    rows = []
    for i, (v, lab) in enumerate(vs):
        y = []
        for s in schemes:
            sub = d[(d.scheme == s) & (d.variant == v) & (d.core == "C1-TB5")]
            y.append(gm(sub.sp) if len(sub) else np.nan)
        ax.bar(x + (i - 2) * w, y, width=w - 0.02, color=CAT[i], label=lab)
        for s, yy in zip(schemes, y): rows.append(dict(scheme=s, variant=v, speedup_geomean=round(yy, 3) if yy == yy else ""))
    ax.set_xticks(x); ax.set_xticklabels([LBL[s] for s in schemes]); ax.set_ylabel("Speed-up over base (geomean of ops)")
    ax.axhline(1, color=INK2, lw=0.8); ax.legend(ncol=5, fontsize=6.5, loc="upper center", bbox_to_anchor=(0.5, 1.17))
    ax.grid(axis="x", visible=False)
    pd.DataFrame(rows).to_csv(os.path.join(TAB, "ext_speedup_C1.csv"), index=False)
    save(fig, "fig5_extension_speedup")


# ------------------------------------------------------------------ Fig 6: unit latency
def fig_latency():
    d = rd("E5_unit_latency.csv"); e4 = rd("E4_extensions.csv")
    base = e4[(e4.variant == "base") & (e4.core == "C1-TB5")].set_index(["scheme", "op"]).cycles
    d["sp"] = [base[(s, o)] / c for s, o, c in zip(d.scheme, d.op, d.cycles)]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.4))
    for k, knob in enumerate(["lat_keccak", "lat_modmul"]):
        ax = axes[k]
        for i, s in enumerate(KEMS + DSAS):
            sub = d[(d.knob == knob) & (d.scheme == s)]
            vals = sorted(sub.value.unique())
            ax.plot(vals, [gm(sub[sub.value == v].sp) for v in vals], marker="o", ms=4, lw=2, color=CAT[i], label=LBL[s])
        ax.set_xlabel("Keccak instruction latency (cycles)" if k == 0 else "modmul / butterfly latency (cycles)")
        ax.set_ylabel("Speed-up over base")
        if k == 0:
            ax.set_xscale("log"); tk = sorted(d[d.knob == "lat_keccak"].value.unique())
            ax.set_xticks(tk); ax.set_xticklabels([str(int(v)) for v in tk], fontsize=6.5)
            ax.axvline(124, color=INK2, lw=0.6, ls=":"); ax.axvline(2500, color=INK2, lw=0.6, ls=":")
            ax.text(124, ax.get_ylim()[0], " 1-round unit", fontsize=6, color=INK2, va="bottom")
            ax.text(2500, ax.get_ylim()[0], " lane-serial", fontsize=6, color=INK2, va="bottom")
    axes[0].legend(fontsize=6.3, ncol=2)
    save(fig, "fig6_unit_latency")


# ------------------------------------------------------------------ Fig 7: leakage
def fig_leak():
    p = os.path.join(RES, "E6c_leakage_long.csv")
    if not os.path.exists(p): print("   (E6c missing)"); return
    d = pd.read_csv(p)
    hws = ["CT-ref", "EarlyDiv", "EarlyMul-rs2", "EarlyMul-any"]
    vs = ["base", "prefix", "prefix-gccO2", "prefix-gccOs", "kslash", "base-gccO2", "m", "all", "all-gccO2", "allz", "allz-gccO2"]
    vlab = {"base": "PQClean (clang -O2)", "prefix": "pre-2024 code (clang -O2)", "prefix-gccO2": "pre-2024 code (gcc -O2)",
            "prefix-gccOs": "pre-2024 code (gcc -Os)", "kslash": "forced division (clang)", "base-gccO2": "PQClean (gcc -O2)",
            "m": "+modmul ISE", "all": "+all ISE", "all-gccO2": "+all ISE (gcc)", "allz": "+all ISE + fixed-lat. compress",
            "allz-gccO2": "+all ISE + fixed-lat. compress (gcc)"}
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.6), sharey=True)
    for k, test in enumerate(["fixed-vs-random ct", "valid-vs-invalid ct"]):
        ax = axes[k]; ax.grid(False)
        sub = d[(d.scheme == "ml-kem-768") & (d.test == test)]
        M = np.zeros((len(vs), len(hws))); T = [[""] * len(hws) for _ in vs]
        for a, v in enumerate(vs):
            for b, hw in enumerate(hws):
                r = sub[(sub.variant == v) & (sub.hw == hw)].iloc[0]
                t = float("inf") if str(r.t) == "inf" else abs(float(r.t))
                M[a, b] = min(np.log10(1 + t), 3)
                T[a][b] = ("∞" if t == float("inf") else f"{t:.0f}" if t >= 10 else f"{t:.1f}")
        ax.imshow(M, cmap=SEQ, vmin=0, vmax=3, aspect="auto")
        for a in range(len(vs)):
            for b in range(len(hws)):
                leak = M[a, b] > np.log10(1 + 4.5)
                ax.text(b, a, T[a][b] + (" ●" if leak else ""), ha="center", va="center", fontsize=6.5,
                        color="white" if M[a, b] > 1.6 else INK)
        ax.set_xticks(range(len(hws))); ax.set_xticklabels(hws, rotation=30, ha="right", fontsize=6.5)
        ax.set_yticks(range(len(vs))); ax.set_yticklabels([vlab[v] for v in vs], fontsize=6.8)
        ax.set_title(f"{test}", fontsize=7.5, color=INK)
    fig.text(0.5, -0.08, "ML-KEM-768 decapsulation, 1000 trials. Cell = |t| (Welch); ● = |t| > 4.5. Effect sizes in tables/E6c.",
             ha="center", fontsize=6.5, color=INK2)
    save(fig, "fig7_leakage")


# ------------------------------------------------------------------ Fig 8: area vs speed-up
def fig_area():
    p = os.path.join(RES, "E7_area.csv")
    if not os.path.exists(p): print("   (E7 missing)"); return
    a = pd.read_csv(p).set_index("block")
    def ge(prefix): return float(a[a.index.str.startswith(prefix)]["ge"].iloc[0])
    core_rows = a[a.index.str.startswith("Baseline")]
    # C1-TB5 equivalent = author's RV32IM 5-stage core (serial mul/div) + single-cycle RV32M multiplier
    core = float(core_rows["ge"].iloc[0]) + ge("RV32M") if len(core_rows) else 32480.0  # fallback: Ibex maxperf [CHECK]
    ls = ge("pq.keccak-ls"); kf = ge("pq.keccak (")
    units = {"m": ge("pq.kmul") + ge("pq.dmul"), "mb": ge("pq.kmul") + ge("pq.dmul") + ge("pq.kct"),
             "k": kf, "all": ge("pq.kmul") + ge("pq.dmul") + ge("pq.kct") + kf,
             "k-ls": ls, "all-ls": ge("pq.kmul") + ge("pq.dmul") + ge("pq.kct") + ls}
    e4 = rd("E4_extensions.csv"); e4 = e4[e4.core == "C1-TB5"]
    base = e4[e4.variant == "base"].set_index(["scheme", "op"]).cycles
    fig, ax = plt.subplots(figsize=(3.6, 2.7))
    rows = []
    for i, v in enumerate(["base", "m", "mb", "k", "all", "k-ls", "all-ls"]):
        sub = e4[e4.variant == v]
        sp = gm([base[(s, o)] / c for s, o, c in zip(sub.scheme, sub.op, sub.cycles)])
        ov = units.get(v, 0.0) / core * 100
        ax.scatter([ov], [sp], s=40, color=CAT[i], zorder=3, edgecolor="white", linewidth=1.5)
        ax.annotate(v, (ov, sp), textcoords="offset points", xytext=(6, -3), fontsize=7, color=INK)
        rows.append(dict(variant=v, core_GE=round(core), added_GE=round(units.get(v, 0.0)), area_overhead_pct=round(ov, 1), speedup_geomean=round(sp, 3)))
    ax.set_xlabel("Added logic area (% of C1-TB5-equivalent core, Yosys GE est.)\n-ls: lane-serial Keccak, plus 3.2 kbit RAM", fontsize=7); ax.set_ylabel("Speed-up (geomean, 6 schemes × 3 ops)")
    pd.DataFrame(rows).to_csv(os.path.join(TAB, "area_speedup.csv"), index=False)
    save(fig, "fig8_area_speedup")


# ------------------------------------------------------------------ tables
def tables():
    e1 = rd("E1_ops.csv")
    pqm4 = {("ml-kem-512", "KeyGen"): 595793, ("ml-kem-512", "Encaps"): 700605, ("ml-kem-512", "Decaps"): 888653,
            ("ml-kem-768", "KeyGen"): 988722, ("ml-kem-768", "Encaps"): 1138225, ("ml-kem-768", "Decaps"): 1387984,
            ("ml-kem-1024", "KeyGen"): 1536343, ("ml-kem-1024", "Encaps"): 1708071, ("ml-kem-1024", "Decaps"): 2020327,
            ("ml-dsa-44", "KeyGen"): 1874405, ("ml-dsa-44", "Sign"): 7925955, ("ml-dsa-44", "Verify"): 2063096,
            ("ml-dsa-65", "KeyGen"): 3205533, ("ml-dsa-65", "Sign"): 12359056, ("ml-dsa-65", "Verify"): 3377305,
            ("ml-dsa-87", "KeyGen"): 5341863, ("ml-dsa-87", "Sign"): 15579513, ("ml-dsa-87", "Verify"): 5610203}
    e1["pqm4_m4_clean"] = [pqm4.get((s, o), np.nan) for s, o in zip(e1.scheme, e1.op)]
    e1["ratio_vs_pqm4"] = (e1.cycles / e1.pqm4_m4_clean).round(3)
    e1.to_csv(os.path.join(TAB, "table_baseline_vs_pqm4.csv"), index=False)
    with open(os.path.join(TAB, "table_baseline_vs_pqm4.tex"), "w") as f:
        f.write("% pqm4 numbers: mupq/pqm4 benchmarks.md (Cortex-M4, clean) [CHECK WITH AUTHOR: re-copy at submission]\n")
        f.write("\\begin{tabular}{llrrrr}\\toprule\nScheme & Op & Cycles (C1-TB5) & Instr. & CPI & Ratio vs pqm4 \\\\\\midrule\n")
        for _, r in e1.iterrows():
            f.write(f"{LBL[r.scheme]} & {r.op} & {r.cycles:,} & {r.instret:,} & {r.cpi:.2f} & {r.ratio_vs_pqm4:.2f} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n")
    print("   tables written")


def table_loc():
    p = os.path.join(RES, "E6b_leak_localisation.csv")
    if not os.path.exists(p): return
    d = pd.read_csv(p); d = d[(d.scheme == "ml-kem-768") & (d.n_trial_varying > 0)]
    with open(os.path.join(TAB, "table_leak_localisation.tex"), "w") as f:
        f.write("\\begin{tabular}{lllrl}\\toprule\nHardware & Variant & Function & \\#input-dep.\\ instr. & Operand data \\\\\\midrule\n")
        for _, r in d.iterrows():
            f.write(f"{r.hw} & {r.variant} & {str(r.function).replace('_', '\\_')} & {r.n_trial_varying} & {r.operand_class if isinstance(r.operand_class, str) else ''} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n")


def table_validation():
    p1, p2 = os.path.join(RES, "V1_calibration.csv"), os.path.join(RES, "V2_rtl_validation.csv")
    if os.path.exists(p1):
        c = pd.read_csv(p1); u = pd.read_csv(os.path.join(RES, "V1_calibration_uncalibrated.csv"))
        with open(os.path.join(TAB, "table_calibration.tex"), "w") as f:
            f.write("\\begin{tabular}{lrrrrrr}\\toprule\n & \\multicolumn{3}{c}{serial multiplier} & \\multicolumn{3}{c}{embedded multiplier}\\\\\n"
                    "Pattern & RTL & sim (datasheet) & sim (calibrated) & RTL & sim (datasheet) & sim (calibrated)\\\\\\midrule\n")
            for pat in c.pattern.unique():
                r = []
                for mf in (0, 1):
                    a = c[(c.pattern == pat) & (c.mul_fast == mf)].iloc[0]; b = u[(u.pattern == pat) & (u.mul_fast == mf)].iloc[0]
                    r += [f"{a.rtl_cyc_per_pattern:g}", f"{b.sim_cyc_per_pattern:g}", f"{a.sim_cyc_per_pattern:g}"]
                f.write(f"{pat} & " + " & ".join(r) + " \\\\\n")
            f.write("\\bottomrule\n\\end{tabular}\n")
    if os.path.exists(p2):
        v = pd.read_csv(p2)
        with open(os.path.join(TAB, "table_rtl_validation.tex"), "w") as f:
            f.write("\\begin{tabular}{lllrrrc}\\toprule\nKernel & Compiler & Multiplier & RTL cycles & Sim.\\ cycles & Error (\\%) & Hash match \\\\\\midrule\n")
            for _, r in v.iterrows():
                f.write(f"{r.kernel} & {r.compiler} & {'embedded' if r.mul_fast else 'serial'} & {r.rtl_cycles:,} & {r.sim_cycles:,} & {r.error_pct:.3f} & {'yes' if r.bit_exact else 'no'} \\\\\n")
            f.write("\\bottomrule\n\\end{tabular}\n")
    print("   validation tables written")


def table_compiler():
    j = json.load(open(os.path.join(RES, "E0_functional_check.json")))
    rows = []
    for k, r in j.items():
        sch, var = k.split("/")
        if not sch.startswith("ml-kem"): continue
        if var in ("base", "prefix-clangO2", "prefix-clangOs", "prefix-gccO2", "prefix-gccOs", "base-gccO2", "base-gccOs", "Os", "kslash"):
            rows.append(dict(scheme=sch, build=var, div_instr=r["div_instr"], instret=r["instret"]))
    pd.DataFrame(rows).to_csv(os.path.join(TAB, "compiler_divisions.csv"), index=False)
    print("   compiler table written")


if __name__ == "__main__":
    for f in (table_validation, table_compiler, fig_profile, fig_dse, fig_cache, fig_ext, fig_latency, fig_leak, fig_area, tables, table_loc):
        f()
