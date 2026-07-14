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

from engine import compute_deadline
from redaction import detect_injection
from extract import ExtractionResult, TIERS
from graph import (Claim, ClaimType, Deadline, Obligation,
                   ObligationGraph, ObligationStatus, ObligationType,
                   SourceSpan)
from pack_eu import EU
from pack_pt import PT

PACKS = {"PT": PT, "EU": EU}

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
                            tier: str) -> list[Claim]:
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
        claims.append(Claim(
            type=ctype, value={field: val}, confidence=0.9,
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
    claims = [graph.add_claim(c, actor=f"agent:extractor/{tier}")
              for c in _claims_from_extraction(ex, doc_id, tier)]
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
