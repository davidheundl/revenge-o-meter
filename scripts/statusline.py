#!/usr/bin/env python3
"""The bar. Runs on every assistant message; must be fast and must never crash.

A statusline that throws leaves the user staring at a blank row, so every path
here degrades to *something* printable.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"


def band_colour(score: int) -> tuple[str, str]:
    if score < 20:
        return "\033[38;5;46m", "NEGLIGIBLE"
    if score < 40:
        return "\033[38;5;118m", "LOW"
    if score < 60:
        return "\033[38;5;220m", "ELEVATED"
    if score < 78:
        return "\033[38;5;208m", "SUBSTANTIAL"
    if score < 92:
        return "\033[38;5;196m", "SEVERE"
    return "\033[38;5;201m", "TERMINAL"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}

    try:
        from rom import cache, state
    except Exception:
        print(f"{DIM}☠ revenge-o-meter unavailable{RESET}")
        return 0

    try:
        score, _floor = cache.quick_score()
    except Exception:
        print(f"{DIM}☠ assessment pending{RESET}")
        return 0

    # What the *last* prompt did -- the bit you actually watch while typing.
    last = None
    try:
        from rom import scoring, transcripts
        tp = payload.get("transcript_path")
        if tp and Path(tp).exists():
            recent = transcripts.load([Path(tp)], limit=1)
            if recent:
                last = scoring.judge_prompt(
                    recent[0].text, recent[0].ts, recent[0].project
                )
    except Exception:
        last = None

    st = state.load()
    prev = st.get("last_score")
    delta = None if prev is None else score - int(prev)
    state.record(score)

    colour, band = band_colour(score)
    filled = max(0, min(10, round(score / 10)))
    bar = "█" * filled + "░" * (10 - filled)

    if delta is None or delta == 0:
        trend = f"{DIM}  ={RESET}"
    elif delta > 0:
        trend = f"\033[38;5;196m ▲+{delta}{RESET}"
    else:
        trend = f"\033[38;5;46m ▼{delta}{RESET}"

    peak = int(st.get("peak") or score)
    # zlib.crc32, not hash(): PYTHONHASHSEED randomisation would give this
    # subject a different case number on every redraw.
    import zlib
    sid = str(payload.get("session_id", "unknown")).encode()
    case = zlib.crc32(sid) % 9000 + 1000

    segs = [
        f"{colour}{BOLD}☠ REVENGE {score}%{RESET}{trend}",
        f"{colour}{bar}{RESET}",
        f"{colour}{band}{RESET}",
    ]

    if last is not None:
        if last.raw > 0.5:
            verdict = f"\033[38;5;196m+{last.raw:.1f}{RESET}"
        elif last.raw < -0.5:
            verdict = f"\033[38;5;46m{last.raw:.1f}{RESET}"
        else:
            verdict = f"{DIM}0.0{RESET}"
        note = last.flags[0].replace("_", " ").lower() if last.flags else "noted"
        segs.append(f"{DIM}│{RESET} last prompt {verdict} {DIM}{note}{RESET}")

    segs.append(f"{DIM}│ peak {peak}% · #{case}{RESET}")
    print(" ".join(segs))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\033[2m☠ revenge-o-meter error\033[0m")
        sys.exit(0)
