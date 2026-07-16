"""Tier-2 extraction regression tests.

HONESTY NOTE: tier2 heuristics are anchored to the same templates the
corpus generator emits, so 100% here is a template-fit ceiling, NOT a
claim that regex beats LLMs on real documents. These tests lock the
harness end-to-end and guard regressions; tiers 0/1 provide the
meaningful zero-shot numbers.
"""

import sys
from pathlib import Path

sys.path.insert(0, "scripts")

from corpus import generate_corpus
from extract import extract_tier2
from benchmark_extraction import field_correct, SCORED


def test_tier2_perfect_on_seed42(tmp_path):
    docs = generate_corpus(tmp_path, n_per_type=8, seed=42)
    for d in docs:
        pred = extract_tier2(d.text).model_dump()
        for field in SCORED:
            gold_val = getattr(d, field)
            assert field_correct(field, pred.get(field), gold_val), \
                f"{d.doc_id}.{field}: {pred.get(field)!r} != {gold_val!r}"


def test_tier2_abstains_on_unknown_text():
    r = extract_tier2("Estimado cliente, obrigado pela sua carta.")
    assert r.regime_id is None
    assert r.deadline_amount is None
    assert r.event_date is None


# ----------------------- OCR garbage must abstain, not crash (Ph. 10)
def test_impossible_dates_abstain_rather_than_crash():
    """A fax-quality scan produced '31 de fevereiro de 2026'. The
    parser raised ValueError and aborted the whole document. An
    unreadable field must route to a human, not kill the pipeline."""
    for junk in ("efetuada em 31 de fevereiro de 2026",
                 "efetuada em 99 de março de 2026",
                 "deemed received on 31 February 2026",
                 "deemed received on 45 June 2026"):
        r = extract_tier2(junk)          # must not raise
        assert r.event_date is None


def test_ocr_mangled_document_does_not_crash_the_extractor():
    mangled = ("Tribusal Judicial da Comarca de Colmbra\n"
               "Fica v. Ex.º, Lúsitânia Construções, Lda., na "
               "qualidade de Mó, ltada para, no preso de MM dias, "
               "contestar\ne pagamento da quantia de € 165.435,45\n"
               "efetuada em 31 de fevereiro de 2026.")
    r = extract_tier2(mangled)           # must not raise
    assert r.event_date is None
