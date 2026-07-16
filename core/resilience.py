"""Mandate — Phase 14: degradation as a first-class, logged event.

The project has claimed since day one that an outage is a quality dial
rather than a failure. Until now that was true by CONSTRUCTION — the
deterministic core needs no network — but it was nowhere enforced and
nowhere recorded. The caller picked a tier by hand; nothing probed
health, nothing demoted, and an outage left no trace.

That last part is what a regulator actually asks for. DORA does not ask
whether you use AI. It asks what happened when it failed, and expects
the answer to be in a log you cannot edit.

So:
  * the LADDER is explicit and ordered, not implied by an if-chain;
  * health is PROBED, not assumed;
  * demotion is automatic and carries a REASON;
  * every demotion is appended to the same hash-chained ledger as the
    obligations themselves — the outage sits in the record beside the
    decisions it affected;
  * the floor is a human, and the router reaches it rather than raising.

The router never touches the Deadline Engine. That is the point: the
engine is not a rung on the ladder, it is the ground the ladder stands
on.
"""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

# The ladder, best to worst. Order lives in ONE place.
LADDER: tuple[str, ...] = ("tier0", "tier1", "tier2")

TIER_LABEL = {
    "tier0": "☁️ Cloud AI",
    "tier1": "🔒 Local AI",
    "tier2": "⚙️ Rules only",
    "tier3": "📋 Playbooks + human",
}


def probe_tier0() -> bool:
    """A frontier model needs a key and an egress path."""
    return bool(os.environ.get("GROQ_API_KEY"))


def probe_tier1(host: str = "http://localhost:11434") -> bool:
    """A local model needs a local server, and nothing else."""
    try:
        urllib.request.urlopen(f"{host}/api/tags", timeout=1)
        return True
    except Exception:
        return False


def probe_tier2() -> bool:
    """Rules need nothing. This is deliberately hardcoded True: if it
    could ever be False the ladder would have no floor, and a system
    whose floor can fall is not a ladder, it is a hope."""
    return True


DEFAULT_PROBES: dict[str, Callable[[], bool]] = {
    "tier0": probe_tier0,
    "tier1": probe_tier1,
    "tier2": probe_tier2,
}


@dataclass
class Routing:
    """The outcome of asking for a tier."""
    tier: str
    requested: str
    degraded: bool
    reason: str

    @property
    def label(self) -> str:
        return TIER_LABEL.get(self.tier, self.tier)


@dataclass
class TierRouter:
    """Chooses the best rung that is actually up, and says so.

    `forced_down` simulates an outage — the pull-the-cable demo — and
    is also how the resilience path gets TESTED. A resilience story you
    cannot exercise on demand is a resilience story you do not have.
    """
    probes: dict[str, Callable[[], bool]] = field(
        default_factory=lambda: dict(DEFAULT_PROBES))
    forced_down: set[str] = field(default_factory=set)
    graph: object = None            # optional: log to the ledger
    _cache: dict[str, bool] = field(default_factory=dict)

    # ---- health ----
    def available(self, tier: str, use_cache: bool = True) -> bool:
        if tier in self.forced_down:
            return False
        if tier == "tier3":
            return True             # a human is always available
        if use_cache and tier in self._cache:
            return self._cache[tier]
        probe = self.probes.get(tier)
        ok = bool(probe()) if probe else False
        self._cache[tier] = ok
        return ok

    def refresh(self) -> None:
        self._cache.clear()

    def status(self) -> dict[str, bool]:
        return {t: self.available(t) for t in LADDER}

    # ---- routing ----
    def route(self, requested: str = "tier0",
              actor: str = "system") -> Routing:
        """Return the best rung at or below `requested` that is up.

        Never raises, never returns None: if every AI rung is down the
        answer is tier3 — the engine plus a human — which is the floor
        the whole architecture exists to guarantee.
        """
        if requested not in LADDER:
            requested = LADDER[0]
        start = LADDER.index(requested)
        for tier in LADDER[start:]:
            if self.available(tier):
                degraded = tier != requested
                reason = (f"{TIER_LABEL[requested]} unavailable "
                          f"({self._why(requested)}); degraded to "
                          f"{TIER_LABEL[tier]}" if degraded else
                          f"{TIER_LABEL[tier]} available")
                r = Routing(tier, requested, degraded, reason)
                if degraded:
                    self._log(r, actor)
                return r
        r = Routing("tier3", requested, True,
                    f"every automated tier is down "
                    f"({self._why(requested)}); the deadline engine "
                    f"and the human queue carry the work — no "
                    f"obligation is lost, only unassisted")
        self._log(r, actor)
        return r

    def _why(self, tier: str) -> str:
        if tier in self.forced_down:
            return "simulated outage"
        return {"tier0": "no API key or no egress",
                "tier1": "no local model server",
                "tier2": "unavailable"}.get(tier, "unknown")

    # ---- the auditable part ----
    def _log(self, r: Routing, actor: str) -> None:
        """An outage that leaves no trace is an outage you cannot
        report. This one lands in the same hash-chained ledger as the
        obligations it affected."""
        if self.graph is None:
            return
        try:
            self.graph._append_event(
                "tier_degraded", actor,
                {"requested": r.requested, "actual": r.tier,
                 "reason": r.reason,
                 "ladder_status": {t: self.available(t)
                                   for t in LADDER}})
        except Exception:
            pass          # logging must never break the routing


def pull_the_cable(router: TierRouter, tier: str = "tier0") -> None:
    """Simulate an outage of one rung. The demo's party trick, and the
    test suite's resilience harness."""
    router.forced_down.add(tier)
    router.refresh()


def restore(router: TierRouter, tier: Optional[str] = None) -> None:
    if tier is None:
        router.forced_down.clear()
    else:
        router.forced_down.discard(tier)
    router.refresh()
