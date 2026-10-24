#!/usr/bin/env python3
"""sotc: where inside a function the time goes: profile_lines.py dump function [exe]. Every sampled
address (leaf and return addresses) whose inline chain passes through `function` is charged to
the line of `function` it came from (inclusive samples)."""
import collections, subprocess, sys
dump, wanted = sys.argv[1], sys.argv[2]
exe = sys.argv[3] if len(sys.argv) > 3 else 'out/bb-probe.exe'
rows, samples = [], 1
for line in open(dump, encoding='utf-8', errors='replace'):
    parts = line.split()
    if parts[0] == 'samples':
        samples = int(parts[1]); continue
    where = ' '.join(parts[:-2])
    if where.startswith('bb-probe.exe+'):
        rows.append((int(where.split('+')[1], 16), int(parts[-2]), int(parts[-1])))
addrs = [hex(0x140000000 + a) for a, _, _ in rows]
out = []
for i in range(0, len(addrs), 2000):
    out += subprocess.run(['llvm-symbolizer', f'--obj={exe}', '--functions=short'] + addrs[i:i+2000],
                          capture_output=True, text=True).stdout.strip().split('\n\n')
lines = collections.Counter()
for (a, leaf, inc), text in zip(rows, out):
    frames = text.split('\n')
    # pairs: function, file:line; innermost first. Charge to the frame just inside `wanted`.
    for k in range(0, len(frames) - 1, 2):
        if frames[k] == wanted:
            callee = frames[k - 2] if k >= 2 else '(self)'
            where = frames[k + 1].split('/')[-1]
            lines[f'{where:40s} -> {callee[:60]}'] += inc
            break
for key, n in lines.most_common(30):
    print(f'{100*n/samples:5.1f}%  {key}')
