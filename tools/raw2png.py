#!/usr/bin/env python3
"""sotc: convert BB_FRAME_DUMP_TRIGGER dumps (raw 32-bit pixels, name_NNN_WxH.raw) to PNG."""
import re
import sys
from pathlib import Path
from PIL import Image

for path in map(Path, sys.argv[1:]):
    w, h = map(int, re.search(r'_(\d+)x(\d+)\.raw$', path.name).groups())
    data = path.read_bytes()[:w * h * 4]
    Image.frombuffer('RGBA', (w, h), data, 'raw', 'BGRA', 0, 1).convert('RGB').save(path.with_suffix('.png'))
    print(path.with_suffix('.png'))
