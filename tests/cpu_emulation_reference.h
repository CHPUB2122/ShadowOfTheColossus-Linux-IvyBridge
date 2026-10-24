// SPDX-License-Identifier: GPL-2.0-or-later
// Independent scalar instruction semantics. No intrinsics or generated guest instructions.
#pragma once

#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <span>

namespace CpuTest {
using Word = std::uint64_t;
constexpr Word CF = 1, PF = 4, AF = 0x10, ZF = 0x40, SF = 0x80, OF = 0x800;
constexpr Word Arithmetic = CF | PF | AF | ZF | SF | OF;
constexpr int Rsp = 4, Rsi = 6, Rdi = 7;

struct State {
    std::array<Word, 16> gpr{};
    std::array<std::array<Word, 4>, 16> ymm{};
    Word flags{}, entry_rsp{};
    std::array<std::uint8_t, 96> memory{};
    std::array<std::uint8_t, 64> stack{};
    std::array<std::uint8_t, 128> red_zone{};
    std::array<std::uint8_t, 32> rip_memory{};
};

enum class Op { Tzcnt, Lzcnt, Andn, Bextr, Blsi, Blsmsk, Blsr, Movbe,
                Extrq, Insertq, Movntss, Movntsd };
enum class Location { Register, Memory, Indexed, Stack, Rip };
struct Operand {
    Location location = Location::Register;
    int reg = 0, offset = 0;
};
inline Operand Reg(int reg) { return {Location::Register, reg}; }
inline Operand Mem(int offset = 0) { return {Location::Memory, 0, offset}; }
inline Operand Indexed() { return {Location::Indexed}; } // [rsi + rdi*4 - 7], rdi=2
inline Operand Stack(int offset) { return {Location::Stack, 0, offset}; }
inline Operand Rip(int offset = 0) { return {Location::Rip, 0, offset}; }

inline Word Mask(unsigned bits) {
    return bits == 64 ? ~Word{0} : (Word{1} << bits) - 1;
}

inline std::span<std::uint8_t> Memory(State& s, Operand op) {
    std::span<std::uint8_t> bytes;
    int offset = op.offset;
    switch (op.location) {
    case Location::Memory: bytes = s.memory; offset += 32; break;
    case Location::Indexed: bytes = s.memory; offset += 32 + int(s.gpr[Rdi]) * 4 - 7; break;
    case Location::Stack:
        bytes = op.offset < 0 ? std::span<std::uint8_t>{s.red_zone} : std::span<std::uint8_t>{s.stack};
        if (op.offset < 0) offset += 128;
        break;
    case Location::Rip: bytes = s.rip_memory; offset += 16; break;
    default: assert(false);
    }
    assert(offset >= 0 && unsigned(offset) < bytes.size());
    return bytes.subspan(offset);
}

inline Word Read(State& s, Operand op, unsigned bits) {
    if (op.location == Location::Register) return s.gpr[op.reg] & Mask(bits);
    auto bytes = Memory(s, op);
    assert(bytes.size() >= bits / 8);
    Word value = 0;
    // Explicit little endian loads, including unaligned words, without host instruction oracles.
    for (unsigned i = 0; i < bits / 8; ++i) value |= Word{bytes[i]} << (i * 8);
    return value;
}

inline void Write(State& s, Operand op, unsigned bits, Word value) {
    value &= Mask(bits);
    if (op.location == Location::Register) {
        s.gpr[op.reg] = bits == 16 ? (s.gpr[op.reg] & ~Mask(16)) | value : value;
        return; // 32-bit writes zero-extend; 16-bit writes preserve the upper bits.
    }
    auto bytes = Memory(s, op);
    assert(bytes.size() >= bits / 8);
    for (unsigned i = 0; i < bits / 8; ++i) bytes[i] = value >> (i * 8);
}

inline Word DefinedFlags(Op op) {
    switch (op) {
    case Op::Tzcnt: case Op::Lzcnt: return CF | ZF;
    case Op::Bextr: return CF | ZF | OF;
    case Op::Andn: case Op::Blsi: case Op::Blsmsk: case Op::Blsr: return CF | ZF | SF | OF;
    default: return Arithmetic;
    }
}

// A description of the original encoding, shared only for operand selection, not semantics.
struct Instruction {
    Op op{};
    unsigned bits = 64;
    Operand dst{}, src{}, control{};
    bool immediate = false, exhaustive = false;
    std::uint8_t length = 0, index = 0;
};

inline void Reference(const Instruction& t, State& s) {
    const auto op = t.op;
    if (op == Op::Extrq || op == Op::Insertq) {
        const Word source = s.ymm[t.src.reg][0];
        const Word destination = s.ymm[t.dst.reg][0];
        const Word control = op == Op::Extrq ? source : s.ymm[t.src.reg][1];
        const unsigned length_field = t.immediate ? t.length & 63 : control & 63;
        const unsigned index = t.immediate ? t.index & 63 : (control >> 8) & 63;
        const unsigned length = length_field ? length_field : 64;
        assert(index + length <= 64); // the other combinations have architecturally undefined results
        if (op == Op::Extrq) {
            s.ymm[t.dst.reg][0] = (destination >> index) & Mask(length);
        } else {
            const Word mask = Mask(length) << index;
            s.ymm[t.dst.reg][0] = (destination & ~mask) | ((source << index) & mask);
        }
        // Destination [127:64] is undefined. The legacy encoding preserves YMM [255:128].
        return;
    }
    if (op == Op::Movntss || op == Op::Movntsd) {
        Write(s, t.dst, t.bits, s.ymm[t.src.reg][0]);
        return;
    }
    const Word source = Read(s, t.src, t.bits);
    Word result = 0, flags = 0;
    switch (op) {
    case Op::Tzcnt:
    case Op::Lzcnt:
        for (; result < t.bits; ++result) {
            const unsigned bit = op == Op::Tzcnt ? unsigned(result) : t.bits - 1 - unsigned(result);
            if ((source >> bit) & 1) break;
        }
        flags = (source == 0 ? CF : 0) | (result == 0 ? ZF : 0);
        break;
    case Op::Andn:
        result = ~source & Read(s, t.control, t.bits);
        break;
    case Op::Bextr: {
        const Word control = Read(s, t.control, t.bits);
        const unsigned start = control & 255, length = (control >> 8) & 255;
        // Copy individual bits: independent of the trampoline's shifts/mask/RCX implementation.
        for (unsigned i = 0; i < length && start + i < t.bits; ++i)
            result |= ((source >> (start + i)) & 1) << i;
        break;
    }
    case Op::Blsi:
        for (unsigned i = 0; i < t.bits; ++i) {
            if ((source >> i) & 1) { result = Word{1} << i; break; }
        }
        flags = source != 0 ? CF : 0;
        break;
    case Op::Blsmsk:
        result = Mask(t.bits);
        for (unsigned i = 0; i < t.bits; ++i) {
            if ((source >> i) & 1) { result = Mask(i + 1); break; }
        }
        flags = source == 0 ? CF : 0;
        break;
    case Op::Blsr:
        result = source;
        for (unsigned i = 0; i < t.bits; ++i) {
            if ((source >> i) & 1) { result &= ~(Word{1} << i); break; }
        }
        flags = source == 0 ? CF : 0;
        break;
    case Op::Movbe:
        for (unsigned i = 0; i < t.bits / 8; ++i)
            result |= ((source >> (i * 8)) & 255) << (t.bits - 8 - i * 8);
        Write(s, t.dst, t.bits, result);
        return; // all flags preserved
    default: assert(false);
    }
    result &= Mask(t.bits);
    if (op != Op::Tzcnt && op != Op::Lzcnt) {
        if (result == 0) flags |= ZF;
        if (result & (Word{1} << (t.bits - 1))) flags |= SF;
    }
    const Word defined = DefinedFlags(op);
    s.flags = (s.flags & ~defined) | (flags & defined);
    Write(s, t.dst, t.bits, result);
}
} // namespace CpuTest
