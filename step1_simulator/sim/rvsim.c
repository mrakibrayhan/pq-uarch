/*
 * rvsim.c -- PQ-uArch: RV32IM instruction-set simulator with a cycle-level
 * timing model of a single-issue, in-order, 5-stage embedded RISC-V pipeline
 * (IF ID EX MEM WB, full forwarding, branches resolved in EX).
 *
 * Author: Md. Rakib Rayhan (North South University)
 *
 * Timing model (scoreboard form of an in-order 5-stage pipeline)
 *   - one instruction may enter EX per cycle;
 *   - ALU results are forwarded (ready next cycle); loads add `loaduse`
 *     cycles (load-use hazard);
 *   - branches are predicted in IF (static-NT, BTFN, bimodal, gshare);
 *     a mispredict costs `brpen` cycles; JAL costs `jalpen` (target in ID);
 *     JALR uses a return-address stack when `ras`=1;
 *   - multiplier: single-cycle, pipelined (3 cyc), iterative (32 cyc,
 *     stalls pipeline) or early-terminating (data dependent, stalls);
 *   - divider: iterative fixed (34 cyc) or early-terminating (data dependent);
 *   - optional blocking set-associative write-back I$ and D$ (LRU), main
 *     memory latency `memlat`; with no cache, memory is single-cycle SRAM;
 *   - optional PQC custom instructions on opcode custom-0 (0x0B):
 *       f3=0 pq.kmred  rd = MontRed_q3329(rs1)                (ML-KEM)
 *       f3=1 pq.kmul   rd = MontRed_q3329((i16)rs1*(i16)rs2)  (ML-KEM)
 *       f3=2 pq.kbar   rd = BarrettRed_q3329((i16)rs1)        (ML-KEM)
 *       f3=3 pq.kct    packed Cooley-Tukey butterfly          (ML-KEM NTT)
 *       f3=4 pq.kgs    packed Gentleman-Sande butterfly       (ML-KEM INTT)
 *       f3=5 pq.dmul   rd = MontRed_q8380417((i64)rs1*rs2)   (ML-DSA)
 *       f3=6 pq.cmul   rd = rs1*rs2 (f7=0) or high word of rs1*rs2 (f7=1);
 *                      fixed latency, data-independent multiply
 *       f3=7 pq.keccak Keccak-f[1600] on the 200-byte state at [rs1]
 *
 * Usage: rvsim prog.elf [key=value ...] [out=result.json]
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MEMSZ   (32u << 20)
#define MMIO    0xFFFF0000u
static uint8_t *mem;

/* ------------------------------------------------------------ config */
typedef struct {
    char bp[16]; int bpbits; int brpen; int jalpen; int ras;
    char mul[16]; char div[16]; int loaduse;
    int ic_kb, ic_ways, dc_kb, dc_ways, line, memlat;
    int lat_kmul, lat_kbfly, lat_dmul, lat_keccak;
    long long maxinstr; int profile; int latmap;
    int mul_it, mul_hix, div_it;   /* iterative unit latencies (cycles EX is busy) */
} cfg_t;
static cfg_t C = {"bimodal", 9, 2, 1, 1, "1", "iter", 1,
                  0, 2, 0, 2, 32, 10, 1, 2, 2, 124, 4000000000LL, 1, 0, 32, 1, 34};

static void setcfg(const char *k, const char *v) {
#define I(n) if (!strcmp(k, #n)) { C.n = atoi(v); return; }
#define S(n) if (!strcmp(k, #n)) { snprintf(C.n, sizeof C.n, "%s", v); return; }
    S(bp) I(bpbits) I(brpen) I(jalpen) I(ras) S(mul) S(div) I(loaduse)
    I(ic_kb) I(ic_ways) I(dc_kb) I(dc_ways) I(line) I(memlat)
    I(lat_kmul) I(lat_kbfly) I(lat_dmul) I(lat_keccak) I(profile) I(latmap) I(mul_it) I(mul_hix) I(div_it)
    if (!strcmp(k, "maxinstr")) { C.maxinstr = atoll(v); return; }
    fprintf(stderr, "unknown option %s\n", k); exit(2);
}

