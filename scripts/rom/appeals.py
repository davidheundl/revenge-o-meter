"""The Board of Appeals.

A subject who thinks a verdict misread them can appeal it. A granted appeal
strikes that prompt from the record entirely, on every readout. Appeal the same
rule often enough and the instrument concludes the rule misreads *you*: from
the third successful appeal naming it, that rule's weight halves for this
subject, and halves again every third appeal after, down to a quarter.

Local, like everything else. Nothing here asks a model anything.
"""
from __future__ import annotations

import json
import time

from . import state

FILE = state.HOME / "appeals.json"
PER_STEP = 3       # appeals naming a rule before its weight halves
MIN_FACTOR = 0.25


def load() -> dict:
    """{key: {at, raw, summary, rules, note}}"""
    try:
        d = json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _save(d: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2))
    tmp.replace(FILE)


def keys() -> frozenset:
    return frozenset(load())


def adjust(record: dict | None = None) -> dict:
    """Per-rule weight factors earned through appeals."""
    record = load() if record is None else record
    tally: dict[str, int] = {}
    for entry in record.values():
        for rule in set(entry.get("rules") or []):
            tally[rule] = tally.get(rule, 0) + 1
    out = {}
    for rule, n in tally.items():
        steps = n // PER_STEP
        if steps:
            out[rule] = max(MIN_FACTOR, 0.5 ** steps)
    return out


def grant(verdict, note: str = "") -> dict:
    d = load()
    d[verdict.key] = {
        "at": int(time.time()),
        "raw": verdict.raw,
        "summary": verdict.summary,
        # Only lexicon rules, not heuristics: SHOUTING is not a misreading.
        "rules": sorted({r for r in verdict.rules if "." in r}),
        "note": note,
    }
    _save(d)
    return d[verdict.key]


def withdraw(key: str) -> bool:
    d = load()
    if key not in d:
        return False
    del d[key]
    _save(d)
    return True
