"""Mandate — PT jurisdiction pack: hand-verified deadline tests.

Every expected date below was computed BY HAND against the cited
rules (2026 calendar; Easter Sunday 2026 = April 5). These tests are
the pack's certificate: the engine must score 20/20, forever.

PT 2026 national holidays used in cases: 1 Jan (Ano Novo),
3 Apr (Sexta-feira Santa), 5 Apr (Páscoa), 25 Apr, 1 May (Friday),
10 Jun (Wednesday), 4 Jun (Corpo de Deus), 15 Aug (Saturday),
5 Oct (Monday), 1 Nov (Sunday), 1 Dec (Tuesday), 8 Dec (Tuesday),
25 Dec (Friday).
Férias judiciais 2026: 22 Dec 2025–3 Jan 2026;
Palm Sunday 29 Mar – Easter Monday 6 Apr; 16 Jul–31 Aug;
22 Dec 2026–3 Jan 2027.
"""

from datetime import date

import pytest

from engine import compute_deadline
from pack_pt import PT, judicial_vacations


def due(regime, event, amount, unit="days", urgent=False):
    return compute_deadline(PT, regime, event, amount, unit,
                            urgent=urgent).due_date


# ---------------- férias judiciais sanity ----------------
def test_pascoa_window_2026():
    vacs = judicial_vacations(2026)
    labels = {v[2]: (v[0], v[1]) for v in vacs}
    a, b = labels["férias judiciais (Páscoa)"]
    assert a == date(2026, 3, 29)   # Palm Sunday
    assert b == date(2026, 4, 6)    # Easter Monday


# ---------------- cc_corridos (CC art. 279.º) ----------------
def test_cc_simple_10_days():
    # event Mon 5 Jan; day excluded -> count 6..15 Jan; 15 Jan = Thursday
    assert due("cc_corridos", date(2026, 1, 5), 10) == date(2026, 1, 15)


def test_cc_end_on_saturday_does_not_roll():
    # CC 279.º e) rolls Sundays/holidays only; Saturday stands.
    # event Wed 7 Jan + 10 -> 17 Jan (Saturday) — stays.
    assert due("cc_corridos", date(2026, 1, 7), 10) == date(2026, 1, 17)


def test_cc_end_on_sunday_rolls_monday():
    # event Thu 8 Jan + 10 -> 18 Jan (Sunday) -> Mon 19 Jan
    assert due("cc_corridos", date(2026, 1, 8), 10) == date(2026, 1, 19)


def test_cc_end_on_holiday_rolls():
    # event 22 May + 10 -> 1 Jun?? no: 1 Jun 2026 is Monday, not holiday.
    # Use 10 Jun (Wed, Dia de Portugal): event 31 May + 10 -> 10 Jun
    # (holiday) -> 11 Jun (Thu).
    assert due("cc_corridos", date(2026, 5, 31), 10) == date(2026, 6, 11)


def test_cc_no_vacation_suspension():
    # crosses summer férias but CC does not suspend:
    # event 10 Jul + 10 -> 20 Jul (Monday), counted straight through.
    assert due("cc_corridos", date(2026, 7, 10), 10) == date(2026, 7, 20)


def test_cc_months_corresponding_day():
    # 15 Jan + 1 month -> 15 Feb (Sunday) -> rolls Mon 16 Feb (CC e)
    assert due("cc_corridos", date(2026, 1, 15), 1, "months") == \
        date(2026, 2, 16)


def test_cc_months_month_end_clamp():
    # 31 Jan + 1 month -> 28 Feb 2026 (Saturday) — CC does not roll Sat.
    assert due("cc_corridos", date(2026, 1, 31), 1, "months") == \
        date(2026, 2, 28)


def test_cc_years():
    # 5 Mar 2026 + 1 year -> 5 Mar 2027 (Friday)
    assert due("cc_corridos", date(2026, 3, 5), 1, "years") == \
        date(2027, 3, 5)


# ---------------- cpc_processual (CPC art. 138.º) ----------------
def test_cpc_simple_no_vacation():
    # event Mon 12 Jan + 10 continuous -> 22 Jan (Thursday)
    assert due("cpc_processual", date(2026, 1, 12), 10) == \
        date(2026, 1, 22)