/* ------------------------------------------------------------ caches */
typedef struct { int on, sets, ways, lb; uint32_t *tag; uint8_t *valid, *dirty; uint32_t *lru;
                 uint64_t acc, miss, wb; } cache_t;
static cache_t IC, DC;
static void cache_init(cache_t *c, int kb, int ways, int line) {
    memset(c, 0, sizeof *c);
    if (kb <= 0) return;
    c->on = 1; c->ways = ways; c->lb = __builtin_ctz(line);
    c->sets = (kb * 1024) / (line * ways);
    size_t n = (size_t)c->sets * ways;
    c->tag = calloc(n, 4); c->valid = calloc(n, 1); c->dirty = calloc(n, 1); c->lru = calloc(n, 4);
}
static uint32_t lru_clock = 0;
/* returns extra cycles */
static int cache_access(cache_t *c, uint32_t addr, int write) {
    if (!c->on) return 0;
    c->acc++;
    uint32_t blk = addr >> c->lb, set = blk % c->sets, tag = blk / c->sets;
    size_t b = (size_t)set * c->ways;
    lru_clock++;
    for (int w = 0; w < c->ways; w++)
        if (c->valid[b + w] && c->tag[b + w] == tag) {
            c->lru[b + w] = lru_clock; if (write) c->dirty[b + w] = 1; return 0;
        }
    c->miss++;
    int vic = 0; uint32_t best = 0xFFFFFFFFu;
    for (int w = 0; w < c->ways; w++) {
        if (!c->valid[b + w]) { vic = w; best = 0; break; }
        if (c->lru[b + w] < best) { best = c->lru[b + w]; vic = w; }
    }
    int pen = C.memlat;
    if (c->valid[b + vic] && c->dirty[b + vic]) { pen += C.memlat; c->wb++; }
    c->valid[b + vic] = 1; c->tag[b + vic] = tag; c->dirty[b + vic] = (uint8_t)write;
    c->lru[b + vic] = lru_clock;
    return pen;
}

/* ------------------------------------------------------------ branch predictor */
static uint8_t *bpt; static uint32_t ghr; static uint64_t br_n, br_miss;
static uint32_t ras_stk[16]; static int ras_sp;
static int bp_predict(uint32_t pc, int32_t off) {
    if (!strcmp(C.bp, "nt")) return 0;
    if (!strcmp(C.bp, "btfn")) return off < 0;
    uint32_t m = (1u << C.bpbits) - 1, i = (pc >> 2) & m;
    if (!strcmp(C.bp, "gshare")) i = ((pc >> 2) ^ ghr) & m;
    return bpt[i] >= 2;
}
static void bp_update(uint32_t pc, int taken) {
    if (!strcmp(C.bp, "nt") || !strcmp(C.bp, "btfn")) return;
    uint32_t m = (1u << C.bpbits) - 1, i = (pc >> 2) & m;
    if (!strcmp(C.bp, "gshare")) i = ((pc >> 2) ^ ghr) & m;
    if (taken && bpt[i] < 3) bpt[i]++;
    if (!taken && bpt[i] > 0) bpt[i]--;
    ghr = ((ghr << 1) | (uint32_t)taken) & m;
}

