"""Mandate — Phase 10c: cross-reader agreement as a corruption detector.

Phase 8 tried to calibrate confidence from TIER agreement and hit an
honest wall: the cloud tier made 1 error in 440 fields, so there was
nothing to discriminate. The scan corpus fixes that — classical OCR
corrupts 14.3% of fields at fax quality, and those corruptions are
plausible, well-formed values that no downstream check can catch.

The signal here is READER agreement. Two readers see the same page:
tesseract (0.3 s, corrupts 14.3%) and a local VLM (34.6 s, corrupts
0.4%). Where they agree, the reading is almost certainly right. Where
they disagree, one of them misread — and since the VLM is right far
more often, disagreement is mostly OCR lying.

What it buys, concretely: run both readers (cost: the VLM's latency,
which you were paying anyway if you care about correctness), keep the
VLM's answer, and get a per-field confidence for free — plus a named
list of fields a human must check.

Usage:
  uv run python scripts/calibrate_perception.py --profile fax
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "core")
sys.path.insert(0, "scripts")

from benchmark_extraction import field_correct  # noqa: E402
from calibration import (Calibrator, auc,  # noqa: E402
                         expected_calibration_error, reliability_table)
from extract import FIELDS  # noqa: E402


def load(profile: str, reader: str) -> dict:
    p = Path(f"runs/perception_{reader}_{profile}.jsonl")
    if not p.exists():
        sys.exit(f"missing {p} — run scripts/benchmark_perception.py "
                 f"--profiles {profile} --readers {reader}")
    return {json.loads(l)["doc_id"]: json.loads(l)["pred"]
            for l in p.read_text().splitlines()}


def agree(a, b) -> bool:
    if a is None or b is None:
        return False
    return str(a).strip().lower() == str(b).strip().lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="fax")
    ap.add_argument("--primary", default="vlm", choices=["vlm", "ocr"])
    ap.add_argument("--target", type=float, default=0.99)
    args = ap.parse_args()

    gold = {g["doc_id"]: g for g in json.loads(
        Path("data/corpus/gold.json").read_text())}
    ocr = load(args.profile, "ocr")
    vlm = load(args.profile, "vlm")
    prim = vlm if args.primary == "vlm" else ocr

    recs, caught, missed, ocr_corrupt = [], [], [], 0
    for did in sorted(set(ocr) & set(vlm) & set(gold)):
        g = gold[did]
        for f in FIELDS:
            o, v = ocr[did].get(f), vlm[did].get(f)
            p = prim[did].get(f)
            sig = ("both_read_the_same" if agree(o, v)
                   else "readers_disagree" if (o is not None
                                               and v is not None)
                   else "one_reader_abstained" if (o is None) != (v is None)
                   else "both_abstained")
            ok = p is not None and field_correct(f, p, g[f])
            recs.append({"doc_id": did, "field": f, "signal": sig,
                         "correct": ok})
            # does disagreement catch OCR's silent corruptions?
            o_wrong = o is not None and not field_correct(f, o, g[f])
            if o_wrong:
                ocr_corrupt += 1
                (caught if sig != "both_read_the_same" else missed
                 ).append((did, f, o, g[f]))

    print(f"profile: {args.profile} · primary reader: {args.primary} · "
          f"{len(set(ocr) & set(vlm))} pages · {len(recs)} fields")

    # ---------- the headline: disagreement as a corruption detector ----
    print(f"\n== can reader disagreement catch OCR's silent lies? ==")
    if ocr_corrupt:
        rate = len(caught) / ocr_corrupt
        print(f"OCR corrupted {ocr_corrupt} fields · disagreement "
              f"flagged {len(caught)} of them ({rate:.1%})")
        print(f"MISSED (both readers agreed on a wrong value): "
              f"{len(missed)}")
        for d, f, o, t in missed[:6]:
            print(f"    {d:<13}{f:<16}both read {o!r} · truth {t!r}")
    else:
        print("no OCR corruptions in this profile — nothing to catch")

    # ---------- calibration (5-fold CV) ----------
    docs = sorted({r["doc_id"] for r in recs})
    folds = [set(docs[i::5]) for i in range(5)]
    pairs, pairs_nt = [], []
    for test_docs in folds:
        cal_i = [r for r in recs if r["doc_id"] not in test_docs]
        c_i = Calibrator().fit(cal_i)
        for r in recs:
            if r["doc_id"] in test_docs:
                pr = (c_i.confidence(r["field"], r["signal"]),
                      r["correct"])
                pairs.append(pr)
                if r["signal"] != "both_abstained":
                    pairs_nt.append(pr)
    n_err = sum(1 for _, ok in pairs if not ok)
    print(f"\n== calibrating {args.primary}'s confidence from reader "
          f"agreement ==")
    print(f"errors available to discriminate: {n_err} "
          f"({n_err/max(len(pairs),1):.1%})   "
          f"[Phase 8 had 1 in 440 and could not measure this]")
    print("\nCAUTION — a tautology lives in this metric. When BOTH "
          "readers abstain, the primary has no answer, so 'correct' is")
    print("False by construction. That cell predicts failure perfectly "
          "because it IS failure. It inflates AUC without carrying")
    print("information, so the honest number excludes it:")
    if n_err >= 5:
        print(f"AUC, agreement signal : {auc(pairs)}   "
              f"(inflated — includes the tautological cell)")
        print(f"AUC, non-tautological : {auc(pairs_nt)}   "
              f"(both_abstained excluded — this is the real number)")
        print(f"AUC, a constant       : "
              f"{auc([(0.9, ok) for _, ok in pairs])}  (0.5 by "
              f"construction)")
        print(f"ECE, agreement signal : "
              f"{expected_calibration_error(pairs)}")
        print(f"ECE, hardcoded 0.9    : "
              f"{expected_calibration_error([(0.9, ok) for _, ok in pairs])}")
        print(f"\n{'bin':<12}{'n':>5}{'claimed':>10}{'observed':>10}")
        for row in reliability_table(pairs):
            print(f"{row['bin']:<12}{row['n']:>5}"
                  f"{row['claimed']:>10.3f}{row['observed']:>10.3f}")
    else:
        print("too few errors to report AUC honestly")

    c = Calibrator().fit(recs)
    print(f"\nWHAT THIS SIGNAL IS FOR — read the table below carefully:")
    print(f"  reader disagreement predicts that OCR is wrong, NOT that")
    print(f"  the VLM is wrong. With the VLM as primary, disagreement")
    print(f"  barely moves its confidence — because when they differ it")
    print(f"  is almost always OCR that misread. The signal is an")
    print(f"  excellent CORRUPTION DETECTOR and a poor VLM-confidence")
    print(f"  estimator. Same signal, two jobs, one of which it cannot do.")
    print(f"\n{'signal':<24}{'confidence':>12}{'n':>6}")
    seen = {}
    for r in recs:
        seen.setdefault(r["signal"], [0, 0])
        seen[r["signal"]][0] += r["correct"]
        seen[r["signal"]][1] += 1
    for sig, (ok, n) in sorted(seen.items(),
                               key=lambda kv: -kv[1][0] / kv[1][1]):
        print(f"{sig:<24}{ok/n:>12.3f}{n:>6}")

    print(f"\n== risk-coverage ==")
    print(f"{'target':>8}{'tau':>8}{'auto-accepted':>16}"
          f"{'precision':>11}{'to human':>10}")
    for t in (0.95, 0.99, 1.00):
        tau = Calibrator(table=c.table, support=c.support,
                         prior=c.prior).calibrate_threshold(recs, t)
        kept = [(s, ok) for s, ok in pairs if s >= tau]
        if kept:
            pr = sum(ok for _, ok in kept) / len(kept)
            print(f"{t:>8.2f}{tau:>8.3f}{len(kept):>16}{pr:>11.3f}"
                  f"{len(pairs)-len(kept):>10}")
        else:
            print(f"{t:>8.2f}{tau:>8.3f}{0:>16}{'n/a':>11}"
                  f"{len(pairs):>10}")

    Path("models").mkdir(exist_ok=True)
    c.save("models/calibration_perception.json")
    print("\nwrote models/calibration_perception.json")


if __name__ == "__main__":
    main()
