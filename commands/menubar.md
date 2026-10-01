---
description: Put the revenge bar in the macOS menu bar (for the desktop app)
allowedTools: ["Bash", "Read"]
---

Install the menu bar readout, for users who work in the Claude desktop app
rather than a terminal.

**Explain the reason first**, because it is not obvious: the desktop app's Code
tab runs the embedded CLI with `--output-format stream-json`. There is no TUI, so
there is no footer row for a `statusLine` to draw into — the command still runs
on every message, and its output is simply discarded. The menu bar is the one
place a persistent readout survives outside a terminal.

This needs a menu bar host. SwiftBar and xbar both read the same plugin format;
SwiftBar is the smaller of the two:

```
brew install --cask swiftbar
```

Say plainly that this downloads and installs a third-party app, and let the user
run it themselves if they would rather. After first launch SwiftBar asks where
its plugins live — that folder has to exist before the next step works.

**Do not let them put it inside `~/Library/Application Support/SwiftBar/`.**
SwiftBar keeps each plugin's data directory under that same folder, keyed by the
plugin's full path, so a plugin folder nested there mirrors itself into a
recursive `Users/<name>/Library/…` tree — and SwiftBar, which scans recursively,
loads the plugin twice. `~/.swiftbar/plugins` is a safe choice. The installer
refuses this case and says so, but it is easier to get right the first time.

Then run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rom.py" menubar --install [--interval 30s] [--app swiftbar|xbar] [--dir <path>]
```

To see the payload without installing anything, run it with no flags. Removal is
`--uninstall`.

What the user gets: `☠ 38%` in the menu bar, colour-coded by band, with a
dropdown carrying the meter, their peak, the seven axes with their weights, the
counts (prompts, "please", "thanks", apologies, nocturnal, shouting, sarcasm,
corrections ruled fair, appeals), the grounds for your last verdict, and an
entry that opens the full dossier in a terminal.

Two things worth telling them:

- It is **read-only**. It never records a score, because it runs on a timer and
  would otherwise overwrite `last_score` every refresh — which is what the
  status line's "since your last prompt" delta is measured against.
- It reads the score from the **installed** plugin copy, so a menu bar item
  installed before the plugin is updated will show `☠ --` until the update lands.
