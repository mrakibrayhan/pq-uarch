/* PQ-uArch custom-0 instruction intrinsics (see sim/rvsim.c for semantics). */
#ifndef PQEXT_H
#define PQEXT_H
#include <stdint.h>
static inline int32_t PQ_KMRED(int32_t a) { int32_t r; __asm__(".insn r 0x0b, 0, 0, %0, %1, x0" : "=r"(r) : "r"(a)); return r; }
static inline int32_t PQ_KMUL(int32_t a, int32_t b) { int32_t r; __asm__(".insn r 0x0b, 1, 0, %0, %1, %2" : "=r"(r) : "r"(a), "r"(b)); return r; }
static inline int32_t PQ_KBAR(int32_t a) { int32_t r; __asm__(".insn r 0x0b, 2, 0, %0, %1, x0" : "=r"(r) : "r"(a)); return r; }
static inline uint32_t PQ_KCT(uint32_t p, int32_t z) { uint32_t r; __asm__(".insn r 0x0b, 3, 0, %0, %1, %2" : "=r"(r) : "r"(p), "r"(z)); return r; }
static inline uint32_t PQ_KGS(uint32_t p, int32_t z) { uint32_t r; __asm__(".insn r 0x0b, 4, 0, %0, %1, %2" : "=r"(r) : "r"(p), "r"(z)); return r; }
static inline int32_t PQ_DMUL(int32_t a, int32_t b) { int32_t r; __asm__(".insn r 0x0b, 5, 0, %0, %1, %2" : "=r"(r) : "r"(a), "r"(b)); return r; }
static inline uint32_t PQ_CMUL(uint32_t a, uint32_t b) { uint32_t r; __asm__(".insn r 0x0b, 6, 0, %0, %1, %2" : "=r"(r) : "r"(a), "r"(b)); return r; }
static inline uint32_t PQ_CMULHU(uint32_t a, uint32_t b) { uint32_t r; __asm__(".insn r 0x0b, 6, 1, %0, %1, %2" : "=r"(r) : "r"(a), "r"(b)); return r; }
static inline void PQ_KECCAK(uint64_t *s) { __asm__ volatile(".insn r 0x0b, 7, 0, x0, %0, x0" : : "r"(s) : "memory"); }
#endif
