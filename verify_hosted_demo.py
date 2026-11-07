#!/usr/bin/env python3
"""Load the LIVE hosted demo in a real browser and drive it.

Proves the deployed page actually boots the Python engine and returns verdicts,
rather than just returning HTTP 200.
"""
import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://richardchua1234.github.io/firebreak/"
shot = "/opt/data/paypal-hack/demo/hosted-demo-live.png"

# CloakBrowser's bundled playwright expects build 1248; this box has 1234, so
# point it at the browser that is actually installed instead of downloading one.
import os
EXEC = os.environ.get(
    "CHROME_BIN",
    "/opt/hermes/.playwright/chromium_headless_shell-1234/"
    "chrome-headless-shell-linux64/chrome-headless-shell",
)
if not os.path.exists(EXEC):
    sys.exit(f"no chromium at {EXEC}")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=EXEC)
    page = browser.new_page(viewport={"width": 1280, "height": 1000})

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
            if m.type == "error" else None)

    print(f"opening {URL}")
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)

    # the boot overlay is removed only once Pyodide has loaded AND imported
    print("waiting for the Python engine to boot (Pyodide download)…")
    deadline = time.time() + 240
    booted = False
    while time.time() < deadline:
        if page.query_selector("#boot") is None:
            booted = True
            break
        msg = page.query_selector("#bootmsg")
        if msg:
            print(f"   … {msg.inner_text()[:90]}")
        time.sleep(5)
    print(f"engine booted: {booted}")
    if not booted:
        el = page.query_selector("#bootmsg")
        print("BOOT FAILED:", el.inner_text() if el else "?")
        browser.close()
        sys.exit(1)

    print(f"badge: {page.inner_text('#badge1')}")

    # ── 1. compile the policy ──────────────────────────────────────────
    page.click("#bCompile")
    page.wait_for_timeout(2500)
    print(f"\ncompile status : {page.inner_text('#s1')}")
    rows = page.query_selector_all("#rules table tbody tr")
    print(f"rule rows      : {len(rows)}")
    for r in rows[:6]:
        cells = [c.inner_text().strip() for c in r.query_selector_all("td")]
        print("   " + " | ".join(cells[:3]) + f"  <- {cells[3][:46]}")

    # ── 2. evaluate three cases ────────────────────────────────────────
    print()
    for merchant, amount, label in (("Sketchy Ads Ltd", "120.00", "do-not-pay"),
                                    ("Acme Hosting", "180.00", "over ceiling"),
                                    ("Acme Hosting", "1500.00", "over daily cap")):
        page.fill("#merchant", merchant)
        page.fill("#amount", amount)
        page.click("#bEval")
        page.wait_for_timeout(1800)
        head = page.query_selector(".verdict .vhead")
        print(f"  {merchant:16} {amount:>8} ({label:14}) -> "
              f"{head.inner_text() if head else '??'}")

    # ── 3. ledger + tamper ─────────────────────────────────────────────
    page.click("#bVerify")
    page.wait_for_timeout(1800)
    rows = page.query_selector_all("#ledgerBox table tbody tr")
    chain = page.inner_text("#chainMsg")
    print(f"\nledger entries : {len(rows)}")
    print(f"verify         : {chain.splitlines()[0][:110] if chain else '?'}")

    page.click("#bTamper")
    page.wait_for_timeout(1800)
    chain2 = page.inner_text("#chainMsg")
    print(f"after tamper   : {chain2.splitlines()[0][:130] if chain2 else '?'}")

    page.screenshot(path=shot, full_page=True)
    print(f"\nscreenshot     : {shot}")
    if errors:
        print(f"page errors    : {errors[:3]}")
    else:
        print("page errors    : none")
    browser.close()

ok = len(rows) >= 3 and "BROKEN" in chain2.upper()
print("\nRESULT:", "PASS — live app runs the real engine" if ok else "CHECK NEEDED")
sys.exit(0 if ok else 1)
