"""Phase 12 — the obligation GRAPH.

Until now "Obligation Graph" was aspirational: obligations existed
independently and nothing connected them. That permits a specific,
nasty failure — an amendment lands, the original deadline is legally
dead, and the system keeps counting down to it. A superseded
obligation that still fires alerts is worse than no system, because it
teaches people to ignore alerts.
"""

from datetime import date

import pytest

from graph import (Claim, ClaimType, CycleDetected, Deadline, Edge,
                   EdgeType, Obligation, ObligationGraph,
                   ObligationStatus, ObligationType, SourceSpan)


@pytest.fixture()
def g(tmp_path):
    return ObligationGraph(tmp_path / "log.jsonl")


def _claim(g):
    return g.add_claim(Claim(
        type=ClaimType.OBLIGATION_TRIGGER, value={"x": 1},
        confidence=0.9, source=SourceSpan(doc_id="d1")))


def _obl(g, desc="contestação", due=None):
    c = _claim(g)
    o = g.create_obligation(Obligation(
        type=ObligationType.RESPOND, description=desc,
        debtor="Empresa X", creditor="Tribunal", jurisdiction="PT",
        regime_id="cpc_processual", event_date=date(2026, 3, 23),
        claim_ids=[c.id]))
    if due:
        g.attach_deadline(o.id, Deadline(
            due_date=due, regime="cpc", jurisdiction="PT",
            legal_refs=["CPC 138"], steps=["…"]))
    return o


# ------------------------------------------------ structural sanity
def test_an_obligation_cannot_relate_to_itself(g):
    o = _obl(g)
    with pytest.raises(ValueError):
        g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=o.id,
                        to_id=o.id))


def test_edges_require_known_obligations(g):
    o = _obl(g)
    with pytest.raises(ValueError):
        g.add_edge(Edge(type=EdgeType.SUPERSEDES, from_id=o.id,
                        to_id="obl_nope"))


def test_dependency_cycles_are_rejected(g):
    """Two obligations each waiting on the other can never start."""
    a, b = _obl(g, "A"), _obl(g, "B")
    g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=a.id,
                    to_id=b.id))
    with pytest.raises(CycleDetected):
        g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=b.id,
                        to_id=a.id))


def test_longer_cycles_are_rejected_too(g):
    a, b, c = _obl(g, "A"), _obl(g, "B"), _obl(g, "C")
    g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=a.id, to_id=b.id))
    g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=b.id, to_id=c.id))
    with pytest.raises(CycleDetected):
        g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=c.id,
                        to_id=a.id))


# --------------------------------------------------- supersession
def test_superseding_kills_the_original_deadline(g):
    """THE failure this phase exists to prevent."""
    old = _obl(g, "original contestação", due=date(2026, 4, 13))
    new = _obl(g, "amended contestação", due=date(2026, 5, 20))
    g.supersede(new.id, old.id, actor="human:hugo",
                reason="prorrogação deferida em 2026-04-02")

    assert g.obligations[old.id].status is ObligationStatus.VOID
    assert g.superseded_by(old.id) == new.id
    assert g.is_live(old.id) is False
    assert g.is_live(new.id) is True
    # and it is GONE from what anyone is shown
    assert old.id not in [o.id for o in g.open_obligations()]
    assert new.id in [o.id for o in g.open_obligations()]


def test_supersession_records_why_in_the_chain(g):
    old, new = _obl(g, "original"), _obl(g, "amended")
    g.supersede(new.id, old.id, actor="human:hugo",
                reason="prorrogação deferida em 2026-04-02")
    log = g.log_path.read_text()
    assert "prorrogação deferida" in log
    assert "edge_added" in log
    assert g.verify_chain() is True


def test_supersession_works_from_awaiting_approval(g):
    """An amendment can land while a draft sits at the human gate.
    VOID is not reachable from AWAITING_APPROVAL, so the transition
    must step back rather than raise."""
    old, new = _obl(g, "original"), _obl(g, "amended")
    g.transition(old.id, ObligationStatus.IN_PROGRESS, "agent")
    g.transition(old.id, ObligationStatus.AWAITING_APPROVAL, "agent")
    g.supersede(new.id, old.id, actor="human:hugo")
    assert g.obligations[old.id].status is ObligationStatus.VOID


