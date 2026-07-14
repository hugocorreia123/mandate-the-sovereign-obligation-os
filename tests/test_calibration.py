"""Phase 8 — calibration tests.

The machinery must: read agreement correctly, produce confidences that
*mean* something (better ECE than a hardcoded constant), and give a
threshold that actually delivers the requested precision.
"""

import random

import pytest

from calibration import (Calibrator, agreement_signal,
                         expected_calibration_error, reliability_table)


# ---------------------------------------------------- agreement signal
def test_signal_all_agree_and_majority():
    assert agreement_signal({"a": "X", "b": "X", "c": "X"}) == "all_agree"
    assert agreement_signal({"a": "X", "b": "X", "c": "Y"}) == "majority"


def test_signal_disagree_single_and_abstained():
    assert agreement_signal({"a": "X", "b": "Y"}) == "disagree"
    assert agreement_signal({"a": "X", "b": None}) == "single_source"
    assert agreement_signal({"a": None, "b": None}) == "abstained"


def test_signal_is_case_and_space_insensitive():
    assert agreement_signal({"a": " Ana Silva ",
                             "b": "ana silva"}) == "all_agree"


# --------------------------------------------------------- calibrator
def _records(n=200, seed=1):
    """Synthetic world: agreement really does predict correctness."""
    rng = random.Random(seed)
    truth = {"all_agree": 0.97, "majority": 0.80,
             "single_source": 0.60, "disagree": 0.25}
    out = []
    for _ in range(n):
        for f in ("event_date", "debtor"):
            sig = rng.choice(list(truth))
            out.append({"field": f, "signal": sig,
                        "correct": rng.random() < truth[sig]})
    return out


def test_confidence_is_monotone_in_agreement():
    c = Calibrator().fit(_records())
    t = c.table["event_date"]
    assert t["all_agree"] > t["majority"] > t["disagree"]


def test_abstained_is_zero_confidence():
    c = Calibrator().fit(_records())
    assert c.confidence("event_date", "abstained") == 0.0


def test_unseen_cell_falls_back_to_prior_not_optimism():
    c = Calibrator().fit(_records())
    conf = c.confidence("a_field_never_seen", "all_agree")
    assert conf == c.prior
    assert conf < 0.97          # does not inherit the optimistic cell


def test_smoothing_prevents_claiming_certainty():
    c = Calibrator().fit([{"field": "f", "signal": "all_agree",
                           "correct": True}] * 3)
    assert c.table["f"]["all_agree"] < 1.0    # never claims 1.00


def test_calibrated_beats_hardcoded_constant_on_ece():
    recs = _records(300, seed=2)
    cal, test = recs[:400], recs[400:]
    c = Calibrator().fit(cal)
    pairs = [(c.confidence(r["field"], r["signal"]), r["correct"])
             for r in test]
    ece_cal = expected_calibration_error(pairs)
    ece_flat = expected_calibration_error([(0.9, ok) for _, ok in pairs])
    assert ece_cal < ece_flat, (ece_cal, ece_flat)


# ------------------------------------------------ conformal threshold
def test_threshold_delivers_target_precision():
    recs = _records(400, seed=3)
    cal, test = recs[:500], recs[500:]
    c = Calibrator().fit(cal)
    tau = c.calibrate_threshold(cal, target_precision=0.90)
    kept = [r["correct"] for r in test
            if c.confidence(r["field"], r["signal"]) >= tau]
    assert kept, "threshold accepted nothing"
    precision = sum(kept) / len(kept)
    assert precision >= 0.85, precision   # holds on held-out data


def test_higher_target_is_stricter():
    recs = _records(400, seed=4)
    c = Calibrator().fit(recs)
    t90 = c.calibrate_threshold(recs, 0.90)
    t97 = c.calibrate_threshold(recs, 0.97)
    assert t97 >= t90


def test_unreachable_target_accepts_nothing():
    """If no confidence cell can clear the target on calibration data,
    the threshold must exclude everything rather than quietly settle
    for less. (Note: a small, lucky cell CAN legitimately hit 1.000 —
    so the target here is genuinely unreachable by construction.)"""
    recs = [{"field": "f", "signal": "disagree", "correct": i % 4 == 0}
            for i in range(80)]          # every cell ~25% correct
    c = Calibrator().fit(recs)
    tau = c.calibrate_threshold(recs, 0.99)
    assert tau > 1.0
    assert not c.accepts("f", "disagree")


# ------------------------------------------------------------ metrics
def test_ece_zero_for_perfect_calibration():
    pairs = [(1.0, True)] * 50 + [(0.0, False)] * 50
    assert expected_calibration_error(pairs) == 0.0


def test_reliability_table_shape():
    rows = reliability_table([(0.9, True), (0.9, True), (0.1, False)])
    assert all({"bin", "n", "claimed", "observed"} <= set(r)
               for r in rows)


def test_roundtrip_save_load(tmp_path):
    c = Calibrator().fit(_records())
    c.calibrate_threshold(_records(), 0.9)
    p = tmp_path / "cal.json"
    c.save(p)
    c2 = Calibrator.load(p)
    assert c2.tau == c.tau
    assert c2.confidence("event_date", "all_agree") == \
        c.confidence("event_date", "all_agree")
