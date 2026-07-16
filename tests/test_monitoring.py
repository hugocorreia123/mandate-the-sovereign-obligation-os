"""Phase 16 — the calendar comes looking for you.

The module's reason to exist, in one line: an alert measured in
calendar days lies about urgency, and the system already knows better.
"""

import json
from datetime import date

import pytest

from engine import days_remaining
from graph import (Claim, ClaimType, Deadline, Obligation,
                   ObligationGraph, ObligationStatus, ObligationType,
                   SourceSpan)
from monitoring import (Alert, EscalationPolicy, Level, Monitor,
                        render)
from pack_es import ES
from pack_eu import EU
from pack_pt import PT

PACKS = {"PT": PT, "EU": EU, "ES": ES}


@pytest.fixture()
def g(tmp_path):
    return ObligationGraph(tmp_path / "log.jsonl")


@pytest.fixture()
def mon():
    return Monitor(packs=PACKS)


def _obl(g, due, jur="PT", regime="cpc_processual", desc="contestação"):
    c = g.add_claim(Claim(type=ClaimType.OBLIGATION_TRIGGER,
                          value={"x": 1}, confidence=0.9,
                          source=SourceSpan(doc_id="d1")))
    o = g.create_obligation(Obligation(
        type=ObligationType.RESPOND, description=desc, debtor="X",
        creditor="Y", jurisdiction=jur, regime_id=regime,
        event_date=date(2026, 1, 5), claim_ids=[c.id]))
    g.attach_deadline(o.id, Deadline(
        due_date=due, regime=regime, jurisdiction=jur,
        legal_refs=["…"], steps=["…"]))
    return o


# ============ the reason this module exists ============
def test_a_calendar_overstates_the_time_you_actually_have(g, mon):
    """18 calendar days across férias judiciais is 9 that count. A
    calendar app tells you you have nearly three weeks. You do not."""
    o = _obl(g, date(2026, 4, 13))
    a = mon.assess(g, o.id, date(2026, 3, 26))
    assert a.calendar_days == 18
    assert a.legal_days == 9
    assert a.misleading_by == 9
    assert "overstates the time available by 9" in a.reason


def test_the_same_dates_are_urgent_or_calm_depending_on_the_regime(
        g, mon):
    """Identical dates. Spain. One has nine working days left, the
    other thirty — and a calendar shows 42 for both. One of them
    warrants an alert today; the other genuinely does not."""
    lec = _obl(g, date(2026, 9, 9), "ES", "lec_habiles", "procesal")
    lpac = _obl(g, date(2026, 9, 9), "ES", "lpac_habiles", "admin")
    today = date(2026, 7, 29)

    # the raw truth, straight from the engine
    assert days_remaining(ES, "lec_habiles", today,
                          date(2026, 9, 9)) == (42, 9)
    assert days_remaining(ES, "lpac_habiles", today,
                          date(2026, 9, 9)) == (42, 30)

    a_lec = mon.assess(g, lec.id, today)
    a_lpac = mon.assess(g, lpac.id, today)
    assert a_lec is not None            # 9 legal days -> speak
    assert a_lec.level is Level.NOTICE
    assert a_lec.calendar_days == 42 and a_lec.legal_days == 9
    assert a_lec.misleading_by == 33    # a calendar overstates by a month
    assert a_lpac is None               # 30 legal days -> stay quiet


def test_escalation_uses_legal_days_not_calendar_days(g, mon):
    """Across Easter, 12 calendar days is 7 that count under the CPA.
    The level must be decided by the 7 — a system that escalates on
    the 12 is measuring something the law does not use.

    (The expected numbers here were computed, not guessed: the first
    version of this test asserted <=5 because I estimated Easter's
    cost by eye and was wrong.)"""
    o = _obl(g, date(2026, 4, 8), "PT", "cpa_uteis")
    assert days_remaining(PT, "cpa_uteis", date(2026, 3, 27),
                          date(2026, 4, 8)) == (12, 7)
    a = mon.assess(g, o.id, date(2026, 3, 27))
    assert (a.calendar_days, a.legal_days) == (12, 7)
    assert a.misleading_by == 5
    assert a.level is Level.NOTICE      # 7 legal days, per the policy
    # and the same span, one day later, is a different world
    b = mon.assess(g, o.id, date(2026, 4, 2))
    assert b.legal_days < a.legal_days


# ============ levels ============
def test_levels_escalate_as_the_deadline_approaches(g, mon):
    o = _obl(g, date(2026, 2, 20), "PT", "cpa_uteis")
    seen = []
    for today in (date(2026, 2, 2), date(2026, 2, 11),
                  date(2026, 2, 16), date(2026, 2, 18),
                  date(2026, 2, 19)):
        a = mon.assess(g, o.id, today)
        seen.append(a.level if a else Level.OK)
    ranks = [list(Level).index(l) for l in seen]
    assert ranks == sorted(ranks)          # monotone, never regresses


def test_a_distant_deadline_is_silent(g, mon):
    o = _obl(g, date(2026, 12, 1))
    assert mon.assess(g, o.id, date(2026, 1, 6)) is None


def test_a_past_deadline_is_breached(g, mon):
    o = _obl(g, date(2026, 1, 10))
    a = mon.assess(g, o.id, date(2026, 1, 20))
    assert a.level is Level.BREACHED


