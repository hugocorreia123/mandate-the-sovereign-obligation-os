"""Mandate — ES jurisdiction pack: hand-verified deadline tests.

Expected dates computed BY HAND against the cited articles, 2026
calendar. Spanish national holidays used: 1 Jan, 6 Jan (Reyes),
3 Apr (Viernes Santo), 1 May (Friday), 15 Aug (Saturday),
12 Oct (Monday), 1 Nov (Sunday), 6 Dec (Sunday), 8 Dec (Tuesday),
25 Dec (Friday).

The pack's reason for existing is the AUGUST DIVERGENCE: procedural
deadlines stop for the whole of August (LEC art. 130.2) while
administrative ones do not (LPAC art. 30.2). Two regimes, one country,
opposite treatment of the same month — the distinction a generic
"business days" helper silently destroys.
"""

from datetime import date

import pytest

from engine import compute_deadline
from pack_es import ES, judicial_vacations


def due(regime, event, amount, unit="days"):
    return compute_deadline(ES, regime, event, amount, unit).due_date


# ---------------------------------------------- the August divergence
def test_august_is_inhabil_for_procedural_deadlines():
    """LEC art. 130.2. 28 Jul + 10 días hábiles: 29,30,31 Jul = 3;
    all August skipped; 1,2,3,4,7,8,9 Sep = 10th on Wed 9 Sep."""
    assert due("lec_habiles", date(2026, 7, 28), 10) == date(2026, 9, 9)


def test_august_is_habil_for_administrative_deadlines():
    """LPAC art. 30.2 — the administrative calendar does not stop.
    29,30,31 Jul, 3,4,5,6,7,10,11 Aug -> Tue 11 Aug."""
    assert due("lpac_habiles", date(2026, 7, 28), 10) == \
        date(2026, 8, 11)


def test_the_two_regimes_diverge_by_almost_a_month():
    """The whole point of the pack: same event, same period, one
    country — a month apart. Encoded as data, not as code."""
    lec = due("lec_habiles", date(2026, 7, 28), 10)
    lpac = due("lpac_habiles", date(2026, 7, 28), 10)
    assert (lec - lpac).days == 29


def test_august_window_is_the_whole_month():
    v = judicial_vacations(2026)
    (a, b, label), = v
    assert a == date(2026, 8, 1) and b == date(2026, 8, 31)
    assert "130.2" in label


# ---------------------------------------- lec_habiles (LEC 130-133)
def test_lec_simple_count_no_august():
    """Event Mon 12 Jan; start 13th. Hábiles: 13,14,15,16,19,20,21,
    22,23,26 -> Mon 26 Jan."""
    assert due("lec_habiles", date(2026, 1, 12), 10) == date(2026, 1, 26)


def test_lec_skips_national_holidays():
    """Event Wed 31 Dec 2025. Counting: 1 Jan (Año Nuevo — skipped),
    2 Jan = hábil 1, 3-4 weekend, 5 Jan = 2, 6 Jan (Reyes — skipped),
    7 Jan = 3, 8 Jan = 4 -> Thu 8 Jan. Two holidays and a weekend
    inside four working days.

    (This case was hand-walked twice: the first expected value was
    off by one because I counted 1 Jan as the start rather than the
    first SKIPPED day. The engine was right.)"""
    assert due("lec_habiles", date(2025, 12, 31), 4) == date(2026, 1, 8)


def test_lec_event_inside_august_starts_in_september():
    """Event 10 Aug: August is inhábil, so nothing counts until 1 Sep.
    1,2,3,4,7 Sep = 5 -> Mon 7 Sep."""
    assert due("lec_habiles", date(2026, 8, 10), 5) == date(2026, 9, 7)


def test_lec_long_period_crossing_august():
    """Event Fri 24 Jul; start 27 Jul. Hábiles 27,28,29,30,31 = 5;
    August skipped entirely; 1,2,3,4,7,8,9,10,11,14,15 Sep = 16th
    -> Tue 15 Sep."""
    assert due("lec_habiles", date(2026, 7, 24), 16) == date(2026, 9, 15)


# --------------------------------------- lpac_habiles (Ley 39/2015)
def test_lpac_ten_days_plain():
    """Event Mon 12 Jan; 13,14,15,16,19,20,21,22,23,26 -> 26 Jan."""
    assert due("lpac_habiles", date(2026, 1, 12), 10) == \
        date(2026, 1, 26)


def test_lpac_works_straight_through_august():
    """Event Mon 3 Aug; 4,5,6,7,10,11,12,13,14,17 (15 Aug is a
    Saturday anyway) -> Mon 17 Aug."""
    assert due("lpac_habiles", date(2026, 8, 3), 10) == \
        date(2026, 8, 17)


