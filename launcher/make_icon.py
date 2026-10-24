# SPDX-License-Identifier: GPL-2.0-or-later
"""sotc: draws the launcher icon (original art, no game assets): make_icon.py <out without extension>

A colossus face close up: a stone mask with moss and cracks, framed by its shaggy fur, glowing
blue eyes and the glowing sigil on its brow. Plain shapes, readable down to 16x16."""
from PIL import Image, ImageDraw, ImageFilter
import math
import random
import sys

S = 1024
random.seed(11)
CX, CY = 512, 560


def glow(img, draw_fn, blur):
    layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    return Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(blur)))


def sigil(d, cx, cy, r, color, width):
    """A colossus-like rune: a vertical stroke, a crossbar, a cup and side ticks."""
    d.line([(cx, cy - r), (cx, cy + r)], fill=color, width=width)
    d.line([(cx - r * 0.7, cy - r * 0.35), (cx + r * 0.7, cy - r * 0.35)], fill=color, width=width)
    d.arc([cx - r * 0.75, cy - r * 0.3, cx + r * 0.75, cy + r * 0.9], 0, 180, fill=color, width=width)
    for s in (-1, 1):
        d.line([(cx + s * r * 0.95, cy - r * 0.7), (cx + s * r * 0.95, cy - r * 0.05)], fill=color, width=width)


# Background: dark stormy blue-grey, lighter in the middle
art = Image.new('RGBA', (S, S), (26, 30, 36, 255))
art = glow(art, lambda d: d.ellipse([140, 160, 884, 980], fill=(84, 88, 92, 255)), 160)

# Fur: curved strands radiating from the face, dark browns with lighter tips
fur = Image.new('RGBA', (S, S), (0, 0, 0, 0))
fd = ImageDraw.Draw(fur)
for _ in range(1600):
    a = random.uniform(0, 2 * math.pi)
    r0 = random.uniform(300, 400)
    length = random.uniform(90, 200)
    bend = random.uniform(-0.35, 0.35)
    pts = []
    for k in range(6):
        t = k / 5
        ang = a + bend * t
        rr = r0 + length * t
        pts.append((CX + math.cos(ang) * rr, CY + math.sin(ang) * rr * 0.92))
    shade = random.randint(18, 46)
    color = (shade + 8, shade + 4, shade, 255)
    fd.line(pts, fill=color, width=random.randint(5, 11), joint='curve')
    if random.random() < 0.25:  # a lighter tip
        fd.line(pts[-2:], fill=(shade + 40, shade + 34, shade + 26, 255), width=4)
art = Image.alpha_composite(art, fur.filter(ImageFilter.GaussianBlur(1.2)))

# Stone mask: base, lit upper plate, side plates (shadow), lower jaw
d = ImageDraw.Draw(art)
mask_outline = [(300, 300), (512, 214), (724, 300), (790, 520), (728, 800), (512, 905), (296, 800), (234, 520)]
d.polygon(mask_outline, fill=(82, 78, 72))
d.polygon([(330, 330), (512, 258), (694, 330), (722, 470), (512, 432), (302, 470)], fill=(112, 107, 98))
d.polygon([(260, 540), (440, 590), (420, 772), (318, 760)], fill=(62, 59, 55))
d.polygon([(764, 540), (584, 590), (604, 772), (706, 760)], fill=(62, 59, 55))
d.polygon([(420, 790), (604, 790), (580, 880), (512, 900), (444, 880)], fill=(70, 66, 61))
# moss patches
moss = Image.new('RGBA', (S, S), (0, 0, 0, 0))
md = ImageDraw.Draw(moss)
for (x, y, w, h) in [(330, 330, 120, 40), (600, 300, 100, 34), (280, 600, 60, 90), (680, 620, 54, 80), (470, 860, 90, 30)]:
    md.ellipse([x, y, x + w, y + h], fill=(86, 104, 58, 90))
art = Image.alpha_composite(art, moss.filter(ImageFilter.GaussianBlur(14)))
d = ImageDraw.Draw(art)
# cracks
for path in [[(360, 360), (392, 402), (420, 420)], [(650, 370), (622, 420), (600, 446)],
             [(470, 770), (500, 812), (520, 858)], [(560, 630), (590, 668), (612, 700)],
             [(300, 520), (336, 540)], [(724, 520), (690, 540)]]:
    d.line(path, fill=(42, 40, 38), width=7, joint='curve')
# shading: darker towards the bottom of the mask
shade = Image.new('RGBA', (S, S), (0, 0, 0, 0))
ImageDraw.Draw(shade).polygon(mask_outline, fill=(0, 0, 0, 255))
grad = Image.new('L', (S, S), 0)
gp = grad.load()
for y in range(S):
    v = int(max(0, min(1, (y - 520) / 420)) * 110)
    for x in range(S):
        gp[x, y] = v
shade.putalpha(Image.composite(grad, Image.new('L', (S, S), 0), shade.split()[3]))
art = Image.alpha_composite(art, shade)

# Eyes: dark sockets, blue glow, bright cores
d = ImageDraw.Draw(art)
for ex in (400, 624):
    d.ellipse([ex - 74, 496, ex + 74, 584], fill=(14, 14, 16))
art = glow(art, lambda g: [g.ellipse([ex - 56, 508, ex + 56, 572], fill=(110, 196, 255, 240)) for ex in (400, 624)], 26)
d = ImageDraw.Draw(art)
for ex in (400, 624):
    d.ellipse([ex - 28, 524, ex + 28, 556], fill=(225, 246, 255))

# Sigil on the brow
art = glow(art, lambda g: sigil(g, 512, 356, 64, (170, 220, 255, 255), 28), 18)
d = ImageDraw.Draw(art)
sigil(d, 512, 356, 64, (240, 250, 255, 255), 12)

# Vignette
vig = Image.new('L', (S, S), 0)
ImageDraw.Draw(vig).ellipse([-140, -120, S + 140, S + 160], fill=255)
vig = vig.filter(ImageFilter.GaussianBlur(120))
dark = Image.new('RGBA', (S, S), (8, 10, 12, 255))
art = Image.composite(art, dark, vig)

# Rounded icon frame
frame_mask = Image.new('L', (S, S), 0)
ImageDraw.Draw(frame_mask).rounded_rectangle([16, 16, S - 16, S - 16], radius=190, fill=255)
icon = Image.new('RGBA', (S, S), (0, 0, 0, 0))
icon.paste(art, (0, 0), frame_mask)
ImageDraw.Draw(icon).rounded_rectangle([16, 16, S - 16, S - 16], radius=190,
                                       outline=(196, 164, 98, 255), width=22)

out = sys.argv[1] if len(sys.argv) > 1 else 'sotc'
icon.resize((256, 256), Image.LANCZOS).save(out + '.png')
icon.save(out + '.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print('wrote', out + '.png', out + '.ico')
