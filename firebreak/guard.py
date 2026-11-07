"""The orchestrator: the thing a human actually talks to.

Ties together intent parsing (AI), policy (deterministic), risk (deterministic),
PayPal execution and the audit ledger, and enforces the one rule that matters:
**nothing above the policy ceiling moves without a recorded human decision.**
"""
from __future__ import annotations

import re
from decimal import Decimal

from . import llm, policy as policy_mod, risk as risk_mod
from .ledger import Ledger
from .models import Decision, PaymentRequest, Policy
from .paypal_api import PayPalError

INTENT_PROMPT = """Extract a single payment intent from the user's instruction.

Return ONLY JSON: {"merchant": str, "amount": number, "currency": str, "purpose": str}
- currency defaults to "USD" if not stated.
- merchant is the payee name as written, title-cased.
- purpose is a short reason, or "" if none was given.
If the text does not describe a payment, return {"error": "not a payment"}.
"""


def intent_from_text(text: str, use_ai: bool = True) -> PaymentRequest:
    """Understand "renew Figma, about $15" as a structured request."""
    if use_ai and llm.available():
        try:
            doc = llm.chat_json(INTENT_PROMPT, text)
            if doc.get("merchant") and doc.get("amount") is not None:
                return PaymentRequest.build(
                    merchant=str(doc["merchant"]),
                    amount=doc["amount"],
                    currency=str(doc.get("currency") or "USD"),
                    purpose=str(doc.get("purpose") or ""),
                    requested_by="agent")
        except llm.AIUnavailable:
            pass
    return _intent_deterministic(text)


def _intent_deterministic(text: str) -> PaymentRequest:
    """Pattern-based fallback so the guardrail works with no model configured."""
    amount = None
    m = re.search(r"(?:\$|usd\s*|sgd\s*)([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text, re.I)
    if m:
        amount = Decimal(m.group(1).replace(",", ""))
    if amount is None:
        m = re.search(r"\b([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(dollars|usd|sgd)\b", text, re.I)
        if m:
            amount = Decimal(m.group(1).replace(",", ""))
    if amount is None:
        # a bare number is still an amount: "pay Acme 180 for hosting"
        m = re.search(r"\b([0-9][0-9,]*(?:\.[0-9]{1,2})?)\b", text)
        if m:
            amount = Decimal(m.group(1).replace(",", ""))
    if amount is None:
        raise ValueError(f"could not find an amount in {text!r}")

    currency = "SGD" if re.search(r"\bsgd\b", text, re.I) else "USD"

    merchant = ""
    m = re.search(r"\b(?:pay|paid|renew|invoice from|invoice for|to)\s+([A-Za-z0-9][A-Za-z0-9 .&'\-]{1,40})", text)
    if m:
        merchant = m.group(1)
    if not merchant:
        m = re.search(r"\b(?:for|from)\s+([A-Za-z0-9][A-Za-z0-9 .&'\-]{1,40})", text)
        merchant = m.group(1) if m else "unknown-merchant"
    merchant = re.sub(r"\b(for|about|around|the|our|invoice|subscription)\b.*$", "", merchant, flags=re.I)
    merchant = re.sub(r"[\s,]*[0-9][0-9,.]*\s*$", "", merchant)     # drop a trailing amount
    merchant = merchant.strip(" .,-")
    if not merchant:
        merchant = "unknown-merchant"
    return PaymentRequest.build(merchant=merchant.title(), amount=amount, currency=currency,
                                purpose=text.strip()[:120], requested_by="agent")


class Firebreak:
    """Guardrail in front of an agent that wants to spend."""

    def __init__(self, paypal, policy: Policy, ledger_path: str = "firebreak-ledger.jsonl",
                 use_ai: bool = True, mode: str = "orders"):
        self.paypal = paypal
        self.policy = policy
        self.ledger = Ledger(ledger_path)
        self.use_ai = use_ai
        self.mode = mode                      # "orders" (checkout) or "payouts"

    # ── inspection ─────────────────────────────────────────────────────────
    def history(self) -> list[dict]:
        try:
            return self.paypal.list_transactions()
        except PayPalError:
            return []

    def check(self, request: PaymentRequest) -> Decision:
        """Decide only. Records the decision; moves no money."""
        findings = risk_mod.analyze(request, self.history())
        decision = policy_mod.evaluate(self.policy, request, self.history(), findings)
        self.ledger.append("decision", decision.to_dict())
        return decision

    # ── execution ──────────────────────────────────────────────────────────
    def act(self, request: PaymentRequest) -> tuple[Decision, dict | None]:
        """Decide, then act only if the decision permits it.

        AUTO_APPROVE -> execute now.
        ESCALATE     -> prepare the order and stop; a human must confirm.
        BLOCK        -> nothing is created at all.
        """
        decision = self.check(request)

        if decision.blocked:
            self.ledger.append("refused", {"request": request.to_dict(), "reasons": decision.reasons})
            return decision, None

        if self.mode == "payouts":
            if decision.needs_human:
                self.ledger.append("awaiting_human", {"request": request.to_dict(),
                                                      "reasons": decision.reasons})
                return decision, {"status": "AWAITING_HUMAN", "mode": "payouts"}
            result = self.paypal.send_payout(request)
            self.ledger.append("executed", {"request": request.to_dict(), "result": result,
                                            "approved_by": "policy"})
            return decision, result

        # orders mode
        order = self.paypal.create_order(request)
        if decision.needs_human:
            self.ledger.append("awaiting_human", {
                "order_id": order.get("id"), "request": request.to_dict(),
                "reasons": decision.reasons,
                "approve_url": self.paypal.approve_url(order)})
            return decision, order

        # auto-approved: proceed to capture (in sandbox the payer still consents)
        captured = self.paypal.capture_order(order["id"])
        self.ledger.append("executed", {"order_id": order.get("id"), "request": request.to_dict(),
                                        "result": captured, "approved_by": "policy"})
        return decision, captured

    def confirm(self, order_id: str, approved_by: str = "human") -> dict:
        """Complete a payment a human has explicitly approved. Records who did it."""
        try:
            result = self.paypal.capture_order(order_id)
        except PayPalError as exc:
            self.ledger.append("approval_failed", {"order_id": order_id, "error": str(exc)})
            raise
        self.ledger.append("executed", {"order_id": order_id, "result": result,
                                        "approved_by": approved_by})
        return result

    def audit(self) -> tuple[bool, list[str]]:
        return self.ledger.verify()


def policy_from_text(text: str, use_ai: bool = True) -> Policy:
    return policy_mod.compile_policy(text, use_ai=use_ai)
