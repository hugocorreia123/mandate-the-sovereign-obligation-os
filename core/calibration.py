"""Mandate — Phase 8: calibrated confidence + conformal abstention.

The problem: a confidence of 0.9 stamped on every claim is not a
measurement, it is decoration. In a legal ledger it is worse than
nothing — it invites trust it has not earned.

The signal (free): **tier agreement**. Tier-2 is deterministic and
offline, so it can always run alongside whichever tier is in use. Per
field, the tiers either agree, partly agree, disagree, or abstain. That
is a conformity signal costing no extra egress and no extra tokens.

The calibration: on a held-out split of the gold set, measure the
empirical accuracy of each (field, signal) cell. That table *is* the
confidence function — "0.87" then means "87 of 100 such fields were
right on data this model had not seen".

The guarantee (conformal risk control): choose the smallest threshold
τ such that fields auto-accepted at confidence ≥ τ are correct at the
target rate on the calibration split. Everything below τ routes to a
human. The abstention rate becomes a *consequence of a chosen risk
level*, not a vibe.

Honest scope: this is split-conformal / risk-control in spirit — a
finite-sample empirical guarantee under exchangeability, on n=40. It
is directional, and the README says so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# agreement states, ordered from strongest evidence to weakest
SIGNALS = ("all_agree", "majority", "single_source", "disagree",
           "abstained")


def agreement_signal(values: dict[str, Any]) -> str:
    """Classify per-field agreement across tiers.

    `values` maps tier name -> that tier's value for one field.
    None means the tier abstained on that field.
    """
    present = {t: v for t, v in values.items() if v is not None}
    if not present:
        return "abstained"
    norm = [str(v).strip().lower() for v in present.values()]
    uniq = set(norm)
    if len(present) == 1:
        return "single_source"
    if len(uniq) == 1:
        return "all_agree"
    # majority = one value held by more than half the *present* tiers
    top = max(uniq, key=norm.count)
    if norm.count(top) > len(norm) / 2:
        return "majority"
    return "disagree"


@dataclass
class Calibrator:
    """Maps (field, agreement signal) -> empirical accuracy."""
    table: dict[str, dict[str, float]] = field(default_factory=dict)
    support: dict[str, dict[str, int]] = field(default_factory=dict)
    prior: float = 0.5          # fallback for unseen cells
    tau: float = 0.0            # conformal abstention threshold
    target_precision: float = 0.95

    # ---------------------------------------------------------- fit
    def fit(self, records: Iterable[dict]) -> "Calibrator":
        """records: {field, signal, correct: bool}"""
        hits: dict[tuple[str, str], list[int]] = {}
        for r in records:
            hits.setdefault((r["field"], r["signal"]), []).append(
                1 if r["correct"] else 0)
        self.table, self.support = {}, {}
        for (f, sig), vals in hits.items():
            # Laplace smoothing: with tiny cells, don't claim 1.00
            acc = (sum(vals) + 1) / (len(vals) + 2)
            self.table.setdefault(f, {})[sig] = round(acc, 4)
            self.support.setdefault(f, {})[sig] = len(vals)
        allv = [1 if r["correct"] else 0 for r in records]
        self.prior = round((sum(allv) + 1) / (len(allv) + 2), 4) \
            if allv else 0.5
        return self

    def confidence(self, field_name: str, signal: str) -> float:
        if signal == "abstained":
            return 0.0
        return self.table.get(field_name, {}).get(signal, self.prior)

    # ------------------------------------------- conformal threshold
    def calibrate_threshold(self, records: Iterable[dict],
                            target_precision: float = 0.95) -> float:
        """Smallest τ whose auto-accepted set hits the target
        precision on calibration data. Risk control, not a guess."""
        recs = [r for r in records if r["signal"] != "abstained"]
        scored = [(self.confidence(r["field"], r["signal"]),
                   bool(r["correct"])) for r in recs]
        self.target_precision = target_precision
        candidates = sorted({round(s, 4) for s, _ in scored})
        for tau in candidates:
            kept = [ok for s, ok in scored if s >= tau]
            if kept and (sum(kept) / len(kept)) >= target_precision:
                self.tau = tau
                return tau
        self.tau = 1.01          # nothing is safe to auto-accept
        return self.tau

    def accepts(self, field_name: str, signal: str) -> bool:
        return self.confidence(field_name, signal) >= self.tau

    # --------------------------------------------------------- io
    def to_json(self) -> str:
        return json.dumps({"table": self.table, "support": self.support,
                           "prior": self.prior, "tau": self.tau,
                           "target_precision": self.target_precision},
                          indent=2, sort_keys=True)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def load(cls, path: str | Path) -> "Calibrator":
        d = json.loads(Path(path).read_text())
        c = cls(table=d["table"], support=d.get("support", {}),
                prior=d["prior"], tau=d["tau"],
                target_precision=d.get("target_precision", 0.95))
        return c


# ------------------------------------------------------------ metrics
def expected_calibration_error(pairs: list[tuple[float, bool]],
                               bins: int = 10) -> float:
    """ECE: mean |claimed confidence - observed accuracy| per bin.

    0.0 = perfectly calibrated. This is the number that says whether a
    confidence is a measurement or decoration.
    """
    if not pairs:
        return 0.0
    total, err = len(pairs), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        cell = [(c, ok) for c, ok in pairs
                if (c > lo or (b == 0 and c >= lo)) and c <= hi]
        if not cell:
            continue
        conf = sum(c for c, _ in cell) / len(cell)
        acc = sum(1 for _, ok in cell if ok) / len(cell)
        err += (len(cell) / total) * abs(conf - acc)
    return round(err, 4)


def reliability_table(pairs: list[tuple[float, bool]], bins: int = 5
                      ) -> list[dict]:
    """Rows of (bin, n, claimed, observed) — the honest diagram."""
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        cell = [(c, ok) for c, ok in pairs
                if (c > lo or (b == 0 and c >= lo)) and c <= hi]
        if not cell:
            continue
        out.append({
            "bin": f"{lo:.1f}–{hi:.1f}", "n": len(cell),
            "claimed": round(sum(c for c, _ in cell) / len(cell), 3),
            "observed": round(sum(1 for _, ok in cell if ok)
                              / len(cell), 3)})
    return out
