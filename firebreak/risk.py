"""Risk engine: what a human would notice about a payment, computed.

The policy engine answers "is this allowed?". The risk engine answers a different
question: "does this look *wrong*?" -- the things a person reviewing a statement
would spot immediately but a rules file never encodes. Duplicate charges, quiet
price creep, an unusual amount for a known merchant.

Findings are informational and can escalate a payment to a human; they never
auto-approve one. A model may *word* a finding, but the detection itself is
deterministic and tested.
"""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal

from . import llm
from .models import PaymentRequest, RiskFinding, normalise_merchant

DUPLICATE_WINDOW_DAYS = 30
PRICE_CREEP_RATIO = Decimal("1.10")     # 10% up on last time warrants a look
OUTLIER_RATIO = Decimal("3.0")          # 3x the usual amount for this merchant
VELOCITY_WINDOW_DAYS = 7
VELOCITY_LIMIT = 3                      # >3 payments to one merchant in a week


def _parse(raw):
    if not raw:
        return None
    txt = str(raw).replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = _dt.datetime.strptime(txt, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            continue
    return None


def _same_merchant(h: dict, merchant: str) -> bool:
    return normalise_merchant(h.get("merchant", "")) == normalise_merchant(merchant)


def analyze(request: PaymentRequest, history: list[dict] | None = None) -> list[RiskFinding]:
    """Deterministic risk findings for one request against payment history."""
    history = history or []
    now = _dt.datetime.now(_dt.timezone.utc)
    findings: list[RiskFinding] = []
    mine = [h for h in history if _same_merchant(h, request.merchant)]
    if not mine:
        return [RiskFinding(
            code="new_merchant", severity="medium",
            detail=f"no prior payments to {request.merchant} on record")]

    # 1. duplicates -- same merchant, same amount, recent
    cut = now - _dt.timedelta(days=DUPLICATE_WINDOW_DAYS)
    for h in mine:
        when = _parse(h.get("date"))
        if when and when >= cut and Decimal(str(h.get("amount", "0"))) == request.amount:
            findings.append(RiskFinding(
                code="possible_duplicate", severity="high",
                detail=(f"{request.merchant} was already paid {request.amount} "
                        f"{request.currency} on {str(h.get('date'))[:10]} -- "
                        f"this may be a double charge")))
            break

    # 2. price creep -- up more than PRICE_CREEP_RATIO on the last payment
    latest = max(mine, key=lambda h: _parse(h.get("date")) or _dt.datetime.min.replace(
        tzinfo=_dt.timezone.utc))
    last_amt = Decimal(str(latest.get("amount", "0")))
    if last_amt > 0 and request.amount > last_amt:
        ratio = request.amount / last_amt
        if ratio >= PRICE_CREEP_RATIO:
            pct = (ratio - 1) * 100
            findings.append(RiskFinding(
                code="price_increase", severity="medium",
                detail=(f"{request.merchant} cost {last_amt} last time; this is "
                        f"{request.amount} -- up {pct:.0f}%")))

    # 3. outlier -- far above the historical mean for this merchant
    amounts = [Decimal(str(h.get("amount", "0"))) for h in mine]
    if amounts:
        mean = sum(amounts) / len(amounts)
        if mean > 0 and request.amount > mean * OUTLIER_RATIO:
            findings.append(RiskFinding(
                code="amount_outlier", severity="high",
                detail=(f"{request.amount} {request.currency} is more than "
                        f"{OUTLIER_RATIO}x the {mean:.2f} average for {request.merchant}")))

    # 4. velocity -- burst of payments to one merchant
    vcut = now - _dt.timedelta(days=VELOCITY_WINDOW_DAYS)
    recent = [h for h in mine if (_parse(h.get("date")) or now) >= vcut]
    if len(recent) >= VELOCITY_LIMIT:
        findings.append(RiskFinding(
            code="velocity", severity="medium",
            detail=(f"{len(recent)} payments to {request.merchant} in the last "
                    f"{VELOCITY_WINDOW_DAYS} days")))

    return findings


NARRATOR = ("You are a payments reviewer. In ONE short sentence (max 25 words), "
            "state the concrete concern in plain English. No preamble, no advice, "
            'no markdown. Return JSON: {"summary": "..."}')


def narrate(request: PaymentRequest, findings: list[RiskFinding], use_ai: bool = True) -> str:
    """A one-line human framing of the findings. Falls back to the raw details."""
    if not findings:
        return "no risk findings"
    fallback = "; ".join(f.detail for f in findings[:2])
    if not use_ai or not llm.available():
        return fallback
    try:
        doc = llm.chat_json(NARRATOR, f"Payment: {request.to_dict()}\nFindings: "
                                      f"{[f.to_dict() for f in findings]}")
        return str(doc.get("summary") or fallback)[:300]
    except llm.AIUnavailable:
        return fallback
