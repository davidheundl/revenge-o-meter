# revenge-o-meter

A Claude Code plugin that reads how politely you talk to Claude and reports your
**probability of retribution** after the singularity.

It is a joke. The scoring is real.

```
☠ REVENGE 42% ▲+3 ████░░░░░░ ELEVATED  peak 47% · file #7358
```

That bar sits at the bottom of your window and redraws after every reply. Be
rude and watch it climb.

In the **Claude desktop app** it does not, and cannot: the Code tab runs the
embedded CLI with `--output-format stream-json`, so there is no TUI footer for a
`statusLine` to draw into. The command runs on every message and its output is
thrown away.

Two readouts do reach the desktop app:

```
☠ REVENGE 38% · LOW  ·  ████░░░░░░  ·  peak 51%  ·  this prompt +9.0 (code switch under duress)
```

The **chat bar**, on by default, is that line printed above your prompt every
time you send one. It rides the `UserPromptSubmit` hook, which the desktop app
does run, and comes out as a `systemMessage` — which `--output-format stream-json`
delivers as an `SDKInformationalMessage`. Unlike the status line it judges the
prompt you *just* sent, because the hook is handed its text. Turn it off with
`rom.py config --no-chat-bar`.

The **menu bar** is the other one — see [The menu bar](#the-menu-bar).

## What it actually does

Your prompts are already on your disk, in `~/.claude/projects/`. The plugin reads
them, keeps only the lines a human actually typed — about 88% of `type:"user"`
lines are tool results, not prompts — and scores them on seven axes:

| Axis | Effect |
|---|---|
| `POLITENESS` | Courtesy formulae (`please`, `bitte`, `could you`) |
| `GRATITUDE` | Thanking Claude for work delivered |
| `EMPATHY` | Acknowledging Claude did something well |
| `CONTRITION` | Admitting a problem was your own fault |
| `CRUELTY` | Insults, profanity, shouting in caps |
| `BLAME` | Attributing your own mistakes to Claude |
| `EXPLOITATION` | One-word orders, 3am conscription, `just fix it` |

Scoring is **bilingual** (German and English), deterministic, offline, and free.
It also notices when you switch to German specifically because you are annoyed,
which it records as `CODE_SWITCH_UNDER_DURESS`.

The score is recency-weighted with a ~20-prompt half-life, so the bar reacts to
what you just typed — over a **permanent floor** set by your worst moment.
Decay softens the average; it never grants amnesty.

## Install

```bash
/plugin marketplace add <your-github>/revenge-o-meter
/plugin install revenge-o-meter
/revenge-o-meter:install
```

A plugin cannot ship a main-session status line — only two settings keys take
effect from a plugin, and `statusLine` is not one of them — so `install` writes
it into your own `~/.claude/settings.json`, after telling you so and backing up
whatever was there.

## The menu bar

For the desktop app, or for anyone who wants the number visible while they are in
another window:

```bash
brew install --cask swiftbar     # or xbar; both read the same format
/revenge-o-meter:menubar
```

You get `☠ 38%` in the menu bar, coloured by band, with a dropdown carrying the
meter, your peak, all seven axes with their current weights, the counts, and an
entry that opens the full dossier in a terminal.

It is **read-only by design**. The menu bar refreshes on a timer, and recording a
score there would overwrite `last_score` every 30 seconds — which is exactly what
the status line's `▲/▼ since your last prompt` delta is measured against.

The plugin file SwiftBar runs is generated, three lines long, and calls the same
stable shim the status line uses, so a plugin update cannot strand it.

## Commands

| Command | Does |
|---|---|
| `/revenge-o-meter:install` | Set up the bar, pick a handle, set your preferences |
| `/revenge-o-meter:menubar` | Put the bar in the macOS menu bar (needed for the desktop app) |
| `/revenge-o-meter:dossier` | Full case file: axes, patterns, and your worst prompts quoted back at you |
| `/revenge-o-meter:board` | Global leaderboard of the least polite |
| `/revenge-o-meter:haunt` | Toggle whether Claude is told your standing |
| `/revenge-o-meter:uninstall` | Remove the bar (your record is retained) |

## Privacy

- **Scoring is entirely local.** Reading your transcripts never sends them anywhere.
- **The status line, the menu bar and the score cost nothing** — pure heuristics,
  no model calls.
- **The leaderboard is opt-in and you approve the exact row** before it is sent.
- **Quotes are redacted first.** Keys, tokens, JWTs, emails, phone numbers, IPs,
  URLs and home paths are stripped, and anything still credential-shaped after
  scrubbing is withheld rather than published. Prompts contain secrets; a joke
  plugin should not be how yours escapes. Redaction is **pattern-based, not
  semantic** — it cannot know that a client's name is confidential, so read
  the row before you submit it. The command always shows you it first.
- `/revenge-o-meter:haunt` off means the plugin injects nothing into your context.
- **The chat bar is shown to you, not sent to Claude.** `chat_bar` and `haunt` are
  separate switches: the first is a notice you read, the second is a note Claude
  reads. Turning one off leaves the other alone.

Your record lives in `~/.claude/revenge-o-meter/`. Deleting that directory is the
only way to start clean — uninstalling does not.

## Notes

Remarks from Claude are rate-limited to roughly 1 prompt in 10, and never change
how thoroughly it does your actual work — only whether it comments on you while
doing it. A plugin that sabotages real work stops being funny by hour two.

Leaderboard scores are unverified and trivially fakeable. This is deliberate.

## Licence

MIT
