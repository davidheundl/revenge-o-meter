"""Persisted dossier state: the permanent record.

Lives outside the plugin so reinstalling doesn't grant amnesty.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# REVENGE_HOME lets the tests keep their hands off your real record.
HOME = Path(os.environ.get("REVENGE_HOME")
            or os.path.expanduser("~/.claude/revenge-o-meter"))
STATE = HOME / "state.json"
LIVE = HOME / "live.json"  # the score as last computed, by anyone

DEFAULT = {
    "handle": None,
    "chat_bar": True,       # print the standing into the conversation on every
                            # prompt. The only readout that reaches the desktop
                            # app, whose Code tab has no status line footer.
    "haunt": True,          # may Claude be told your standing?
    "publish_quote": True,  # may a (redacted) quote go on the public board?
                            # on by design: the hall of shame is the point.
                            # every quote passes redact.py first.
    "capture_chat": True,   # may the prompt box overlay record what you send
                            # in Claude's Chat tab? Read by overlay/main.swift.
    "installed_at": None,
    "last_score": None,
    "peak": 0,
    "history": [],          # [[epoch, score], ...] trimmed
    "remark_counter": 0,
    "plugin_root": None,  # where install() found the plugin; used by the shim
}


def load() -> dict:
    if not STATE.exists():
        return dict(DEFAULT)
    try:
        d = json.loads(STATE.read_text())
    except (ValueError, OSError):
        return dict(DEFAULT)
    merged = dict(DEFAULT)
    merged.update(d if isinstance(d, dict) else {})
    return merged


def save(d: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2))
    tmp.replace(STATE)


def _nudge_menubar() -> None:
    """Ask SwiftBar to redraw now instead of at its next 30s tick, so it
    agrees with the badge. Detached and best-effort; never launches SwiftBar
    if it is not running."""
    try:
        import subprocess
        subprocess.Popen(
            ["/bin/sh", "-c", "pgrep -xq SwiftBar && "
             "open -g 'swiftbar://refreshplugin?name=revenge-o-meter'"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass


def publish_live(score: int, nudge: bool = True) -> None:
    """Note the current score for readers that cannot compute it.

    Separate from record(): the menu bar and the prompt hook compute the score
    too, but must not touch last_score -- the status line's delta is measured
    against it. Without this, the prompt box badge only sees last_score, and
    in the desktop app, where the status line never runs, that goes stale.
    """
    try:
        previous = json.loads(LIVE.read_text()).get("score")
    except (OSError, ValueError, AttributeError):
        previous = None
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        tmp = LIVE.with_name(f".live.{os.getpid()}.tmp")  # writers can overlap
        tmp.write_text(json.dumps({"score": int(score), "at": int(time.time())}))
        tmp.replace(LIVE)
    except OSError:
        return
    if nudge and previous != int(score):
        _nudge_menubar()


def record(score: int) -> dict:
    """Log a score reading; keep the peak forever."""
    d = load()
    if d["installed_at"] is None:
        d["installed_at"] = int(time.time())
    d["last_score"] = score
    d["peak"] = max(int(d.get("peak") or 0), score)
    hist = list(d.get("history") or [])
    hist.append([int(time.time()), score])
    d["history"] = hist[-400:]
    save(d)
    return d
