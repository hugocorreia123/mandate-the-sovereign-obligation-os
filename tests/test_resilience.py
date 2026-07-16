"""Phase 14 — pull the cable.

The project has claimed since the pitch that an outage is a quality
dial rather than a failure. This is where that claim gets exercised on
demand — because a resilience story you cannot trigger is a resilience
story you do not have.
"""

import json
from datetime import date

import pytest

from engine import compute_deadline
from graph import (Claim, ClaimType, ObligationGraph, SourceSpan)
from pack_pt import PT
from resilience import (LADDER, TierRouter, pull_the_cable, restore)


def router(**up):
    """A router whose rungs are up/down exactly as asked."""
    return TierRouter(probes={t: (lambda v=up.get(t, True): v)
                              for t in LADDER})


# ------------------------------------------------------- the ladder
def test_it_takes_the_best_rung_that_is_actually_up():
    r = router()
    assert r.route("tier0").tier == "tier0"
    assert r.route("tier0").degraded is False


def test_it_degrades_one_rung_when_the_cloud_is_out():
    r = router(tier0=False)
    out = r.route("tier0")
    assert out.tier == "tier1"
    assert out.degraded is True
    assert "degraded to" in out.reason


def test_it_keeps_falling_until_something_answers():
    r = router(tier0=False, tier1=False)
    assert r.route("tier0").tier == "tier2"


def test_the_floor_is_a_human_and_it_never_raises():
    """THE architectural guarantee: with every automated tier down the
    answer is still an answer. No obligation is lost, only unassisted."""
    r = router(tier0=False, tier1=False, tier2=False)
    out = r.route("tier0")
    assert out.tier == "tier3"
    assert "no obligation is lost" in out.reason


def test_asking_for_a_lower_rung_does_not_climb_back_up():
    """A caller who asks for Rules-only gets Rules-only, even with the
    cloud available — sovereignty is a choice, not a fallback."""
    r = router()
    assert r.route("tier2").tier == "tier2"
    assert r.route("tier2").degraded is False


def test_ladder_order_lives_in_one_place():
    assert LADDER == ("tier0", "tier1", "tier2")


# ------------------------------------------------ pull the cable
def test_pulling_the_cable_demotes_and_restoring_recovers():
    r = router()
    assert r.route("tier0").tier == "tier0"
    pull_the_cable(r, "tier0")
    assert r.route("tier0").tier == "tier1"
    restore(r)
    assert r.route("tier0").tier == "tier0"


def test_restore_can_bring_back_one_rung_at_a_time():
    r = router()
    pull_the_cable(r, "tier0")
    pull_the_cable(r, "tier1")
    assert r.route("tier0").tier == "tier2"
    restore(r, "tier1")
    assert r.route("tier0").tier == "tier1"


# ------------------------------- the auditable part (DORA)
def test_a_degradation_is_written_to_the_hash_chained_ledger(tmp_path):
    """An outage that leaves no trace is an outage you cannot report."""
    g = ObligationGraph(tmp_path / "log.jsonl")
    r = router(tier0=False)
    r.graph = g
    r.route("tier0", actor="agent:pipeline")

    events = [json.loads(l) for l in
              g.log_path.read_text(encoding="utf-8").splitlines()]
    deg = [e for e in events if e["type"] == "tier_degraded"]
    assert len(deg) == 1
    assert deg[0]["payload"]["requested"] == "tier0"
    assert deg[0]["payload"]["actual"] == "tier1"
    assert "unavailable" in deg[0]["payload"]["reason"]
    assert deg[0]["payload"]["ladder_status"]["tier0"] is False
    assert g.verify_chain() is True


def test_a_healthy_route_is_not_logged_as_an_incident(tmp_path):
    """Only degradations are events. Logging every success would bury
    the one line a regulator came to read."""
    g = ObligationGraph(tmp_path / "log.jsonl")
    r = router()
    r.graph = g
    r.route("tier0")
    assert not g.log_path.exists() or "tier_degraded" not in \
        g.log_path.read_text(encoding="utf-8")


def test_the_outage_sits_in_the_record_beside_the_work_it_affected(
        tmp_path):
    g = ObligationGraph(tmp_path / "log.jsonl")
    g.add_claim(Claim(type=ClaimType.DATE, value={"d": "2026-03-23"},
                      confidence=0.9, source=SourceSpan(doc_id="d1")))
    r = router(tier0=False)
    r.graph = g
    r.route("tier0", actor="agent:pipeline")

    types = [json.loads(l)["type"] for l in
             g.log_path.read_text(encoding="utf-8").splitlines()]
    assert types == ["claim_added", "tier_degraded"]
    assert g.verify_chain() is True


def test_logging_failure_never_breaks_routing():
    """A broken ledger must not take the system down with it: the
    routing decision matters more than the record of it."""
    class Exploding:
        def _append_event(self, *a, **k):
            raise RuntimeError("disk on fire")
    r = router(tier0=False)
    r.graph = Exploding()
    assert r.route("tier0").tier == "tier1"      # still routed


# --------------------------------------------- THE THESIS, asserted
def test_the_deadline_still_computes_with_every_ai_tier_down():
    """The claim the whole architecture rests on, as a test.

    The engine is not a rung on the ladder. It is the ground the
    ladder stands on — so pulling every cable changes what READS the
    document, and changes nothing about what the law says.
    """
    r = router(tier0=False, tier1=False, tier2=False)
    assert r.route("tier0").tier == "tier3"     # only humans left

    result = compute_deadline(PT, "cpc_processual", date(2026, 3, 23),
                              10)
    assert result.due_date == date(2026, 4, 13)   # unchanged, always
    assert "138" in result.legal_refs[0]
    assert result.steps[-1].startswith("DUE:")


def test_the_computed_date_is_identical_at_every_rung():
    """Degradation costs completeness, never correctness — the
    deadline does not care which model read the page."""
    dates = set()
    for combo in ({}, {"tier0": False}, {"tier0": False,
                                         "tier1": False}):
        r = router(**combo)
        r.route("tier0")          # whatever it routes to…
        dates.add(compute_deadline(PT, "cpc_processual",
                                   date(2026, 3, 23), 10).due_date)
    assert dates == {date(2026, 4, 13)}       # …the law is the law
