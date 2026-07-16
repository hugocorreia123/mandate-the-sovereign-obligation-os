"""Mandate — Phase 10b: the perception benchmark.

Every number in this project before Phase 10 was measured on CLEAN
TEXT. This measures what happens when the document is a scan.

The metric that matters is NOT accuracy. It is the split between
ABSTENTION and CORRUPTION:

  * a field that comes back None routes to a human. Cost: attention.
  * a field that comes back WRONG routes to a filing. Cost: the case.

OCR does not abstain. Found while building this: at fax quality
tesseract read "€ 185.435,45" as "€ 165.435,45" — a EUR 20,000 error,
correctly formatted, in the right place, that every downstream check
accepts. The local 7B's much-praised "abstains rather than
hallucinates" property does not extend to the perception layer, and
that is the point of measuring it.

Usage:
  uv run python scripts/benchmark_perception.py --profiles clean fax
  uv run python scripts/benchmark_perception.py --readers ocr vlm
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "core")
sys.path.insert(0, "scripts")

from benchmark_extraction import field_correct  # noqa: E402
from extract import FIELDS, TIERS  # noqa: E402
from perception import OCRUnavailable, ocr_page, vlm_page  # noqa: E402


def read_page(path: Path, lang: str, reader: str) -> str:
    if reader == "ocr":
        return ocr_page(path, lang=lang)
    if reader == "vlm":
        return vlm_page(path)
    raise ValueError(reader)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", nargs="+",
                    default=["clean", "photocopy", "fax"])
    ap.add_argument("--readers", nargs="+", default=["ocr"],
                    choices=["ocr", "vlm"])
    ap.add_argument("--tier", default="tier2",
                    help="extraction tier applied to the read text")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    gold = json.loads(Path("data/corpus/gold.json").read_text())
    if args.limit:
        gold = gold[:args.limit]
    Path("runs").mkdir(exist_ok=True)
    report = {}

    for reader in args.readers:
        for profile in args.profiles:
            key = f"{reader}:{profile}"
            cache = Path(f"runs/perception_{reader}_{profile}.jsonl")
            done = {}
            if cache.exists():
                for line in cache.read_text().splitlines():
                    r = json.loads(line)
                    done[r["doc_id"]] = r

            with cache.open("a") as f:
                for g in gold:
                    if g["doc_id"] in done:
                        continue
                    page = Path(f"data/scans/{profile}/"
                                f"{g['doc_id']}.png")
                    if not page.exists():
                        print(f"  missing scan: {page} — run "
                              f"core/scanning.py {profile}")
                        continue
                    t0 = time.time()
                    try:
                        text = read_page(page, g["language"], reader)
                    except OCRUnavailable as e:
                        sys.exit(f"\n{e}")
                    except Exception as e:
                        print(f"  {key} {g['doc_id']} ERROR {e}")
                        continue
                    pred = TIERS[args.tier](text).model_dump()
                    rec = {"doc_id": g["doc_id"], "pred": pred,
                           "chars": len(text),
                           "seconds": round(time.time() - t0, 2)}
                    f.write(json.dumps(rec, default=str) + "\n")
                    f.flush()
                    done[g["doc_id"]] = rec
                    print(f"  {key} {g['doc_id']} "
                          f"({rec['seconds']}s, {rec['chars']} chars)")

            # ---- score: abstention vs CORRUPTION ----
            n_fields = n_ok = n_abst = n_wrong = 0
            corrupted = []
            for g in gold:
                if g["doc_id"] not in done:
                    continue
                pred = done[g["doc_id"]]["pred"]
                for fld in FIELDS:
                    n_fields += 1
                    v = pred.get(fld)
                    if v is None:
                        n_abst += 1
                    elif field_correct(fld, v, g[fld]):
                        n_ok += 1
                    else:
                        n_wrong += 1
                        if fld in ("amount_eur", "event_date",
                                   "deadline_amount"):
                            corrupted.append(
                                (g["doc_id"], fld, v, g[fld]))
            if not n_fields:
                continue
            report[key] = {
                "n_docs": len(done),
                "accuracy": round(n_ok / n_fields, 4),
                "abstain_rate": round(n_abst / n_fields, 4),
                "corruption_rate": round(n_wrong / n_fields, 4),
                "mean_seconds": round(
                    sum(r["seconds"] for r in done.values())
                    / len(done), 2),
                "critical_corruptions": [
                    {"doc": d, "field": f, "read": str(v),
                     "truth": str(t)} for d, f, v, t in corrupted[:20]],
            }

    # ---------------- the table ----------------
    print(f"\n{'reader:profile':<18}{'acc':>7}{'abstain':>9}"
          f"{'CORRUPT':>9}{'s/page':>8}   what it means")
    for key, r in report.items():
        # Judge by the ABSOLUTE corruption rate, not by whether
        # abstention happens to exceed it. 14% silently-wrong fields is
        # catastrophic however many others were abstained: an abstention
        # costs attention, a corruption costs the case. (This note used
        # to compare the two rates and called 14.3% corruption "safe".)
        c = r["corruption_rate"]
        note = ("UNUSABLE: >5% of fields are silently WRONG"
                if c > 0.05 else
                "RISKY: >1% silently wrong — human review mandatory"
                if c > 0.01 else
                "acceptable: corruption <1%, misses abstain to a human")
        print(f"{key:<18}{r['accuracy']:>7.3f}{r['abstain_rate']:>9.1%}"
              f"{r['corruption_rate']:>9.1%}{r['mean_seconds']:>8.1f}"
              f"   {note}")

    crit = [(k, c) for k, r in report.items()
            for c in r["critical_corruptions"]]
    if crit:
        print(f"\n== silently WRONG values on money/date fields "
              f"({len(crit)}) ==")
        print("   these do not abstain — they route to a filing")
        for k, c in crit[:12]:
            print(f"   {k:<16}{c['doc']:<13}{c['field']:<16}"
                  f"read {c['read']!r:>16}  truth {c['truth']!r}")

    Path("models").mkdir(exist_ok=True)
    Path("models/perception_benchmark.json").write_text(
        json.dumps(report, indent=2))
    print("\nwrote models/perception_benchmark.json")


if __name__ == "__main__":
    main()
