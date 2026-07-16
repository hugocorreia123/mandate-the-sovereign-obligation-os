"""Mandate — Jurisdiction Pack: Spain (ES).

The third pack, and the one that tests whether the architecture was a
two-jurisdiction coincidence. It is not: Spain needs a rule Portugal
and the EU do not have, and the engine absorbs it as data.

Regimes:
  lec_habiles      — procedural deadline in DÍAS HÁBILES
                     (LEC art. 130-133). Saturdays, Sundays, national
                     holidays and — the trap — the WHOLE OF AUGUST are
                     inhábiles for procedural purposes (LEC art. 130.2).
                     Structurally similar to the Portuguese férias
                     judiciais, but a fixed calendar month rather than
                     an Easter-derived window: the same mechanism, a
                     different rule, expressed as data.
  lpac_habiles     — administrative deadline in días hábiles
                     (Ley 39/2015, art. 30.2). Saturdays, Sundays and
                     holidays excluded — but August COUNTS: the
                     administrative calendar does not stop in August.
                     Two Spanish regimes, opposite August treatment.
                     This is exactly the kind of distinction a single
                     "business days" helper silently destroys.
  cc_naturales     — civil term in días naturales (Código Civil
                     art. 5.1): every day counts, the event day is
                     excluded, and there is NO end-roll — a term
                     ending on a Sunday ends on that Sunday.

Holiday calendar: the national set (the `holidays` package). Spain's
autonomous communities and municipalities add their own, which change
the count; that is a documented limitation, as in the PT pack.

Documented limitations (MVP): autonomous/local holidays; the
24-31 December judicial closure (LOPJ art. 183 as amended);
habilitación de días inhábiles (LEC art. 131); the 20-day dilación
rules; plazos de meses under LEC art. 133.3 (de fecha a fecha), which
the engine's month unit approximates.

Simplified, source-cited engineering implementation — not legal advice.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Optional

import holidays as _hol

from engine import JurisdictionPack, Rule


@lru_cache(maxsize=8)
def _es_holidays(year: int):
    return _hol.Spain(years=[year])


def is_holiday(d: date) -> bool:
    return d in _es_holidays(d.year)


def holiday_name(d: date) -> Optional[str]:
    return _es_holidays(d.year).get(d)


def judicial_vacations(year: int) -> list[tuple[date, date, str]]:
    """LEC art. 130.2 — August is inhábil for procedural deadlines.

    Note what this is NOT: it is not Portugal's férias judiciais. It is
    a fixed calendar month, needs no Easter algorithm, and it applies
    to procedural time limits only — the administrative regime below
    ignores it entirely.
    """
    return [(date(year, 8, 1), date(year, 8, 31),
             "mes de agosto inhábil (LEC art. 130.2)")]


ES = JurisdictionPack(
    id="ES",
    name="España",
    timezone="Europe/Madrid",
    is_holiday=is_holiday,
    holiday_name=holiday_name,
    judicial_vacations=judicial_vacations,
    rules={
        "lec_habiles": Rule(
            id="lec_habiles",
            name="Plazo procesal en días hábiles (LEC)",
            legal_basis=("LEC, arts. 130-133: días hábiles; agosto "
                         "inhábil (art. 130.2); cómputo desde el día "
                         "siguiente (art. 133.1)"),
            count_business_days=True,          # Sat/Sun/holidays skipped
            suspend_in_judicial_vacations=True,  # + all of August
            roll_end_on=("sat", "sun", "holiday"),
            start_day_excluded=True,
        ),
        "lpac_habiles": Rule(
            id="lpac_habiles",
            name="Plazo administrativo en días hábiles (LPAC)",
            legal_basis=("Ley 39/2015 (LPAC), art. 30.2: días hábiles, "
                         "excluidos sábados, domingos y festivos; "
                         "agosto SÍ es hábil en vía administrativa"),
            count_business_days=True,
            suspend_in_judicial_vacations=False,   # August counts here
            roll_end_on=("sat", "sun", "holiday"),
            start_day_excluded=True,
        ),
        "cc_naturales": Rule(
            id="cc_naturales",
            name="Plazo civil en días naturales (CC)",
            legal_basis=("Código Civil, art. 5.1: cómputo de fecha a "
                         "fecha, excluido el día inicial; sin prórroga "
                         "por día inhábil"),
            count_business_days=False,
            suspend_in_judicial_vacations=False,
            roll_end_on=(),          # no end-roll: a Sunday is the end
            start_day_excluded=True,
        ),
    },
)
