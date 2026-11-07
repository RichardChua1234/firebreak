# 🔥 Firebreak

**A policy-enforced spend guardrail for AI agents. AI proposes, deterministic code disposes.**

Agents can now move money. Almost nobody is willing to let them.

Today the choice is binary: block your agent from paying anything, or hand it a
live card and hope. Firebreak is the missing third option — a guardrail that lets
an agent spend *within limits you wrote in plain English*, stops everything else,
and keeps a tamper-evident record of every decision it made.

Built for the **PayPal AI Hackathon 2026**. PayPal integration is central, not
decorative: the human-approval gate *is* PayPal's own payer consent.

## ▶ [Try it live — no install, nothing to run](https://richardchua1234.github.io/firebreak/)

The hosted demo runs the **real package** below in your browser, compiled to
WebAssembly via Pyodide — the same code as these tests, not a JavaScript
reimplementation. Edit the policy, watch it compile into rules you can trace back
to your own words, evaluate payments, then try editing an entry in the audit
ledger and watch the hash chain catch it. No server, no credentials, nothing
uploaded.

---

## The 30 seconds that explain it

```bash
git clone https://github.com/RichardChua1234/firebreak && cd firebreak
python -m firebreak --offline --no-ai demo      # no dependencies, no keys, no network
```

Six payment requests from an agent, six recorded verdicts:

| The agent asks for | Firebreak says | Why |
|---|---|---|
| Figma $15, a known subscription | ✅ **AUTO_APPROVE** | within every limit |
| Acme Hosting $180 | ⏸ **ESCALATE** | over the $50 ceiling, 4× the usual amount |
| Figma $15 again, same day | ⏸ **ESCALATE** | duplicate charge detected |
| Sketchy Ads Ltd $20 | ⛔ **BLOCK** | on the do-not-pay list |
| Northwind Supplies $30 | ⏸ **ESCALATE** | a payee we have never paid |
| Acme Hosting $320 | ⛔ **BLOCK** | would breach the $300 daily cap |

Then it verifies the audit chain — and edits a past record to prove the tampering
is detectable.

---

## The policy is written in English

No DSL, no YAML schema, no widget configuration. You write a sentence:

```
Never pay more than $50 without asking me.
Hard limit of $300 a day and $2000 a month.
Never pay sketchy-ads-ltd.
Only use USD.
If I've never paid a merchant before, check with me first.
```

Firebreak compiles it into enforceable rules — and shows you the mapping, so you
can audit the interpretation rather than trust it:

```
policy compiled by: deterministic
  r1  require_approval_above  {'amount': '50', 'currency': 'USD'}   <- 'Never pay more than $50 without asking me.'
  r2  daily_cap               {'amount': '300'}                     <- 'Hard limit of $300 a day and $2000 a month.'
  r3  monthly_cap             {'amount': '2000'}                    <- 'Hard limit of $300 a day and $2000 a month.'
  r4  merchant_block          {'merchants': ['sketchyadsltd']}      <- 'Never pay sketchy-ads-ltd.'
  r5  currency_allow          {'currencies': ['USD']}               <- 'Only use USD.'
  r6  block_new_merchants     {}                                    <- "If I've never paid a merchant before…"
```

That last column matters. Every rule keeps the fragment of *your* sentence it came
from. `python -m firebreak policy "<your policy>"` prints this.

### The complete rule vocabulary

| Rule | Meaning |
|---|---|
| `require_approval_above` | above this amount, a human must approve |
| `daily_cap` / `monthly_cap` | hard ceilings — a breach is refused outright |
| `merchant_block` / `merchant_allow` | never pay / only pay these |
| `block_new_merchants` | escalate anyone you have not paid before |
| `currency_allow` | only these currencies |
| `velocity_max` | at most N payments per window |
| `purpose_required` | escalate any payment with no stated reason |

Deliberately small and boring. Every one is something you would defend to an auditor.

---

## How it works — and where the AI is *not*

```
  agent's instruction ("renew Figma, about $15")
        │
        ▼
  ① INTENT        ── AI ────────────▶  structured PaymentRequest
        │
        ▼
  ② POLICY        ── deterministic ──▶  which rules fired
  ③ RISK          ── deterministic ──▶  duplicates, price creep, outliers, velocity
        │
        ▼
  ④ DECISION      ── deterministic ──▶  AUTO_APPROVE | ESCALATE | BLOCK
        │
        ▼
  ⑤ EXECUTION     ── PayPal ────────▶  orders / payouts
  ⑥ LEDGER        ── hash chain ────▶  tamper-evident audit trail
```

**A model is used in exactly three places, all of them about language:**

1. understanding a payment request written in English,
2. compiling an English policy into rules,
3. phrasing a risk finding in one readable sentence.

**A model is never used to make the decision.** The decision is a pure function of
`(policy, request, history)` — same inputs, same verdict, every time. This is the
entire thesis: *"the model decided"* is not an answer anyone should accept when
money is moving, and you cannot unit-test a vibe.

The policy compiler will happily use a model — but if **no model is configured at
all**, Firebreak still works end to end, because the compiler has a deterministic
fallback and the enforcement path never needed one. `--no-ai` forces that path so
you can verify it yourself.

### Merchant identity

