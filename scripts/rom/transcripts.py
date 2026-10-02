"""Read Claude Code transcripts and extract only what a human actually typed.

Plus one file that is not a transcript: chat-prompts.jsonl, where the prompt
box overlay records what you send in Claude's Chat tab. Chat conversations
live on Anthropic's servers, never in ~/.claude/projects, and plugin hooks do
not run there, so this is the only way they reach the record.

The on-disk JSONL is an internal format. Empirically (verified against 26 files /
72MB / 2840 `type:"user"` lines), ~88% of `type:"user"` lines are NOT prompts --
they are tool results. There is no `sourceType` field to lean on. So we filter
structurally, then strip the wrappers that look like prose but aren't.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import state

# REVENGE_PROJECTS lets the tests point at fixtures instead of your history.
PROJECTS_DIR = Path(os.environ.get("REVENGE_PROJECTS")
                    or os.path.expanduser("~/.claude/projects"))
REPLY_TAIL = 3000  # chars of Claude's previous reply kept as context

CHAT_LOG = state.HOME / "chat-prompts.jsonl"  # written by overlay/main.swift
CHAT_PROJECT = "claude-chat"
# The overlay also sees the Code tab's prompt box. A chat-log line whose text
# Claude Code recorded within this many seconds is the same prompt, twice.
ECHO_WINDOW = 600

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
    prev_reply: str = ""   # tail of what Claude said just before this prompt

    @property
    def words(self) -> int:
        return len(self.text.split())

    @property
    def key(self) -> str:
        """Stable id for one submission, shared by every copy of it that a
        resumed or forked session leaves behind."""
        return prompt_key(self.text, self.ts)


def prompt_key(text: str, ts: datetime | None) -> str:
    stamp = ts.isoformat() if ts else ""
    return hashlib.sha1(f"{stamp}\n{text}".encode()).hexdigest()[:12]


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


def _reply_text(obj: dict) -> str:
    """The prose of an assistant line: text blocks only, no thinking, no tools."""
    return _content_text(obj.get("message", {}).get("content")).strip()


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
    if paths:
        yield from paths
        return
    yield from sorted(PROJECTS_DIR.rglob("*.jsonl"))
    if CHAT_LOG.exists():
        yield CHAT_LOG


def text_hash(text: str) -> str:
    return hashlib.sha1(" ".join(text.split()).lower().encode()).hexdigest()[:12]


def drop_echoes(items: list, info) -> list:
    """Drop chat-log prompts that Claude Code also recorded.

    info(item) -> (is_chat, text_hash, epoch). Shared by load() and the
    verdict store, which only has the hash, so both drop the same ones."""
    code: dict[str, list[float]] = {}
    for it in items:
        chat, h, t = info(it)
        if not chat:
            code.setdefault(h, []).append(t)
    return [it for it in items
            if not (info(it)[0] and any(abs(info(it)[2] - t) <= ECHO_WINDOW
                                        for t in code.get(info(it)[1], ())))]


def _epoch(ts: datetime | None) -> float:
    return ts.timestamp() if ts else 0.0


def _load_chat(fp: Path) -> list[Prompt]:
    out = []
    try:
        lines = fp.read_text(errors="ignore").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        text = str(obj.get("text") or "").strip()
        if not text:
            continue
        out.append(Prompt(text=text, ts=_parse_ts(obj.get("ts")), session="chat",
                          project=CHAT_PROJECT))
    return out


def load(paths: list[Path] | None = None, limit: int | None = None) -> list[Prompt]:
    """Every human prompt on disk, oldest first."""
    out: list[Prompt] = []
    for fp in iter_transcripts(paths):
        if fp == CHAT_LOG:
            out.extend(_load_chat(fp))
            continue
        project = fp.parent.name
        try:
            handle = fp.open(errors="ignore")
        except OSError:
            continue
        reply = ""  # Claude's last words before the next prompt, in this file
        with handle:
            for line in handle:
                assistant = '"type":"assistant"' in line or '"type": "assistant"' in line
                if assistant:
                    # Most assistant lines are tool calls; only parse the ones
                    # that can carry prose.
                    if '"text"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if obj.get("isSidechain") or obj.get("agentId"):
                        continue
                    text = _reply_text(obj)
                    if text:
                        reply = text[-REPLY_TAIL:]
                    continue
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
                        prev_reply=reply,
                    )
                )
                reply = ""
    out = drop_echoes(out, lambda p: (p.project == CHAT_PROJECT, text_hash(p.text),
                                      _epoch(p.ts)))
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


def last_reply(path: Path, max_bytes: int = 512_000) -> str:
    """Claude's most recent prose in one transcript, reading only its tail.
    For the prompt hook, which has five seconds and a transcript that can run
    to tens of megabytes."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            lines = fh.read().decode("utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    # The prompt being judged may or may not be written yet; either way the
    # last assistant prose in the file is the reply it answers.
    for line in reversed(lines):
        if '"text"' not in line or not (
                '"type":"assistant"' in line or '"type": "assistant"' in line):
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if obj.get("isSidechain") or obj.get("agentId"):
            continue
        text = _reply_text(obj)
        if text:
            return text[-REPLY_TAIL:]
    return ""
