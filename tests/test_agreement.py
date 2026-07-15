"""Phase 9 — kappa machinery tests."""

import pytest

from agreement import (agreement_report, cohens_kappa, confusion,
                       raw_agreement, render_confusion)

L = ["UNGROUNDED", "PARTIALLY_GROUNDED", "GROUNDED"]


def test_perfect_agreement_is_one():
    a = ["GROUNDED", "UNGROUNDED", "PARTIALLY_GROUNDED"] * 4
    assert cohens_kappa(a, a) == 1.0


def test_chance_agreement_is_about_zero():
    # both raters use the same marginals but pair up at random
    a = ["GROUNDED"] * 5 + ["UNGROUNDED"] * 5
    b = ["GROUNDED", "UNGROUNDED"] * 5
    k = cohens_kappa(a, b)
    assert -0.3 < k < 0.3          # near chance


def test_total_disagreement_is_negative():
    a = ["GROUNDED"] * 5 + ["UNGROUNDED"] * 5
    b = ["UNGROUNDED"] * 5 + ["GROUNDED"] * 5
    assert cohens_kappa(a, b) < 0


def test_kappa_punishes_agreement_that_chance_explains():
    """90% raw agreement can be worthless if both raters almost always
    say the same thing anyway — that is the entire point of kappa."""
    a = ["GROUNDED"] * 19 + ["UNGROUNDED"]
    b = ["GROUNDED"] * 20
    assert raw_agreement(a, b) == 0.95
    assert cohens_kappa(a, b) < 0.2      # chance explains it


def test_raters_must_be_same_length():
    with pytest.raises(ValueError):
        cohens_kappa(["GROUNDED"], ["GROUNDED", "UNGROUNDED"])


def test_empty_is_zero_not_crash():
    assert cohens_kappa([], []) == 0.0
    assert raw_agreement([], []) == 0.0


def test_confusion_counts_rows_human_cols_judge():
    h = ["GROUNDED", "GROUNDED", "UNGROUNDED"]
    j = ["GROUNDED", "UNGROUNDED", "UNGROUNDED"]
    m = confusion(h, j, L)
    assert m["GROUNDED"]["GROUNDED"] == 1
    assert m["GROUNDED"]["UNGROUNDED"] == 1
    assert m["UNGROUNDED"]["UNGROUNDED"] == 1


def test_render_confusion_is_readable():
    h = ["GROUNDED", "UNGROUNDED"]
    j = ["GROUNDED", "UNGROUNDED"]
    out = render_confusion(h, j, L)
    assert "judge" in out and "human" in out


def test_strictness_detects_a_harsher_judge():
    h = ["GROUNDED"] * 10
    j = ["PARTIALLY_GROUNDED"] * 10        # judge one grade down
    rep = agreement_report(h, j, L)
    assert "STRICTER" in rep["strictness"]["reading"]
    assert rep["strictness"]["mean_shift"] < 0


def test_strictness_detects_a_lenient_judge():
    h = ["UNGROUNDED"] * 10
    j = ["PARTIALLY_GROUNDED"] * 10
    rep = agreement_report(h, j, L)
    assert "LENIENT" in rep["strictness"]["reading"]


def test_no_bias_when_disagreements_are_symmetric():
    h = ["GROUNDED", "UNGROUNDED"] * 5
    j = ["PARTIALLY_GROUNDED", "PARTIALLY_GROUNDED"] * 5
    rep = agreement_report(h, j, L)
    assert rep["strictness"]["reading"] == "no systematic strictness bias"


def test_report_carries_everything_needed_to_judge_the_judge():
    h = ["GROUNDED"] * 6 + ["UNGROUNDED"] * 6
    j = ["GROUNDED"] * 5 + ["PARTIALLY_GROUNDED"] + ["UNGROUNDED"] * 6
    rep = agreement_report(h, j, L)
    assert set(rep) >= {"n", "cohens_kappa", "raw_agreement",
                        "confusion", "human_marginals",
                        "judge_marginals", "strictness"}
    assert rep["n"] == 12


# ------------------------------- label-space coverage (Phase 9 finding)
def test_detects_a_judge_that_never_uses_the_harshest_label():
    """The finding that motivated this diagnostic: a judge scored
    kappa 0.62 ('substantial' by convention) while catching 0 of 4
    clearly-broken drafts — because it had never once said UNGROUNDED.
    Kappa rewards agreement on the easy majority; only the marginals
    expose a collapsed label space."""
    human = ["UNGROUNDED"] * 4 + ["PARTIALLY_GROUNDED"] * 9 + \
        ["GROUNDED"] * 9
    judge = ["PARTIALLY_GROUNDED"] * 4 + ["PARTIALLY_GROUNDED"] * 9 + \
        ["PARTIALLY_GROUNDED"] * 1 + ["GROUNDED"] * 8
    rep = agreement_report(human, judge, L)
    cov = rep["label_coverage"]
    assert cov["collapsed"] is True
    assert cov["judge_never_used"] == ["UNGROUNDED"]
    assert "NEVER USES" in cov["reading"]
    assert rep["cohens_kappa"] > 0.5      # looks fine; isn't


def test_full_label_space_is_not_flagged():
    human = ["UNGROUNDED", "PARTIALLY_GROUNDED", "GROUNDED"] * 3
    judge = ["UNGROUNDED", "GROUNDED", "PARTIALLY_GROUNDED"] * 3
    cov = agreement_report(human, judge, L)["label_coverage"]
    assert cov["collapsed"] is False
    assert cov["judge_never_used"] == []
