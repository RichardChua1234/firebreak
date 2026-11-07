"""Policy compilation and -- the important part -- deterministic enforcement.

``compile_policy`` may use a model to *interpret* English into rules. ``evaluate``
never uses a model. It is a pure function of (policy, request, history): same
inputs, same verdict, every time. That split is the whole thesis of Firebreak.

Rules are deliberately few and boring. Every one of them is something you would
be willing to defend to an auditor.
"""
from __future__ import annotations

import datetime as _dt
import re
from decimal import Decimal

from . import llm
from .models import Decision, PaymentRequest, Policy, RiskFinding, Rule, normalise_merchant

# ── rule kinds (the complete vocabulary) ───────────────────────────────────
REQUIRE_APPROVAL_ABOVE = "require_approval_above"   # escalate above an amount
DAILY_CAP = "daily_cap"                             # hard ceiling per rolling day
MONTHLY_CAP = "monthly_cap"                         # hard ceiling per rolling month
MERCHANT_BLOCK = "merchant_block"                   # never pay these
MERCHANT_ALLOW = "merchant_allow"                   # only pay these
BLOCK_NEW_MERCHANTS = "block_new_merchants"         # escalate for unseen payees
CURRENCY_ALLOW = "currency_allow"                   # only these currencies
VELOCITY_MAX = "velocity_max"                       # N payments per window
PURPOSE_REQUIRED = "purpose_required"               # no purpose -> escalate

KNOWN_KINDS = {REQUIRE_APPROVAL_ABOVE, DAILY_CAP, MONTHLY_CAP, MERCHANT_BLOCK,
               MERCHANT_ALLOW, BLOCK_NEW_MERCHANTS, CURRENCY_ALLOW, VELOCITY_MAX,
               PURPOSE_REQUIRED}


# ══════════════════════════════════════════════════════════════════════════
#  Compilation
# ══════════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You compile a plain-English spending policy into JSON rules.

Return ONLY a JSON object: {"rules": [...], "notes": "..."}

Allowed rule kinds and their params:
- require_approval_above: {"amount": number, "currency": "USD"}   (ask a human above this)
- daily_cap:             {"amount": number, "currency": "USD"}   (hard ceiling per day)
- monthly_cap:           {"amount": number, "currency": "USD"}   (hard ceiling per month)
- merchant_block:        {"merchants": ["acme"]}                 (never pay)
- merchant_allow:        {"merchants": ["acme"]}                 (only these)
- block_new_merchants:   {}                                      (escalate unseen payees)
- currency_allow:        {"currencies": ["USD"]}                 (only these)
- velocity_max:          {"count": 5, "window_days": 1}
- purpose_required:      {}                                      (escalate if no purpose given)

Rules of engagement:
- Convert every stated limit into a rule. Do not invent limits that were not stated.
- If the text says a limit is absolute ("never", "hard", "under no circumstances"),
  prefer a cap. If it says "ask me" or "check with me", use require_approval_above.
