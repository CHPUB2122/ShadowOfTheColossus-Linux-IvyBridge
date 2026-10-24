#!/usr/bin/env python3
"""sotc: diagnose existing prepared Linux artifacts without rebuilding/repreparing.

GDB counts rendering boundaries and captures timer operands at the watchdog.
--no-gdb instead preserves /proc samples and the loader's signal-frame dump.
Original game files, previous logs and shader caches are never removed.
"""
import argparse
import ctypes
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import time
from sotc_graphics_debug import PROFILES, check_profile, make_profile, sample_cvars, validate_prepared
from sotc_launch import (load_ini, resolve_storage, prepared_command, user_lock,
                         file_manifest, shell_status)

ROOT = Path(__file__).resolve().parent.parent


def render_counters(text):
    snapshots = []
    final = {}
    for line in text.splitlines():
        if line.startswith("SOTC RENDER DIAG "):
            snapshots.append({k: int(v, 0) for k, v in re.findall(r"(\w+)=(0x[0-9a-f]+|\d+)", line)})
        match = re.fullmatch(r"SOTC DIAG (\w+)=([0-9a-f]{16})", line)
        if match:
            final[match[1]] = int(match[2], 16)
    return {"periodic": snapshots, "watchdog": final}


def screenshot_info(path):
    result = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    try:
        from PIL import Image, ImageStat
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            result.update(size=list(rgb.size), mean_rgb=ImageStat.Stat(rgb).mean,
                          all_black=all(hi == 0 for lo, hi in rgb.getextrema()))
    except (ImportError, OSError):
        pass
    return result


def sample_stacks(pid, tasks, output, elapsed):
    # tgkill selects only threads in this test process. SIGUSR2 invokes the
    # loader's existing read-only dump; it does not unblock waits or inject input.
    libc = ctypes.CDLL(None, use_errno=True)
    tgkill = libc.tgkill
    tgkill.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    tgkill.restype = ctypes.c_int
    names = ("shadPS4:GpuDraw", "shadPS4:GpuComm", "Game Render", "RenderFlip",
             "Shadow Game Upd", "Resource Loadin")
    for task_pid, tid, name in tasks:
        if task_pid == pid and (tid == pid or name.startswith(names)):
            os.write(output.fileno(), f"SOTC STACK SAMPLE elapsed={elapsed:.3f} tid={tid} name={name}\n".encode())
            if tgkill(pid, tid, signal.SIGUSR2):
                os.write(output.fileno(), f"SOTC STACK SAMPLE errno={ctypes.get_errno()}\n".encode())
            time.sleep(0.03)


