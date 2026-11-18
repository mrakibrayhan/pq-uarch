#!/usr/bin/env python3
"""PQ-uArch experiments E1-E6. Writes CSV/JSON files to ../results.

E1  cycle profile by kernel category (core C1-TB5, base code)
E2  microarchitecture design-space exploration (base code, 36 cores)
E3  cache-size x code-variant sensitivity (I$/D$ 1-32 KB, memlat 20)
E4  ISA-extension speedups on the 4 reference cores
E5  extension-unit latency sensitivity (Keccak unit, modmul units)
E6  timing-leakage (TVLA Welch t-test) for ML-KEM decapsulation
E6b localisation: which functions execute variable-latency mul/div in decaps
E6c ML-KEM-768 leakage with 1000 trials, effect sizes, pre-KyberSlash code and gcc builds
Usage: python3 run_experiments.py [E1 E2 ...]   (default: all)
Author: Md. Rakib Rayhan
"""
import csv, itertools, json, math, os, sys, time
from collections import Counter
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

NPROC = max(1, os.cpu_count() or 1)


def elf(s, v, mode="perf"):
    return os.path.join(ELF, f"{s}_{v}_{mode}.elf")


def wcsv(name, rows):
    path = os.path.join(RES, name)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"  wrote {name} ({len(rows)} rows)")


def _job(a):
    s, v, cname, cfg, extra = a
    d = run(elf(s, v), **cfg)
    out = []
    for op, cyc in per_op(d, s).items():
        out.append(dict(scheme=s, variant=v, core=cname, op=op, cycles=round(cyc), **extra))
    tot = d["instret"]
    for r in out:
        r.update(cpi=round(d["cycles"] / tot, 4), bp_miss=round(d["bp"]["miss"] / max(1, d["bp"]["n"]), 4),
                 ic_miss=round(d["ic"]["miss"] / max(1, d["ic"]["acc"]), 4),
                 dc_miss=round(d["dc"]["miss"] / max(1, d["dc"]["acc"]), 4))
    return out


def pmap(jobs):
    with Pool(NPROC) as p:
        return [r for rs in p.map(_job, jobs, chunksize=1) for r in rs]


# ------------------------------------------------------------------ E1
def E1():
    rows, ops = [], []
    for s in SCHEMES:
        d = run(elf(s, "base"), profile=True, **CORES["C1-TB5"])
        po = per_op(d, s)
        n = 1 if kind(s) == "kem" else NSIGN
        for g, prof in d["profile"].items():
            if g == "0":
                continue
            op = OPS[kind(s)][int(g)]
            c = Counter(); ins = Counter()
            for fn, (cy, ni) in prof.items():
                c[category(fn)] += cy; ins[category(fn)] += ni
            tot = sum(c.values())
            for cat in c:
                rows.append(dict(scheme=s, op=op, category=cat, cycles=round(c[cat] / n),
                                 share=round(c[cat] / tot, 4), cpi=round(c[cat] / max(1, ins[cat]), 3)))
            ops.append(dict(scheme=s, op=op, cycles=round(po[op]), instret=round(d["regions"][g]["instret"] / n),
                            cpi=round(po[op] * n / d["regions"][g]["instret"], 3)))
    wcsv("E1_profile.csv", rows); wcsv("E1_ops.csv", ops)


# ------------------------------------------------------------------ E2
def E2():
    jobs = []
    for bp, mul, mem in itertools.product(["nt", "btfn", "bimodal", "gshare"], ["iter", "3p", "1"],
                                          ["sram", "c4k", "c16k"]):
        cfg = dict(bp=bp, mul=mul, div="iter", bpbits=9)
        cfg.update(dict(jalpen=2, ras=0) if bp in ("nt", "btfn") else dict(jalpen=1, ras=1))
        if mem != "sram":
            kb = 4 if mem == "c4k" else 16
            cfg.update(ic_kb=kb, dc_kb=kb, ic_ways=2, dc_ways=2, memlat=20)
        for s in SCHEMES:
            jobs.append((s, "base", f"{bp}/{mul}/{mem}", cfg, dict(bp=bp, mul=mul, mem=mem)))
    wcsv("E2_dse.csv", pmap(jobs))


