#!/usr/bin/env python3
"""One RenderDoc experiment on the existing layout renderer; production stays untouched."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from sotc_fmask_test import LAYOUT, sha
from sotc_launch import (ROOT, DIAGNOSTICS, file_manifest, load_ini, play,
                         prepared_command, resolve_storage, user_lock)

OUTPUT = ROOT / "out/graphics-pixel"
HOOK = OUTPUT / "capture-hook.so"


def build():
    OUTPUT.mkdir(exist_ok=True)
    command = ["cc", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror",
               "-march=ivybridge", "-mno-avx2", "-mno-bmi", "-mno-bmi2",
               str(ROOT / "tools/sotc_renderdoc_hook.c"), "-o", str(HOOK), "-ldl", "-pthread"]
    subprocess.run(command, check=True)
    (OUTPUT / "build.json").write_text(json.dumps({"command": command, "sha256": sha(HOOK)}, indent=2))
    (OUTPUT / "CTestTestfile.cmake").write_text(
        f'add_test(pixel-capture-hook "{sys.executable}" "{ROOT / "tests/test_pixel_capture.py"}")\n'
        'set_tests_properties(pixel-capture-hook PROPERTIES TIMEOUT 30)\n')
    print(f"Built capture helper only: {HOOK}")


def run(dry_run=False):
    tool = shutil.which("renderdoccmd")
    if not dry_run:
        if not tool:
            raise ValueError("renderdoccmd missing. On the host: sudo pacman -S --needed renderdoc")
        if not os.environ.get("DISPLAY"):
            raise ValueError("DISPLAY missing: run in the host desktop with XWayland available")
        if not HOOK.is_file():
            raise ValueError("capture helper missing; run --build first")
        built = json.loads((OUTPUT / "build.json").read_text())
        if sha(HOOK) != built["sha256"]:
            raise ValueError("capture helper differs from build.json")
    info = json.loads((LAYOUT / "build-info.json").read_text())
    if sha(LAYOUT / "libbbgpu.so") != info["fixed_library_sha256"]:
        raise ValueError("layout renderer differs from the host-tested variant")
    user = OUTPUT / "user"
    if not dry_run and not user.exists():
        OUTPUT.mkdir(exist_ok=True)
        with user_lock(LAYOUT / "user"):
            original = file_manifest(LAYOUT / "user")
            subprocess.run(["cp", "-a", "--reflink=auto", str(LAYOUT / "user"), str(user)], check=True)
            if file_manifest(user) != original:
                raise ValueError("capture profile copy verification failed")
            (OUTPUT / "user-manifest.json").write_text(json.dumps(original, indent=2))
    if not dry_run and not (OUTPUT / "user-manifest.json").exists():
        raise ValueError("unverified capture profile; existing files have been preserved")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session = OUTPUT / f"capture-{stamp}-{os.getpid()}"
    env = os.environ.copy()
    load_ini(env)
    resolve_storage(env, user)
    for key in DIAGNOSTICS:
        env.pop(key, None)
    env.update(SOTC_RENDER_DIAG="0", SOTC_SYNC_DIAG="0", SOTC_FRAME_LOG="0",
               SOTC_GRAPHICS_DIAG="0", SOTC_CP_THREADS="1", SOTC_RECORD_THREAD="1",
               SOTC_VK_NAMES="1", BB_DUMP_SHADERS="1", SOTC_FMASK_TRACE="0",
               SDL_VIDEODRIVER="x11", SOTC_SHOT_COUNT="3",
               SOTC_PIXEL_TRIGGER=str(session / "trigger"),
               SOTC_PIXEL_OUTPUT=str(session / "wander"),
               BB_FRAME_DUMP_TRIGGER=str(session / "screenshot"))
    env["LD_LIBRARY_PATH"] = str(LAYOUT) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    env["LD_PRELOAD"] = str(HOOK) + (" " + env["LD_PRELOAD"] if env.get("LD_PRELOAD") else "")
    game = prepared_command(env.get("SOTC_GAME_DIR") or ROOT.parent / "CUSA08809", user)
    command = [tool or "renderdoccmd", "capture", "--wait-for-exit", "--capture-file",
               str(session / "wander"), *game]
    metadata = {"command": command, "renderer": str(LAYOUT / "libbbgpu.so"),
                "renderer_sha256": sha(LAYOUT / "libbbgpu.so"),
                "environment": {k: v for k, v in env.items() if k.startswith(
                    ("SOTC_", "BB_", "SDL_", "LD_", "VK_"))},
                "session": str(session), "user": str(user),
                "supervisor_pid": os.getpid(),
                "note": "Wrapper exit is renderdoccmd status, not proof of clean game exit. PNG request is near capture, not an exact frame pairing."}
    if dry_run:
        print(json.dumps(metadata, indent=2))
        return 0
    session.mkdir()
    (session / "capture.json").write_text(json.dumps(metadata, indent=2))
    # A separate session lock protects active.json throughout play(), which takes the profile lock.
    with user_lock(OUTPUT / "session-lock"):
        (OUTPUT / "active.json").write_text(json.dumps(metadata, indent=2))
        print(f"Capture directory: {session}\nWhen Wander is magenta, in another terminal:\n"
              "python3 tools/sotc_pixel_capture.py --capture", flush=True)
        return play(command, env, user)


def capture():
    info = json.loads((OUTPUT / "active.json").read_text())
    os.kill(info["supervisor_pid"], 0)
    session = Path(info["session"])
    # Once per session: bounded to three frames, not continuous logging/capturing.
    with (session / "requested").open("x") as marker:
        marker.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
    (session / "screenshot").touch()
    (session / "trigger").touch()
    print(f"Three frames requested. Keep camera still; wait for three .rdc files in {session}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--build", action="store_true")
    action.add_argument("--run", action="store_true")
    action.add_argument("--capture", action="store_true")
    action.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if args.build:
            build()
        elif args.capture:
            capture()
        else:
            return run(args.dry_run)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"sotc capture: {error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
