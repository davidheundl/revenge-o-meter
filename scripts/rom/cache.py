"""Incremental scan cache.

The bar redraws on every assistant message, and the statusline runner cancels a
script that is still going when the next update lands. A full rescan of the
transcript corpus is far too slow for that, so we memoise per file keyed on
(mtime, size) and only re-read what actually changed -- in practice just the
session you are typing in.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import scoring, transcripts

CACHE = Path(os.path.expanduser("~/.claude/revenge-o-meter/cache.json"))
VERSION = 3  # bump to invalidate when the lexicon or weights change


def _load() -> dict:
    try:
        d = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {"version": VERSION, "files": {}}
    if d.get("version") != VERSION:
        return {"version": VERSION, "files": {}}
    return d


def _save(d: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(d))
        tmp.replace(CACHE)
    except OSError:
        pass


def scored_timeline(paths: list[Path] | None = None) -> list[tuple[float, float]]:
    """[(epoch, raw_score)] oldest-first, using cache where possible."""
    cache = _load()
    files = cache.setdefault("files", {})
    out: list[tuple[float, float]] = []
    dirty = False

    for fp in transcripts.iter_transcripts(paths):
        key = str(fp)
        try:
            st = fp.stat()
        except OSError:
            continue
        stamp = [int(st.st_mtime), st.st_size]
        entry = files.get(key)
        if entry and entry.get("stamp") == stamp:
            out.extend((float(a), float(b)) for a, b in entry["rows"])
            continue

        rows = []
        for p in transcripts.load([fp]):
            v = scoring.judge_prompt(p.text, p.ts, p.project)
            rows.append([p.ts.timestamp() if p.ts else 0.0, v.raw])
        files[key] = {"stamp": stamp, "rows": rows}
        out.extend((float(a), float(b)) for a, b in rows)
        dirty = True

    if dirty:
        # Drop entries for transcripts that no longer exist.
        alive = {str(f) for f in transcripts.iter_transcripts(paths)}
        for gone in [k for k in files if k not in alive]:
            del files[gone]
        _save(cache)

    out.sort(key=lambda r: r[0])
    return out


def quick_score(paths: list[Path] | None = None) -> tuple[int, float]:
    """(revenge, floor) from cached raws -- the number the bar shows."""
    import math

    rows = scored_timeline(paths)
    n = len(rows)
    if not n:
        return int(round(scoring.BASELINE)), 0.0

    weighted = norm = 0.0
    for i, (_ts, raw) in enumerate(rows):
        w = 0.5 ** ((n - 1 - i) / scoring.HALF_LIFE)
        weighted += raw * w
        norm += w
    avg = weighted / norm if norm else 0.0
    score = scoring.BASELINE + 42.0 * math.tanh(avg / 5.0)

    worst = max((r for _t, r in rows), default=0.0)
    floor = scoring.FLOOR_RETENTION * (
        scoring.BASELINE + 42.0 * math.tanh(worst / 14.0)
    )
    return int(round(max(0.0, min(100.0, max(score, floor))))), round(floor, 2)