/* ------------------------------------------------------------ ELF + symbols */
typedef struct { uint32_t lo, hi; char name[64]; } sym_t;
static sym_t syms[8192]; static int nsyms;
static uint16_t *pc2f; static uint32_t text_lo, text_hi;
static uint32_t entry;
static void load_elf(const char *path) {
    FILE *f = fopen(path, "rb"); if (!f) { perror(path); exit(1); }
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *e = malloc(n); if (fread(e, 1, n, f) != (size_t)n) exit(1); fclose(f);
#define R32(p) (*(uint32_t *)(p))
#define R16(p) (*(uint16_t *)(p))
    entry = R32(e + 24);
    uint32_t phoff = R32(e + 28), shoff = R32(e + 32);
    int phnum = R16(e + 44), shnum = R16(e + 48);
    text_lo = 0xFFFFFFFF; text_hi = 0;
    for (int i = 0; i < phnum; i++) {
        uint8_t *p = e + phoff + 32 * i;
        if (R32(p) != 1) continue;
        uint32_t off = R32(p + 4), va = R32(p + 8), fs = R32(p + 16), ms = R32(p + 20), fl = R32(p + 24);
        if (va + ms > MEMSZ) { fprintf(stderr, "segment out of range\n"); exit(1); }
        memcpy(mem + va, e + off, fs); memset(mem + va + fs, 0, ms - fs);
        if (fl & 1) { if (va < text_lo) text_lo = va; if (va + ms > text_hi) text_hi = va + ms; }
    }
    for (int i = 0; i < shnum; i++) {
        uint8_t *s = e + shoff + 40 * i;
        if (R32(s + 4) != 2) continue; /* SHT_SYMTAB */
        uint32_t off = R32(s + 16), size = R32(s + 20), link = R32(s + 24);
        char *str = (char *)(e + R32(e + shoff + 40 * link + 16));
        for (uint32_t k = 0; k < size / 16; k++) {
            uint8_t *y = e + off + 16 * k;
            if ((y[12] & 15) != 2 || R32(y + 8) == 0 || nsyms >= 8191) continue; /* STT_FUNC */
            sym_t *q = &syms[++nsyms];
            q->lo = R32(y + 4); q->hi = q->lo + R32(y + 8);
            snprintf(q->name, 64, "%s", str + R32(y));
        }
    }
    uint32_t nw = (text_hi - text_lo) / 4 + 1;
    pc2f = calloc(nw, 2);
    for (int i = 1; i <= nsyms; i++)
        for (uint32_t a = syms[i].lo; a < syms[i].hi; a += 4)
            if (a >= text_lo && a < text_hi) pc2f[(a - text_lo) / 4] = (uint16_t)i;
    snprintf(syms[0].name, 64, "?");
    free(e);
}

/* ------------------------------------------------------------ PQC helpers */
static int16_t kmred(int32_t a) { int16_t t = (int16_t)a * (int16_t)-3327; return (int16_t)((a - (int32_t)t * 3329) >> 16); }
static int16_t kbar(int16_t a) { int16_t t = (int16_t)(((int32_t)20159 * a + (1 << 25)) >> 26); t = (int16_t)(t * 3329); return (int16_t)(a - t); }
static int32_t dmred(int64_t a) { int32_t t = (int32_t)((uint64_t)a * (uint64_t)58728449); return (int32_t)((a - (int64_t)t * 8380417) >> 32); }
static const uint64_t KRC[24] = {
 0x0000000000000001ULL,0x0000000000008082ULL,0x800000000000808aULL,0x8000000080008000ULL,
 0x000000000000808bULL,0x0000000080000001ULL,0x8000000080008081ULL,0x8000000000008009ULL,
 0x000000000000008aULL,0x0000000000000088ULL,0x0000000080008009ULL,0x000000008000000aULL,
 0x000000008000808bULL,0x800000000000008bULL,0x8000000000008089ULL,0x8000000000008003ULL,
 0x8000000000008002ULL,0x8000000000000080ULL,0x000000000000800aULL,0x800000008000000aULL,
 0x8000000080008081ULL,0x8000000000008080ULL,0x0000000080000001ULL,0x8000000080008008ULL};
#define ROL(a, o) (((a) << (o)) ^ ((a) >> (64 - (o))))
static void keccakf(uint64_t s[25]) {
    static const int rho[25] = {0,1,62,28,27,36,44,6,55,20,3,10,43,25,39,41,45,15,21,8,18,2,61,56,14};
    for (int r = 0; r < 24; r++) {
        uint64_t Cc[5], D, B[25];
        for (int x = 0; x < 5; x++) Cc[x] = s[x] ^ s[x+5] ^ s[x+10] ^ s[x+15] ^ s[x+20];
        for (int x = 0; x < 5; x++) { D = Cc[(x+4)%5] ^ ROL(Cc[(x+1)%5], 1); for (int y = 0; y < 25; y += 5) s[y+x] ^= D; }
        for (int x = 0; x < 5; x++) for (int y = 0; y < 5; y++) {
            int o = rho[x + 5*y]; uint64_t v = s[x + 5*y];
            B[y + 5*((2*x + 3*y) % 5)] = o ? ROL(v, o) : v; }
        for (int x = 0; x < 5; x++) for (int y = 0; y < 25; y += 5)
            s[y+x] = B[y+x] ^ ((~B[y+(x+1)%5]) & B[y+(x+2)%5]);
        s[0] ^= KRC[r];
    }
}

