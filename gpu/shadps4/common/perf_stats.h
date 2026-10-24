// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: the part of Pink-shadPS4's performance statistics that its command recorder
// (vk_recorder.cpp) reports to. Statistics are off here: every call compiles to nothing.
#pragma once

#include "common/types.h"

namespace Common::PerfStats {

enum class Id : u32 {
    RecorderCommands,
    RecorderDrains,
    RecorderDrainNs,
    RecorderBusyNs,
    RecorderSubmitWaits,
    RecorderSubmitWaitNs,
    RecorderWakes,
};

constexpr bool Enabled() noexcept {
    return false;
}

constexpr void Add(Id, u64 = 1) noexcept {}

} // namespace Common::PerfStats
