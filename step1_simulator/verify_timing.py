#!/usr/bin/env python3
"""Verify the timing model on micro-benchmarks with hand-derived cycle counts."""
import json, os, subprocess, sys
H = os.path.dirname(os.path.abspath(__file__)); B = os.path.join(H, "build")
elf = os.path.join(B, "timing_tests.elf")
subprocess.run(["clang", "--target=riscv32", "-march=rv32im", "-mabi=ilp32", "-nostdlib", "-fuse-ld=lld",
                "-mno-relax", "-T", os.path.join(H, "firmware", "link.ld"),
                os.path.join(H, "firmware", "tests", "timing_tests.S"), "-o", elf], check=True)
# region k is measured from the cycle the BEG store issues to the cycle the END store issues.
# BEG = li + sw(begin) ; END = li + sw(end): li of END adds 1 cycle inside the window.
def run(**cfg):
    args = [os.path.join(B, "rvsim"), elf, "profile=0"] + [f"{k}={v}" for k, v in cfg.items()]
    d = json.loads(subprocess.run(args, capture_output=True, text=True).stdout)
    return [int(x) for x in d["samples"]]
cases = [
  # (config, expected [T1..T5]) -- each window = body + 2 (sw-begin issue, li of END)
  (dict(bp="nt", mul="1", div="iter", loaduse=1, brpen=2),
   [64+2, 32*3+2, 50*2+49*2+2, 16+2, 8*34+2]),
  (dict(bp="btfn", mul="iter", div="early", loaduse=1, brpen=2),
   [64+2, 32*3+2, 50*2+1*2+2, 16*32+2, 8*(3+2)+2]),
  (dict(bp="bimodal", mul="3p", div="iter", loaduse=0, brpen=3),
   [64+2, 32*2+2, None, 1+15*3+2, 8*34+2]),
]
ok = True
for cfg, exp in cases:
    got = run(**cfg)
    for i, (g, e) in enumerate(zip(got, exp)):
        if e is None: continue
        flag = "OK " if g == e else "BAD"; ok &= g == e
        print(f"{flag} {cfg} T{i+1}: got {g} expected {e}")
print("timing model verified" if ok else "MISMATCH"); sys.exit(0 if ok else 1)
