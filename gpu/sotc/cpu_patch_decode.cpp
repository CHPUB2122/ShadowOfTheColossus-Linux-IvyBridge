// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: extracted from cpu_patches.cpp's Windows scanner; no loader activation here.
#include <string>
#include "cpu_patch_decode.h"
#include "common/decoder.h"

namespace Core::CpuPatchScanner {
bool DecodeInstruction(const void* code, std::size_t available,
                       ZydisDecodedInstruction& instruction, Operands& operands) {
    instruction = {};
    operands = {};
    if (!code || !available) return false;
    const auto status = Common::Decoder::Instance()->decodeInstruction(
        instruction, operands.data(), const_cast<void*>(code), available);
    if (!ZYAN_SUCCESS(status)) {
        instruction.length = 0;
        return false;
    }
    return true;
}

bool IsStackPointerRegister(ZydisRegister reg) {
    return reg != ZYDIS_REGISTER_NONE &&
           ZydisRegisterGetLargestEnclosing(ZYDIS_MACHINE_MODE_LONG_64, reg) == ZYDIS_REGISTER_RSP;
}

bool IsControlFlowTerminator(const ZydisDecodedInstruction& instruction) {
    return instruction.meta.category == ZYDIS_CATEGORY_UNCOND_BR ||
           instruction.meta.category == ZYDIS_CATEGORY_RET ||
           instruction.meta.category == ZYDIS_CATEGORY_INTERRUPT ||
           instruction.meta.category == ZYDIS_CATEGORY_SYSRET ||
           instruction.mnemonic == ZYDIS_MNEMONIC_UD2;
}

std::uintptr_t GetRelativeTarget(std::uintptr_t address,
                                const ZydisDecodedInstruction& instruction,
                                const Operands& operands) {
    for (ZyanU8 index = 0; index < instruction.operand_count_visible; ++index) {
        const auto& operand = operands[index];
        if (operand.type != ZYDIS_OPERAND_TYPE_IMMEDIATE || !operand.imm.is_relative) continue;
        ZyanU64 target{};
        if (ZYAN_SUCCESS(ZydisCalcAbsoluteAddress(&instruction, &operand, address, &target)))
            return target;
    }
    return 0;
}
} // namespace Core::CpuPatchScanner
