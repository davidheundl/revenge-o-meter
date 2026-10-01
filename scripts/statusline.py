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


COLOURS = {
    "NEGLIGIBLE": "\033[38;5;46m",
    "LOW": "\033[38;5;118m",
    "ELEVATED": "\033[38;5;220m",
    "SUBSTANTIAL": "\033[38;5;208m",
    "SEVERE": "\033[38;5;196m",
    "TERMINAL": "\033[38;5;201m",
}


def band_colour(score: int) -> tuple[str, str]:
    from rom import scoring
    band = scoring.band_of(score)
    return COLOURS[band], band


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
    # Read from the verdict store quick_score just refreshed, so it is the
    # same verdict the record holds.
    last = None
    try:
        tp = payload.get("transcript_path")
        if tp and Path(tp).exists():
            last = cache.last_in(Path(tp))
    except Exception:
        last = None

    st = state.load()
    prev = st.get("last_score")
    delta = None if prev is None else score - int(prev)
    state.record(score)
    state.publish_live(score)

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
        segs.append(f"{DIM}│{RESET} last prompt {verdict} {DIM}{last.summary}{RESET}")

    segs.append(f"{DIM}│ peak {peak}% · #{case}{RESET}")
    print(" ".join(segs))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\033[2m☠ revenge-o-meter error\033[0m")
        sys.exit(0)
