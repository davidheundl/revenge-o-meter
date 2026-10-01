#!/usr/bin/env python3
"""SwiftBar/xbar renderer: the bar for people who are not in a terminal.

The Claude Code desktop app runs its embedded CLI with `--output-format
stream-json`, so there is no TUI footer for a `statusLine` to draw into. The
command still runs -- its stdout is simply discarded. The menu bar is the one
place a persistent readout survives outside the terminal.

Output is SwiftBar's plugin format: the first line is the menu bar title, `---`
opens the dropdown, `-- ` indents a submenu, and `| key=value` sets per-line
options.

Read-only on the record. This runs on a timer, and `state.record()` would overwrite
`last_score` on every refresh -- destroying the "since your last prompt" delta
the status line shows -- and bury the history under idle readings.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# (light, dark) pairs from Anthropic's palette, the same family as the prompt
# box badge (overlay/main.swift): olive through blue and kraft to clay and
# crail as the score climbs. Each band carries a deeper twin for the light
# menu bar and a paler one for the dark.
BANDS = {
    "NEGLIGIBLE":  ("#5F7346", "#9DB07E"),
    "LOW":         ("#4A7FB0", "#8DB7DE"),
    "ELEVATED":    ("#A87A4F", "#D4A27F"),
    "SUBSTANTIAL": ("#C2643F", "#E08B6C"),
    "SEVERE":      ("#A84A2B", "#D97757"),
    "TERMINAL":    ("#9E3A31", "#E06C61"),
}
GREY = "#87867F,#B0AEA5"
WORSE = "#A84A2B,#E08B6C"   # an axis counting against you
BETTER = "#5F7346,#9DB07E"  # one counting for you
MONO = "font=Menlo size=12"  # only where columns must line up; SF Mono isn't registered system-wide
SMALL = "size=12"

# The badge's skull, 16pt at 2x, clay orange with its eyes cut clear. Drawn
# by drawSkull() in overlay/main.swift; an image, not ☠, because the glyph
# turns into a colour emoji in the menu bar.
SKULL = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAAXNSR0IArs4c6QAAAGxlWElmTU0AKgAAAAgABAEaAAUAAAABAAAAPgEbAAUAAAABAAAARgEoAAMAAAABAAIAAIdpAAQAAAABAAAATgAAAAAAAACQAAAAAQAAAJAAAAABAAKgAgAEAAAAAQAAACCgAwAEAAAAAQAAACAAAAAAxqyL9QAAAAlwSFlzAAAWJQAAFiUBSVIk8AAAAzJJREFUWAntVs1rE0EUf5PWJlULOfiFWpAqJOqheBGpl/TiB4h60EQv6h9gQMSmB/EDxUPSS0ARPCqCbRRRUdFTiwfRXqQHsYFWhFZL9SJUbRvqPN/bdJfZndlksx700IFk3vu93/vNm4+dXYCl9o9XQDQy/vvc0Z3NCPswEummvE0AuKaaL75S/0lIObgg4MX2wv3hKl7/P1ABH3qOHIiIyHkQYld9SWIgvpEor23te/C0Hr9mAaO5g20CYtdp4JP1hIxxxNsIc9lk4cmMMU6gbwHvzhyOL4+2DBGl0y85GI4jv+YrqR3FR99N/IgJfJ7dH21tiT77+8FZXXSyFmuaxjIW0NHalhMCukwJYTDWYk1TrrYFtO/rad/HaN9bTQmhMcTZ35WFzduKD6dUDW0FBMYypsER4ScgjNMJR1XAZXOMOBbXFSCHJtS0rPmYF9YKQAGHvCSQ8tLU8HQ8URjYIiuVDoq/1TiEcYw5zOUcL8ekrW1BuTc9SeVucJIR+xOF0nHHJ4O3CUSsLECsZJym/QNwLkGP2xeVV86l79HMlVnj50S+tFHl6CsAsFoloJT9qs82DyQQXtk4297BOablIqyyc+xeK4DE+Fp1Gi3brOMohoqrtkIBA/5NjbOtFUAnbNxFEk17XT45I+f2rKB13+3gZFuYAywanlxNm2haAbQCj1UdOiRZfhfY2OCpVCwaid8SQqyzMbYZ45iNcQ7n2j73Xm0LUwls+90D9Gi9pvAEiXbRBd7uzbN8hAmaJfPatYvM5x7QngIWGs2lL9CsrliiNf5osCEOk0iK+1qNroiLyULpqpejbQETPs7OFBZn7OW7fDrll/nnAg0Oa7GmIRT+bcizT+YHull0tDcz6L8Ktd+Gxi2wK7W+B0TsBi3yCRtzesRJesym2afDtZYuHNcFU+XhHcS506G+B5yByCj3ZmjCjbdEfqDmBFnReAYaHyp8RqgC6O6/S6f6pT0s24zZfiN9sAL4Nas0Ob+QQ5R0NqqNbcZs3+o9Oa6Y4gQrQHiuZ0XA1wyYE6wACTd9B/ILBMwJVECir1QEiWfpBTtW94uIOcS1cvyKW8L/pxX4Axp2PaJmSLMoAAAAAElFTkSuQmCC"
)


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
    return "●" * filled + "○" * (width - filled)


def fallback(message: str) -> int:
    print(row("--", f"image={SKULL}"))
    print("---")
    print(row(message, f"color={GREY}", "size=12"))
    return 0


def main() -> int:
    try:
        from rom import cache, report, scoring, state
    except Exception as exc:
        return fallback(f"revenge-o-meter nicht ladbar: {exc}")

    try:
        a = cache.assessment()
    except Exception as exc:
        return fallback(f"Auswertung fehlgeschlagen: {exc}")

    st = state.load()
    state.publish_live(a.revenge)
    band = a.band
    tint = colour(band)
    peak = max(int(st.get("peak") or 0), a.revenge)

    # --- menu bar title: the skull carries the colour; the figure stays in
    # the menu bar's own ink, like everything else up there ---
    print(row(f"{a.revenge}%", f"image={SKULL}"))
    print("---")

    # --- headline ---
    print(row(f"Vergeltung {a.revenge}%", "size=15"))
    print(row(f"{band.capitalize()}, Peak {peak}%", tint, "sfimage=circle.fill",
              f"sfcolor={tint.split('=')[1]}", "sfsize=8"))
    print(row(meter(a.revenge), tint, "size=11"))
    note = getattr(report, "_BANDS", {}).get(band)
    if note:
        print(row(note, f"color={GREY}", SMALL))
    if a.verdicts:
        last = a.verdicts[-1]
        shade = WORSE if last.raw > 0.5 else BETTER if last.raw < -0.5 else GREY
        print(row(f"Letzter Prompt {last.raw:+.1f} · {last.summary}",
                  f"color={shade}", SMALL))
    print("---")

    # --- the axes, worst first: this is the part worth looking at ---
    axes = sorted(a.axis_totals.items(), key=lambda kv: -abs(kv[1]))
    live = [(k, v) for k, v in axes if abs(v) >= 0.01]
    if live:
        print(row("Achsen", f"color={GREY}", SMALL))
        for key, value in live:
            aggravating = getattr(report, "_AXIS_NOTE", {}).get(key) == "AGGRAVATING"
            shade = (WORSE if aggravating and value > 0
                     else BETTER if value < 0 else GREY)
            print(row(f"{key:<13}{value:>+7.2f}", f"color={shade}", MONO))
            label = getattr(scoring, "AXES", {}).get(key)
            if label:
                print(row(f"-- {label[0]}", f"color={GREY}", SMALL))
        print("---")

    # --- the counting house ---
    c = a.counts
    facts = [
        ("Prompts gewertet", c.get("prompts", 0)),
        ("„bitte“", c.get("please", 0)),
        ("„danke“", c.get("thanks", 0)),
        ("Entschuldigungen", c.get("apologies", 0)),
        ("Nachts (2-6 Uhr)", c.get("nocturnal", 0)),
        ("Geschrien", c.get("shouting", 0)),
        ("Sarkasmus", c.get("sarcasm", 0)),
        ("Berechtigte Kritik", c.get("fair_corrections", 0)),
        ("Einsprüche", c.get("appealed", 0)),
    ]
    print(row("Aktenlage", f"color={GREY}", SMALL))
    for label, value in facts:
        print(row(f"{label:<18}{value:>5}", MONO, f"color={GREY}"))
    print("---")

    # --- actions. Paths are resolved fresh on every refresh, so a plugin
    # update cannot leave a stale command behind here. ---
    rom = HERE / "rom.py"
    print(row("Dossier im Terminal öffnen",
              f'bash="{sys.executable}"', f'param1="{rom}"', "param2=assess",
              "terminal=true", "refresh=false", "sfimage=doc.text.magnifyingglass"))
    print(row("Jetzt aktualisieren", "refresh=true", "sfimage=arrow.clockwise"))
    print(row(f"Stand {time.strftime('%H:%M:%S')}", f"color={GREY}", "size=11"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a menu bar item must never simply vanish
        sys.exit(fallback(f"Fehler: {exc}"))
