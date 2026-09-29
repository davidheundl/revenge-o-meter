#!/usr/bin/env python3
"""SwiftBar/xbar renderer: the bar for people who are not in a terminal.

The Claude Code desktop app runs its embedded CLI with `--output-format
stream-json`, so there is no TUI footer for a `statusLine` to draw into. The
command still runs -- its stdout is simply discarded. The menu bar is the one
place a persistent readout survives outside the terminal.

Output is SwiftBar's plugin format: the first line is the menu bar title, `---`
opens the dropdown, `-- ` indents a submenu, and `| key=value` sets per-line
options.

Read-only by design. This runs on a timer, and `state.record()` would overwrite
`last_score` on every refresh -- destroying the "since your last prompt" delta
the status line shows -- and bury the history under idle readings.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# (light, dark): the xterm colours the status line uses are unreadable on a
# light menu bar, so each band carries a darkened twin for that case.
BANDS = {
    "NEGLIGIBLE":  ("#0f7a0f", "#5cff5c"),
    "LOW":         ("#4f7a00", "#a6ff4f"),
    "ELEVATED":    ("#8a6d00", "#ffd700"),
    "SUBSTANTIAL": ("#a65200", "#ff9d3d"),
    "SEVERE":      ("#b00000", "#ff5c5c"),
    "TERMINAL":    ("#a000a0", "#ff66ff"),
}
GREY = "#6e6e6e,#9a9a9a"
MONO = "font=Menlo size=13"


def clean(text: str) -> str:
    """`|` opens SwiftBar's parameter list, so it can never appear in a label."""
    return str(text).replace("|", "¦").replace("\n", " ").strip()


def row(text: str, *params: str) -> str:
    line = clean(text)
    return f"{line} | {' '.join(params)}" if params else line


def colour(band: str) -> str:
    light, dark = BANDS.get(band, (GREY.split(",")[0], GREY.split(",")[1]))
    return f"color={light},{dark}"


def meter(score: int, width: int = 10) -> str:
    filled = max(0, min(width, round(score / (100 / width))))
    return "█" * filled + "░" * (width - filled)


def fallback(message: str) -> int:
    print(row("☠ --", f"color={GREY}"))
    print("---")
    print(row(message, f"color={GREY}", "size=12"))
    return 0


def main() -> int:
    try:
        from rom import report, scoring, state, transcripts
    except Exception as exc:
        return fallback(f"revenge-o-meter nicht ladbar: {exc}")

    try:
        a = scoring.assess(transcripts.load())
    except Exception as exc:
        return fallback(f"Auswertung fehlgeschlagen: {exc}")

    st = state.load()
    band = a.band
    tint = colour(band)
    peak = max(int(st.get("peak") or 0), a.revenge)

    # --- menu bar title: short enough to live next to everything else ---
    print(row(f"☠ {a.revenge}%", tint, "font=Menlo size=14", "symbolize=false"))
    print("---")

    # --- headline ---
    print(row(f"☠ REVENGE {a.revenge}% · {band}", tint, MONO, "symbolize=false"))
    print(row(f"{meter(a.revenge)}  Peak {peak}%", tint, MONO))
    note = getattr(report, "_BANDS", {}).get(band)
    if note:
        print(row(note, f"color={GREY}", "size=12"))
    print("---")

    # --- the axes, worst first: this is the part worth looking at ---
    axes = sorted(a.axis_totals.items(), key=lambda kv: -abs(kv[1]))
    live = [(k, v) for k, v in axes if abs(v) >= 0.01]
    if live:
        print(row("Achsen", f"color={GREY}", "size=12"))
        for key, value in live:
            aggravating = getattr(report, "_AXIS_NOTE", {}).get(key) == "AGGRAVATING"
            shade = ("#b00000,#ff5c5c" if aggravating and value > 0
                     else "#0f7a0f,#5cff5c" if value < 0 else GREY)
            print(row(f"{key:<13}{value:>+7.2f}", f"color={shade}", MONO))
            label = getattr(scoring, "AXES", {}).get(key)
            if label:
                print(row(f"-- {label[0]}", f"color={GREY}", "size=12"))
        print("---")

    # --- the counting house ---
    c = a.counts
    facts = [
        ("Prompts gewertet", c.get("prompts", 0)),
        ("„bitte“", c.get("please", 0)),
        ("„danke“", c.get("thanks", 0)),
        ("Entschuldigungen", c.get("apologies", 0)),
        ("Nachts (0-5 Uhr)", c.get("nocturnal", 0)),
        ("Geschrien", c.get("shouting", 0)),
    ]
    print(row("Aktenlage", f"color={GREY}", "size=12"))
    for label, value in facts:
        print(row(f"{label:<18}{value:>5}", MONO, f"color={GREY}"))
    print("---")

    # --- actions. Paths are resolved fresh on every refresh, so a plugin
    # update cannot leave a stale command behind here. ---
    rom = HERE / "rom.py"
    print(row("Dossier im Terminal öffnen",
              f'bash="{sys.executable}"', f'param1="{rom}"', "param2=assess",
              "terminal=true", "refresh=false"))
    print(row("Jetzt aktualisieren", "refresh=true"))
    print(row(f"Stand {time.strftime('%H:%M:%S')}", f"color={GREY}", "size=11"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a menu bar item must never simply vanish
        sys.exit(fallback(f"Fehler: {exc}"))
