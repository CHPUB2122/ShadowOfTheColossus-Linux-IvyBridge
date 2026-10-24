#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
mkdir -p out
# Windows: MSYS2 CLANG64 (packages in packaging/windows/README.md). The GPU library is static
# there and CMake links bb-probe.exe as well. ThinLTO by default (BB_LTO=OFF disables it);
# Clang PGO from pgo/bbgpu.profdata when present (tools/pgo_train.sh makes it).
case $(uname -s) in
MINGW*|MSYS*)
    # shellcheck source=msys2-env.sh
    source ./msys2-env.sh
    for tool in clang cmake ninja pkg-config; do
        command -v "$tool" >/dev/null || { echo "Need $tool from MSYS2 CLANG64 (packaging/windows/README.md)." >&2; exit 1; }
    done
    if [[ ! -f gpu/third_party/fsr-vulkan/CMakeLists.txt || ! -f gpu/third_party/imgui/imgui.h ||
          ! -f gpu/third_party/xbyak/xbyak/xbyak.h ]]; then
        git submodule update --init --recursive
    fi
    for patch in gpu/patches/fsr-vulkan/*.patch; do
        if ! git -C gpu/third_party/fsr-vulkan apply --reverse --check "$PWD/$patch" 2>/dev/null; then
            git -C gpu/third_party/fsr-vulkan apply "$PWD/$patch"
        fi
    done
    # sotc: llvm-windres, binutils windres fails on build paths with spaces ("Unable to create
    # temp file").
    # sotc: BB_PGO=generate builds an instrumented exe (Clang profile in pgo/, see
    # gpu/CMakeLists.txt); by default pgo/bbgpu.profdata is used when present.
    pgo=${BB_PGO:-}
    if [[ -z $pgo ]]; then
        if [[ -f pgo/bbgpu.profdata ]]; then pgo=use; else pgo=off; fi
    fi
    mkdir -p pgo
    cmake -S gpu -B out/gpu -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBB_PGO="$pgo" \
        -DBB_PGO_DIR="$PWD/pgo" -DBB_LTO="${BB_LTO:-ON}" -DCMAKE_C_COMPILER=clang \
        -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_RC_COMPILER=llvm-windres >/dev/null
    echo "GPU library and loader: PGO $pgo, LTO ${BB_LTO:-ON}"
    if ! ninja -C out/gpu bb-probe bb-gpu-capabilities > out/gpu-build.log 2>&1; then
        grep -v '^\[' out/gpu-build.log | tail -40 >&2
        echo 'Build failed (full log: out/gpu-build.log)' >&2; exit 1
    fi
    cp out/gpu/bb-probe.exe out/gpu/bb-gpu-capabilities.exe out/
    echo "Built $PWD/out/bb-probe.exe"
    exit 0
    ;;
esac
# sotc: native Linux stage 1. All sources and test executables share CMake's Ivy Bridge flags.
if [[ $(uname -s) != Linux ]]; then
    echo 'Supported build hosts: Linux x86-64 or MSYS2 CLANG64.' >&2
    exit 1
fi
if [[ $# -gt 1 || ( $# -eq 1 && $1 != --test ) ]]; then
    echo 'Usage: bash build.sh [--test]' >&2
    exit 1
fi
# Keep every build attempt, including failures, before the next invocation updates the latest logs.
log_directory="out/logs/linux-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$log_directory"
save_build_logs() {
    local result=$?
    for log in gpu-configure.log gpu-build.log linux-build-info.txt tests-build.log tests.log; do
        if [[ -f out/$log ]]; then cp -- "out/$log" "$log_directory/$log" || true; fi
    done
    printf 'exit status: %s\n' "$result" >"$log_directory/result.txt"
}
trap save_build_logs EXIT
: >out/gpu-configure.log
: >out/gpu-build.log
# Optional local copies of distro packages: useful when system installation is not authorized.
deps_prefix=${BB_DEPS_PREFIX:-}
if [[ -z $deps_prefix && -d out/deps/arch-root/usr ]]; then
    deps_prefix=$PWD/out/deps/arch-root/usr
fi
if [[ -n $deps_prefix ]]; then
    deps_prefix=$(cd -- "$deps_prefix" && pwd)
    export PATH="$deps_prefix/bin:$PATH"
    export LD_LIBRARY_PATH="$deps_prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export CMAKE_PREFIX_PATH="$deps_prefix${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
fi
missing=()
for tool in cmake ninja pkg-config cc c++ python3; do
    command -v "$tool" >/dev/null || missing+=("$tool")
done
if (( ${#missing[@]} )); then
    printf 'Missing build tools: %s\n' "${missing[*]}" >&2
    echo 'See docs/sotc/LINUX-IVYBRIDGE.md for installation commands.' >&2
    exit 1
fi
if ! pkg-config --exists vulkan sdl3 x11 libxxhash libavformat libavcodec libavutil libswscale libswresample; then
    echo 'Missing development libraries (pkg-config):' >&2
    pkg-config --print-errors --exists vulkan sdl3 x11 libxxhash libavformat libavcodec libavutil libswscale libswresample >&2
    exit 1
fi
# Use the existing submodule revisions, without updating them to their upstream heads.
if [[ ! -f gpu/third_party/fsr-vulkan/CMakeLists.txt || ! -f gpu/third_party/imgui/imgui.h ||
      ! -f gpu/third_party/xbyak/xbyak/xbyak.h || ! -f third_party/LibAtrac9/C/src/decoder.c ]]; then
    git submodule update --init --recursive
fi
bash tools/setup_linux_vma.sh
for patch in gpu/patches/fsr-vulkan/*.patch; do
    if ! git -C gpu/third_party/fsr-vulkan apply --reverse --check "$PWD/$patch" 2>/dev/null; then
        git -C gpu/third_party/fsr-vulkan apply "$PWD/$patch"
    fi
done
# Explicit OFF also clears a previous build's PGO/LTO choice; no automatic profile selection.
cmake -S gpu -B out/gpu -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DCMAKE_C_COMPILER="${CC:-cc}" -DCMAKE_CXX_COMPILER="${CXX:-c++}" \
    -DBB_PGO=off -DBB_LTO=OFF \
    -DCMAKE_DISABLE_FIND_PACKAGE_VulkanMemoryAllocator=TRUE \
    -DVMA_INCLUDE_DIR="$PWD/out/deps/vma-3.3.0" >out/gpu-configure.log 2>&1 || {
    tail -60 out/gpu-configure.log >&2
    exit 1
}
{
    git rev-parse HEAD
    git submodule status --recursive
    "${CC:-cc}" --version
    "${CXX:-c++}" --version
    cmake --version
    ninja --version
    pkg-config --modversion vulkan sdl3 x11 libxxhash libavformat libavcodec libavutil libswscale libswresample
    printf '%s\n' 'CPU: -march=ivybridge -mno-avx2 -mno-bmi -mno-bmi2 -mno-movbe -mno-lzcnt' 'PGO: off; LTO: OFF'
    printf 'Local dependencies: %s\n' "${deps_prefix:-none}"
} >out/linux-build-info.txt
printf '%s\n' 'Linux x86-64: Ivy Bridge, PGO off, LTO OFF'
if ! cmake --build out/gpu --parallel "${BB_JOBS:-2}" --target bb-probe bb-gpu-capabilities >out/gpu-build.log 2>&1; then
    tail -40 out/gpu-build.log >&2
    echo 'Build failed (full log: out/gpu-build.log)' >&2
    exit 1
fi
cp out/gpu/bb-probe out/gpu/bb-gpu-capabilities out/
echo "Built $PWD/out/bb-probe and $PWD/out/gpu/libbbgpu.so"
if [[ ${1:-} == --test ]]; then
    cmake --build out/gpu --parallel "${BB_JOBS:-2}" \
        --target pad-test file-mods-test content-test runtime-test sema-test savedata-test \
        upscaler-support-test cpu-emulation-test cpu-patch-decode-test >out/tests-build.log 2>&1 || {
        tail -80 out/tests-build.log >&2
        exit 1
    }
    for test in pad file-mods content runtime sema; do
        cp "out/gpu/$test-test" "out/$test-test"
    done
    ctest --test-dir out/gpu --output-on-failure | tee out/tests.log
fi
