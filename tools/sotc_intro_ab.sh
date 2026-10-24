#!/usr/bin/env bash
# sotc: A/B of the intro's river shot (~128 s, no input): out/intro-ab/<name>-N.png and a
# detail score of the water (std dev of a high-pass filter; ripples raise it).
# usage: tools/sotc_intro_ab.sh name [--env X=Y ...]
cd "$(dirname "$0")/.."
name=$1; shift
export SOTC_GAME_DIR=${SOTC_GAME_DIR:-"I:/EMULADORES/Playstation 4/JOGOS/Shadow Of The Colossus/CUSA08809"}
start=$(date +%s)
timeout 300 /c/PyBuild312/python.exe tools/sotc_play.py 132 --keep-save --cmdline out/water.cmdline --patches out/water.patches \
    --env BB_VBLANK_HZ=120 --log "out/intro-ab-$name.txt" "$@" 126:shot 128:shot 130:shot >/dev/null 2>&1
mkdir -p out/intro-ab
i=0
for f in $(find user/screenshots out/dump -name '*.png' -newermt "@$start" ! -name sheet.png 2>/dev/null | sort); do
    cp "$f" "out/intro-ab/$name-$i.png"; i=$((i+1))
done
/c/PyBuild312/python.exe - "$name" <<'PY'
import sys, glob
from PIL import Image, ImageFilter, ImageStat
name = sys.argv[1]
for f in sorted(glob.glob(f'out/intro-ab/{name}-*.png')):
    im = Image.open(f).convert('L').crop((1000, 600, 1900, 960))
    hp = Image.eval(im.filter(ImageFilter.GaussianBlur(3)), lambda v: v)
    from PIL import ImageChops
    d = ImageChops.difference(im, hp)
    print(name, f.split('-')[-1], 'mean %.1f detail %.2f' % (ImageStat.Stat(im).mean[0], ImageStat.Stat(d).mean[0]))
PY
