---
description: Toggle whether Claude is told your standing
allowedTools: ["Bash"]
---

Toggle the occasional deadpan remarks.

Check the current value with
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rom.py" config`, then flip it with
`--haunt` or `--no-haunt` based on what the user asked for. If they did not say
which way, turn it to the opposite of its current state and confirm.

When enabling, remind them it injects a short note into context on roughly 1
prompt in 10, and that it never changes how thoroughly Claude does their actual
work — only whether it comments.