def test_a_satisfied_obligation_is_not_voided_by_supersession(g):
    """History is not rewritten: something already done stays done."""
    old, new = _obl(g, "original"), _obl(g, "amended")
    g.transition(old.id, ObligationStatus.IN_PROGRESS, "agent")
    g.transition(old.id, ObligationStatus.AWAITING_APPROVAL, "agent")
    g.transition(old.id, ObligationStatus.SATISFIED, "human")
    g.supersede(new.id, old.id, actor="human")
    assert g.obligations[old.id].status is ObligationStatus.SATISFIED


def test_a_chain_of_amendments_leaves_only_the_last_live(g):
    v1, v2, v3 = _obl(g, "v1"), _obl(g, "v2"), _obl(g, "v3")
    g.supersede(v2.id, v1.id, actor="human")
    g.supersede(v3.id, v2.id, actor="human")
    live = [o.id for o in g.open_obligations()]
    assert live == [v3.id]


# ---------------------------------------------------- dependencies
def test_a_blocked_obligation_is_open_but_not_actionable(g):
    """It is real, and it is not yet anyone's problem. Those are
    different things, and a human should only be shown the second."""
    ruling = _obl(g, "await court ruling", due=date(2026, 5, 1))
    reply = _obl(g, "reply to the ruling", due=date(2026, 6, 1))
    g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=reply.id,
                    to_id=ruling.id,
                    reason="the period runs from the ruling"))

    assert g.blocked_by(reply.id) == [ruling.id]
    assert g.is_live(reply.id) is False
    assert reply.id in [o.id for o in g.open_obligations()]
    assert reply.id not in [o.id for o in g.actionable_obligations()]
    assert ruling.id in [o.id for o in g.actionable_obligations()]


def test_satisfying_the_blocker_releases_the_dependent(g):
    ruling = _obl(g, "await ruling")
    reply = _obl(g, "reply")
    g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=reply.id,
                    to_id=ruling.id))
    g.transition(ruling.id, ObligationStatus.IN_PROGRESS, "agent")
    g.transition(ruling.id, ObligationStatus.AWAITING_APPROVAL, "agent")
    g.transition(ruling.id, ObligationStatus.SATISFIED, "human")

    assert g.blocked_by(reply.id) == []
    assert g.is_live(reply.id) is True
    assert reply.id in [o.id for o in g.actionable_obligations()]


def test_multiple_blockers_all_must_clear(g):
    a, b, dep = _obl(g, "A"), _obl(g, "B"), _obl(g, "dependent")
    for blocker in (a, b):
        g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=dep.id,
                        to_id=blocker.id))
    assert len(g.blocked_by(dep.id)) == 2
    for blocker in (a, b):
        g.transition(blocker.id, ObligationStatus.IN_PROGRESS, "x")
        g.transition(blocker.id, ObligationStatus.AWAITING_APPROVAL, "x")
        g.transition(blocker.id, ObligationStatus.SATISFIED, "human")
    assert g.blocked_by(dep.id) == []


# ---------------------------------------------------- renewal chains
def test_a_renewal_chain_can_be_walked(g):
    y1, y2, y3 = _obl(g, "term 2024"), _obl(g, "term 2025"), \
        _obl(g, "term 2026")
    g.add_edge(Edge(type=EdgeType.RENEWS, from_id=y1.id, to_id=y2.id))
    g.add_edge(Edge(type=EdgeType.RENEWS, from_id=y2.id, to_id=y3.id))
    assert g.chain(y1.id) == [y1.id, y2.id, y3.id]


def test_chain_walking_survives_a_loop(g):
    a, b = _obl(g, "A"), _obl(g, "B")
    g.add_edge(Edge(type=EdgeType.RENEWS, from_id=a.id, to_id=b.id))
    g.add_edge(Edge(type=EdgeType.RENEWS, from_id=b.id, to_id=a.id))
    assert g.chain(a.id) == [a.id, b.id]      # terminates


# --------------------------------------------------------- replay
def test_edges_survive_replay_and_the_chain_still_verifies(g):
    old, new = _obl(g, "original"), _obl(g, "amended")
    dep = _obl(g, "dependent")
    g.supersede(new.id, old.id, actor="human", reason="amendment")
    g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=dep.id,
                    to_id=new.id))

    g2 = ObligationGraph(g.log_path)
    assert len(g2.edges) == 2
    assert g2.superseded_by(old.id) == new.id
    assert g2.blocked_by(dep.id) == [new.id]
    assert g2.obligations[old.id].status is ObligationStatus.VOID
    assert g2.verify_chain() is True
