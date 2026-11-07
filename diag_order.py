#!/usr/bin/env python3
"""Diagnostic: inspect the real order payload to find the approval link, and
prove PayPal refuses to capture without the payer's consent."""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load_env(p):
    env = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


import os
os.environ.update({k: v for k, v in load_env(HERE / ".env.paypal").items() if v})

from firebreak.models import PaymentRequest
from firebreak.paypal_api import PayPalError, PayPalSandbox

pp = PayPalSandbox(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_SECRET"])
print("token:", "OK" if pp.token() else "FAIL")

req = PaymentRequest.build("Figma", "15.00", purpose="monthly design seat")
order = pp.create_order(req)

print("\n=== FULL order response (keys) ===")
print("top-level keys:", sorted(order.keys()))
print("status        :", order.get("status"))
print("id            :", order.get("id"))

print("\n=== the links PayPal actually returned ===")
for link in order.get("links", []):
    print(f"  rel={link.get('rel'):<14} method={link.get('method','?'):<6} href={link.get('href')}")

print("\n=== which rel names map to a human approval page? ===")
for link in order.get("links", []):
    href = link.get("href", "")
    if any(s in href for s in ("checkoutnow", "paypal.com/checkout", "approve", "payer")):
        print(f"  CANDIDATE: rel={link.get('rel')} -> {href}")

print("\n=== attempt capture WITHOUT payer consent (expect a refusal) ===")
try:
    res = pp.capture_order(order["id"])
    print("  UNEXPECTED SUCCESS:", json.dumps(res)[:300])
except PayPalError as exc:
    print(f"  ✓ refused as expected")
    print(f"    message : {exc}")
    print(f"    status  : {exc.status}")
    print(f"    raw body: {exc.body[:400]}")

print("\n=== re-fetch the order to confirm it is still awaiting approval ===")
fresh = pp.get_order(order["id"])
print("  status now:", fresh.get("status"))
for link in fresh.get("links", []):
    print(f"    rel={link.get('rel'):<14} {link.get('href')}")
