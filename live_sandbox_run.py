#!/usr/bin/env python3
"""Live PayPal SANDBOX run — real API calls, real order IDs, real approval URLs.

Loads credentials from .env.paypal (never from argv, never echoed), then proves
the integration against https://api-m.sandbox.paypal.com:

  1. OAuth token            -> the credential pair is valid
  2. payment history        -> best effort via the Reporting API
  3. BLOCK decision         -> no order is created at all
  4. ESCALATE decision      -> a real order + a real PayPal approval URL
  5. AUTO_APPROVE decision  -> order created, capture refused by PayPal until
                               the payer consents (the gate is PayPal's own)

Writes machine-readable evidence to live-evidence.json.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

HERE = pathlib.Path(__file__).resolve().parent


def load_env(path: pathlib.Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def rule(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> int:
    import os
    env = load_env(HERE / ".env.paypal")
    for k, v in env.items():
        if v:
            os.environ[k] = v

    if not os.environ.get("PAYPAL_CLIENT_ID") or not os.environ.get("PAYPAL_SECRET"):
        print("credentials missing in .env.paypal")
        return 1

    from firebreak import guard, policy as policy_mod
    from firebreak.ledger import Ledger
    from firebreak.models import PaymentRequest
    from firebreak.paypal_api import PayPalError, PayPalSandbox

    evidence: dict = {"base": "https://api-m.sandbox.paypal.com", "scenarios": []}

    policy_text = ("Never pay more than $50 without asking me. "
                   "Hard limit of $300 a day and $2000 a month. "
                   "Never pay sketchy-ads-ltd. Only use USD. "
                   "If I've never paid a merchant before, check with me first.")
    policy = policy_mod.compile_policy(policy_text, use_ai=False)

    pp = PayPalSandbox(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_SECRET"])

    # ── 1. credentials really work ────────────────────────────────────────
    rule("1. AUTHENTICATION against the real PayPal sandbox")
    try:
        tok = pp.token()
    except PayPalError as exc:
        print(f"  ✗ AUTH FAILED: {exc}")
        return 1
    print(f"  ✓ OAuth token obtained  ({len(tok)} chars, live from api-m.sandbox.paypal.com)")
    evidence["auth"] = "ok"

    # ── 2. history ────────────────────────────────────────────────────────
    rule("2. PAYMENT HISTORY (Reporting API, best effort in sandbox)")
    hist = pp.list_transactions(days=90)
    print(f"  transactions returned: {len(hist)}")
    if not hist:
        print("  (sandbox reporting is often empty — the risk engine reports")
        print("   'no history to compare against', which is the honest answer)")
    evidence["history_count"] = len(hist)

    ledger_path = HERE / "live-ledger.jsonl"
    if ledger_path.exists():
        ledger_path.unlink()
    fb = guard.Firebreak(pp, policy, ledger_path=str(ledger_path), use_ai=False, mode="orders")

    def scenario(label: str, req: PaymentRequest, expect: str) -> None:
        rule(f"{label}\n   request: {req.merchant} {req.amount} {req.currency} — expect {expect}")
        decision, result = fb.act(req)
        for line in decision.explain().splitlines():
            print("   " + line)
        rec = {"label": label, "request": req.to_dict(), "action": decision.action,
               "reasons": decision.reasons,
               "risk": [f.to_dict() for f in decision.risk]}
        if isinstance(result, dict) and result.get("id"):
            rec["order_id"] = result["id"]
            rec["approve_url"] = result.get("approve_url", "")
            print(f"\n   PayPal order id : {result['id']}")
            if result.get("approve_url"):
                print(f"   approval URL    : {result['approve_url']}")
            if result.get("error"):
                print(f"   capture refused : {result['error']}")
        elif result is None:
            print("\n   no order created — refused before touching the API")
        evidence["scenarios"].append(rec)

    scenario("BLOCK — a merchant on the do-not-pay list",
             PaymentRequest.build("Sketchy Ads Ltd", "20.00", purpose="ad credits"),
             "no API call at all")

    scenario("ESCALATE — over the auto-approval ceiling",
             PaymentRequest.build("Acme Hosting", "180.00", purpose="annual hosting renewal"),
             "real order + real approval URL, held for a human")

    scenario("AUTO_APPROVE — a small payment to a known merchant",
             PaymentRequest.build("Figma", "15.00", purpose="monthly design seat"),
             "order created; PayPal still demands payer consent")

    # ── 4. ledger ─────────────────────────────────────────────────────────
    rule("3. AUDIT LEDGER")
    lg = Ledger(ledger_path)
    ok, problems = lg.verify()
    print(f"  entries: {lg.count()}   chain integrity: {'OK' if ok else 'BROKEN'}")
    for e in lg.entries():
        p = e.get("payload", {})
        r = p.get("request", {})
        line = f"   {e['seq']:>3}  {e['event']:<16} {r.get('merchant',''):<20} {r.get('amount','')}"
        if p.get("order_id"):
            line += f"   order={p['order_id']}"
        print(line)
    evidence["ledger_entries"] = lg.count()
    evidence["ledger_integrity"] = ok

    (HERE / "live-evidence.json").write_text(json.dumps(evidence, indent=2, default=str),
                                             encoding="utf-8")
    print("\n  evidence written to live-evidence.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
