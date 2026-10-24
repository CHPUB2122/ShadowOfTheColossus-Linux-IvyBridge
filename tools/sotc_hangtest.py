#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""sotc: repeat a short boot and count black-screen hangs.

    python tools/sotc_hangtest.py RUNS [NAME=VALUE ...]

Each run starts the game (tools/sotc_play.py), dumps the presented frame 40 s after the main
loop and counts it as a hang when that frame is black or missing. The environment pairs go to
the game. A hang keeps its log as out/hang-N.txt (with thread stacks).
"""
import glob
import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parent.parent


def main():
    runs = int(sys.argv[1])
    env = [arg for pair in sys.argv[2:] if pair != '--fresh' for arg in ('--env', pair)]
    if '--fresh' in sys.argv[2:]:
        env.append('--fresh')
    hangs = 0
    for i in range(1, runs + 1):
        subprocess.run([sys.executable, str(ROOT / 'tools' / 'sotc_play.py'), '50', '--from-main-loop', *env,
                        '40:shot', '45:stacks'], cwd=ROOT, stdout=subprocess.DEVNULL)
        frames = sorted(glob.glob(str(ROOT / 'out' / 'dump' / 'output_*.png')))
        brightness = [sum(ImageStat.Stat(Image.open(f)).mean) for f in frames]
        hung = not brightness or max(brightness) <= 5
        hangs += hung
        if hung:
            shutil.copy(ROOT / 'out' / 'run.txt', ROOT / 'out' / f'hang-{i}.txt')
        print(f'run {i}: {"HANG" if hung else "ok"} {[round(b) for b in brightness]}', flush=True)
    print(f'{hangs}/{runs} hangs with {" ".join(sys.argv[2:]) or "defaults"}')


if __name__ == '__main__':
    main()