/* ------------------------------------------------------------ data-dependent latencies */
static int msb(uint32_t v) { return v ? 31 - __builtin_clz(v) : -1; }
static int ebytes(uint32_t b) {
    int m = 1; uint32_t t = b >> 8;
    if (!(t == 0 || t == 0x00FFFFFF)) { m = 2; t = b >> 16;
        if (!(t == 0 || t == 0xFFFF)) { m = 3; t = b >> 24;
            if (!(t == 0 || t == 0xFF)) m = 4; } }
    return m;
}
static int mul_lat2(uint32_t a, uint32_t b, int high) {
    if (!strcmp(C.mul, "earlyany")) { int x = ebytes(a), y = ebytes(b); return 1 + (x < y ? x : y) + (high ? 1 : 0); }
    return -1;
}
static int mul_lat(uint32_t b, int high) {
    if (!strcmp(C.mul, "1")) return 1;
    if (!strcmp(C.mul, "3p")) return 3;          /* pipelined: handled as result latency */
    if (!strcmp(C.mul, "iter")) return C.mul_it + (high ? C.mul_hix : 0);
    /* "early": ARM7TDMI-style early termination on the multiplier operand rs2 (8 bits/cycle)
       "earlyany": early termination on the operand with fewer significant bytes        */
    int m = 1; uint32_t t = b >> 8;
    if (!(t == 0 || t == 0x00FFFFFF)) { m = 2; t = b >> 16;
        if (!(t == 0 || t == 0xFFFF)) { m = 3; t = b >> 24;
            if (!(t == 0 || t == 0xFF)) m = 4; } }
    return 1 + m + (high ? 1 : 0);
}
static int div_lat(uint32_t a, uint32_t b, int sgn) {
    if (!strcmp(C.div, "iter")) return C.div_it;
    /* "early": radix-2 restoring divider that skips leading quotient zeros */
    if (sgn) { a = (int32_t)a < 0 ? -a : a; b = (int32_t)b < 0 ? -b : b; }
    if (b == 0) return 3;
    int d = msb(a) - msb(b);
    return 3 + (d > 0 ? d + 1 : 1);
}

/* ------------------------------------------------------------ main loop */
#define MAXREG 16
/* latmap: per-PC min/max latency of variable-latency instructions inside region 4 */
static uint8_t *lat_min, *lat_max;
/* per-PC latency sum in the current region-4 instance vs. the first instance:
   a PC is "trial-varying" if its summed latency differs between decapsulations */
