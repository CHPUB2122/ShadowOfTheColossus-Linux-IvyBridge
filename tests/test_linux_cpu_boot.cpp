// SPDX-License-Identifier: GPL-2.0-or-later
// End-to-end scanner -> RX trampolines -> real SIGILL/ucontext, without game files.
#include <cassert>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <functional>
#include <thread>
#include <vector>
#include <sys/mman.h>
#include <xbyak/xbyak.h>
#include "cpu_patches.h"
#include "sotc_patches.h"
#include "cpu_emulation_reference.h"
extern "C" int runtime_signal_stack_prepare(void);
using namespace Xbyak::util;
using namespace CpuTest;
namespace {
volatile sig_atomic_t signals_seen;
Word observed[2];
void handler(int, siginfo_t*, void* context) {
    char local;
    stack_t stack{};
    if (sigaltstack(nullptr, &stack) || !(stack.ss_flags & SS_ONSTACK) ||
        &local < static_cast<char*>(stack.ss_sp) ||
        &local >= static_cast<char*>(stack.ss_sp) + stack.ss_size ||
        !sotc_handle_illegal(context)) _Exit(132);
    signals_seen = signals_seen + 1;
}
struct Answer { Word value, flags; };
using Function = Answer (*)(Word, void*, Word);
struct Case {
    const char* name;
    Instruction reference;
    std::function<void(Xbyak::CodeGenerator&)> emit;
    bool memory = false, store = false, late = false, sse = false;
};
}
int main() {
    assert(runtime_signal_stack_prepare());
    struct sigaction sa{};
    sa.sa_sigaction = handler;
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigemptyset(&sa.sa_mask);
    assert(sigaction(SIGILL, &sa, nullptr) == 0);
    constexpr std::size_t image_size = 65536, trampoline_size = 65536, segment_size = 32768;
    auto* image = static_cast<unsigned char*>(mmap(nullptr, image_size + trampoline_size,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_32BIT, -1, 0));
    assert(image != MAP_FAILED);
    std::memset(image, 0x90, image_size);
    Xbyak::CodeGenerator finish(256, image + 0x7f00);
    finish.mov(r10, reinterpret_cast<Word>(observed));
    finish.mov(r8, qword[rsp - 8]); finish.mov(qword[r10], r8);
    finish.mov(r8, qword[rsp - 128]); finish.mov(qword[r10 + 8], r8);
    finish.pushfq(); finish.pop(rdx); finish.ret();
    const std::vector<Case> cases{
        {"tzcnt64", {Op::Tzcnt,64,Reg(0),Reg(7)}, [](auto& c){ c.tzcnt(rax,rdi); }},
        {"tzcnt32 trap", {Op::Tzcnt,32,Reg(0),Reg(7)}, [](auto& c){ c.tzcnt(eax,edi); }},
        {"lzcnt64", {Op::Lzcnt,64,Reg(0),Reg(7)}, [](auto& c){ c.lzcnt(rax,rdi); }},
        {"lzcnt32 trap", {Op::Lzcnt,32,Reg(0),Reg(7)}, [](auto& c){ c.lzcnt(eax,edi); }},
        {"andn64", {Op::Andn,64,Reg(0),Reg(7),Reg(2)}, [](auto& c){ c.andn(rax,rdi,rdx); }},
        {"bextr64", {Op::Bextr,64,Reg(0),Reg(7),Reg(2)}, [](auto& c){ c.bextr(rax,rdi,rdx); }},
        {"blsi64", {Op::Blsi,64,Reg(0),Reg(7)}, [](auto& c){ c.blsi(rax,rdi); }},
        {"blsmsk64", {Op::Blsmsk,64,Reg(0),Reg(7)}, [](auto& c){ c.blsmsk(rax,rdi); }},
        {"blsr64", {Op::Blsr,64,Reg(0),Reg(7)}, [](auto& c){ c.blsr(rax,rdi); }},
        {"movbe32 trap", {Op::Movbe,32,Reg(0),Mem()}, [](auto& c){ c.movbe(eax,dword[rdi]); },true},
        {"movbe32 store", {Op::Movbe,32,Mem(),Reg(2)}, [](auto& c){ c.movbe(dword[rdi],edx); c.mov(rax,rdx); },true,true},
        {"movbe64", {Op::Movbe,64,Reg(0),Mem()}, [](auto& c){ c.movbe(rax,qword[rdi]); },true},
        {"movbe16", {Op::Movbe,16,Reg(0),Mem()}, [](auto& c){ c.movbe(ax,word[rdi]); },true},
        {"late andn JIT", {Op::Andn,64,Reg(0),Reg(7),Reg(2)}, [](auto& c){ c.andn(rax,rdi,rdx); },false,false,true},
        {"late movbe fallback", {Op::Movbe,32,Reg(0),Mem()}, [](auto& c){ c.movbe(eax,dword[rdi]); },true,false,true},
        {"late extrq context", {}, [](auto& c){
            c.movq(xmm0,rdi); c.movq(xmm1,rdx);
            const unsigned char bytes[]={0x66,0x0f,0x79,0xc1}; c.db(bytes,4); c.movq(rax,xmm0);
        },false,false,true,true},
    };
    std::vector<uintptr_t> starts;
    std::vector<Function> functions;
    constexpr Word sentinel = 0x3770600601020304;
    for (std::size_t i = 0; i < cases.size(); ++i) {
        auto* at = image + (cases[i].late ? 0xc000 : 0x100) + i * 256;
        Xbyak::CodeGenerator c(256, at);
        c.mov(eax, 0x202); c.push(rax); c.popfq();
        c.mov(rax,sentinel); c.mov(qword[rsp-8],rax); c.mov(qword[rsp-128],rax);
        if (cases[i].reference.bits == 16) c.mov(eax,0); // known upper bits for partial MOVBE write
        cases[i].emit(c);
        c.jmp(rsi);
        if (!cases[i].late) starts.push_back(reinterpret_cast<uintptr_t>(at));
        functions.push_back(reinterpret_cast<Function>(at));
    }
    starts.push_back(reinterpret_cast<uintptr_t>(finish.getCode()));
    Core::RegisterPatchModule(image,image_size,image+image_size,trampoline_size);
    assert(!sotc_cpu_patches_ready(image));
    Core::PatchShortSse4aInstructions(reinterpret_cast<uintptr_t>(image),segment_size,starts);
    Core::PrePatchInstructions(reinterpret_cast<uintptr_t>(image),segment_size);
    assert(sotc_cpu_patches_ready(image));
    assert(mprotect(image,image_size+trampoline_size,PROT_READ|PROT_EXEC)==0);
    unsigned comparisons = 0;
    const auto run = [&] {
        assert(runtime_signal_stack_prepare());
        for (std::size_t i=0;i<cases.size();++i) {
            const auto& test=cases[i];
            for (Word input : {Word{0},Word{1},Word{8},Word{0x80000000},Word{~Word{0}}}) {
                Word memory=input, control=0x0808;
                State expected;
                expected.flags=0x202; expected.gpr[7]=input; expected.gpr[2]=control;
                expected.gpr[0]=test.reference.bits==16 ? 0 : sentinel;
                Write(expected,Mem(),64,input);
                if (!test.sse) Reference(test.reference,expected);
                const Word value=test.sse ? (input>>8)&255 :
                    test.store ? control : expected.gpr[0];
                const Answer result=functions[i](test.memory ? reinterpret_cast<Word>(&memory) : input,
                    const_cast<unsigned char*>(finish.getCode()),control);
                const Word mask=test.sse ? Arithmetic : DefinedFlags(test.reference.op);
                if (result.value!=value || (result.flags&mask)!=(expected.flags&mask)) {
                    std::printf("FAIL %s input=%llx result=%llx/%llx expected=%llx/%llx\n",
                        test.name,(unsigned long long)input,(unsigned long long)result.value,
                        (unsigned long long)(result.flags&mask),(unsigned long long)value,
                        (unsigned long long)(expected.flags&mask));
                    std::fflush(stdout); std::abort();
                }
                assert(memory==Read(expected,Mem(),64));
                assert(observed[0]==sentinel && observed[1]==sentinel);
                ++comparisons;
            }
        }
    };
    run();
    std::thread worker(run); worker.join();
    assert(signals_seen>0);
    // Unsupported RSP register operands must leave the module gated.
    auto* bad=static_cast<unsigned char*>(mmap(nullptr,8192,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS|MAP_32BIT,-1,0));
    assert(bad!=MAP_FAILED); std::memset(bad,0x90,8192);
    Xbyak::CodeGenerator rejected(256,bad); rejected.tzcnt(eax,esp); rejected.ret();
    Core::RegisterPatchModule(bad,4096,bad+4096,4096);
    const uintptr_t root=reinterpret_cast<uintptr_t>(bad);
    Core::PatchShortSse4aInstructions(root,4096,std::span(&root,1));
    assert(!sotc_cpu_patches_ready(bad));
    std::printf("PASS: %u end-to-end comparisons; %d SIGILL on alternate stacks; unsupported site blocked\n",
                comparisons,int(signals_seen));
}
