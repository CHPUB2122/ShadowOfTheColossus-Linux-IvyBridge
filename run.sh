#!/usr/bin/env bash
# Linux: launch the existing prepared build, preserving its modules, patches and settings.
#   bash run.sh [--build] [--software] [--game directory] [--user directory] [--dry-run]
# Building is explicit; preparing a new image remains a separate step through sotc.py.
#   --software: Mesa's Lavapipe CPU renderer (slow; for machines without a Vulkan GPU).
# The normal command never builds, reparses the dump or requires nix-shell.
# BB_GAME_DIR is accepted for SOTC_GAME_DIR (the dumped game folder, default ../CUSA08809).
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ${1:-} == --build ]]; then
    shift
    bash build.sh
fi
if [[ ${1:-} == --software ]]; then
    shift
    if [[ -z ${VK_DRIVER_FILES:-} ]]; then
        for candidate in /run/opengl-driver/share/vulkan/icd.d/lvp_icd*.json /usr/share/vulkan/icd.d/lvp_icd*.json; do
            if [[ -f $candidate ]]; then export VK_DRIVER_FILES=$candidate; break; fi
        done
    fi
    if [[ -z ${VK_DRIVER_FILES:-} ]]; then echo 'Lavapipe not found; set VK_DRIVER_FILES.' >&2; exit 1; fi
    export VK_LOADER_LAYERS_DISABLE='~implicit~'
fi
if [[ -z ${PYTHON:-} ]]; then
    PYTHON=$(command -v python3 || true)
    if [[ -z $PYTHON ]]; then
        for candidate in /nix/store/*-python3-*/bin/python3; do
            if [[ -x $candidate ]]; then PYTHON=$candidate; break; fi
        done
    fi
fi
if [[ -z ${PYTHON:-} ]]; then echo 'Install Python 3 or set PYTHON.' >&2; exit 1; fi
if [[ -n ${BB_GAME_DIR:-} && -z ${SOTC_GAME_DIR:-} ]]; then export SOTC_GAME_DIR=$BB_GAME_DIR; fi
exec "$PYTHON" tools/sotc_launch.py "$@"
