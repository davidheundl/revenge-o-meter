"""Persisted dossier state: the permanent record.

Lives outside the plugin so reinstalling doesn't grant amnesty.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

HOME = Path(os.path.expanduser("~/.claude/revenge-o-meter"))
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


def publish_live(score: int) -> None:
    """Note the current score for readers that cannot compute it.

    Separate from record(): the menu bar and the prompt hook compute the score
    too, but must not touch last_score -- the status line's delta is measured
    against it. Without this, the prompt box badge only sees last_score, and
    in the desktop app, where the status line never runs, that goes stale.
    """
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        tmp = LIVE.with_name(f".live.{os.getpid()}.tmp")  # writers can overlap
        tmp.write_text(json.dumps({"score": int(score), "at": int(time.time())}))
        tmp.replace(LIVE)
    except OSError:
        pass


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
