#!/usr/bin/env python3
"""Final live sandbox evidence run — the exact sequence used for the demo video.

Every PayPal call below is real, against api-m.sandbox.paypal.com. Nothing here
is simulated; where a step cannot succeed in sandbox the real API error is shown
verbatim rather than worked around.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load_env(p: pathlib.Path) -> None:
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


load_env(HERE / ".env.paypal")

from firebreak import guard, policy as policy_mod          # noqa: E402
from firebreak.ledger import Ledger                        # noqa: E402
from firebreak.models import PaymentRequest                # noqa: E402
from firebreak.paypal_api import PayPalError, PayPalSandbox  # noqa: E402

BASE = "https://api-m.sandbox.paypal.com"
ev: dict = {"base": BASE, "steps": []}


def rule(t: str) -> None:
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main() -> int:
    pp = PayPalSandbox(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_SECRET"])

    rule("STEP 1 — authenticate to the real PayPal sandbox")
    token = pp.token()
    print(f"  ✓ OAuth token issued by {BASE}  ({len(token)} chars)")
    ev["auth"] = "ok"

    policy_text = ("Never pay more than $50 without asking me. "
                   "Hard limit of $300 a day and $2000 a month. "
                   "Never pay sketchy-ads-ltd. Only use USD.")
    rule("STEP 2 — the policy, in plain English")
    print("  " + policy_text)
    policy = policy_mod.compile_policy(policy_text, use_ai=False)
    print()
    print(policy_mod.describe(policy))
    ev["policy_rules"] = [r.to_dict() for r in policy.rules]

    ledger_path = HERE / "demo-ledger.jsonl"
    if ledger_path.exists():
        ledger_path.unlink()
    fb = guard.Firebreak(pp, policy, ledger_path=str(ledger_path), use_ai=False, mode="orders")

    # ── 3. BLOCK: no API call ────────────────────────────────────────────
    rule("STEP 3 — BLOCK: a merchant on the do-not-pay list")
    d, res = fb.act(PaymentRequest.build("Sketchy Ads Ltd", "20.00", purpose="ad credits"))
    print("  " + d.explain().replace("\n", "\n  "))
    print(f"\n  order created? {'NO — refused before any API call' if res is None else res.get('id')}")
    ev["steps"].append({"step": "block", "action": d.action, "order_created": res is not None,
                        "reasons": d.reasons})

    # ── 4. ESCALATE: real order + real approval URL ──────────────────────
    rule("STEP 4 — ESCALATE: over the ceiling, so a human must consent")
    d, res = fb.act(PaymentRequest.build("Acme Hosting", "180.00",
                                         purpose="annual hosting renewal"))
    print("  " + d.explain().replace("\n", "\n  "))
    oid = res.get("id") if res else None
    url = res.get("approve_url", "") if res else ""
    print(f"\n  PayPal order id  : {oid}")
    print(f"  real approval URL: {url}")
    print("  -> the payer consents on PayPal's own page; Firebreak holds.")
    ev["steps"].append({"step": "escalate", "action": d.action, "order_id": oid,
                        "approve_url": url, "reasons": d.reasons})

    # ── 5. capture refused by PayPal itself ──────────────────────────────
    rule("STEP 5 — prove the gate is PayPal's, not ours")
    print("  Attempting to capture that order WITHOUT the payer approving it...")
    try:
        pp.capture_order(oid)
        print("  !! capture unexpectedly succeeded")
        ev["capture_without_consent"] = "UNEXPECTED_SUCCESS"
    except PayPalError as exc:
        detail = ""
        try:
            detail = json.loads(exc.body)["details"][0]["issue"]
        except Exception:
            pass
        print(f"  ✓ PayPal refused: {detail or exc}")
        print(f"    HTTP {exc.status}")
        print(f"    \"{json.loads(exc.body)['details'][0]['description'][:150]}...\""
              if exc.body.startswith("{") else "")
        ev["capture_without_consent"] = {"issue": detail or str(exc), "http": exc.status}

    fetched = pp.get_order(oid)
    print(f"\n  order status still: {fetched.get('status')}  (awaiting the payer)")
    ev["order_status_after"] = fetched.get("status")

    # ── 6. ledger ────────────────────────────────────────────────────────
    rule("STEP 6 — the tamper-evident audit ledger")
    lg = Ledger(ledger_path)
    ok, problems = lg.verify()
    print(f"  entries: {lg.count()}   chain integrity: {'OK' if ok else 'BROKEN'}")
    for e in lg.entries():
        p = e.get("payload", {})
        r = p.get("request", {})
        print(f"   {e['seq']:>3}  {e['event']:<16} {r.get('merchant',''):<18} {r.get('amount',''):>7}")
    ev["ledger"] = {"entries": lg.count(), "integrity_ok": ok}

    (HERE / "live-evidence.json").write_text(json.dumps(ev, indent=2, default=str),
                                             encoding="utf-8")
    print("\n  evidence -> live-evidence.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
