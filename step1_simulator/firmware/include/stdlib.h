#ifndef MIN_STDLIB_H
#define MIN_STDLIB_H
#include <stddef.h>
void *malloc(size_t n);
void free(void *p);
void exit(int c) __attribute__((noreturn));
void abort(void) __attribute__((noreturn));
#endif
