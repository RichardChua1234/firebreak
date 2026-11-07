#!/usr/bin/env python3
"""Validate the exact Python the browser demo will run, against the real engine.

Prints the JSON payloads the page will render, so the page is built on verified
output rather than guesses. Nothing here is browser-specific.
"""
import json
import sys
from decimal import Decimal

sys.path.insert(0, "/opt/data/paypal-hack")

from firebreak import ledger as L, models as M, policy as P, risk as R  # noqa: E402

print("Ledger methods :", [a for a in dir(L.Ledger) if not a.startswith("_")])
print("RiskFinding    :", [a for a in dir(M.RiskFinding) if not a.startswith("_")])
print()

POLICY = (
    "Never pay more than $50 without asking me. "
    "Hard limit of $300 a day and $2000 a month. "
    "Never pay sketchy-ads-ltd. "
    "Only use USD. "
    "If I've never paid a merchant before, check with me first."
)

HISTORY = [
    {"transaction_id": "seed-1", "merchant": "Acme Hosting", "amount": "45.00",
     "currency": "USD", "date": "2026-09-08T10:00:00+00:00", "status": "COMPLETED"},
    {"transaction_id": "seed-2", "merchant": "Acme Hosting", "amount": "45.00",
     "currency": "USD", "date": "2026-10-08T10:00:00+00:00", "status": "COMPLETED"},
    {"transaction_id": "seed-3", "merchant": "Figma", "amount": "15.00",
     "currency": "USD", "date": "2026-09-28T10:00:00+00:00", "status": "COMPLETED"},
    {"transaction_id": "seed-4", "merchant": "Figma", "amount": "15.00",
     "currency": "USD", "date": "2026-10-28T10:00:00+00:00", "status": "COMPLETED"},
]

# ── 1. compile ─────────────────────────────────────────────────────────
pol = P.compile_policy(POLICY, use_ai=False)
compile_payload = {
    "compiled_by": pol.compiled_by,
    "rule_count": len(pol.rules),
    "rules": [r.to_dict() for r in pol.rules],
}
print("=== compile ===")
print(json.dumps(compile_payload, indent=2)[:900])
print()

# ── 2. evaluate three cases ────────────────────────────────────────────
CASES = [
    ("Sketchy Ads Ltd", "120.00", "USD", "on the do-not-pay list"),
    ("Acme Hosting", "180.00", "USD", "over the $50 ceiling, known merchant"),
    ("Figma", "15.00", "USD", "known merchant, small amount"),
]

print("=== evaluate ===")
results = []
for merchant, amount, currency, label in CASES:
    req = M.PaymentRequest(merchant=merchant, amount=Decimal(amount), currency=currency)
    findings = R.analyze(req, HISTORY)
    dec = P.evaluate(pol, req, HISTORY, findings)
    d = dec.to_dict()
    results.append({"label": label, "merchant": merchant, "amount": amount,
                    "decision": d, "findings": [f.to_dict() for f in findings]})
    print(f"  {merchant:18} {amount:>8}  ->  {json.dumps(d)[:170]}")

# ── 3. ledger ──────────────────────────────────────────────────────────
print("\n=== ledger ===")
path = "/tmp/browser-demo-ledger.jsonl"
try:
    import os
    os.remove(path)
except OSError:
    pass
led = L.Ledger(path)
entries = []
for r in results:
    rec = led.append("verdict", {"merchant": r["merchant"], "amount": r["amount"],
                                 "verdict": r["decision"]})
    entries.append(rec)
print(f"  appended {len(entries)} entries")
print(f"  first entry keys: {sorted(entries[0].keys())}")

checks = {}
for name in ("verify", "integrity", "verify_chain", "check", "is_valid"):
    if hasattr(led, name):
        try:
            checks[name] = getattr(led, name)()
        except Exception as exc:                                  # noqa: BLE001
            checks[name] = f"raised {exc}"
print(f"  integrity checks: {json.dumps(checks, default=str)[:300]}")
print(f"  ledger files: {[p for p in __import__('os').listdir('/tmp') if 'browser-demo' in p]}")

print("\n=== summary of what the page will show ===")
print(f"  rules compiled : {compile_payload['rule_count']}")
print(f"  verdicts       : {[r['decision'].get('action') for r in results]}")
print(f"  ledger entries : {len(entries)}")
