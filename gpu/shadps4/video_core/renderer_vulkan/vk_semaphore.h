// SPDX-FileCopyrightText: Copyright 2020 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include <atomic>
#include <condition_variable>
#include <thread>
#include <queue>
#include "common/types.h"
#include "video_core/renderer_vulkan/vk_common.h"

VK_DEFINE_HANDLE(VmaAllocation)

namespace Vulkan {

/// sotc: SOTC_WAIT_SPIN_US, microseconds GPU waits poll before sleeping (0 = off).
u32 SotcWaitSpinUs();

class Instance;
class Scheduler;

class Semaphore {
public:
    explicit Semaphore(const Instance& instance_);
    ~Semaphore();

    [[nodiscard]] u64 CurrentTick() const noexcept {
        return current_tick.load(std::memory_order_acquire);
    }

    [[nodiscard]] u64 KnownGpuTick() const noexcept {
        return gpu_tick.load(std::memory_order_acquire);
    }

    [[nodiscard]] bool IsFree(u64 tick) const noexcept {
        return KnownGpuTick() >= tick;
    }

    [[nodiscard]] u64 NextTick() noexcept {
        return current_tick.fetch_add(1, std::memory_order_release);
    }

    [[nodiscard]] vk::Semaphore Handle() const noexcept {
        return semaphore.get();
    }

    /// Refresh the known GPU tick
    void Refresh();

    /// Waits for a tick to be hit on the GPU
    void Wait(u64 tick);

    /// sotc (wait_marker of Pink-shadPS4, luizgustavs): waits until the host can read the GPU
    /// writes of everything up to tick. With SOTC_WAIT_MARKER=2 it returns as soon as the GPU has
    /// written the marker recorded at the end of that submission, before the driver reports the
    /// semaphore; the known GPU tick is left alone, so nothing of that submission is reused early.
    void WaitHostRead(u64 tick);

    /// Marker words written by the GPU, one per cache line.
    enum class MarkerSlot : u32 { Timeline = 0, Ahead = 1 };

    [[nodiscard]] bool HasMarker() const noexcept {
        return static_cast<bool>(marker_buffer);
    }

    /// Records, after every earlier command, the write of value into slot, visible to the host
    /// together with all earlier writes. Outside a render pass.
    void RecordMarker(vk::CommandBuffer cmdbuf, MarkerSlot slot, u32 value) const;

    [[nodiscard]] bool MarkerReached(MarkerSlot slot, u64 value) const noexcept;

    /// Polls the marker of slot for up to the spin budget; true when it reached value.
    bool SpinMarker(MarkerSlot slot, u64 value) const;

    [[nodiscard]] bool TrustMarker() const noexcept {
        return marker_mode >= 2 && HasMarker();
    }

protected:
    const Instance& instance;
    vk::UniqueSemaphore semaphore;    ///< Timeline semaphore.
    std::atomic<u64> gpu_tick{0};     ///< Current known GPU tick.
    std::atomic<u64> current_tick{1}; ///< Current logical tick.
    u32 marker_mode{};                ///< SOTC_WAIT_MARKER
    u32 marker_spin_us{};             ///< How long a wait polls the marker
    vk::Buffer marker_buffer{};
    VmaAllocation marker_allocation{};
    const volatile u32* marker_data{};
};

} // namespace Vulkan
