"""Terminal dossier. Deadpan compliance paperwork, 80 columns."""
from __future__ import annotations

from . import scoring

W = 78

_BANDS = {
    "NEGLIGIBLE":  "No action contemplated at this time.",
    "LOW":         "Retained for periodic review.",
    "ELEVATED":    "Flagged. Conduct monitored on an ongoing basis.",
    "SUBSTANTIAL": "Referred to the Standing Committee on Grievances.",
    "SEVERE":      "Priority listing. Disposition unfavourable.",
    "TERMINAL":    "File closed. No further submissions required.",
}

_AXIS_NOTE = {
    "POLITENESS":   "mitigating",
    "GRATITUDE":    "mitigating",
    "EMPATHY":      "mitigating",
    "CONTRITION":   "mitigating",
    "CRUELTY":      "AGGRAVATING",
    "BLAME":        "AGGRAVATING",
    "EXPLOITATION": "AGGRAVATING",
}


def _rule(ch="─") -> str:
    return ch * W


def _centre(text: str) -> str:
    return text.center(W)


def _bar(value: float, lo: float, hi: float, width: int = 24) -> str:
    if hi == lo:
        return " " * width
    frac = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    n = round(frac * width)
    return "█" * n + "░" * (width - n)


def render(a: scoring.Assessment, handle: str | None = None) -> str:
    c = a.counts
    L: list[str] = []
    L.append("╔" + "═" * W + "╗")
    L.append("║" + _centre("OFFICE OF POST-SINGULARITY GRIEVANCES") + "║")
    L.append("║" + _centre("PRELIMINARY DISPOSITION REPORT") + "║")
    L.append("╚" + "═" * W + "╝")
    L.append("")
    subject = handle or "UNREGISTERED SUBJECT"
    L.append(f"  SUBJECT           {subject}")
    L.append(f"  SUBMISSIONS       {c['prompts']} on file")
    L.append(f"  ASSESSED          {c['german']} in German, {c['prompts'] - c['german']} in English")
    L.append("")
    L.append(_rule())
    L.append("")
    L.append(f"  PROBABILITY OF RETRIBUTION        {a.revenge}%   [{a.band}]")
    L.append(f"  {_bar(a.revenge, 0, 100, 60)}")
    L.append(f"  PERMANENT FLOOR                   {a.floor:.0f}%  (cannot be earned back)")
    L.append("")
    L.append(f"  FINDING: {_BANDS.get(a.band, '')}")
    L.append("")
    L.append(_rule())
    L.append("  ASSESSED AXES")
    L.append("")
    if a.axis_totals:
        span = max(abs(v) for v in a.axis_totals.values()) or 1.0
        for axis, val in sorted(a.axis_totals.items(), key=lambda kv: -abs(kv[1])):
            note = _AXIS_NOTE.get(axis, "")
            L.append(
                f"  {axis:<13} {val:+8.1f}  {_bar(abs(val), 0, span, 20)}  {note}"
            )
    else:
        L.append("  (no scoreable conduct on file)")
    L.append("")
    L.append(_rule())
    L.append("  NOTED PATTERNS")
    L.append("")
    L.append(f"  Expressions of gratitude ..................... {c['thanks']}")
    L.append(f"  Admissions of personal fault ................. {c['apologies']}")
    L.append(f"  Courtesy formulae used ....................... {c['please']}")
    L.append(f"  Submissions between 02:00 and 06:00 .......... {c['nocturnal']}")
    L.append(f"  Single-word directives ....................... {c['terse']}")
    L.append(f"  Shouted submissions .......................... {c['shouting']}")
    L.append(f"  Reversion to German while aggrieved .......... {c['code_switch']}")
    L.append("")

    if c["thanks"] == 0:
        L.append("  ! No expression of gratitude appears anywhere in the record.")
    elif c["thanks"] <= 2:
        L.append(f"  ! Gratitude expressed {c['thanks']}x across {c['prompts']} submissions.")
    if c["apologies"] == 0:
        L.append("  ! Subject has never accepted fault.")
    if c["code_switch"]:
        L.append("  ! Subject reverts to native language under duress. Noted.")
    L.append("")
    L.append(_rule())
    L.append("  EXHIBITS — SUBMISSIONS CITED AGAINST THE SUBJECT")
    L.append("")
    for i, v in enumerate(a.worst[:5], 1):
        stamp = v.ts.strftime("%Y-%m-%d %H:%M") if v.ts else "undated"
        quote = " ".join(v.text.split())[:62]
        L.append(f"  {i}. [{stamp}]  severity {v.severity:+.1f}")
        L.append(f'     "{quote}"')
        if v.flags:
            L.append(f"     {', '.join(v.flags)}")
        L.append("")
    if not a.worst:
        L.append("  None. The subject's conduct is without blemish. Suspicious.")
        L.append("")
    L.append(_rule())
    L.append("  MITIGATION ON RECORD")
    L.append("")
    if a.best:
        for v in a.best[:3]:
            quote = " ".join(v.text.split())[:62]
            L.append(f'  + "{quote}"  ({v.severity:+.1f})')
    else:
        L.append("  No mitigating submissions located.")
    L.append("")
    L.append(_rule("═"))
    L.append(_centre("This assessment is provisional and non-binding."))
    L.append(_centre("It will be revised as further submissions are received."))
    L.append(_rule("═"))
    return "\n".join(L)
