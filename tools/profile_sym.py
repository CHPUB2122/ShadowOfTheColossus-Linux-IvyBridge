#!/usr/bin/env python3
"""sotc: symbolize a SOTC_PROFILE report (bb-probe.exe offsets) from a log: profile_sym.py log [exe]"""
import re, subprocess, sys
text = open(sys.argv[1], encoding='utf-8', errors='replace').read()
start = text.find('SOTC profile of')
lines = text[start:].splitlines()[:150]
exe = sys.argv[2] if len(sys.argv) > 2 else 'out/gpu/bb-probe.exe'
offs = sorted({m for l in lines for m in re.findall(r'bb-probe\.exe\+(0x[0-9a-f]+)', l)})
out = subprocess.run(['llvm-symbolizer', f'--obj={exe}', '--no-inlines', '--functions=short',
                      *[hex(0x140000000 + int(o, 16)) for o in offs]], capture_output=True, text=True).stdout.split('\n\n')
sym = {o: r.strip().split('\n')[0][:100] for o, r in zip(offs, out)}
for l in lines:
    m = re.search(r'bb-probe\.exe\+(0x[0-9a-f]+)', l)
    print(l.rstrip() + ('   ' + sym.get(m.group(1), '') if m else ''))
