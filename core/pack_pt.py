"""Mandate — Jurisdiction Pack: Portugal (PT).

Encodes the three everyday Portuguese counting regimes, each with its
statutory basis, plus the national holiday calendar and férias
judiciais. Simplified, source-cited engineering implementation — not
legal advice; municipal holidays and special regimes (dilação,
justo impedimento, multa do art. 139.º CPC) are documented
limitations for the MVP.

Regimes:
  cc_corridos      — continuous calendar days (Código Civil art. 279.º):
                     event day excluded (al. b); term ending on a
                     SUNDAY or HOLIDAY rolls to the next working day
                     (al. e) — note: Saturdays do NOT roll under the CC.
  cpc_processual   — procedural deadline (CPC art. 138.º): continuous,
                     SUSPENDED during férias judiciais (unless urgent
                     or >= 6 months — urgency exposed as a flag; the
                     6-month exception is a documented limitation);
                     if the end falls when courts are closed
                     (Sat/Sun/holiday), rolls to the next working day
                     (art. 138.º/2).
  cpa_uteis        — administrative deadline in business days
                     (CPA art. 87.º): Saturdays, Sundays and holidays
                     do not count.

Férias judiciais (LOSJ art. 28.º):
  22 Dec – 3 Jan · Palm Sunday – Easter Monday · 16 Jul – 31 Aug.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Optional

import holidays as _hol
from dateutil.easter import easter

from engine import JurisdictionPack, Rule


@lru_cache(maxsize=8)
def _pt_holidays(year: int):
    return _hol.Portugal(years=[year])


def is_holiday(d: date) -> bool:
    return d in _pt_holidays(d.year)


def holiday_name(d: date) -> Optional[str]:
    return _pt_holidays(d.year).get(d)


def judicial_vacations(year: int) -> list[tuple[date, date, str]]:
    """LOSJ art. 28.º — the three férias judiciais windows for `year`.

    Note the Christmas window spans the year boundary: the window
    starting 22 Dec of `year` ends 3 Jan of `year`+1, and the window
    that started 22 Dec of `year`-1 covers 1–3 Jan of `year`.
    """
    e = easter(year)  # Easter Sunday
    palm_sunday = e - timedelta(days=7)
    easter_monday = e + timedelta(days=1)
    return [
        (date(year - 1, 12, 22), date(year, 1, 3),
         "férias judiciais (Natal, tail)"),
        (palm_sunday, easter_monday, "férias judiciais (Páscoa)"),
        (date(year, 7, 16), date(year, 8, 31),
         "férias judiciais (Verão)"),
        (date(year, 12, 22), date(year + 1, 1, 3),
         "férias judiciais (Natal)"),
    ]


PT = JurisdictionPack(
    id="PT",
    name="Portugal",
    is_holiday=is_holiday,
    holiday_name=holiday_name,
    judicial_vacations=judicial_vacations,
    rules={
        "cc_corridos": Rule(
            id="cc_corridos",
            name="Prazo civil contínuo (dias corridos)",
            legal_basis="Código Civil, art. 279.º (als. b, e)",
            count_business_days=False,
            suspend_in_judicial_vacations=False,
            roll_end_on=("sun", "holiday"),  # CC: Saturday does NOT roll
            start_day_excluded=True,
        ),
        "cpc_processual": Rule(
            id="cpc_processual",
            name="Prazo processual (CPC)",
            legal_basis=("CPC, art. 138.º (contínuo; suspensão em férias "
                         "judiciais; n.º 2 end-roll) + CC art. 279.º b) "
                         "+ LOSJ art. 28.º"),
            count_business_days=False,
            suspend_in_judicial_vacations=True,
            roll_end_on=("sat", "sun", "holiday"),
            start_day_excluded=True,
        ),
        "cpa_uteis": Rule(
            id="cpa_uteis",
            name="Prazo administrativo em dias úteis (CPA)",
            legal_basis="CPA, art. 87.º (c): dias úteis",
            count_business_days=True,
            suspend_in_judicial_vacations=False,
            roll_end_on=("sat", "sun", "holiday"),
            start_day_excluded=True,
        ),
    },
)
