"""Obligation Graph tests: schema, state machine, hash chain,
tamper detection, replay, and integration with the Deadline Engine."""

import json
from datetime import date
from pathlib import Path

import pytest

from engine import compute_deadline
from pack_pt import PT
from graph import (ALLOWED_TRANSITIONS, Claim, ClaimType, Deadline,
                   IllegalTransition, Obligation, ObligationGraph,
                   ObligationStatus, ObligationType, SourceSpan)


@pytest.fixture()
def g(tmp_path):
    return ObligationGraph(tmp_path / "log.jsonl")


def _claim(**kw):
    base = dict(type=ClaimType.OBLIGATION_TRIGGER, value="contestar",
                confidence=0.91, language="pt",
                source=SourceSpan(doc_id="doc_1", page=2,
                                  excerpt="prazo de 10 dias"))
    base.update(kw)
    return Claim(**base)


def test_obligation_requires_known_claims(g):
    with pytest.raises(ValueError):
        g.create_obligation(Obligation(
            type=ObligationType.RESPOND, description="contestação",
            debtor="Empresa X", creditor="Tribunal de Lisboa",
            jurisdiction="PT", regime_id="cpc_processual",
            event_date=date(2026, 3, 23), claim_ids=["clm_missing"]))


def test_full_flow_with_engine_integration(g):
    c = g.add_claim(_claim())
    o = g.create_obligation(Obligation(
        type=ObligationType.RESPOND, description="contestação",
        debtor="Empresa X", creditor="Tribunal de Lisboa",
        jurisdiction="PT", regime_id="cpc_processual",
        event_date=date(2026, 3, 23), claim_ids=[c.id],
        doc_id="doc_1"), actor="agent:obligation")
    r = compute_deadline(PT, o.regime_id, o.event_date, 10)
    g.attach_deadline(o.id, Deadline(
        due_date=r.due_date, regime=r.regime, jurisdiction="PT",
        legal_refs=r.legal_refs, steps=r.steps))
    assert g.obligations[o.id].deadline.due_date == date(2026, 4, 13)

    g.transition(o.id, ObligationStatus.IN_PROGRESS, "agent:drafter")
    g.transition(o.id, ObligationStatus.AWAITING_APPROVAL,
                 "agent:drafter")
    g.transition(o.id, ObligationStatus.SATISFIED, "human:hugo",
                 note="approved and filed")
    assert g.obligations[o.id].status == ObligationStatus.SATISFIED


def test_illegal_transition_raises(g):
    c = g.add_claim(_claim())
    o = g.create_obligation(Obligation(
        type=ObligationType.PAY, description="pagamento",
        debtor="X", creditor="Y", jurisdiction="PT",
        regime_id="cc_corridos", event_date=date(2026, 1, 5),
        claim_ids=[c.id]))
    with pytest.raises(IllegalTransition):
        g.transition(o.id, ObligationStatus.SATISFIED, "human")
    # terminal states allow nothing
    assert ALLOWED_TRANSITIONS[ObligationStatus.SATISFIED] == set()


def test_hash_chain_verifies_and_detects_tampering(g, tmp_path):
    c = g.add_claim(_claim())
    g.create_obligation(Obligation(
        type=ObligationType.NOTIFY, description="notificar",
        debtor="X", creditor="Y", jurisdiction="EU",
        regime_id="eu_1182_days", event_date=date(2026, 1, 12),
        claim_ids=[c.id]))
    assert g.verify_chain() is True

    lines = g.log_path.read_text().splitlines()
    ev = json.loads(lines[0])
    ev["payload"]["claim"]["confidence"] = 0.99  # forge
    lines[0] = json.dumps(ev, default=str)
    g.log_path.write_text("\n".join(lines) + "\n")
    assert g.verify_chain() is False


def test_replay_reconstructs_state(g, tmp_path):
    c = g.add_claim(_claim())
    o = g.create_obligation(Obligation(
        type=ObligationType.RESPOND, description="contestação",
        debtor="X", creditor="Y", jurisdiction="PT",
        regime_id="cpc_processual", event_date=date(2026, 3, 23),
        claim_ids=[c.id]))
    g.transition(o.id, ObligationStatus.IN_PROGRESS, "agent")

    g2 = ObligationGraph(g.log_path)  # replay from disk
    assert g2.obligations[o.id].status == ObligationStatus.IN_PROGRESS
    assert c.id in g2.claims
    assert g2.verify_chain() is True


def test_open_obligations_sorted_by_deadline(g):
    c = g.add_claim(_claim())
    o1 = g.create_obligation(Obligation(
        type=ObligationType.PAY, description="later",
        debtor="X", creditor="Y", jurisdiction="PT",
        regime_id="cc_corridos", event_date=date(2026, 1, 5),
        claim_ids=[c.id]))
    o2 = g.create_obligation(Obligation(
        type=ObligationType.PAY, description="sooner",
        debtor="X", creditor="Y", jurisdiction="PT",
        regime_id="cc_corridos", event_date=date(2026, 1, 5),
        claim_ids=[c.id]))
    g.attach_deadline(o1.id, Deadline(
        due_date=date(2026, 3, 1), regime="cc", jurisdiction="PT",
        legal_refs=[], steps=[]))
    g.attach_deadline(o2.id, Deadline(
        due_date=date(2026, 2, 1), regime="cc", jurisdiction="PT",
        legal_refs=[], steps=[]))
    assert [o.description for o in g.open_obligations()][:2] == \
        ["sooner", "later"]
