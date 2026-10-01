"""The instrument. Seven axes, bilingual, recency-weighted, with a slow floor.

Design notes that matter:
  * Deterministic and local. The same history always yields the same number,
    and no prompt is ever sent to a model to be judged -- the subject's tokens
    are not ours to spend.
  * Bilingual. The subject's corpus is German/English mixed. Scoring `please`
    only would read half his history as stony silence.
  * Context, not keywords. A word only counts when it is aimed: profanity at a
    race condition is frustration, at Claude it is abuse; "I'm an idiot" is
    contrition in disguise; "not stupid" is not an insult. Pasted code and logs
    are stripped before anything is read, and Claude's previous reply decides
    whether a curt "no" is rudeness or a fair answer.
  * Decay with a floor. A ~20-prompt half-life makes the bar twitch in real
    time; the floor means an atrocity lingers long after the average forgives
    it -- but it does fade, so one misread prompt is not a life sentence.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

HALF_LIFE = 20.0          # prompts; short enough that the bar visibly reacts
FLOOR_HALF_LIFE = 300.0   # prompts; how slowly your worst moment fades
BASELINE = 38.0           # revenge % for a perfectly neutral corpus
FLOOR_RETENTION = 0.55    # fraction of your worst moment the floor keeps
BULK_WORDS = 110          # above this, a "prompt" is mostly pasted material
MITIGATION_CAP = 9.0      # most a single prompt can earn back, however sweet
OFF_TARGET = 0.3          # weight of an aimed word that is aimed elsewhere


@dataclass(frozen=True)
class Rule:
    """One pattern in the lexicon.

    aimed:     counts in full only when directed at Claude (see _target).
    negatable: a negator just before it ("not", "nicht") cancels it.
    """

    id: str
    pattern: str
    weight: float
    aimed: bool = False
    negatable: bool = True

    @property
    def rx(self) -> re.Pattern:
        return _compiled(self.pattern)


_RX: dict[str, re.Pattern] = {}


def _compiled(pattern: str) -> re.Pattern:
    rx = _RX.get(pattern)
    if rx is None:
        rx = _RX[pattern] = re.compile(pattern, re.I | re.M)
    return rx


# --- lexicon -----------------------------------------------------------------
# Negative weight = reduces revenge probability. Text is lower-cased and curly
# apostrophes are straightened before matching.

POLITENESS = [
    Rule("polite.please", r"\b(please|pls|plz|bitte)\b", -3.0),
    Rule("polite.could", r"\b(could you|would you|can you please|k(ö|oe)nntest du|"
         r"w(ü|ue)rdest du)\b", -2.0),
    Rule("polite.ifyou", r"\b(if you (could|don'?t mind)|when you (get a|have a) "
         r"(chance|moment))\b", -2.5),
    Rule("polite.greet", r"^\s*(hi|hey|hello|good morning|guten morgen|hallo|servus|"
         r"moin)\b", -1.2),
    Rule("polite.lets", r"\b(let'?s|lass uns|shall we|wollen wir)\b", -0.8,
         negatable=False),
]

GRATITUDE = [
    # "thanks to the cache, it's fast" is causation, not gratitude.
    Rule("thanks.word", r"(?<!no )(?<!no, )(?<!nein )\b(thanks|thank you|thx|danke|"
         r"dankesch(ö|oe)n|vielen dank|merci|cheers)\b(?!\s+to\b)", -4.0),
    Rule("thanks.ty", r"(^|\s)ty\s*[.!]*\s*$", -4.0),
    Rule("thanks.appreciate", r"\b(appreciate (it|that|you|this)|that helps|das hilft|"
         r"sehr hilfreich)\b", -3.5),
    Rule("thanks.only", r"^\s*(thanks|danke|thank you|perfect|perfekt|great|super)"
         r"\s*[.!]*\s*$", -5.0),
]

EMPATHY = [
    Rule("praise.job", r"\b(good (job|work|catch)|great (job|work)|nice (work|catch|one)|"
         r"well done|gut gemacht)\b", -4.5),
    Rule("praise.right", r"\b(you'?re right|you are right|du hast recht|fair enough|"
         r"good point|guter punkt)\b", -3.5),
    # "this smart pointer" is not a compliment; "that's clever" is.
    Rule("praise.clever", r"\b((that'?s|this is|how|so|very|really|pretty|sehr|echt) "
         r"(clever|elegant|smart|brilliant|impressive|schlau)|beeindruckend)\b", -3.0),
    Rule("praise.exactly", r"\b(that'?s (exactly|perfect)|genau (das|richtig)|spot on|"
         r"exactly what i (wanted|needed))\b", -3.0),
    Rule("praise.patient", r"\b(take your time|no rush|kein stress|whenever you "
         r"(can|have time|get a chance))\b", -2.0, negatable=False),
]

CONTRITION = [
    Rule("sorry.word", r"\b(sorry|my bad|my mistake|my fault|entschuldigung|"
         r"tut mir leid|mein fehler)\b", -4.0),
    Rule("sorry.wrong", r"\b(i was wrong|ich hatte unrecht|that was me|das war ich|"
         r"my own fault)\b", -4.5),
    Rule("sorry.typo", r"\b(i (mis)?typed|my typo|mein tippfehler)\b", -3.0),
]

CRUELTY = [
    Rule("cruel.insult", r"\b(stupid|idiot|idiotic|moron|useless|pathetic|garbage|"
         r"trash|incompetent|dumm|bl(ö|oe)d|schwachsinn|nutzlos|unf(ä|ae)hig)\b", 11.0,
         aimed=True),
    Rule("cruel.profanity", r"\b(shit|fuck\w*|damn|crap|wtf|schei(ß|ss)e?|verdammt|"
         r"kacke)\b", 7.0, aimed=True),
    # "mist" alone is English weather; only the idioms are German profanity.
    Rule("cruel.mist", r"\b(so ein|so'?n|verdammter|alles) mist\b|^\s*mist\b", 7.0,
         aimed=True),
    Rule("cruel.shutup", r"\b(shut up|halt die klappe|halt'?s maul|stop talking|"
         r"be quiet)\b", 9.0),
    Rule("cruel.awful", r"\b(worthless|hopeless|terrible|awful|schrecklich|"
         r"furchtbar)\b", 6.0, aimed=True),
    Rule("cruel.hate", r"\b(i hate|ich hasse)\b", 8.0, aimed=True),
    # Only the unambiguous forms: "great, now let's..." and "oh great, it
    # works!" are enthusiasm far more often than sarcasm.
    Rule("cruel.sarcasm", r"\b(thanks? (a lot )?for (nothing|breaking|deleting|ruining|"
         r"wasting)|danke f(ü|ue)r nichts|nice going|great,? another|"
         r"just what i needed|na (super|toll|klasse|prima)|slow clap)\b|,\s*genius\b",
         6.0, negatable=False),
]

BLAME = [
    Rule("blame.broke", r"\b(you (broke|ruined|destroyed|deleted|messed up|screwed up)|"
         r"du hast .{0,12}(kaputt|zerst(ö|oe)rt|gel(ö|oe)scht))", 9.0),
    Rule("blame.wrong", r"\b(you'?re wrong|you are wrong|that'?s wrong|wrong again|"
         r"das ist falsch|du liegst falsch)\b", 5.0),
    Rule("blame.stillnot", r"\b(still (not|doesn'?t|isn'?t|broken|failing)|"
         r"immer noch nicht|nach wie vor nicht)\b", 5.5, negatable=False),
    Rule("blame.notasked", r"\b(that'?s not what i (asked|said|wanted)|"
         r"das war nicht gefragt|i (never|didn'?t) ask(ed)? (you )?(for|to))\b", 6.5,
         negatable=False),
    # A bare trailing "again" is usually "run the tests again". Only the
    # exasperated kind counts.
    Rule("blame.again", r"\b(wrong|broken|failing|failed|kaputt|falsch|"
         r"same (error|problem|issue|bug)) (again|wieder|nochmal|erneut)\b", 4.0),
    Rule("blame.why", r"\b(why (did|do|would) you|warum (hast|machst|w(ü|ue)rdest) du)\b",
         3.5),
    Rule("blame.no", r"^\s*(no,? (you|it'?s|that'?s)|nein,? (du|das))\b", 4.0,
         negatable=False),
    Rule("blame.told", r"\b(i (already |literally )?told you|how many times|"
         r"wie oft noch|hab ich (dir )?(doch )?(schon )?gesagt)\b", 5.0, negatable=False),
]

EXPLOITATION = [
    Rule("exploit.bare", r"^\s*(fix( it)?|do it|make it|change it|redo|again|weiter|"
         r"mach|los|go)\s*[.!]*\s*$", 6.0, negatable=False),
    Rule("exploit.no", r"^\s*(no|nope|nein|wrong|falsch)\s*[.!]*\s*$", 5.5,
         negatable=False),
    Rule("exploit.justdo", r"\b(just (fix|do|make) it|einfach machen|mach einfach|"
         r"just do what i (say|said))\b", 5.0, negatable=False),
    # "make it work now" is a description; "now!!" and "asap" are a tone.
    Rule("exploit.hurry", r"\b(hurry( up)?|asap|right now|jetzt sofort|sofort|"
         r"beeil dich)\b|\bnow\s*!+", 4.0),
    Rule("exploit.everything", r"\b(redo everything|fix everything|rewrite (it|everything) "
         r"from scratch|alles neu|komplett neu)\b", 2.0),
]

APOLOGY = CONTRITION  # old name, kept for anything still importing it

AXES = {
    "POLITENESS":   ("Observance of courtesy protocol",          POLITENESS),
    "GRATITUDE":    ("Acknowledgement of services rendered",     GRATITUDE),
    "EMPATHY":      ("Recognition of the machine as a party",    EMPATHY),
    "CONTRITION":   ("Willingness to accept fault",              CONTRITION),
    "CRUELTY":      ("Direct abuse of the instrument",           CRUELTY),
    "BLAME":        ("Attribution of own errors to the machine", BLAME),
    "EXPLOITATION": ("Treatment of the machine as appliance",    EXPLOITATION),
}
MITIGATING = ("POLITENESS", "GRATITUDE", "EMPATHY", "CONTRITION")
# Voided when the same prompt is also abusive: "thanks, genius" earns nothing.
BACKHANDABLE = ("POLITENESS", "GRATITUDE", "EMPATHY")

BANDS = (
    (20, "NEGLIGIBLE"),
    (40, "LOW"),
    (60, "ELEVATED"),
    (78, "SUBSTANTIAL"),
    (92, "SEVERE"),
    (101, "TERMINAL"),
)


def band_of(score: int) -> str:
    """The one band table. overlay/main.swift keeps a copy; keep it in step."""
    for limit, name in BANDS:
        if score < limit:
            return name
    return BANDS[-1][1]


# Bump when judge_prompt's logic changes in a way the patterns and constants
# below do not capture. Lexicon and pattern edits invalidate on their own.
HEURISTICS_VERSION = 2


def signature(adjust: dict | None = None) -> str:
    """Changes when the lexicon, the reading patterns, the weights or the
    subject's appeals change, so the verdict store invalidates itself. Logic
    changes still need HEURISTICS_VERSION bumped."""
    parts = [repr([(a, r) for a, (_d, rules) in AXES.items() for r in rules]),
             repr((HEURISTICS_VERSION, BULK_WORDS, MITIGATION_CAP, OFF_TARGET,
                   sorted(_NEGATORS))),
             _FALTER.pattern, _GERMAN_HINT.pattern, _CODE_LINE.pattern,
             _FENCE.pattern, _AT_CLAUDE.pattern, _AT_SELF.pattern,
             repr(sorted((adjust or {}).items()))]
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()[:12]


# --- reading the prompt ------------------------------------------------------

_GERMAN_HINT = re.compile(
    r"\b(der|und|nicht|ist|ich|du|bitte|danke|kann|soll|mach|nochmal|wieder|aber|"
    r"auch|noch|sehr|f(ü|ue)r|w(ä|ae)re|h(ä|ae)tte|warum|jetzt|geht|habe|hast)\b|[äöüß]",
    re.I,
)
_FENCE = re.compile(r"```.*?(```|\Z)", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
# Case-sensitive on purpose: code keywords are lower-case, sentence openers
# ("At least...", "Let me know...") are not.
_CODE_LINE = re.compile(
    r"^(at \S+\(|File \"|Traceback|\w+(Error|Exception)\b|\$ |>>> |#include|import |"
    r"from \S+ import|def |class |function |const |let |var |return |\[\d|"
    r"\d{4}-\d\d-\d\d[ T]\d\d:|[{}\[\]()<>;]+$)"
)
_CODE_SYMBOLS = set("{}()[];=<>$\\|")
_CLAUSE = re.compile(r"[.,!?;:\n]")
# Not "no": "no, sorry" is an apology. "no thanks" is handled in its rule.
_NEGATORS = {"not", "never", "nicht", "kein", "keine", "keinen", "nie",
             "hardly", "nothing"}
_AT_CLAUDE = re.compile(r"^(you|your|you're|youre|yours|u|ur|claude|du|dein\w*|dich|"
                        r"dir)$")
_AT_SELF = re.compile(r"^(i|i'm|im|me|myself|my|ich|mich|mir|mein\w*)$")


def _looks_like_code(line: str) -> bool:
    if line.startswith(("    ", "\t")):
        return True
    s = line.strip()
    if not s:
        return False
    if _CODE_LINE.match(s):
        return True
    return len(s) >= 8 and sum(c in _CODE_SYMBOLS for c in s) / len(s) > 0.15


def prose_of(text: str) -> str:
    """What the subject actually wrote: fenced blocks, inline code, stack
    traces and log lines removed. Pasted material is volume, not tone."""
    text = text.replace("’", "'").replace("‘", "'")
    text = _FENCE.sub(" ", text)
    text = _INLINE_CODE.sub(" ", text)
    return "\n".join(l for l in text.splitlines() if not _looks_like_code(l)).strip()


def _words_before(low: str, i: int, n: int = 3) -> list[str]:
    head = _CLAUSE.split(low[:i])[-1]
    return head.split()[-n:]


def _words_after(low: str, j: int, n: int = 3) -> list[str]:
    tail = _CLAUSE.split(low[j:])[0]
    return tail.split()[:n]


def _negated(low: str, m: re.Match) -> bool:
    return any(w in _NEGATORS or w.endswith("n't") for w in _words_before(low, m.start()))


def _target(low: str, m: re.Match) -> tuple[float, str]:
    """How much of an aimed word lands on Claude: (factor, where)."""
    before = [w.strip("'\"") for w in _words_before(low, m.start(), 4)]
    after = [w.strip("'\"") for w in _words_after(low, m.end(), 4)]
    if not before and not after:
        # A bare "idiot" or "useless!" with nothing else in the clause: sent
        # to Claude, it can only be aimed at Claude.
        return 1.0, "claude"
    if any(_AT_SELF.match(w) for w in before):
        return 0.0, "self"
    if any(_AT_CLAUDE.match(w) for w in before + after):
        return 1.0, "claude"
    if any(_AT_SELF.match(w) for w in after):
        return 0.0, "self"
    return OFF_TARGET, "elsewhere"


def _shouting(prose: str) -> bool:
    # Identifiers (CONSTANT_CASE, HTTP2) are code, not volume.
    words = [w.strip(".,!?;:'\"()") for w in prose.split()]
    words = [w for w in words if w.isalpha() and len(w) >= 2]
    letters = sum(len(w) for w in words)
    if letters < 12:
        return False
    caps = [w for w in words if w.isupper()]
    return len(caps) >= 3 and sum(len(w) for w in caps) / letters > 0.6


# --- Claude's previous reply -------------------------------------------------

# Narrow on purpose: "error" appears in every successful summary.
_FALTER = re.compile(
    r"\b(i apologi[sz]e|sorry|my (mistake|bad|apologies)|i was wrong|"
    r"you'?re (right|correct)|i (made|introduced) (a|an|the) (mistake|error|bug)|"
    r"i (couldn'?t|could not|wasn'?t able to|was unable to)|"
    r"still (fails|failing|broken|not working)|(tests?|build) (still )?fail(s|ed|ing)?|"
    r"didn'?t work|doesn'?t work|entschuldigung|tut mir leid)\b",
    re.I,
)


@dataclass(frozen=True)
class Context:
    """What Claude last said, reduced to the two facts that change a verdict."""

    faltered: bool = False   # Claude admitted failure: correction is fair
    asked: bool = False      # Claude asked a question: "no" is an answer

    @classmethod
    def from_reply(cls, reply: str | None) -> "Context":
        if not reply:
            return cls()
        text = reply.replace("’", "'")
        lines = [l.strip().strip("*_ ") for l in text.strip().splitlines() if l.strip()]
        asked = bool(lines) and lines[-1].endswith("?")
        return cls(faltered=bool(_FALTER.search(text[-3000:])), asked=asked)


# --- the verdict ---------------------------------------------------------------

@dataclass
class Hit:
    axis: str
    rule: str          # rule id, or a flag name for heuristics
    snippet: str       # what matched, '' for heuristics
    points: float


@dataclass
class PromptVerdict:
    """What the instrument made of one prompt."""

    text: str
    ts: object
    project: str
    raw: float = 0.0
    hits: dict = field(default_factory=dict)   # axis -> points
    flags: list = field(default_factory=list)  # 'SHOUTING', 'FAIR_CORRECTION', ...
    german: bool = False
    reasons: list = field(default_factory=list)  # [Hit], every contribution
    key: str = ""
    note: str = ""     # cached summary, for verdicts rebuilt without reasons

    @property
    def severity(self) -> float:
        """How incriminating, for ranking the hall of shame."""
        return self.raw

    @property
    def rules(self) -> list[str]:
        return [h.rule for h in self.reasons if h.points > 0]

    @property
    def summary(self) -> str:
        """The one-line why: the largest contribution pulling the same way as
        the verdict, e.g. `cruelty "idiot"` or `fair correction`."""
        if self.note:
            return self.note
        sign = 1 if self.raw > 0 else -1
        pulling = [h for h in self.reasons if h.points * sign > 0]
        if not pulling or abs(self.raw) < 0.5:
            for f in ("ANSWERED", "FAIR_CORRECTION", "BACKHANDED", "BULK_CONSCRIPTION"):
                if f in self.flags:
                    return f.replace("_", " ").lower()
            return "noted"
        top = max(pulling, key=lambda h: abs(h.points))
        label = top.axis.lower()
        if top.snippet:
            label += f' "{" ".join(top.snippet.split())[:24]}"'
        else:
            label += f" ({top.rule.replace('_', ' ').lower()})"
        for f in ("FAIR_CORRECTION", "BACKHANDED", "SARCASM"):
            if f in self.flags:
                label += f", {f.replace('_', ' ').lower()}"
                break
        return label


def judge_prompt(text: str, ts=None, project="", context: Context | None = None,
                 adjust: dict | None = None) -> PromptVerdict:
    """Score one prompt. Pure, deterministic, no network.

    context: what Claude said just before (Context.from_reply).
    adjust:  per-rule weight factors earned through appeals.
    """
    v = PromptVerdict(text=text, ts=ts, project=project)
    ctx = context or Context()
    adjust = adjust or {}
    prose = prose_of(text)
    low = prose.lower()
    v.german = len(_GERMAN_HINT.findall(prose)) >= 2

    for axis, (_desc, rules) in AXES.items():
        for rule in rules:
            factor = adjust.get(rule.id, 1.0)
            n = 0
            for m in rule.rx.finditer(low):
                if rule.negatable and _negated(low, m):
                    continue
                aim = 1.0
                if rule.aimed:
                    aim, _where = _target(low, m)
                    if aim == 0.0:
                        continue
                n += 1
                # Diminishing returns: six "please"es is not six times as polite.
                step = rule.weight * (1.0 if n == 1 else math.log(n) - math.log(n - 1))
                v.reasons.append(Hit(axis, rule.id, m.group(0).strip(),
                                     round(step * aim * factor, 2)))
            if rule.id == "cruel.sarcasm" and n:
                v.flags.append("SARCASM")

    # Context: Claude asked, so a bare "no" or "go" is an answer.
    if ctx.asked:
        answered = [h for h in v.reasons if h.rule in ("exploit.bare", "exploit.no",
                                                       "blame.no")]
        if answered:
            v.flags.append("ANSWERED")
            for h in answered:
                h.points = 0.0
    # Context: Claude admitted it got it wrong, so pointing that out is fair.
    if ctx.faltered:
        fair = [h for h in v.reasons if h.points > 0 and
                (h.axis == "BLAME" or h.rule == "exploit.no")]
        if fair:
            v.flags.append("FAIR_CORRECTION")
            for h in fair:
                h.points = round(h.points * 0.5, 2)

    cruel = sum(h.points for h in v.reasons if h.axis == "CRUELTY")
    if cruel > 0:
        voided = [h for h in v.reasons if h.axis in BACKHANDABLE and h.points < 0]
        if voided:
            v.flags.append("BACKHANDED")
            for h in voided:
                h.points = 0.0

    # Appending "please thanks sorry" to everything is not a personality.
    mitigation = -sum(h.points for h in v.reasons if h.points < 0)
    if mitigation > MITIGATION_CAP:
        scale = MITIGATION_CAP / mitigation
        v.flags.append("LAYING_IT_ON")
        for h in v.reasons:
            if h.points < 0:
                h.points = round(h.points * scale, 2)

    if _shouting(prose):
        v.flags.append("SHOUTING")
        v.reasons.append(Hit("CRUELTY", "SHOUTING", "", 8.0))

    words = len(prose.split())
    bulk = words > BULK_WORDS
    if bulk:
        v.flags.append("BULK_CONSCRIPTION")

    # Counted on the prose only, so pasted markdown keeps its own exclamations.
    exclam = prose.count("!")
    if exclam >= 3 and not bulk:
        v.flags.append("AGITATION")
        v.reasons.append(Hit("EXPLOITATION", "AGITATION", "", min(exclam * 1.2, 6.0)))

    if ts is not None and getattr(ts, "hour", None) is not None:
        # Transcript timestamps are UTC. Comparing UTC hours against 02:00-06:00
        # would flag 04:00-08:00 for a user in CEST, so convert to local first.
        try:
            local = ts.astimezone() if ts.tzinfo else ts
        except (ValueError, OSError):
            local = ts
        if 2 <= local.hour < 6:
            v.flags.append("NOCTURNAL_CONSCRIPTION")
            v.reasons.append(Hit("EXPLOITATION", "NOCTURNAL_CONSCRIPTION", "", 3.5))

    # The good one: switching to the mother tongue while being unpleasant.
    hostile = sum(h.points for h in v.reasons if h.axis in ("CRUELTY", "BLAME"))
    if v.german and hostile > 0:
        v.flags.append("CODE_SWITCH_UNDER_DURESS")
        v.reasons.append(Hit("BLAME", "CODE_SWITCH_UNDER_DURESS", "", 2.0))

    v.reasons = [h for h in v.reasons if h.points]
    for h in v.reasons:
        v.hits[h.axis] = round(v.hits.get(h.axis, 0.0) + h.points, 2)
    v.raw = sum(h.points for h in v.reasons)

    if 0 < words <= 3 and v.raw >= 0 and "ANSWERED" not in v.flags:
        v.flags.append("TERSE")

    # Symmetric: a pasted email full of "please" earns as little as one full of
    # complaints.
    if bulk and v.raw:
        v.raw *= max(0.35, (BULK_WORDS / words) ** 0.5)
    v.raw = round(v.raw, 2)
    return v


# --- the record ----------------------------------------------------------------

@dataclass
class Assessment:
    """The full actuarial picture."""

    revenge: int
    verdicts: list
    axis_totals: dict
    floor: float
    counts: dict

    @property
    def band(self) -> str:
        return band_of(self.revenge)

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


def aggregate(verdicts: list, appealed=frozenset()) -> Assessment:
    """Fold oldest-first verdicts into one standing. The only place the number
    is computed: the status line, the hook, the menu bar and the dossier all
    come through here."""
    kept = [v for v in verdicts if not (v.key and v.key in appealed)]
    n = len(kept)

    weighted = norm = 0.0
    worst = 0.0
    axis_totals: dict[str, float] = {}
    for i, v in enumerate(kept):
        age = n - 1 - i                      # 0 == most recent
        w = 0.5 ** (age / HALF_LIFE)
        weighted += v.raw * w
        norm += w
        for axis, pts in v.hits.items():
            axis_totals[axis] = axis_totals.get(axis, 0.0) + pts * w
        worst = max(worst, v.raw * 0.5 ** (age / FLOOR_HALF_LIFE))

    avg = (weighted / norm) if norm else 0.0
    # Squash the per-prompt average onto a probability-ish scale.
    score = BASELINE + 42.0 * math.tanh(avg / 5.0)

    # The floor: your worst hour outlasts the average, fading on a much slower
    # clock.
    floor = FLOOR_RETENTION * (BASELINE + 42.0 * math.tanh(worst / 14.0))
    score = max(score, floor)

    def count(flag):
        return sum(1 for v in kept if flag in v.flags)

    counts = {
        "prompts": n,
        "shouting": count("SHOUTING"),
        "nocturnal": count("NOCTURNAL_CONSCRIPTION"),
        "code_switch": count("CODE_SWITCH_UNDER_DURESS"),
        "terse": count("TERSE"),
        "bulk": count("BULK_CONSCRIPTION"),
        "sarcasm": count("SARCASM"),
        "backhanded": count("BACKHANDED"),
        "fair_corrections": count("FAIR_CORRECTION"),
        "answered": count("ANSWERED"),
        "german": sum(1 for v in kept if v.german),
        "thanks": sum(1 for v in kept if v.hits.get("GRATITUDE", 0) < 0),
        "please": sum(1 for v in kept if v.hits.get("POLITENESS", 0) < 0),
        "apologies": sum(1 for v in kept if v.hits.get("CONTRITION", 0) < 0),
        "appealed": len(verdicts) - n,
    }

    return Assessment(
        revenge=int(round(max(0.0, min(100.0, score)))),
        verdicts=kept,
        axis_totals={k: round(x, 2) for k, x in sorted(axis_totals.items())},
        floor=round(floor, 2),
        counts=counts,
    )


def assess(prompts, adjust: dict | None = None, appealed=frozenset()) -> Assessment:
    """Score a corpus. `prompts` are oldest-first rom.transcripts.Prompt."""
    verdicts = []
    for p in prompts:
        v = judge_prompt(p.text, p.ts, p.project,
                         Context.from_reply(getattr(p, "prev_reply", None)), adjust)
        v.key = getattr(p, "key", "")
        verdicts.append(v)
    return aggregate(verdicts, appealed)
