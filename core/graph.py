"""Mandate — the Obligation Graph (deterministic core).

Typed claims -> obligations -> state transitions, with an append-only,
hash-chained event log. This module is the system's spine: agents and
humans PROPOSE mutations; the graph ENFORCES the state machine and
records everything immutably.

Design rules:
  - Every fact is a Claim with a SourceSpan (doc, page, excerpt) and a
    calibrated confidence — no orphan facts.
  - Obligations reference the claims that evidence them.
  - State transitions are whitelisted; illegal moves raise.
  - The event log is append-only JSONL; each event carries
    prev_hash + hash (SHA-256), so tampering is detectable with
    verify_chain().
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from security import Action, Principal, authorize


# ---------------------------------------------------------------- claims
class SourceSpan(BaseModel):
    doc_id: str
    page: Optional[int] = None
    excerpt: str = ""


class ClaimType(str, Enum):
    PARTY = "party"
    AMOUNT = "amount"
    DATE = "date"
    LEGAL_BASIS = "legal_basis"
    OBLIGATION_TRIGGER = "obligation_trigger"
    JURISDICTION = "jurisdiction"
    OTHER = "other"


class Claim(BaseModel):
    id: str = Field(default_factory=lambda: f"clm_{uuid4().hex[:10]}")
    type: ClaimType
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    language: str = "pt"
    source: SourceSpan
    extracted_by: str = "tier0"  # tier0/tier1/tier2/human


# ------------------------------------------------------------ obligations
class ObligationType(str, Enum):
    RESPOND = "respond"
    PAY = "pay"
    RENEW = "renew"
    NOTIFY = "notify"
    FILE = "file"
    OTHER = "other"


class ObligationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    SATISFIED = "satisfied"
    ESCALATED = "escalated"
    BREACHED = "breached"
    VOID = "void"


ALLOWED_TRANSITIONS: dict[ObligationStatus, set[ObligationStatus]] = {
    ObligationStatus.PENDING: {ObligationStatus.IN_PROGRESS,
                               ObligationStatus.ESCALATED,
                               ObligationStatus.VOID},
    ObligationStatus.IN_PROGRESS: {ObligationStatus.AWAITING_APPROVAL,
                                   ObligationStatus.ESCALATED,
                                   ObligationStatus.VOID},
    ObligationStatus.AWAITING_APPROVAL: {ObligationStatus.SATISFIED,
                                         ObligationStatus.IN_PROGRESS,
                                         ObligationStatus.ESCALATED},
    ObligationStatus.ESCALATED: {ObligationStatus.IN_PROGRESS,
                                 ObligationStatus.BREACHED,
                                 ObligationStatus.VOID},
    ObligationStatus.SATISFIED: set(),
    ObligationStatus.BREACHED: set(),
    ObligationStatus.VOID: set(),
}


class Deadline(BaseModel):
    due_date: date
    regime: str
    jurisdiction: str
    legal_refs: list[str]
    steps: list[str]


class Obligation(BaseModel):
    id: str = Field(default_factory=lambda: f"obl_{uuid4().hex[:10]}")
    type: ObligationType
    description: str
    debtor: str
    creditor: str
    amount_eur: Optional[float] = None
    jurisdiction: str
    regime_id: str
    event_date: date
    deadline: Optional[Deadline] = None
    status: ObligationStatus = ObligationStatus.PENDING
    claim_ids: list[str] = Field(default_factory=list)
    doc_id: str = ""


class IllegalTransition(Exception):
    pass


# ---------------------------------------------------------------- store
class ObligationGraph:
    """In-memory graph with an append-only, hash-chained JSONL log."""

    def __init__(self, log_path: str | Path = "obligation_log.jsonl"):
        self.log_path = Path(log_path)
        self.claims: dict[str, Claim] = {}
        self.obligations: dict[str, Obligation] = {}
        self._last_hash = "GENESIS"
        if self.log_path.exists():
            self._replay()

    # ---- event log ----
    def _append_event(self, event_type: str, actor: str,
                      payload: dict) -> dict:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "actor": actor,
            "payload": payload,
            "prev_hash": self._last_hash,
        }
        blob = json.dumps(event, sort_keys=True, default=str)
        event["hash"] = hashlib.sha256(blob.encode()).hexdigest()
        with self.log_path.open("a") as f:
            f.write(json.dumps(event, default=str) + "\n")
        self._last_hash = event["hash"]
        return event

    def verify_chain(self) -> bool:
        """Recompute every hash; any edit/deletion breaks the chain."""
        prev = "GENESIS"
        for line in self.log_path.read_text().splitlines():
            ev = json.loads(line)
            claimed = ev.pop("hash")
            if ev.get("prev_hash") != prev:
                return False
            blob = json.dumps(ev, sort_keys=True, default=str)
            if hashlib.sha256(blob.encode()).hexdigest() != claimed:
                return False
            prev = claimed
        return True

    def _replay(self) -> None:
        for line in self.log_path.read_text().splitlines():
            ev = json.loads(line)
            self._last_hash = ev["hash"]
            p = ev["payload"]
            if ev["type"] == "claim_added":
                c = Claim.model_validate(p["claim"])
                self.claims[c.id] = c
            elif ev["type"] == "obligation_created":
                o = Obligation.model_validate(p["obligation"])
                self.obligations[o.id] = o
            elif ev["type"] == "deadline_attached":
                o = self.obligations[p["obligation_id"]]
                o.deadline = Deadline.model_validate(p["deadline"])
            elif ev["type"] == "status_changed":
                o = self.obligations[p["obligation_id"]]
                o.status = ObligationStatus(p["to"])

    # ---- mutations (all logged) ----
    def add_claim(self, claim: Claim, actor: str = "system") -> Claim:
        self.claims[claim.id] = claim
        self._append_event("claim_added", actor,
                           {"claim": claim.model_dump(mode="json")})
        return claim

    def create_obligation(self, obligation: Obligation,
                          actor: str = "system") -> Obligation:
        missing = [c for c in obligation.claim_ids
                   if c not in self.claims]
        if missing:
            raise ValueError(f"unknown claim ids: {missing}")
        self.obligations[obligation.id] = obligation
        self._append_event(
            "obligation_created", actor,
            {"obligation": obligation.model_dump(mode="json")})
        return obligation

    def attach_deadline(self, obligation_id: str, deadline: Deadline,
                        actor: str = "engine") -> None:
        o = self.obligations[obligation_id]
        o.deadline = deadline
        self._append_event(
            "deadline_attached", actor,
            {"obligation_id": obligation_id,
             "deadline": deadline.model_dump(mode="json")})

    def transition(self, obligation_id: str, to: ObligationStatus,
                   actor: str, note: str = "",
                   principal: Principal | None = None) -> None:
        """Move an obligation through the workflow.

        If `principal` is supplied, authorization is enforced: only an
        APPROVE-capable role may reach SATISFIED, only VOID-capable may
        void. Agents call without a principal (they are internal and
        cannot reach SATISFIED anyway — the state machine forbids it
        from any state a human has not first reviewed).
        """
        o = self.obligations[obligation_id]
        if principal is not None:
            needed = {ObligationStatus.SATISFIED: Action.APPROVE,
                      ObligationStatus.VOID: Action.VOID
                      }.get(to, Action.TRANSITION)
            authorize(principal, needed)
            actor = principal.actor()
        if to not in ALLOWED_TRANSITIONS[o.status]:
            raise IllegalTransition(
                f"{o.status.value} -> {to.value} is not allowed")
        frm = o.status
        o.status = to
        self._append_event(
            "status_changed", actor,
            {"obligation_id": obligation_id, "from": frm.value,
             "to": to.value, "note": note})

    # ---- queries ----
    def open_obligations(self) -> list[Obligation]:
        closed = {ObligationStatus.SATISFIED, ObligationStatus.VOID,
                  ObligationStatus.BREACHED}
        return sorted(
            (o for o in self.obligations.values()
             if o.status not in closed),
            key=lambda o: (o.deadline.due_date if o.deadline
                           else date.max))
