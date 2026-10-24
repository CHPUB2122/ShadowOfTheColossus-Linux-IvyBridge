/* sotc: optional cumulative render diagnostics, also readable by the Linux watchdog.
 * Snapshot reads are lock-free; no rendering state or synchronization is changed. */
#pragma once
#include <stdint.h>

#define SOTC_RENDER_COUNTERS(X) \
    X(GNM_SUBMIT, "gnm_submit") X(GNM_FLIP, "gnm_submit_flip") \
    X(GFX_QUEUED, "gfx_queued") X(GFX_STARTED, "gfx_started") X(GFX_FINISHED, "gfx_finished") \
    X(DRAW, "draw_calls") X(DISPATCH, "dispatch_calls") \
    X(VK_SUBMIT, "vk_submit_enter") X(VK_SUBMITTED, "vk_submit_success") \
    X(FLIP_REQUEST, "flip_request") X(FLIP_QUEUED, "flip_queued") X(FLIP_DEQUEUED, "flip_dequeued") \
    X(FLIP_SIGNAL, "flip_event_found") X(FLIP_MISSING, "flip_event_missing") \
    X(FLIP_CONSUMED, "flip_event_consumed") \
    X(GNM_SIGNAL, "gnm_event_found") X(GNM_MISSING, "gnm_event_missing") \
    X(GNM_CONSUMED, "gnm_event_consumed") \
    X(GAME_PRESENT, "game_present_return") X(AUX_PRESENT, "aux_present_return") \
    X(READ_REQUEST, "buffer_read_enter") X(READ_COMPLETE, "buffer_read_return") \
    X(GUEST_FAULT, "guest_fault_attempt") X(FAULT_PC, "last_fault_pc") X(FAULT_ADDR, "last_fault_addr")

enum SotcRenderCounter {
#define SOTC_DIAG_ENUM(id, name) SOTC_DIAG_##id,
    SOTC_RENDER_COUNTERS(SOTC_DIAG_ENUM)
#undef SOTC_DIAG_ENUM
    SOTC_DIAG_COUNT
};

#ifdef __cplusplus
extern "C" {
#endif
int bbgpu_render_diag_snapshot(uint64_t values[SOTC_DIAG_COUNT]);
const char *bbgpu_render_diag_name(int index);
#ifdef __cplusplus
}

#include <atomic>
#include <cstdlib>
namespace SotcRenderDiag {
inline const bool enabled = [] {
    const char* value = std::getenv("SOTC_RENDER_DIAG");
    return value && value[0] == '1';
}();
static_assert(std::atomic<uint64_t>::is_always_lock_free);
inline std::atomic<uint64_t> counters[SOTC_DIAG_COUNT]{};
inline void Count(SotcRenderCounter counter) {
    if (enabled) counters[counter].fetch_add(1, std::memory_order_relaxed);
}
struct Operation {
    SotcRenderCounter complete;
    Operation(SotcRenderCounter begin, SotcRenderCounter end) : complete{end} { Count(begin); }
    ~Operation() { Count(complete); }
};
void Report(); // existing vblank thread; at most one line per five seconds
}
#endif
