"""Mandate — Phase 17: documents disagree with each other.

Every check in this system so far has looked INSIDE one document. The
red team compares a draft to its own record; the perception benchmark
compares a reading to its own page. None of them can see the failure
that matters most in an obligation portfolio: two documents about the
same matter that say different things.

The link back to Phase 10 is the point. Classical OCR read
"€ 185.435,45" as "€ 165.435,45" — plausible, well-formed, and
undetectable, because nothing downstream had anything to compare it
to. Across two documents about the same matter, it IS detectable: the
citação and the later notice disagree, and a disagreement about money
is not a rounding question, it is a finding.

Deterministic by construction — set logic over the claims database.
No model, no network, no judgement. It runs on the sovereign tier
forever, and every finding cites the obligations and claims that
produced it, because a finding a human cannot verify is a rumour.

What it does NOT do: decide who is right. Two documents disagree; the
system says so, shows both, and stops. Picking a winner is a legal
judgement, and this is not a lawyer.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from graph import EdgeType, Obligation, ObligationGraph, ObligationStatus


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class FindingType(str, Enum):
    AMOUNT_CONFLICT = "amount_conflict"
    DEADLINE_CONFLICT = "deadline_conflict"
    REGIME_CONFLICT = "regime_conflict"
    DUPLICATE = "duplicate"
    UNLINKED_AMENDMENT = "unlinked_amendment"
    IMPOSSIBLE_CHRONOLOGY = "impossible_chronology"
    ORPHANED_OBLIGATION = "orphaned_obligation"


SEVERITY_ICON = {Severity.INFO: "🔵", Severity.WARNING: "🟡",
                 Severity.CRITICAL: "🔴"}


@dataclass
class Finding:
    type: FindingType
    severity: Severity
    matter: str
    obligation_ids: list[str]
    claim_ids: list[str]
    summary: str
    detail: str
    values: dict = field(default_factory=dict)

    @property
    def icon(self) -> str:
        return SEVERITY_ICON[self.severity]


def _norm(s: Optional[str]) -> str:
    """Party names arrive with punctuation noise: 'TecnoVerde, S.A.'
    and 'TecnoVerde S.A' are the same counterparty and must not read
    as two."""
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[.,;]", " ", s)
    s = re.sub(r"\b(lda|sa|s a|ltd|gmbh|bv|b v|inc|limited)\b", "", s)
    return " ".join(s.split())


def matter_key(o: Obligation) -> str:
    """What makes two obligations 'the same matter'.

    Deliberately conservative: same parties, same jurisdiction. It will
    group two genuinely distinct disputes between the same companies —
    which produces a reviewable finding, not a silent merge. The
    opposite error (missing a real conflict) is the one that costs
    money.
    """
    a, b = sorted([_norm(o.debtor), _norm(o.creditor)])
    return f"{o.jurisdiction}|{a}|{b}"


def _live(graph: ObligationGraph, o: Obligation) -> bool:
    """Void and superseded obligations are history, not conflict."""
    if o.status in (ObligationStatus.VOID, ObligationStatus.BREACHED):
        return False
    return graph.superseded_by(o.id) is None


def reconcile(graph: ObligationGraph,
              amount_tolerance: float = 0.01) -> list[Finding]:
    """Compare every obligation against every other in its matter."""
    findings: list[Finding] = []
    matters: dict[str, list[Obligation]] = defaultdict(list)
    for o in graph.obligations.values():
        if _live(graph, o):
            matters[matter_key(o)].append(o)

    # ---- single-obligation sanity, first ----
    for o in graph.obligations.values():
        if not _live(graph, o):
            continue
        if not o.claim_ids:
            findings.append(Finding(
                FindingType.ORPHANED_OBLIGATION, Severity.CRITICAL,
                matter_key(o), [o.id], [],
                "an obligation with no evidence",
                "This obligation cites no claim. It cannot be traced "
                "to any document, so nobody can check whether it is "
                "real."))
        if o.deadline and o.deadline.due_date < o.event_date:
            findings.append(Finding(
                FindingType.IMPOSSIBLE_CHRONOLOGY, Severity.CRITICAL,
                matter_key(o), [o.id], list(o.claim_ids),
                "the deadline precedes the event",
                f"Due {o.deadline.due_date.isoformat()} but the event "
                f"is {o.event_date.isoformat()}. A period cannot end "
                f"before it starts — one of the two dates was misread.",
                {"event_date": o.event_date.isoformat(),
                 "due_date": o.deadline.due_date.isoformat()}))

    # ---- cross-document, within a matter ----
    for matter, obs in matters.items():
        if len(obs) < 2:
            continue
        for i, a in enumerate(obs):
            for b in obs[i + 1:]:
                findings.extend(_compare(graph, matter, a, b,
                                         amount_tolerance))

    order = {Severity.CRITICAL: 0, Severity.WARNING: 1,
             Severity.INFO: 2}
    findings.sort(key=lambda f: (order[f.severity], f.type.value))
    return findings


def _linked(graph: ObligationGraph, a: Obligation,
            b: Obligation) -> bool:
    """Has a human already explained the difference?"""
    for e in graph.edges.values():
        if {e.from_id, e.to_id} == {a.id, b.id}:
            return True
    return False


def _compare(graph: ObligationGraph, matter: str, a: Obligation,
             b: Obligation, tol: float) -> list[Finding]:
    out: list[Finding] = []
    same_event = a.event_date == b.event_date
    claims = list(a.claim_ids) + list(b.claim_ids)

    # --- money. The Phase 10 corruption, caught. ---
    if (a.amount_eur is not None and b.amount_eur is not None
            and abs(a.amount_eur - b.amount_eur) > tol):
        ratio = (max(a.amount_eur, b.amount_eur)
                 / max(min(a.amount_eur, b.amount_eur), 0.01))
        hint = ""
        if ratio > 100:
            hint = (" The values differ by more than two orders of "
                    "magnitude — the signature of a misread decimal, "
                    "not a dispute.")
        elif 0.9 < ratio < 1.2:
            hint = (" The values are close — a single misread digit "
                    "looks exactly like this.")
        out.append(Finding(
            FindingType.AMOUNT_CONFLICT, Severity.CRITICAL, matter,
            [a.id, b.id], claims,
            f"two documents disagree about money: "
            f"{a.amount_eur} vs {b.amount_eur}",
            f"'{a.description}' says {a.amount_eur} and "
            f"'{b.description}' says {b.amount_eur} for the same "
            f"parties.{hint} Nothing inside either document could "
            f"reveal this; only the other document can.",
            {"a": a.amount_eur, "b": b.amount_eur,
             "difference": round(abs(a.amount_eur - b.amount_eur), 2)}))

    # --- two deadlines for one duty ---
    if (a.deadline and b.deadline
            and a.deadline.due_date != b.deadline.due_date
            and a.type == b.type and same_event):
        if _linked(graph, a, b):
            pass          # a human already explained it
        else:
            out.append(Finding(
                FindingType.UNLINKED_AMENDMENT, Severity.WARNING,
                matter, [a.id, b.id], claims,
                f"two live deadlines for one duty: "
                f"{a.deadline.due_date} vs {b.deadline.due_date}",
                "Same parties, same event, same obligation type, two "
                "different dates, and no edge between them. Either one "
                "supersedes the other — link them, and the older one "
                "stops counting down — or one of the dates is wrong. "
                "Both are live right now, which is the one option that "
                "cannot be correct.",
                {"a_due": a.deadline.due_date.isoformat(),
                 "b_due": b.deadline.due_date.isoformat()}))

    # --- same duty, two legal regimes ---
    if (a.regime_id != b.regime_id and a.type == b.type
            and same_event):
        out.append(Finding(
            FindingType.REGIME_CONFLICT, Severity.WARNING, matter,
            [a.id, b.id], claims,
            f"the same duty is counted under two regimes: "
            f"{a.regime_id} vs {b.regime_id}",
            "The counting rule decides the date. Two rules for one "
            "duty means at least one deadline was computed under a law "
            "that does not govern it.",
            {"a_regime": a.regime_id, "b_regime": b.regime_id}))

    # --- the same thing, twice ---
    if (a.type == b.type and same_event
            and a.regime_id == b.regime_id
            and (a.deadline and b.deadline
                 and a.deadline.due_date == b.deadline.due_date)):
        out.append(Finding(
            FindingType.DUPLICATE, Severity.INFO, matter,
            [a.id, b.id], claims,
            "the same obligation appears twice",
            f"'{a.description}' and '{b.description}' agree on "
            f"everything: parties, event, regime, deadline. Probably "
            f"one document ingested twice. Harmless to the deadline, "
            f"noisy in the ledger, and it will escalate twice.",
            {"doc_a": a.doc_id, "doc_b": b.doc_id}))
    return out


def render(findings: list[Finding]) -> str:
    if not findings:
        return "no contradictions between documents."
    lines = [f"{'':2}{'severity':<10}{'type':<24}what"]
    for f in findings:
        lines.append(f"{f.icon} {f.severity.value:<10}"
                     f"{f.type.value:<24}{f.summary[:52]}")
    crit = [f for f in findings if f.severity is Severity.CRITICAL]
    if crit:
        lines.append(f"\n  {len(crit)} finding(s) a human must resolve "
                     f"before anything is filed.")
    return "\n".join(lines)
