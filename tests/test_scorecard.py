"""Phase 18 — the README's numbers are outputs, not claims.

The module's job is to FAIL when a published number stops being true.
So the tests mostly check that it can fail, and that it does not lie
about what it could not check.
"""

import json
from pathlib import Path

import pytest

import scorecard
from scorecard import Kind, claims, render, run


def test_it_fails_when_a_published_number_drifts(tmp_path,
                                                monkeypatch):
    """The whole point. Pin a claim the evidence no longer supports
    and CI must go red."""
    f = tmp_path / "claims.json"
    f.write_text(json.dumps({"probe": 1.0}))
    monkeypatch.setattr(scorecard, "CLAIMS_FILE", f)
    monkeypatch.setattr(scorecard, "claims", lambda: [
        scorecard.Claim("probe", "a probe", Kind.VERIFIED,
                        lambda: 0.5, tolerance=0.01)])
    results, failed = run()
    assert failed is True
    assert results[0].status == "DRIFT"
    assert "was 1.0, now 0.5" in results[0].detail
    assert "says something untrue" in render(results)


def test_a_drift_inside_tolerance_is_not_a_failure(tmp_path,
                                                   monkeypatch):
    """Float noise must not cry wolf: a scorecard that fails on
    rounding is a scorecard someone will disable."""
    f = tmp_path / "claims.json"
    f.write_text(json.dumps({"probe": 0.9000}))
    monkeypatch.setattr(scorecard, "CLAIMS_FILE", f)
    monkeypatch.setattr(scorecard, "claims", lambda: [
        scorecard.Claim("probe", "a probe", Kind.VERIFIED,
                        lambda: 0.9004, tolerance=0.005)])
    _, failed = run()
    assert failed is False


def test_missing_evidence_is_reported_not_invented(tmp_path,
                                                   monkeypatch):
    """A claim whose evidence is absent must say so. Silently passing
    would be the exact failure this module exists to prevent."""
    f = tmp_path / "claims.json"
    f.write_text(json.dumps({"probe": 0.9}))
    monkeypatch.setattr(scorecard, "CLAIMS_FILE", f)
    monkeypatch.setattr(scorecard, "claims", lambda: [
        scorecard.Claim("probe", "a probe", Kind.PINNED,
                        lambda: None, evidence="runs/nothing.jsonl")])
    results, failed = run()
    assert results[0].status == "missing"
    assert failed is False            # absent evidence is not a lie
    assert "no evidence" in results[0].detail


def test_a_computation_that_explodes_does_not_pass_silently(
        tmp_path, monkeypatch):
    def boom():
        raise ValueError("scorer changed shape")
    f = tmp_path / "claims.json"
    f.write_text("{}")
    monkeypatch.setattr(scorecard, "CLAIMS_FILE", f)
    monkeypatch.setattr(scorecard, "claims", lambda: [
        scorecard.Claim("probe", "a probe", Kind.VERIFIED, boom)])
    results, _ = run()
    assert results[0].status == "missing"
    assert "ValueError" in results[0].detail


def test_update_repins_every_claim(tmp_path, monkeypatch):
    f = tmp_path / "claims.json"
    f.write_text(json.dumps({"probe": 1.0}))
    monkeypatch.setattr(scorecard, "CLAIMS_FILE", f)
    monkeypatch.setattr(scorecard, "claims", lambda: [
        scorecard.Claim("probe", "a probe", Kind.VERIFIED,
                        lambda: 0.5, tolerance=0.001)])
    _, failed = run(update=True)
    assert failed is False
    assert json.loads(f.read_text())["probe"] == 0.5


# ---------------------------------------- the honesty of the taxonomy
def test_unverifiable_claims_are_named_never_quietly_passed():
    """An unverifiable claim is not a scandal. An unverifiable claim
    presented as verified is."""
    unver = [c for c in claims() if c.kind == Kind.UNVERIFIED]
    assert unver, "something is always out of CI's reach — say which"
    for c in unver:
        assert c.compute is None      # it cannot even pretend
        assert len(c.note) > 40       # and it explains itself


def test_the_kappa_claim_carries_its_own_caveat():
    """κ=0.615 was measured against the BROKEN judge. Publishing it
    beside a post-fix score without that caveat is exactly the sin
    this project keeps finding in other people's evaluations."""
    k = [c for c in claims() if c.key == "judge_kappa"][0]
    assert "PRE-FIX" in k.note.upper()
    assert "not as validation" in k.note.lower()
    post = [c for c in claims() if c.key == "judge_kappa_postfix"][0]
    assert post.kind == Kind.UNVERIFIED


def test_pinned_claims_admit_the_model_was_not_re_run():
    """Re-scoring a cache is not a live measurement. Calling it one
    would make the scorecard theatre."""
    tier0 = [c for c in claims() if c.key == "tier0_macro"][0]
    assert tier0.kind == Kind.PINNED
    assert "cached" in tier0.note.lower()
    assert "scorer" in tier0.note.lower()


def test_every_claim_points_at_its_evidence_or_explains_why_not():
    for c in claims():
        if c.kind == Kind.UNVERIFIED:
            assert c.note
        else:
            assert c.evidence or c.note, f"{c.key} cites nothing"


def test_the_deterministic_claims_are_verified_not_pinned():
    """Anything with no model in the loop must be recomputed for real
    — pinning it would hide a code regression behind a cache."""
    for key in ("deadline_cases_pt", "tier2_macro", "tests_total"):
        c = [x for x in claims() if x.key == key][0]
        assert c.kind == Kind.VERIFIED


def test_the_scorecard_calls_no_model_and_needs_no_key():
    import sys
    names = set(dir(sys.modules["scorecard"]))
    for forbidden in ("groq", "openai", "requests", "httpx"):
        assert forbidden not in names