def main():
    defaults = os.environ.copy()
    load_ini(defaults)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=defaults.get("SOTC_GAME_DIR"),
                        required=not defaults.get("SOTC_GAME_DIR"))
    parser.add_argument("--user", type=Path)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--shot-interval", type=float, default=10,
                        help="rearm capture at this interval in seconds; 0 disables periodic shots")
    parser.add_argument("--stack-interval", type=float, default=20,
                        help="sample selected threads without GDB at this interval; 0 disables it")
    parser.add_argument("--no-gdb", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--graphics-profile", choices=PROFILES,
                        help="isolated engine CVars; keeps existing patches and cmdline.bin")
    parser.add_argument("--graphics-diag", action="store_true",
                        help="sample shader/resource/attachment bindings and effective engine CVars")
    args = parser.parse_args()
    if not 10 <= args.timeout <= 600:
        parser.error("--timeout must be between 10 and 600 seconds")
    if args.shot_interval < 0 or args.stack_interval < 0:
        parser.error("capture intervals must be nonnegative")
    prepared = ["boot-linked.bin", "content.bin", "sotc-cpu.bin", "patches.bin", "cmdline.bin"]
    required = [ROOT / "out" / name for name in ["bb-probe", *prepared]]
    for path in required:
        if not path.is_file():
            parser.error(f"missing existing artifact: {path}; use the project's existing launcher first")
    env = defaults
    try:
        user = resolve_storage(env, args.user)
    except ValueError as error:
        parser.error(str(error))
    game = args.game.resolve()
    if not (game / "eboot.bin").is_file():
        parser.error(f"game directory has no eboot.bin: {game}")
    if user == game or game in user.parents:
        parser.error("--user must be outside the original game directory")
    if not args.no_gdb and not shutil.which("gdb"):
        parser.error("gdb is unavailable; use --no-gdb for watchdog and /proc diagnostics")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logs = ROOT / "out" / "logs" / f"render-{stamp}-{os.getpid()}"
    logs.mkdir(parents=True)
    graphics_profile = None
    cmdline = ROOT / "out/cmdline.bin"
    if args.graphics_profile:
        cmdline = logs / "cmdline.bin"
        try:
            graphics_profile = make_profile(ROOT / "out/boot-linked.bin", ROOT / "out/cmdline.bin",
                                            cmdline, args.graphics_profile)
        except (ValueError, OSError) as error:
            parser.error(str(error))
    if args.graphics_diag and not args.graphics_profile:
        # Sampling is only enabled after the exact prepared layout is validated.
        try:
            validate_prepared(ROOT / "out/boot-linked.bin")
        except (ValueError, OSError) as error:
            parser.error(str(error))
    command = prepared_command(game, user, cmdline=cmdline, timeout=args.timeout)
    if not args.no_gdb:
        command = [shutil.which("gdb"), "--batch", "--nx", "--quiet", "-ex",
                   "source " + str(ROOT / "tools" / "sotc_render_gdb.py"), "--args", *command]
    env["BB_FRAME_DUMP_TRIGGER"] = str(logs / "capture-trigger")
    env["SOTC_SHOT_COUNT"] = "3"
    env.setdefault("BB_CONFIG", str(ROOT / "sotc.ini"))
    env.setdefault("SOTC_THREAD_IDS", "1")
    env.setdefault("SOTC_RENDER_DIAG", "1")
    env.setdefault("SOTC_SYNC_DIAG", "1")
    env.setdefault("SOTC_FRAME_LOG", "30")
    if args.graphics_diag:
        env["SOTC_GRAPHICS_DIAG"] = "1"
        env.setdefault("SOTC_PASS_TRACE", "1")
    metadata = {"command": command, "gdb": not args.no_gdb,
                "graphics_profile": graphics_profile,
                "note": "--timeout is an absolute run deadline, not a no-progress detector.",
                "shot_interval": args.shot_interval, "stack_interval": args.stack_interval,
                "gpu_devices": sorted(str(p) for p in Path("/dev/dri").glob("*")),
                "sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in [*required, ROOT / "out/gpu/libbbgpu.so"]},
                "environment": {k: v for k, v in env.items() if k.startswith(("SOTC_", "BB_", "VK_", "SDL_"))}}
    if graphics_profile:
        metadata["sha256"][str(cmdline.relative_to(ROOT))] = hashlib.sha256(cmdline.read_bytes()).hexdigest()
    (logs / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
    for name, options in (("git-status.txt", ["status", "--short", "--branch"]),
                          ("git-diff.patch", ["diff", "--binary", "HEAD"])):
        (logs / name).write_bytes(subprocess.check_output(["git", *options], cwd=ROOT))
    print(f"Diagnostics: {logs}", flush=True)
    if args.dry_run:
        print("Dry run: no game/debugger launched.")
        return 0
    previous_screenshots = set((user / "screenshots").glob("*.png"))
    (logs / "capture-trigger").touch(exist_ok=False)
    with user_lock(user) as lock_fd, (logs / "game.log").open("x") as output:
        before = file_manifest(user / "savedata")
        if (user / "savedata").is_dir():
            shutil.copytree(user / "savedata", logs / "savedata-before", symlinks=True)
            if file_manifest(logs / "savedata-before") != before:
                raise ValueError(f"save backup verification failed: {logs}")
        metadata["saves_before"] = before
        (logs / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   start_new_session=True, pass_fds=(lock_fd,))
        started = time.monotonic()
        sample = 0
        next_shot, next_stack = args.shot_interval, args.stack_interval
        captures = []
        graphics_samples = []
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed >= sample * 5:
                    # GDB is the parent; only inspect tasks belonging to this run.
                    pids = [process.pid]
                    if not args.no_gdb:
                        try:
                            children = Path(f"/proc/{process.pid}/task/{process.pid}/children").read_text()
                            pids += [int(p) for p in children.split()]
                        except OSError:
                            pass
                    lines = [f"elapsed={elapsed:.3f}\n"]
                    task_names = []
                    for pid in pids:
                        proc = Path(f"/proc/{pid}")
                        try:
                            (logs / f"maps-{sample}-{pid}.txt").write_text((proc / "maps").read_text())
                            for entry in ("status", "io", "smaps_rollup"):
                                try:
                                    (logs / f"{entry}-{sample}-{pid}.txt").write_text((proc / entry).read_text())
                                except OSError:
                                    pass
                            for task in sorted((proc / "task").iterdir()):
                                name = (task / 'comm').read_text().strip()
                                task_names.append((pid, int(task.name), name))
                                lines.append(f"pid={pid} tid={task.name} name={name} "
                                             f"wchan={(task/'wchan').read_text().strip()} stat={(task/'stat').read_text().strip()}\n")
                        except OSError as error:
                            lines.append(f"pid={pid}: {error}\n")
                    (logs / f"tasks-{sample}.txt").write_text("".join(lines))
                    system = []
                    for entry in ("meminfo", "pressure/memory", "pressure/io"):
                        try:
                            system.append(entry + "\n" + Path("/proc", entry).read_text())
                        except OSError:
                            pass
                    (logs / f"system-{sample}.txt").write_text("\n".join(system))
                    if args.graphics_profile or args.graphics_diag:
                        # The loader is the direct child in --no-gdb mode. Reading
                        # /proc memory may be denied with GDB; report that, never inject writes.
                        guest_pid = pids[-1]
                        snapshot = sample_cvars(guest_pid, (logs / "game.log").read_bytes())
                        snapshot["seconds"] = elapsed
                        graphics_samples.append(snapshot)
                        (logs / "graphics-cvars.json").write_text(json.dumps(graphics_samples, indent=2) + "\n")
                    if (args.no_gdb and args.stack_interval and elapsed >= next_stack
                            and b"Image at " in (logs / "game.log").read_bytes()):
                        sample_stacks(process.pid, task_names, output, elapsed)
                        next_stack = elapsed + args.stack_interval
                    sample += 1
                if args.shot_interval and elapsed >= next_shot:
                    trigger = logs / "capture-trigger"
                    pending = trigger.exists()
                    if not pending:
                        trigger.touch(exist_ok=False)
                    captures.append({"seconds": elapsed, "previous_trigger_still_pending": pending})
                    next_shot = elapsed + args.shot_interval
                if elapsed > args.timeout + 30:
                    (logs / "external-timeout.txt").write_text("Debugger/loader exceeded watchdog plus 30 seconds.\n")
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            os.killpg(process.pid, signal.SIGTERM)
        finally:
            code = process.wait()
        after = file_manifest(user / "savedata")
    text = (logs / "game.log").read_text(errors="replace")
    watchdog = "STOP: watchdog timeout" in text
    termination = "deadline" if watchdog else "exit" if code == 0 else "error"
    if (logs / "external-timeout.txt").exists():
        termination = "external-timeout"
    result = {"returncode": code, "seconds": time.monotonic() - started,
              "termination": termination, "absolute_deadline_seconds": args.timeout,
              "watchdog_dump": watchdog, "render_counters": render_counters(text),
              "graphics_profile": graphics_profile, "graphics_cvars": graphics_samples,
              "graphics_profile_check": check_profile(graphics_profile, graphics_samples),
              "saves_after": after,
              "changed_save_files": sorted(k for k in before.keys() | after.keys()
                                           if before.get(k) != after.get(k)),
              "capture_requests": captures,
              "new_screenshots": [screenshot_info(p) for p in sorted(
                  set((user / "screenshots").glob("*.png")) - previous_screenshots)]}
    (logs / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Exit: {code}; log: {logs / 'game.log'}")
    if graphics_profile:
        print(f"Graphics profile {graphics_profile['name']}: {result['graphics_profile_check']['status']}")
    print("A presenter call alone does not prove a rendered game frame. Check the captured PNGs and flip completion.")
    return shell_status(code)


if __name__ == "__main__":
    raise SystemExit(main())
