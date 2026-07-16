"""Phase 10 — the scan generator and the perception tier.

The generator must be deterministic (a benchmark you cannot reproduce
is an anecdote) and must actually DISCRIMINATE — the profiles were
calibrated by sweeping until OCR started losing facts, because a
degradation ladder that OCR shrugs off measures nothing.
"""

import random
from pathlib import Path

import pytest
from PIL import Image

from corpus import generate_corpus
from perception import (LANG_PACK, OCRUnavailable, available_langs,
                        ocr_page)
from scanning import PROFILES, ScanProfile, degrade, render, scan_corpus


# ----------------------------------------------------- the generator
def test_renders_a_page(tmp_path):
    docs = generate_corpus(tmp_path / "c", n_per_type=1, seed=42)
    img = render(docs[0].text, random.Random(1))
    assert img.width == 1240 and img.height >= 1754
    assert img.mode == "L"


def test_scanning_is_deterministic(tmp_path):
    docs = generate_corpus(tmp_path / "c", n_per_type=1, seed=42)
    a = scan_corpus(tmp_path / "c", tmp_path / "a", "fax", seed=7)
    b = scan_corpus(tmp_path / "c", tmp_path / "b", "fax", seed=7)
    assert Image.open(a[0]).tobytes() == Image.open(b[0]).tobytes()


def test_different_seeds_give_different_scans(tmp_path):
    generate_corpus(tmp_path / "c", n_per_type=1, seed=42)
    a = scan_corpus(tmp_path / "c", tmp_path / "a", "fax", seed=7)
    b = scan_corpus(tmp_path / "c", tmp_path / "b", "fax", seed=8)
    assert Image.open(a[0]).tobytes() != Image.open(b[0]).tobytes()


def test_profiles_are_ordered_by_damage(tmp_path):
    """clean < office < photocopy < fax, monotonically."""
    order = ["clean", "office", "photocopy", "fax"]
    prev = None
    for name in order:
        p = PROFILES[name]
        score = (p.skew_deg + p.noise / 10 + p.blur * 2
                 + (95 - p.jpeg_quality) / 20 + (1 - p.dpi_scale) * 3)
        if prev is not None:
            assert score > prev, f"{name} is not worse than the last"
        prev = score


def test_degradation_actually_changes_the_pixels(tmp_path):
    docs = generate_corpus(tmp_path / "c", n_per_type=1, seed=42)
    base = render(docs[0].text, random.Random(1))
    fax = degrade(base.copy(), PROFILES["fax"], random.Random(1))
    assert fax.tobytes() != base.tobytes()


def test_every_corpus_document_gets_a_scan(tmp_path):
    docs = generate_corpus(tmp_path / "c", n_per_type=2, seed=42)
    made = scan_corpus(tmp_path / "c", tmp_path / "s", "office")
    assert len(made) == len(docs)
    assert all(p.exists() for p in made)


# ------------------------------------------------ the perception tier
def test_language_pack_map_is_explicit():
    assert LANG_PACK["pt"] == "por" and LANG_PACK["en"] == "eng"


def test_missing_pack_refuses_rather_than_mismeasuring(tmp_path):
    """Reading Portuguese with the English model silently strips
    diacritics. Strict mode must raise, not quietly substitute."""
    if "por" in available_langs():
        pytest.skip("por pack installed — cannot test the refusal")
    docs = generate_corpus(tmp_path / "c", n_per_type=1, seed=42)
    scans = scan_corpus(tmp_path / "c", tmp_path / "s", "clean")
    pt = [p for p in scans if p.stem.startswith("pt")]
    if not pt:
        pytest.skip("no pt document in this sample")
    with pytest.raises(OCRUnavailable):
        ocr_page(pt[0], lang="pt", strict=True)


def test_non_strict_falls_back_but_only_when_asked(tmp_path):
    if "por" in available_langs():
        pytest.skip("por pack installed")
    docs = generate_corpus(tmp_path / "c", n_per_type=1, seed=42)
    scans = scan_corpus(tmp_path / "c", tmp_path / "s", "clean")
    pt = [p for p in scans if p.stem.startswith("pt")]
    if not pt:
        pytest.skip("no pt document")
    out = ocr_page(pt[0], lang="pt", strict=False)
    assert len(out) > 50          # it read something, under protest


@pytest.mark.skipif(not available_langs(), reason="no tesseract")
def test_ocr_reads_a_clean_english_page(tmp_path):
    generate_corpus(tmp_path / "c", n_per_type=2, seed=42)
    scans = scan_corpus(tmp_path / "c", tmp_path / "s", "clean")
    en = [p for p in scans if p.stem.startswith("en")]
    if not en:
        pytest.skip("no en document")
    out = ocr_page(en[0], lang="en")
    assert len(out) > 200
    assert "Regulation" in out or "Agreement" in out
