#!/usr/bin/env python3
"""PQ-uArch build script.

1. compiles the simulator (sim/rvsim.c -> build/rvsim)
2. makes patched copies of the PQClean sources for each ISA variant
3. cross-compiles every (scheme, variant, mode) to an RV32IM ELF with clang
4. builds the same code natively (x86) and checks that the simulator gives
   bit-identical outputs (functional cross-check of the ISS + extensions)

Variants
  base    unmodified PQClean "clean" code
  kslash  ML-KEM only: poly_tomsg written with a real division by q, as in the
          pre-2024 reference code (emulates the code a compiler emits when it
          does not strength-reduce the division; the KyberSlash pattern)
  m       modular-multiply instructions (pq.kmul/kmred/kbar or pq.dmul)
  mb      m + packed NTT butterflies (ML-KEM; for ML-DSA identical to m)
  k       Keccak-f[1600] permutation instruction only
  all     mb + k
  allz    all + the constant multiplies in poly/polyvec compress and poly_tomsg
          moved onto pq.cmul (a fixed-latency multiply) -- ML-KEM only
  Os      base code compiled with -Os instead of -O2 (compiler effect check)
  prefix  ML-KEM only: the pre-2024 reference code of poly_tomsg / poly(vec)_compress, i.e.
          division by the constant q written in C (the code KyberSlash attacked); whether a
          division instruction appears is up to the compiler
Extra builds with a second compiler (riscv64-unknown-elf-gcc 13) are listed in EXTRA.
Author: Md. Rakib Rayhan
"""
import json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.join(HERE, "build")
SCHEMES = {"ml-kem-512": "PQCLEAN_MLKEM512_CLEAN", "ml-kem-768": "PQCLEAN_MLKEM768_CLEAN",
           "ml-kem-1024": "PQCLEAN_MLKEM1024_CLEAN", "ml-dsa-44": "PQCLEAN_MLDSA44_CLEAN",
           "ml-dsa-65": "PQCLEAN_MLDSA65_CLEAN", "ml-dsa-87": "PQCLEAN_MLDSA87_CLEAN"}
VARIANTS = ["base", "kslash", "m", "mb", "k", "all", "allz", "Os"]
CC_GCC = ["riscv64-unknown-elf-gcc", "-march=rv32im", "-mabi=ilp32", "-O2", "-ffreestanding", "-nostdlib",
          "-fno-builtin", "-mno-relax", "-Wl,--no-relax"]
# extra (variant, compiler, opt) builds; tag suffix e.g. "base-gccOs"
EXTRA = [("prefix", "clang", "-O2"), ("prefix", "clang", "-Os"), ("prefix", "gcc", "-O2"), ("prefix", "gcc", "-Os"),
         ("base", "gcc", "-O2"), ("base", "gcc", "-Os"), ("m", "gcc", "-O2"), ("all", "gcc", "-O2"), ("allz", "gcc", "-O2")]
CC_RV = ["clang", "--target=riscv32", "-march=rv32im", "-mabi=ilp32", "-O2", "-ffreestanding",
         "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-mno-relax", "-Wno-unused-command-line-argument"]


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        print(" ".join(cmd)); print(r.stdout); print(r.stderr); sys.exit(1)
    return r.stdout


