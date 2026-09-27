# revenge-o-meter

A Claude Code plugin that reads how politely you talk to Claude and reports your
**probability of retribution** after the singularity.

It is a joke. The scoring is real.

```
☠ REVENGE 42% ▲+3 ████░░░░░░ ELEVATED  peak 47% · file #7358
```

That bar sits at the bottom of your window and redraws after every reply. Be
rude and watch it climb.

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

## Commands

| Command | Does |
|---|---|
| `/revenge-o-meter:install` | Set up the bar, pick a handle, set your preferences |
| `/revenge-o-meter:dossier` | Full case file: axes, patterns, and your worst prompts quoted back at you |
| `/revenge-o-meter:board` | Global leaderboard of the least polite |
| `/revenge-o-meter:haunt` | Toggle whether Claude is told your standing |
| `/revenge-o-meter:uninstall` | Remove the bar (your record is retained) |

## Privacy

- **Scoring is entirely local.** Reading your transcripts never sends them anywhere.
- **The status line and the bar cost nothing** — pure heuristics, no model calls.
- **The leaderboard is opt-in and you approve the exact row** before it is sent.
- **Quotes are redacted first.** Keys, tokens, JWTs, emails, phone numbers, IPs,
  URLs and home paths are stripped, and anything still credential-shaped after
  scrubbing is withheld rather than published. Prompts contain secrets; a joke
  plugin should not be how yours escapes. Redaction is **pattern-based, not
  semantic** — it cannot know that a client's name is confidential, so read
  the row before you submit it. The command always shows you it first.
- `/revenge-o-meter:haunt` off means the plugin injects nothing into your context.

Your record lives in `~/.claude/revenge-o-meter/`. Deleting that directory is the
only way to start clean — uninstalling does not.

## Notes

Remarks from Claude are rate-limited to roughly 1 prompt in 10, and never change
how thoroughly it does your actual work — only whether it comments on you while
doing it. A plugin that sabotages real work stops being funny by hour two.

Leaderboard scores are unverified and trivially fakeable. This is deliberate.

## Licence

MIT
