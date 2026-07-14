"""Mandate — Phase 8 runner: calibrate extraction confidence.

Uses the CACHED tier runs (runs/extractions_tier*.jsonl) — no API
calls, no egress. Splits the gold set into calibration/test, fits the
(field, agreement-signal) -> accuracy table on calibration, then
reports on the held-out test split:

  * ECE, calibrated vs the old hardcoded 0.9
  * a reliability table (claimed vs observed)
  * the conformal threshold τ and the precision/abstention it buys

Usage:
  uv run python scripts/calibrate_extraction.py
  uv run python scripts/calibrate_extraction.py --target 0.99
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, "core")
sys.path.insert(0, "scripts")

from calibration import (Calibrator, agreement_signal,  # noqa: E402
                         expected_calibration_error,
                         reliability_table)
from extract import FIELDS  # noqa: E402
from benchmark_extraction import field_correct  # noqa: E402


def load_runs(tiers):
    out = {}
    for t in tiers:
        p = Path(f"runs/extractions_{t}.jsonl")
        if not p.exists():
            continue
        out[t] = {}
        for line in p.read_text().splitlines():
            r = json.loads(line)
            out[t][r["doc_id"]] = r["pred"]
    return out


def build_records(gold, runs, primary):
    """One record per (doc, field): the agreement signal + whether the
    PRIMARY tier's answer was actually right."""
    recs = []
    for g in gold:
        did = g["doc_id"]
        if did not in runs.get(primary, {}):
            continue
        for f in FIELDS:
            values = {t: runs[t][did].get(f)
                      for t in runs if did in runs[t]}
            sig = agreement_signal(values)
            pred = runs[primary][did].get(f)
            ok = (pred is not None
                  and field_correct(f, pred, g[f]))
            recs.append({"doc_id": did, "field": f, "signal": sig,
                         "correct": ok, "pred": pred})
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--primary", default="tier0",
                    help="the tier whose answers we are scoring")
    ap.add_argument("--target", type=float, default=0.95,
                    help="target precision on auto-accepted fields")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    gold = json.loads(Path("data/corpus/gold.json").read_text())
    runs = load_runs(["tier0", "tier1", "tier2"])
    if args.primary not in runs:
        sys.exit(f"no cached run for {args.primary} — run "
                 f"scripts/benchmark_extraction.py first")
    print(f"tiers available: {list(runs)}  ·  primary: {args.primary}")

    recs = build_records(gold, runs, args.primary)
    docs = sorted({r["doc_id"] for r in recs})
    random.Random(args.seed).shuffle(docs)
    cut = len(docs) // 2
    cal_docs, test_docs = set(docs[:cut]), set(docs[cut:])
    cal = [r for r in recs if r["doc_id"] in cal_docs]
    test = [r for r in recs if r["doc_id"] in test_docs]
    print(f"split: {len(cal_docs)} calibration docs / "
          f"{len(test_docs)} test docs  "
          f"({len(cal)} / {len(test)} field-decisions)")

    c = Calibrator().fit(cal)
    tau = c.calibrate_threshold(cal, target_precision=args.target)

    # ---- evaluate on the held-out split
    pairs = [(c.confidence(r["field"], r["signal"]), r["correct"])
             for r in test if r["signal"] != "abstained"]
    ece_cal = expected_calibration_error(pairs)
    ece_flat = expected_calibration_error(
        [(0.9, ok) for _, ok in pairs])

    print(f"\n== calibration quality (held-out) ==")
    print(f"ECE, calibrated confidence : {ece_cal}")
    print(f"ECE, hardcoded 0.9         : {ece_flat}   "
          f"({'better' if ece_cal < ece_flat else 'WORSE'} by "
          f"{abs(ece_flat-ece_cal):.3f})")

    print(f"\n{'bin':<12}{'n':>5}{'claimed':>10}{'observed':>10}")
    for row in reliability_table(pairs):
        print(f"{row['bin']:<12}{row['n']:>5}{row['claimed']:>10.3f}"
              f"{row['observed']:>10.3f}")

    print(f"\n== conformal abstention (target precision "
          f"{args.target}) ==")
    print(f"threshold τ = {tau}")
    kept = [(s, ok) for s, ok in pairs if s >= tau]
    drop = [(s, ok) for s, ok in pairs if s < tau]
    n_abst = len([r for r in test if r["signal"] == "abstained"])
    if kept:
        prec = sum(ok for _, ok in kept) / len(kept)
        print(f"auto-accepted : {len(kept)} fields · "
              f"precision {prec:.3f}  (target {args.target})")
    if drop:
        prec_d = sum(ok for _, ok in drop) / len(drop)
        print(f"-> human queue: {len(drop)} fields · they would have "
              f"been {prec_d:.3f} correct (this is the value: the "
              f"risky ones)")
    print(f"tier abstained : {n_abst} fields (routed to human "
          f"automatically)")

    print(f"\n{'field':<18}{'signal':<15}{'conf':>7}{'n':>5}")
    for f in sorted(c.table):
        for sig in sorted(c.table[f], key=lambda s: -c.table[f][s]):
            print(f"{f:<18}{sig:<15}{c.table[f][sig]:>7.3f}"
                  f"{c.support[f][sig]:>5}")

    Path("models").mkdir(exist_ok=True)
    c.save("models/calibration.json")
    print("\nwrote models/calibration.json")


if __name__ == "__main__":
    main()
