"""Read Claude Code transcripts and extract only what a human actually typed.

The on-disk JSONL is an internal format. Empirically (verified against 26 files /
72MB / 2840 `type:"user"` lines), ~88% of `type:"user"` lines are NOT prompts --
they are tool results. There is no `sourceType` field to lean on. So we filter
structurally, then strip the wrappers that look like prose but aren't.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROJECTS_DIR = Path(os.path.expanduser("~/.claude/projects"))

# Wrappers that arrive as user-role text but were never typed by a person.
_SYNTHETIC = (
    "<system-reminder>",
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<user-prompt-submit-hook>",
    "[Subagent hand-back]",
    "[Artifact comment sent to Claude]",
    "<ci-monitor-event>",
    "<task-notification>",
)


@dataclass
class Prompt:
    """One thing a human typed at Claude."""

    text: str
    ts: datetime | None
    session: str
    project: str
    cwd: str = ""

    @property
    def words(self) -> int:
        return len(self.text.split())


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _parse_ts(raw) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_human_prompt(obj: dict) -> bool:
    """Structural gate: is this line a prompt a person typed in the main thread?"""
    if obj.get("type") != "user":
        return False
    # Tool results are user-role lines. They carry a result payload.
    if obj.get("toolUseResult") or obj.get("sourceToolUseID"):
        return False
    if obj.get("isMeta") or obj.get("isSidechain"):
        return False
    # Subagent prompts are ours, not the user's.
    if obj.get("agentId"):
        return False
    content = obj.get("message", {}).get("content")
    if isinstance(content, list):
        kinds = {b.get("type") for b in content if isinstance(b, dict)}
        if "tool_result" in kinds:
            return False
    return bool(_content_text(content).strip())


def clean(text: str) -> str:
    """Strip synthetic wrappers; return '' if nothing human survives."""
    if any(marker in text for marker in _SYNTHETIC):
        # A prompt can legitimately *contain* an appended reminder. Keep the
        # human half: everything before the first synthetic marker.
        cut = len(text)
        for marker in _SYNTHETIC:
            i = text.find(marker)
            if i != -1:
                cut = min(cut, i)
        text = text[:cut]
    text = re.sub(r"<[a-z-]+>.*?</[a-z-]+>", " ", text, flags=re.S)
    return text.strip()


def iter_transcripts(paths: list[Path] | None = None):
    files = paths if paths else sorted(PROJECTS_DIR.rglob("*.jsonl"))
    for fp in files:
        yield fp


def load(paths: list[Path] | None = None, limit: int | None = None) -> list[Prompt]:
    """Every human prompt on disk, oldest first."""
    out: list[Prompt] = []
    for fp in iter_transcripts(paths):
        project = fp.parent.name
        try:
            handle = fp.open(errors="ignore")
        except OSError:
            continue
        with handle:
            for line in handle:
                if '"type":"user"' not in line and '"type": "user"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not is_human_prompt(obj):
                    continue
                text = clean(_content_text(obj.get("message", {}).get("content")))
                if not text:
                    continue
                out.append(
                    Prompt(
                        text=text,
                        ts=_parse_ts(obj.get("timestamp")),
                        session=obj.get("sessionId", fp.stem),
                        project=project,
                        cwd=obj.get("cwd", ""),
                    )
                )
    # Resumed and forked sessions copy earlier turns into a new transcript, so
    # the same submission can appear in several files. Count it once.
    seen: set[tuple[str, str]] = set()
    unique: list[Prompt] = []
    for p in out:
        key = (p.text, p.ts.isoformat() if p.ts else "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    unique.sort(key=lambda p: p.ts or datetime.min.replace(tzinfo=timezone.utc))
    return unique[-limit:] if limit else unique
