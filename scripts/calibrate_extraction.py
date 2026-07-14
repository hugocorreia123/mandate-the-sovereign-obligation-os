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
                         auc, expected_calibration_error,
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
            pred = runs[primary][did].get(f)
            # The signal describes OUR tier's standing. If the primary
            # abstained, that is the signal — regardless of whether the
            # other tiers happen to agree with each other.
            sig = ("abstained" if pred is None
                   else agreement_signal(values))
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
    ap.add_argument("--folds", type=int, default=5)
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

    # k-fold CV: with n=40 documents a 50/50 split throws away half the
    # (already scarce) errors. Out-of-fold predictions let every error
    # contribute to the evaluation while never scoring a document whose
    # own data fitted the cell.
    k = args.folds
    folds = [set(docs[i::k]) for i in range(k)]
    pairs, oof = [], []
    for i, test_docs in enumerate(folds):
        cal_i = [r for r in recs if r["doc_id"] not in test_docs]
        test_i = [r for r in recs if r["doc_id"] in test_docs]
        c_i = Calibrator().fit(cal_i)
        for r in test_i:
            conf = c_i.confidence(r["field"], r["signal"])
            oof.append({**r, "conf": conf})
            if r["signal"] != "abstained":
                pairs.append((conf, r["correct"]))
    n_err = sum(1 for _, ok in pairs if not ok)
    print(f"{k}-fold CV over {len(docs)} docs · "
          f"{len(recs)} field-decisions · "
          f"{len(pairs)} answered · {n_err} errors to discriminate")

    # the shipped calibrator is fitted on everything
    cal = recs
    c = Calibrator().fit(recs)
    tau = c.calibrate_threshold(recs, target_precision=args.target)
    ece_cal = expected_calibration_error(pairs)
    ece_flat = expected_calibration_error(
        [(0.9, ok) for _, ok in pairs])

    print(f"\n== calibration quality (held-out) ==")
    print(f"ECE, calibrated confidence : {ece_cal}")
    print(f"ECE, hardcoded 0.9         : {ece_flat}   "
          f"({'better' if ece_cal < ece_flat else 'WORSE'} by "
          f"{abs(ece_flat-ece_cal):.3f})")
    if ece_cal >= ece_flat:
        print("  NOTE: a constant can be well-calibrated by accident "
              "when it sits at the base rate — but it cannot "
              "DISCRIMINATE. See risk-coverage below: a constant "
              "cannot be thresholded at all.")
    n_err = sum(1 for _, ok in pairs if not ok)
    MIN_ERR = 5          # below this, AUC is noise, not evidence
    if n_err < MIN_ERR:
        print(f"AUC (discrimination)       : NOT REPORTED — only "
              f"{n_err} error(s) in the out-of-fold evaluation.")
        print(f"  With fewer than {MIN_ERR} negatives AUC is a "
              f"coin-flip artifact, not a measurement. A confidence "
              f"signal cannot be")
        print(f"  validated against errors that do not occur. This is "
              f"an UNMEASURABLE result, not a good one. See 'Limits'.")
    else:
        print(f"AUC, calibrated confidence : {auc(pairs)}   "
              f"[0.5 = separates nothing, 1.0 = perfect]")
        print(f"AUC, hardcoded 0.9         : "
              f"{auc([(0.9, ok) for _, ok in pairs])}   "
              f"(a constant scores 0.5 by construction — it cannot be "
              f"thresholded, whatever its ECE)")

    print(f"\n{'bin':<12}{'n':>5}{'claimed':>10}{'observed':>10}")
    for row in reliability_table(pairs):
        print(f"{row['bin']:<12}{row['n']:>5}{row['claimed']:>10.3f}"
              f"{row['observed']:>10.3f}")

    print(f"\n== conformal abstention (target precision "
          f"{args.target}) ==")
    print(f"threshold τ = {tau}")
    kept = [(s, ok) for s, ok in pairs if s >= tau]
    drop = [(s, ok) for s, ok in pairs if s < tau]
    n_abst = len([r for r in oof if r["signal"] == "abstained"])
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

    print(f"\n== risk-coverage (what the signal actually buys) ==")
    print(f"{'target':>8}{'tau':>8}{'auto-accepted':>16}"
          f"{'precision':>11}{'to human':>10}")
    for target in (0.90, 0.95, 0.99, 1.00):
        t = Calibrator(table=c.table, support=c.support,
                       prior=c.prior).calibrate_threshold(cal, target)
        k = [(s_, ok) for s_, ok in pairs if s_ >= t]
        if k:
            pr = sum(ok for _, ok in k) / len(k)
            print(f"{target:>8.2f}{t:>8.3f}{len(k):>16}"
                  f"{pr:>11.3f}{len(pairs)-len(k):>10}")
        else:
            print(f"{target:>8.2f}{t:>8.3f}{0:>16}{'—':>11}"
                  f"{len(pairs):>10}")

    print(f"\n{'field':<18}{'signal':<15}{'conf':>7}{'n':>5}")
    for f in sorted(c.table):
        for sig in sorted(c.table[f], key=lambda s: -c.table[f][s]):
            print(f"{f:<18}{sig:<15}{c.table[f][sig]:>7.3f}"
                  f"{c.support[f][sig]:>5}")

    print(f"\n== limits of this measurement ==")
    print(f"errors available to calibrate against: {n_err} in "
          f"{len(pairs)} answered fields "
          f"({n_err/max(len(pairs),1):.1%})")
    if n_err < 10:
        print("  n=40 documents is too small to validate DISCRIMINATION "
              "for a tier this accurate: there are almost no errors to")
        print("  separate. The machinery is unit-tested on synthetic "
              "data where errors exist; the corpus needs to be larger")
        print("  or harder before the confidence signal can be trusted "
              "as a threshold. Reported, not hidden.")
    print(f"\nabstentions routed to a human automatically: "
          f"{sum(1 for r in oof if r['signal'] == 'abstained')} "
          f"fields — this part IS actionable today.")

    Path("models").mkdir(exist_ok=True)
    c.save("models/calibration.json")
    print("\nwrote models/calibration.json")


if __name__ == "__main__":
    main()
