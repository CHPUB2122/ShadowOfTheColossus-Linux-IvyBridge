// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: pure decoding helpers shared by CPU patch scanners, independent of host exception APIs.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <Zydis/Zydis.h>

namespace Core::CpuPatchScanner {
using Operands = std::array<ZydisDecodedOperand, ZYDIS_MAX_OPERAND_COUNT>;

// Failure always leaves length == 0. Never decode beyond the supplied byte window.
bool DecodeInstruction(const void* code, std::size_t available,
                       ZydisDecodedInstruction& instruction, Operands& operands);
bool IsStackPointerRegister(ZydisRegister reg);
bool IsControlFlowTerminator(const ZydisDecodedInstruction& instruction);
std::uintptr_t GetRelativeTarget(std::uintptr_t address,
                                const ZydisDecodedInstruction& instruction,
                                const Operands& operands);
} // namespace Core::CpuPatchScanner
