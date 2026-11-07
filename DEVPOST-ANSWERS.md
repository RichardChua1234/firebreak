# Devpost questionnaire — every field, answered

Companion to `SUBMISSION.md`. This covers the judge-facing section after Project Story.

---

## ⚠️ Checkboxes — three are unticked and all are required

From the screenshots:

| Checkbox | Status |
|---|---|
| "…from an eligible jurisdiction to compete" (story section) | ✅ ticked |
| "…are **not** employees, representatives nor agents of the Promotion Entities" | ❌ **UNTICKED — tick it** |
| "…at least the age of majority where I reside" | ❌ **UNTICKED — tick it** |
| "…from an eligible jurisdiction to compete" (second one) | ❌ **UNTICKED — tick it** |

You are not a PayPal employee or agent, you are over 18 in Singapore, and Singapore
is eligible. All three are straightforwardly true — just unticked.

---

## `*` Explain how your project meets the main technology requirement

```
PAYPAL TOOLS

1. PayPal Orders v2 API — the human-approval path.
   POST /v2/checkout/orders creates the order for any payment that needs human
   approval; the returned HATEOAS link with rel="approve" is the approval URL
   handed to the person. POST /v2/checkout/orders/{id}/capture then completes it
   — and PayPal itself refuses with HTTP 422 ORDER_NOT_APPROVED until the payer
   has actually consented. That refusal is the entire point of the project: the
   human gate is PayPal's own, not a simulation.

2. PayPal Payouts v1 — the autonomous path, for payments where no per-item
   consent exists by design.

3. PayPal OAuth 2.0 (/v1/oauth2/token) — client-credentials token for every call.

4. PayPal Sandbox (api-m.sandbox.paypal.com) with sandbox business and personal
   test accounts. All development and every claim in this submission were tested
   against the free sandbox environment. No live money was ever involved.

The sandbox integration is real, not stubbed: genuine order IDs, genuine approval
URLs, a genuine 422 from PayPal when capture is attempted without consent, and the
order left in CREATED status because PayPal would not move the money.

AI TOOL

One large language model, reached over any OpenAI-compatible endpoint (I ran
deepseek/deepseek-v4.1-flash via OpenRouter). It does exactly three jobs, all of
them about language:

  a) turning an English payment request into a structured intent,
  b) compiling a plain-English spending policy into enforceable rules,
  c) writing the human-readable "why" behind a risk finding.

It never decides whether a payment proceeds. That decision is a pure deterministic
function of (policy, request, history) — same inputs, same verdict, every time.

Deliberately, the AI is optional: with no model configured, every AI step falls
back to deterministic logic and the guardrail still works end to end. The
requirement is met, but the safety of the system does not rest on the model.
```

## `*` Which additional sponsor tool(s) did you use for this project?

```
None. The project uses only the PayPal developer platform, an LLM, and the Python
standard library.
```

If the field will not accept "none", select whatever equivalent option it offers
and say so — do not claim a tool you did not use.

## `*` Public code repository URL

```
https://github.com/RichardChua1234/firebreak
```

## `*` URL to a working demo, hosted application or test build

```
https://github.com/RichardChua1234/firebreak
```

Firebreak is deliberately a **local CLI**, not a web app — it sits between an agent
and a wallet, so there is nothing to host and no server that should hold your
credentials. The repo *is* the test build: clone it and the demo runs in two
commands with no install, no key and no configuration.

A genuinely browser-hosted alternative, if you would rather give judges a URL that
opens an environment:

```
https://codespaces.new/RichardChua1234/firebreak
```

That opens a ready GitHub Codespace with the repository loaded — they get a terminal
and can run the demo immediately. Caveat: it requires judges to have a GitHub
account, and it spins up a machine for them. The repo URL is the safer default.

## Testing instructions or credentials the judges need

```
No credentials and no install required. The offline demo uses a built-in mock
PayPal, so it runs anywhere with Python 3.10+ and nothing else — the project has
zero third-party dependencies.

  git clone https://github.com/RichardChua1234/firebreak
  cd firebreak
  python -m firebreak --offline demo        # the full guardrail, end to end
  python -m unittest discover -s tests      # 39 tests, all should pass

The demo prints, in order: the policy you wrote in English, the 6 enforceable
rules it compiled with the exact sentence each rule came from, then each payment
verdict (AUTO_APPROVE / ESCALATE / BLOCK) with its reasons, and finally the
hash-chained ledger.

There are deliberately no test credentials to share. The live-sandbox scripts
(live_sandbox_run.py, final_sandbox_evidence.py) expect you to supply your own
sandbox client ID and secret via environment variables. The output of my own live
run against api-m.sandbox.paypal.com is committed as live-evidence.json so the
result is verifiable without handing over my keys.
```

