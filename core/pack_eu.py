"""Mandate — Jurisdiction Pack: European Union (Regulation 1182/71).

Encodes the counting rules of Regulation (EEC, Euratom) No 1182/71,
which governs periods, dates and time limits in EU acts — the rules
behind every "within 30 days" in an EU regulation.

Regimes:
  eu_1182_days          — continuous days (art. 3(1): event day
                          excluded; art. 3(3): Saturdays, Sundays and
                          public holidays COUNT; art. 3(4): a period
                          ending on a Saturday, Sunday or public
                          holiday extends to the end of the following
                          working day).
  eu_1182_working_days  — working-day periods (art. 2(2): working days
                          = all days except public holidays, Saturdays
                          and Sundays).
  weeks / months / years — art. 3(2)(c): the period ends on the day of
                          the last week/month/year that is the same
                          weekday / same date as the event day; if the
                          date does not exist in the final month, the
                          period ends on that month's last day. The
                          art. 3(4) end-roll applies.

Holiday calendar: the EU-institution core set — 1 Jan, Good Friday,
Easter Monday, 1 May, 9 May (Europe Day), Ascension, Whit Monday,
25–26 Dec. Documented limitation: the institutions' full list is
published annually in the Official Journal and includes additional
closure days; deadlines addressed to a Member State authority use that
state's own holidays (use the national pack). Art. 3(5) (a period of
two days or more must include at least two working days) is a
documented limitation for the MVP.

Simplified, source-cited engineering implementation — not legal advice.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Optional

from dateutil.easter import easter

from engine import JurisdictionPack, Rule


@lru_cache(maxsize=16)
def _eu_holidays(year: int) -> dict[date, str]:
    e = easter(year)
    return {
        date(year, 1, 1): "New Year's Day",
        e - timedelta(days=2): "Good Friday",
        e + timedelta(days=1): "Easter Monday",
        date(year, 5, 1): "Labour Day",
        date(year, 5, 9): "Europe Day",
        e + timedelta(days=39): "Ascension Day",
        e + timedelta(days=50): "Whit Monday",
        date(year, 12, 25): "Christmas Day",
        date(year, 12, 26): "Second day of Christmas",
    }


def is_holiday(d: date) -> bool:
    return d in _eu_holidays(d.year)


def holiday_name(d: date) -> Optional[str]:
    return _eu_holidays(d.year).get(d)


def judicial_vacations(year: int) -> list[tuple[date, date, str]]:
    """No judicial-vacation suspension exists under Reg. 1182/71."""
    return []


EU = JurisdictionPack(
    id="EU",
    name="European Union (Reg. 1182/71)",
    timezone="Europe/Brussels",
    is_holiday=is_holiday,
    holiday_name=holiday_name,
    judicial_vacations=judicial_vacations,
    rules={
        "eu_1182_days": Rule(
            id="eu_1182_days",
            name="EU period in days (Reg. 1182/71)",
            legal_basis=("Reg. (EEC, Euratom) 1182/71, art. 3(1) "
                         "event-day exclusion; 3(2)(b); 3(3) holidays "
                         "count; 3(4) end-roll to next working day"),
            count_business_days=False,
            suspend_in_judicial_vacations=False,
            roll_end_on=("sat", "sun", "holiday"),
            start_day_excluded=True,
        ),
        "eu_1182_working_days": Rule(
            id="eu_1182_working_days",
            name="EU period in working days (Reg. 1182/71)",
            legal_basis=("Reg. (EEC, Euratom) 1182/71, art. 2(2) "
                         "working days; art. 3(1) event-day exclusion"),
            count_business_days=True,
            suspend_in_judicial_vacations=False,
            roll_end_on=("sat", "sun", "holiday"),
            start_day_excluded=True,
        ),
    },
)