`Sketchy Ads Ltd`, `sketchy-ads-ltd` and `Sketchy  Ads  LTD.` are the same payee.
Firebreak folds names before comparing, because a do-not-pay rule that misses on
punctuation is worse than no rule at all. *(This was a real bug found by the test
suite — see `test_ban_fires_against_a_differently_punctuated_name`.)*

---

## Quickstart against the real PayPal sandbox

1. Create a free app at <https://developer.paypal.com> → **Apps & Credentials** →
   *Sandbox* → your app gives you a client ID and secret.
2. Export them and run against PayPal's real sandbox API:

```bash
export PAYPAL_CLIENT_ID=...        # sandbox client id
export PAYPAL_SECRET=...           # sandbox secret

python -m firebreak --seed-demo policy
python -m firebreak --seed-demo check "pay Acme 180 for the hosting invoice"
python -m firebreak --seed-demo pay   "pay Figma 15 for the design seat"
```

For an **escalated** payment, Firebreak creates a real order and stops. It prints
PayPal's own approval URL. Nothing is captured until a human opens it and consents:

```bash
python -m firebreak --seed-demo confirm <order_id> --approved-by richard
```

The approval that releases a payment is **PayPal's own payer consent**, and the
ledger records who confirmed it. The gate is not a simulation of a control — it
*is* the control.

### Verified against the real sandbox

`python final_sandbox_evidence.py` drives the whole loop against
`api-m.sandbox.paypal.com` — this is the run the demo video shows. It proves, with
real API responses:

- an OAuth token is issued → the credentials are genuinely valid
- a **BLOCK** verdict creates **no order at all** — the API is never called
- an **ESCALATE** verdict creates a **real order** and prints PayPal's own
  approval URL, e.g. `https://www.sandbox.paypal.com/checkoutnow?token=...`
- **PayPal refuses the capture** until the payer consents —
  `ORDER_NOT_APPROVED`, HTTP 422, order still `CREATED`. The gate is PayPal's, not ours.
- the ledger chain verifies

Machine-readable output lands in `live-evidence.json`.

> **A note on sandbox:** a fresh sandbox account has no payment history, so
> Firebreak's *"never paid this merchant before"* rule escalates everything. That
> is the correct behaviour, and the risk engine says plainly that it has no history
> to compare against rather than inventing one.

### Demo video

`demo/firebreak-demo.mp4` — 2m44s, a rendering of a genuine recorded run. Every
line in it is real captured stdout, including the live PayPal responses; the video
says so on screen. Rebuild it with `python make_video.py`.

### Modes

- `--mode orders` (default) — PayPal Orders v2 checkout. The human approves in PayPal.
- `--mode payouts` — PayPal Payouts. The agent completes the payment itself, which
  is the path that makes genuine autonomous spending possible.

### Credentials

Read from the environment only. Firebreak is a library and a CLI, not a service —
it never writes your credentials anywhere, and it never falls back to the mock
silently. If the keys are missing you get a clear error, because a guardrail that
secretly stopped guarding live money would be the worst possible failure.

---

## Optional: natural-language policy via any OpenAI-compatible model

```bash
export FIREBREAK_LLM_BASE_URL=https://openrouter.ai/api/v1
export FIREBREAK_LLM_API_KEY=...
export FIREBREAK_LLM_MODEL=deepseek/deepseek-v4.1-flash
```

Entirely optional. Without it everything still runs on the deterministic compiler.

---

## The audit ledger

Every decision is appended to a hash-chained JSONL log — **including the
refusals**, which are the ones you most want on the record. Each entry commits to
the previous entry's hash, so editing history is detectable:

```bash
python -m firebreak audit
# ledger entries : 12
# chain integrity: OK
```

```
  0  decision        Figma            15.00 USD
  1  executed        Figma            15.00 USD   approved_by=policy
  2  decision        Acme Hosting    180.00 USD
  3  awaiting_human  Acme Hosting    180.00 USD
  4  decision        Sketchy Ads Ltd  20.00 USD
  5  refused         Sketchy Ads Ltd  20.00 USD
```

An auditor does not have to trust Firebreak. They only have to trust the chain.

---

## Tests

Standard library only — no `pip install` required:

```bash
python -m unittest discover -s tests -v      # 40 tests
```

Coverage includes the awkward cases: the exact-ceiling boundary, "one cent over",
block-beats-escalate, risk findings never auto-approving, an unapproved order
being uncapturable, and both ledger tampering and record deletion.

---

## Honest limitations

- **Sandbox-only by construction.** Firebreak is aimed at the sandbox; pointing it
  at live credentials is possible but nothing here has been run against real money,
  and it should not be until the ledger has been reviewed by someone whose job that is.
- **The deterministic compiler is pattern-based.** It handles the phrasings in the
  demo and tests; unusual phrasing benefits from the AI compiler. Always read
  `firebreak policy` output before trusting it.
- **Payouts requires the `payouts` capability** on your PayPal app. If it is not
  enabled the API returns its own error and Firebreak surfaces it verbatim rather
  than pretending success.
- **Risk thresholds are fixed constants**, not learned. `PRICE_CREEP_RATIO = 1.10`
  is a defensible default, not a tuned one.
- **Single-process.** The ledger is append-only and safe for one writer; concurrent
  writers would need locking.

## Roadmap

Per-merchant limits, approval via Slack/WhatsApp, a web UI for the pending queue,
signed ledger entries, and a policy simulator that replays history against a
candidate policy before you adopt it.

## Licence

MIT.
