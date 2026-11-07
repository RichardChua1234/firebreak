#!/usr/bin/env python3
"""Build the Firebreak YouTube thumbnail. Two variants, 1280x720, type-crisp."""
import os
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

W, H = 1280, 720
OUT = "/opt/data/paypal-hack/demo"
FDIR = "/usr/share/fonts/truetype"
BOLD = f"{FDIR}/dejavu/DejaVuSans-Bold.ttf"
MONO = f"{FDIR}/dejavu/DejaVuSansMono-Bold.ttf"
REG = f"{FDIR}/dejavu/DejaVuSans.ttf"

BG = (10, 13, 18)
WHITE = (245, 248, 252)
AMBER = (255, 168, 66)
EMBER = (255, 106, 26)
RED = (255, 72, 66)
GREY = (122, 134, 152)
DIM = (72, 84, 100)
CYAN = (56, 214, 255)


def font(path, size):
    return ImageFont.truetype(path, size)


def tracked(draw, xy, text, fnt, fill, tracking=0, anchor_y="top"):
    """Draw text with letter-spacing. Returns total width."""
    x, y = xy
    if tracking == 0:
        draw.text((x, y), text, font=fnt, fill=fill)
        return draw.textlength(text, font=fnt)
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + tracking
    return x - xy[0] - tracking


def fit(draw, text, path, target_w, start=200, tracking=0):
    """Largest font size whose rendered width fits target_w."""
    size = start
    while size > 20:
        f = font(path, size)
        w = sum(draw.textlength(c, font=f) for c in text) + tracking * (len(text) - 1)
        if w <= target_w:
            return f, w
        size -= 2
    return font(path, 20), target_w


def radial_glow(size, centre, radius, colour, strength):
    """Soft radial glow layer."""
    layer = Image.new("RGB", size, (0, 0, 0))
    d = ImageDraw.Draw(layer)
    steps = 26
    for i in range(steps, 0, -1):
        r = radius * i / steps
        a = strength * (1 - i / steps) ** 1.8
        box = [centre[0] - r, centre[1] - r, centre[0] + r, centre[1] + r]
        d.ellipse(box, fill=tuple(int(c * a) for c in colour))
    return layer.filter(ImageFilter.GaussianBlur(radius * 0.16))


def pill(draw, xy, text, fnt, fg, bg, pad=(22, 12), radius=None):
    x, y = xy
    tw = draw.textlength(text, font=fnt)
    asc, desc = fnt.getmetrics()
    th = asc + desc
    w, h = tw + pad[0] * 2, th + pad[1] * 2
    r = radius if radius is not None else h // 2
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=bg)
    draw.text((x + pad[0], y + pad[1]), text, font=fnt, fill=fg)
    return w, h


def horizontal_mask(size, lo, hi, p=1.0):
    """L->R gradient mask: lo at x=0, hi at x=W."""
    m = Image.new("L", size)
    px = m.load()
    for x in range(size[0]):
        t = (x / max(size[0] - 1, 1)) ** p
        v = int(lo + (hi - lo) * t)
        for y in range(size[1]):
            px[x, y] = v
    return m


# ══════════════════════════════════════════════════════════ VARIANT A
def variant_a(bg_path):
    base = Image.open(bg_path).convert("RGB").resize((W, H), Image.LANCZOS)
    grey = base.convert("L").point(lambda v: int(v * 0.62))
    img = ImageOps.colorize(grey, black="#05070A", white="#B0632A").convert("RGB")
    img = Image.blend(img, Image.new("RGB", (W, H), BG), 0.34)
    mask = horizontal_mask((W, H), 0, 235, p=0.75)
    img = Image.composite(img, Image.new("RGB", (W, H), (5, 7, 10)), mask)
    img = Image.blend(img, Image.new("RGB", (W, H), (3, 4, 6)), 0.22)

    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 5, W, H], fill=EMBER)

    pill(d, (72, 62), "PAYPAL AI HACKATHON", font(BOLD, 22), WHITE, (18, 24, 34))

    f_head, w1 = fit(d, "FIREBREAK", BOLD, 1010, start=210, tracking=4)
    tracked(d, (70, 214), "FIREBREAK", f_head, WHITE, tracking=4)
    d.rectangle([74, 214 + f_head.size + 36, 74 + w1 * 0.30, 214 + f_head.size + 45], fill=EMBER)

    f_sub = font(BOLD, 50)
    d.text((74, 214 + f_head.size + 78), "AI proposes.", font=f_sub, fill=AMBER)
    y2 = 214 + f_head.size + 78 + 62
    d.text((74, y2), "Deterministic code disposes.", font=f_sub, fill=WHITE)

    d.text((74, H - 74), "python stdlib only  ·  39 tests  ·  live PayPal sandbox  ·  MIT",
           font=font(MONO, 21), fill=GREY)
    img.save(f"{OUT}/firebreak-thumb-a.png")
    return f"{OUT}/firebreak-thumb-a.png"


