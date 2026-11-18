/* PQ-uArch harness: one source for ML-KEM and ML-DSA, all modes.
 *   -DNS=<PQClean namespace>  -DIS_KEM / -DIS_DSA
 *   -DMODE_PERF : region 1/2/3 = keygen/encaps(sign)/decaps(verify)
 *   -DMODE_LEAK : region 4 = ML-KEM decaps, fixed-vs-random ciphertext classes
 *   -DNATIVE    : host build that prints the same values (for KAT cross-check)
 */
#include <stddef.h>
#include <stdint.h>
#include "api.h"
#define CAT2(a, b) a##_##b
#define CAT(a, b) CAT2(a, b)
#define F(x) CAT(NS, x)
void rng_seed(uint64_t s); uint64_t rng_next(void);
#ifdef NATIVE
#include <stdio.h>
static void pq_val(uint32_t v) { printf("%u\n", v); }
static void rbeg(int i) { (void)i; }
static void rend(int i) { (void)i; }
#else
#define MMIO ((volatile uint32_t *)0xFFFF0000u)
static void pq_val(uint32_t v) { MMIO[4] = v; }
static inline void rbeg(int i) { __asm__ volatile("" ::: "memory"); MMIO[2] = (uint32_t)i; __asm__ volatile("" ::: "memory"); }
static inline void rend(int i) { __asm__ volatile("" ::: "memory"); MMIO[3] = (uint32_t)i; __asm__ volatile("" ::: "memory"); }
#endif
static uint32_t fnv(const uint8_t *p, size_t n) { uint32_t h = 2166136261u; while (n--) { h ^= *p++; h *= 16777619u; } return h; }
#ifndef NTRIALS
#define NTRIALS 400
#endif

#ifdef IS_KEM
static uint8_t pk[F(CRYPTO_PUBLICKEYBYTES)], sk[F(CRYPTO_SECRETKEYBYTES)];
static uint8_t ct[F(CRYPTO_CIPHERTEXTBYTES)], ct0[F(CRYPTO_CIPHERTEXTBYTES)], ss1[32], ss2[32];
int main(void) {
#ifdef MODE_PERF
    for (int it = 0; it < 2; it++) {            /* it=0 warms caches/predictors */
        if (it) rbeg(1); F(crypto_kem_keypair)(pk, sk); if (it) rend(1);
        if (it) rbeg(2); F(crypto_kem_enc)(ct, ss1, pk); if (it) rend(2);
        if (it) rbeg(3); F(crypto_kem_dec)(ss2, ct, sk); if (it) rend(3);
    }
    pq_val(fnv(pk, sizeof pk)); pq_val(fnv(ct, sizeof ct)); pq_val(fnv(ss1, 32));
    for (int i = 0; i < 32; i++) if (ss1[i] != ss2[i]) return 1;
    return 0;
#else /* MODE_LEAK */
    /* LEAKTEST=1: fixed vs random valid ciphertext (fixed key)  -- TVLA fixed-vs-random
     * LEAKTEST=2: random valid vs random invalid ciphertext (fixed key) -- FO
     *             implicit-rejection path must not be distinguishable by time.
     * The class is applied with a branch-free masked select that reads both
     * candidate buffers, so cache/predictor state before the measured
     * decapsulation does not depend on the class (removes harness artefacts). */
    static uint8_t ctr[sizeof ct], cti[sizeof ct];
    F(crypto_kem_keypair)(pk, sk);
    F(crypto_kem_enc)(ct0, ss1, pk);
    F(crypto_kem_dec)(ss2, ct0, sk);              /* warm-up */
    for (int i = 0; i < NTRIALS; i++) {
        uint32_t cls = (uint32_t)(rng_next() & 1);
        uint8_t m = (uint8_t)(0u - cls);
        F(crypto_kem_enc)(ctr, ss1, pk);
#if LEAKTEST == 2
        for (size_t k = 0; k < sizeof ct; k += 8) { uint64_t r = rng_next(); for (int q = 0; q < 8 && k + q < sizeof ct; q++) cti[k + q] = (uint8_t)(r >> (8 * q)); }
        for (size_t k = 0; k < sizeof ct; k++) ct[k] = (uint8_t)((cti[k] & m) | (ctr[k] & (uint8_t)~m));
#else
        for (size_t k = 0; k < sizeof ct; k++) ct[k] = (uint8_t)((ctr[k] & m) | (ct0[k] & (uint8_t)~m));
#endif
        pq_val(cls);
        rbeg(4); F(crypto_kem_dec)(ss2, ct, sk); rend(4);
    }
    return 0;
#endif
}
#endif

#ifdef IS_DSA
#ifndef NSIGN
#define NSIGN 10
#endif
static uint8_t pk[F(CRYPTO_PUBLICKEYBYTES)], sk[F(CRYPTO_SECRETKEYBYTES)], sig[F(CRYPTO_BYTES)], msg[32];
int main(void) {
    size_t siglen; int bad = 0; uint32_t h = 0;
    for (int it = 0; it < 1 + NSIGN; it++) {     /* it=0 warms caches/predictors */
        for (int i = 0; i < 32; i++) msg[i] = (uint8_t)(i * 7 + it);
        if (it) rbeg(1); F(crypto_sign_keypair)(pk, sk); if (it) rend(1);
        if (it) rbeg(2); F(crypto_sign_signature)(sig, &siglen, msg, 32, sk); if (it) rend(2);
        if (it) rbeg(3); bad |= F(crypto_sign_verify)(sig, siglen, msg, 32, pk); if (it) rend(3);
        h ^= fnv(sig, siglen);
    }
    pq_val(fnv(pk, sizeof pk)); pq_val(h); pq_val((uint32_t)bad);
    return bad;
}
#endif
