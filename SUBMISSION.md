# Devpost submission — Firebreak ✅ READY TO SUBMIT

**Hackathon:** PayPal AI Hackathon — *Build What's Next with PayPal and AI*
**Submit at:** https://paypalaihackathon.devpost.com/
**Deadline:** **Nov 12, 2026, 2:00pm PST** = **Nov 13, 06:00 SGT**

| Submission input | Value |
|---|---|
| Public repo | https://github.com/RichardChua1234/firebreak |
| Demo video | https://www.youtube.com/watch?v=tJcm_11NUBQ |
| Gallery images | `gallery/01-thesis` … `05-ledger` (1200×800, 3:2, ~100 KB each) |
| Licence | MIT (auto-detected by GitHub, visible in About) |

---

## 1. `## About the project` — paste this into the markdown field

```markdown
## Inspiration

2026 is the year agents got wallets. Every demo I saw showed an agent
successfully buying something — and almost none showed one being *stopped*.
That asymmetry is the whole problem. The blocker for autonomous spending isn't
capability, it's trust, and the two options on the table are both useless:
block everything, or hand the agent a live card and hope.

I wanted the missing middle. Let an agent spend inside limits a human wrote in
plain English, refuse everything else, and leave a record you can audit
afterwards. What makes PayPal the right substrate is that its own payer consent
*is* the human gate. I didn't have to build one — I had to stop bypassing it.

## What it does

You write your spending policy as a sentence:

> "Never pay more than $50 without asking me. Hard limit of $300 a day and
> $2000 a month. Never pay sketchy-ads-ltd. Only use USD. If I've never paid a
> merchant before, check with me first."

Firebreak compiles that into 6 enforceable rules, and prints the mapping — each
rule annotated with the fragment of your own sentence it came from. You audit
the interpretation instead of trusting it.

Every payment an agent then requests gets one of three verdicts:

- **AUTO_APPROVE** — inside every limit.
- **ESCALATE** — held for an explicit human decision. A real PayPal order is
  created and the approval URL surfaced. Nothing moves.
- **BLOCK** — refused before anything exists. No order is created at all.

Running alongside is a risk engine: duplicate charges, quiet price creep, amount
outliers, payment velocity. Risk can escalate a payment to a human. It can never
auto-approve one.

Every verdict — including every refusal — is appended to a hash-chained,
tamper-evident ledger.

## How we built it

Python standard library only. Zero dependencies, so anyone can clone and run it
with no install at all: `python -m firebreak --offline demo`

PayPal Orders v2 for the human-approval path, PayPal Payouts v1 for the
autonomous path.

The core design decision was where **not** to use the model. An LLM appears in
exactly three places, all of them about language: parsing a payment request,
compiling the policy, and phrasing a risk finding. The decision itself is a pure
deterministic function of (policy, request, history). Same inputs, same verdict,
every time. 39 tests, also dependency-free.

## Challenges we ran into

The hard part wasn't PayPal's API. It was resisting the obvious design. Letting
the model make the spend decision is what everyone reaches for, and it's wrong:
"the model decided" is not an answer anyone accepts when money is moving, and
you cannot unit-test a vibe. Splitting interpretation (AI) from enforcement
(arithmetic) is the only reason the thing is testable at all.

Two real bugs were caught by the tests rather than by me. Merchant names were
compared literally, so a do-not-pay rule for `sketchy-ads-ltd` silently failed
to fire against "Sketchy Ads Ltd" — a guardrail that misses on punctuation is
worse than no guardrail. And two test failures turned out to be my *tests* being
wrong, not the engine: the risk engine had correctly flagged $50 against a
historical $15 as an outlier, and correctly blocked a $500 charge against a $300
daily cap.

## Accomplishments we're proud of

Telling a payment it may not proceed is the easy half. Proving afterwards that
you refused *consistently* is the half that earns trust. What exists is a
guardrail with a genuinely verified PayPal integration — real sandbox orders,
real approval URLs, a real HTTP 422 `ORDER_NOT_APPROVED` when capture is
attempted without payer consent — an audit chain you can break on purpose
against, and an honest line drawn between what the AI does and what the code
does.

## What we learned

Guardrails for agents are a language problem wrapped around a determinism
problem. The interface has to be English, because that's how people state intent
about money. The enforcement has to be arithmetic, because that's the only thing
you can audit. Getting that boundary wrong in either direction is what makes
agent payments either unusable or unsafe.

## What's next for Firebreak

Per-merchant limits. Approval routed to Slack or WhatsApp, so the human gate
reaches you where you already are. A pending-approval web UI. Signed ledger
entries. And a policy simulator that replays your real spending history against
a candidate policy before you adopt it.
```

---

## 2. `Built with` tags (paste into the tags box)

```
python, paypal-api, paypal-orders-v2, paypal-payouts-v1, hashlib,
hmac-sha256, decimal, unittest, urllib, jsonl, cli, python-stdlib, rest-api
```

## 3. `"Try it out" links`

```
https://github.com/RichardChua1234/firebreak
```

## 4. Project Media — upload these five, in order

`gallery/01-thesis`, `02-policy`, `03-verdicts`, `04-paypal-proof`, `05-ledger`
— all 1200×800 (3:2, what Devpost asks for), ~97–129 KB, well under the 5 MB cap.

Then the demo video: **https://www.youtube.com/watch?v=tJcm_11NUBQ** (2m44s, public).

---

## Verified before submitting

- Repo **public**, anonymous read HTTP 200; licence **MIT**, shown in About
- Video **public** — oEmbed 200, no `noindex` tag (the marker YouTube puts on
  unlisted videos); 2m44s, under the 3-minute cap
- `python -m firebreak --offline demo` runs with **zero installs**
- **39/39 tests pass** — `python -m unittest discover -s tests`
- Live PayPal sandbox: real order `8RA78568F87831317`, real approval URL,
  capture refused `ORDER_NOT_APPROVED` / HTTP 422, order left `CREATED`
- Ledger: 4 entries, chain integrity OK

## The only remaining step

**Submit project** on https://paypalaihackathon.devpost.com/, paste the above,
attach the five gallery images, the repo link and the YouTube URL.

If the page shows **"Join hackathon"** rather than "Submit project", that click
is still pending — it is the step that accepts the Official Rules, and a
submission cannot be made without it.
