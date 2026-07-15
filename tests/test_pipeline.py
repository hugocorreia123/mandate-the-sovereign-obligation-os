"""Pipeline tests — deterministic spine, no API keys needed.

Fake drafter/red-team injections prove the doctrine mechanically:
a draft missing the engine's date is BLOCKED before the human gate.
"""

import sys
from pathlib import Path

sys.path.insert(0, ".")

from corpus import generate_corpus
from graph import ObligationGraph, ObligationStatus
from pipeline import approve, process_document


def good_drafter(text, ex, r):
    return (f"Draft: respond by {r.due_date.isoformat()} "
            f"({ex.deadline_amount} {ex.deadline_unit}) per "
            f"{ex.legal_basis}. Amount EUR {ex.amount_eur:,.2f}. "
            f"DRAFT — PENDING LEGAL REVIEW")


def bad_drafter(text, ex, r):
    return "Draft: respond by 2099-01-01 someday. No citations."


def test_full_flow_reaches_human_gate(tmp_path):
    docs = generate_corpus(tmp_path / "c", n_per_type=1, seed=42)
    g = ObligationGraph(tmp_path / "log.jsonl")
    d = docs[0]  # pt citação
    res = process_document(d.text, d.doc_id, g, tier="tier2",
                           drafter=good_drafter)
    assert res.status == "awaiting_approval"
    assert res.red_team_verdict["pass"] is True
    o = g.obligations[res.obligation_id]
    assert o.status == ObligationStatus.AWAITING_APPROVAL
    assert o.deadline is not None
    assert g.verify_chain() is True

    approve(g, res.obligation_id, "hugo")
    assert g.obligations[res.obligation_id].status == \
        ObligationStatus.SATISFIED


def test_bad_draft_blocked_before_gate(tmp_path):
    docs = generate_corpus(tmp_path / "c", n_per_type=1, seed=42)
    g = ObligationGraph(tmp_path / "log.jsonl")
    d = docs[0]
    res = process_document(d.text, d.doc_id, g, tier="tier2",
                           drafter=bad_drafter)
    assert res.status == "in_progress"          # NOT at the gate
    assert res.red_team_verdict["pass"] is False
    failed = [c["check"] for c in res.red_team_verdict["checks"]
              if not c["pass"]]
    assert "due_date_verbatim" in failed


def test_abstention_routes_to_human(tmp_path):
    g = ObligationGraph(tmp_path / "log.jsonl")
    res = process_document("Estimado cliente, bom dia.", "junk_001",
                           g, tier="tier2")
    assert res.status == "needs_human_extraction"
    assert res.obligation_id is None


def test_every_corpus_doc_flows_deterministically(tmp_path):
    docs = generate_corpus(tmp_path / "c", n_per_type=2, seed=42)
    g = ObligationGraph(tmp_path / "log.jsonl")
    for d in docs:
        res = process_document(d.text, d.doc_id, g, tier="tier2",
                               drafter=good_drafter)
        assert res.status == "awaiting_approval", d.doc_id
    assert len(g.obligations) == len(docs)
    assert g.verify_chain() is True


# ------------------------------- the empty-draft hole (Phase 9e)
def empty_drafter(text, ex, r):
    return ""


def whitespace_drafter(text, ex, r):
    return "   \n\n  "


def test_an_empty_draft_never_reaches_the_human_gate(tmp_path):
    """The judge scores an empty draft GROUNDED — it contains no false
    claims — which is how groundedness peaked at 0.938 on a batch with
    4 empty drafts. Silence must fail, mechanically."""
    docs = generate_corpus(tmp_path / "c", n_per_type=1, seed=42)
    g = ObligationGraph(tmp_path / "log.jsonl")
    res = process_document(docs[0].text, docs[0].doc_id, g,
                           tier="tier2", drafter=empty_drafter)
    assert res.status != "awaiting_approval"
    failed = [c["check"] for c in res.red_team_verdict["checks"]
              if not c["pass"]]
    assert "draft_not_empty" in failed


def test_whitespace_is_not_a_draft(tmp_path):
    docs = generate_corpus(tmp_path / "c", n_per_type=1, seed=42)
    g = ObligationGraph(tmp_path / "log.jsonl")
    res = process_document(docs[0].text, docs[0].doc_id, g,
                           tier="tier2", drafter=whitespace_drafter)
    assert res.status != "awaiting_approval"
