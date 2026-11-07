"""Firebreak — a policy-enforced spend guardrail for AI agents.

The design principle is one line: **AI proposes, deterministic code disposes.**

AI is used where it is genuinely good (understanding a payment request in
natural language, compiling a plain-English policy into rules, explaining risk),
and is deliberately NOT used for the decision itself. The enforcement path is
deterministic, auditable and testable, because "the model decided" is not an
acceptable answer when money is moving.
"""

__version__ = "0.1.0"
