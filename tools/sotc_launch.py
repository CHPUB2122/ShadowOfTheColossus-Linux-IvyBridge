#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Play the existing native Linux build, without preparing or replacing artifacts.

Production: bash run.sh --game /path/to/CUSA08809
Diagnostics: python3 tools/sotc_render_debug.py --no-gdb --game /path/to/CUSA08809
"""
import argparse
from contextlib import contextmanager
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ("bb-probe", "boot-linked.bin", "content.bin", "sotc-cpu.bin",
             "patches.bin", "cmdline.bin")
DIAGNOSTICS = ("SOTC_RENDER_DIAG", "SOTC_SYNC_DIAG", "SOTC_FRAME_LOG",
               "SOTC_GRAPHICS_DIAG", "SOTC_PASS_TRACE", "SOTC_THREAD_IDS",
               "SOTC_SHOT_COUNT", "SOTC_FPS", "SOTC_CMD_STATS")


def load_ini(env, root=ROOT):
    config = root / "sotc.ini"
    if config.is_file():
        for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith(("#", ";")) and "=" in line:
                name, value = line.split("=", 1)
                env.setdefault(name.strip(), value.strip())


def project_path(value, root=ROOT):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def resolve_storage(env, requested=None, root=ROOT):
    """One path for guest saves and the GPU library's pre-main static initializers."""
    sotc, gpu = env.get("SOTC_USER_DIR"), env.get("BB_GPU_USER_DIR")
    if requested is None and sotc and gpu and project_path(sotc, root) != project_path(gpu, root):
        raise ValueError("SOTC_USER_DIR and BB_GPU_USER_DIR name different profiles; "
                         "select one explicitly with --user (no saves are moved)")
    user = project_path(requested or sotc or gpu or root / "user", root)
    env["SOTC_USER_DIR"] = env["BB_GPU_USER_DIR"] = str(user)
    env["BB_CONFIG"] = str(project_path(env.get("BB_CONFIG") or root / "sotc.ini", root))
    return user


def prepared_command(game, user, root=ROOT, cmdline=None, timeout=None):
    game = project_path(game, root)
    if not (game / "eboot.bin").is_file():
        raise ValueError(f"game directory has no eboot.bin: {game}")
    if user == game or game in user.parents:
        raise ValueError("the user directory must be outside the original game directory")
    out = root / "out"
    for name in ARTIFACTS:
        if not (out / name).is_file():
            raise ValueError(f"missing prepared artifact: {out / name}; "
                             "build/prepare explicitly before playing")
    command = [str(out / "bb-probe"), str(out / "boot-linked.bin")]
    for option, name in zip(("--content-profile", "--sotc-cpu", "--patches", "--sotc-cmdline"),
                            ARTIFACTS[2:]):
        command += [option, str(cmdline if name == "cmdline.bin" and cmdline else out / name)]
    command += ["--app0", str(game), "--user", str(user)]
    # Normal sessions explicitly opt out of the old loader's 10-second test deadline,
    # including when using a preserved binary built before the default was corrected.
    command += ["--timeout", str(0 if timeout is None else timeout)]
    return command


@contextmanager
def user_lock(user):
    """Prevent the production and diagnostic launchers from writing one profile concurrently."""
    import fcntl
    user.mkdir(parents=True, exist_ok=True)
    with (user / ".sotc-session.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(f"another session is using {user}; close it first") from error
        # Children also hold the lock if the supervisor is terminated unexpectedly.
        yield lock.fileno()


def file_manifest(directory):
    result = {}
    if directory.is_dir():
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                result[str(path.relative_to(directory))] = {
                    "size": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


def shell_status(code):
    return 128 - code if code < 0 else code


def termination(code):
    code = shell_status(code)
    return {0: "exit", 139: "sigsegv", 142: "sigalrm", 130: "sigint", 143: "sigterm"}.get(code, "error")


def play(command, env, user, root=ROOT):
    with user_lock(user) as lock_fd:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        logs = root / "out/logs" / f"play-{stamp}-{os.getpid()}"
        logs.mkdir(parents=True)
        before = file_manifest(user / "savedata")
        if (user / "savedata").is_dir():
            shutil.copytree(user / "savedata", logs / "savedata-before", symlinks=True)
            if file_manifest(logs / "savedata-before") != before:
                raise ValueError(f"save backup verification failed: {logs}")
        metadata = {"command": command, "cwd": str(root), "user": str(user),
                    "mode": "benchmark" if env.get("SOTC_FRAME_LOG") == "1" else "production",
                    "environment": {k: v for k, v in env.items()
                                    if k.startswith(("SOTC_", "BB_", "VK_", "SDL_"))},
                    "sha256": {name: hashlib.sha256((root / "out" / name).read_bytes()).hexdigest()
                               for name in (*ARTIFACTS, "gpu/libbbgpu.so")},
                    "saves_before": before}
        (logs / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"SotC: {user}\nLog: {logs / 'game.log'}", flush=True)
        started = time.monotonic()
        with (logs / "game.log").open("xb") as output:
            process = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, pass_fds=(lock_fd,))
            def forward(sig, _frame):
                if process.poll() is None:
                    try:
                        process.send_signal(sig)
                    except ProcessLookupError:
                        pass
            previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
            try:
                code = process.wait()
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
        after = file_manifest(user / "savedata")
        result = {"returncode": code, "shell_status": shell_status(code), "termination": termination(code),
                  "seconds": time.monotonic() - started, "saves_after": after,
                  "changed_save_files": sorted(k for k in before.keys() | after.keys()
                                               if before.get(k) != after.get(k))}
        (logs / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(f"Exit: {shell_status(code)} ({result['termination']})", flush=True)
        if code:
            print("\n".join((logs / "game.log").read_text(errors="replace").splitlines()[-20:]), file=sys.stderr)
        return shell_status(code)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path)
    parser.add_argument("--user", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="show command/settings without starting or writing saves")
    parser.add_argument("--benchmark", action="store_true",
                        help="opt in to existing per-frame timing only; no session deadline")
    args = parser.parse_args(argv)
    env = os.environ.copy()
    load_ini(env)
    try:
        user = resolve_storage(env, args.user)
        command = prepared_command(args.game or env.get("SOTC_GAME_DIR") or env.get("BB_GAME_DIR")
                                   or ROOT.parent / "CUSA08809", user)
        for name in DIAGNOSTICS:
            # Some older diagnostics check presence, so NAME=0 still enables them.
            env.pop(name, None)
        for name in ("SOTC_RENDER_DIAG", "SOTC_SYNC_DIAG", "SOTC_FRAME_LOG", "SOTC_GRAPHICS_DIAG"):
            env[name] = "0"
        env.pop("BB_FRAME_DUMP_TRIGGER", None)
        env.pop("SOTC_PROFILE", None)
        # Production uses both normal renderer threads. The diagnostic launcher
        # continues to honor explicit threading overrides for experiments.
        env["SOTC_CP_THREADS"] = env["SOTC_RECORD_THREAD"] = "1"
        if args.benchmark:
            env["SOTC_FRAME_LOG"] = "1"
        if args.dry_run:
            print(json.dumps({"command": command, "cwd": str(ROOT), "user": str(user),
                              "environment": {k: v for k, v in env.items()
                                              if k.startswith(("SOTC_", "BB_", "VK_", "SDL_"))}}, indent=2))
            return 0
        return play(command, env, user)
    except (ValueError, OSError) as error:
        parser.exit(1, f"sotc: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
