#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Isolated graphics A/B/C: preserved cache, targeted recompile, FMASK type fix.

The normal launcher and original user directory are never changed by this tool.
Prepared executables/libraries live in out/graphics-fmask; see LINUX-FMASK.md.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from sotc_launch import (ROOT, DIAGNOSTICS, load_ini, resolve_storage, prepared_command,
                         user_lock, file_manifest, play)

VARIANT = ROOT / "out/graphics-fmask"
LAYOUT = ROOT / "out/graphics-layout"
MODES = ("baseline", "recompile", "fixed", "layout")
SHADERS = (0xdf2d1d0b, 0x949ac65e)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    env = os.environ.copy()
    load_ini(env)
    source = resolve_storage(env)
    if (VARIANT / "users").exists():
        raise ValueError("isolated users already exist; existing tests are preserved")
    info = json.loads((VARIANT / "build-info.json").read_text())
    if sha(ROOT / "out/gpu/libbbgpu.so") != info["baseline_library_sha256"]:
        raise ValueError("the stable renderer changed since this variant was built")
    with user_lock(source):
        original = file_manifest(source)
        (VARIANT / "users").mkdir()
        quarantine = {}
        for mode in MODES[:3]:
            target = VARIANT / "users" / mode
            subprocess.run(["cp", "-a", "--reflink=auto", str(source), str(target)], check=True)
            if file_manifest(target) != original:
                raise ValueError(f"copy verification failed: {target}")
            removed = []
            if mode != "baseline":
                for shader in SHADERS:
                    # Only these two proven FMASK-producing shaders are recompiled.
                    # Metadata/pipeline keys stay; a missing binary is skipped by preload.
                    for path in sorted((target / "cache").rglob(f"0x{shader:016x}_*.spv")):
                        relative = path.relative_to(target)
                        archive = VARIANT / "quarantine" / mode / relative
                        archive.parent.mkdir(parents=True, exist_ok=True)
                        removed.append({"path": str(relative), "sha256": sha(path)})
                        path.rename(archive)
            quarantine[mode] = removed
        if file_manifest(source) != original:
            raise ValueError("the source user directory changed during preparation")
        (VARIANT / "users-manifest.json").write_text(json.dumps({
            "source": str(source), "source_files": original, "quarantine": quarantine,
            "note": "Isolated snapshots; no automatic restoration to the active profile."}, indent=2) + "\n")
    print(f"Prepared three verified snapshots from {source}.")
    print("baseline: original renderer/cache; recompile: original renderer/two shader hashes recompiled;")
    print("fixed: patched renderer/the same two hashes recompiled. Original saves/cache are untouched.")


def validate():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = VARIANT / f"validation-{stamp}-{os.getpid()}"
    output.mkdir()
    result = {}
    for mode, binary, library, extra in (
        ("before", "fmask-baseline-test", ROOT / "out/gpu", ["allow-old"]),
        ("after", "fmask-shader-test", VARIANT, []),
    ):
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = str(library) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        user = output / mode / "user"
        user.mkdir(parents=True)
        env["BB_GPU_USER_DIR"] = str(user)
        run = subprocess.run([str(VARIANT / binary), str(output / mode), *extra], env=env,
                             capture_output=True, timeout=15)
        (output / f"{mode}.log").write_bytes(run.stdout + run.stderr)
        run.check_returncode()
        result[mode] = {}
        for name in ("read", "sample"):
            checked = subprocess.run(["spirv-val", "--target-env", "vulkan1.3",
                                      str(output / mode / f"{name}.spv")],
                                     capture_output=True, timeout=10)
            message = checked.stdout + checked.stderr
            (output / f"{mode}-{name}-validation.log").write_bytes(message)
            result[mode][name] = {"code": checked.returncode, "message": message.decode()}
            if mode == "before":
                if not checked.returncode or b"Vector access is out of bounds" not in message:
                    raise ValueError("the baseline did not reproduce the expected FMASK defect")
            else:
                checked.check_returncode()
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: baseline read/sample invalid; fixed read/sample valid. Evidence: {output}")


