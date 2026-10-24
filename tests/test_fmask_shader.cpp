// SPDX-License-Identifier: GPL-2.0-or-later
// Exercise the real FMASK resource patching pass and SPIR-V emitter, without Vulkan/game data.
#include <array>
#include <bit>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include "common/elf_info.h"
#include "shader_recompiler/backend/spirv/emit_spirv.h"
#include "shader_recompiler/ir/ir_emitter.h"
#include "shader_recompiler/ir/passes/ir_passes.h"

namespace Core {
class Emulator {
public:
    static void SetSerial() {
        auto& elf = Common::ElfInfo::Instance();
        elf.initialized = true;
        elf.game_serial = "CUSA08809";
    }
};
}

static bool Emit(const std::filesystem::path& output, bool sample, bool allow_old) {
    using namespace Shader;
    Info info{};
    info.hw_stage = HwStage::Fragment;
    info.sw_stage = SwStage::Fragment;
    RuntimeInfo runtime{};
    runtime.Initialize(info.hw_stage, info.sw_stage);
    runtime.hw.fs.color_buffers[0].num_format = AmdGpu::NumberFormat::Float;
    Profile profile{};
    profile.supported_spirv = 0x00010600;
    profile.support_int64 = true;

    Common::ObjectPool<IR::Inst> pool;
    IR::Block block(pool);
    IR::IREmitter ir(block);
    const auto coords = ir.CompositeConstruct(ir.Imm32(0u), ir.Imm32(0u),
                                              ir.Imm32(0u), ir.Imm32(0u));
    const auto color = sample ? ir.ImageSampleRaw(ir.Imm32(0u), ir.Imm32(0u), coords,
                                                  coords, coords, ir.Imm32(0.f), {})
                              : ir.ImageRead(ir.Imm32(0u), coords, ir.Imm32(0u), ir.Imm32(0u), {});
    std::array<IR::Inst*, 4> extracts{};
    std::array<IR::Inst*, 4> outputs{};
    for (u32 i = 0; i < 4; ++i) {
        const auto component = ir.CompositeExtract(color, i);
        extracts[i] = component.Inst();
        ir.SetAttribute(IR::Attribute::RenderTarget0, IR::F32{component}, i);
        outputs[i] = &block.Instructions().back();
        info.stores.Set(IR::Attribute::RenderTarget0, i);
    }
    ir.Epilogue();

    auto image = AmdGpu::Image::Null(false);
    image.base_address = 0x1000000000ULL >> 8;
    image.data_format = u64(AmdGpu::DataFormat::FormatFmask64_S16_F8);
    image.num_format = u64(AmdGpu::NumberFormat::Uint);
    image.width = image.height = 7;
    const auto words = std::bit_cast<std::array<u32, 8>>(image);
    Optimization::ResourceDiscovery usage{};
    usage.user = color.Inst();
    usage.sharps[0].num_dwords = 8;
    for (u32 i = 0; i < 8; ++i) usage.sharps[0].dwords[i] = ir.Imm32(words[i]);
    Optimization::ResourceDiscoveryList resources{usage};
    Optimization::ResourcePatchingPass(info, resources, profile);
    const auto replacement_type = extracts[0]->Arg(0).Type();
    std::printf("FMASK %s replacement=%u expected=%u\n", sample ? "sample" : "read",
                u32(replacement_type), u32(IR::Type::F32x4));
    if (!allow_old && replacement_type != IR::Type::F32x4) return false;

    IR::Program program(info);
    program.blocks.push_back(&block);
    program.post_order_blocks.push_back(&block);
    program.syntax_list.push_back({.data = {.block = &block},
                                   .type = IR::AbstractSyntaxNode::Type::Block});
    program.syntax_list.push_back({.type = IR::AbstractSyntaxNode::Type::Return});
    Optimization::ConstantPropagationPass(program.post_order_blocks);
    if (!allow_old) {
        // The fix preserves the raw XY payload and supplies zero for absent channels.
        constexpr std::array<u32, 4> expected{0x76543210, 0xfedcba98, 0, 0};
        for (u32 i = 0; i < 4; ++i) {
            const auto value = outputs[i]->Arg(1);
            if (!value.IsImmediate() || std::bit_cast<u32>(value.F32()) != expected[i]) {
                std::fprintf(stderr, "FMASK component %u changed unexpectedly\n", i);
                return false;
            }
        }
    }
    Backend::Bindings bindings{};
    const auto binary = Backend::SPIRV::EmitSPIRV(profile, runtime, program, bindings);
    std::ofstream file(output, std::ios::binary);
    file.write(reinterpret_cast<const char*>(binary.data()), binary.size() * sizeof(u32));
    return bool(file);
}

int main(int argc, char** argv) {
    if (argc < 2) return 2;
    Core::Emulator::SetSerial();
    const std::filesystem::path directory{argv[1]};
    const bool allow_old = argc > 2;
    std::filesystem::create_directories(directory);
    return Emit(directory / "read.spv", false, allow_old) &&
                   Emit(directory / "sample.spv", true, allow_old) ? 0 : 1;
}
