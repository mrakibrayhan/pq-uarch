/* Host wrapper: prints the kernel's return value (same hash the RTL core leaves in a0). */
#undef main
#include <stdio.h>
#include <stdint.h>
int kmain(void);
int main(void) { printf("%u\n", (uint32_t)kmain()); return 0; }
