#!/usr/bin/env python3
"""Build Firebreak Devpost gallery images. Devpost wants 3:2, <=5MB, JPG/PNG."""
import os
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

W, H = 1200, 800
OUT = "/opt/data/paypal-hack/gallery"
os.makedirs(OUT, exist_ok=True)

F = "/usr/share/fonts/truetype"
B, M, R = f"{F}/dejavu/DejaVuSans-Bold.ttf", f"{F}/dejavu/DejaVuSansMono-Bold.ttf", f"{F}/dejavu/DejaVuSans.ttf"

BG = (10, 13, 18)
PANEL = (17, 22, 31)
LINE = (40, 50, 66)
WHITE = (244, 247, 251)
AMBER = (255, 172, 70)
EMBER = (255, 106, 26)
RED = (255, 78, 70)
GREEN = (74, 222, 128)
CYAN = (72, 208, 255)
GREY = (140, 152, 168)
DIM = (92, 104, 122)


def f(path, size):
    return ImageFont.truetype(path, size)


def fit(d, text, path, target, start=60, tracking=0):
    s = start
    while s > 12:
        fnt = f(path, s)
        w = sum(d.textlength(c, font=fnt) for c in text) + tracking * (len(text) - 1)
        if w <= target:
            return fnt, w
        s -= 1
    return f(path, 12), target


def tracked(d, xy, text, fnt, fill, tracking=0):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=fnt, fill=fill)
        x += d.textlength(ch, font=fnt) + tracking


def canvas(bg_art=None):
    if bg_art and os.path.exists(bg_art):
        base = Image.open(bg_art).convert("RGB").resize((W, H), Image.LANCZOS)
        g = base.convert("L").point(lambda v: int(v * 0.5))
        img = ImageOps.colorize(g, black="#05070A", white="#7A4420").convert("RGB")
        img = Image.blend(img, Image.new("RGB", (W, H), BG), 0.5)
        m = Image.new("L", (W, H))
        px = m.load()
        for x in range(W):
            v = int(70 + 185 * (x / (W - 1)) ** 1.5)
            for y in range(H):
                px[x, y] = v
        img = Image.composite(img, Image.new("RGB", (W, H), (5, 7, 10)), m)
        img = Image.blend(img, Image.new("RGB", (W, H), (3, 4, 6)), 0.30)
    else:
        img = Image.new("RGB", (W, H), BG)
    return img


def finish(img, name, header, title):
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 5], fill=EMBER)
    tracked(d, (56, 40), header.upper(), f(B, 19), EMBER, tracking=2)
    fnt, _ = fit(d, title, B, W - 112, start=44)
    d.text((56, 72), title, font=fnt, fill=WHITE)
    d.rectangle([56, 72 + fnt.size + 20, 56 + 74, 72 + fnt.size + 25], fill=EMBER)
    d.text((56, H - 46), "Firebreak  ·  github.com/RichardChua1234/firebreak",
           font=f(M, 17), fill=DIM)
    p_png = f"{OUT}/{name}.png"
    img.save(p_png)
    p_jpg = f"{OUT}/{name}.jpg"
    img.convert("RGB").save(p_jpg, "JPEG", quality=92, optimize=True)
    kb = os.path.getsize(p_jpg) / 1024
    print(f"  {p_jpg}  1200x800 (3:2)  {kb:,.0f} KB  {'OK <5MB' if kb < 5120 else 'TOO BIG'}")
    return p_jpg


# ─────────────────────────────────────────────────── 01 thesis
def g01():
    img = canvas("/opt/data/paypal-hack/demo/thumb-bg.png")
    d = ImageDraw.Draw(img)
    tracked(d, (56, 56), "PAYPAL AI HACKATHON", f(B, 20), EMBER, tracking=3)
    fnt, w = fit(d, "FIREBREAK", B, W - 112, start=120, tracking=5)
    tracked(d, (52, 150), "FIREBREAK", fnt, WHITE, tracking=5)
    d.rectangle([56, 150 + fnt.size + 34, 56 + 120, 150 + fnt.size + 42], fill=EMBER)
    d.text((56, 150 + fnt.size + 74), "AI proposes.", font=f(B, 46), fill=AMBER)
    d.text((56, 150 + fnt.size + 132), "Deterministic code disposes.", font=f(B, 46), fill=WHITE)

    pills = ["39 tests, all passing", "zero dependencies", "live PayPal sandbox"]
    x = 56
    for p in pills:
        fnt2 = f(B, 21)
        tw = d.textlength(p, font=fnt2)
        d.rounded_rectangle([x, H - 152, x + tw + 44, H - 100], radius=26, fill=(20, 26, 36),
                            outline=LINE, width=2)
        d.text((x + 22, H - 141), p, font=fnt2, fill=GREY)
        x += tw + 62
    return finish(img, "01-thesis", "The problem nobody has solved", "Firebreak")


