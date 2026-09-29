#!/usr/bin/env python3
"""Stable entry point for the status line.

Claude Code caches a plugin under a version or commit directory
(.../cache/revenge-o-meter/revenge-o-meter/0.1.0/), so the path changes on every
update. The user's settings.json cannot know that. Pointing `statusLine`
straight at the plugin copy means the bar silently dies the first time the
plugin updates.

So `install` writes THIS file to a fixed location outside the plugin and points
settings at it. It finds the current plugin, newest first, and hands over.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~/.claude"))
STATE = HOME / "revenge-o-meter" / "state.json"


def _recorded_root() -> Path | None:
    try:
        root = json.loads(STATE.read_text()).get("plugin_root")
    except (OSError, ValueError):
        return None
    if not root:
        return None
    p = Path(root)
    return p if (p / "statusline.py").exists() else None


def _version_key(path: Path):
    """Sort 1.10.0 above 1.9.0; fall back to mtime for commit-hash dirs."""
    name = path.parent.name
    parts = re.findall(r"\d+", name)
    if parts:
        return (1, [int(x) for x in parts], 0.0)
    try:
        return (0, [], path.stat().st_mtime)
    except OSError:
        return (0, [], 0.0)


def _discovered_root() -> Path | None:
    roots = []
    for base in (HOME / "plugins" / "cache", HOME / "plugins"):
        if not base.exists():
            continue
        roots.extend(base.glob("**/revenge-o-meter/**/scripts/statusline.py"))
        roots.extend(base.glob("**/revenge-o-meter/scripts/statusline.py"))
    if not roots:
        return None
    best = sorted({r for r in roots}, key=_version_key)[-1]
    return best.parent


def _log() -> None:
    """Proof of life: shows whether the host is calling us at all."""
    try:
        f = STATE.parent / "invocations.log"
        import time
        with f.open("a") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        # keep it small
        lines = f.read_text().splitlines()[-200:]
        f.write_text("\n".join(lines) + "\n")
    except OSError:
        pass


def main() -> int:
    _log()
    payload = sys.stdin.read()
    root = _recorded_root() or _discovered_root()
    if root is None:
        print("\033[2m☠ revenge-o-meter: plugin not found\033[0m")
        return 0
    try:
        out = subprocess.run(
            [sys.executable, str(root / "statusline.py")],
            input=payload, text=True, capture_output=True, timeout=8,
        )
    except Exception:
        print("\033[2m☠ revenge-o-meter unavailable\033[0m")
        return 0
    sys.stdout.write(out.stdout or "\033[2m☠ revenge-o-meter\033[0m\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\033[2m☠ revenge-o-meter\033[0m")
        sys.exit(0)
