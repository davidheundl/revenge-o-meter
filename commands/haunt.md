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

**Do not confuse this with the chat bar.** `haunt` is whether *Claude* is told
the standing; `chat_bar` is whether *the user* sees it, as a one-line notice on
every prompt. They are independent, and the chat bar is what makes the plugin
work in the desktop app at all. Its flags are `--chat-bar` / `--no-chat-bar` on
the same `config` command. If the user asks to "turn off the score" or "stop the
messages", ask which of the two they mean before flipping either.