# ─────────────────────────────────────────────────── 02 policy compiler
def g02():
    img = canvas()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([56, 200, W - 56, 330], radius=12, fill=(14, 19, 27), outline=LINE, width=2)
    d.text((80, 216), "you write this:", font=f(M, 17), fill=DIM)
    quote = ['"Never pay more than $50 without asking me. Hard limit of $300',
             'a day and $2000 a month. Never pay sketchy-ads-ltd. Only use USD.',
             'If I\'ve never paid a merchant before, check with me first."']
    for i, ln in enumerate(quote):
        d.text((80, 244 + i * 26), ln, font=f(M, 19), fill=AMBER)

    d.text((56, 352), "you get this — every rule traced to your own words:",
           font=f(B, 22), fill=WHITE)

    rows = [
        ("r1", "require_approval_above", "50 USD", "Never pay more than $50 without asking me."),
        ("r2", "daily_cap", "300 USD", "Hard limit of $300 a day and $2000 a month."),
        ("r3", "monthly_cap", "2000 USD", "Hard limit of $300 a day and $2000 a month."),
        ("r4", "merchant_block", "sketchyadsltd", "Never pay sketchy-ads-ltd."),
        ("r5", "currency_allow", "USD", "Only use USD."),
        ("r6", "block_new_merchants", "—", "If I've never paid a merchant before, check with me first."),
    ]
    y = 396
    for rid, kind, params, src in rows:
        d.rounded_rectangle([56, y, W - 56, y + 50], radius=8, fill=(15, 20, 29))
        d.text((76, y + 14), rid, font=f(M, 19), fill=EMBER)
        d.text((122, y + 14), kind, font=f(M, 19), fill=WHITE)
        d.text((470, y + 14), params, font=f(M, 19), fill=CYAN)
        s = src if len(src) <= 46 else src[:44] + ".."
        d.text((690, y + 14), f"<- {s}", font=f(M, 15), fill=DIM)
        y += 58
    return finish(img, "02-policy", "1. English in, audit-able rules out",
                  "The interpretation is the product")


# ─────────────────────────────────────────────────── 03 verdicts
def g03():
    img = canvas()
    d = ImageDraw.Draw(img)
    cards = [
        (GREEN, "AUTO_APPROVE", "Inside every limit.", "Payment proceeds. Ledger entry written."),
        (AMBER, "ESCALATE", "Over a limit, or unfamiliar.", "Held. Real PayPal order created, approval URL returned. Nothing moves until a human consents."),
        (RED, "BLOCK", "Against a hard rule.", "Refused before anything exists. No order is created at all."),
    ]
    x = 56
    cw = (W - 112 - 2 * 22) // 3
    for col, name, sub, body in cards:
        d.rounded_rectangle([x, 220, x + cw, 620], radius=14, fill=PANEL, outline=LINE, width=2)
        d.rectangle([x, 220, x + cw, 226], fill=col)
        d.text((x + 26, 252), name, font=f(B, 23), fill=col)
        d.text((x + 26, 292), sub, font=f(R, 18), fill=WHITE)
        words, line, ly = body.split(), "", 350
        for wd in words:
            t = (line + " " + wd).strip()
            if d.textlength(t, font=f(R, 17)) > cw - 52:
                d.text((x + 26, ly), line, font=f(R, 17), fill=GREY)
                ly += 26
                line = wd
            else:
                line = t
        d.text((x + 26, ly), line, font=f(R, 17), fill=GREY)
        x += cw + 22
    d.text((56, 650), "The decision is a pure function of (policy, request, history). "
                      "Same inputs, same verdict — every time.",
           font=f(R, 20), fill=GREY)
    d.text((56, 686), "Risk findings can escalate a payment to a human. "
                      "They can never auto-approve one.", font=f(R, 20), fill=GREY)
    return finish(img, "03-verdicts", "2. One decision, three verdicts", "Where the money stops")


