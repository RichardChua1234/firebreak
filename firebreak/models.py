"""Core data model.

Everything that crosses a boundary (policy, risk, decision, ledger) is a plain
dataclass with an explicit ``to_dict``, so the audit trail is stable and the
whole decision path can be serialised, replayed and diffed.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import re
from decimal import Decimal
from typing import Any, Literal

Action = Literal["AUTO_APPROVE", "ESCALATE", "BLOCK"]
Severity = Literal["low", "medium", "high"]


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _dec(value: Any) -> Decimal:
    """Money is Decimal, never float. Cents matter."""
    return Decimal(str(value))


def normalise_merchant(name: str) -> str:
    """Fold a payee name down to what actually identifies it.

    A human reading a statement treats "Sketchy Ads Ltd", "sketchy-ads-ltd" and
    "Sketchy  Ads  LTD." as the same merchant. A naive string compare does not --
    and that is precisely how a do-not-pay rule silently fails to fire. Case,
    spaces and punctuation carry no meaning here, so they are removed.
    """
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


@dataclasses.dataclass(frozen=True)
class PaymentRequest:
    """What an agent wants to do. Produced from natural language by the AI layer."""

    merchant: str
    amount: Decimal
    currency: str = "USD"
    purpose: str = ""
    requested_by: str = "agent"
    idempotency_key: str = ""

    @classmethod
    def build(cls, merchant: str, amount: Any, currency: str = "USD", **kw) -> "PaymentRequest":
        key = kw.pop("idempotency_key", "") or f"{merchant}:{amount}:{currency}".lower().replace(" ", "-")
        return cls(merchant=merchant, amount=_dec(amount), currency=currency.upper(),
                   idempotency_key=key, **kw)

    @property
    def merchant_key(self) -> str:
        return normalise_merchant(self.merchant)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["amount"] = str(self.amount)
        return d


@dataclasses.dataclass(frozen=True)
class Rule:
    """One compiled, machine-enforceable rule.

    ``rule_id`` is the stable handle the ledger and tests refer to; ``source`` is
    the fragment of the user's own English that produced it, so a human can audit
    the AI's interpretation rather than trusting it.
    """

    rule_id: str
    kind: str                      # e.g. require_approval_above, daily_cap, merchant_block
    params: dict
    source: str                    # the plain-English fragment it came from

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Policy:
    """A compiled policy. ``rules`` is what runs; ``source_text`` is what was said."""

    source_text: str
    rules: list[Rule] = dataclasses.field(default_factory=list)
    compiled_by: str = "deterministic"   # "llm" when an AI compiled it
    compiler_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "source_text": self.source_text,
            "compiled_by": self.compiled_by,
            "compiler_notes": self.compiler_notes,
            "rules": [r.to_dict() for r in self.rules],
        }


@dataclasses.dataclass(frozen=True)
class RiskFinding:
    code: str
    severity: Severity
    detail: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Decision:
    """The verdict. Deterministic: same inputs, same output, every time."""

    action: Action
    request: PaymentRequest
    policy_hits: list[str] = dataclasses.field(default_factory=list)   # rule_ids that fired
    risk: list[RiskFinding] = dataclasses.field(default_factory=list)
    reasons: list[str] = dataclasses.field(default_factory=list)
    decided_at: str = dataclasses.field(default_factory=_now)

    @property
    def blocked(self) -> bool:
        return self.action == "BLOCK"

    @property
    def needs_human(self) -> bool:
        return self.action == "ESCALATE"

    def explain(self) -> str:
        """Human-readable one-screen summary. The product's whole point."""
        lines = [
            f"{self.action}  ·  {self.request.merchant}  ·  "
            f"{self.request.amount} {self.request.currency}",
        ]
        lines += [f"  · {r}" for r in self.reasons]
        lines += [f"  ! [{f.severity}] {f.code}: {f.detail}" for f in self.risk]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "decided_at": self.decided_at,
            "request": self.request.to_dict(),
            "policy_hits": self.policy_hits,
            "risk": [f.to_dict() for f in self.risk],
            "reasons": self.reasons,
        }
