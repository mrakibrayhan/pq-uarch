/* Validation kernels for the RTL core. main() returns an FNV-1a hash of the outputs in a0,
 * so the RTL run, the PQ-uArch simulator and a native build can be compared bit-exactly.
 *   KERNEL 1: SHAKE256 over 1 KB (Keccak-f[1600] dominated)
 *   KERNEL 2: ML-KEM-512 NTT + INTT on 2 polynomials
 *   KERNEL 3: ML-DSA-44 NTT + INTT on 1 polynomial
 *   KERNEL 4: ML-KEM-512 KeyGen + Encaps + Decaps
 *   KERNEL 5: ML-KEM-768 KeyGen + Encaps + Decaps
 *   KERNEL 6: ML-DSA-44 KeyGen + Sign + Verify
 */
#include <stddef.h>
#include <stdint.h>
#include "fips202.h"
#define CAT2(a, b) a##_##b
#define CAT(a, b) CAT2(a, b)
#define F(x) CAT(NS, x)
static uint32_t h = 2166136261u;
static void mix(const void *p, size_t n) { const uint8_t *b = p; while (n--) { h ^= *b++; h *= 16777619u; } }
#if KERNEL == 1
static uint8_t in[1024], out[64];
int main(void) { for (int i = 0; i < 1024; i++) in[i] = (uint8_t)(i * 31 + 7); shake256(out, 64, in, 1024); mix(out, 64); return (int)h; }
#elif KERNEL == 2
#include "ntt.h"
static int16_t a[2][256];
int main(void) {
    for (int k = 0; k < 2; k++) {
        for (int i = 0; i < 256; i++) a[k][i] = (int16_t)((i * 17 + k * 5) % 3329);
        F(ntt)(a[k]); F(invntt)(a[k]); mix(a[k], sizeof a[k]);
    }
    return (int)h;
}
#elif KERNEL == 3
#include "ntt.h"
static int32_t a[256];
int main(void) { for (int i = 0; i < 256; i++) a[i] = (int32_t)((i * 7919) % 8380417);
    F(ntt)(a); F(invntt_tomont)(a); mix(a, sizeof a); return (int)h; }
#elif KERNEL == 4 || KERNEL == 5
#include "api.h"
static uint8_t pk[F(CRYPTO_PUBLICKEYBYTES)], sk[F(CRYPTO_SECRETKEYBYTES)], ct[F(CRYPTO_CIPHERTEXTBYTES)], s1[32], s2[32];
int main(void) { F(crypto_kem_keypair)(pk, sk); F(crypto_kem_enc)(ct, s1, pk); F(crypto_kem_dec)(s2, ct, sk);
    mix(ct, sizeof ct); mix(s1, 32); for (int i = 0; i < 32; i++) if (s1[i] != s2[i]) return 1; return (int)h; }
#elif KERNEL == 6
#include "api.h"
static uint8_t pk[F(CRYPTO_PUBLICKEYBYTES)], sk[F(CRYPTO_SECRETKEYBYTES)], sig[F(CRYPTO_BYTES)], m[32];
int main(void) { size_t sl; for (int i = 0; i < 32; i++) m[i] = (uint8_t)i;
    F(crypto_sign_keypair)(pk, sk); F(crypto_sign_signature)(sig, &sl, m, 32, sk);
    if (F(crypto_sign_verify)(sig, sl, m, 32, pk)) return 1; mix(sig, sl); return (int)h; }
#endif
