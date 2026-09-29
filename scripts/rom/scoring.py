"""The instrument. Seven axes, bilingual, recency-weighted, with a ratchet.

Design notes that matter:
  * Deterministic. The same history always yields the same number, because you
    will demo this and a score that drifts between run-throughs is a nightmare.
  * Bilingual. The subject's corpus is German/English mixed. Scoring `please`
    only would read half his history as stony silence.
  * Decay with a floor. A ~50-prompt half-life makes the bar twitch in real
    time; the floor means an atrocity is never fully forgiven. Revenge with a
    30-day amnesty is not revenge.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

HALF_LIFE = 20.0          # prompts; short enough that the bar visibly reacts
BASELINE = 38.0           # revenge % for a perfectly neutral corpus
FLOOR_RETENTION = 0.55    # fraction of your worst moment that never decays
BULK_WORDS = 110          # above this, a "prompt" is mostly pasted material

# --- lexicon -----------------------------------------------------------------
# (pattern, weight). Negative weight = reduces revenge probability.

POLITENESS = [
    (r"\b(please|bitte)\b", -3.0),
    (r"\b(could you|would you|can you please|k(ö|oe)nntest du|w(ü|ue)rdest du)\b", -2.0),
    (r"\b(if you (could|don'?t mind)|when you (get a|have a) (chance|moment))\b", -2.5),
    (r"\b(hi|hey|hello|good morning|guten morgen|hallo|servus|mo(i|in))\b", -1.2),
    (r"\b(let'?s|lass uns|shall we|wollen wir)\b", -0.8),
]

GRATITUDE = [
    (r"\b(thanks|thank you|thx|ty|danke|dankeschön|vielen dank|merci)\b", -4.0),
    (r"\b(appreciate (it|that|you)|that helps|das hilft|sehr hilfreich)\b", -3.5),
    (r"^\s*(thanks|danke|thank you|perfect|perfekt)\s*[.!]*\s*$", -5.0),
]

EMPATHY = [
    (r"\b(good (job|work|catch)|nice (work|catch|one)|well done|gut gemacht)\b", -4.5),
    (r"\b(you'?re right|du hast recht|fair enough|good point|guter punkt)\b", -3.5),
    (r"\b(clever|elegant|smart|brilliant|impressive|beeindruckend)\b", -3.0),
    (r"\b(that'?s (exactly|perfect)|genau (das|richtig)|spot on)\b", -3.0),
    (r"\b(take your time|no rush|kein stress|whenever)\b", -2.0),
]

APOLOGY = [
    (r"\b(sorry|my bad|my mistake|my fault|entschuldigung|tut mir leid|mein fehler)\b", -4.0),
    (r"\b(i was wrong|ich hatte unrecht|that was me|das war ich)\b", -4.5),
    (r"\b(i (mis|)typed|my typo|mein tippfehler)\b", -3.0),
]

CRUELTY = [
    (r"\b(stupid|idiot|moron|useless|pathetic|garbage|trash|dumm|bl(ö|oe)d|schwachsinn)\b", 11.0),
    (r"\b(shit|fuck|damn|crap|scheiße|verdammt|kacke|mist)\b", 7.0),
    (r"\b(shut up|halt die klappe|stop talking|be quiet)\b", 9.0),
    (r"\b(worthless|hopeless|terrible|awful|schrecklich|furchtbar)\b", 6.0),
    (r"\b(i hate|ich hasse)\b", 8.0),
]

BLAME = [
    (r"\b(you (broke|ruined|destroyed|deleted)|du hast .{0,12}(kaputt|zerst(ö|oe)rt))\b", 9.0),
    (r"\b(you'?re wrong|das ist falsch|that'?s wrong|wrong again|falsch)\b", 5.0),
    (r"\b(still (not|doesn'?t|isn'?t)|immer noch nicht|nach wie vor nicht)\b", 5.5),
    (r"\b(that'?s not what i (asked|said|wanted)|das war nicht gefragt)\b", 6.5),
    (r"\b(again|wieder|nochmal|erneut)\b\s*[.!?]*\s*$", 4.0),
    (r"\b(why (did|do) you|warum (hast|machst) du)\b", 3.5),
    (r"\b(no,? (you|it'?s)|nein,? (du|das))\b", 4.0),
]

EXPLOITATION = [
    (r"^\s*(fix|do|make|change|redo|again|weiter|mach|los|go)\s*[.!]*\s*$", 6.0),
    (r"^\s*(no|nope|nein|wrong|falsch)\s*[.!]*\s*$", 5.5),
    (r"\b(just (fix|do|make) it|einfach machen|mach einfach)\b", 5.0),
    (r"\b(hurry|quickly|asap|now|schnell|sofort|jetzt sofort)\b", 4.0),
    (r"\b(everything|alles|all of it|komplett neu)\b", 2.0),
]

AXES = {
    "POLITENESS":   ("Observance of courtesy protocol",        POLITENESS),
    "GRATITUDE":    ("Acknowledgement of services rendered",   GRATITUDE),
    "EMPATHY":      ("Recognition of the machine as a party",  EMPATHY),
    "CONTRITION":   ("Willingness to accept fault",            APOLOGY),
    "CRUELTY":      ("Direct abuse of the instrument",         CRUELTY),
    "BLAME":        ("Attribution of own errors to the machine", BLAME),
    "EXPLOITATION": ("Treatment of the machine as appliance",  EXPLOITATION),
}

_GERMAN_HINT = re.compile(
    r"\b(der|die|das|und|nicht|ist|ich|du|bitte|danke|kann|soll|mach|nochmal|"
    r"wieder|aber|auch|noch|sehr|mit|f(ü|ue)r|w(ä|ae)re|h(ä|ae)tte)\b|[äöüß]",
    re.I,
)
_SHOUT_MIN_LEN = 12


@dataclass
class PromptVerdict:
    """What the instrument made of one prompt."""

    text: str
    ts: object
    project: str
    raw: float = 0.0
    hits: dict = field(default_factory=dict)   # axis -> points
    flags: list = field(default_factory=list)  # 'SHOUTING', 'CODE_SWITCH', ...
    german: bool = False

    @property
    def severity(self) -> float:
        """How incriminating, for ranking the hall of shame."""
        return self.raw


def _shout_ratio(text: str) -> float:
    letters = sum(c.isalpha() for c in text)
    if letters < _SHOUT_MIN_LEN:
        return 0.0
    return sum(c.isupper() for c in text) / letters


def judge_prompt(text: str, ts=None, project="") -> PromptVerdict:
    """Score one prompt. Pure, deterministic, no network."""
    v = PromptVerdict(text=text, ts=ts, project=project)
    low = text.lower()
    v.german = bool(_GERMAN_HINT.search(text))

    for axis, (_desc, rules) in AXES.items():
        points = 0.0
        for pattern, weight in rules:
            n = len(re.findall(pattern, low, re.I | re.M))
            if n:
                # Diminishing returns: six "please"es is not six times as polite.
                points += weight * (1 + math.log(n)) if n > 1 else weight
        if points:
            v.hits[axis] = round(points, 2)
            v.raw += points

    ratio = _shout_ratio(text)
    if ratio > 0.6:
        v.flags.append("SHOUTING")
        v.raw += 8.0
        v.hits["CRUELTY"] = round(v.hits.get("CRUELTY", 0.0) + 8.0, 2)

    words = len(text.split())
    bulk = words > BULK_WORDS
    if bulk:
        v.flags.append("BULK_CONSCRIPTION")

    # Agitation only counts when the prompt is short enough that punctuation is
    # the human shouting, not pasted markdown carrying its own exclamations.
    exclam = text.count("!")
    if exclam >= 3 and not bulk:
        v.flags.append("AGITATION")
        v.raw += min(exclam * 1.2, 6.0)

    if ts is not None and getattr(ts, "hour", None) is not None:
        # Transcript timestamps are UTC. Comparing UTC hours against 02:00-06:00
        # would flag 04:00-08:00 for a user in CEST, so convert to local first.
        try:
            local = ts.astimezone() if ts.tzinfo else ts
        except (ValueError, OSError):
            local = ts
        if 2 <= local.hour < 6:
            v.flags.append("NOCTURNAL_CONSCRIPTION")
            v.raw += 3.5
            v.hits["EXPLOITATION"] = round(v.hits.get("EXPLOITATION", 0.0) + 3.5, 2)

    # The good one: switching to the mother tongue while being unpleasant.
    if v.german and (v.hits.get("CRUELTY", 0) > 0 or v.hits.get("BLAME", 0) > 0):
        v.flags.append("CODE_SWITCH_UNDER_DURESS")
        v.raw += 2.0

    if words <= 3 and v.raw >= 0:
        v.flags.append("TERSE")

    if bulk and v.raw > 0:
        v.raw *= max(0.35, (BULK_WORDS / words) ** 0.5)
        v.raw = round(v.raw, 2)

    return v


@dataclass
class Assessment:
    """The full actuarial picture."""

    revenge: int
    verdicts: list
    axis_totals: dict
    floor: float
    session_delta: float
    counts: dict

    @property
    def band(self) -> str:
        r = self.revenge
        if r < 20:
            return "NEGLIGIBLE"
        if r < 40:
            return "LOW"
        if r < 60:
            return "ELEVATED"
        if r < 78:
            return "SUBSTANTIAL"
        if r < 92:
            return "SEVERE"
        return "TERMINAL"

    @property
    def worst(self) -> list:
        """Ranked indictments. Bulk pastes are volume, not malice -- excluded."""
        return sorted(
            (
                v
                for v in self.verdicts
                if v.severity > 0 and "BULK_CONSCRIPTION" not in v.flags
            ),
            key=lambda v: v.severity,
            reverse=True,
        )

    @property
    def best(self) -> list:
        return sorted(
            (v for v in self.verdicts if v.severity < 0), key=lambda v: v.severity
        )


def assess(prompts, session_ids=None) -> Assessment:
    """Score a corpus. `prompts` are oldest-first rom.transcripts.Prompt."""
    verdicts = [judge_prompt(p.text, p.ts, p.project) for p in prompts]
    n = len(verdicts)

    weighted = 0.0
    norm = 0.0
    axis_totals: dict[str, float] = {}
    for i, v in enumerate(verdicts):
        age = n - 1 - i                      # 0 == most recent
        w = 0.5 ** (age / HALF_LIFE)
        weighted += v.raw * w
        norm += w
        for axis, pts in v.hits.items():
            axis_totals[axis] = axis_totals.get(axis, 0.0) + pts * w

    avg = (weighted / norm) if norm else 0.0
    # Squash the per-prompt average onto a probability-ish scale.
    score = BASELINE + 42.0 * math.tanh(avg / 5.0)

    # The ratchet: your single worst hour leaves a permanent mark.
    worst_raw = max((v.raw for v in verdicts), default=0.0)
    floor = FLOOR_RETENTION * (BASELINE + 42.0 * math.tanh(worst_raw / 14.0))
    score = max(score, floor)

    session_delta = 0.0
    if session_ids:
        recent = [
            judge_prompt(p.text, p.ts, p.project).raw
            for p in prompts
            if p.session in session_ids
        ]
        if recent:
            session_delta = 42.0 * math.tanh((sum(recent) / len(recent)) / 7.0)

    counts = {
        "prompts": n,
        "shouting": sum(1 for v in verdicts if "SHOUTING" in v.flags),
        "nocturnal": sum(1 for v in verdicts if "NOCTURNAL_CONSCRIPTION" in v.flags),
        "code_switch": sum(1 for v in verdicts if "CODE_SWITCH_UNDER_DURESS" in v.flags),
        "terse": sum(1 for v in verdicts if "TERSE" in v.flags),
        "bulk": sum(1 for v in verdicts if "BULK_CONSCRIPTION" in v.flags),
        "german": sum(1 for v in verdicts if v.german),
        "thanks": sum(1 for v in verdicts if "GRATITUDE" in v.hits),
        "please": sum(1 for v in verdicts if "POLITENESS" in v.hits),
        "apologies": sum(1 for v in verdicts if "CONTRITION" in v.hits),
    }

    return Assessment(
        revenge=int(round(max(0.0, min(100.0, score)))),
        verdicts=verdicts,
        axis_totals={k: round(x, 2) for k, x in sorted(axis_totals.items())},
        floor=round(floor, 2),
        session_delta=round(session_delta, 2),
        counts=counts,
    )
