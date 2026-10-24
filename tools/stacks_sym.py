#!/usr/bin/env python3
"""sotc: symbolize a STACKS dump (BB_STACKS_TRIGGER) of a log: stacks_sym.py log [thread-name-filter...]"""
import re, subprocess, sys
text = open(sys.argv[1], encoding='utf-8', errors='replace').read()
block = text[text.find('STACKS: begin'):text.find('STACKS: end')]
lines = [l for l in block.splitlines() if l.startswith(('thread', '    '))]
addrs = sorted({m for l in lines for m in re.findall(r'exe (0x[0-9a-f]+)', l)})
out = subprocess.run(['llvm-addr2line', '-f', '-C', '-e', 'out/bb-probe.exe', *addrs], capture_output=True, text=True).stdout.splitlines()
sym = {a: out[2 * i][:140] for i, a in enumerate(addrs)}
filters = sys.argv[2:]
show = False
for l in lines:
    if l.startswith('thread'):
        show = not filters or any(f in l for f in filters)
        if show: print(l[:110])
    elif show:
        m = re.search(r'exe (0x[0-9a-f]+)', l)
        print('   ', sym[m.group(1)] if m else l.strip())