# ============ what must never be escalated ============
def test_a_satisfied_obligation_is_never_chased(g, mon):
    o = _obl(g, date(2026, 1, 10))
    g.transition(o.id, ObligationStatus.IN_PROGRESS, "a")
    g.transition(o.id, ObligationStatus.AWAITING_APPROVAL, "a")
    g.transition(o.id, ObligationStatus.SATISFIED, "human")
    assert mon.assess(g, o.id, date(2026, 2, 1)) is None


def test_a_superseded_obligation_is_never_chased(g, mon):
    """Phase 12's whole point: an amendment killed this deadline. A
    system that keeps counting down to it teaches people to ignore
    alerts."""
    old = _obl(g, date(2026, 1, 10), desc="original")
    new = _obl(g, date(2026, 3, 10), desc="amended")
    g.supersede(new.id, old.id, actor="human", reason="prorrogação")
    assert mon.assess(g, old.id, date(2026, 2, 1)) is None
    assert mon.assess(g, new.id, date(2026, 3, 6)) is not None


def test_a_blocked_obligation_IS_chased_because_the_clock_runs(g, mon):
    """The law does not care that you are waiting on someone else."""
    from graph import Edge, EdgeType
    blocker = _obl(g, date(2026, 6, 1), desc="await ruling")
    dep = _obl(g, date(2026, 1, 12), desc="reply")
    g.add_edge(Edge(type=EdgeType.DEPENDS_ON, from_id=dep.id,
                    to_id=blocker.id))
    a = mon.assess(g, dep.id, date(2026, 1, 9))
    assert a is not None
    assert "the clock runs anyway" in a.reason


# ============ the sweep: fire once, log, breach ============
def test_each_level_fires_exactly_once(g, mon):
    """An alert that repeats is an alert that gets filtered — and a
    filtered channel will one day carry the real one."""
    o = _obl(g, date(2026, 1, 20), "PT", "cpa_uteis")
    first = mon.sweep(g, date(2026, 1, 15))
    assert first[0].new is True
    again = mon.sweep(g, date(2026, 1, 15))
    assert again[0].new is False          # same level, silent


def test_a_worsening_level_speaks_again(g, mon):
    o = _obl(g, date(2026, 1, 20), "PT", "cpa_uteis")
    mon.sweep(g, date(2026, 1, 8))
    later = mon.sweep(g, date(2026, 1, 19))
    assert later[0].new is True
    assert later[0].level is Level.CRITICAL


def test_fired_levels_survive_a_restart(g, mon, tmp_path):
    """Derived from the ledger, so a restart cannot resurrect
    yesterday's warning."""
    o = _obl(g, date(2026, 1, 20), "PT", "cpa_uteis")
    mon.sweep(g, date(2026, 1, 15))
    g2 = ObligationGraph(g.log_path)          # replay from disk
    again = Monitor(packs=PACKS).sweep(g2, date(2026, 1, 15))
    assert again[0].new is False


def test_a_breach_is_a_legal_event_not_a_colour(g, mon):
    o = _obl(g, date(2026, 1, 10))
    mon.sweep(g, date(2026, 1, 20))
    assert g.obligations[o.id].status is ObligationStatus.BREACHED
    events = [json.loads(l) for l in
              g.log_path.read_text(encoding="utf-8").splitlines()]
    assert any(e["type"] == "escalated"
               and e["payload"]["level"] == "breached" for e in events)
    assert g.verify_chain() is True


def test_a_breach_from_the_human_gate_steps_back_rather_than_raising(
        g, mon):
    o = _obl(g, date(2026, 1, 10))
    g.transition(o.id, ObligationStatus.IN_PROGRESS, "a")
    g.transition(o.id, ObligationStatus.AWAITING_APPROVAL, "a")
    mon.sweep(g, date(2026, 1, 20))        # must not raise
    assert g.obligations[o.id].status is ObligationStatus.BREACHED


def test_the_sweep_logs_the_legal_and_calendar_days(g, mon):
    o = _obl(g, date(2026, 4, 13))
    mon.sweep(g, date(2026, 3, 26))
    ev = [json.loads(l) for l in
          g.log_path.read_text(encoding="utf-8").splitlines()]
    esc = [e for e in ev if e["type"] == "escalated"][0]
    assert esc["payload"]["calendar_days"] == 18
    assert esc["payload"]["legal_days"] == 9


def test_alerts_are_ordered_worst_first(g, mon):
    _obl(g, date(2026, 1, 10), desc="breached")
    _obl(g, date(2026, 1, 14), desc="critical")
    _obl(g, date(2026, 1, 30), desc="notice")
    alerts = mon.sweep(g, date(2026, 1, 13))
    assert alerts[0].level is Level.BREACHED


def test_render_names_the_lie(g, mon):
    _obl(g, date(2026, 4, 13))
    out = render(mon.sweep(g, date(2026, 3, 26)))
    assert "overstate the time available" in out


def test_the_monitor_sends_nothing(mon):
    """Mandate surfaces; humans act — the same rule as the drafting
    gate. Nothing is mailed, posted or auto-escalated to a person who
    never asked.

    Asserted on IMPORTS, not on source text: the first version grepped
    the module for the word "webhook" and failed on its own docstring
    saying there wasn't one. A test a comment can break is testing
    prose, not behaviour.
    """
    import monitoring
    import sys
    mod = sys.modules["monitoring"]
    names = set(dir(mod))
    for forbidden in ("smtplib", "requests", "httpx", "socket",
                      "urllib"):
        assert forbidden not in names, \
            f"monitoring imported {forbidden} — it must not reach out"
    # and the module's own namespace holds no client object
    assert not [n for n in names
                if "client" in n.lower() or "session" in n.lower()]
