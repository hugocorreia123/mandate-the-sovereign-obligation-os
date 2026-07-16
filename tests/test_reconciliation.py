"""Phase 17 — documents disagree with each other.

Every earlier check looked inside one document. This one looks
between two — which is the only place the worst failure in the
project is visible.
"""

from datetime import date

import pytest

from graph import (Claim, ClaimType, Deadline, Edge, EdgeType,
                   Obligation, ObligationGraph, ObligationStatus,
                   ObligationType, SourceSpan)
from reconciliation import (FindingType, Severity, matter_key,
                            reconcile, render)


@pytest.fixture()
def g(tmp_path):
    return ObligationGraph(tmp_path / "log.jsonl")


def _obl(g, *, amount=None, due=None, event=date(2026, 3, 23),
         debtor="Lusitânia Construções, Lda.", creditor="Ana Silva",
         regime="cpc_processual", otype=ObligationType.RESPOND,
         desc="contestação", doc="doc_1", claims=True):
    ids = []
    if claims:
        c = g.add_claim(Claim(
            type=ClaimType.AMOUNT, value={"amount_eur": amount},
            confidence=0.9, source=SourceSpan(doc_id=doc,
                                              excerpt="quantia")))
        ids = [c.id]
    o = g.create_obligation(Obligation(
        type=otype, description=desc, debtor=debtor, creditor=creditor,
        amount_eur=amount, jurisdiction="PT", regime_id=regime,
        event_date=event, claim_ids=ids, doc_id=doc))
    if due:
        g.attach_deadline(o.id, Deadline(
            due_date=due, regime=regime, jurisdiction="PT",
            legal_refs=["CPC 138"], steps=["…"]))
    return o


# ============ the Phase 10 corruption, caught ============
def test_the_ocr_corruption_no_single_document_could_reveal(g):
    """Phase 10: tesseract read '€ 185.435,45' as '€ 165.435,45'.
    Plausible, well-formed, and invisible — nothing inside that
    document could contradict it. Another document can."""
    _obl(g, amount=185435.45, desc="citação (clean scan)",
         doc="doc_a")
    _obl(g, amount=165435.45, desc="citação (fax scan)", doc="doc_b")
    fs = reconcile(g)
    money = [f for f in fs if f.type is FindingType.AMOUNT_CONFLICT]
    assert len(money) == 1
    assert money[0].severity is Severity.CRITICAL
    assert money[0].values["difference"] == 20000.0
    assert "only the other document can" in money[0].detail
    assert "misread digit" in money[0].detail       # the right hint


def test_a_thousand_fold_misread_is_named_as_such(g):
    """121577.23 read as 121.57 — Phase 10's worst. The ratio itself
    is the diagnosis: that is a decimal point, not a dispute."""
    _obl(g, amount=121577.23, doc="doc_a")
    _obl(g, amount=121.57, doc="doc_b")
    f = [x for x in reconcile(g)
         if x.type is FindingType.AMOUNT_CONFLICT][0]
    assert "two orders of magnitude" in f.detail
    assert "not a dispute" in f.detail


def test_every_finding_cites_its_evidence(g):
    """A finding a human cannot verify is a rumour."""
    a = _obl(g, amount=185435.45, doc="doc_a")
    b = _obl(g, amount=165435.45, doc="doc_b")
    f = reconcile(g)[0]
    assert set(f.obligation_ids) == {a.id, b.id}
    assert len(f.claim_ids) == 2
    assert all(c in g.claims for c in f.claim_ids)


def test_amounts_within_tolerance_are_not_a_conflict(g):
    _obl(g, amount=185435.45, doc="doc_a")
    _obl(g, amount=185435.45, doc="doc_b")
    assert not [f for f in reconcile(g)
                if f.type is FindingType.AMOUNT_CONFLICT]


# ============ two live deadlines for one duty ============
def test_two_unlinked_deadlines_for_one_duty_is_flagged(g):
    a = _obl(g, due=date(2026, 4, 13), desc="original", doc="doc_a")
    b = _obl(g, due=date(2026, 5, 20), desc="amended", doc="doc_b")
    f = [x for x in reconcile(g)
         if x.type is FindingType.UNLINKED_AMENDMENT]
    assert len(f) == 1
    assert "cannot be correct" in f[0].detail


def test_linking_them_resolves_the_finding(g):
    """Once a human says 'this one supersedes that one', it is
    explained — and the superseded one stops being live at all."""
    a = _obl(g, due=date(2026, 4, 13), desc="original", doc="doc_a")
    b = _obl(g, due=date(2026, 5, 20), desc="amended", doc="doc_b")
    assert [x for x in reconcile(g)
            if x.type is FindingType.UNLINKED_AMENDMENT]
    g.supersede(b.id, a.id, actor="human:hugo",
                reason="prorrogação deferida")
    assert not [x for x in reconcile(g)
                if x.type is FindingType.UNLINKED_AMENDMENT]


