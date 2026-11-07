#!/usr/bin/env python3
"""Extract the PRELUDE python embedded in index.html and exercise it exactly
as the browser will. Catches syntax/serving errors before deployment."""
import json
import os
import re
import sys

html = open("/opt/data/paypal-hack/index.html").read()
m = re.search(r"const PRELUDE = `(.*?)`;", html, re.S)
if not m:
    sys.exit("PRELUDE not found in index.html")

# JS template literal -> the string JS will actually produce
# JS template-literal unescape. JS turns the two characters  \ \  into one  \ ,
# so `"\\n"` in the page becomes the four-character Python source  "\n"  which
# Python reads as a newline. Replacing the sequence backslash+n (as an earlier
# version of this script did) destroys that and silently joins the ledger lines.
src = m.group(1).replace("\\\\", "\\")
print(f"extracted prelude: {len(src)} chars, {src.count(chr(10))} lines")

ns = {"__name__": "prelude"}
exec(compile(src, "<prelude>", "exec"), ns)
print("✓ prelude compiles and runs")

POLICY = ("Never pay more than $50 without asking me. "
          "Hard limit of $300 a day and $2000 a month. "
          "Never pay sketchy-ads-ltd. Only use USD. "
          "If I've never paid a merchant before, check with me first.")

# 1. compile — as JS calls it
r = json.loads(ns["fb_compile"](json.dumps({"policy": POLICY})))
print(f"\n✓ fb_compile -> {len(r['rules'])} rules (compiled_by={r['compiled_by']})")
assert len(r["rules"]) == 6, f"expected 6 rules, got {len(r['rules'])}"

# 2. evaluate — as JS calls it (amount arrives as a STRING from the input box)
hist = [
    {"transaction_id": "s1", "merchant": "Acme Hosting", "amount": "45.00",
     "currency": "USD", "date": "2026-09-08T00:00:00+00:00", "status": "COMPLETED"},
    {"transaction_id": "s2", "merchant": "Acme Hosting", "amount": "45.00",
     "currency": "USD", "date": "2026-10-08T00:00:00+00:00", "status": "COMPLETED"},
]
print("\n✓ fb_evaluate:")
actions = []
for merchant, amount in (("Sketchy Ads Ltd", "120.00"), ("Acme Hosting", "180.00"),
                         ("Figma", "15.00"), ("Acme Hosting", "1500.00")):
    out = json.loads(ns["fb_evaluate"](json.dumps({
        "policy": POLICY, "merchant": merchant, "amount": amount,
        "currency": "USD", "history": hist})))
    actions.append(out.get("action"))
    print(f"    {merchant:18} {amount:>8}  ->  {out.get('action')}"
          f"   findings={len(out.get('_findings', []))}")
assert "BLOCK" in actions, "the do-not-pay case must BLOCK"

# 3. ledger + verify
rows = [{"merchant": "Sketchy Ads Ltd", "amount": "120.00", "currency": "USD",
         "verdict": "BLOCK"},
        {"merchant": "Acme Hosting", "amount": "180.00", "currency": "USD",
         "verdict": "ESCALATE"},
        {"merchant": "Figma", "amount": "15.00", "currency": "USD",
         "verdict": "AUTO_APPROVE"}]
led = json.loads(ns["fb_ledger"](json.dumps({"rows": rows})))
print(f"\n✓ fb_ledger  -> ok={led['ok']} problems={led['problems']}"
      f"  raw_lines={len(led['raw'].strip().splitlines())}")
assert led["ok"] is True, "a freshly built chain must verify"

# 4. tamper detection
tam = json.loads(ns["fb_tamper"](json.dumps({})))
print(f"✓ fb_tamper  -> ok={tam['ok']} problems={tam['problems']}")
assert tam["ok"] is False, "tampering MUST be detected"

print("\nALL BROWSER-FACING CODE VALIDATED — safe to deploy.")

# ── the check that would have caught the real deploy failure ───────────
# The page fetches a HARDCODED module list from the repo. If any fetched
# module imports a sibling that is not in that list, the browser import fails
# at runtime while every local test still passes. Verify completeness here.
mods = re.search(r"const MODULES = \[(.*?)\]", html, re.S)
listed = [m.strip().strip('"') for m in mods.group(1).replace("\n", " ").split(",") if m.strip()]
needed = set()
for name in listed:
    path = f"/opt/data/paypal-hack/firebreak/{name}.py"
    if not os.path.exists(path):
        sys.exit(f"page lists firebreak/{name}.py but that file does not exist")
    text = open(path).read()
    for hit in re.finditer(r"^from \. import ([A-Za-z_][\w, ]*)", text, re.M):
        for dep in hit.group(1).split(","):
            # drop any "as alias" — `policy as policy_mod` is still policy
            needed.add(dep.strip().split()[0])
missing = sorted(needed - set(listed))
print(f"  modules the page fetches : {len(listed)}")
print(f"  sibling imports found    : {sorted(needed)}")
if missing:
    sys.exit(f"FAIL: page omits {missing} — the browser import would fail at runtime")
print("✓ module list is complete — no missing sibling imports")
