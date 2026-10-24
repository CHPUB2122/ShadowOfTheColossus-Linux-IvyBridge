#!/usr/bin/env bash
# sotc: the pinned header-only VMA dependency, without root or system-wide installation.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
header=out/deps/vma-3.3.0/vk_mem_alloc.h
sha=90ce12fc4a2466235a09ae02905dd0c13aee80c1bbf11b331ab61230c2ceb112
if [[ ! -f $header ]]; then
    mkdir -p "$(dirname -- "$header")"
    temporary=$(mktemp "${header}.XXXXXX")
    trap 'rm -f -- "$temporary"' EXIT
    curl --fail --silent --show-error --location --retry 2 \
        https://raw.githubusercontent.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator/v3.3.0/include/vk_mem_alloc.h \
        --output "$temporary"
    printf '%s  %s\n' "$sha" "$temporary" | sha256sum --check --status
    mv -- "$temporary" "$header"
fi
if ! printf '%s  %s\n' "$sha" "$header" | sha256sum --check --status; then
    echo "VMA 3.3.0 checksum mismatch: $header" >&2
    exit 1
fi
echo "VMA 3.3.0 verified: $header"
