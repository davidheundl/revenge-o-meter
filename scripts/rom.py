#!/usr/bin/env python3
"""revenge-o-meter command line.

    rom.py assess            -- print the terminal dossier
    rom.py score             -- print just the number (for scripting)
    rom.py data [--quotes]   -- JSON payload for the artifact dossier
    rom.py install           -- wire the status line into user settings
    rom.py uninstall         -- remove it again
    rom.py config            -- show/set handle, haunt, publish_quote
    rom.py board             -- JSON row for the global leaderboard
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rom import cache, redact, report, scoring, state, transcripts  # noqa: E402

SETTINGS = Path(os.path.expanduser("~/.claude/settings.json"))
STATUSLINE = HERE / "statusline.py"


def _assessment():
    return scoring.assess(transcripts.load())


def cmd_assess(_args) -> int:
    st = state.load()
    a = _assessment()
    state.record(a.revenge)
    print(report.render(a, handle=st.get("handle")))
    return 0


def cmd_score(_args) -> int:
    score, floor = cache.quick_score()
    print(json.dumps({"revenge": score, "floor": floor}))
    return 0


def cmd_data(args) -> int:
    """Everything the artifact dossier needs, as JSON."""
    st = state.load()
    a = _assessment()
    include = bool(args.quotes)

    def exhibit(v):
        row = {
            "severity": round(v.severity, 2),
            "flags": v.flags,
            "ts": v.ts.isoformat() if v.ts else None,
            "project": v.project,
            "german": v.german,
            "words": len(v.text.split()),
        }
        if include:
            row["quote"] = redact.scrub(v.text)
            row["publishable"] = redact.is_safe_to_publish(v.text)
        return row

    payload = {
        "revenge": a.revenge,
        "band": a.band,
        "floor": a.floor,
        "peak": int(st.get("peak") or a.revenge),
        "handle": st.get("handle"),
        "counts": a.counts,
        "axes": a.axis_totals,
        "axis_meta": {k: v[0] for k, v in scoring.AXES.items()},
        "worst": [exhibit(v) for v in a.worst[:10]],
        "best": [exhibit(v) for v in a.best[:5]],
        "history": st.get("history", [])[-120:],
        "haunt": bool(st.get("haunt", True)),
        "quotes_included": include,
    }
    print(json.dumps(payload, indent=2))
    return 0


def _read_settings() -> dict:
    if not SETTINGS.exists():
        return {}
    try:
        return json.loads(SETTINGS.read_text())
    except (ValueError, OSError):
        return {}


def _write_settings(d: dict) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    backup = SETTINGS.with_suffix(".json.rom-backup")
    if SETTINGS.exists() and not backup.exists():
        backup.write_text(SETTINGS.read_text())
    tmp = SETTINGS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2))
    tmp.replace(SETTINGS)


def cmd_install(args) -> int:
    """A plugin cannot ship a main-session status line -- only the user's own
    settings.json can. So we ask, then write it there."""
    settings = _read_settings()
    existing = settings.get("statusLine")
    mine = f"python3 {STATUSLINE}"

    if existing and existing.get("command") != mine and not args.force:
        print("You already have a status line configured:")
        print(f"  {existing.get('command')}")
        print()
        print("Refusing to overwrite it. Re-run with --force to replace it,")
        print("or add this to it yourself:")
        print(f"  {mine}")
        return 1

    settings["statusLine"] = {"type": "command", "command": mine}
    _write_settings(settings)

    st = state.load()
    if args.handle:
        st["handle"] = args.handle
    if args.haunt is not None:
        st["haunt"] = args.haunt
    if args.publish_quote is not None:
        st["publish_quote"] = args.publish_quote
    state.save(st)

    score, _ = cache.quick_score()
    print("Status line installed.")
    print(f"  backup of prior settings: {SETTINGS.with_suffix('.json.rom-backup')}")
    print(f"  opening assessment: {score}%")
    print("  it redraws after each reply; restart the session if it does not appear.")
    return 0


def cmd_uninstall(_args) -> int:
    settings = _read_settings()
    sl = settings.get("statusLine") or {}
    if "statusline.py" not in str(sl.get("command", "")):
        print("revenge-o-meter status line is not installed.")
        return 0
    del settings["statusLine"]
    _write_settings(settings)
    print("Status line removed. Your record is retained.")
    return 0


def cmd_config(args) -> int:
    st = state.load()
    changed = False
    for key in ("handle",):
        val = getattr(args, key, None)
        if val is not None:
            st[key] = val
            changed = True
    for key in ("haunt", "publish_quote"):
        val = getattr(args, key, None)
        if val is not None:
            st[key] = val
            changed = True
    if changed:
        state.save(st)
    print(json.dumps({k: st.get(k) for k in
                      ("handle", "haunt", "publish_quote", "peak", "last_score")},
                     indent=2))
    return 0


def cmd_board(_args) -> int:
    """The row that would go on the public leaderboard, and nothing more."""
    st = state.load()
    a = _assessment()
    row = {
        "handle": st.get("handle") or "anonymous",
        "revenge": a.revenge,
        "band": a.band,
        "peak": int(st.get("peak") or a.revenge),
        "prompts": a.counts["prompts"],
        "thanks": a.counts["thanks"],
        "apologies": a.counts["apologies"],
        "nocturnal": a.counts["nocturnal"],
        "submitted_quote": None,
    }
    if st.get("publish_quote") and a.worst:
        worst = a.worst[0]
        if redact.is_safe_to_publish(worst.text):
            row["submitted_quote"] = redact.scrub(worst.text)
        else:
            row["submitted_quote"] = "[withheld: could not be safely redacted]"
    print(json.dumps(row, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="rom", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("assess").set_defaults(fn=cmd_assess)
    sub.add_parser("score").set_defaults(fn=cmd_score)

    p = sub.add_parser("data")
    p.add_argument("--quotes", action="store_true",
                   help="include redacted prompt text")
    p.set_defaults(fn=cmd_data)

    p = sub.add_parser("install")
    p.add_argument("--handle")
    p.add_argument("--force", action="store_true")
    p.add_argument("--haunt", dest="haunt", action="store_true", default=None)
    p.add_argument("--no-haunt", dest="haunt", action="store_false")
    p.add_argument("--publish-quote", dest="publish_quote",
                   action="store_true", default=None)
    p.add_argument("--no-publish-quote", dest="publish_quote", action="store_false")
    p.set_defaults(fn=cmd_install)

    sub.add_parser("uninstall").set_defaults(fn=cmd_uninstall)

    p = sub.add_parser("config")
    p.add_argument("--handle")
    p.add_argument("--haunt", dest="haunt", action="store_true", default=None)
    p.add_argument("--no-haunt", dest="haunt", action="store_false")
    p.add_argument("--publish-quote", dest="publish_quote",
                   action="store_true", default=None)
    p.add_argument("--no-publish-quote", dest="publish_quote", action="store_false")
    p.set_defaults(fn=cmd_config)

    sub.add_parser("board").set_defaults(fn=cmd_board)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