# ══════════════════════════════════════════════════════════ VARIANT B
def variant_b():
    img = Image.new("RGB", (W, H), BG)
    img = Image.blend(img, radial_glow((W, H), (1040, 150), 620, (255, 120, 40), 0.55), 0.62)
    img = Image.blend(img, horizontal_mask((W, H), 30, 0, p=1.4).convert("RGB"), 0.0)
    d = ImageDraw.Draw(img)

    # terminal card (right)
    tx, ty, tw_, th_ = 622, 152, 596, 412
    d.rounded_rectangle([tx, ty, tx + tw_, ty + th_], radius=16, fill=(14, 18, 26),
                        outline=(38, 48, 64), width=2)
    d.rounded_rectangle([tx, ty, tx + tw_, ty + 42], radius=16, fill=(22, 28, 38))
    d.rectangle([tx, ty + 26, tx + tw_, ty + 42], fill=(22, 28, 38))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = tx + 26 + i * 26
        d.ellipse([cx - 7, ty + 13, cx + 7, ty + 27], fill=c)
    d.text((tx + 118, ty + 11), "firebreak — live sandbox run", font=font(MONO, 17), fill=DIM)

    fm = font(MONO, 20)
    x, y = tx + 30, ty + 70
    lines = [
        ("$ firebreak pay --merchant sketchy-ads-ltd", GREY),
        ("              --amount 120", GREY),
        ("", GREY),
        ('policy    never pay "sketchy-ads-ltd"', CYAN),
        ("risk      seen 3 days ago, 3.0x outlier", CYAN),
        ("", GREY),
        ("VERDICT   BLOCK", RED),
        ("ledger    #0007 appended, chain OK", GREY),
    ]
    for text, col in lines:
        d.text((x, y), text, font=fm, fill=col)
        y += 34
    d.rounded_rectangle([tx + 30, y + 4, tx + 30 + 132, y + 40], radius=6, fill=(48, 16, 16),
                        outline=(120, 34, 30), width=2)
    d.text((tx + 44, y + 12), "no order made", font=font(MONO, 17), fill=(255, 120, 110))

    # headline (left)
    for i, (text, col) in enumerate([("AI", AMBER), ("PROPOSES.", WHITE)]):
        d.text((74, 196 + i * 74), text, font=font(BOLD, 66), fill=col)
    d.text((74, 350), "CODE", font=font(BOLD, 66), fill=EMBER)
    d.text((74, 424), "DISPOSES.", font=font(BOLD, 66), fill=WHITE)

    f_h, _ = fit(d, "FIREBREAK", BOLD, 470, start=76, tracking=3)
    tracked(d, (74, 96), "FIREBREAK", f_h, WHITE, tracking=3)

    d.rectangle([0, H - 5, W, H], fill=EMBER)
    d.text((74, H - 68), "a spend guardrail for AI agents  ·  MIT",
           font=font(MONO, 21), fill=GREY)
    img.save(f"{OUT}/firebreak-thumb-b.png")
    return f"{OUT}/firebreak-thumb-b.png"


for fn in (lambda: variant_a(f"{OUT}/thumb-bg.png"), variant_b):
    p = fn()
    im = Image.open(p)
    jp = p.replace(".png", ".jpg")
    im.convert("RGB").save(jp, "JPEG", quality=93, optimize=True, subsampling=0)
    print(f"{p}  {im.size[0]}x{im.size[1]}  {os.path.getsize(p):,} bytes")
    print(f"{jp}  {Image.open(jp).size[0]}x{Image.open(jp).size[1]}  "
          f"{os.path.getsize(jp):,} bytes  ({'OK <2MB' if os.path.getsize(jp) < 2_000_000 else 'TOO BIG'})")
