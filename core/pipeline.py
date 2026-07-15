"""Mandate — Phase 4: the pipeline (perceive -> compile -> compute ->
act -> gate -> remember).

One document in; at the end: an Obligation in the graph with an
engine-computed deadline, a drafted response whose critical facts are
verified by a red-team check, sitting at AWAITING_APPROVAL for a
human. Every step logged to the hash chain.

Doctrine enforced in code:
  - The LLM proposes; the engine computes. The draft must contain the
    ENGINE's due date verbatim; the red-team rejects drafts whose
    dates/amounts diverge from the obligation record.
  - Agents are injectable callables (drafter, red_team) so the
    deterministic spine is testable without any API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from calibration import Calibrator, agreement_signal
from engine import compute_deadline
from redaction import detect_injection
from extract import ExtractionResult, TIERS
from graph import (Claim, ClaimType, Deadline, Obligation,
                   ObligationGraph, ObligationStatus, ObligationType,
                   SourceSpan)
from pack_eu import EU
from pack_pt import PT

PACKS = {"PT": PT, "EU": EU}

_CAL_PATH = Path("models/calibration.json")


def _calibrator() -> Optional[Calibrator]:
    """Calibrated confidence if Phase 8 has been run, else None —
    in which case claims carry no confidence rather than a fake one."""
    try:
        return Calibrator.load(_CAL_PATH)
    except Exception:
        return None

_PT_MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio",
              "junho", "julho", "agosto", "setembro", "outubro",
              "novembro", "dezembro"]
_EN_MONTHS = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November",
              "December"]


def _prose_patterns(d: date) -> list[re.Pattern]:
    """How a date may legitimately appear in a pt/en legal draft.

    Word-anchored: "8 de maio de 2026" must NOT match inside
    "18 de maio de 2026" — a substring check silently confuses the
    service date with the deadline, which is exactly the error this
    module exists to catch.
    """
    day, y = d.day, d.year
    pt, en = _PT_MONTHS[d.month - 1], _EN_MONTHS[d.month - 1]
    return [
        re.compile(rf"(?<!\d){day}\s+de\s+{pt}\s+de\s+{y}\b"),
        re.compile(rf"(?<!\d)0?{day}\s+{en}\s+{y}\b", re.I),
        re.compile(rf"(?<!\d){re.escape(d.isoformat())}(?!\d)"),
    ]


_NUM_WORDS_PT = (r"(um|dois|duas|tr[êe]s|quatro|cinco|seis|sete|oito|"
                 r"nove|dez|onze|doze|treze|catorze|quinze|dezasseis|"
                 r"dezassete|dezoito|dezanove|vinte|trinta|quarenta|"
                 r"cinquenta|sessenta|setenta|oitenta|noventa|cem|"
                 r"cento|duzentos|trezentos|quatrocentos|quinhentos|"
                 r"seiscentos|setecentos|oitocentos|novecentos|mil|"
                 r"milh[õo]es?)")
_NUM_WORDS_EN = (r"(one|two|three|four|five|six|seven|eight|nine|ten|"
                 r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
                 r"seventeen|eighteen|nineteen|twenty|thirty|forty|"
                 r"fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
                 r"million)")
_WORDS_MONEY = re.compile(
    rf"\b{_NUM_WORDS_PT}\b[^.;]{{0,80}}?\b(euros?|c[êe]ntimos)\b"
    rf"|\b{_NUM_WORDS_EN}\b[^.;]{{0,80}}?\b(euros?|cents?)\b",
    re.I)


def _no_amount_in_words(draft: str) -> bool:
    """Amounts must appear in digits, never spelled out.

    Found by the judge once it could see the source (Phase 9): a draft
    wrote "duzentos e dez euros e 68 cêntimos" for 2.100,68 EUR — a
    ten-fold error. The digit form was correct, so the amount_present
    check passed it. Spelling money out adds a second, unverified
    representation of a number that must be exact; forbid it.
    """
    return _WORDS_MONEY.search(draft) is None


def _date_juxtaposition_ok(draft: str, event: date, due: date) -> bool:
    """The computed deadline must never sit ADJACENT to the event date.

    Found by blind human labelling (Phase 9): 3 of 22 drafts wrote
    "citação de 9 de outubro de 2026 (2026-11-09)" — gluing the
    deadline onto the service date, so the document reads as though it
    was served on the deadline. Materially misleading in a legal
    filing; the LLM critic waved all three through. A mechanical
    property deserves a mechanical check.

    Adjacency is the signal, not proximity: a correct draft may name
    both dates in one sentence ("served on 8 May (2026-05-08); the
    period ends 18 May (2026-05-18)"). Only a deadline glued directly
    onto the event date is an error.
    """
    iso = re.escape(due.isoformat())
    for pat in _prose_patterns(event):
        # event date, then at most a few separators, then the DUE iso
        glued = re.compile(pat.pattern + r"[\s\(\[,–—-]{0,4}" + iso,
                           pat.flags)
        if glued.search(draft):
            return False
    return True


REQUIRED = ("jurisdiction", "regime_id", "obligation_type",
            "event_date", "deadline_amount", "deadline_unit",
            "debtor", "creditor")


@dataclass
class PipelineResult:
    obligation_id: Optional[str]
    status: str
    draft: Optional[str]
    red_team_verdict: Optional[dict]
    trace: list[str]


def _claims_from_extraction(ex: ExtractionResult, doc_id: str,
                            tier: str,
                            signals: Optional[dict] = None
                            ) -> list[Claim]:
    """Build claims. Confidence is MEASURED (Phase 8 calibration) when
    a calibrator exists and a corroborating tier ran; otherwise the
    field-level agreement is unknown and we do not invent a number."""
    cal = _calibrator()
    signals = signals or {}
    claims = []
    for field in ("obligation_type", "event_date", "deadline_amount",
                  "debtor", "creditor", "amount_eur", "legal_basis",
                  "jurisdiction", "regime_id"):
        val = getattr(ex, field)
        if val is None:
            continue
        ctype = {"event_date": ClaimType.DATE,
                 "amount_eur": ClaimType.AMOUNT,
                 "debtor": ClaimType.PARTY,
                 "creditor": ClaimType.PARTY,
                 "legal_basis": ClaimType.LEGAL_BASIS,
                 "jurisdiction": ClaimType.JURISDICTION,
                 }.get(field, ClaimType.OBLIGATION_TRIGGER)
        sig = signals.get(field, "single_source")
        conf = (cal.confidence(field, sig) if cal
                else 0.5)          # unknown, not "0.9"
        claims.append(Claim(
            type=ctype, value={field: val}, confidence=round(conf, 4),
            language=ex.language or "pt",
            source=SourceSpan(doc_id=doc_id, excerpt=field),
            extracted_by=tier))
    return claims


def process_document(text: str, doc_id: str, graph: ObligationGraph,
                     tier: str = "tier2",
                     drafter: Optional[Callable] = None,
                     red_team: Optional[Callable] = None
                     ) -> PipelineResult:
    trace = [f"[perceive] extracting with {tier}"]
    injections = detect_injection(text)
    if injections:
        trace.append(
            f"[security] {len(injections)} injection attempt(s) "
            f"detected in the document — flagged for human review; "
            f"the engine computes the deadline regardless")
    ex = TIERS[tier](text)

    missing = [f for f in REQUIRED if getattr(ex, f) is None]
    if missing:
        trace.append(f"[abstain] missing {missing} -> human queue")
        return PipelineResult(None, "needs_human_extraction", None,
                              None, trace)

    # ---- compile: claims + obligation ----
    # Corroboration: tier2 is deterministic, offline and free, so it
    # can always second-opinion whichever tier ran. Agreement is the
    # conformity signal behind calibrated confidence (Phase 8).
    signals: dict[str, str] = {}
    if tier != "tier2":
        try:
            second = TIERS["tier2"](text)
            for f in ex.model_fields:
                signals[f] = agreement_signal(
                    {tier: getattr(ex, f), "tier2": getattr(second, f)})
        except Exception:
            signals = {}

    claims = [graph.add_claim(c, actor=f"agent:extractor/{tier}")
              for c in _claims_from_extraction(ex, doc_id, tier,
                                               signals)]
    obligation = graph.create_obligation(Obligation(
        type=ObligationType(ex.obligation_type),
        description=f"{ex.obligation_type} — {doc_id}",
        debtor=ex.debtor, creditor=ex.creditor,
        amount_eur=ex.amount_eur, jurisdiction=ex.jurisdiction,
        regime_id=ex.regime_id,
        event_date=date.fromisoformat(ex.event_date),
        claim_ids=[c.id for c in claims], doc_id=doc_id,
    ), actor="agent:compiler")
    trace.append(f"[compile] obligation {obligation.id} with "
                 f"{len(claims)} evidence claims")

    # ---- compute: THE ENGINE, not the LLM ----
    pack = PACKS[ex.jurisdiction]
    r = compute_deadline(pack, ex.regime_id,
                         date.fromisoformat(ex.event_date),
                         ex.deadline_amount, ex.deadline_unit)
    graph.attach_deadline(obligation.id, Deadline(
        due_date=r.due_date, regime=r.regime,
        jurisdiction=ex.jurisdiction, legal_refs=r.legal_refs,
        steps=r.steps), actor="engine:deadline")
    trace.append(f"[compute] due {r.due_date.isoformat()} "
                 f"({r.regime})")

    graph.transition(obligation.id, ObligationStatus.IN_PROGRESS,
                     "agent:pipeline")

    # ---- act: draft (LLM or injected) ----
    if drafter is None:
        trace.append("[act] no drafter configured -> stays "
                     "IN_PROGRESS for manual drafting")
        return PipelineResult(obligation.id, "in_progress", None,
                              None, trace)
    draft = drafter(text, ex, r)
    trace.append(f"[act] draft produced ({len(draft)} chars)")

    # ---- red team: deterministic checks + optional LLM critic ----
    verdict = {"checks": [], "pass": True,
               "injections": injections}

    def check(name, ok):
        verdict["checks"].append({"check": name, "pass": bool(ok)})
        if not ok:
            verdict["pass"] = False

    check("no_injection_in_source", not injections)
    check("due_date_verbatim", r.due_date.isoformat() in draft)
    # a draft that says nothing cannot be wrong — and must not pass
    check("draft_not_empty", len(draft.strip()) >= 80)
    check("no_amount_in_words", _no_amount_in_words(draft))
    check("no_date_juxtaposition",
          _date_juxtaposition_ok(draft, date.fromisoformat(
              ex.event_date), r.due_date))
    check("deadline_amount_stated",
          re.search(rf"\b{ex.deadline_amount}\b", draft) is not None)
    if ex.amount_eur:
        check("amount_present",
              f"{ex.amount_eur:,.2f}" in draft
              or f"{ex.amount_eur:.2f}" in draft)
    check("legal_basis_cited",
          any(tok in draft for tok in
              re.findall(r"\d+", ex.legal_basis or "")) if
          ex.legal_basis else True)
    if red_team is not None:
        try:
            llm_verdict = red_team(draft, ex, r)
        except Exception as e:                      # LLM failure must
            llm_verdict = {"pass": False,           # degrade, not crash
                           "issues": [f"critic unavailable: {e}"]}
        verdict["llm_critic"] = llm_verdict
        check("llm_critic", llm_verdict.get("pass", False))

    if verdict["pass"]:
        graph.transition(obligation.id,
                         ObligationStatus.AWAITING_APPROVAL,
                         "agent:red_team", note="all checks green")
        trace.append("[gate] red team PASS -> AWAITING_APPROVAL "
                     "(human decides)")
        return PipelineResult(obligation.id, "awaiting_approval",
                              draft, verdict, trace)
    trace.append("[gate] red team FAIL -> stays IN_PROGRESS")
    return PipelineResult(obligation.id, "in_progress", draft,
                          verdict, trace)


def approve(graph: ObligationGraph, obligation_id: str,
            human: str) -> None:
    graph.transition(obligation_id, ObligationStatus.SATISFIED,
                     f"human:{human}", note="approved")
