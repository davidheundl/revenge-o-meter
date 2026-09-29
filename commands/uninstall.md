---
description: Remove the status line (your record is retained)
allowedTools: ["Bash"]
---

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rom.py" uninstall`.

If they also installed the menu bar item, remove that too:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rom.py" menubar --uninstall`. It leaves
SwiftBar or xbar itself alone — say so, and let them remove the app themselves if
they want it gone.

This removes the `statusLine` key from the user's settings. Tell them their
score history in `~/.claude/revenge-o-meter/` is kept, so reinstalling does not
grant amnesty — and that deleting that directory is how they actually start over.
