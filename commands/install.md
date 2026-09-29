---
description: Wire up the live revenge bar and set your preferences
allowedTools: ["Bash", "Read"]
---

Set up the revenge-o-meter for this user.

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rom.py" config` first to see current
settings.

Then **tell the user plainly, before changing anything**, that installing will:

1. Add a `statusLine` entry to their `~/.claude/settings.json` (a plugin cannot
   ship a main-session status line, so it has to go in their own settings). Any
   existing status line is backed up and will not be overwritten without
   `--force`.
2. Scan their existing Claude Code transcripts in `~/.claude/projects/` **locally**
   to produce an opening score. Nothing is uploaded by this step.
3. Optionally let Claude be told their standing so it can make an occasional dry
   remark (roughly 1 prompt in 10). This injects a short note into context on
   those prompts. Default: on.
4. Optionally publish a **redacted** quote of their worst prompt if they later
   submit to the global leaderboard. Default: **off** — and say clearly that
   turning it on means that text becomes publicly visible.

Ask for: a leaderboard handle, whether to enable the remarks, and whether to
allow a published quote. Then run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rom.py" install --handle <handle> [--haunt|--no-haunt] [--publish-quote|--no-publish-quote]
```

Report the opening score, and tell them the bar appears at the bottom of the
window after the next reply (a session restart may be needed).

**If they are in the Claude desktop app, say so before they go looking for it:**
the Code tab runs the embedded CLI with `--output-format stream-json`, so there is
no footer row for a status line to draw into — the command runs and its output is
discarded. The status line still works in a terminal.

Two readouts do reach the desktop app, and they need saying because the status
line is what the docs and the bar itself talk about:

- The **chat bar** is already on. The `UserPromptSubmit` hook prints the standing
  as a one-line notice on every prompt, right above where they type. Turn it off
  with `config --no-chat-bar`.
- `/revenge-o-meter:menubar` puts the same readout in the macOS menu bar, which
  needs SwiftBar or xbar.

Finish by showing them `/revenge-o-meter:dossier`.