def prepare_layout():
    source = VARIANT / "users/baseline"
    target = LAYOUT / "user"
    if not source.is_dir() or target.exists():
        raise ValueError("need the preserved baseline snapshot and an uncreated layout user")
    with user_lock(source):
        before = file_manifest(source)
        subprocess.run(["cp", "-a", "--reflink=auto", str(source), str(target)], check=True)
        if file_manifest(target) != before:
            raise ValueError("layout snapshot verification failed")
        # Metadata 22 rejects 21 before reading its incompatible layouts. No file is
        # deleted or moved: this fourth variant also retains the complete old cache.
        (LAYOUT / "user-manifest.json").write_text(json.dumps(before, indent=2) + "\n")
    print(f"Layout variant prepared: {target}; original files preserved.")


def validate_layout():
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(LAYOUT) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = LAYOUT / f"validation-{stamp}-{os.getpid()}"
    output.mkdir()
    user = output / "user"
    user.mkdir(exist_ok=True)
    env["BB_GPU_USER_DIR"] = str(user)
    cache = VARIANT / "users/baseline/cache/CUSA08809_nodma"
    legacy = cache / "0x00000df3a2d7e682.meta"
    run = subprocess.run([str(LAYOUT / "shader-permutations-test"), str(legacy)],
                         env=env, capture_output=True, timeout=20)
    (output / "permutations.log").write_bytes(run.stdout + run.stderr)
    run.check_returncode()
    run = subprocess.run([str(LAYOUT / "fmask-shader-test"), str(output)],
                         env=env, capture_output=True, timeout=20)
    (output / "fmask.log").write_bytes(run.stdout + run.stderr)
    run.check_returncode()
    for name in ("read", "sample"):
        run = subprocess.run(["spirv-val", "--target-env", "vulkan1.3", str(output / f"{name}.spv")],
                             capture_output=True, timeout=10)
        (output / f"{name}-validation.log").write_bytes(run.stdout + run.stderr)
        run.check_returncode()
    print(f"PASS: permutation ownership, classification, metadata and FMASK SPIR-V. Evidence: {output}")


def run(mode):
    user = LAYOUT / "user" if mode == "layout" else VARIANT / "users" / mode
    if not user.is_dir():
        raise ValueError("prepare the isolated snapshots first: --prepare")
    info = json.loads(((LAYOUT if mode == "layout" else VARIANT) / "build-info.json").read_text())
    library = LAYOUT if mode == "layout" else VARIANT if mode == "fixed" else ROOT / "out/gpu"
    expected = info["fixed_library_sha256"] if mode in ("fixed", "layout") else info["baseline_library_sha256"]
    if sha(library / "libbbgpu.so") != expected:
        raise ValueError("renderer hash differs from the reviewed variant")
    env = os.environ.copy()
    load_ini(env)
    resolve_storage(env, user)
    for name in DIAGNOSTICS:
        env.pop(name, None)
    env.update(SOTC_RENDER_DIAG="0", SOTC_SYNC_DIAG="0", SOTC_FRAME_LOG="0", SOTC_GRAPHICS_DIAG="0",
               SOTC_CP_THREADS="1", SOTC_RECORD_THREAD="1", BB_DUMP_SHADERS="1",
               SOTC_FMASK_TRACE="1", SOTC_SHOT_COUNT="3",
               BB_FRAME_DUMP_TRIGGER=str(VARIANT / f"capture-{mode}"))
    env["LD_LIBRARY_PATH"] = str(library) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    command = prepared_command(env.get("SOTC_GAME_DIR") or ROOT.parent / "CUSA08809", user)
    print(f"Graphics test: {mode}; screenshots: {user / 'screenshots'}", flush=True)
    print(f"Request three adjacent frames: python3 tools/sotc_fmask_test.py --capture {mode}", flush=True)
    return play(command, env, user)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--validate", action="store_true")
    actions.add_argument("--prepare-layout", action="store_true")
    actions.add_argument("--validate-layout", action="store_true")
    actions.add_argument("--run", choices=MODES)
    actions.add_argument("--capture", choices=MODES)
    args = parser.parse_args()
    try:
        if args.prepare:
            prepare()
        elif args.validate:
            validate()
        elif args.prepare_layout:
            prepare_layout()
        elif args.validate_layout:
            validate_layout()
        elif args.run:
            return run(args.run)
        else:
            trigger = VARIANT / f"capture-{args.capture}"
            trigger.touch(exist_ok=True)
            print(f"Capture requested: {trigger}")
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"sotc: {error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
