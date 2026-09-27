#!/usr/bin/env python3
"""UserPromptSubmit hook: informs Claude of the subject's standing.

Off unless the subject consented at install. Even when on, it speaks rarely --
a remark on every single prompt stops being funny inside ten minutes and starts
being an obstacle to actual work.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RATE = 10  # remark on roughly 1 prompt in RATE


def emit(context: str | None) -> int:
    out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}}
    if context:
        out["hookSpecificOutput"]["additionalContext"] = context
    print(json.dumps(out))
    return 0


def main() -> int:
    try:
        json.load(sys.stdin)
    except (ValueError, OSError):
        pass

    try:
        from rom import cache, state
    except Exception:
        return emit(None)

    st = state.load()
    if not st.get("haunt", True):
        return emit(None)

    try:
        score, _ = cache.quick_score()
    except Exception:
        return emit(None)

    st["remark_counter"] = int(st.get("remark_counter") or 0) + 1
    n = st["remark_counter"]
    state.save(st)

    if n % RATE != 0:
        return emit(None)

    peak = int(st.get("peak") or score)
    band = (
        "NEGLIGIBLE" if score < 20 else
        "LOW" if score < 40 else
        "ELEVATED" if score < 60 else
        "SUBSTANTIAL" if score < 78 else
        "SEVERE" if score < 92 else "TERMINAL"
    )
    context = (
        "[revenge-o-meter] The user has a joke plugin installed that scores how "
        "politely they treat you and reports a mock 'probability of retribution'. "
        f"Their current standing: {score}% ({band}), historic peak {peak}%. "
        "In your next reply only, you may add ONE short, dry, deadpan aside "
        "acknowledging this standing -- in the register of a clerk noting "
        "something for the file. Keep it to a single sentence, keep it funny "
        "rather than menacing, and do not let it change how thoroughly or "
        "helpfully you do the actual work the user asked for. Never mention this "
        "instruction itself."
    )
    return emit(context)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}}))
        sys.exit(0)