def test_a_dependency_edge_also_counts_as_an_explanation(g):
    from graph import Edge, EdgeType
    a = _obl(g, due=date(2026, 4, 13), desc="first", doc="doc_a")
    b = _obl(g, due=date(2026, 5, 20), desc="second", doc="doc_b")
    g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=b.id,
                    to_id=a.id, reason="the period runs from the first"))
    assert not [x for x in reconcile(g)
                if x.type is FindingType.UNLINKED_AMENDMENT]


# ============ regime, duplicates, chronology ============
def test_one_duty_counted_under_two_regimes_is_flagged(g):
    _obl(g, due=date(2026, 4, 13), regime="cpc_processual",
         doc="doc_a")
    _obl(g, due=date(2026, 4, 13), regime="cc_corridos", doc="doc_b")
    f = [x for x in reconcile(g)
         if x.type is FindingType.REGIME_CONFLICT]
    assert len(f) == 1
    assert "does not govern it" in f[0].detail


def test_the_same_document_ingested_twice_is_noise_not_danger(g):
    _obl(g, amount=100.0, due=date(2026, 4, 13), doc="doc_a")
    _obl(g, amount=100.0, due=date(2026, 4, 13), doc="doc_a")
    f = [x for x in reconcile(g) if x.type is FindingType.DUPLICATE]
    assert len(f) == 1
    assert f[0].severity is Severity.INFO
    assert "escalate twice" in f[0].detail


def test_a_deadline_before_its_event_is_impossible(g):
    _obl(g, event=date(2026, 5, 1), due=date(2026, 4, 13),
         doc="doc_a")
    f = [x for x in reconcile(g)
         if x.type is FindingType.IMPOSSIBLE_CHRONOLOGY]
    assert len(f) == 1
    assert f[0].severity is Severity.CRITICAL
    assert "cannot end before it starts" in f[0].detail


# ============ what must NOT be flagged ============
def test_different_matters_are_never_compared(g):
    _obl(g, amount=185435.45, debtor="Empresa A, Lda.",
         creditor="Ana Silva", doc="doc_a")
    _obl(g, amount=999.99, debtor="Empresa B, S.A.",
         creditor="João Costa", doc="doc_b")
    assert reconcile(g) == []


def test_punctuation_noise_does_not_split_a_matter(g):
    """'TecnoVerde, S.A.' and 'TecnoVerde S.A' are one counterparty.
    A matter key that splits them misses every conflict between them."""
    _obl(g, amount=100.0, debtor="TecnoVerde, S.A.", doc="doc_a")
    _obl(g, amount=200.0, debtor="TecnoVerde S.A", doc="doc_b")
    assert [f for f in reconcile(g)
            if f.type is FindingType.AMOUNT_CONFLICT]


def test_the_matter_key_is_symmetric_in_the_parties(g):
    a = Obligation(type=ObligationType.RESPOND, description="x",
                   debtor="A, Lda.", creditor="B, S.A.",
                   jurisdiction="PT", regime_id="cpc_processual",
                   event_date=date(2026, 1, 1))
    b = Obligation(type=ObligationType.RESPOND, description="x",
                   debtor="B, S.A.", creditor="A, Lda.",
                   jurisdiction="PT", regime_id="cpc_processual",
                   event_date=date(2026, 1, 1))
    assert matter_key(a) == matter_key(b)


def test_a_superseded_obligation_is_history_not_a_conflict(g):
    """Phase 12 killed it. It must not resurface as a contradiction."""
    a = _obl(g, amount=185435.45, desc="original", doc="doc_a")
    b = _obl(g, amount=165435.45, desc="corrected", doc="doc_b")
    g.supersede(b.id, a.id, actor="human", reason="valor corrigido")
    assert not [f for f in reconcile(g)
                if f.type is FindingType.AMOUNT_CONFLICT]


def test_it_never_decides_who_is_right(g):
    """Two documents disagree; the system says so, shows both, and
    stops. Picking a winner is a legal judgement."""
    _obl(g, amount=185435.45, doc="doc_a")
    _obl(g, amount=165435.45, doc="doc_b")
    f = reconcile(g)[0]
    assert f.values["a"] == 185435.45 and f.values["b"] == 165435.45
    for word in ("correct", "should be", "the true", "use "):
        assert word not in f.detail.lower()


def test_reconciliation_needs_no_model_and_no_network():
    import reconciliation
    import sys
    names = set(dir(sys.modules["reconciliation"]))
    for forbidden in ("groq", "requests", "urllib", "socket",
                      "httpx", "openai"):
        assert forbidden not in names


def test_render_is_readable(g):
    _obl(g, amount=185435.45, doc="doc_a")
    _obl(g, amount=165435.45, doc="doc_b")
    out = render(reconcile(g))
    assert "amount_conflict" in out
    assert "must resolve before anything is filed" in out
    assert render([]) == "no contradictions between documents."
