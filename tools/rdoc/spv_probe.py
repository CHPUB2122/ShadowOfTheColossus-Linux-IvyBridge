# Make probe variants of a SPIR-V asm: replace the 4 stores into frag_color0 with given f32 ids.
# usage: spv_probe.py in.spvasm out.spvasm id0 id1 id2 id3
import sys, re
src, dst, ids = sys.argv[1], sys.argv[2], sys.argv[3:7]
L = open(src).read().split('\n')
chain = {}
for i, l in enumerate(L):
    m = re.match(r'\s*(%\w+) = OpAccessChain %\w+ %frag_color0 %u32_id_(\d)', l)
    if m: chain[m.group(1)] = int(m.group(2))
n = 0
for i, l in enumerate(L):
    m = re.match(r'(\s*OpStore )(%\w+) (%\w+)$', l)
    if m and m.group(2) in chain:
        L[i] = m.group(1) + m.group(2) + ' %' + ids[chain[m.group(2)]].lstrip('%_'); n += 1
open(dst, 'w').write('\n'.join(L))
print('replaced', n)
