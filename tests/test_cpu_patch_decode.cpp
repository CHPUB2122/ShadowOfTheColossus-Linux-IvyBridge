// SPDX-License-Identifier: GPL-2.0-or-later
// Pure scanner helpers: decode bytes and compute branch targets; never execute guest code.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <optional>
#include <vector>
#include "cpu_patch_decode.h"
#ifndef _WIN32
#include <sys/mman.h>
#include <unistd.h>
#endif

using namespace Core::CpuPatchScanner;
struct Fixture {
    std::vector<std::uint8_t> bytes;
    ZydisMnemonic mnemonic;
    bool terminal = false;
    std::optional<std::int64_t> relative{};
};

int main() {
    const std::vector<Fixture> fixtures{
        {{0x90}, ZYDIS_MNEMONIC_NOP},
        {{0x48, 0xc7, 0xc0, 0, 0, 0, 0}, ZYDIS_MNEMONIC_MOV},
        {{0xc3}, ZYDIS_MNEMONIC_RET, true},
        {{0xc2, 0x10, 0}, ZYDIS_MNEMONIC_RET, true},
        {{0xcc}, ZYDIS_MNEMONIC_INT3, true},
        {{0x0f, 0x0b}, ZYDIS_MNEMONIC_UD2, true},
        {{0x0f, 0x07}, ZYDIS_MNEMONIC_SYSRET, true},
        {{0xeb, 0x7f}, ZYDIS_MNEMONIC_JMP, true, 127},
        {{0xeb, 0x80}, ZYDIS_MNEMONIC_JMP, true, -128},
        {{0xeb, 0xfe}, ZYDIS_MNEMONIC_JMP, true, -2},
        {{0xe9, 0xff, 0xff, 0xff, 0x7f}, ZYDIS_MNEMONIC_JMP, true, 0x7fffffff},
        {{0xe9, 0, 0, 0, 0x80}, ZYDIS_MNEMONIC_JMP, true, -0x80000000ll},
        {{0xe8, 0xfc, 0xff, 0xff, 0xff}, ZYDIS_MNEMONIC_CALL, false, -4},
        {{0x75, 0xf0}, ZYDIS_MNEMONIC_JNZ, false, -16},
        {{0x0f, 0x85, 0x80, 0, 0, 0}, ZYDIS_MNEMONIC_JNZ, false, 128},
        {{0xff, 0x20}, ZYDIS_MNEMONIC_JMP, true},
        {{0xff, 0x10}, ZYDIS_MNEMONIC_CALL},
        {{0x48, 0x8d, 0x05, 8, 0, 0, 0}, ZYDIS_MNEMONIC_LEA},
        {{0xc4, 0xe2, 0xe8, 0xf7, 0xc3}, ZYDIS_MNEMONIC_BEXTR},
        {{0x66, 0x0f, 0x79, 0xc1}, ZYDIS_MNEMONIC_EXTRQ},
        {{0xf2, 0x0f, 0x79, 0xc1}, ZYDIS_MNEMONIC_INSERTQ},
        {{0x48, 0x0f, 0x38, 0xf0, 0x06}, ZYDIS_MNEMONIC_MOVBE},
        {{0xf3, 0x48, 0x0f, 0xbd, 0xc1}, ZYDIS_MNEMONIC_LZCNT},
        {{0xf3, 0x48, 0x0f, 0xbc, 0xc1}, ZYDIS_MNEMONIC_TZCNT},
    };
    constexpr std::uintptr_t address = 0x100000000ull;
    ZydisDecodedInstruction instruction{};
    Operands operands{};
    std::size_t truncated = 0;
    for (const auto& f : fixtures) {
        assert(DecodeInstruction(f.bytes.data(), f.bytes.size(), instruction, operands));
        assert(instruction.mnemonic == f.mnemonic && instruction.length == f.bytes.size());
        assert(IsControlFlowTerminator(instruction) == f.terminal);
        const auto target = f.relative ? address + f.bytes.size() + *f.relative : 0;
        assert(GetRelativeTarget(address, instruction, operands) == target);
        if (f.mnemonic == ZYDIS_MNEMONIC_LEA) {
            assert(operands[1].type == ZYDIS_OPERAND_TYPE_MEMORY &&
                   operands[1].mem.base == ZYDIS_REGISTER_RIP);
        }
        for (std::size_t length = 0; length < f.bytes.size(); ++length) {
            assert(!DecodeInstruction(f.bytes.data(), length, instruction, operands));
            assert(instruction.length == 0);
            ++truncated;
        }
    }
    for (auto reg : {ZYDIS_REGISTER_SPL, ZYDIS_REGISTER_SP, ZYDIS_REGISTER_ESP, ZYDIS_REGISTER_RSP})
        assert(IsStackPointerRegister(reg));
    for (auto reg : {ZYDIS_REGISTER_NONE, ZYDIS_REGISTER_RAX, ZYDIS_REGISTER_AH,
                    ZYDIS_REGISTER_RBP, ZYDIS_REGISTER_R12, ZYDIS_REGISTER_XMM0})
        assert(!IsStackPointerRegister(reg));
    assert(!DecodeInstruction(nullptr, 15, instruction, operands) && instruction.length == 0);
    const std::vector<std::uint8_t> invalid(16, 0x66);
    assert(!DecodeInstruction(invalid.data(), invalid.size(), instruction, operands));
    assert(instruction.length == 0);

#ifndef _WIN32
    const auto page = std::size_t(sysconf(_SC_PAGESIZE));
    void* mapping = mmap(nullptr, page * 2, PROT_READ | PROT_WRITE,
                         MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(mapping != MAP_FAILED);
    auto* end = static_cast<std::uint8_t*>(mapping) + page;
    assert(mprotect(end, page, PROT_NONE) == 0);
    for (const auto& f : fixtures) {
        auto* code = end - f.bytes.size();
        std::memcpy(code, f.bytes.data(), f.bytes.size());
        assert(DecodeInstruction(code, f.bytes.size(), instruction, operands));
        for (std::size_t length = 0; length < f.bytes.size(); ++length) {
            code = end - length;
            std::memcpy(code, f.bytes.data(), length);
            assert(!DecodeInstruction(code, length, instruction, operands));
            assert(instruction.length == 0);
        }
    }
    assert(munmap(mapping, page * 2) == 0);
#endif
    std::printf("PASS: %zu encodings, %zu truncated windows, branch targets and RSP aliases",
                fixtures.size(), truncated);
#ifndef _WIN32
    std::printf("; guarded page boundaries");
#endif
    std::puts("; guest code never executed");
}
