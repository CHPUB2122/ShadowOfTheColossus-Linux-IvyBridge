// sotc: stand-in for shadPS4's core/tls.h. cpu_patches.cpp still compiles its TCB patch
// generators, but they are not in its patch table: the loader (src/probe.c) redirects the
// guest's `mov reg, fs:[0]` loads to the TEB TLS slot itself.
#pragma once
#include "common/types.h"

namespace Core {
struct Tcb {
    Tcb* tcb_self;
    void* tcb_dtv;
    void* tcb_thread;
    void* tcb_fiber;
};
inline u32 GetTcbKey() {
    return 0;
}
} // namespace Core
