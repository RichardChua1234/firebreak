"""Thin, dependency-free LLM client for the *interpretive* steps only.

Firebreak uses a model for exactly three things, all of which are judgement calls
about language rather than decisions about money:

1. turning a payment request in English into a structured intent,
2. compiling a plain-English spending policy into enforceable rules,
3. writing the human-readable "why" behind a risk finding.

The decision itself is never delegated to a model -- see :mod:`firebreak.policy`.

Works with any OpenAI-compatible endpoint. Point it at OpenRouter, a local
server, or nothing at all: with no key configured every AI step falls back to the
deterministic path and the guardrail still works end to end.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class AIUnavailable(RuntimeError):
    """No usable model configured -- callers fall back to deterministic logic."""


def _config() -> tuple[str, str, str]:
    base = (os.environ.get("FIREBREAK_LLM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "").rstrip("/")
    key = (os.environ.get("FIREBREAK_LLM_API_KEY")
           or os.environ.get("OPENAI_API_KEY")
           or os.environ.get("OPENROUTER_API_KEY")
           or "")
    if not base and os.environ.get("OPENROUTER_API_KEY"):
        base = "https://openrouter.ai/api/v1"
    if not base and key:
        base = "https://api.openai.com/v1"
    model = os.environ.get("FIREBREAK_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or ""
    if not model:
        model = "deepseek/deepseek-v4.1-flash" if "openrouter" in base else "gpt-4o-mini"
    return base, key, model


def available() -> bool:
    base, key, _ = _config()
    return bool(base and key)


def chat_json(system: str, user: str, *, timeout: int = 60) -> dict:
    """Ask the model for a JSON object. Raises :class:`AIUnavailable` if unset."""
    base, key, model = _config()
    if not base or not key:
        raise AIUnavailable("no LLM configured (FIREBREAK_LLM_BASE_URL / _API_KEY)")

    body = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            doc = json.loads(resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as exc:
        raise AIUnavailable(f"LLM HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:200]}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AIUnavailable(f"LLM unreachable: {exc}") from None

    content = (doc.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise AIUnavailable("empty completion")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # tolerate a model that wraps JSON in prose or fences
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end > start:
            return json.loads(content[start:end + 1])
        raise AIUnavailable(f"model did not return JSON: {content[:200]}") from None
