/* Runtime-only tests have no loaded game image or observed BPE heaps. */
#include <stdint.h>
uintptr_t runtime_sotc_heap(void) { return 0; }
uintptr_t runtime_sotc_heap_table(void) { return 0; }
