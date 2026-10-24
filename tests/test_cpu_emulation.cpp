// SPDX-License-Identifier: GPL-2.0-or-later
// Run only the existing gpu/sotc emulation, compared with scalar software references.
// Original BMI1/MOVBE/LZCNT/SSE4a bytes are decoded as data, never executed.
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <functional>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
#include <Zydis/Zydis.h>
#include <xbyak/xbyak.h>
#include "cpu_patches.h"
#include "cpu_emulation_reference.h"
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#include <unistd.h>
#endif

using namespace Xbyak::util;
using namespace CpuTest;

namespace {
using Emit = std::function<void(Xbyak::CodeGenerator&)>;

// Low guest addresses are a contract of GuestMemory's RIP-relative relocation.
// The final page is inaccessible: boundary loads/stores must use exactly their operand width.
struct LowMemory {
    std::uint8_t* base{};
    std::size_t page = 4096;
    LowMemory() {
#ifdef _WIN32
        for (Word address = 0x10000000; !base && address < 0x70000000; address += 0x10000)
            base = static_cast<std::uint8_t*>(VirtualAlloc(reinterpret_cast<void*>(address),
                page * 3, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
        DWORD previous;
        if (!base || !VirtualProtect(base + page * 2, page, PAGE_NOACCESS, &previous))
            throw std::runtime_error("low guest allocation failed");
#else
        page = std::size_t(sysconf(_SC_PAGESIZE));
        void* mapped = mmap(nullptr, page * 3, PROT_READ | PROT_WRITE,
                            MAP_PRIVATE | MAP_ANONYMOUS | MAP_32BIT, -1, 0);
        if (mapped == MAP_FAILED) throw std::runtime_error("MAP_32BIT failed");
        base = static_cast<std::uint8_t*>(mapped);
        if (mprotect(base + page * 2, page, PROT_NONE)) throw std::runtime_error("mprotect failed");
#endif
        if (reinterpret_cast<Word>(base + page * 3) >= (Word{1} << 31))
            throw std::runtime_error("guest fixture above 2 GiB");
    }
    std::uint8_t* data() const { return base + page * 2 - 32; }
    ~LowMemory() {
#ifdef _WIN32
        if (base) VirtualFree(base, 0, MEM_RELEASE);
#else
        if (base) munmap(base, page * 3);
#endif
    }
};

// void run(State*), System V on Linux, Windows x64 on Windows.
// No GPR is reserved while running the trampoline. Host storage is above the test stack.
// PUSHFQ for capture runs above that stack too, preserving all 128 guest red-zone bytes.
struct Runner : Xbyak::CodeGenerator {
    explicit Runner(const Emit& body) : Xbyak::CodeGenerator(8192) {
        const std::array<int, 8> saved{3, 5, 6, 7, 12, 13, 14, 15};
        for (int reg : saved) push(Xbyak::Reg64(reg));
#ifdef _WIN32
        mov(r15, rcx);
#else
        mov(r15, rdi);
#endif
        sub(rsp, 1024);
        lea(rsp, ptr[rsp + 256]);
        mov(ptr[rsp + 256], r15);
        mov(ptr[r15 + offsetof(State, entry_rsp)], rsp);
#ifdef _WIN32
        for (int i = 6; i < 16; ++i) movdqu(ptr[rsp + 320 + (i - 6) * 16], Xbyak::Xmm(i));
#endif
        push(qword[r15 + offsetof(State, flags)]);
        popfq();
        for (int i = 0; i < 64; i += 8) {
            mov(rax, ptr[r15 + offsetof(State, stack) + i]);
            mov(ptr[rsp + i], rax);
        }
        for (int i = 0; i < 128; i += 8) {
            mov(rax, ptr[r15 + offsetof(State, red_zone) + i]);
            mov(ptr[rsp - 128 + i], rax);
        }
        for (int i = 0; i < 16; ++i)
            vmovdqu(Xbyak::Ymm(i), ptr[r15 + offsetof(State, ymm) + i * 32]);
        for (int i = 0; i < 15; ++i)
            if (i != Rsp) mov(Xbyak::Reg64(i), ptr[r15 + offsetof(State, gpr) + i * 8]);
        mov(r15, ptr[r15 + offsetof(State, gpr) + 15 * 8]);
        body(*this);
        lea(rsp, ptr[rsp + 192]);
        pushfq();
        push(rax);
        mov(rax, ptr[rsp + 80]); // original RSP + 256: State*
        for (int i = 1; i < 16; ++i)
            if (i != Rsp) mov(ptr[rax + offsetof(State, gpr) + i * 8], Xbyak::Reg64(i));
        lea(rdx, ptr[rsp - 176]);
        mov(ptr[rax + offsetof(State, gpr) + Rsp * 8], rdx);
        mov(rdx, ptr[rsp]);
        mov(ptr[rax + offsetof(State, gpr)], rdx);
        mov(rdx, ptr[rsp + 8]);
        mov(ptr[rax + offsetof(State, flags)], rdx);
        for (int i = 0; i < 16; ++i)
            vmovdqu(ptr[rax + offsetof(State, ymm) + i * 32], Xbyak::Ymm(i));
        lea(rsp, ptr[rsp - 176]);
        for (int i = 0; i < 64; i += 8) {
            mov(rdx, ptr[rsp + i]);
            mov(ptr[rax + offsetof(State, stack) + i], rdx);
        }
        for (int i = 0; i < 128; i += 8) {
            mov(rdx, ptr[rsp - 128 + i]);
            mov(ptr[rax + offsetof(State, red_zone) + i], rdx);
        }
#ifdef _WIN32
        for (int i = 6; i < 16; ++i) movdqu(Xbyak::Xmm(i), ptr[rsp + 320 + (i - 6) * 16]);
#endif
        lea(rsp, ptr[rsp + 768]);
        for (auto i = saved.rbegin(); i != saved.rend(); ++i) pop(Xbyak::Reg64(*i));
        ret();
        ready();
    }
};

Xbyak::Reg Gpr(int index, unsigned bits) { return Xbyak::Reg(index, Xbyak::Operand::REG, bits); }
Xbyak::Address Address(Operand operand, unsigned bits, LowMemory& low) {
    Xbyak::RegExp expression;
    switch (operand.location) {
    case Location::Memory: expression = rsi + operand.offset; break;
    case Location::Indexed: expression = rsi + rdi * 4 - 7; break;
    case Location::Stack: expression = rsp + operand.offset; break;
    case Location::Rip:
        return Xbyak::AddressFrame(bits)[rip + static_cast<void*>(low.data() + 16 + operand.offset)];
    default: throw std::runtime_error("not a memory operand");
    }
    return Xbyak::AddressFrame(bits)[expression];
}

void Encode(const Instruction& t, Xbyak::CodeGenerator& c, LowMemory& low) {
    const auto reg = Gpr(t.dst.reg, t.bits);
    const auto source = Gpr(t.src.reg, t.bits);
    const auto binary = [&](const Xbyak::Operand& other) {
        const auto first = Xbyak::Reg32e(t.dst.reg, t.bits);
        const auto control = Xbyak::Reg32e(t.control.reg, t.bits);
        if (t.op == Op::Andn) c.andn(first, Xbyak::Reg32e(t.src.reg, t.bits), other);
        else c.bextr(first, other, control);
    };
    if (t.op == Op::Extrq || t.op == Op::Insertq) {
        // Xbyak has no SSE4a mnemonics. These are the AMD legacy encodings; decode only.
        const bool extrq_immediate = t.op == Op::Extrq && t.immediate;
        const int reg_field = extrq_immediate ? 0 : t.dst.reg;
        const int rm_field = extrq_immediate ? t.dst.reg : t.src.reg;
        c.db(t.op == Op::Extrq ? 0x66 : 0xf2);
        const int rex = 0x40 | ((reg_field >> 3) << 2) | (rm_field >> 3);
        if (rex != 0x40) c.db(rex);
        c.db(0x0f);
        c.db(t.immediate ? 0x78 : 0x79);
        c.db(0xc0 | ((reg_field & 7) << 3) | (rm_field & 7));
        if (t.immediate) { c.db(t.length); c.db(t.index); }
    } else if (t.op == Op::Movntss || t.op == Op::Movntsd) {
        if (t.op == Op::Movntss) c.movss(Address(t.dst, 32, low), Xbyak::Xmm(t.src.reg));
        else c.movsd(Address(t.dst, 64, low), Xbyak::Xmm(t.src.reg));
        auto* bytes = const_cast<std::uint8_t*>(c.getCode());
        for (std::size_t i = 0; i + 1 < c.getSize(); ++i)
            if (bytes[i] == 0x0f && bytes[i + 1] == 0x11) { bytes[i + 1] = 0x2b; return; }
        throw std::runtime_error("MOVNT fixture encoding failed");
    } else if (t.op == Op::Movbe) {
        if (t.dst.location == Location::Register) c.movbe(reg, Address(t.src, t.bits, low));
        else c.movbe(Address(t.dst, t.bits, low), source);
    } else if (t.op == Op::Andn) {
        if (t.control.location == Location::Register) binary(Gpr(t.control.reg, t.bits));
        else binary(Address(t.control, t.bits, low));
    } else if (t.op == Op::Bextr) {
        if (t.src.location == Location::Register) binary(source);
        else binary(Address(t.src, t.bits, low));
    } else {
        const auto unary = [&](const Xbyak::Operand& other) {
            switch (t.op) {
            case Op::Tzcnt: c.tzcnt(reg, other); break;
            case Op::Lzcnt: c.lzcnt(reg, other); break;
            case Op::Blsi: c.blsi(Xbyak::Reg32e(t.dst.reg, t.bits), other); break;
            case Op::Blsmsk: c.blsmsk(Xbyak::Reg32e(t.dst.reg, t.bits), other); break;
            case Op::Blsr: c.blsr(Xbyak::Reg32e(t.dst.reg, t.bits), other); break;
            default: throw std::runtime_error("bad unary instruction");
            }
        };
        if (t.src.location == Location::Register) unary(source);
        else unary(Address(t.src, t.bits, low));
    }
}

constexpr const char* Names[] = {"tzcnt", "lzcnt", "andn", "bextr", "blsi", "blsmsk",
                                "blsr", "movbe", "extrq", "insertq", "movntss", "movntsd"};
const char* Name(Op op) { return Names[unsigned(op)]; }

void AuditGeneratedCode(const Runner& runner) {
    ZydisDecoder decoder;
    ZydisDecoderInit(&decoder, ZYDIS_MACHINE_MODE_LONG_64, ZYDIS_STACK_WIDTH_64);
    for (std::size_t offset = 0; offset < runner.getSize();) {
        ZydisDecodedInstruction instruction;
        if (!ZYAN_SUCCESS(ZydisDecoderDecodeInstruction(&decoder, nullptr, runner.getCode() + offset,
                                                        runner.getSize() - offset, &instruction)))
            throw std::runtime_error("cannot decode generated runner");
        switch (instruction.meta.isa_set) {
        case ZYDIS_ISA_SET_BMI1: case ZYDIS_ISA_SET_BMI2: case ZYDIS_ISA_SET_AVX2:
        case ZYDIS_ISA_SET_LZCNT: case ZYDIS_ISA_SET_MOVBE: case ZYDIS_ISA_SET_SSE4A:
            throw std::runtime_error("unsupported native instruction in generated runner");
        default: break;
        }
        offset += instruction.length;
    }
}

std::vector<Instruction> Cases() {
    std::vector<Instruction> tests;
    const std::array<int, 15> regs{0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15};
    const auto memory = [](unsigned bits) {
        return std::vector<Operand>{Mem(), Mem(3), Mem(-7), Indexed(), Stack(8),
            Stack(-8), Stack(-128), Rip(), Rip(16 - int(bits / 8))};
    };
    for (Op op : {Op::Tzcnt, Op::Lzcnt, Op::Blsi, Op::Blsmsk, Op::Blsr}) {
        for (unsigned bits : {16u, 32u, 64u}) {
            if (bits == 16 && op != Op::Tzcnt && op != Op::Lzcnt) continue;
            for (std::size_t i = 0; i < regs.size(); ++i) {
                const int dst = regs[i];
                tests.push_back({op, bits, Reg(dst), Reg(dst)});
                tests.push_back({op, bits, Reg(dst), Reg(regs[(i + 1) % regs.size()])});
            }
            for (auto mem : memory(bits)) {
                tests.push_back({op, bits, Reg(0), mem});
                if (mem.location == Location::Memory) tests.push_back({op, bits, Reg(Rsi), mem});
                if (mem.location == Location::Indexed) tests.push_back({op, bits, Reg(Rdi), mem});
            }
        }
    }
    for (unsigned bits : {32u, 64u}) {
        for (Op op : {Op::Andn, Op::Bextr}) {
            for (std::size_t i = 0; i < regs.size(); ++i) {
                const int a = regs[i], b = regs[(i + 1) % regs.size()], d = regs[(i + 2) % regs.size()];
                tests.push_back({op, bits, Reg(a), Reg(b), Reg(d)});
                tests.push_back({op, bits, Reg(a), Reg(a), Reg(b)});
                tests.push_back({op, bits, Reg(a), Reg(b), Reg(a)});
                tests.push_back({op, bits, Reg(a), Reg(a), Reg(a)});
            }
            for (auto mem : memory(bits)) {
                if (op == Op::Andn) {
                    tests.push_back({op, bits, Reg(0), Reg(3), mem});
                    tests.push_back({op, bits, Reg(mem.location == Location::Indexed ? Rdi : Rsi), Reg(3), mem});
                } else {
                    tests.push_back({op, bits, Reg(1), mem, Reg(1)});
                    tests.push_back({op, bits, Reg(2), mem, Reg(2)});
                }
            }
        }
        // Exhaust all 65536 control values on distinct, source/control-overlap, and stack forms.
        tests.push_back({Op::Bextr, bits, Reg(0), Reg(3), Reg(2), false, true});
        tests.push_back({Op::Bextr, bits, Reg(1), Reg(1), Reg(1), false, true});
        tests.push_back({Op::Bextr, bits, Reg(1), Stack(-8), Reg(1), false, true});
    }
    for (unsigned bits : {16u, 32u, 64u}) {
        for (auto mem : memory(bits)) {
            tests.push_back({Op::Movbe, bits, Reg(0), mem});
            tests.push_back({Op::Movbe, bits, mem, Reg(3)});
        }
        for (int reg : regs) {
            tests.push_back({Op::Movbe, bits, Reg(reg), Mem()});
            tests.push_back({Op::Movbe, bits, Mem(), Reg(reg)});
        }
    }
    for (Op op : {Op::Extrq, Op::Insertq}) {
        for (const auto& [dst, src] : {std::pair{0, 1}, {1, 1}, {8, 15}, {15, 15}, {7, 8}, {8, 7}})
            tests.push_back({op, 64, Reg(dst), Reg(src)});
        for (unsigned length = 0; length < 64; ++length) {
            const unsigned real_length = length ? length : 64;
            for (unsigned index : {0u, 64 - real_length}) {
                // High immediate bits must be ignored; cover both ordinary and extended XMMs.
                tests.push_back({op, 64, Reg(int(length % 16)), Reg(int((length + 1) % 16)), {},
                                  true, false, std::uint8_t(length | 0x80), std::uint8_t(index | 0xc0)});
            }
        }
        tests.push_back({op, 64, Reg(15), Reg(15), {}, true, false, 0, 0});
    }
    for (auto mem : memory(64)) {
        if (mem.location == Location::Rip) continue; // MOVNT is rewritten in place, not relocated
        for (int src : {1, 15}) {
            tests.push_back({Op::Movntss, 32, mem, Reg(src)});
            tests.push_back({Op::Movntsd, 64, mem, Reg(src)});
        }
    }
    return tests;
}

State RandomState(std::mt19937_64& random) {
    State state;
    for (auto& value : state.gpr) value = random();
    for (auto& vector : state.ymm) for (auto& value : vector) value = random();
    const auto fill = [&](auto& bytes) {
        for (std::size_t offset = 0; offset < bytes.size(); offset += 8) {
            const Word value = random();
            std::memcpy(bytes.data() + offset, &value, 8);
        }
    };
    fill(state.memory); fill(state.stack); fill(state.red_zone); fill(state.rip_memory);
    state.flags = 0x202 | (random() & Arithmetic);
    return state;
}

void Controls(const Instruction& t, State& s, unsigned length, unsigned index) {
    if (t.op == Op::Bextr) {
        Word control = Read(s, t.control, t.bits) & ~Word{0xffff};
        Write(s, t.control, t.bits, control | (length << 8) | index);
    } else if (!t.immediate && (t.op == Op::Extrq || t.op == Op::Insertq)) {
        auto& control = s.ymm[t.src.reg][t.op == Op::Extrq ? 0 : 1];
        control = (control & ~Word{0x3f3f}) | ((length & 63) | (index << 8));
    }
}

bool Same(const Instruction& t, const State& a, const State& b, bool verbose) {
    for (int i = 0; i < 16; ++i) {
        if (a.gpr[i] != b.gpr[i]) {
            if (verbose) std::printf(" GPR[%d]: expected=%016llx actual=%016llx\n", i,
                (unsigned long long)a.gpr[i], (unsigned long long)b.gpr[i]);
            return false;
        }
        for (int lane = 0; lane < 4; ++lane) {
            if ((t.op == Op::Extrq || t.op == Op::Insertq) && i == t.dst.reg && lane == 1) continue;
            if (a.ymm[i][lane] != b.ymm[i][lane]) {
                if (verbose) std::printf(" YMM[%d] qword[%d]: expected=%016llx actual=%016llx\n", i, lane,
                    (unsigned long long)a.ymm[i][lane], (unsigned long long)b.ymm[i][lane]);
                return false;
            }
        }
    }
    const Word flags = DefinedFlags(t.op);
    if ((a.flags & flags) != (b.flags & flags)) {
        if (verbose) std::printf(" flags(mask=%llx): expected=%llx actual=%llx\n",
            (unsigned long long)flags, (unsigned long long)(a.flags & flags), (unsigned long long)(b.flags & flags));
        return false;
    }
    const auto bytes = [&](const auto& expected, const auto& actual, const char* name) {
        if (expected == actual) return true;
        if (verbose) {
            const auto difference = std::mismatch(expected.begin(), expected.end(), actual.begin());
            const auto offset = difference.first - expected.begin();
            std::printf(" %s[%td]: expected=%02x actual=%02x\n", name, offset,
                        unsigned(*difference.first), unsigned(*difference.second));
        }
        return false;
    };
    return bytes(a.memory, b.memory, "memory") && bytes(a.stack, b.stack, "stack") &&
           bytes(a.red_zone, b.red_zone, "red zone") && bytes(a.rip_memory, b.rip_memory, "RIP memory");
}

void ReferenceAnchors() {
    // Fixed architectural answers check the oracle independently of the generated code.
    State state;
    state.flags = Arithmetic | 0x202;
    state.gpr[0] = 0x123456789abcffff;
    Reference({Op::Tzcnt, 16, Reg(0), Reg(1)}, state);
    assert(state.gpr[0] == 0x123456789abc0010 && (state.flags & (CF | ZF)) == CF);
    state.gpr[1] = 0x80000000;
    Reference({Op::Lzcnt, 32, Reg(0), Reg(1)}, state);
    assert(state.gpr[0] == 0 && (state.flags & (CF | ZF)) == ZF);
    state.gpr[1] = 0;
    Reference({Op::Blsmsk, 32, Reg(0), Reg(1)}, state);
    assert(state.gpr[0] == 0xffffffff && (state.flags & DefinedFlags(Op::Blsmsk)) == (CF | SF));
    state.gpr[1] = 0x8000000000000000;
    Reference({Op::Blsi, 64, Reg(0), Reg(1)}, state);
    assert(state.gpr[0] == state.gpr[1] && (state.flags & DefinedFlags(Op::Blsi)) == (CF | SF));
    Reference({Op::Blsr, 64, Reg(0), Reg(1)}, state);
    assert(state.gpr[0] == 0 && (state.flags & DefinedFlags(Op::Blsr)) == ZF);
    state.gpr[2] = 0xff00;
    Reference({Op::Bextr, 64, Reg(0), Reg(1), Reg(2)}, state);
    assert(state.gpr[0] == state.gpr[1] && (state.flags & DefinedFlags(Op::Bextr)) == 0);
    Reference({Op::Andn, 32, Reg(0), Reg(1), Reg(1)}, state);
    assert(state.gpr[0] == 0 && (state.flags & DefinedFlags(Op::Andn)) == ZF);
    Write(state, Mem(), 64, 0x0102030405060708);
    const Word flags = state.flags;
    Reference({Op::Movbe, 64, Reg(0), Mem()}, state);
    assert(state.gpr[0] == 0x0807060504030201 && state.flags == flags);
    state.ymm[0][0] = 0xfedcba9876543210;
    state.ymm[1][0] = 0x0808;
    Reference({Op::Extrq, 64, Reg(0), Reg(1)}, state);
    assert(state.ymm[0][0] == 0x32 && state.flags == flags);
    state.ymm[0][0] = 0x1122334455667788;
    state.ymm[1][0] = 0xaa;
    state.ymm[1][1] = 0x1008;
    Reference({Op::Insertq, 64, Reg(0), Reg(1)}, state);
    assert(state.ymm[0][0] == 0x1122334455aa7788 && state.flags == flags);
}
#ifdef __linux__
void ClockReplacement() {
    // Exercise the real RDTSC scanner/trampoline against a hostile, valid
    // System V callee. It destroys every caller-saved register and YMM lane.
    constexpr Word timestamp = 0xfedcba9876543210;
    Xbyak::CodeGenerator clock(4096), trampoline(16384);
    for (int reg : {1, 2, 6, 7, 8, 9, 10, 11}) clock.mov(Xbyak::Reg64(reg), 0xdeadbeef);
    for (int i = 0; i < 16; ++i) clock.vxorps(Xbyak::Ymm(i), Xbyak::Ymm(i), Xbyak::Ymm(i));
    clock.xor_(eax, eax); clock.stc(); clock.mov(rax, timestamp); clock.ret(); clock.ready();
    uintptr_t site = 0;
    Runner runner([&](auto& c) {
        site = reinterpret_cast<uintptr_t>(c.getCurr());
        c.rdtsc(); c.nop(3);
    });
    AuditGeneratedCode(runner);
    Core::RegisterPatchModule(runner.getCode<void*>(), runner.getSize(),
                              trampoline.getCode<void*>(), 16384);
    const std::array<uintptr_t, 2> starts{site, site + 5};
    u64 unpatched = 0;
    assert(Core::PatchRdtscInstructions(reinterpret_cast<uintptr_t>(runner.getCode()),
        runner.getSize(), starts, clock.getCode<void*>(), &unpatched) == 1);
    assert(unpatched == 0 && *reinterpret_cast<unsigned char*>(site) == 0xe9);
    std::mt19937_64 random(0x745343);
    for (int i = 0; i < 512; ++i) {
        State actual = RandomState(random), expected = actual;
        runner.getCode<void (*)(State*)>()(&actual);
        expected.gpr[0] = Word{std::uint32_t(timestamp)};
        expected.gpr[2] = timestamp >> 32;
        expected.gpr[Rsp] = actual.entry_rsp;
        assert(Same({Op::Movbe, 64, Reg(0), Reg(1)}, expected, actual, true));
        assert((actual.flags & Arithmetic) == (expected.flags & Arithmetic));
    }
    std::puts("PASS: Linux RDTSC replacement, 512 full GPR/YMM/flags/red-zone comparisons");
}
#endif
} // namespace

int main() try {
    ReferenceAnchors();
    LowMemory low;
    std::mt19937_64 random(0x3770);
    const auto cases = Cases();
    std::array<unsigned, 12> family_cases{}, family_failures{};
    Word trials = 0;
    unsigned failures = 0;
    const std::array<Word, 20> edges{0, 1, 2, 3, 0x7fff, 0x8000, 0xffff, 0x10000,
        0x7fffffff, 0x80000000, 0xffffffff, 0x100000000, 0x7fffffffffffffff,
        0x8000000000000000, ~Word{0}, 0xaaaaaaaaaaaaaaaa, 0x5555555555555555,
        0x0001000100010001, 0x0000000100000000, 0x8000000080000000};
    for (std::size_t case_index = 0; case_index < cases.size(); ++case_index) {
        const auto& t = cases[case_index];
        const bool indexed = t.src.location == Location::Indexed ||
            t.dst.location == Location::Indexed || t.control.location == Location::Indexed;
        ++family_cases[unsigned(t.op)];
        Xbyak::CodeGenerator encoded(256, low.base); // original instructions are non-executable data
        Encode(t, encoded, low);
        bool emitted = false;
        Runner runner([&](auto& c) { emitted = Core::EmitCpuEmulationForTest(low.base, c); });
        if (!emitted) throw std::runtime_error(std::string("no existing patch for ") + Name(t.op));
        AuditGeneratedCode(runner);
        bool passed = true;
        const auto run = [&](State input, unsigned length, unsigned index) {
            if (!passed) return;
            if (indexed) input.gpr[Rdi] = 2;
            Controls(t, input, length, index);
            State actual = input;
            actual.gpr[Rsi] = reinterpret_cast<Word>(actual.memory.data() + 32);
            State expected = actual;
            std::memcpy(low.data(), actual.rip_memory.data(), actual.rip_memory.size());
            runner.getCode<void (*)(State*)>()(&actual);
            std::memcpy(actual.rip_memory.data(), low.data(), actual.rip_memory.size());
            expected.gpr[Rsp] = actual.entry_rsp;
            expected.entry_rsp = actual.entry_rsp;
            Reference(t, expected);
            ++trials;
            if (!Same(t, expected, actual, false)) {
                if (failures < 10) {
                    std::printf("FAIL case %zu: %s/%u dst=%d src=(%u,%d,%d) control=%d len=%u index=%u input=%llx flags=%llx\n",
                        case_index, Name(t.op), t.bits, t.dst.reg, unsigned(t.src.location), t.src.reg,
                        t.src.offset, t.control.reg, length, index, (unsigned long long)input.gpr[0],
                        (unsigned long long)input.flags);
                    Same(t, expected, actual, true);
                }
                passed = false;
            }
        };
        for (Word value : edges) {
            for (unsigned pattern = 0; pattern < 64 && passed; ++pattern) {
                State input = RandomState(random);
                if (indexed) input.gpr[Rdi] = 2;
                input.flags = 0x202;
                for (unsigned bit = 0; bit < 6; ++bit)
                    if (pattern & (1u << bit)) input.flags |= Word{1} << std::array{0, 2, 4, 6, 7, 11}[bit];
                if (t.op == Op::Extrq || t.op == Op::Insertq) input.ymm[t.dst.reg][0] = value;
                else if (t.op == Op::Movntss || t.op == Op::Movntsd) input.ymm[t.src.reg][0] = value;
                else Write(input, t.src, t.bits, value);
                const unsigned length = pattern;
                const unsigned index = (t.op == Op::Extrq || t.op == Op::Insertq) ? 0 : (pattern * 7) & 255;
                run(input, length, index);
            }
        }
        for (unsigned bit = 0; bit < t.bits && passed; ++bit) {
            State input = RandomState(random);
            if (indexed) input.gpr[Rdi] = 2;
            if (t.op == Op::Extrq || t.op == Op::Insertq) input.ymm[t.dst.reg][0] = Word{1} << bit;
            else if (t.op == Op::Movntss || t.op == Op::Movntsd) input.ymm[t.src.reg][0] = Word{1} << bit;
            else Write(input, t.src, t.bits, Word{1} << bit);
            run(input, bit, 0);
        }
        for (unsigned i = 0; i < 512 && passed; ++i) {
            const unsigned length = random() % 64;
            const unsigned index = (t.op == Op::Extrq || t.op == Op::Insertq)
                ? (length ? random() % (65 - length) : 0) : random() % 256;
            run(RandomState(random), length, index);
        }
        if (t.exhaustive || ((t.op == Op::Extrq || t.op == Op::Insertq) && !t.immediate)) {
            const unsigned limit = t.op == Op::Bextr ? 256 : 64;
            for (unsigned length = 0; length < limit && passed; ++length)
                for (unsigned index = 0; index < limit && passed; ++index) {
                    if (limit == 64 && index + (length ? length : 64) > 64) continue;
                    run(RandomState(random), length, index);
                }
        }
        if (!passed) { ++failures; ++family_failures[unsigned(t.op)]; }
    }
    for (unsigned i = 0; i < family_cases.size(); ++i)
        std::printf("%-8s %u forms, %u failed\n", Names[i], family_cases[i], family_failures[i]);
    std::printf("%s: %zu forms, %llu software comparisons; native guest instructions never executed\n",
                failures ? "FAIL" : "PASS", cases.size(), (unsigned long long)trials);
#ifdef __linux__
    if (!failures) ClockReplacement();
#endif
    return failures ? 1 : 0;
} catch (const std::exception& error) {
    std::fprintf(stderr, "cpu-emulation-test: %s\n", error.what());
    return 1;
}
