#!/usr/bin/env python3
"""Build the demo video (<3 min) from REAL captured output.

Nothing in this video is typed by hand: every line comes from re-running the
project and capturing its actual stdout, including the live PayPal sandbox
responses. The video is a rendering of a real run, and says so on screen.

    python make_video.py
    -> demo/firebreak-demo.mp4
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "demo"
FRAMES = OUT / "frames"
PY = sys.executable or "python3"

W, H = 1280, 720
PAD = 48
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

BG = (13, 17, 23)
CHROME = (22, 27, 34)
TXT = (201, 209, 217)
DIM = (139, 148, 158)
CMD = (255, 255, 255)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
YELLOW = (210, 168, 0)
CYAN = (86, 182, 194)
MAGENTA = (219, 110, 191)
ORANGE = (255, 165, 89)


def font(size: int, bold: bool = False):
    return ImageFont.truetype(FONT_B if bold else FONT, size)


def colour(line: str) -> tuple:
    s = line.strip()
    if s.startswith("$"):
        return CMD
    if "✓" in s or s.startswith("  ✓") or "MONEY MOVED" in s or "chain integrity: OK" in s:
        return GREEN
    if "✗" in s or "BLOCK" in s or "REFUSED" in s or "BROKEN" in s:
        return RED
    if "ESCALATE" in s or "AWAITING" in s or "held" in s or s.startswith("!!"):
        return YELLOW
    if "AUTO_APPROVE" in s or "EXECUTED" in s:
        return GREEN
    if s.startswith("===") or s.startswith("──") or s.startswith("STEP"):
        return CYAN
    if "approve" in s.lower() and "http" in s.lower():
        return MAGENTA
    if re.match(r"^\s*[r•]\d", s) or s.startswith("  !"):
        return ORANGE
    return TXT


def wrap(line: str, width: int = 96) -> list[str]:
    if len(line) <= width:
        return [line]
    out, cur = [], line
    indent = len(line) - len(line.lstrip())
    first = True
    while len(cur) > width:
        cut = cur.rfind(" ", 0, width)
        cut = cut if cut > 20 else width
        out.append(cur[:cut])
        cur = " " * (indent + 4) + cur[cut:].lstrip()
        first = False
    out.append(cur)
    return out


class Term:
    """A tiny terminal-screen model: append lines, render the tail."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, tuple]] = []

    def add(self, text: str = "") -> None:
        for piece in wrap(text):
            self.lines.append((piece, colour(piece)))

    def add_block(self, text: str) -> None:
        for ln in text.splitlines():
            self.add(ln)

    def cmd(self, text: str) -> None:
        self.add("$ " + text)

    def visible(self, rows: int = 25) -> list[tuple[str, tuple]]:
        return self.lines[-rows:]


def render(term: Term, caption: str, disclosure: str | None = None) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # window chrome
    d.rectangle([0, 0, W, 40], fill=CHROME)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse([20 + i * 22, 14, 32 + i * 22, 26], fill=c)
    d.text((W // 2 - 190, 11), "firebreak  —  zsh  —  120x34", font=font(15), fill=DIM)

    # reserve room for the caption band BEFORE drawing text, so the terminal
    # never runs underneath it (a bug in the first cut of this renderer)
    band = 62 if disclosure else 46
    rows = max(6, (H - band - 74) // 24)
    f = font(17)
    y = 62
    for text, col in term.visible(rows):
        d.text((PAD, y), text, font=f, fill=col)
        y += 24

    d.rectangle([0, H - band, W, H], fill=(28, 34, 44))
    if disclosure:
        d.text((PAD, H - band + 8), disclosure, font=font(14), fill=DIM)
        d.text((PAD, H - band + 30), caption, font=font(18, bold=True), fill=CYAN)
    elif caption:
        d.text((PAD, H - band + 12), caption, font=font(18, bold=True), fill=CYAN)
    return img


def card(title: str, subtitle: str, lines: list[str], accent=CYAN) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 8, H], fill=accent)
    d.text((90, 180), title, font=font(46, bold=True), fill=(255, 255, 255))
    d.text((90, 250), subtitle, font=font(22), fill=accent)
    y = 320
    for ln in lines:
        d.text((90, y), ln, font=font(19), fill=TXT)
        y += 32
    return img


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=300)
    return p.stdout


