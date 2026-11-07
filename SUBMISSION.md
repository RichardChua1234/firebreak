# Devpost submission — Firebreak ✅ READY TO SUBMIT

**Hackathon:** PayPal AI Hackathon — *Build What's Next with PayPal and AI*
**Submit at:** https://paypalaihackathon.devpost.com/
**Deadline:** **Nov 12, 2026, 2:00pm PST** = **Nov 13, 06:00 SGT**

| Submission input | Value |
|---|---|
| Public repo | https://github.com/RichardChua1234/firebreak |
| Demo video | https://www.youtube.com/watch?v=tJcm_11NUBQ |
| Licence | MIT (auto-detected by GitHub, visible in About) |
| Commit | `8a721ce` |

### Verified before submitting

- Repo is **public**, anonymous read returns HTTP 200
- Licence **MIT**, detected by GitHub and shown in the repo About section
- Video **public** — oEmbed HTTP 200, title *Firebreak*, author *Richard Chua*, and
  **no `noindex` robots tag** (the marker YouTube puts on unlisted videos)
- Video **2m44s** — under the 3-minute limit
- Functional demo runs with **zero installs**: `python -m firebreak --offline demo`
- **39/39 tests pass**; `python -m unittest discover -s tests`
- Real PayPal sandbox integration proven (`ORDER_NOT_APPROVED` on capture without
  payer consent, real order IDs, real approval URLs)

---

## Paste into the Devpost form

**Project name**
```
Firebreak — a policy-enforced spend guardrail for AI agents
```

**Elevator pitch** (≤200 chars)
```
Agents can move money now, and nobody will let them. Firebreak turns a plain-English spending policy into enforceable rules: AI proposes, deterministic code disposes. Every verdict is audited.
```

**Inspiration**
```
2026 is the year agents got wallets. Every demo shows an agent buying something; almost none show one being stopped. The real blocker isn't capability, it's trust — and today's options are "block everything" or "hand it a live card and hope." We wanted the missing middle: let an agent spend inside limits a human wrote, refuse the rest, and leave a record you can audit. PayPal makes that real rather than simulated, because the human-approval gate is PayPal's own payer consent.
```

**What it does**
```
You write your spending policy as a sentence:

"Never pay more than $50 without asking me. Hard limit of $300 a day and $2000 a month. Never pay sketchy-ads-ltd. Only use USD. If I've never paid a merchant before, check with me first."

Firebreak compiles it into enforceable rules — and prints the mapping, each rule annotated with the fragment of your own sentence it came from, so you audit the interpretation instead of trusting it.

Then every payment an agent requests gets one of three verdicts: AUTO_APPROVE (inside every limit), ESCALATE (held for an explicit human decision; nothing moves), or BLOCK (refused before anything is created).

A risk engine runs alongside the policy — duplicate charges, quiet price creep, amount outliers, payment velocity. Risk can escalate a payment to a human; it can never auto-approve one.

Every verdict, including refusals, is appended to a hash-chained tamper-evident ledger. Editing history is detectable, and the demo proves it live.

Against the real PayPal sandbox: a BLOCK verdict creates no order at all, an ESCALATE verdict creates a real order and prints PayPal's own approval URL, and PayPal itself refuses the capture with ORDER_NOT_APPROVED until the payer consents.
```

**How we built it**
```
Python standard library only — zero dependencies, so a judge can clone and run it with no pip install at all. PayPal Orders v2 for the checkout path (the human approves in PayPal) and PayPal Payouts v1 for the autonomous path.

The core design decision was where NOT to use a model. A model is used in exactly three places, all of them about language: parsing an English payment request, compiling an English policy into rules, and phrasing a risk finding. The decision itself is a pure deterministic function of (policy, request, history) — same inputs, same verdict, every time.

39 unit tests, also dependency-free, covering the awkward cases: the exact ceiling boundary, one cent over, block-beats-escalate, risk findings never auto-approving, an unapproved order being uncapturable, and both ledger tampering and record deletion.
```

**Challenges**
```
The hardest problem wasn't the payments API — it was deciding where not to use the model. Letting an LLM make the spend decision is the obvious design and the wrong one: "the model decided" is not an answer anyone accepts when money is moving, and you cannot unit-test a vibe. Splitting interpretation (AI) from enforcement (deterministic) is what made the whole thing testable.

Two real bugs were caught by the tests rather than by us. Merchant names were compared literally, so a do-not-pay rule for "sketchy-ads-ltd" silently failed to fire against "Sketchy Ads Ltd" — a guardrail that misses on punctuation is worse than no guardrail. And the risk engine flagged $50 against a historical $15 as a 3.3x outlier, which was correct and which our own test had wrongly assumed should auto-approve.
```

**Accomplishments**
```
Telling a payment it may not proceed is the easy half; proving afterwards that you did so consistently is the half that earns trust. A working, testable, dependency-free guardrail with a verifiable audit chain — and an honest line between what the AI does and what the code does — is the part we're proud of.
```

**What we learned**
```
Guardrails for agents are a language problem wrapped around a determinism problem. The interface has to be English, because that's how humans state intent about money. The enforcement has to be arithmetic, because that's the only thing you can audit.
```

**What's next**
```
Per-merchant limits, approval routed to Slack/WhatsApp, a pending-approval web UI, signed ledger entries, and a policy simulator that replays real history against a candidate policy before you adopt it.
```

**Built with**
```
python, paypal-orders-api, paypal-payouts-api, urllib, hashlib, decimal, unittest
```

---

## The only remaining step

Click **Submit project** on https://paypalaihackathon.devpost.com/, paste the above,
attach the repo URL and the YouTube URL, and submit.

If the page shows **"Join hackathon"** rather than "Submit project", that click is
still pending — it is the step that accepts the Official Rules, and it must happen
before a submission can be made.