# ─────────────────────────────────────────────────── 04 paypal proof
def g04():
    img = canvas()
    d = ImageDraw.Draw(img)
    x, y, cw, ch = 56, 210, W - 112, 440
    d.rounded_rectangle([x, y, x + cw, y + ch], radius=14, fill=(13, 17, 24), outline=LINE, width=2)
    d.rounded_rectangle([x, y, x + cw, y + 40], radius=14, fill=(22, 28, 38))
    d.rectangle([x, y + 24, x + cw, y + 40], fill=(22, 28, 38))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = x + 24 + i * 24
        d.ellipse([cx - 6, y + 14, cx + 6, y + 26], fill=c)
    d.text((x + 118, y + 12), "real run against api-m.sandbox.paypal.com", font=f(M, 16), fill=DIM)

    lines = [
        ("POST /v2/checkout/orders", GREY),
        ("  -> 201  order_id: 8RA78568F87831317", GREEN),
        ("  -> approve_url: sandbox.paypal.com/checkoutnow?token=8RA78...", CYAN),
        ("", GREY),
        ("POST /v2/checkout/orders/8RA78568F87831317/capture   (no consent)", GREY),
        ("  -> 422  name: ORDER_NOT_APPROVED", RED),
        ("", GREY),
        ("GET /v2/checkout/orders/8RA78568F87831317", GREY),
        ("  -> status: CREATED   (PayPal refused; money did not move)", AMBER),
    ]
    yy = y + 66
    for text, col in lines:
        d.text((x + 30, yy), text, font=f(M, 19), fill=col)
        yy += 33
    d.text((56, 682), "The human-approval gate is PayPal's own payer consent. Not a mock, "
                      "not a simulation.", font=f(R, 20), fill=WHITE)
    return finish(img, "04-paypal-proof", "3. Verified against the real API", "The gate is PayPal's")


# ─────────────────────────────────────────────────── 05 ledger
def g05():
    img = canvas()
    d = ImageDraw.Draw(img)
    x, y, cw, ch = 56, 210, W - 112, 330
    d.rounded_rectangle([x, y, x + cw, y + ch], radius=14, fill=(13, 17, 24), outline=LINE, width=2)
    d.text((x + 30, y + 22), "ledger.jsonl  —  hash-chained, append-only", font=f(M, 18), fill=DIM)
    rows = [
        ("#0004", "a7f3c9d1e8b2...", "BLOCK   sketchy-ads-ltd   120.00 USD"),
        ("#0005", "3e81bad4f7c0...", "ESCALATE acme-hosting     180.00 USD"),
        ("#0006", "c02f5a9b1d47...", "APPROVE  figma             15.00 USD"),
    ]
    yy = y + 66
    for n, h, body in rows:
        d.text((x + 30, yy), n, font=f(M, 19), fill=EMBER)
        d.text((x + 118, yy), h, font=f(M, 19), fill=CYAN)
        d.text((x + 330, yy), body, font=f(M, 19), fill=WHITE)
        yy += 38
    d.text((x + 30, yy + 16), "each entry hashes the one before it", font=f(M, 17), fill=DIM)

    y2 = 570
    d.rounded_rectangle([56, y2, W - 56, y2 + 108], radius=12, fill=(20, 14, 14), outline=(90, 40, 36), width=2)
    d.text((80, y2 + 18), "Diagnostics included:", font=f(B, 20), fill=RED)
    d.text((80, y2 + 52), "edit an entry in the middle  ->  chain broken, reported", font=f(M, 18), fill=GREY)
    d.text((80, y2 + 78), "delete an entry entirely      ->  gap detected, reported", font=f(M, 18), fill=GREY)
    return finish(img, "05-ledger", "4. Every verdict, including refusals",
                  "If it can't be audited, it didn't happen")


print("building Firebreak gallery (1200x800, 3:2):")
for fn in (g01, g02, g03, g04, g05):
    fn()
print("\ndone.")