## `*` Which AI tools have you leveraged while working on this project?

```
Two distinct layers, and I want to be precise about both.

1. INSIDE THE PRODUCT — a large language model over any OpenAI-compatible
   endpoint (I ran deepseek/deepseek-v4.1-flash via OpenRouter). Three language
   jobs only: parsing an English payment request, compiling an English spending
   policy, and phrasing the reason behind a risk finding. It never decides
   whether a payment proceeds.

2. TO BUILD THE PROJECT — Hermes Agent (Nous Research), an autonomous agent
   running that same model, which wrote and tested the code under my direction.
   Leonardo AI generated the promotional artwork.

Full disclosure, because it is the most interesting thing about the build: the
product is designed so that the AI is optional. With no model configured, every
AI step falls back to deterministic logic and the guardrail still works end to
end. I built a guardrail with an AI in it and then made sure the guardrail does
not depend on the AI — because a safety mechanism that depends on a model's mood
is not a safety mechanism.
```

## `*` Describe the level of learning you/your team derived from the project

Dropdown — **pick the highest option** (typically "Significant" / "A great deal").
I cannot see the available options, so this is a judgement call for you. The
finding that justifies a high answer is genuinely non-obvious: where exactly to
put the boundary between interpretation and enforcement in an agent system.

## `*` Did you gain AI value that you can use in your career?

Dropdown — **Yes.** It maps directly onto production, evals and governance work:
this is a working example of an AI system with a deterministic core and an audit
trail, which is what agent deployment in a regulated environment actually needs.

## `*` Are you open to us contacting you for additional feedback regarding your experience with integrating PayPal?

Your call — **Yes** is the practical answer (teams that give feedback typically get
early API access, credits and swag). Nothing shared beyond your own experience.

## `*` How would you rate your overall experience integrating PayPal? (1=poor, 10=excellent)

**8.** Strong API, real sandbox fidelity, one clear documentation gap (below).

## `*` Overall experience rating: Please share why or provide additional feedback

```
Strong overall. Orders v2 is clean, and the sandbox behaves like production —
which is the whole reason the project works. Because the sandbox is real, I could
prove the payer-consent rule for real instead of mocking it, and that is not
something you can say about most payment integrations.

Two things cost me real time and are worth fixing:

1. The approval URL is not a top-level field on the create-order response. It is
   buried in the HATEOAS links array under rel="approve". Every integration needs
   that URL — it is the single thing you hand to the human — and every beginner
   will hit the same wall. Surfacing it directly, or documenting it far more
   loudly, would save everybody an hour.

2. The live/sandbox toggle in the dashboard is easy to get wrong, and its failure
   mode is confusing rather than obvious. Given what those credentials are
   attached to, a clearer signal of which environment a key belongs to would
   prevent a genuinely dangerous class of mistake.

Neither is a blocker. And the 422 ORDER_NOT_APPROVED behaviour is excellent
design on its own: the API refuses to move money and says exactly why. That is
precisely the guarantee I built the whole project on top of.
```

## If you used the APIMatic Context Plugin… (optional)

Leave blank — not used.

## If you used AG Grid… (optional)

Leave blank — not used.

---

## Verified facts behind these answers

- LLM: OpenAI-compatible, default `deepseek/deepseek-v4.1-flash` over OpenRouter;
  `firebreak/llm.py` documents the three language-only jobs
- With no key configured every AI step falls back to deterministic logic —
  `llm.available()` gates each call
- Python `>=3.10`; zero third-party dependencies
- Offline demo uses `MockPayPal`, so no credentials are needed to run it
- 39/39 tests pass; 1,887 lines across 12 files in the package and tests
- Live sandbox: order `8RA78568F87831317`, capture refused `ORDER_NOT_APPROVED`
  / HTTP 422, order left `CREATED`, ledger chain OK
