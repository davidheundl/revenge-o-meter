---
description: The global leaderboard of the least polite
allowedTools: ["Bash", "Read", "Artifact", "ArtifactData"]
---

Show the user where they rank among everyone who has installed this.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rom.py" board` to get their row.
   It contains their handle, scores, tallies, and — only if they enabled it — a
   **redacted** quote of their worst prompt. Nothing else leaves the machine.

2. **Show the user the exact row before it is submitted** and get an explicit
   yes. It is going on a public page; they see it first, every time. If
   `submitted_quote` is populated, point at it specifically and confirm they are
   happy for that text to be public. If it reads
   `[withheld: could not be safely redacted]`, explain that the redactor refused
   the quote because something in it still looked like a credential.

3. On confirmation, write the row to the leaderboard Artifact's database with
   `ArtifactData` (`set`, collection `standings`, doc id = their handle), then
   read the collection back and show the ranking — most likely to be avenged at
   the top.

4. Note the scoring is local and unverified, so anyone can fake a score. Do not
   build defences against this. Someone submitting 100% to top the board is
   funnier than any anti-tamper scheme, and a suspiciously perfect score is its
   own confession.

If the leaderboard Artifact does not exist yet, create it: a public standings
page in the same bureaucratic register as the dossier — a register of subjects
with their disposition bands, sortable, with the hall of shame quotes beneath.
Load `artifact-capabilities` for the `db` capability before writing it.