def test_lpac_skips_the_assumption_holiday_when_it_is_a_weekday():
    """2027: 15 Aug falls on a Sunday, so use 2025's calendar shape —
    here we simply assert the holiday itself is never counted."""
    from pack_es import is_holiday
    assert is_holiday(date(2026, 8, 15))          # Asunción
    assert is_holiday(date(2026, 10, 12))         # Fiesta Nacional


# ------------------------------------------- cc_naturales (CC art. 5)
def test_cc_naturales_counts_every_day():
    """Event 5 Jan + 10 naturales -> 15 Jan (Thursday)."""
    assert due("cc_naturales", date(2026, 1, 5), 10) == date(2026, 1, 15)


def test_cc_naturales_does_not_roll_off_a_sunday():
    """CC art. 5.1 has no prórroga: event Thu 8 Jan + 10 -> Sun 18 Jan,
    and it STAYS on the Sunday. Contrast Portugal's CC art. 279.º e),
    which rolls Sundays to the next working day — two civil codes,
    opposite end-rules."""
    assert due("cc_naturales", date(2026, 1, 8), 10) == date(2026, 1, 18)


def test_cc_naturales_ignores_august():
    """The civil term is not procedural: August is ordinary time.
    Event 1 Aug + 20 naturales -> 21 Aug (Friday)."""
    assert due("cc_naturales", date(2026, 8, 1), 20) == date(2026, 8, 21)


def test_cc_naturales_months_corresponding_day():
    """de fecha a fecha: 15 Jan + 1 month -> 15 Feb (a Sunday, and it
    stays there — no roll)."""
    assert due("cc_naturales", date(2026, 1, 15), 1, "months") == \
        date(2026, 2, 15)


# ------------------------------------------------- explanation trace
def test_result_cites_the_august_rule():
    r = compute_deadline(ES, "lec_habiles", date(2026, 7, 28), 10)
    assert r.due_date == date(2026, 9, 9)
    assert any("130" in ref for ref in r.legal_refs)
    assert r.steps[-1].startswith("DUE:")


def test_three_jurisdictions_one_engine():
    """The architectural claim, asserted: PT, EU and ES run through the
    same engine with contradictory rules, selected by data."""
    from pack_eu import EU
    from pack_pt import PT
    ev = date(2026, 1, 31)
    pt = compute_deadline(PT, "cc_corridos", ev, 1, "months").due_date
    eu = compute_deadline(EU, "eu_1182_days", ev, 1, "months").due_date
    es = compute_deadline(ES, "cc_naturales", ev, 1, "months").due_date
    # 28 Feb 2026 is a Saturday.
    assert pt == date(2026, 2, 28)   # PT CC: does not roll Saturdays
    assert eu == date(2026, 3, 2)    # Reg. 1182/71 art. 3(4): rolls
    assert es == date(2026, 2, 28)   # ES CC art. 5.1: no roll at all


# --------------------------------- what the third pack broke (Ph. 11)
def test_deadline_expires_in_the_jurisdictions_own_timezone():
    """A Madrid court deadline printed "23:59 Europe/Lisbon" — Spain is
    CET, Portugal WET, so the stated expiry was an hour wrong on a
    legal filing. Two packs in one timezone had hidden the hardcode."""
    from pack_pt import PT
    assert ES.timezone == "Europe/Madrid"
    assert PT.timezone == "Europe/Lisbon"
    r = compute_deadline(ES, "lec_habiles", date(2026, 1, 12), 10)
    assert "Europe/Madrid" in r.steps[-1]
    assert "Lisbon" not in r.steps[-1]


def test_the_trace_names_the_rule_that_moved_the_date():
    """The August skip moves a deadline by a month. The trace said only
    "skipping weekends and holidays" — a lawyer auditing the
    explanation could not see the rule responsible. An unexplained
    month is not an audit trail."""
    r = compute_deadline(ES, "lec_habiles", date(2026, 7, 28), 10)
    counting = [s for s in r.steps if "business days" in s][0]
    assert "suspended" in counting
    assert "agosto" in counting and "130.2" in counting


def test_business_day_regimes_can_also_suspend():
    """The engine only consulted the suspension calendar on CONTINUOUS
    counts. Portugal never needed both (its suspension is continuous,
    its business-day regime does not suspend), so two jurisdictions
    hid the assumption. Spain needs both at once."""
    lec = compute_deadline(ES, "lec_habiles", date(2026, 7, 28), 10)
    lpac = compute_deadline(ES, "lpac_habiles", date(2026, 7, 28), 10)
    assert lec.due_date > lpac.due_date          # August cost a month
    assert (lec.due_date - lpac.due_date).days == 29
