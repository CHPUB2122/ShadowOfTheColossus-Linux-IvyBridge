/* sotc: Linux signal frames stay off guest stacks and their live red zones. */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "runtime.h"
#ifdef _WIN32
int runtime_signal_stack_prepare(void) { return 1; }
#else
#include <signal.h>
#include <pthread.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

typedef struct { void *memory; size_t size; } SignalStack;
static pthread_key_t signal_stack_key;
static pthread_once_t signal_stack_once=PTHREAD_ONCE_INIT;
static int signal_stack_key_ok;
static void signal_stack_free(void *data) {
    SignalStack *s=data;
    stack_t disabled={.ss_flags=SS_DISABLE};
    sigaltstack(&disabled,NULL);
    munmap(s->memory,s->size);
    free(s);
}
static void signal_stack_key_create(void) {
    signal_stack_key_ok=pthread_key_create(&signal_stack_key,signal_stack_free)==0;
}
int runtime_signal_stack_prepare(void) {
    pthread_once(&signal_stack_once,signal_stack_key_create);
    if (!signal_stack_key_ok) return 0;
    if (pthread_getspecific(signal_stack_key)) return 1;
    stack_t current;
    if (sigaltstack(NULL,&current)) return 0;
    if (!(current.ss_flags&SS_DISABLE)) return current.ss_size>=256*1024;
    const size_t page=(size_t)sysconf(_SC_PAGESIZE), usable=256*1024;
    SignalStack *s=malloc(sizeof(*s));
    if (!s) return 0;
    s->size=usable+2*page;
    s->memory=mmap(NULL,s->size,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if (s->memory==MAP_FAILED) { free(s); return 0; }
    stack_t stack={.ss_sp=(char *)s->memory+page,.ss_size=usable};
    if (mprotect(stack.ss_sp,usable,PROT_READ|PROT_WRITE) ||
        sigaltstack(&stack,NULL) || pthread_setspecific(signal_stack_key,s)) {
        stack_t disabled={.ss_flags=SS_DISABLE};
        sigaltstack(&disabled,NULL);
        munmap(s->memory,s->size); free(s); return 0;
    }
    return 1;
}
#endif
