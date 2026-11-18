ENTRY(_start)
SECTIONS {
  . = 0x0;
  .text : { *(.text.start) *(.text*) }
  . = 0x10000;                       /* data space (dmem), separate from imem */
  .rodata : { *(.rodata*) *(.srodata*) }
  .data : { *(.data*) *(.sdata*) }
  . = ALIGN(4);
  __bss_start = .;
  .bss : { *(.bss*) *(.sbss*) *(COMMON) }
  . = ALIGN(4);
  __bss_end = .;
  __heap_start = ALIGN(16);
}
