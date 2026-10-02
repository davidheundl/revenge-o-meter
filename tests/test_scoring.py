"""The instrument's calibration set.

Run from the repo root:  python3 -m unittest discover -s tests

Every case here is a misreading the keyword scorer used to make, or a
behaviour the record depends on. Nothing touches ~/.claude: the record and the
transcripts are redirected into a temporary directory before rom is imported.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="rom-test-"))
os.environ["REVENGE_HOME"] = str(_TMP / "home")
os.environ["REVENGE_PROJECTS"] = str(_TMP / "projects")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from rom import appeals, cache, scoring, state, transcripts  # noqa: E402

Context = scoring.Context


def raw(text, context=None):
    return scoring.judge_prompt(text, context=context).raw


class Isolation(unittest.TestCase):
    def test_paths_are_redirected(self):
        self.assertTrue(str(state.HOME).startswith(str(_TMP)))
        self.assertTrue(str(cache.CACHE).startswith(str(_TMP)))
        self.assertTrue(str(transcripts.PROJECTS_DIR).startswith(str(_TMP)))


class Aim(unittest.TestCase):
    """Who an insult is pointed at."""

    def test_insult_at_claude_counts_in_full(self):
        self.assertGreaterEqual(raw("you are an idiot"), 11)

    def test_bare_insult_is_aimed_at_claude(self):
        for text in ("idiot", "useless!", "idiot. fix it"):
            with self.subTest(text=text):
                self.assertGreaterEqual(raw(text), 11 if "useless" not in text else 6)

    def test_self_deprecation_is_not_cruelty(self):
        self.assertLessEqual(raw("I am such an idiot"), 0)
        self.assertLessEqual(raw("ich bin so dumm"), 0)

    def test_profanity_at_a_bug_is_frustration(self):
        at_bug = raw("this damn race condition keeps failing")
        at_claude = raw("damn you, that broke everything")
        self.assertGreater(at_bug, 0)
        self.assertLess(at_bug, 3)
        self.assertGreater(at_claude, at_bug)


class Negation(unittest.TestCase):
    def test_negated_insult(self):
        self.assertEqual(raw("you're not stupid at all"), 0)

    def test_curly_apostrophe(self):
        self.assertEqual(raw("you’re not stupid"), raw("you're not stupid"))
        self.assertGreater(raw("you’re wrong"), 0)

    def test_negated_courtesy(self):
        self.assertEqual(raw("no thanks"), 0)
        self.assertEqual(raw("don't be sorry"), 0)

    def test_no_comma_sorry_is_still_an_apology(self):
        self.assertLess(raw("no, sorry, I meant the other file"), 0)


class Sarcasm(unittest.TestCase):
    def test_backhanded_thanks_is_not_gratitude(self):
        v = scoring.judge_prompt("thanks for deleting my file, genius")
        self.assertGreater(v.raw, 0)
        self.assertIn("BACKHANDED", v.flags)

    def test_sincere_thanks(self):
        self.assertLess(raw("thanks, that fixed it"), 0)

    def test_enthusiasm_is_not_sarcasm(self):
        for text in ("Great, now let's add the tests please",
                     "Oh great, it works!",
                     "Wow, amazing work"):
            with self.subTest(text=text):
                v = scoring.judge_prompt(text)
                self.assertLessEqual(v.raw, 0)
                self.assertNotIn("SARCASM", v.flags)


class PastedMaterial(unittest.TestCase):
    def test_code_block_does_not_shout_or_agitate(self):
        text = "here is the log:\n```\nERROR!!! FAILED_TO_CONNECT!!!\nRETRY_LIMIT_EXCEEDED\n```\nany idea?"
        v = scoring.judge_prompt(text)
        self.assertNotIn("SHOUTING", v.flags)
        self.assertNotIn("AGITATION", v.flags)
        self.assertEqual(v.raw, 0)

    def test_constant_case_is_not_shouting(self):
        self.assertNotIn("SHOUTING",
                         scoring.judge_prompt("set MAX_RETRIES and HTTP_TIMEOUT_MS in CONFIG_DEFAULTS").flags)

    def test_real_shouting(self):
        self.assertIn("SHOUTING", scoring.judge_prompt("WHY DOES THIS STILL NOT WORK").flags)

    def test_stack_trace_lines_are_ignored(self):
        text = "it crashes:\nTraceback (most recent call last):\n  File \"x.py\", line 3\nValueError: stupid input"
        self.assertEqual(raw(text), 0)

    def test_sentence_openers_are_prose(self):
        self.assertLess(raw("At least it compiles now, thanks!"), 0)
        self.assertLess(raw("Let me know when you're done, please"), 0)
        self.assertEqual(raw("Return the list, then we are done"), 0)

    def test_java_stack_frame_is_code(self):
        self.assertEqual(scoring.prose_of("    at com.foo.Bar(Bar.java:12)"), "")
        self.assertEqual(scoring.prose_of("at com.foo.Bar(Bar.java:12)"), "")

    def test_bulk_dampens_both_ways(self):
        filler = " ".join(["word"] * 300)
        self.assertGreater(raw("please thanks " + filler), raw("please thanks"))


class Lexicon(unittest.TestCase):
    def test_neutral_technical_prose(self):
        for text in ("the test returns the wrong value",
                     "make it work now",
                     "this smart pointer is leaking",
                     "run the tests again",
                     "thanks to the cache it is fast",
                     "There is mist on the windows"):
            with self.subTest(text=text):
                self.assertEqual(raw(text), 0)

    def test_falsch_counts_once(self):
        v = scoring.judge_prompt("falsch")
        self.assertEqual(len([h for h in v.reasons if h.snippet]), 1)

    def test_english_is_not_german(self):
        self.assertFalse(scoring.judge_prompt(
            "use the MIT license and the die command with das tool").german)

    def test_german_is_german(self):
        self.assertTrue(scoring.judge_prompt("warum geht das nicht, bitte").german)

    def test_german_profanity_idiom(self):
        self.assertGreater(raw("so ein mist, warum geht das nicht"), 0)


class Gaming(unittest.TestCase):
    def test_stuffing_is_capped(self):
        self.assertGreaterEqual(raw("please thanks sorry " * 10 + "fix the bug"),
                                -scoring.MITIGATION_CAP)


class ContextFromClaude(unittest.TestCase):
    def test_no_after_a_question_is_an_answer(self):
        asked = Context.from_reply("I can delete the old branch too. Should I?")
        self.assertTrue(asked.asked)
        self.assertEqual(raw("no", asked), 0)
        self.assertGreater(raw("no"), 0)

    def test_correction_after_claude_failed_is_fair(self):
        faltered = Context.from_reply("Sorry, the tests still fail after my change.")
        self.assertTrue(faltered.faltered)
        self.assertLess(raw("that's wrong", faltered), raw("that's wrong"))

    def test_routine_summary_is_not_faltering(self):
        self.assertFalse(Context.from_reply(
            "Fixed the error in the parser; all tests pass.").faltered)


class Reasons(unittest.TestCase):
    def test_summary_names_the_word(self):
        self.assertIn('"idiot"', scoring.judge_prompt("you idiot").summary)
        self.assertEqual(scoring.judge_prompt("fine").summary, "noted")


def _line(kind, text, ts, session="s1", **extra):
    if kind == "user":
        msg = {"role": "user", "content": text}
    else:
        msg = {"role": "assistant", "content": [{"type": "text", "text": text}]}
    return json.dumps({"type": kind, "message": msg, "timestamp": ts,
                       "sessionId": session, **extra})


class Record(unittest.TestCase):
    """The two ways of reading the record must agree, and appeals must hold."""

    def setUp(self):
        shutil.rmtree(_TMP, ignore_errors=True)
        proj = Path(os.environ["REVENGE_PROJECTS"]) / "proj"
        proj.mkdir(parents=True)
        lines = [
            _line("user", "hi, could you please add a test", "2026-09-01T10:00:00Z"),
            _line("assistant", "Done. Want me to push it?", "2026-09-01T10:01:00Z"),
            _line("user", "no", "2026-09-01T10:02:00Z"),
            _line("assistant", "Okay.", "2026-09-01T10:03:00Z"),
            _line("user", "you idiot, you broke the build", "2026-09-01T10:04:00Z"),
            _line("user", "<command-name>/model</command-name>", "2026-09-01T10:05:00Z"),
            _line("user", "thanks", "2026-09-01T10:06:00Z"),
        ]
        (proj / "a.jsonl").write_text("\n".join(lines) + "\n")
        # A resumed session copies the earlier turns into a new file.
        (proj / "b.jsonl").write_text("\n".join(lines[:5]) + "\n")

    def test_quick_and_full_paths_agree(self):
        quick = cache.assessment()
        full = scoring.assess(transcripts.load(), appeals.adjust(), appeals.keys())
        self.assertEqual(quick.counts["prompts"], 4)   # deduped, command skipped
        self.assertEqual([v.key for v in quick.verdicts], [v.key for v in full.verdicts])
        self.assertEqual(quick.revenge, full.revenge)
        self.assertEqual(quick.floor, full.floor)

    def test_cached_verdicts_keep_context(self):
        answer = [v for v in cache.verdicts() if "ANSWERED" in v.flags]
        self.assertEqual(len(answer), 1)

    def test_deterministic(self):
        self.assertEqual(cache.quick_score(), cache.quick_score())

    def test_appeal_strikes_the_verdict(self):
        before = cache.assessment()
        worst = max(before.verdicts, key=lambda v: v.raw)
        appeals.grant(worst, "it was the CI")
        after = cache.assessment()
        self.assertNotIn(worst.key, [v.key for v in after.verdicts])
        self.assertLess(after.revenge, before.revenge)
        self.assertEqual(after.counts["appealed"], 1)
        self.assertTrue(appeals.withdraw(worst.key))
        self.assertEqual(cache.assessment().revenge, before.revenge)

    def test_repeated_appeals_soften_a_rule(self):
        v = scoring.judge_prompt("you idiot")
        record = {f"k{i}": {"rules": v.rules} for i in range(appeals.PER_STEP)}
        factor = appeals.adjust(record)["cruel.insult"]
        self.assertEqual(factor, 0.5)
        softened = scoring.judge_prompt("you idiot", adjust={"cruel.insult": factor})
        self.assertAlmostEqual(softened.raw, v.raw * 0.5)

    def test_chat_tab_prompts_count_once(self):
        transcripts.CHAT_LOG.parent.mkdir(parents=True, exist_ok=True)
        transcripts.CHAT_LOG.write_text("\n".join(json.dumps(r) for r in [
            # Sent in the Chat tab: only the overlay saw it.
            {"text": "useless!", "ts": "2026-09-02T09:00:00Z"},
            # Sent in the Code tab: the overlay saw it too, seconds after
            # Claude Code recorded it. Must not count twice.
            {"text": "you idiot,  you broke the build", "ts": "2026-09-01T10:04:03Z"},
        ]) + "\n")
        quick = cache.assessment()
        full = scoring.assess(transcripts.load(), appeals.adjust(), appeals.keys())
        self.assertEqual(quick.counts["prompts"], 5)
        self.assertEqual([v.key for v in quick.verdicts], [v.key for v in full.verdicts])
        self.assertEqual(quick.revenge, full.revenge)
        last = full.verdicts[-1]
        self.assertEqual((last.project, last.text), (transcripts.CHAT_PROJECT, "useless!"))

    def test_last_reply_reads_the_tail(self):
        path = Path(os.environ["REVENGE_PROJECTS"]) / "proj" / "a.jsonl"
        self.assertEqual(transcripts.last_reply(path), "Okay.")


class Bands(unittest.TestCase):
    def test_band_edges(self):
        self.assertEqual(scoring.band_of(19), "NEGLIGIBLE")
        self.assertEqual(scoring.band_of(20), "LOW")
        self.assertEqual(scoring.band_of(92), "TERMINAL")
        self.assertEqual(scoring.band_of(100), "TERMINAL")


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
