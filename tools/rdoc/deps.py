import re, sys
L=open(sys.argv[1]).read().splitlines()
defs={}
for i,l in enumerate(L):
    m=re.match(r'\s*\S+ (_\d+) = (.*);',l)
    if m: defs[m.group(1)]=(i+1,m.group(2))
# map sample result -> image
samp={}
for v,(ln,e) in defs.items():
    if 'ImageSample' in e or 'ImageFetch' in e:
        img=None
        for k in range(ln-1,ln-8,-1):
            mm=re.search(r'\*(fs_img\d+|vs_img\d+)',L[k-1])
            if mm: img=mm.group(1); break
        samp[v]=(ln,img)
def reach(root):
    seen=set(); st=[root]
    while st:
        v=st.pop()
        if v in seen or v not in defs: continue
        seen.add(v); st+=re.findall(r'_\d+',defs[v][1])
    return seen
for root in sys.argv[2:]:
    r=reach(root)
    print(root, 'samples:', sorted({(samp[v][1],samp[v][0]) for v in r if v in samp}, key=lambda x:x[1]))
    print('  srt dwords:', sorted({int(m) for v in r for m in re.findall(r'srt_flatbuf\.data\[(\d+)\]', defs[v][1])})[:80])
