// SPDX-License-Identifier: GPL-2.0-or-later
// Real resource patching/specialization and permutation ownership; no GPU or game.
#include <array>
#include <bit>
#include <cstdio>
#include <fstream>
#include <iterator>
#include "common/serdes.h"
#include "shader_recompiler/ir/ir_emitter.h"
#include "shader_recompiler/ir/passes/ir_passes.h"
#include "video_core/renderer_vulkan/vk_pipeline_cache.h"

namespace Vulkan {
bool LoadShaderMeta(Serialization::Archive&, Shader::Info&, Shader::StageSpecialization&, size_t&);
}

#define CHECK(condition) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); return false; } } while (0)

static Shader::Info Material(AmdGpu::DataFormat format) {
    Shader::Info info{};
    info.hw_stage = Shader::HwStage::Fragment;
    info.sw_stage = Shader::SwStage::Fragment;
    info.FlatBuf().resize(16);
    auto image = AmdGpu::Image::Null(false);
    image.base_address = 0x1000000000ULL >> 8;
    image.width = image.height = 7;
    image.num_format = u64(AmdGpu::NumberFormat::Uint);
    image.data_format = u64(format);
    std::memcpy(info.FlatBuf().data(), &image, sizeof(image));
    return info;
}

static bool Specialization() {
    using namespace Shader;
    constexpr auto fmask = AmdGpu::DataFormat::FormatFmask64_S16_F8;
    constexpr auto normal = AmdGpu::DataFormat::Format32_32;
    auto info = Material(fmask);
    RuntimeInfo runtime{}; runtime.Initialize(info.hw_stage, info.sw_stage);
    Profile profile{};
    Common::ObjectPool<IR::Inst> pool;
    IR::Block block(pool);
    IR::IREmitter ir(block);
    const auto coords = ir.CompositeConstruct(ir.Imm32(0u), ir.Imm32(0u),
                                              ir.Imm32(0u), ir.Imm32(0u));
    const auto color = ir.ImageRead(ir.Imm32(0u), coords, ir.Imm32(0u), ir.Imm32(0u), {});
    Optimization::ResourceDiscovery usage{};
    usage.user = color.Inst();
    usage.sharps[0].num_dwords = 8;
    for (u32 i = 0; i < 8; ++i) {
        usage.sharps[0].dwords[i] = ir.GetUserData(IR::ScalarReg(i));
    }
    Optimization::ResourcePatchingPass(info, Optimization::ResourceDiscoveryList{usage}, profile);
    CHECK(info.images.empty());
    CHECK(info.fmasks.size() == 1 && info.fmasks[0].sharp_idx == 0);
    const StageSpecialization was_fmask{info, runtime, profile, {}};
    auto changed = Material(normal);
    info.FlatBuf() = changed.FlatBuf();
    const StageSpecialization now_normal{info, runtime, profile, {}};
    CHECK(!(was_fmask == now_normal));
    CHECK(!(now_normal == was_fmask));

    info.fmasks.clear();
    ImageResource resource{};
    resource.sharp_fetch.summary = SharpFetch<AmdGpu::Image>::Summary::SingleLoad;
    resource.sharp_fetch.load_mask = 255;
    info.images.push_back(resource);
    const StageSpecialization normal_image{info, runtime, profile, {}};
    info.FlatBuf() = Material(fmask).FlatBuf();
    const StageSpecialization changed_to_fmask{info, runtime, profile, {}};
    CHECK(!(normal_image == changed_to_fmask));
    CHECK(!(changed_to_fmask == normal_image));
    for (const auto* original : {&was_fmask, &changed_to_fmask}) {
        Serialization::Archive archive;
        original->Serialize(archive);
        Serialization::Archive input{archive.TakeOff()};
        StageSpecialization restored{};
        restored.info = &info;
        CHECK(restored.Deserialize(input));
        CHECK(*original == restored && restored == *original);
    }

    auto different_count = changed_to_fmask;
    different_count.images.emplace_back();
    different_count.bitset.reset();
    CHECK(!(different_count == changed_to_fmask));
    CHECK(!(changed_to_fmask == different_count));
    puts("PASS: dynamic FMASK transitions and unequal resource counts cannot reuse a specialization");
    return true;
}

static bool OwnershipAndSerialization() {
    using namespace Shader;
    Vulkan::Program program;
    program.info = Material(AmdGpu::DataFormat::Format32_32);
    StageSpecialization first{}; first.info = &program.info;
    program.AddPermut({}, std::move(first));
    auto analysis = std::make_unique<Info>(Material(AmdGpu::DataFormat::Format8_8_8_8));
    analysis->images.resize(14);
    const auto* address = analysis.get();
    RuntimeInfo runtime{}; runtime.Initialize(analysis->hw_stage, analysis->sw_stage);
    StageSpecialization spec{}; spec.info = address;
    program.AddPermut({}, std::move(spec), std::move(analysis));
    CHECK(&program.ModuleInfo(1) == address);
    CHECK(program.modules[1].spec.info == address);
    CHECK(program.ModuleInfo(0).images.empty());
    CHECK(program.ModuleInfo(1).images.size() == 14);
    // Moving the module vector must leave Info pointers retained by pipelines valid.
    program.modules.resize(32);
    CHECK(&program.ModuleInfo(1) == address && program.modules[1].spec.info == address);

    Serialization::Archive archive;
    program.ModuleInfo(1).Serialize(archive);
    Info restored{};
    Serialization::Archive input{archive.TakeOff()};
    CHECK(restored.Deserialize(input));
    CHECK(restored.images.size() == 14);
    CHECK(restored.FlatBuf() == program.ModuleInfo(1).FlatBuf());
    puts("PASS: separate permutation analysis survives vector movement and metadata serialization");
    return true;
}

int main(int argc, char** argv) {
    if (!Specialization() || !OwnershipAndSerialization()) return 1;
    if (argc == 2) {
        std::ifstream file(argv[1], std::ios::binary);
        std::vector<u8> bytes{std::istreambuf_iterator<char>(file), {}};
        if (bytes.size() < 8) return 1;
        Serialization::Archive archive{std::move(bytes)};
        Shader::Info info{};
        Shader::StageSpecialization spec{};
        size_t index{};
        if (Vulkan::LoadShaderMeta(archive, info, spec, index)) return 1;
        puts("PASS: old metadata with incompatible permutation analyses is rejected");
    }
    return 0;
}