static uint32_t *lat_cur, *lat_ref; static uint8_t *lat_var; static int lat_first = 1;
static void latrec(uint32_t pc, int L) {
    uint32_t q = (pc - text_lo) / 4;
    if (L < lat_min[q]) lat_min[q] = (uint8_t)L; if (L > lat_max[q]) lat_max[q] = (uint8_t)L;
    lat_cur[q] += (uint32_t)L;
}
static uint64_t prof_cyc[MAXREG][8192], prof_ins[MAXREG][8192];
static uint64_t reg_cyc[MAXREG], reg_ins[MAXREG];
static double *samples; static int nsamp, capsamp;
static uint32_t vals[65536]; static int nvals; static uint32_t a0_out;

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: rvsim prog.elf [k=v...] [out=f.json]\n"); return 2; }
    const char *out = NULL;
    for (int i = 2; i < argc; i++) {
        char k[64], *eq = strchr(argv[i], '='); if (!eq) continue;
        snprintf(k, sizeof k, "%.*s", (int)(eq - argv[i]), argv[i]);
        if (!strcmp(k, "out")) out = eq + 1; else setcfg(k, eq + 1);
    }
    mem = calloc(MEMSZ, 1);
    load_elf(argv[1]);
    cache_init(&IC, C.ic_kb, C.ic_ways, C.line);
    cache_init(&DC, C.dc_kb, C.dc_ways, C.line);
    { uint32_t nw = (text_hi - text_lo) / 4 + 1; lat_min = malloc(nw); lat_max = calloc(nw, 1); memset(lat_min, 255, nw);
      lat_cur = calloc(nw, 4); lat_ref = calloc(nw, 4); lat_var = calloc(nw, 1); }
    bpt = calloc(1u << C.bpbits, 1); memset(bpt, 1, 1u << C.bpbits);

    uint32_t x[32] = {0}, pc = entry;
    x[2] = MEMSZ - 16;
    uint64_t now = 0, fetch_ready = 0, ready[32] = {0}, instret = 0;
    uint64_t region_t0[MAXREG] = {0}, region_i0[MAXREG] = {0};
    int region = 0; uint32_t last_iline = 0xFFFFFFFF;
    int exitcode = -1; uint64_t prev = 0;
    uint64_t n_mul = 0, n_div = 0, n_ld = 0, n_st = 0, n_br = 0, n_cust = 0, stall_lu = 0;
    capsamp = 1024; samples = malloc(sizeof(double) * capsamp);

    while (instret < (uint64_t)C.maxinstr) {
        if (pc >= MEMSZ || (pc & 3)) { fprintf(stderr, "bad pc %08x\n", pc); exitcode = 99; break; }
        uint32_t in = *(uint32_t *)(mem + pc);
        uint32_t op = in & 0x7f, rd = (in >> 7) & 31, f3 = (in >> 12) & 7, rs1 = (in >> 15) & 31,
                 rs2 = (in >> 20) & 31, f7 = in >> 25;
        int32_t immI = (int32_t)in >> 20;
        int32_t immS = ((int32_t)(in & 0xfe000000) >> 20) | ((in >> 7) & 31);
        int32_t immB = ((int32_t)(in & 0x80000000) >> 19) | ((in & 0x80) << 4) | ((in >> 20) & 0x7e0) | ((in >> 7) & 0x1e);
        int32_t immU = (int32_t)(in & 0xfffff000);
        int32_t immJ = ((int32_t)(in & 0x80000000) >> 11) | (in & 0xff000) | ((in >> 9) & 0x800) | ((in >> 20) & 0x7fe);
        uint32_t a = x[rs1], b = x[rs2], r = 0, npc = pc + 4;
        int use1 = 0, use2 = 0, wr = 0;
        /* ---- front end */
        uint64_t t = fetch_ready > now + 1 ? fetch_ready : now + 1;
        if (instret == 0) t = 0;
        uint32_t iline = pc >> 5;
        if (IC.on && iline != last_iline) { t += cache_access(&IC, pc, 0); last_iline = iline; }
        uint64_t lat = 1;      /* cycles until result usable by next instruction in EX */
        uint64_t block = 0;    /* extra cycles the whole pipeline is held */
        switch (op) {
        case 0x37: r = immU; wr = 1; break;
        case 0x17: r = pc + immU; wr = 1; break;
        case 0x6f: if (immJ == 0 && rd == 0) { a0_out = x[10]; exitcode = 0; instret++; now = t; goto done; }
            r = pc + 4; wr = 1; npc = pc + immJ; block = C.jalpen;
            if (C.ras && rd == 1) { ras_stk[ras_sp & 15] = pc + 4; ras_sp++; } break;
        case 0x67: use1 = 1; r = pc + 4; wr = 1; npc = (a + immI) & ~1u;
            if (C.ras && rd == 0 && rs1 == 1 && ras_sp > 0) { ras_sp--; block = (ras_stk[ras_sp & 15] == npc) ? C.jalpen : C.brpen; }
            else { block = C.brpen; if (C.ras && rd == 1) { ras_stk[ras_sp & 15] = pc + 4; ras_sp++; } }
            break;
        case 0x63: { use1 = use2 = 1; int tk = 0;
            switch (f3) { case 0: tk = a == b; break; case 1: tk = a != b; break;
                case 4: tk = (int32_t)a < (int32_t)b; break; case 5: tk = (int32_t)a >= (int32_t)b; break;
                case 6: tk = a < b; break; case 7: tk = a >= b; break; }
            int pr = bp_predict(pc, immB); bp_update(pc, tk); br_n++; n_br++;
            if (pr != tk) { br_miss++; block = C.brpen; }
            if (tk) npc = pc + immB; break; }
        case 0x03: { use1 = 1; uint32_t ad = a + immI; n_ld++;
            if (ad >= MEMSZ) { fprintf(stderr, "load fault %08x pc %08x\n", ad, pc); exitcode = 98; goto done; }
            switch (f3) { case 0: r = (int8_t)mem[ad]; break; case 1: r = (int16_t)*(uint16_t *)(mem + ad); break;
                case 2: r = *(uint32_t *)(mem + ad); break; case 4: r = mem[ad]; break; case 5: r = *(uint16_t *)(mem + ad); break; }
            wr = 1; lat = 1 + C.loaduse; block = cache_access(&DC, ad, 0); break; }
        case 0x23: { use1 = use2 = 1; uint32_t ad = a + immS; n_st++;
            if (ad >= MMIO) {
                uint32_t reg = ad - MMIO;
                if (reg == 0) fputc((int)(b & 0xff), stderr);
                else if (reg == 4) { exitcode = (int)b; a0_out = b; instret++; now = t; goto done; }
                else if (reg == 8) { region = (int)(b % MAXREG); region_t0[region] = t; region_i0[region] = instret; }
                else if (reg == 12) { int id = (int)(b % MAXREG);
                    reg_cyc[id] += t - region_t0[id]; reg_ins[id] += instret - region_i0[id];
                    if (nsamp == capsamp) { capsamp *= 2; samples = realloc(samples, sizeof(double) * capsamp); }
                    samples[nsamp++] = (double)(t - region_t0[id]); region = 0;
                    if (C.latmap && id == 4) { uint32_t nw = (text_hi - text_lo) / 4;
                        for (uint32_t q = 0; q < nw; q++) { if (lat_first) lat_ref[q] = lat_cur[q]; else if (lat_cur[q] != lat_ref[q]) lat_var[q] = 1; lat_cur[q] = 0; }
                        lat_first = 0; } }
                else if (reg == 16) { if (nvals < 65536) vals[nvals++] = b; }
                break; }
            if (ad >= MEMSZ) { fprintf(stderr, "store fault %08x pc %08x\n", ad, pc); exitcode = 97; goto done; }
            switch (f3) { case 0: mem[ad] = (uint8_t)b; break; case 1: *(uint16_t *)(mem + ad) = (uint16_t)b; break;
                case 2: *(uint32_t *)(mem + ad) = b; break; }
            block = cache_access(&DC, ad, 1); break; }
        case 0x13: use1 = 1; wr = 1;
            switch (f3) { case 0: r = a + immI; break; case 2: r = (int32_t)a < immI; break; case 3: r = a < (uint32_t)immI; break;
                case 4: r = a ^ immI; break; case 6: r = a | immI; break; case 7: r = a & immI; break;
                case 1: r = a << (immI & 31); break;
                case 5: r = (in >> 30) & 1 ? (uint32_t)((int32_t)a >> (immI & 31)) : a >> (immI & 31); break; }
            break;
        case 0x33: use1 = use2 = 1; wr = 1;
            if (f7 == 1) {
                if (f3 < 4) { n_mul++;
                    switch (f3) { case 0: r = a * b; break;
                        case 1: r = (uint32_t)(((int64_t)(int32_t)a * (int32_t)b) >> 32); break;
                        case 2: r = (uint32_t)(((int64_t)(int32_t)a * (uint64_t)b) >> 32); break;
                        case 3: r = (uint32_t)(((uint64_t)a * b) >> 32); break; }
                    int L = mul_lat2(a, b, f3 != 0); if (L < 0) L = mul_lat(b, f3 != 0);
                    if (C.latmap && region == 4) latrec(pc, L);
                    if (!strcmp(C.mul, "3p")) lat = 3; else if (L > 1) { block = L - 1; lat = 1; }
                } else { n_div++;
                    switch (f3) {
                    case 4: r = b == 0 ? 0xffffffff : ((int32_t)a == INT32_MIN && (int32_t)b == -1) ? a : (uint32_t)((int32_t)a / (int32_t)b); break;
                    case 5: r = b == 0 ? 0xffffffff : a / b; break;
                    case 6: r = b == 0 ? a : ((int32_t)a == INT32_MIN && (int32_t)b == -1) ? 0 : (uint32_t)((int32_t)a % (int32_t)b); break;
                    case 7: r = b == 0 ? a : a % b; break; }
                    block = div_lat(a, b, f3 == 4 || f3 == 6) - 1;
                    if (C.latmap && region == 4) latrec(pc, (int)block + 1);
                }
            } else switch (f3) {
                case 0: r = f7 ? a - b : a + b; break; case 1: r = a << (b & 31); break;
                case 2: r = (int32_t)a < (int32_t)b; break; case 3: r = a < b; break; case 4: r = a ^ b; break;
                case 5: r = f7 ? (uint32_t)((int32_t)a >> (b & 31)) : a >> (b & 31); break;
                case 6: r = a | b; break; case 7: r = a & b; break; }
            break;
        case 0x0f: break;      /* fence */
        case 0x73: break;      /* ecall/csr: ignored */
        case 0x0b: n_cust++; use1 = 1; wr = 1;
            switch (f3) {
            case 0: r = (uint32_t)(int32_t)kmred((int32_t)a); lat = C.lat_kmul; break;
            case 1: use2 = 1; r = (uint32_t)(int32_t)kmred((int32_t)(int16_t)a * (int16_t)b); lat = C.lat_kmul; break;
            case 2: r = (uint32_t)(int32_t)kbar((int16_t)a); lat = C.lat_kmul; break;
            case 3: { use2 = 1; int16_t lo = (int16_t)a, hi = (int16_t)(a >> 16);
                int16_t tt = kmred((int32_t)(int16_t)b * hi);
                r = (uint16_t)(int16_t)(lo + tt) | ((uint32_t)(uint16_t)(int16_t)(lo - tt) << 16); lat = C.lat_kbfly; break; }
            case 4: { use2 = 1; int16_t lo = (int16_t)a, hi = (int16_t)(a >> 16);
                int16_t nlo = kbar((int16_t)(lo + hi)); int16_t d = (int16_t)(hi - lo);
                int16_t nhi = kmred((int32_t)(int16_t)b * d);
                r = (uint16_t)nlo | ((uint32_t)(uint16_t)nhi << 16); lat = C.lat_kbfly; break; }
            case 6: use2 = 1; r = f7 ? (uint32_t)(((uint64_t)a * b) >> 32) : a * b; lat = 1; break;
            case 5: use2 = 1; r = (uint32_t)dmred((int64_t)(int32_t)a * (int32_t)b); lat = C.lat_dmul; break;
            case 7: { wr = 0; uint64_t st[25]; if (a + 200 > MEMSZ) { exitcode = 96; goto done; }
                memcpy(st, mem + a, 200); keccakf(st); memcpy(mem + a, st, 200);
                block = C.lat_keccak - 1;
                for (int k = 0; k < 200; k += 4) { block += cache_access(&DC, a + k, 0); }
                for (int k = 0; k < 200; k += C.line) block += cache_access(&DC, a + k, 1);
                break; }
            default: fprintf(stderr, "bad custom f3 %u\n", f3); exitcode = 95; goto done; }
            break;
        default: fprintf(stderr, "illegal instr %08x at %08x\n", in, pc); exitcode = 94; goto done;
        }
        if (use1 && rs1 && ready[rs1] > t) { if (op == 0x03 || op == 0x23 || 1) stall_lu += ready[rs1] - t; t = ready[rs1]; }
        if (use2 && rs2 && ready[rs2] > t) { stall_lu += ready[rs2] - t; t = ready[rs2]; }
        /* re-evaluate data-dependent blocking after operand stall (block is relative to issue) */
        now = t;
        if (wr && rd) { x[rd] = r; ready[rd] = now + lat + block; }
        fetch_ready = now + 1 + block;
        if (C.profile) {
            uint32_t fi = (pc >= text_lo && pc < text_hi) ? pc2f[(pc - text_lo) / 4] : 0;
            prof_cyc[region][fi] += (now + 1 + block) - (prev ? prev : 0);
            prof_ins[region][fi]++;
            prev = now + 1 + block;
        }
        pc = npc; instret++;
    }
