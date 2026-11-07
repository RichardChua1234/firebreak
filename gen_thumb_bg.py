#!/usr/bin/env python3
"""Generate the Firebreak thumbnail background via Leonardo. No text in the image."""
import json
import os
import sys
import time
import urllib.request

BASE = "https://cloud.leonardo.ai/api/rest/v1"
MODEL = "6bef9f1b-29cb-40c7-b9df-32b51c1f67d3"  # Leonardo Creative

key = None
with open("/opt/data/.env") as fh:
    for line in fh:
        if line.startswith("LEONARDO_API_KEY="):
            key = line.split("=", 1)[1].strip()
if not key:
    sys.exit("no LEONARDO_API_KEY found")


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# balance --------------------------------------------------------------
try:
    me = call("GET", "/me")
    u = me.get("user_details", [{}])
    u = u[0] if isinstance(u, list) else u
    for k in ("subscriptionTokens", "paidTokens", "subscriptionGptTokens",
              "apiSubscriptionTokens", "apiPaidTokens"):
        if k in u:
            print(f"  {k}: {u[k]}")
except Exception as exc:
    print(f"  balance check failed: {exc}")

PROMPT = (
    "Cinematic dark tech poster background, wide 16:9 composition. A glowing "
    "translucent vertical wall of fire forms an impassable barrier across the "
    "centre of the frame. On the left, a sleek dark chrome robotic hand reaches "
    "forward, fingertips stopping just short of the barrier, lit by hard orange "
    "rim light. On the right behind the barrier, a softly glowing cyan credit "
    "card hovers in the haze. Deep charcoal near-black background, volumetric "
    "smoke, dramatic orange and cyan lighting, high contrast, moody premium "
    "poster aesthetic, ultra sharp, cinematic depth of field. "
    "No text, no words, no letters, no numbers, no watermarks."
)

print("\n=== creating generation ===")
job = call("POST", "/generations", {
    "prompt": PROMPT,
    "modelId": MODEL,
    "width": 1280,
    "height": 720,
    "num_images": 1,
    "guidance_scale": 7,
    "presetStyle": "CINEMATIC",
})
gen = job.get("sdGenerationJob", {})
gid = gen.get("generationId")
print(f"  id   : {gid}")
print(f"  cost : {json.dumps(gen.get('cost'))}")

if not gid:
    sys.exit(f"no generation id: {json.dumps(job)[:400]}")

print("\n=== polling ===")
url = None
for i in range(30):
    time.sleep(6)
    st = call("GET", f"/generations/{gid}")
    g = st.get("generations_by_pk", {})
    status = g.get("status")
    print(f"  [{i:02d}] {status}")
    if status == "COMPLETE":
        imgs = g.get("generated_images", [])
        if imgs:
            url = imgs[0].get("url")
        break
    if status == "FAILED":
        sys.exit("generation FAILED")

if not url:
    sys.exit("no image url")

out = "/opt/data/paypal-hack/demo/thumb-bg.png"
os.makedirs(os.path.dirname(out), exist_ok=True)
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as fh:
    fh.write(r.read())

import struct
with open(out, "rb") as fh:
    fh.seek(16)
    w, h = struct.unpack(">II", fh.read(8))
print(f"\n=== saved ===")
print(f"  {out}  ({os.path.getsize(out):,} bytes, {w}x{h})")
