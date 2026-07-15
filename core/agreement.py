"""Mandate — Phase 9: inter-rater agreement (Cohen's kappa).

An LLM judge nobody validated is an opinion with a number attached.
This module measures whether the judge agrees with a careful human
BEYOND CHANCE — the only thing that makes its verdicts worth acting on.

    kappa = (Po - Pe) / (1 - Pe)
      Po = observed agreement
      Pe = agreement expected from the raters' marginal rates alone

Interpretation is deliberately not reduced to a verdict. A low kappa
can mean the judge is broken, or that the task is genuinely ambiguous.
(In a sibling project the judge scored kappa 0.237 while agreeing with
the human on every clear failure and splitting only on borderline
cases — that is a finding, not a defect.) The confusion matrix is
printed so a reader can tell which is which.
"""

from __future__ import annotations

from collections import Counter


def cohens_kappa(a: list[str], b: list[str]) -> float:
    """Chance-corrected agreement between two raters."""
    if len(a) != len(b):
        raise ValueError("raters must label the same items")
    if not a:
        return 0.0
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in set(a) | set(b))
    if pe >= 1.0:
        return 1.0 if po == 1.0 else 0.0
    return round((po - pe) / (1 - pe), 4)


def raw_agreement(a: list[str], b: list[str]) -> float:
    if not a:
        return 0.0
    return round(sum(1 for x, y in zip(a, b) if x == y) / len(a), 4)


def confusion(a: list[str], b: list[str],
              labels: list[str] | None = None) -> dict:
    """Nested dict: rows = rater A (human), cols = rater B (judge)."""
    labels = labels or sorted(set(a) | set(b))
    m = {ra: {rb: 0 for rb in labels} for ra in labels}
    for x, y in zip(a, b):
        m[x][y] += 1
    return m


def render_confusion(a: list[str], b: list[str],
                     labels: list[str] | None = None,
                     a_name: str = "human",
                     b_name: str = "judge") -> str:
    """A readable matrix — where the disagreement lives is the point."""
    labels = labels or sorted(set(a) | set(b))
    m = confusion(a, b, labels)
    w = max([len(x) for x in labels] + [12]) + 2
    lines = [f"{'':<{w}}" + "".join(f"{l:>{w}}" for l in labels)
             + f"{'(' + b_name + ' →)':>{w}}"]
    for ra in labels:
        lines.append(f"{ra:<{w}}"
                     + "".join(f"{m[ra][rb]:>{w}}" for rb in labels))
    lines.append(f"({a_name} ↓)")
    return "\n".join(lines)


def agreement_report(human: list[str], judge: list[str],
                     labels: list[str] | None = None) -> dict:
    """Everything needed to judge the judge."""
    k = cohens_kappa(human, judge)
    return {
        "n": len(human),
        "cohens_kappa": k,
        "raw_agreement": raw_agreement(human, judge),
        "confusion": confusion(human, judge, labels),
        "human_marginals": dict(Counter(human)),
        "judge_marginals": dict(Counter(judge)),
        "strictness": _strictness(human, judge, labels),
        "label_coverage": _label_coverage(human, judge, labels),
    }


def _label_coverage(human: list[str], judge: list[str],
                    labels: list[str] | None = None) -> dict:
    """Does the judge ever use the whole label space?

    A rater that never reaches for the harshest verdict cannot be a
    gate, no matter how good its kappa looks: kappa rewards agreement
    on the easy majority. This diagnostic exists because a judge with
    kappa 0.62 was found to have caught 0 of 4 clearly-broken drafts —
    it had simply never used UNGROUNDED at all.
    """
    space = set(labels or (set(human) | set(judge)))
    used_h, used_j = set(human), set(judge)
    unused = sorted(space - used_j)
    return {
        "labels": sorted(space),
        "judge_used": sorted(used_j),
        "human_used": sorted(used_h),
        "judge_never_used": unused,
        "collapsed": bool(unused),
        "reading": (f"JUDGE NEVER USES {unused} — it cannot flag what "
                    f"it has no category for; kappa overstates its "
                    f"usefulness as a gate"
                    if unused else
                    "judge uses the full label space"),
    }


_ORDER = ["UNGROUNDED", "PARTIALLY_GROUNDED", "GROUNDED"]


def _strictness(human: list[str], judge: list[str],
                labels: list[str] | None = None) -> dict:
    """Is the judge systematically harsher or softer than the human?

    Systematic bias is a different problem from random noise, and the
    fix differs: bias can be corrected, noise cannot.
    """
    order = [l for l in _ORDER if l in set(human) | set(judge)] or \
        sorted(set(human) | set(judge))
    idx = {l: i for i, l in enumerate(order)}
    diffs = [idx[j] - idx[h] for h, j in zip(human, judge)
             if h in idx and j in idx]
    if not diffs:
        return {"mean_shift": 0.0, "reading": "n/a"}
    mean = sum(diffs) / len(diffs)
    if mean < -0.15:
        reading = "judge is STRICTER than the human"
    elif mean > 0.15:
        reading = "judge is more LENIENT than the human"
    else:
        reading = "no systematic strictness bias"
    return {"mean_shift": round(mean, 3), "reading": reading,
            "stricter_n": sum(1 for d in diffs if d < 0),
            "lenient_n": sum(1 for d in diffs if d > 0),
            "same_n": sum(1 for d in diffs if d == 0)}
