/* Deterministic randombytes() (splitmix64) so every run is reproducible
 * and the simulator output can be checked against a native build. */
#include <stddef.h>
#include <stdint.h>
static uint64_t st = 0x5EED5EED12345678ULL;
void rng_seed(uint64_t s) { st = s; }
uint64_t rng_next(void) { uint64_t z = (st += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL; z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL; return z ^ (z >> 31); }
int PQCLEAN_randombytes(uint8_t *out, size_t n) { while (n) { uint64_t v = rng_next(); for (int i = 0; i < 8 && n; i++, n--) *out++ = (uint8_t)(v >> (8 * i)); } return 0; }
