"""Mandate — extraction benchmark: per-field accuracy per language
per tier, against the gold set. Resumable per tier via runs/ cache.

Usage:
  python scripts/benchmark_extraction.py --tiers tier2
  python scripts/benchmark_extraction.py --tiers tier2 tier0 tier1
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "core")
from dotenv import load_dotenv  # noqa: E402
load_dotenv()
from extract import FIELDS, TIERS  # noqa: E402

SCORED = [f for f in FIELDS]


def norm_party(s):
    return " ".join(str(s).lower().replace(",", " ").split()) \
        if s else None


def field_correct(field, pred, gold):
    if pred is None:
        return False
    if field in ("debtor", "creditor"):
        p, g = norm_party(pred), norm_party(gold)
        return p == g or (p in g or g in p)
    if field == "amount_eur":
        return abs(float(pred) - float(gold)) < 0.01
    if field == "legal_basis":
        toks = set(re.findall(r"\d+", str(gold)))
        return bool(toks & set(re.findall(r"\d+", str(pred))))
    return str(pred) == str(gold)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", nargs="+", default=["tier2"],
                    choices=list(TIERS))
    ap.add_argument("--corpus", default="data/corpus")
    args = ap.parse_args()

    gold = json.loads(Path(args.corpus, "gold.json").read_text())
    Path("runs").mkdir(exist_ok=True)
    Path("models").mkdir(exist_ok=True)
    report = {}

    for tier in args.tiers:
        cache = Path(f"runs/extractions_{tier}.jsonl")
        done = {}
        if cache.exists():
            for line in cache.read_text().splitlines():
                rec = json.loads(line)
                done[rec["doc_id"]] = rec["pred"]
        fn = TIERS[tier]
        with cache.open("a") as f:
            for g in gold:
                if g["doc_id"] in done:
                    continue
                text = Path(args.corpus, "docs",
                            f"{g['doc_id']}.txt").read_text()
                t0 = time.time()
                try:
                    pred = fn(text).model_dump()
                except Exception as e:
                    print(f"  {tier} {g['doc_id']} ERROR {e} "
                          f"(rerun to resume)")
                    continue
                done[g["doc_id"]] = pred
                f.write(json.dumps(
                    {"doc_id": g["doc_id"], "pred": pred,
                     "seconds": round(time.time() - t0, 2)}) + "\n")
                f.flush()
                print(f"  {tier} {g['doc_id']} ok "
                      f"({time.time()-t0:.1f}s)")

        # score
        per = {}
        for lang in ("pt", "en", "all"):
            docs = [g for g in gold
                    if lang in ("all", g["language"])]
            per[lang] = {}
            for field in SCORED:
                n_ok = sum(
                    1 for g in docs
                    if g["doc_id"] in done and field_correct(
                        field, done[g["doc_id"]].get(field), g[field]))
                per[lang][field] = round(n_ok / max(len(docs), 1), 3)
            per[lang]["_macro"] = round(
                sum(per[lang][f] for f in SCORED) / len(SCORED), 3)
        report[tier] = per

        print(f"\n== {tier} ==  (n={len(done)}/{len(gold)})")
        print(f"{'field':<18}{'pt':>7}{'en':>7}{'all':>7}")
        for field in SCORED + ["_macro"]:
            print(f"{field:<18}"
                  f"{per['pt'][field]:>7.2f}"
                  f"{per['en'][field]:>7.2f}"
                  f"{per['all'][field]:>7.2f}")

    Path("models/extraction_benchmark.json").write_text(
        json.dumps(report, indent=2))
    print("\nwrote models/extraction_benchmark.json")


if __name__ == "__main__":
    main()
