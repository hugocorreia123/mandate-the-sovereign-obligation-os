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
