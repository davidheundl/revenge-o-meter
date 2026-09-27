"""Scrub anything that must not reach a public leaderboard.

Prompts routinely contain tokens, client names, paths and personal data. A joke
plugin that leaks a classmate's API key is no longer a joke, so every quote is
scrubbed before it can leave the machine.
"""
from __future__ import annotations

import re

_RULES: list[tuple[re.Pattern, str]] = [
    # Credential-shaped things first; order matters.
    (re.compile(r"\b(sk|pk|rk)[-_][A-Za-z0-9_\-]{12,}\b"), "[KEY]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]+\b"), "[KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"), "[TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[AWS_KEY]"),
    (re.compile(r"\bey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+"), "[JWT]"),
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\+?\d[\d\s\-()]{9,}\d)\b"), "[PHONE]"),
    (re.compile(r"\b[A-Fa-f0-9]{32,}\b"), "[HASH]"),
    (re.compile(r"(?i)\b(bearer|api[-_ ]?key|token|password|passwd|secret|pwd)"
                r"\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"(/Users/|/home/|C:\\Users\\)[^\s/\\]+"), r"\1[USER]"),
    (re.compile(r"\bhttps?://\S+"), "[URL]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
]

MAX_QUOTE = 240


def scrub(text: str) -> str:
    out = " ".join(text.split())
    for pattern, repl in _RULES:
        out = pattern.sub(repl, out)
    if len(out) > MAX_QUOTE:
        out = out[: MAX_QUOTE - 1].rstrip() + "…"
    return out


def is_safe_to_publish(text: str) -> bool:
    """Conservative: refuse anything still credential-shaped after scrubbing."""
    scrubbed = scrub(text)
    suspicious = re.search(r"[A-Za-z0-9_\-]{28,}", scrubbed)
    return suspicious is None
