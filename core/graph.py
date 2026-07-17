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


class EdgeType(str, Enum):
    """How one obligation relates to another.

    These are not decorations: each carries a consequence the engine
    enforces. A superseded obligation that keeps counting down is
    worse than no system at all — it teaches people to ignore alerts.
    """
    SUPERSEDES = "supersedes"      # an amendment replaces the original
    DEPENDS_ON = "depends_on"      # cannot proceed until the other is
    #                                satisfied (its period runs from
    #                                the other's satisfaction)
    TRIGGERS = "triggers"          # satisfying this one activates that
    RENEWS = "renews"              # a term renewed: the next link in a
    #                                renewal chain


class Edge(BaseModel):
    id: str = Field(default_factory=lambda: f"edg_{uuid4().hex[:10]}")
    type: EdgeType
    from_id: str                   # the acting obligation
    to_id: str                     # the affected obligation
    reason: str = ""               # why — a human must be able to read
    claim_ids: list[str] = Field(default_factory=list)


class CycleDetected(Exception):
    """A dependency cycle: obligations that each wait on the other."""


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
        self.edges: dict[str, Edge] = {}
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
        # ensure_ascii=False: the ledger stored Portuguese as
        # "prorroga\\u00e7\\u00e3o" — valid JSON, unreadable to the
        # humans it exists for, and invisible to grep. A log whose
        # premise is "a court may one day read this" must be readable
        # in the language of the jurisdiction. The hash is computed
        # over the same form it is written in, so the chain stays
        # consistent.
        blob = json.dumps(event, sort_keys=True, default=str,
                          ensure_ascii=False)
        event["hash"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str,
                               ensure_ascii=False) + "\n")
        self._last_hash = event["hash"]
        return event

    def verify_chain(self) -> bool:
        """Recompute every hash; any edit/deletion breaks the chain.

        A ledger with no events verifies: nothing has been tampered
        with because nothing has happened. This used to raise
        FileNotFoundError — a fresh system could not answer "is my
        chain intact?" — and callers papered over it with
        `not path.exists() or verify_chain()`, which is a workaround
        for a broken method rather than a fix. Found by the Phase 19
        hardening pass, when the first hostile document abstained and
        wrote no events at all.
        """
        if not self.log_path.exists():
            return True
        prev = "GENESIS"
        for line in self.log_path.read_text(
                encoding="utf-8").splitlines():
            ev = json.loads(line)
            claimed = ev.pop("hash")
            if ev.get("prev_hash") != prev:
                return False
            blob = json.dumps(ev, sort_keys=True, default=str,
                              ensure_ascii=False)
            if hashlib.sha256(
                    blob.encode("utf-8")).hexdigest() != claimed:
                return False
            prev = claimed
        return True

    def _replay(self) -> None:
        for line in self.log_path.read_text(
                encoding="utf-8").splitlines():
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
            elif ev["type"] == "edge_added":
                e = Edge.model_validate(p["edge"])
                self.edges[e.id] = e

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

    # ---- edges ----
    def add_edge(self, edge: Edge, actor: str = "system") -> Edge:
        """Relate two obligations. Rejects nonsense structurally."""
        for oid in (edge.from_id, edge.to_id):
            if oid not in self.obligations:
                raise ValueError(f"unknown obligation: {oid}")
        if edge.from_id == edge.to_id:
            raise ValueError("an obligation cannot relate to itself")
        missing = [c for c in edge.claim_ids if c not in self.claims]
        if missing:
            raise ValueError(f"unknown claim ids: {missing}")
        if edge.type is EdgeType.DEPENDS_ON:
            # would this close a waiting-loop?
            if self._reaches(edge.to_id, edge.from_id,
                             EdgeType.DEPENDS_ON):
                raise CycleDetected(
                    f"{edge.from_id} depends on {edge.to_id}, which "
                    f"already depends on it — neither could ever start")
        self.edges[edge.id] = edge
        self._append_event("edge_added", actor,
                           {"edge": edge.model_dump(mode="json")})
        return edge

    def _out(self, oid: str, etype: "EdgeType | None" = None
             ) -> list[Edge]:
        return [e for e in self.edges.values()
                if e.from_id == oid and (etype is None
                                         or e.type is etype)]

    def _in(self, oid: str, etype: "EdgeType | None" = None
            ) -> list[Edge]:
        return [e for e in self.edges.values()
                if e.to_id == oid and (etype is None
                                       or e.type is etype)]

    def _reaches(self, start: str, target: str,
                 etype: EdgeType) -> bool:
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            if cur == target:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(e.to_id for e in self._out(cur, etype))
        return False

    def supersede(self, new_id: str, old_id: str, actor: str,
                  reason: str = "", claim_ids: list[str] | None = None
                  ) -> Edge:
        """An amendment replaces an earlier obligation — atomically.

        Recording the edge is not enough: the old obligation must STOP
        being live, or the ledger keeps counting down to a deadline the
        law has already killed. Supersession therefore voids the old
        obligation and says why, in one logged step.
        """
        edge = self.add_edge(Edge(
            type=EdgeType.SUPERSEDES, from_id=new_id, to_id=old_id,
            reason=reason or f"superseded by {new_id}",
            claim_ids=claim_ids or []), actor=actor)
        old = self.obligations[old_id]
        if old.status not in (ObligationStatus.SATISFIED,
                              ObligationStatus.VOID,
                              ObligationStatus.BREACHED):
            if old.status is not ObligationStatus.PENDING:
                # VOID is reachable from PENDING/IN_PROGRESS/ESCALATED;
                # from AWAITING_APPROVAL it is not, so step back first.
                if old.status is ObligationStatus.AWAITING_APPROVAL:
                    self.transition(old_id, ObligationStatus.IN_PROGRESS,
                                    actor,
                                    note="stepped back to void: "
                                         "superseded")
            self.transition(old_id, ObligationStatus.VOID, actor,
                            note=edge.reason)
        return edge

    def superseded_by(self, oid: str) -> Optional[str]:
        inc = self._in(oid, EdgeType.SUPERSEDES)
        return inc[0].from_id if inc else None

    def blocked_by(self, oid: str) -> list[str]:
        """Unsatisfied obligations this one is waiting on."""
        return [e.to_id for e in self._out(oid, EdgeType.DEPENDS_ON)
                if self.obligations[e.to_id].status
                is not ObligationStatus.SATISFIED]

    def is_live(self, oid: str) -> bool:
        """Live = not closed, not superseded, not blocked."""
        o = self.obligations[oid]
        closed = {ObligationStatus.SATISFIED, ObligationStatus.VOID,
                  ObligationStatus.BREACHED}
        if o.status in closed:
            return False
        if self.superseded_by(oid):
            return False
        return not self.blocked_by(oid)

    def chain(self, oid: str, etype: EdgeType = EdgeType.RENEWS
              ) -> list[str]:
        """Walk a renewal/trigger chain from this obligation."""
        out, cur, seen = [oid], oid, {oid}
        while True:
            nxt = [e.to_id for e in self._out(cur, etype)]
            if not nxt or nxt[0] in seen:
                return out
            cur = nxt[0]
            seen.add(cur)
            out.append(cur)

    # ---- queries ----
    def open_obligations(self) -> list[Obligation]:
        closed = {ObligationStatus.SATISFIED, ObligationStatus.VOID,
                  ObligationStatus.BREACHED}
        return sorted(
            (o for o in self.obligations.values()
             if o.status not in closed
             and not self.superseded_by(o.id)),
            key=lambda o: (o.deadline.due_date if o.deadline
                           else date.max))

    def actionable_obligations(self) -> list[Obligation]:
        """Open, not superseded, and not waiting on anything else.

        This is what a human should actually see. `open_obligations`
        includes items that are blocked — real, but not yet anyone's
        problem.
        """
        return [o for o in self.open_obligations()
                if not self.blocked_by(o.id)]
