/* Minimal freestanding C runtime for the PQ-uArch simulator. */
#include <stddef.h>
#include <stdint.h>
#define MMIO ((volatile uint32_t *)0xFFFF0000u)
void *memcpy(void *d, const void *s, size_t n) { uint8_t *a = d; const uint8_t *b = s;
    if ((((uintptr_t)a | (uintptr_t)b | n) & 3) == 0) { uint32_t *x = d; const uint32_t *y = s; for (size_t i = 0; i < n / 4; i++) x[i] = y[i]; return d; }
    while (n--) *a++ = *b++; return d; }
void *memmove(void *d, const void *s, size_t n) { uint8_t *a = d; const uint8_t *b = s;
    if (a < b) while (n--) *a++ = *b++; else { a += n; b += n; while (n--) *--a = *--b; } return d; }
void *memset(void *d, int c, size_t n) { uint8_t *a = d; while (n--) *a++ = (uint8_t)c; return d; }
int memcmp(const void *x, const void *y, size_t n) { const uint8_t *a = x, *b = y;
    for (size_t i = 0; i < n; i++) if (a[i] != b[i]) return a[i] - b[i]; return 0; }
size_t strlen(const char *s) { size_t n = 0; while (s[n]) n++; return n; }
void exit(int c) { MMIO[1] = (uint32_t)c; for (;;) ; }
void abort(void) { exit(134); }
/* tiny allocator: 256-byte block free-list for small requests, bump for large */
extern char __heap_start[];
static char *brk_p = 0; static void *fl = 0;
void *malloc(size_t n) {
    if (!brk_p) brk_p = __heap_start;
    if (n <= 248) { if (fl) { void *p = fl; fl = *(void **)fl; return p; }
        void *p = brk_p + 8; ((uint32_t *)brk_p)[0] = 256; brk_p += 256; return p; }
    size_t s = (n + 8 + 15) & ~(size_t)15; void *p = brk_p + 8; ((uint32_t *)brk_p)[0] = (uint32_t)s; brk_p += s; return p; }
void free(void *p) { if (!p) return; if (((uint32_t *)((char *)p - 8))[0] == 256) { *(void **)p = fl; fl = p; } }
