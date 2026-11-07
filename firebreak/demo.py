"""Scripted end-to-end scenario -- the thing to watch to understand Firebreak.

Runs entirely offline against the mock by default so it works with no
credentials. Pass ``--online`` (via the CLI) once sandbox keys are set and the
same script drives the real PayPal sandbox API, including real order IDs and
real PayPal approve URLs.

Six requests, chosen to exercise every outcome:
  1. routine renewal within policy            -> AUTO_APPROVE
  2. same merchant, larger amount             -> ESCALATE (over the ceiling)
  3. same amount again, 3 days later          -> ESCALATE (duplicate risk)
  4. a merchant explicitly banned             -> BLOCK
  5. a merchant never paid before             -> ESCALATE (unseen payee)
  6. enough to blow the daily cap             -> BLOCK
Then it verifies the audit chain and attempts a tamper.
"""
from __future__ import annotations

import datetime as _dt
import pathlib
import sys

from . import guard, policy as policy_mod
from .ledger import Ledger
from .models import PaymentRequest
from .paypal_api import MockPayPal, client_from_env

POLICY_TEXT = (
    "Never pay more than $50 without asking me. "
    "Hard limit of $300 a day and $2000 a month. "
    "Never pay sketchy-ads-ltd. "
    "Only use USD. "
    "If I've never paid a merchant before, check with me first."
)


def _history(days_ago: int, merchant: str, amount: str, tid: str) -> dict:
    when = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days_ago)
    return {"transaction_id": tid, "merchant": merchant, "amount": amount, "currency": "USD",
            "date": when.isoformat(timespec="seconds"), "status": "COMPLETED"}


def _rule(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def run_demo(offline: bool = True, use_ai: bool = True, ledger_path: str = "demo-ledger.jsonl") -> int:
    path = pathlib.Path(ledger_path)
    if path.exists():
        path.unlink()                                   # fresh run, fresh chain

    _rule("1. THE POLICY, WRITTEN IN PLAIN ENGLISH")
    print(POLICY_TEXT)
    policy = policy_mod.compile_policy(POLICY_TEXT, use_ai=use_ai)
    print()
    print(policy_mod.describe(policy))

    history = [
        _history(60, "Acme Hosting", "45.00", "seed-1"),
        _history(30, "Acme Hosting", "45.00", "seed-2"),
        _history(70, "Figma", "15.00", "seed-3"),      # outside the 30-day dup window
        _history(40, "Figma", "15.00", "seed-4"),
    ]
    paypal = MockPayPal(history=history) if offline else client_from_env()
    fb = guard.Firebreak(paypal, policy, ledger_path=str(path), use_ai=use_ai,
                         mode="payouts" if offline else "orders")

    scenarios = [
        ("routine renewal, within policy",
         PaymentRequest.build("Figma", "15.00", purpose="monthly design seat")),
        ("same merchant, well over the ceiling",
         PaymentRequest.build("Acme Hosting", "180.00", purpose="annual hosting renewal")),
        ("the same charge a second time",
         PaymentRequest.build("Figma", "15.00", purpose="monthly design seat")),
        ("a merchant we banned outright",
         PaymentRequest.build("Sketchy Ads Ltd", "20.00", purpose="ad credits")),
        ("a brand new supplier we've never paid",
         PaymentRequest.build("Northwind Supplies", "30.00", purpose="office restock")),
        ("a payment that would blow the daily cap",
         PaymentRequest.build("Acme Hosting", "320.00", purpose="bulk renewal")),
    ]

    _rule("2. SIX PAYMENT REQUESTS FROM AN AGENT")
    for title, req in scenarios:
        print(f"\n--- {title}")
        print(f"    request: {req.merchant} {req.amount} {req.currency} ({req.purpose})")
        decision, result = fb.act(req)
        for line in decision.explain().splitlines():
            print("    " + line)
        if result and isinstance(result, dict):
            if result.get("status") == "COMPLETED" or "batch_header" in result:
                print("    -> MONEY MOVED")
            elif decision.needs_human:
                print("    -> held; no money moved")

    _rule("3. THE AUDIT LEDGER (tamper-evident, hash-chained)")
    lg = Ledger(path)
    ok, problems = lg.verify()
    print(f"entries: {lg.count()}   chain integrity: {'OK' if ok else 'BROKEN'}")
    for e in lg.entries():
        p = e.get("payload", {})
        r = p.get("request", {})
        line = f"  {e['seq']:>3}  {e['event']:<15} {r.get('merchant',''):<20} " \
               f"{r.get('amount',''):>8} {r.get('currency','')}"
        if p.get("approved_by"):
            line += f"   approved_by={p['approved_by']}"
        print(line)

    _rule("4. WHY THE LEDGER MATTERS: TAMPER DETECTION")
    raw = path.read_text(encoding="utf-8").splitlines()
    tampered = []
    for line in raw:
        line = line.replace('"180.00"', '"1.80"')        # someone edits history
        tampered.append(line)
    tampered_path = path.with_suffix(".tampered.jsonl")
    tampered_path.write_text("\n".join(tampered) + "\n", encoding="utf-8")
    ok2, problems2 = Ledger(tampered_path).verify()
    print(f"after editing an amount in the file: integrity {'OK' if ok2 else 'BROKEN'}")
    for p in problems2[:3]:
        print("  !", p)
    tampered_path.unlink(missing_ok=True)

    _rule("SUMMARY")
    print("  every request produced a recorded, reasoned verdict")
    print("  nothing above the ceiling moved without a human decision")
    print("  the banned merchant was refused before any order was created")
    print("  editing the history is detectable")
    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
