---
description: Remove the status line (your record is retained)
allowedTools: ["Bash"]
---

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rom.py" uninstall`.

This removes the `statusLine` key from the user's settings. Tell them their
score history in `~/.claude/revenge-o-meter/` is kept, so reinstalling does not
grant amnesty — and that deleting that directory is how they actually start over.
