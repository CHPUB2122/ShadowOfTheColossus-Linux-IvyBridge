# Minimal GCN (GFX7) walker: instruction boundaries + which ones touch VCC. usage: gcnscan.py file.bin [from] [to]
import struct, sys
d = open(sys.argv[1], 'rb').read()
w = struct.unpack('<%dI' % (len(d) // 4), d)
lo = int(sys.argv[2]) if len(sys.argv) > 2 else 0
hi = int(sys.argv[3]) if len(sys.argv) > 3 else len(w)
VOP2 = {0:'cndmask',3:'add_f32',4:'sub_f32',5:'subrev_f32',8:'mul_f32',37:'add_i32',38:'sub_i32',39:'subrev_i32',40:'addc_u32',41:'subb_u32',42:'subbrev_u32',31:'mac_f32',32:'madmk',33:'madak'}
def lit(s): return s == 0xff
i = 0
while i < len(w):
    x = w[i]; n = 1; desc = ''
    if x >> 30 == 0b10 and (x >> 28) != 0b1011 and (x >> 23) & 0x1ff not in (0x17d, 0x17e, 0x17f) and (x>>23) != 0x17d:
        # SOP2: 10xxxxxxx
        op = (x >> 23) & 0x7f; s0 = x & 0xff; s1 = (x >> 8) & 0xff; dst = (x >> 16) & 0x7f
        n += 1 if (lit(s0) or lit(s1)) else 0
        desc = 'SOP2 op%d s%d <- %d,%d' % (op, dst, s0, s1)
        if dst in (106, 107) or s0 in (106, 107) or s1 in (106, 107): desc += '  *VCC*'
    elif x >> 28 == 0b1011 and (x >> 23) & 0x1f not in ():
        top9 = x >> 23
        if top9 == 0x17d:   # SOP1
            op = (x >> 8) & 0xff; s0 = x & 0xff; dst = (x >> 16) & 0x7f; n += 1 if lit(s0) else 0
            desc = 'SOP1 op%d s%d <- %d' % (op, dst, s0)
            if dst in (106, 107) or s0 in (106, 107): desc += '  *VCC*'
        elif top9 == 0x17e:  # SOPC
            s0 = x & 0xff; s1 = (x >> 8) & 0xff; n += 1 if (lit(s0) or lit(s1)) else 0; desc = 'SOPC'
            if s0 in (106, 107) or s1 in (106, 107): desc += '  *VCC*'
        elif top9 == 0x17f:  # SOPP
            desc = 'SOPP op%d imm%d' % ((x >> 16) & 0x7f, x & 0xffff)
        else:  # SOPK
            desc = 'SOPK op%d s%d imm%#x' % ((x >> 23) & 0x1f, (x >> 16) & 0x7f, x & 0xffff)
            if (x >> 16) & 0x7f in (106, 107): desc += '  *VCC*'
    elif x >> 25 == 0b0111111:  # VOP1
        n += 1 if lit(x & 0x1ff) else 0; desc = 'VOP1 op%d' % ((x >> 9) & 0xff)
    elif x >> 25 == 0b0111110:  # VOPC -> writes VCC
        n += 1 if lit(x & 0x1ff) else 0; desc = 'VOPC op%d  *WRITES VCC*' % ((x >> 17) & 0xff)
    elif x >> 31 == 0:  # VOP2
        op = (x >> 25) & 0x3f; n += 1 if (lit(x & 0x1ff) or op in (32, 33)) else 0
        desc = 'VOP2 %s' % VOP2.get(op, 'op%d' % op)
        if op in (37, 38, 39, 40, 41, 42): desc += '  *WRITES VCC (carry)*'
        if op in (0, 40, 41, 42): desc += '  *READS VCC*'
    elif x >> 26 == 0b110100:  # VOP3
        op = (x >> 17) & 0x1ff; y = w[i + 1]; n = 2
        desc = 'VOP3 op%d dst%d src0 %d src1 %d src2 %d' % (op, x & 0xff, y & 0x1ff, (y >> 9) & 0x1ff, (y >> 18) & 0x1ff)
        if op < 256: desc += '  (cmp -> s%d)' % (x & 0xff)
        if 293 <= op <= 298: desc += '  (vop3b carry sdst s%d)' % ((x >> 8) & 0x7f)
        if any(v in (106, 107) for v in (x & 0xff, y & 0x1ff, (y >> 9) & 0x1ff, (y >> 18) & 0x1ff)): desc += '  *VCC*'
    elif x >> 27 == 0b11000:  # SMRD
        desc = 'SMRD'
    elif x >> 26 == 0b110010:  # VINTRP
        desc = 'VINTRP'
    elif x >> 26 in (0b110110, 0b111000, 0b111010, 0b111100, 0b111110):
        n = 2; desc = {0b110110:'DS',0b111000:'MUBUF',0b111010:'MTBUF',0b111100:'MIMG',0b111110:'EXP'}[x >> 26]
    else:
        desc = '??'
    if lo <= i < hi and ('VCC' in desc or len(sys.argv) > 4):
        print(i, ' '.join('%08x' % w[j] for j in range(i, min(i + n, len(w)))), desc)
    i += n
