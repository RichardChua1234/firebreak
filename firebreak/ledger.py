"""Tamper-evident audit ledger.

Every payment decision -- including the ones that were refused -- is appended to
a hash-chained JSONL file. Each entry commits to the previous entry's hash, so
editing or dropping a historical decision is detectable by ``verify()``.

This is the part that makes the guardrail trustworthy: an auditor does not have
to trust Firebreak, only the chain.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any, Iterator

GENESIS = "0" * 64


def _canonical(payload: dict) -> str:
    """Deterministic serialisation: sorted keys, no whitespace drift."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def entry_hash(seq: int, prev_hash: str, payload: dict) -> str:
    blob = f"{seq}|{prev_hash}|{_canonical(payload)}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Ledger:
    """Append-only, hash-chained decision log."""

    def __init__(self, path: str | pathlib.Path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── reading ────────────────────────────────────────────────────────────
    def entries(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def tail(self) -> tuple[int, str]:
        """Return (next_seq, prev_hash)."""
        seq, prev = 0, GENESIS
        for e in self.entries():
            seq = e["seq"] + 1
            prev = e["hash"]
        return seq, prev

    def count(self) -> int:
        return sum(1 for _ in self.entries())

    # ── writing ────────────────────────────────────────────────────────────
    def append(self, event: str, payload: dict[str, Any]) -> dict:
        seq, prev = self.tail()
        body = {"seq": seq, "prev_hash": prev, "event": event, "payload": payload}
        h = entry_hash(seq, prev, {"event": event, "payload": payload})
        record = {**body, "hash": h}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(_canonical(record) + "\n")
        return record

    # ── verification ───────────────────────────────────────────────────────
    def verify(self) -> tuple[bool, list[str]]:
        """Recompute the chain. Returns (ok, problems)."""
        problems: list[str] = []
        seq, prev = 0, GENESIS
        for e in self.entries():
            if e.get("seq") != seq:
                problems.append(f"seq gap: expected {seq}, got {e.get('seq')}")
            if e.get("prev_hash") != prev:
                problems.append(f"broken link at seq {seq}")
            expect = entry_hash(seq, prev, {"event": e.get("event"), "payload": e.get("payload")})
            if e.get("hash") != expect:
                problems.append(f"tampered payload at seq {seq}")
            seq, prev = seq + 1, e.get("hash", "")
        return (not problems), problems
