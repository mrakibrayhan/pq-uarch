"""Python Keccak-f[1600] reference + test-vector writer for the RTL testbenches."""
import random, sys
RC = [0x0000000000000001,0x0000000000008082,0x800000000000808a,0x8000000080008000,0x000000000000808b,0x0000000080000001,
      0x8000000080008081,0x8000000000008009,0x000000000000008a,0x0000000000000088,0x0000000080008009,0x000000008000000a,
      0x000000008000808b,0x800000000000008b,0x8000000000008089,0x8000000000008003,0x8000000000008002,0x8000000000000080,
      0x000000000000800a,0x800000008000000a,0x8000000080008081,0x8000000000008080,0x0000000080000001,0x8000000080008008]
RHO = [0,1,62,28,27,36,44,6,55,20,3,10,43,25,39,41,45,15,21,8,18,2,61,56,14]
M = (1 << 64) - 1
rol = lambda v, n: ((v << n) | (v >> (64 - n))) & M if n else v
def keccakf(s):
    s = list(s)
    for r in range(24):
        C = [s[x] ^ s[x+5] ^ s[x+10] ^ s[x+15] ^ s[x+20] for x in range(5)]
        for x in range(5):
            D = C[(x+4) % 5] ^ rol(C[(x+1) % 5], 1)
            for y in range(5): s[x+5*y] ^= D
        B = [0]*25
        for x in range(5):
            for y in range(5): B[y + 5*((2*x+3*y) % 5)] = rol(s[x+5*y], RHO[x+5*y])
        s = [B[x+5*y] ^ (~B[(x+1) % 5 + 5*y] & B[(x+2) % 5 + 5*y]) for y in range(5) for x in range(5)]
        s = [s[i] for i in range(25)]
        s[0] ^= RC[r]
    return s
if __name__ == "__main__":
    assert keccakf([0]*25)[0] == 0xF1258F7940E1DDE7, "reference self-test failed"
    random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
    with open("vectors.hex", "w") as f:
        for t in range(int(sys.argv[2]) if len(sys.argv) > 2 else 4):
            s = [0]*25 if t == 0 else [random.getrandbits(64) for _ in range(25)]
            o = keccakf(s)
            for v in s + o: f.write(f"{v & 0xffffffff:08x}\n{v >> 32:08x}\n")
