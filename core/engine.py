"""Mandate — Deadline Engine (deterministic core).

Computes legal deadlines under pluggable jurisdiction packs. This
module is deliberately LLM-free: agents PROPOSE (event date, duration,
regime); this engine COMPUTES. Every result carries a step-by-step
explanation trace with legal references — the auditable evidence
chain.

Supported counting regimes (regime ids are pack-defined; the PT pack
ships three):
  - continuous calendar days (with optional end-roll rules)
  - business days (dias úteis)
  - continuous days with judicial-vacation suspension (prazo
    processual)
  - calendar months/years (corresponding-day rule with month-end
    clamp)

DISCLAIMER: encoded rules are a simplified, source-cited engineering
implementation for research/portfolio purposes — not legal advice.
Every rule cites its statutory basis so a lawyer can audit it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Literal, Optional

from dateutil.relativedelta import relativedelta

Unit = Literal["days", "weeks", "months", "years"]


@dataclass
class Rule:
    """A counting regime inside a jurisdiction pack."""
    id: str
    name: str
    legal_basis: str
    count_business_days: bool = False
    suspend_in_judicial_vacations: bool = False
    # end-roll: which non-working end days push to next business day
    roll_end_on: tuple[str, ...] = ()  # subset of ("sat", "sun", "holiday")
    start_day_excluded: bool = True  # event day not counted


@dataclass
class JurisdictionPack:
    id: str
    name: str
    is_holiday: Callable[[date], bool]
    holiday_name: Callable[[date], Optional[str]]
    judicial_vacations: Callable[[int], list[tuple[date, date, str]]]
    rules: dict[str, Rule]


@dataclass
class DeadlineResult:
    due_date: date
    regime: str
    legal_refs: list[str]
    steps: list[str] = field(default_factory=list)

    def explain(self) -> str:
        return "\n".join(f"  {i+1}. {s}" for i, s in enumerate(self.steps))


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Sat, 6=Sun


def _in_ranges(d: date, ranges: list[tuple[date, date, str]]
               ) -> Optional[str]:
    for a, b, label in ranges:
        if a <= d <= b:
            return label
    return None


def compute_deadline(pack: JurisdictionPack, regime_id: str,
                     event_date: date, amount: int, unit: Unit = "days",
                     urgent: bool = False) -> DeadlineResult:
    """Compute a deadline under `pack`'s regime `regime_id`.

    urgent=True disables judicial-vacation suspension (processos
    urgentes — PT: CPC art. 138.º/1 in fine).
    """
    rule = pack.rules[regime_id]
    steps: list[str] = []
    refs = [rule.legal_basis]

    if unit == "weeks":
        steps.append(f"Period of {amount} week(s) converts to "
                     f"{amount * 7} continuous days (ends on the same "
                     f"weekday as the event) [weeks rule].")
        amount, unit = amount * 7, "days"

    steps.append(f"Event date: {event_date.isoformat()} "
                 f"({event_date.strftime('%A')}).")

    # ---------- months / years: corresponding-day rule ----------
    if unit in ("months", "years"):
        delta = (relativedelta(months=amount) if unit == "months"
                 else relativedelta(years=amount))
        due = event_date + delta
        steps.append(
            f"Term of {amount} {unit}: ends on the corresponding day "
            f"({due.isoformat()}); if no corresponding day exists, the "
            f"last day of the month applies "
            f"[{pack.id}: corresponding-day rule].")
        due, roll_steps = _roll_end(pack, rule, due)
        steps.extend(roll_steps)
        return DeadlineResult(due, rule.name, refs, steps)

    # ---------- day counting ----------
    start = event_date
    if rule.start_day_excluded:
        start = event_date + timedelta(days=1)
        steps.append(
            f"Day of the event is not counted; counting starts "
            f"{start.isoformat()} [start-day exclusion].")

    vac_ranges: list[tuple[date, date, str]] = []
    if rule.suspend_in_judicial_vacations and not urgent:
        # cover the plausible span of years
        for y in range(event_date.year, event_date.year + 2):
            vac_ranges.extend(pack.judicial_vacations(y))
    elif rule.suspend_in_judicial_vacations and urgent:
        steps.append("Urgent process: judicial-vacation suspension "
                     "does NOT apply [urgency exception].")

    counted = 0
    d = start - timedelta(days=1)
    while counted < amount:
        d += timedelta(days=1)
        if rule.count_business_days:
            if _is_weekend(d):
                continue
            if pack.is_holiday(d):
                continue
            counted += 1
        else:
            vac = _in_ranges(d, vac_ranges)
            if vac is not None:
                # suspended: day does not count
                if counted == 0 or True:
                    pass
                continue
            counted += 1

    if rule.count_business_days:
        steps.append(f"Counted {amount} business days (skipping "
                     f"weekends and holidays): reaches "
                     f"{d.isoformat()} ({d.strftime('%A')}).")
    else:
        n_susp = 0
        cursor = start
        while cursor <= d:
            if _in_ranges(cursor, vac_ranges):
                n_susp += 1
            cursor += timedelta(days=1)
        if n_susp:
            steps.append(
                f"Counted {amount} continuous days with "
                f"{n_susp} day(s) suspended during judicial "
                f"vacations: reaches {d.isoformat()} "
                f"({d.strftime('%A')}).")
        else:
            steps.append(f"Counted {amount} continuous days: reaches "
                         f"{d.isoformat()} ({d.strftime('%A')}).")

    due, roll_steps = _roll_end(pack, rule, d)
    steps.extend(roll_steps)
    steps.append(f"DUE: {due.isoformat()} ({due.strftime('%A')}), "
                 f"23:59 Europe/Lisbon.")
    return DeadlineResult(due, rule.name, refs, steps)


def _roll_end(pack: JurisdictionPack, rule: Rule, d: date
              ) -> tuple[date, list[str]]:
    """Apply the regime's end-roll rule: if the deadline lands on a
    configured non-working day, push to the next working day."""
    steps: list[str] = []
    if not rule.roll_end_on:
        return d, steps

    def blocked(x: date) -> Optional[str]:
        if "sat" in rule.roll_end_on and x.weekday() == 5:
            return "Saturday"
        if "sun" in rule.roll_end_on and x.weekday() == 6:
            return "Sunday"
        if "holiday" in rule.roll_end_on and pack.is_holiday(x):
            return f"holiday ({pack.holiday_name(x)})"
        return None

    reason = blocked(d)
    while reason is not None:
        nxt = d + timedelta(days=1)
        steps.append(f"End falls on {reason} ({d.isoformat()}): "
                     f"rolls to next day [end-roll rule].")
        d = nxt
        reason = blocked(d)
    return d, steps
