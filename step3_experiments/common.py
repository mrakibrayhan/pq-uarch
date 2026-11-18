"""Shared helpers for the PQ-uArch experiments."""
import json, os, re, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM = os.path.join(ROOT, "step1_simulator", "build", "rvsim")
ELF = os.path.join(ROOT, "step1_simulator", "build", "elf")
RES = os.path.join(ROOT, "results")
KEMS = ["ml-kem-512", "ml-kem-768", "ml-kem-1024"]
DSAS = ["ml-dsa-44", "ml-dsa-65", "ml-dsa-87"]
SCHEMES = KEMS + DSAS
OPS = {"kem": {1: "KeyGen", 2: "Encaps", 3: "Decaps"}, "dsa": {1: "KeyGen", 2: "Sign", 3: "Verify"}}
NSIGN = 10  # measured ML-DSA iterations per run (see harness.c)

# Reference core presets (all single-issue in-order 5-stage RV32IM)
CORES = {
    "C0-Min":  dict(bp="nt", jalpen=2, ras=0, mul="iter", div="iter"),
    "C1-TB5":  dict(bp="nt", jalpen=2, ras=0, mul="1", div="iter"),
    "C2-Emb":  dict(bp="bimodal", bpbits=9, jalpen=1, ras=1, mul="3p", div="iter"),
    "C3-App":  dict(bp="bimodal", bpbits=9, jalpen=1, ras=1, mul="3p", div="iter",
                    ic_kb=8, ic_ways=2, dc_kb=8, dc_ways=2, memlat=20),
}


def kind(s):
    return "kem" if s.startswith("ml-kem") else "dsa"


def run(elf, profile=False, **cfg):
    args = [SIM, elf, f"profile={1 if profile else 0}"] + [f"{k}={v}" for k, v in cfg.items()]
    r = subprocess.run(args, capture_output=True, text=True)
    d = json.loads(r.stdout)
    if d["exit"] != 0:
        raise RuntimeError(f"{elf} {cfg} exit {d['exit']} {r.stderr[-300:]}")
    return d


def per_op(d, scheme):
    """cycles per operation (ML-DSA regions accumulate NSIGN iterations)."""
    n = 1 if kind(scheme) == "kem" else NSIGN
    return {OPS[kind(scheme)][int(k)]: v["cycles"] / n for k, v in d["regions"].items()}


CATS = [("Keccak-f[1600]", r"KeccakF1600"),
        ("SHAKE/SHA3 glue", r"keccak_|shake|sha3|xof|prf|kdf|hash_"),
        ("NTT / INTT", r"(^|_)(inv)?ntt|invntt"),
        ("Pointwise / basemul", r"basemul|pointwise|acc_"),
        ("Modular reduction", r"montgomery|barrett|reduce|caddq|freeze|fqmul|tomont|csubq"),
        ("Pack / compress / round", r"pack|compress|tobytes|frombytes|tomsg|frommsg|decompose|power2round|hint|highbits|lowbits|chknorm"),
        ("Sampling", r"rej_|cbd|uniform|getnoise|gen_matrix|challenge|expand"),
        ("Poly add/sub/shift", r"(add|sub|shiftl)$"),
        ("Memory ops", r"^mem(cpy|set|cmp|move)"),
        ("Verify / cmov", r"verify|cmov")]


def category(fn):
    f = re.sub(r"^PQCLEAN_ML(KEM|DSA)\d+_CLEAN_", "", fn)
    for c, pat in CATS:
        if re.search(pat, f):
            return c
    return "Other"