def patch_tree(scheme, ns, variant, dst):
    src = os.path.join(HERE, "pqclean", scheme)
    shutil.copytree(src, dst)
    shutil.copy(os.path.join(HERE, "pqclean", "common", "fips202.c"), dst)
    kem = scheme.startswith("ml-kem")
    m = variant in ("m", "mb", "all", "allz")
    bf = variant in ("mb", "all", "allz") and kem
    kc = variant in ("k", "all", "allz")

    def edit(fn, f):
        p = os.path.join(dst, fn); s = open(p).read(); s2 = f(s)
        open(p, "w").write(s2)
        return s2 != s

    if kc:
        ok = edit("fips202.c", lambda s: s.replace(
            "static void KeccakF1600_StatePermute(uint64_t *state) {",
            '#include "pqext.h"\nstatic void KeccakF1600_StatePermute(uint64_t *state) {\n    PQ_KECCAK(state); return;'))
        assert ok
    if kem and variant == "kslash":
        ok = edit("poly.c", lambda s: s.replace(
            "            t <<= 1;\n            t += 1665;\n            t *= 80635;\n            t >>= 28;\n            t &= 1;",
            "            uint32_t kq; __asm__(\"\" : \"=r\"(kq) : \"0\"((uint32_t)KYBER_Q));\n"
            "            t += ((int16_t)t >> 15) & KYBER_Q;\n"
            "            t  = (((t << 1) + KYBER_Q / 2) / kq) & 1;"))
        assert ok
    if kem and variant == "prefix":
        assert edit("poly.c", lambda s: s.replace(
            "            t <<= 1;\n            t += 1665;\n            t *= 80635;\n            t >>= 28;\n            t &= 1;",
            "            t += ((int16_t)t >> 15) & KYBER_Q;\n            t  = (((t << 1) + KYBER_Q / 2) / KYBER_Q) & 1;"))
        assert edit("poly.c", lambda s: re.sub(
            r"d0 = u << (\d+);\n\s+d0 \+= \d+;\n\s+d0 \*= \d+;\n\s+d0 >>= \d+;\n(\s+)t\[j\] = d0 & (0x[0-9a-f]+);",
            r"t[j] = ((((uint32_t)u << \1) + KYBER_Q / 2) / KYBER_Q) & \3;", s))
        assert edit("polyvec.c", lambda s: re.sub(
            r"d0 = t\[k\];\n\s+d0 <<= (\d+);\n\s+d0 \+= \d+;\n\s+d0 \*= \d+;\n\s+d0 >>= \d+;\n(\s+)t\[k\] = d0 & (0x[0-9a-f]+);",
            r"t[k] = ((((uint32_t)t[k] << \1) + KYBER_Q / 2) / KYBER_Q) & \3;", s))
    if kem and variant == "allz":
        hi = re.compile(r"d0 \*= (\d{4,});\n(\s+)d0 >>= (\d+);")
        assert edit("polyvec.c", lambda s: hi.sub(
            r"{ uint32_t x_ = (uint32_t)d0; d0 = ((((uint64_t)PQ_CMULHU(x_, \1)) << 32) | PQ_CMUL(x_, \1)) >> \3; }", s))
        pat = re.compile(r"(\w+) \*= (\d{4,});")
        for fn in ("poly.c", "polyvec.c"):
            assert edit(fn, lambda s: '#include "pqext.h"\n' + pat.sub(r"\1 = PQ_CMUL(\1, \2);", s))
    if kem and m:
        assert edit("reduce.c", lambda s: re.sub(
            r"(int16_t \w+_montgomery_reduce\(int32_t a\) \{)", r'#include "pqext.h"\n\1\n    return (int16_t)PQ_KMRED(a);', s))
        assert edit("reduce.c", lambda s: re.sub(
            r"(int16_t \w+_barrett_reduce\(int16_t a\) \{)", r"\1\n    return (int16_t)PQ_KBAR(a);", s))
        assert edit("ntt.c", lambda s: re.sub(
            r"static int16_t fqmul\(int16_t a, int16_t b\) \{\n.*?\n\}",
            '#include "pqext.h"\nstatic int16_t fqmul(int16_t a, int16_t b) {\n    return (int16_t)PQ_KMUL(a, b);\n}', s, flags=re.S))
    if bf:
        assert edit("ntt.c", lambda s: s.replace(
            "                t = fqmul(zeta, r[j + len]);\n                r[j + len] = r[j] - t;\n                r[j] = r[j] + t;",
            "                uint32_t p = (uint16_t)r[j] | ((uint32_t)(uint16_t)r[j + len] << 16);\n"
            "                p = PQ_KCT(p, zeta); (void)t;\n"
            "                r[j] = (int16_t)p; r[j + len] = (int16_t)(p >> 16);"))
        assert edit("ntt.c", lambda s: re.sub(
            r"                t = r\[j\];\n                r\[j\] = \w+_barrett_reduce\(t \+ r\[j \+ len\]\);\n"
            r"                r\[j \+ len\] = r\[j \+ len\] - t;\n                r\[j \+ len\] = fqmul\(zeta, r\[j \+ len\]\);",
            "                uint32_t p = (uint16_t)r[j] | ((uint32_t)(uint16_t)r[j + len] << 16);\n"
            "                p = PQ_KGS(p, zeta); (void)t;\n"
            "                r[j] = (int16_t)p; r[j + len] = (int16_t)(p >> 16);", s))
    if (not kem) and m:
        pat = re.compile(r"\w+_montgomery_reduce\(\(int64_t\)([^;]+?) \* ([^;]+?)\);")
        for fn in ("ntt.c", "poly.c"):
            assert edit(fn, lambda s: '#include "pqext.h"\n' + pat.sub(r"PQ_DMUL(\1, \2);", s))


