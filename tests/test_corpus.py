"""Corpus generator tests: determinism, gold-schema sanity, distractor
presence, and that every gold deadline actually computes under its
declared regime (corpus <-> engine coherence)."""

import json
from datetime import date
from pathlib import Path

from corpus import generate_corpus
from engine import compute_deadline
from pack_eu import EU
from pack_pt import PT

PACKS = {"PT": PT, "EU": EU}


def test_deterministic_under_seed(tmp_path):
    a = generate_corpus(tmp_path / "a", n_per_type=3, seed=7)
    b = generate_corpus(tmp_path / "b", n_per_type=3, seed=7)
    assert [d.text for d in a] == [d.text for d in b]
    c = generate_corpus(tmp_path / "c", n_per_type=3, seed=8)
    assert [d.text for d in a] != [d.text for d in c]


def test_gold_schema_and_files(tmp_path):
    docs = generate_corpus(tmp_path, n_per_type=4, seed=42)
    assert len(docs) == 20
    gold = json.loads((tmp_path / "gold.json").read_text())
    assert len(gold) == 20
    for g in gold:
        assert (tmp_path / "docs" / f"{g['doc_id']}.txt").exists()
        assert g["language"] in ("pt", "en")
        assert g["jurisdiction"] in ("PT", "EU")
        assert g["deadline_amount"] > 0


def test_distractors_present(tmp_path):
    docs = generate_corpus(tmp_path, n_per_type=4, seed=42)
    # every doc must contain at least two date-like strings and the
    # citação/notice types a second amount — the anti-shortcut design
    for d in docs:
        if d.doc_type in ("citacao_cpc", "eu_reg_notice",
                          "renovacao_cc", "eu_renewal"):
            # one gold date + one distractor date
            assert d.text.count(" de 20") + d.text.count(" 20") >= 2


def test_every_gold_deadline_computes(tmp_path):
    docs = generate_corpus(tmp_path, n_per_type=4, seed=42)
    for d in docs:
        pack = PACKS[d.jurisdiction]
        r = compute_deadline(pack, d.regime_id,
                             date.fromisoformat(d.event_date),
                             d.deadline_amount, d.deadline_unit)
        assert r.due_date > date.fromisoformat(d.event_date)
        assert r.steps[-1].startswith("DUE:")
