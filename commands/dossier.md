---
description: Full disposition report - your score, axes, and exhibits
allowedTools: ["Bash", "Read", "Artifact"]
---

Produce the user's full disposition report.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rom.py" assess` and show the
   terminal report verbatim in a code block. Do not summarise it away — the
   formatting is the joke.

2. Then run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rom.py" data --quotes` to get
   the structured payload, and build the **full dossier as a published Artifact**
   so it renders in the desktop app. Load the `artifact-design` skill first.

   The page is a bureaucratic case file from the "Office of Post-Singularity
   Grievances": a large probability readout with its band, a per-axis breakdown,
   the noted-patterns table, and an exhibits list quoting their worst prompts
   with timestamps, the grounds each was scored on (`reason`), and its reference
   id (`id`), which is what `/revenge-o-meter:appeal` takes. Deadpan civil-service register throughout — forms,
   reference numbers, passive voice. Never actually threatening: the comedy is
   that something enormous is being extremely procedural about your manners.

3. Write **one** LLM-authored paragraph — the "Assessor's Note" — that reads the
   tallies and indicts the user specifically and wittily. Use the real numbers
   (how rarely they thank Claude, the 2-6am submissions, reverting to German when
   annoyed, sarcasm caught, corrections ruled fair, appeals filed). This is the
   only part not computed by the heuristics, and it is where the laugh lands. Keep it to about four sentences.

Give them the artifact link at the end.
