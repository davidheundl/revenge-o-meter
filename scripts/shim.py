#!/usr/bin/env python3
"""Stable entry point for the status line.

Claude Code caches a plugin under a version or commit directory
(.../cache/revenge-o-meter/revenge-o-meter/0.1.0/), so the path changes on every
update. The user's settings.json cannot know that. Pointing `statusLine`
straight at the plugin copy means the bar silently dies the first time the
plugin updates.

So `install` writes THIS file to a fixed location outside the plugin and points
settings at it. It finds the current plugin, newest first, and hands over.

The same problem applies to the SwiftBar plugin file in the menu bar, so this
shim takes the script to hand over to as its one argument -- `statusline.py`
when called without one.
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


DEFAULT_TARGET = "statusline.py"
# Which scripts this shim is allowed to hand over to. An allowlist, because the
# target arrives as argv from a file the user can edit.
TARGETS = ("statusline.py", "menubar.py")


def _target() -> str:
    want = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET
    return want if want in TARGETS else DEFAULT_TARGET


def _log(target: str) -> None:
    """Proof of life: shows whether the host is calling us at all."""
    try:
        stem = Path(target).stem
        name = "invocations.log" if target == DEFAULT_TARGET \
            else f"invocations-{stem}.log"
        f = STATE.parent / name
        import time
        with f.open("a") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        # keep it small
        lines = f.read_text().splitlines()[-200:]
        f.write_text("\n".join(lines) + "\n")
    except OSError:
        pass


def _fail(target: str, message: str) -> int:
    """Say so in the host's own language: ANSI in a terminal footer, SwiftBar's
    plugin format in the menu bar, where an escape code would show up raw."""
    if target == "menubar.py":
        print("☠ -- | color=#6e6e6e,#9a9a9a")
        print("---")
        print(f"{message} | size=12 color=#6e6e6e,#9a9a9a")
    else:
        print(f"\033[2m☠ {message}\033[0m")
    return 0


def main() -> int:
    target = _target()
    _log(target)
    # A tty means someone is running this by hand; reading stdin would hang.
    payload = "" if sys.stdin.isatty() else sys.stdin.read()
    # Discovery first: the recorded root goes stale the moment the plugin
    # updates, because the old version directory lingers and still resolves.
    root = _discovered_root() or _recorded_root()
    if root is None:
        return _fail(target, "revenge-o-meter: plugin not found")
    try:
        out = subprocess.run(
            [sys.executable, str(root / target)],
            input=payload, text=True, capture_output=True, timeout=20,
        )
    except Exception:
        return _fail(target, "revenge-o-meter unavailable")
    if not out.stdout:
        return _fail(target, "revenge-o-meter")
    sys.stdout.write(out.stdout)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(_fail(_target(), "revenge-o-meter"))
