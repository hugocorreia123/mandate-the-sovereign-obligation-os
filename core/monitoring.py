"""Mandate — Phase 16: the calendar comes looking for you.

Until now the ledger was a table: true, sorted, and entirely passive.
Passive is how deadlines are missed — nobody misses a deadline they
were standing in front of.

Three decisions worth defending:

1. ESCALATION IS MEASURED IN THE DAYS THE LAW COUNTS, not calendar
   days. "5 days left" is comfortable; five days containing a weekend
   and two holidays is one working day to file. Under férias judiciais
   a thirty-day gap can contain zero. The engine already knows which
   days count — it used that rule to compute the deadline — so the
   alert counts the same way or it is a confident lie.

2. EACH LEVEL FIRES ONCE. An alert that repeats is an alert that gets
   filtered, and a filtered alert is worse than none: it trains people
   to ignore the channel that will one day carry the real one. The
   fired levels are derived from the ledger, so a restart cannot
   resurrect yesterday's warning.

3. A BREACH IS A LEGAL EVENT, NOT A UI STATE. It transitions the
   obligation and lands in the hash chain, because "when did you know"
   is the first question anyone asks afterwards.

What this deliberately does NOT do: send anything. No mail, no
webhook, no auto-escalation to a person who did not ask. Mandate
surfaces; humans act. The same rule as the drafting gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from engine import days_remaining
from graph import ObligationGraph, ObligationStatus


class Level(str, Enum):
    """Ordered. The int value is the comparison, the name is the UI."""
    OK = "ok"
    NOTICE = "notice"
    WARNING = "warning"
    URGENT = "urgent"
    CRITICAL = "critical"
    BREACHED = "breached"


_ORDER = [Level.OK, Level.NOTICE, Level.WARNING, Level.URGENT,
          Level.CRITICAL, Level.BREACHED]
_RANK = {l: i for i, l in enumerate(_ORDER)}

LEVEL_ICON = {Level.OK: "🟢", Level.NOTICE: "🔵", Level.WARNING: "🟡",
              Level.URGENT: "🟠", Level.CRITICAL: "🔴",
              Level.BREACHED: "⚫"}


@dataclass(frozen=True)
class EscalationPolicy:
    """Thresholds in the days the LAW counts, not calendar days."""
    notice: int = 10
    warning: int = 5
    urgent: int = 3
    critical: int = 1

    def level_for(self, legal_days: int) -> Level:
        if legal_days < 0:
            return Level.BREACHED
        if legal_days <= self.critical:
            return Level.CRITICAL
        if legal_days <= self.urgent:
            return Level.URGENT
        if legal_days <= self.warning:
            return Level.WARNING
        if legal_days <= self.notice:
            return Level.NOTICE
        return Level.OK


@dataclass
class Alert:
    obligation_id: str
    level: Level
    calendar_days: int
    legal_days: int
    due_date: date
    description: str
    debtor: str
    jurisdiction: str
    regime: str
    reason: str = ""
    new: bool = True          # has this level fired before?

    @property
    def icon(self) -> str:
        return LEVEL_ICON[self.level]

    @property
    def misleading_by(self) -> int:
        """How many days a calendar app would overstate by. This is
        the number that makes the case for the whole module."""
        return max(0, self.calendar_days - self.legal_days)


@dataclass
class Monitor:
    packs: dict
    policy: EscalationPolicy = field(default_factory=EscalationPolicy)

    # ---- assessment ----
    def assess(self, graph: ObligationGraph, oid: str,
               today: date) -> Optional[Alert]:
        o = graph.obligations[oid]
        if o.deadline is None:
            return None
        # Nothing closed, and nothing an amendment already killed.
        if o.status in (ObligationStatus.SATISFIED,
                        ObligationStatus.VOID,
                        ObligationStatus.BREACHED):
            return None
        if graph.superseded_by(oid):
            return None

        pack = self.packs.get(o.jurisdiction)
        if pack is None:
            return None
        cal, legal = days_remaining(pack, o.regime_id, today,
                                    o.deadline.due_date)
        level = self.policy.level_for(legal)
        if level is Level.OK:
            return None

        reason = (f"{legal} day(s) that count remain under "
                  f"{o.deadline.regime}")
        if cal != legal:
            reason += (f" — a calendar shows {cal}, which overstates "
                       f"the time available by {cal - legal} day(s)")
        # Being blocked does not stop the clock: the law does not care
        # that you are waiting on someone else.
        blockers = graph.blocked_by(oid)
        if blockers:
            reason += (f"; still waiting on {len(blockers)} other "
                       f"obligation(s) — the clock runs anyway")
        return Alert(
            obligation_id=oid, level=level, calendar_days=cal,
            legal_days=legal, due_date=o.deadline.due_date,
            description=o.description, debtor=o.debtor,
            jurisdiction=o.jurisdiction, regime=o.deadline.regime,
            reason=reason)

    # ---- what has already been said ----
    def _fired(self, graph: ObligationGraph) -> dict[str, str]:
        """Highest level already raised per obligation, from the
        ledger — so a restart cannot resurrect yesterday's warning."""
        out: dict[str, str] = {}
        if not graph.log_path.exists():
            return out
        for line in graph.log_path.read_text(
                encoding="utf-8").splitlines():
            ev = json.loads(line)
            if ev["type"] != "escalated":
                continue
            p = ev["payload"]
            prev = out.get(p["obligation_id"])
            if prev is None or _RANK[Level(p["level"])] > _RANK[
                    Level(prev)]:
                out[p["obligation_id"]] = p["level"]
        return out

    # ---- the sweep ----
    def sweep(self, graph: ObligationGraph, today: date,
              actor: str = "monitor") -> list[Alert]:
        """Assess every open obligation. Log what is NEW, breach what
        is late, stay silent about what has already been said."""
        fired = self._fired(graph)
        alerts: list[Alert] = []

        for o in list(graph.obligations.values()):
            a = self.assess(graph, o.id, today)
            if a is None:
                continue
            seen = fired.get(o.id)
            a.new = seen is None or _RANK[a.level] > _RANK[Level(seen)]

            if a.new:
                graph._append_event("escalated", actor, {
                    "obligation_id": o.id, "level": a.level.value,
                    "calendar_days": a.calendar_days,
                    "legal_days": a.legal_days,
                    "due_date": a.due_date.isoformat(),
                    "reason": a.reason})
                # A breach is a legal event, not a colour in a table.
                if a.level is Level.BREACHED:
                    if o.status is ObligationStatus.AWAITING_APPROVAL:
                        graph.transition(
                            o.id, ObligationStatus.IN_PROGRESS, actor,
                            note="stepped back to record a breach")
                    if o.status is not ObligationStatus.ESCALATED:
                        graph.transition(
                            o.id, ObligationStatus.ESCALATED, actor,
                            note=a.reason)
                    graph.transition(o.id, ObligationStatus.BREACHED,
                                     actor, note=a.reason)
            alerts.append(a)

        alerts.sort(key=lambda a: (-_RANK[a.level], a.legal_days))
        return alerts

    def new_alerts(self, graph: ObligationGraph,
                   today: date) -> list[Alert]:
        return [a for a in self.sweep(graph, today) if a.new]


def render(alerts: list[Alert]) -> str:
    if not alerts:
        return "no obligation needs attention today."
    lines = [f"{'':2}{'level':<11}{'due':<12}{'law':>4}"
             f"{'cal':>5}   what"]
    for a in alerts:
        lines.append(
            f"{a.icon} {a.level.value:<11}{a.due_date.isoformat():<12}"
            f"{a.legal_days:>4}{a.calendar_days:>5}   "
            f"{a.description[:38]}")
    lying = [a for a in alerts if a.misleading_by > 0]
    if lying:
        worst = max(lying, key=lambda a: a.misleading_by)
        lines.append(
            f"\n  A calendar would overstate the time available on "
            f"{len(lying)} of these — worst by "
            f"{worst.misleading_by} days ({worst.description[:30]}).")
    return "\n".join(lines)
