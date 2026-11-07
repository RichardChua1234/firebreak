"""Command line interface.

    python -m firebreak policy "never more than $50 without asking me"
    python -m firebreak check  "pay Acme 180 for the hosting invoice"
    python -m firebreak pay    "pay Acme 180 for the hosting invoice"
    python -m firebreak confirm <order_id> --approved-by richard
    python -m firebreak audit
    python -m firebreak demo

Add ``--offline`` to run against the in-memory mock (no credentials needed),
``--seed-demo`` for offline plus 60 days of sample history, and ``--no-ai`` to
force the deterministic code paths.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from . import guard, policy as policy_mod
from .models import PaymentRequest
from .paypal_api import MockPayPal, PayPalError, client_from_env

DEFAULT_POLICY = (
    "Never pay more than $50 without asking me. "
    "Hard limit of $300 a day and $2000 a month. "
    "Never pay sketchy-ads-ltd. "
    "Only use USD. "
    "I've never paid a merchant before, check with me first."
)


def _load_policy(args):
    if args.policy_file:
        text = pathlib.Path(args.policy_file).read_text(encoding="utf-8")
    else:
        text = args.policy or DEFAULT_POLICY
    return guard.policy_from_text(text, use_ai=not args.no_ai)


def _build(args):
    policy = _load_policy(args)
    if args.offline or args.seed_demo:
        client = MockPayPal(history=_demo_history() if args.seed_demo else [])
    else:
        client = client_from_env()
    return guard.Firebreak(client, policy, ledger_path=args.ledger,
                           use_ai=not args.no_ai, mode=args.mode)


def _demo_history() -> list[dict]:
    """A believable 60 days of history so the risk engine has something to chew."""
    return [
        {"transaction_id": "T1", "merchant": "Acme Hosting", "amount": "45.00", "currency": "USD",
         "date": "2026-10-08T09:12:00Z", "status": "COMPLETED"},
        {"transaction_id": "T2", "merchant": "Acme Hosting", "amount": "45.00", "currency": "USD",
         "date": "2026-09-08T09:11:00Z", "status": "COMPLETED"},
        {"transaction_id": "T3", "merchant": "Figma", "amount": "15.00", "currency": "USD",
         "date": "2026-10-02T04:00:00Z", "status": "COMPLETED"},
        {"transaction_id": "T4", "merchant": "Figma", "amount": "15.00", "currency": "USD",
         "date": "2026-09-02T04:00:00Z", "status": "COMPLETED"},
        {"transaction_id": "T5", "merchant": "Acme Hosting", "amount": "45.00", "currency": "USD",
         "date": "2026-11-05T09:12:00Z", "status": "COMPLETED"},
    ]


def _print_decision(d, order=None):
    print(d.explain())
    if order and order.get("id"):
        url = order.get("approve_url") or ""
        print(f"\n  order: {order.get('id')}  status={order.get('status', '')}")
        if url:
            print(f"  human approves here: {url}")
    print()


def cmd_policy(args):
    p = _load_policy(args)
    print(policy_mod.describe(p))
    return 0


def cmd_check(args):
    fb = _build(args)
    req = guard.intent_from_text(args.text, use_ai=not args.no_ai)
    print("understood as:", json.dumps(req.to_dict()))
    d = fb.check(req)
    _print_decision(d)
    return 1 if d.blocked else 0


def cmd_pay(args):
    fb = _build(args)
    req = guard.intent_from_text(args.text, use_ai=not args.no_ai)
    print("understood as:", json.dumps(req.to_dict()))
    d, result = fb.act(req)
    _print_decision(d, result if isinstance(result, dict) else None)
    if d.blocked:
        print("REFUSED - nothing was created. See ledger for the reason.\n")
        return 1
    if d.needs_human:
        oid = (result or {}).get("id", "<order-id>")
        print(f"HELD FOR HUMAN APPROVAL. Nothing has moved.")
        print(f"To release it:  python -m firebreak confirm {oid} --approved-by <you>\n")
        return 2
    print("EXECUTED under policy.\n")
    return 0


def cmd_confirm(args):
    fb = _build(args)
    if isinstance(fb.paypal, MockPayPal):
        fb.paypal.approve(args.order_id)   # stand in for the human's PayPal consent
    try:
        res = fb.confirm(args.order_id, approved_by=args.approved_by)
    except PayPalError as exc:
        print(f"could not capture: {exc}")
        return 1
    print(json.dumps(res, indent=2, default=str)[:1200])
    print(f"\nrecorded as approved by {args.approved_by!r}")
    return 0


def cmd_audit(args):
    from .ledger import Ledger
    lg = Ledger(args.ledger)
    ok, problems = lg.verify()
    n = lg.count()
    print(f"ledger entries : {n}")
    print(f"chain integrity: {'OK' if ok else 'BROKEN'}")
    for p in problems:
        print("  !", p)
    for e in lg.entries():
        payload = e.get("payload", {})
        req = payload.get("request", {})
        label = f"{e['seq']:>3} {e['event']:<16}"
        if req:
            label += f"{req.get('merchant','')} {req.get('amount','')} {req.get('currency','')}"
        if payload.get("approved_by"):
            label += f"  (approved by {payload['approved_by']})"
        print("  " + label)
    return 0 if ok else 1


def cmd_demo(args):
    from .demo import run_demo
    return run_demo(offline=args.offline, use_ai=not args.no_ai, ledger_path=args.ledger)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="firebreak",
                                 description="A policy-enforced spend guardrail for AI agents.")
    ap.add_argument("--policy", help="policy text (English)")
    ap.add_argument("--policy-file", help="path to a policy file")
    ap.add_argument("--ledger", default=os.environ.get("FIREBREAK_LEDGER", "firebreak-ledger.jsonl"))
    ap.add_argument("--offline", action="store_true", help="use the in-memory mock, no credentials")
    ap.add_argument("--seed-demo", action="store_true", help="offline + 60 days of sample history")
    ap.add_argument("--no-ai", action="store_true", help="deterministic code paths only")
    ap.add_argument("--mode", choices=["orders", "payouts"], default="orders")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("policy", help="compile and show the policy rules")
    p.set_defaults(func=cmd_policy)

    p = sub.add_parser("check", help="decide only, move no money")
    p.add_argument("text")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("pay", help="decide and act")
    p.add_argument("text")
    p.set_defaults(func=cmd_pay)

    p = sub.add_parser("confirm", help="release a payment a human approved")
    p.add_argument("order_id")
    p.add_argument("--approved-by", default="human")
    p.set_defaults(func=cmd_confirm)

    p = sub.add_parser("audit", help="verify the tamper-evident ledger")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("demo", help="run the scripted end-to-end scenario")
    p.set_defaults(func=cmd_demo)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (PayPalError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