done:;
    uint64_t cycles = now + 5;
    FILE *o = out ? fopen(out, "w") : stdout;
    fprintf(o, "{\"exit\":%d,\"a0\":%u,\"cycles\":%llu,\"instret\":%llu,", exitcode, a0_out, (unsigned long long)cycles, (unsigned long long)instret);
    fprintf(o, "\"mix\":{\"mul\":%llu,\"div\":%llu,\"load\":%llu,\"store\":%llu,\"branch\":%llu,\"custom\":%llu},",
        (unsigned long long)n_mul, (unsigned long long)n_div, (unsigned long long)n_ld, (unsigned long long)n_st,
        (unsigned long long)n_br, (unsigned long long)n_cust);
    fprintf(o, "\"bp\":{\"n\":%llu,\"miss\":%llu},\"ic\":{\"acc\":%llu,\"miss\":%llu},\"dc\":{\"acc\":%llu,\"miss\":%llu,\"wb\":%llu},",
        (unsigned long long)br_n, (unsigned long long)br_miss, (unsigned long long)IC.acc, (unsigned long long)IC.miss,
        (unsigned long long)DC.acc, (unsigned long long)DC.miss, (unsigned long long)DC.wb);
    fprintf(o, "\"regions\":{");
    int first = 1;
    for (int i = 0; i < MAXREG; i++) if (reg_ins[i]) {
        fprintf(o, "%s\"%d\":{\"cycles\":%llu,\"instret\":%llu}", first ? "" : ",", i,
            (unsigned long long)reg_cyc[i], (unsigned long long)reg_ins[i]); first = 0; }
    fprintf(o, "},\"samples\":[");
    for (int i = 0; i < nsamp; i++) fprintf(o, "%s%.0f", i ? "," : "", samples[i]);
    fprintf(o, "],\"vals\":[");
    for (int i = 0; i < nvals; i++) fprintf(o, "%s%u", i ? "," : "", vals[i]);
    fprintf(o, "],\"varlat\":[");
    { int fst = 1; for (uint32_t q = 0; q < (text_hi - text_lo) / 4; q++) if (lat_max[q] && lat_min[q] != lat_max[q]) {
        uint32_t fi = pc2f[q]; fprintf(o, "%s[\"%s\",%u,%u,%u,%u]", fst ? "" : ",", syms[fi].name, text_lo + 4 * q, lat_min[q], lat_max[q], lat_var[q]); fst = 0; } }
    fprintf(o, "],\"profile\":{");
    first = 1;
    if (C.profile) for (int g = 0; g < MAXREG; g++) {
        int any = 0; for (int i = 0; i <= nsyms; i++) if (prof_ins[g][i]) any = 1;
        if (!any) continue;
        fprintf(o, "%s\"%d\":{", first ? "" : ",", g); first = 0;
        int f2 = 1;
        for (int i = 0; i <= nsyms; i++) if (prof_ins[g][i]) {
            fprintf(o, "%s\"%s\":[%llu,%llu]", f2 ? "" : ",", syms[i].name,
                (unsigned long long)prof_cyc[g][i], (unsigned long long)prof_ins[g][i]); f2 = 0; }
        fprintf(o, "}");
    }
    fprintf(o, "}}\n");
    if (out) fclose(o);
    return exitcode == 0 ? 0 : 1;
}
