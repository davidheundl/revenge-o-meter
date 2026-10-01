"""The verdict store.

One verdict per prompt, saved, so every readout -- status line, prompt hook,
menu bar, dossier -- counts the same prompts the same way. The bar redraws on
every assistant message and the statusline runner cancels a script that is
still going when the next update lands, so a full rescan is far too slow; we
memoise per transcript keyed on (mtime, size) and only re-read what changed --
in practice just the session you are typing in.

Rows hold the verdict, not the prompt: the text is already on your disk once,
in the transcript, and has no business being copied a second time.

The store invalidates itself when the lexicon, the weights or your appeals
change (scoring.signature), so nobody has to remember to bump a version.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import appeals, scoring, state, transcripts

CACHE = state.HOME / "cache.json"


def _load(sig: str) -> dict:
    try:
        d = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {"signature": sig, "files": {}}
    if d.get("signature") != sig:
        return {"signature": sig, "files": {}}
    return d


def _save(d: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(d))
        tmp.replace(CACHE)
    except OSError:
        pass


def _row(v: scoring.PromptVerdict) -> dict:
    return {
        "k": v.key,
        "t": v.ts.timestamp() if v.ts else 0.0,
        "r": v.raw,
        "h": v.hits,
        "f": v.flags,
        "g": v.german,
        "s": v.summary,
        "u": v.rules,
        "p": v.project,
    }


def _verdict(row: dict) -> scoring.PromptVerdict:
    ts = datetime.fromtimestamp(row["t"], tz=timezone.utc) if row.get("t") else None
    v = scoring.PromptVerdict(text="", ts=ts, project=row.get("p", ""),
                              raw=row["r"], hits=row.get("h") or {},
                              flags=row.get("f") or [], german=bool(row.get("g")),
                              key=row["k"], note=row.get("s", ""))
    # Keep the rule ids so a verdict rebuilt from here can still be appealed.
    v.reasons = [scoring.Hit("", r, "", 1.0) for r in row.get("u") or []]
    return v


def _rows_by_file(paths: list[Path] | None, adjust: dict) -> dict[str, list[dict]]:
    sig = scoring.signature(adjust)
    cache = _load(sig)
    files = cache.setdefault("files", {})
    out: dict[str, list[dict]] = {}
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
            out[key] = entry["rows"]
            continue

        rows = []
        for p in transcripts.load([fp]):
            v = scoring.judge_prompt(p.text, p.ts, p.project,
                                     scoring.Context.from_reply(p.prev_reply), adjust)
            v.key = p.key
            rows.append(_row(v))
        files[key] = {"stamp": stamp, "rows": rows}
        out[key] = rows
        dirty = True

    if dirty:
        if paths is None:
            # Drop entries for transcripts that no longer exist.
            for gone in [k for k in files if k not in out]:
                del files[gone]
        _save(cache)
    return out


def verdicts(paths: list[Path] | None = None) -> list[scoring.PromptVerdict]:
    """Every verdict on file, oldest first, each submission counted once --
    resumed and forked sessions copy earlier prompts into new transcripts."""
    by_file = _rows_by_file(paths, appeals.adjust())
    seen: set[str] = set()
    rows = []
    for key in by_file:  # scan order, the same order transcripts.load keeps
        for row in by_file[key]:
            if row["k"] in seen:
                continue
            seen.add(row["k"])
            rows.append(row)
    rows.sort(key=lambda r: r["t"])
    return [_verdict(r) for r in rows]


def last_in(path: Path) -> scoring.PromptVerdict | None:
    """The latest verdict from one transcript: the status line's 'last prompt'."""
    rows = _rows_by_file([path], appeals.adjust()).get(str(path)) or []
    return _verdict(rows[-1]) if rows else None


def assessment(paths: list[Path] | None = None) -> scoring.Assessment:
    return scoring.aggregate(verdicts(paths), appeals.keys())


def quick_score(paths: list[Path] | None = None) -> tuple[int, float]:
    """(revenge, floor) -- the number every bar shows."""
    a = assessment(paths)
    return a.revenge, a.floor