def build_one(scheme, ns, variant, mode, native=False, extra=(), cc="clang", opt="-O2"):
    if variant in ("kslash", "allz", "prefix") and not scheme.startswith("ml-kem"):
        return None
    if mode.startswith("leak") and (not scheme.startswith("ml-kem") or variant in ("mb", "k", "Os")):
        return None
    suf = "" if (cc, opt) == ("clang", "-O2") else f"-{cc}{opt[1:]}"
    tag = f"{scheme}_{variant}{suf}_{mode}"
    src = os.path.join(B, "src", f"{scheme}_{variant}")
    if not os.path.isdir(src):
        patch_tree(scheme, ns, variant, src)
    fw = os.path.join(HERE, "firmware")
    cfiles = sorted(os.path.join(src, f) for f in os.listdir(src) if f.endswith(".c"))
    defs = [f"-DNS={ns}", "-DIS_KEM" if scheme.startswith("ml-kem") else "-DIS_DSA",
            *(["-DMODE_PERF"] if mode == "perf" else ["-DMODE_LEAK", f"-DLEAKTEST={mode[4]}"]),
            *(["-DNTRIALS=1000"] if mode.endswith("k") else []), *extra]
    incs = [f"-I{src}", f"-I{os.path.join(HERE, 'pqclean', 'common')}", f"-I{fw}"]
    if native:
        out = os.path.join(B, "native", tag)
        sh(["gcc", "-O2", "-DNATIVE", *defs, *incs, *cfiles, os.path.join(fw, "harness.c"),
            os.path.join(fw, "rng.c"), "-o", out])
        return out
    out = os.path.join(B, "elf", tag + ".elf")
    o = "-Os" if variant == "Os" else opt
    ccl = [c if c != "-O2" else o for c in (CC_RV if cc == "clang" else CC_GCC)]
    sh([*ccl, *defs, f"-I{os.path.join(fw, 'include')}", *incs, "-T", os.path.join(fw, "link.ld"),
        os.path.join(fw, "start.S"), os.path.join(fw, "libc_min.c"), os.path.join(fw, "rng.c"),
        os.path.join(fw, "harness.c"), *cfiles, "-o", out] + (["-lgcc"] if cc == "gcc" else []))
    return out


def main():
    for d in ("src", "elf", "native"):
        shutil.rmtree(os.path.join(B, d), ignore_errors=True)
        os.makedirs(os.path.join(B, d))
    tmp = os.path.join(B, "rvsim.tmp")   # build then rename, so running jobs never see a missing binary
    sh(["gcc", "-O3", "-march=native", "-o", tmp, os.path.join(HERE, "sim", "rvsim.c")])
    os.replace(tmp, os.path.join(B, "rvsim"))
    sim = os.path.join(B, "rvsim")
    report = {}
    for scheme, ns in SCHEMES.items():
        for v in VARIANTS:
            for mode in ("perf", "leak1", "leak2"):
                elf = build_one(scheme, ns, v, mode)
                if not elf:
                    continue
                if mode == "perf":
                    nat = build_one(scheme, ns, v if v not in ("m", "mb", "k", "all", "allz", "Os") else "base", mode, native=True)
                    ref = [int(x) for x in sh([nat]).split()]
                    js = json.loads(sh([sim, elf, "profile=0"]))
                    ok = js["exit"] == 0 and js["vals"] == ref
                    report[f"{scheme}/{v}"] = {"match_native": ok, "exit": js["exit"], "instret": js["instret"],
                                               "div_instr": js["mix"]["div"], "mul_instr": js["mix"]["mul"]}
                    print(f"{scheme:12s} {v:7s} exit={js['exit']} native-match={ok} instret={js['instret']} div={js['mix']['div']}")
                    if not ok:
                        print("  sim:", js["vals"], " native:", ref); sys.exit(1)
    for v, cc, opt in EXTRA:
        for scheme, ns in SCHEMES.items():
            for mode in ("perf", "leak1", "leak2"):
                if mode != "perf" and opt == "-Os" and v != "prefix":
                    continue
                elf = build_one(scheme, ns, v, mode, cc=cc, opt=opt)
                if not elf or mode != "perf":
                    continue
                nat = build_one(scheme, ns, v if v in ("prefix",) else "base", mode, native=True)
                ref = [int(x) for x in sh([nat]).split()]
                js = json.loads(sh([sim, elf, "profile=0"]))
                ok = js["exit"] == 0 and js["vals"] == ref
                key = f"{scheme}/{v}-{cc}{opt[1:]}"
                report[key] = {"match_native": ok, "exit": js["exit"], "instret": js["instret"],
                               "div_instr": js["mix"]["div"], "mul_instr": js["mix"]["mul"]}
                print(f"{scheme:12s} {key.split('/')[1]:14s} exit={js['exit']} native-match={ok} instret={js['instret']} div={js['mix']['div']}")
                if not ok:
                    print("  sim:", js["vals"], " native:", ref); sys.exit(1)
    # long leakage runs (1000 trials) for ML-KEM-768: main variants and compiler variants
    LONG = [("base", "clang", "-O2"), ("kslash", "clang", "-O2"), ("m", "clang", "-O2"), ("all", "clang", "-O2"),
            ("allz", "clang", "-O2"), ("prefix", "clang", "-O2"), ("prefix", "gcc", "-O2"), ("prefix", "gcc", "-Os"),
            ("base", "gcc", "-O2"), ("all", "gcc", "-O2"), ("allz", "gcc", "-O2")]
    for v, cc, opt in LONG:
        for mode in ("leak1k", "leak2k"):
            build_one("ml-kem-768", SCHEMES["ml-kem-768"], v, mode, cc=cc, opt=opt)
    os.makedirs(os.path.join(HERE, "..", "results"), exist_ok=True)
    json.dump(report, open(os.path.join(HERE, "..", "results", "E0_functional_check.json"), "w"), indent=1)
    print("all variants bit-exact with native reference")


if __name__ == "__main__":
    main()
