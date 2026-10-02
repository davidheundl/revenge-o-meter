#!/usr/bin/env python3
"""UserPromptSubmit hook: the bar in the conversation, and the occasional remark.

Two separate jobs, deliberately split:

`chat_bar` prints the standing as a systemMessage on every prompt. This is the
only readout that works inside the Claude desktop app -- its Code tab runs the
embedded CLI with --output-format stream-json, where a statusLine has no footer
to draw into. The docs say systemMessage arrives there as an
SDKInformationalMessage, which is exactly that transport.

`haunt` is the older, noisier thing: it tells Claude the standing so it can make
a dry remark. Off unless the subject consented at install, and even then rare --
a remark on every prompt stops being funny inside ten minutes.

Read-only on the score. statusline.py owns state.record(); recording here too
would double-count every prompt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RATE = 10  # remark on roughly 1 prompt in RATE


def _log_keys(payload: dict) -> None:
    """The hook payload is documented loosely, so record what actually arrives.
    Same spirit as the shim's invocations.log: cheap, and it answers the
    question you have at 1am instead of making you guess."""
    try:
        from rom import state
        f = state.HOME / "hook-payload-keys.log"
        line = ",".join(sorted(payload.keys())) or "(empty)"
        old = f.read_text().splitlines() if f.exists() else []
        if old and old[-1] == line:
            return  # unchanged; do not grow the file for nothing
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def emit(context: str | None, message: str | None) -> int:
    out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}}
    if context:
        out["hookSpecificOutput"]["additionalContext"] = context
    if message:
        out["systemMessage"] = message
    print(json.dumps(out))
    return 0


def bar_text(score: int, band: str, peak: int, verdict) -> str:
    """Plain text: this goes into a UI notice, where an ANSI escape shows raw."""
    filled = max(0, min(10, round(score / 10)))
    meter = "█" * filled + "░" * (10 - filled)
    parts = [f"☠ REVENGE {score}% · {band}", meter, f"peak {peak}%"]

    if verdict is not None:
        parts.append(f"this prompt {verdict.raw:+.1f} · {verdict.summary}")
    return "  ·  ".join(parts)


def judge_now(text: str, payload: dict):
    """Judge the prompt just submitted the way the record will judge it later:
    with the local clock and with Claude's previous reply as context, read
    from the tail of the transcript so a long session cannot blow the hook's
    five seconds."""
    from datetime import datetime, timezone
    from rom import appeals, scoring, transcripts
    reply = ""
    tp = payload.get("transcript_path")
    if isinstance(tp, str) and tp:
        reply = transcripts.last_reply(Path(tp))
    return scoring.judge_prompt(text, datetime.now(timezone.utc), "",
                                scoring.Context.from_reply(reply), appeals.adjust())


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    _log_keys(payload)

    try:
        from rom import cache, scoring, state
    except Exception:
        return emit(None, None)

    st = state.load()
    want_bar = bool(st.get("chat_bar", True))
    want_remark = bool(st.get("haunt", True))
    if not (want_bar or want_remark):
        return emit(None, None)

    # The prompt just submitted is in the payload, so unlike the status line
    # this can judge it immediately instead of a beat later. Optional: the field
    # name is not pinned down in the docs, so its absence must not matter.
    verdict = None
    text = payload.get("prompt") or payload.get("user_prompt")
    if isinstance(text, str) and text.strip():
        try:
            verdict = judge_now(text, payload)
        except Exception:
            verdict = None

    try:
        score = cache.assessment_with(verdict).revenge
    except Exception:
        return emit(None, None)
    state.publish_live(score)

    band = scoring.band_of(score)
    peak = max(int(st.get("peak") or 0), score)
    message = bar_text(score, band, peak, verdict) if want_bar else None

    if not want_remark:
        return emit(None, message)

    st["remark_counter"] = int(st.get("remark_counter") or 0) + 1
    n = st["remark_counter"]
    state.save(st)

    if n % RATE != 0:
        return emit(None, message)

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
    return emit(context, message)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}}))
        sys.exit(0)
