"""Mandate — EU jurisdiction pack (Reg. 1182/71): hand-verified tests.

Every expected date computed BY HAND against the cited articles.
2026 calendar: Easter Sunday = 5 Apr; Good Friday 3 Apr; Easter Monday
6 Apr; Ascension 14 May (Thu); Whit Monday 25 May; 1 May = Friday;
9 May (Europe Day) = Saturday.
"""

from datetime import date

from engine import compute_deadline
from pack_eu import EU, _eu_holidays


def due(regime, event, amount, unit="days"):
    return compute_deadline(EU, regime, event, amount, unit).due_date


# ---------------- holiday calendar sanity ----------------
def test_easter_based_holidays_2026():
    h = _eu_holidays(2026)
    assert h[date(2026, 4, 3)] == "Good Friday"
    assert h[date(2026, 4, 6)] == "Easter Monday"
    assert h[date(2026, 5, 14)] == "Ascension Day"
    assert h[date(2026, 5, 25)] == "Whit Monday"


# ---------------- days (art. 3(1),(2)(b),(3),(4)) ----------------
def test_days_simple():
    # event Mon 12 Jan; excluded; 13..22 Jan -> Thu 22 Jan
    assert due("eu_1182_days", date(2026, 1, 12), 10) == date(2026, 1, 22)


def test_days_end_saturday_rolls_monday():
    # art. 3(4): Saturday end -> next working day
    # event Wed 7 Jan + 10 -> Sat 17 Jan -> Mon 19 Jan
    assert due("eu_1182_days", date(2026, 1, 7), 10) == date(2026, 1, 19)


def test_days_end_on_holiday_rolls():
    # event Tue 21 Apr + 10 -> Fri 1 May (Labour Day) -> Mon 4 May
    assert due("eu_1182_days", date(2026, 4, 21), 10) == date(2026, 5, 4)


def test_days_count_through_easter_no_suspension():
    # art. 3(3): holidays COUNT (contrast with PT cpc_processual)
    # event Mon 30 Mar + 10 -> Thu 9 Apr (GF 3 Apr and EM 6 Apr counted)
    assert due("eu_1182_days", date(2026, 3, 30), 10) == date(2026, 4, 9)


# ---------------- working days (art. 2(2)) ----------------
def test_working_days_across_easter():
    # event Mon 30 Mar + 5 wd: 31 Mar, 1 Apr, 2 Apr, [GF+wknd+EM skip],
    # 7 Apr, 8 Apr -> Wed 8 Apr
    assert due("eu_1182_working_days", date(2026, 3, 30), 5) == \
        date(2026, 4, 8)


def test_working_days_across_whit_monday():
    # event Wed 20 May + 3 wd: 21, 22, [wknd + Whit Monday skip], 26
    assert due("eu_1182_working_days", date(2026, 5, 20), 3) == \
        date(2026, 5, 26)


# ---------------- weeks (art. 3(2)(c): same weekday) ----------------
def test_weeks_end_same_weekday():
    # event Tue 13 Jan + 2 weeks -> Tue 27 Jan
    assert due("eu_1182_days", date(2026, 1, 13), 2, "weeks") == \
        date(2026, 1, 27)


def test_weeks_end_roll_on_ascension():
    # event Thu 7 May + 1 week -> Thu 14 May (Ascension) -> Fri 15 May
    assert due("eu_1182_days", date(2026, 5, 7), 1, "weeks") == \
        date(2026, 5, 15)


# ---------------- months / years (art. 3(2)(c) + 3(4)) ----------------
def test_months_corresponding_date_rolls_sunday():
    # 15 Jan + 1 month -> Sun 15 Feb -> Mon 16 Feb
    assert due("eu_1182_days", date(2026, 1, 15), 1, "months") == \
        date(2026, 2, 16)


def test_months_clamp_and_saturday_roll():
    # 31 Jan + 1 month -> 28 Feb (no 31 Feb; month-end clamp),
    # Saturday -> Mon 2 Mar. Contrast: the PT Código Civil does NOT
    # roll Saturdays; Reg. 1182/71 art. 3(4) does.
    assert due("eu_1182_days", date(2026, 1, 31), 1, "months") == \
        date(2026, 3, 2)


def test_years_end_on_europe_day_saturday():
    # event 9 May 2025 + 1 year -> Sat 9 May 2026 (also Europe Day)
    # -> Mon 11 May 2026
    assert due("eu_1182_days", date(2025, 5, 9), 1, "years") == \
        date(2026, 5, 11)


# ---------------- explanation trace ----------------
def test_result_carries_refs_and_trace():
    r = compute_deadline(EU, "eu_1182_days", date(2026, 4, 21), 10)
    assert r.due_date == date(2026, 5, 4)
    assert any("1182/71" in ref for ref in r.legal_refs)
    assert r.steps[-1].startswith("DUE:")