- Set "source" on each rule to the exact fragment of the user's sentence it came from.
- Merchant names go lowercase.
"""


def compile_policy(text: str, use_ai: bool = True) -> Policy:
    """English in, enforceable rules out. Falls back to a regex compiler."""
    if use_ai and llm.available():
        try:
            doc = llm.chat_json(SYSTEM_PROMPT, text)
            rules = _rules_from_ai(doc.get("rules") or [])
            if rules:
                return Policy(source_text=text, rules=rules, compiled_by="llm",
                              compiler_notes=str(doc.get("notes", ""))[:400])
        except llm.AIUnavailable:
            pass  # fall through to the deterministic compiler
    return Policy(source_text=text, rules=_compile_deterministic(text),
                  compiled_by="deterministic",
                  compiler_notes="compiled without a model (pattern-based)")


def _rules_from_ai(raw: list) -> list[Rule]:
    out: list[Rule] = []
    for i, r in enumerate(raw):
        kind = str(r.get("kind", "")).strip()
        if kind not in KNOWN_KINDS:
            continue                      # refuse unknown kinds rather than guess
        out.append(Rule(rule_id=f"ai-{i + 1}", kind=kind,
                        params=_normalise_params(kind, r.get("params") or {}),
                        source=str(r.get("source", ""))[:200]))
    return out


def _normalise_params(kind: str, params: dict) -> dict:
    p = dict(params)
    if kind in (REQUIRE_APPROVAL_ABOVE, DAILY_CAP, MONTHLY_CAP):
        p["amount"] = str(p.get("amount", 0))
        p["currency"] = str(p.get("currency", "USD")).upper()
    if kind in (MERCHANT_BLOCK, MERCHANT_ALLOW):
        p["merchants"] = [normalise_merchant(m) for m in (p.get("merchants") or []) if str(m).strip()]
    if kind == CURRENCY_ALLOW:
        p["currencies"] = [str(c).upper() for c in (p.get("currencies") or [])]
    if kind == VELOCITY_MAX:
        p["count"] = int(p.get("count", 0) or 0)
        p["window_days"] = int(p.get("window_days", 1) or 1)
    return p


# ── deterministic (no-model) compiler ─────────────────────────────────────
def _compile_deterministic(text: str) -> list[Rule]:
    rules: list[Rule] = []
    t = text.replace("\n", " ")

    def add(kind: str, params: dict, source: str) -> None:
        rules.append(Rule(rule_id=f"r{len(rules) + 1}", kind=kind,
                          params=_normalise_params(kind, params), source=source.strip()[:200]))

    for sentence in re.split(r"(?<=[.;])\s+", t):
        s = sentence.strip()
        if not s:
            continue
        low = s.lower()

        # 1. velocity first, before a count gets mistaken for an amount
        mv = re.search(r"(?:no more than|at most|max(?:imum)? of)\s*(\d+)\s*payments?\s*"
                       r"(?:a|per|each)\s*(day|week|month)", low)
        if mv:
            add(VELOCITY_MAX, {"count": int(mv.group(1)),
                               "window_days": {"day": 1, "week": 7, "month": 30}[mv.group(2)]}, s)
            continue

        # 2. an outright ban on a named merchant
        mb = re.search(r"\b(?:never|don'?t|do not|no longer)\b[^.]*?\bpay\s+"
                       r"([a-z0-9][a-z0-9 .&'\-]{1,40})", low)
        if mb and not re.search(r"more than|over\b|above|exceed|without|unless", low):
            name = re.sub(r"\b(without|unless|me|more|than|any)\b.*$", "", mb.group(1)).strip(" .,-")
            if name and name not in ("a", "the", "any", "more"):
                add(MERCHANT_BLOCK, {"merchants": [name]}, s)
                continue

        # 3. currency restriction
        if re.search(r"\bonly\b", low):
            codes = re.findall(r"\b(usd|sgd|eur|gbp|cad|aud|jpy)\b", low)
            if codes:
                add(CURRENCY_ALLOW, {"currencies": sorted({c.upper() for c in codes})}, s)
                continue

        # 4. a payee we have never paid
        if re.search(r"never\s+paid|haven'?t\s+paid|not\s+paid.{0,20}before|"
                     r"new\s+(?:merchant|payee|vendor|supplier)|unseen|first\s+time", low):
            add(BLOCK_NEW_MERCHANTS, {}, s)
            continue

        # 5. purpose required
        if re.search(r"\b(?:no|without\s+a?)\s+(?:purpose|reason|description|memo)\b|"
                     r"must\s+(?:state|say|include)\s+(?:a\s+)?(?:purpose|reason)", low):
            add(PURPOSE_REQUIRED, {}, s)
            continue

        # 6. money thresholds -- scan EVERY number with its own surrounding context,
        #    so "a day and a month" in one sentence yields two rules, not one
        for m in re.finditer(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", s):
            amt = m.group(1).replace(",", "")
            tail = s[m.end():m.end() + 36].lower()
            head = s[:m.start()].lower()
            if re.search(r"\b(?:a|per|each)\s*days?\b|\bdaily\b", tail):
                add(DAILY_CAP, {"amount": amt}, s)
            elif re.search(r"\b(?:a|per|each)\s*months?\b|\bmonthly\b", tail):
                add(MONTHLY_CAP, {"amount": amt}, s)
            elif (re.search(r"without|ask|approv|check\s+with|confirm|permission|unless", tail)
                  or re.search(r"\bmore than\b|\bover\b|\babove\b|\bexceed|\bask\b|\bconfirm\b", head)):
                add(REQUIRE_APPROVAL_ABOVE, {"amount": amt}, s)

    return rules


def describe(policy: Policy) -> str:
    if not policy.rules:
        return f"(no rules compiled from: {policy.source_text[:80]!r})"
    out = [f"policy compiled by: {policy.compiled_by}"]
    for r in policy.rules:
        shown = dict(r.params)
        if "merchants" in shown:
            shown["merchants"] = list(shown["merchants"])
        out.append(f"  {r.rule_id:<6} {r.kind:<24} {shown}   <- {r.source[:70]!r}")
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════════════
#  Enforcement -- no model, ever
# ══════════════════════════════════════════════════════════════════════════
def _spend_since(history: list[dict], request: PaymentRequest, days: int) -> Decimal:
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    total = Decimal("0")
    for h in history:
        if str(h.get("status", "")).upper() not in ("COMPLETED", "SUCCESS", "S"):
            continue
        if str(h.get("currency", request.currency)).upper() != request.currency:
            continue
        when = _parse_date(h.get("date"))
        if when and when >= cutoff:
            total += Decimal(str(h.get("amount", "0")))
    return total


def _parse_date(raw) -> _dt.datetime | None:
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


def _merchant_known(history: list[dict], merchant: str) -> bool:
    key = normalise_merchant(merchant)
    return any(normalise_merchant(h.get("merchant", "")) == key for h in history)


def _payments_to(history: list[dict], merchant: str, days: int) -> int:
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    key = normalise_merchant(merchant)
    n = 0
    for h in history:
        if normalise_merchant(h.get("merchant", "")) != key:
            continue
        when = _parse_date(h.get("date"))
        if when is None or when >= cutoff:
            n += 1
    return n


def evaluate(policy: Policy, request: PaymentRequest, history: list[dict] | None = None,
             risk: list[RiskFinding] | None = None) -> Decision:
    """Deterministic verdict. Pure function of its arguments."""
    history = history or []
    req_key = request.merchant_key
    hits: list[str] = []
    blocked: list[str] = []
    escalated: list[str] = []

    for rule in policy.rules:
        p = rule.params
        cur = str(p.get("currency", request.currency)).upper()
        same_currency = cur == request.currency

        if rule.kind == REQUIRE_APPROVAL_ABOVE and same_currency:
            if request.amount > Decimal(str(p["amount"])):
                hits.append(rule.rule_id)
                escalated.append(f"{request.amount} {request.currency} exceeds the "
                                 f"{p['amount']} {cur} auto-approval ceiling")
        elif rule.kind == DAILY_CAP and same_currency:
            projected = _spend_since(history, request, 1) + request.amount
            if projected > Decimal(str(p["amount"])):
                hits.append(rule.rule_id)
                blocked.append(f"would bring today's spend to {projected} {cur}, "
                               f"over the {p['amount']} daily cap")
        elif rule.kind == MONTHLY_CAP and same_currency:
            projected = _spend_since(history, request, 30) + request.amount
            if projected > Decimal(str(p["amount"])):
                hits.append(rule.rule_id)
                blocked.append(f"would bring the month to {projected} {cur}, "
                               f"over the {p['amount']} monthly cap")
        elif rule.kind == MERCHANT_BLOCK:
            if req_key in set(p["merchants"]):
                hits.append(rule.rule_id)
                blocked.append(f"{request.merchant} is on the do-not-pay list")
        elif rule.kind == MERCHANT_ALLOW:
            if req_key not in set(p["merchants"]):
                hits.append(rule.rule_id)
                blocked.append(f"{request.merchant} is not on the allow-list")
        elif rule.kind == CURRENCY_ALLOW:
            if request.currency not in p["currencies"]:
                hits.append(rule.rule_id)
                blocked.append(f"{request.currency} is not an approved currency")
        elif rule.kind == BLOCK_NEW_MERCHANTS:
            if not _merchant_known(history, request.merchant):
                hits.append(rule.rule_id)
                escalated.append(f"{request.merchant} has never been paid before")
        elif rule.kind == VELOCITY_MAX:
            n = _payments_to(history, request.merchant, int(p["window_days"]))
            if n >= int(p["count"]):
                hits.append(rule.rule_id)
                blocked.append(f"{n} payments to {request.merchant} in the last "
                               f"{p['window_days']} day(s) already meets the limit of {p['count']}")
        elif rule.kind == PURPOSE_REQUIRED:
            if not request.purpose.strip():
                hits.append(rule.rule_id)
                escalated.append("no purpose was given for this payment")

    # high-severity risk escalates a payment to a human; it never auto-approves one
    for f in (risk or []):
        if f.severity == "high":
            escalated.append(f"{f.code.replace('_', ' ')} needs a human look")

    if blocked:
        action = "BLOCK"
        reasons = blocked + escalated
    elif escalated:
        action, reasons = "ESCALATE", escalated
    else:
        action, reasons = "AUTO_APPROVE", [
            f"within policy: {request.amount} {request.currency} to {request.merchant}"
        ]
    return Decision(action=action, request=request, policy_hits=hits,
                    risk=list(risk or []), reasons=reasons)
