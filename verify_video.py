#!/usr/bin/env python3
"""Verify the demo video is public, and that it is the right video."""
import json
import re
import urllib.error
import urllib.request

VID = "tJcm_11NUBQ"
UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"),
      "Accept-Language": "en-US,en;q=0.9"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "ignore")


print(f"video id: {VID}\n")

# 1. oEmbed -> 200 means it exists and is publicly fetchable (401 = private)
print("=== oEmbed ===")
try:
    code, body = get(f"https://www.youtube.com/oembed?url=https://youtu.be/{VID}&format=json")
    d = json.loads(body)
    print(f"  HTTP {code}")
    print(f"  title      : {d.get('title')}")
    print(f"  author     : {d.get('author_name')}")
    print(f"  provider   : {d.get('provider_name')}")
    print(f"  thumb      : {d.get('thumbnail_url', '')[:70]}")
except urllib.error.HTTPError as exc:
    print(f"  HTTP {exc.code} — private or unavailable")
except Exception as exc:
    print(f"  failed: {exc}")

# 2. watch page -> unlisted videos carry a noindex robots meta tag
print("\n=== publicity check (watch page) ===")
try:
    code, html = get(f"https://www.youtube.com/watch?v={VID}")
    print(f"  HTTP {code}, {len(html)} bytes")
    noindex = re.search(r'<meta[^>]+name="robots"[^>]+content="([^"]*)"', html, re.I)
    robots = noindex.group(1) if noindex else "(no robots meta)"
    print(f"  robots meta: {robots}")
    if "noindex" in robots.lower():
        print("  ⚠ UNLISTED — YouTube marks unlisted videos noindex.")
        print("    Rules say 'publicly visible'; flip it to Public.")
    else:
        print("  ✓ no noindex tag -> consistent with a PUBLIC video")
    for tag in ("og:title", "og:video:duration", "itemprop=\"duration\""):
        m = re.search(rf'{tag}[^>]*content="([^"]*)"', html)
        if m:
            print(f"  {tag}: {m.group(1)}")
    m = re.search(r'"lengthSeconds":"(\d+)"', html)
    if m:
        secs = int(m.group(1))
        print(f"  duration   : {secs}s = {secs // 60}m{secs % 60:02d}s "
              f"({'UNDER 3 min OK' if secs < 180 else 'OVER 3 min'})")
    m = re.search(r'"viewCount":"(\d+)"', html)
    if m:
        print(f"  viewCount  : {m.group(1)}")
    m = re.search(r'<title>([^<]+)</title>', html)
    if m:
        print(f"  page title : {m.group(1)[:100]}")
except Exception as exc:
    print(f"  watch page fetch failed: {exc}")

print("\n=== clean URL for the submission form ===")
print(f"  https://www.youtube.com/watch?v={VID}")
print(f"  (or https://youtu.be/{VID} — drop the ?is=... tracking parameter)")