def test_cpc_end_on_saturday_rolls_monday():
    # courts closed Saturdays: event Wed 7 Jan + 10 -> 17 Jan (Sat)
    # -> Mon 19 Jan
    assert due("cpc_processual", date(2026, 1, 7), 10) == \
        date(2026, 1, 19)


def test_cpc_suspends_over_easter_vacation():
    # event Mon 23 Mar; counting starts 24 Mar; days 24..28 Mar = 5;
    # 29 Mar-6 Apr suspended (Páscoa); resume 7 Apr..11 Apr = days 6..10
    # -> 11 Apr (Saturday) -> rolls Mon 13 Apr
    assert due("cpc_processual", date(2026, 3, 23), 10) == \
        date(2026, 4, 13)


def test_cpc_urgent_ignores_vacation():
    # same event, urgent: 10 continuous days -> 2 Apr (Thursday);
    # 3 Apr = Sexta-feira Santa (holiday) not relevant (end is 2 Apr)
    assert due("cpc_processual", date(2026, 3, 23), 10, urgent=True) == \
        date(2026, 4, 2)


def test_cpc_event_inside_vacation_starts_after():
    # event 20 Jul (inside summer férias 16 Jul-31 Aug): suspended days
    # don't count; first counted day is 1 Sep; 10 days -> 10 Sep (Thu)
    assert due("cpc_processual", date(2026, 7, 20), 10) == \
        date(2026, 9, 10)


def test_cpc_christmas_tail_january_event():
    # event Fri 2 Jan 2026: 1-3 Jan still férias (window from 22 Dec
    # 2025); counting starts 4 Jan; 10 days -> 13 Jan (Tuesday)
    assert due("cpc_processual", date(2026, 1, 2), 10) == \
        date(2026, 1, 13)


def test_cpc_30_days_over_summer():
    # event 1 Jul; counted 2..15 Jul = 14 days; 16 Jul-31 Aug suspended;
    # resume 1 Sep, need 16 more -> 16 Sep (Wednesday)
    assert due("cpc_processual", date(2026, 7, 1), 30) == \
        date(2026, 9, 16)


# ---------------- cpa_uteis (CPA art. 87.º) ----------------
def test_cpa_10_business_days():
    # event Mon 12 Jan; start Tue 13; 10 úteis: 13,14,15,16,19,20,21,
    # 22,23,26 -> 26 Jan (Monday)
    assert due("cpa_uteis", date(2026, 1, 12), 10) == date(2026, 1, 26)


def test_cpa_skips_holiday():
    # event Wed 27 May; start Thu 28 May; úteis: 28,29 May, 1,2,3 Jun,
    # (4 Jun Corpo de Deus skipped), 5,8,9, (10 Jun holiday skipped),
    # 11,12 -> 10th útil = 12 Jun (Friday)
    assert due("cpa_uteis", date(2026, 5, 27), 10) == date(2026, 6, 12)


def test_cpa_5_days_over_weekend():
    # event Thu 8 Jan; start Fri 9; úteis: 9,12,13,14,15 -> 15 Jan (Thu)
    assert due("cpa_uteis", date(2026, 1, 8), 5) == date(2026, 1, 15)


def test_cpa_august_not_suspended():
    # CPA has no férias judiciais: event Mon 3 Aug; start Tue 4;
    # úteis: 4,5,6,7,10,11,12,13,14,17 (15 Aug is Saturday anyway)
    # -> 17 Aug (Monday)
    assert due("cpa_uteis", date(2026, 8, 3), 10) == date(2026, 8, 17)


# ---------------- explanation trace ----------------
def test_result_carries_explanation_and_refs():
    r = compute_deadline(PT, "cpc_processual", date(2026, 3, 23), 10)
    assert r.due_date == date(2026, 4, 13)
    assert any("suspended" in s or "férias" in s.lower()
               for s in r.steps)
    assert any("138" in ref for ref in r.legal_refs)
    assert r.steps[-1].startswith("DUE:")