# ------------------------------------------------------------------ E3
def E3():
    jobs = []
    for kb in [1, 2, 4, 8, 16, 32]:
        for v in ["base", "all"]:
            cfg = dict(CORES["C2-Emb"], ic_kb=kb, dc_kb=kb, ic_ways=2, dc_ways=2, memlat=20)
            for s in SCHEMES:
                jobs.append((s, v, f"C2+{kb}K", cfg, dict(cache_kb=kb)))
    wcsv("E3_cache.csv", pmap(jobs))


# ------------------------------------------------------------------ E4
def E4():
    jobs = []
    for cname, cfg in CORES.items():
        for s in SCHEMES:
            for v in ["base", "Os", "m", "mb", "k", "all", "allz"]:
                if v in ("mb", "allz") and kind(s) == "dsa":
                    continue
                jobs.append((s, v, cname, cfg, {}))
            for v in ["k", "all"]:   # lane-serial Keccak unit: 2400 + 100 cycles (RTL-verified)
                jobs.append((s, v, cname, dict(cfg, lat_keccak=2500), dict(variant_label=f"{v}-ls")))
            for v in ["base-gccO2", "base-gccOs", "all-gccO2"]:
                jobs.append((s, v, cname, cfg, {}))
    rows = pmap(jobs)
    for r in rows:
        if r.get("variant_label"): r["variant"] = r["variant_label"]
        r.pop("variant_label", None)
    wcsv("E4_extensions.csv", rows)


# ------------------------------------------------------------------ E5
def E5():
    jobs = []
    for lat in [28, 60, 124, 220, 412, 1000, 2500, 5000]:          # Keccak unit: rounds/cycle and 32-bit state transfer
        for s in SCHEMES:
            jobs.append((s, "k", "C1-TB5", dict(CORES["C1-TB5"], lat_keccak=lat), dict(knob="lat_keccak", value=lat)))
    for lat in [1, 2, 3, 4, 6]:                   # modular-multiply units
        for s in SCHEMES:
            jobs.append((s, "mb" if kind(s) == "kem" else "m", "C1-TB5",
                         dict(CORES["C1-TB5"], lat_kmul=lat, lat_kbfly=lat, lat_dmul=lat), dict(knob="lat_modmul", value=lat)))
    wcsv("E5_unit_latency.csv", pmap(jobs))


# ------------------------------------------------------------------ E6
HW = {
    "CT-ref":       dict(bp="nt", jalpen=2, ras=0, mul="1", div="iter"),
    "EarlyDiv":     dict(bp="nt", jalpen=2, ras=0, mul="1", div="early"),
    "EarlyMul-rs2": dict(bp="nt", jalpen=2, ras=0, mul="early", div="iter"),
    "EarlyMul-any": dict(bp="nt", jalpen=2, ras=0, mul="earlyany", div="iter"),
    "BP+Cache":     dict(CORES["C3-App"]),
    "All-variable": dict(CORES["C3-App"], mul="earlyany", div="early"),
}


def welch(a, b):
    import statistics as st
    ma, mb = st.fmean(a), st.fmean(b)
    va, vb = st.pvariance(a), st.pvariance(b)
    den = math.sqrt(va / len(a) + vb / len(b))
    if den == 0:
        return 0.0 if ma == mb else float("inf")
    return (ma - mb) / den


def _leak(a):
    s, v, test, hw = a[:4]
    suffix = a[4] if len(a) > 4 else ""
    d = run(elf(s, v, f"leak{test}{suffix}"), **HW[hw])
    cls, smp = d["vals"], d["samples"]
    a0 = [x for c, x in zip(cls, smp) if c == 0]; a1 = [x for c, x in zip(cls, smp) if c == 1]
    t = welch(a0, a1)
    import statistics as st
    sp = math.sqrt((st.pvariance(a0) + st.pvariance(a1)) / 2)
    dmean = st.fmean(a1) - st.fmean(a0)
    cohen = (dmean / sp) if sp > 0 else (0.0 if dmean == 0 else float("inf"))
    return dict(scheme=s, variant=v, test=("fixed-vs-random ct" if test == 1 else "valid-vs-invalid ct"),
                hw=hw, n0=len(a0), n1=len(a1), mean0=round(sum(a0) / len(a0), 1), mean1=round(sum(a1) / len(a1), 1),
                spread=int(max(smp) - min(smp)), distinct=len(set(smp)),
                t=("inf" if math.isinf(t) else round(t, 2)), leak=int(math.isinf(t) or abs(t) > 4.5),
                delta_mean_cycles=round(dmean, 2), cohen_d=("inf" if math.isinf(cohen) else round(cohen, 3)),
                ntrials=len(smp))


