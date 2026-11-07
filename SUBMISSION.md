# Devpost submission — Firebreak

**Hackathon:** PayPal AI Hackathon — *Build What's Next with PayPal and AI*
**Deadline:** **Nov 12, 2026, 2:00pm PST** = **Nov 13, 06:00 SGT**
**Submit at:** https://paypalaihackathon.devpost.com/
**Repo:** https://github.com/RichardChua1234/firebreak
**Prize pool:** $67,500 · judging Nov 13 – Dec 15 · winners Dec 21

---

## ⛔ Two things only Richard can do

1. **Create a Devpost account and click "Join Hackathon."**
   Per the Official Rules: *"SUBMISSION OF ANY ENTRY CONSTITUTES AGREEMENT TO
   THESE OFFICIAL RULES AS A CONTRACT BETWEEN ENTRANT… THE HACKATHON SPONSOR,
   AND DEVPOST."* The agent will not accept a legal agreement on his behalf.

2. **Create a free PayPal developer sandbox app** at https://developer.paypal.com
   → Apps & Credentials → Sandbox → copy the **client ID** and **secret**.
   These let the agent run the real sandbox path and capture genuine order IDs
   and approval URLs for the demo.

Everything else — code, tests, repo, README, demo, and driving the Devpost form —
is done or automatable by the agent.

---

## Requirement check

| Requirement | Status |
|---|---|
| Integrates the PayPal developer platform, sandbox | ✅ Orders v2 + Payouts v1, stdlib only |
| Uses an AI tool/model | ✅ LLM for intent parsing, policy compilation, risk narration |
| PayPal integration is *central*, not decorative | ✅ the human-approval gate **is** PayPal's payer consent |
| New, or significantly advanced during the window | ✅ written from scratch Nov 7, 2026 |
| Functional demo judges can run | ✅ `python -m firebreak --offline --no-ai demo` — zero installs |
| Setup + run instructions in the repo | ✅ README quickstart |
| Public repo | ✅ |

---

## Devpost form — pre-written answers

**Project name**
Firebreak — a policy-enforced spend guardrail for AI agents

**Elevator pitch (≤200 chars)**
Agents can now move money, and nobody will let them. Firebreak turns a
plain-English spending policy into enforceable rules: AI proposes, deterministic
code disposes. Every decision is audited.

**Inspiration**
2026 is the year agents got wallets. Every demo shows an agent buying something;
almost none show one being *stopped*. The industry's actual blocker isn't
capability, it's trust — and the current options are "block everything" or "hand
it a live card and hope." We wanted the missing middle: let the agent spend
within limits a human wrote, refuse the rest, and leave a record you can audit.
The PayPal platform makes this possible in a way that matters — the human
approval gate is PayPal's own payer consent, so the control is real rather than
simulated.

**What it does**
You write your spending policy as a sentence:

> Never pay more than $50 without asking me. Hard limit of $300 a day and $2000 a
> month. Never pay sketchy-ads-ltd. Only use USD. If I've never paid a merchant
> before, check with me first.

Firebreak compiles it into enforceable rules — and prints the mapping, each rule
annotated with the fragment of your own sentence it came from, so you audit the
interpretation instead of trusting it.

Then, for every payment an agent requests, it returns one of three verdicts:

- **AUTO_APPROVE** — inside every limit
- **ESCALATE** — held for an explicit human decision; nothing moves
- **BLOCK** — refused before anything is created

A risk engine runs alongside the policy: duplicate charges, quiet price creep,
amount outliers, payment velocity. Risk can escalate a payment to a human; it can
never auto-approve one.

Every verdict — including refusals — is appended to a hash-chained,
tamper-evident ledger. Editing history is detectable.

**How we built it**
- **Python standard library only. Zero dependencies.** A judge can clone and run
  it with no `pip install` at all — that was a design constraint, not an accident.
- **PayPal Orders v2** for the checkout path (the human approves in PayPal) and
  **PayPal Payouts v1** for the autonomous path.
- **An explicit AI/non-AI split.** A model is used in exactly three places, all of
  them about language: parsing an English payment request, compiling an English
  policy, and phrasing a risk finding. The decision itself is a pure deterministic
  function of `(policy, request, history)` — same inputs, same verdict, always.
- **39 unit tests**, also dependency-free, covering the awkward cases: the exact
  ceiling boundary, one cent over, block-beats-escalate, risk findings never
  auto-approving, an unapproved order being uncapturable, and both tampering and
  record deletion in the ledger.

**Challenges**
The hardest problem wasn't the payments API — it was deciding where *not* to use
the model. Letting an LLM make the spend decision is the obvious design and the
wrong one: "the model decided" is not an answer anyone accepts when money is
moving, and you cannot unit-test a vibe. Splitting interpretation (AI) from
enforcement (deterministic) is what made the whole thing testable.

Two real bugs were caught by the tests rather than by us. Merchant names were
compared literally, so a do-not-pay rule for `sketchy-ads-ltd` silently failed to
fire against `Sketchy Ads Ltd` — a guardrail that misses on punctuation is worse
than no guardrail. And the risk engine flagged `$50` against a historical `$15` as
a 3.3× outlier, which was *correct* and which our own test had wrongly assumed
should auto-approve.

**Accomplishments**
Telling a payment it may not proceed is the easy half; proving afterwards that you
did so consistently is the half that actually earns trust. A working, testable,
dependency-free guardrail with an auditable chain — and an honest line between what
AI does and what code does — is the part we're proud of.

**What we learned**
Guardrails for agents are a *language* problem wrapped around a *determinism*
problem. The interface has to be English, because that's how humans state intent
about money. The enforcement has to be arithmetic, because that's the only thing
you can audit.

**What's next**
Per-merchant limits, approval routed to Slack/WhatsApp, a pending-approval web UI,
signed ledger entries, and a policy simulator that replays real history against a
candidate policy before you adopt it.

**Built with**
`python`, `paypal-orders-api`, `paypal-payouts-api`, `urllib`, `hashlib`,
`decimal`, `unittest`

---

## Demo evidence to include

`python -m firebreak --offline --no-ai demo` — six requests, six verdicts, ledger
verification, and a live tamper demonstration. Full transcript reproducible in one
command with no credentials.