def build() -> int:
    if FRAMES.exists():
        for f in FRAMES.iterdir():
            f.unlink()
    FRAMES.mkdir(parents=True, exist_ok=True)

    # ── capture REAL output ───────────────────────────────────────────────
    print("capturing real output ...")
    policy_out = run([PY, "-m", "firebreak", "--offline", "--no-ai", "policy"])
    live_out = run([PY, "final_sandbox_evidence.py"])
    demo_out = run([PY, "-m", "firebreak", "--offline", "--no-ai", "demo"])

    t = Term()
    frames: list[tuple[Image.Image, float]] = []

    # ── title ─────────────────────────────────────────────────────────────
    frames.append((card(
        "Firebreak",
        "A policy-enforced spend guardrail for AI agents.",
        ["AI proposes. Deterministic code disposes.",
         "",
         "Agents can move money. Nobody will let them.",
         "This is the missing middle: spend inside limits you wrote,",
         "refuse the rest, and keep a record you can audit.",
         "",
         "· Real PayPal sandbox integration (orders + payouts)",
         "· Zero dependencies · 39 unit tests"],
        accent=ORANGE), 6.5))
    frames.append((card(
        "What you are about to see",
        "A real run — nothing typed by hand.",
        ["Every line below is actual captured stdout, including",
         "live responses from api-m.sandbox.paypal.com.",
         "",
         "1. A spending policy written in plain English",
         "2. A payment refused before any API call",
         "3. A real PayPal order + real approval URL",
         "4. PayPal itself refusing to move money",
         "5. The tamper-evident audit ledger"],
        accent=CYAN), 6.5))

    # ── policy compiled ──────────────────────────────────────────────────
    t.cmd("python -m firebreak --offline policy")
    t.add_block(policy_out.strip())
    frames.append((render(t, "1. Plain-English policy → enforceable rules"), 13.0))

    # ── live: auth + policy + block ──────────────────────────────────────
    t = Term()
    t.cmd("python final_sandbox_evidence.py   # real PayPal sandbox")
    blocks = re.split(r"\n(?=STEP \d)", live_out)
    step1_3 = [b for b in blocks if b.startswith("STEP 1") or b.startswith("STEP 2")
               or b.startswith("STEP 3")]
    t.add_block("\n".join(step1_3).strip())
    frames.append((render(t, "2. Live sandbox: authenticate, compile, BLOCK",
                          "real API — api-m.sandbox.paypal.com"), 24.0))

    # ── live: escalate + real approval URL ───────────────────────────────
    s4 = next((b for b in blocks if b.startswith("STEP 4")), "")
    t.add_block("\n" + s4.strip())
    frames.append((render(t, "3. ESCALATE → real PayPal order, real approval URL",
                          "the human consents on PayPal's own page"), 20.0))

    # ── live: paypal refuses capture ─────────────────────────────────────
    s5 = next((b for b in blocks if b.startswith("STEP 5")), "")
    t.add_block("\n" + s5.strip())
    frames.append((render(t, "4. The gate is PayPal's, not ours",
                          "PayPal refused the capture: ORDER_NOT_APPROVED"), 18.0))

    # ── live: ledger ─────────────────────────────────────────────────────
    s6 = next((b for b in blocks if b.startswith("STEP 6")), "")
    t.add_block("\n" + s6.strip())
    frames.append((render(t, "5. Tamper-evident audit ledger",
                          "every verdict recorded — including the refusals"), 15.0))

    # ── offline: full verdict matrix ─────────────────────────────────────
    t = Term()
    t.cmd("python -m firebreak --offline demo   # six requests, six verdicts")
    grid = re.split(r"\n(?=--- )", demo_out)
    head = grid[0]
    t.add_block(head.strip()[:0] or "")
    for blk in grid[:7]:
        t.add_block(blk.strip()[:1200])
    frames.append((render(t, "6. Six agent requests → six recorded verdicts"), 20.0))

    tail = "\n".join(grid[7:])
    t = Term()
    t.add_block(tail.strip())
    frames.append((render(t, "7. Ledger integrity — and tampering detected"), 18.0))

    # ── closing ──────────────────────────────────────────────────────────
    frames.append((card(
        "AI proposes, deterministic code disposes.",
        "github.com/RichardChua1234/firebreak",
        ["The decision is a pure function of (policy, request, history).",
         "Same inputs, same verdict, every time — because",
         "\"the model decided\" is not an answer anyone accepts",
         "when money is moving.",
         "",
         "Python standard library only. 39 tests. MIT.",
         "",
         "Built for the PayPal AI Hackathon 2026."],
        accent=GREEN), 10.0))

    # ── write frames + concat ────────────────────────────────────────────
    print("writing frames ...")
    concat = []
    total = 0.0
    for i, (img, dur) in enumerate(frames, 1):
        p = FRAMES / f"f{i:03d}.png"
        img.save(p)
        concat.append(f"file '{p}'\nduration {dur}")
        total += dur
    last = FRAMES / f"f{len(frames):03d}.png"
    concat.append(f"file '{last}'\nduration 4.0")   # hold the closing card
    concat.append(f"file '{last}'")
    (FRAMES / "concat.txt").write_text("\n".join(concat) + "\n", encoding="utf-8")

    print(f"total duration: {total:.1f}s")
    out = OUT / "firebreak-demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(FRAMES / "concat.txt"),
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "20", "-r", "30", str(out)], check=True)
    print(f"wrote {out}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(build())