def E6():
    jobs = [(s, v, t, hw) for s in KEMS for v in ["base", "kslash", "m", "all", "allz"] for t in (1, 2) for hw in HW]
    with Pool(NPROC) as p:
        rows = p.map(_leak, jobs, chunksize=1)
    wcsv("E6_leakage.csv", rows)


LONG = ["base", "kslash", "m", "all", "allz", "prefix", "prefix-gccO2", "prefix-gccOs", "base-gccO2", "all-gccO2", "allz-gccO2"]


def E6c():
    """ML-KEM-768, 1000 trials per run, incl. pre-KyberSlash code and gcc builds."""
    hws = ["CT-ref", "EarlyDiv", "EarlyMul-rs2", "EarlyMul-any"]
    jobs = [("ml-kem-768", v, t, hw, "k") for v in LONG for t in (1, 2) for hw in hws]
    with Pool(NPROC) as p:
        rows = p.map(_leak, jobs, chunksize=1)
    wcsv("E6c_leakage_long.csv", rows)


# ------------------------------------------------------------------ E6b
SECRET_PUBLIC = {"polyvec_decompress": "public (ciphertext u)", "poly_decompress": "public (ciphertext v)",
                 "shake128": "public (lengths)", "shake256": "public (lengths)"}


def _loc(a):
    s, v, hw = a
    d = run(elf(s, v, "leak1"), latmap=1, **HW[hw])
    out = {}
    for fn, pc, lo, hi, var in d["varlat"]:
        f = fn.split("_CLEAN_")[-1]
        o = out.setdefault(f, [0, 0, 99, 0]); o[0] += 1; o[1] += var; o[2] = min(o[2], lo); o[3] = max(o[3], hi)
    # n_varlat: instructions whose latency changes within one decaps (any operand);
    # n_trial_varying: instructions whose summed latency differs between decapsulations (input-dependent)
    return [dict(scheme=s, variant=v, hw=hw, function=f, n_varlat=o[0], n_trial_varying=o[1], lat_min=o[2], lat_max=o[3],
                 operand_class=(SECRET_PUBLIC.get(f, "secret-derived") if o[1] else "constant/public tables only"))
            for f, o in sorted(out.items())] or \
           [dict(scheme=s, variant=v, hw=hw, function="(none)", n_varlat=0, n_trial_varying=0, lat_min="", lat_max="", operand_class="")]


def E6b():
    jobs = [(s, v, hw) for s in KEMS for v in ["base", "kslash", "m", "all", "allz"] for hw in ["EarlyDiv", "EarlyMul-rs2", "EarlyMul-any"]]
    jobs += [("ml-kem-768", v, hw) for v in ["prefix", "prefix-gccO2", "prefix-gccOs", "base-gccO2", "all-gccO2", "allz-gccO2"]
             for hw in ["EarlyDiv", "EarlyMul-rs2", "EarlyMul-any"]]
    with Pool(NPROC) as p:
        rows = [r for rs in p.map(_loc, jobs, chunksize=1) for r in rs]
    wcsv("E6b_leak_localisation.csv", rows)


if __name__ == "__main__":
    os.makedirs(RES, exist_ok=True)
    todo = sys.argv[1:] or ["E1", "E2", "E3", "E4", "E5", "E6", "E6b", "E6c"]
    meta = {}
    for e in todo:
        t0 = time.time(); print(f"[{e}] running ..."); globals()[e](); meta[e] = round(time.time() - t0, 1)
        print(f"[{e}] done in {meta[e]} s")
    mp = os.path.join(RES, "run_meta.json")
    old = json.load(open(mp)) if os.path.exists(mp) else {}
    old.update(meta); json.dump(old, open(mp, "w"), indent=1)
