"""Mandate — Phase 18: the README's numbers are outputs, not claims.

An uncomfortable observation motivates this module. The README says
tier0 scores 1.00, that OCR silently corrupts 14.3% of fields, that
cross-reader disagreement caught 63 of 63. Every one of those was true
the day it was measured, and NOTHING has checked it since. They are
assertions with a timestamp — which is exactly what this project spent
four phases criticising in other people's evaluations.

So: every number quoted in the README is REGENERATED here from
committed evidence, on every commit, and CI fails if one drifts. A
claim that cannot be reproduced by a script is a claim that has
already started rotting.

Three honest categories, kept separate because conflating them is how
a scorecard becomes theatre:

  VERIFIED    recomputed right now from committed evidence. If the
              code changes and the number moves, this fails.
  PINNED      recomputed from a committed CACHE of model output
              (runs/*.jsonl). The models are not re-run — that needs
              keys and a GPU — but the SCORING is, so a scorer bug or
              a schema change is caught. The cache is evidence; it is
              not a live measurement, and this says so.
  UNVERIFIED  requires a key, a model, or a human. Named, not hidden.
              An unverifiable claim is not a scandal; an unverifiable
              claim presented as verified is.

Usage:
  uv run python scripts/scorecard.py            # print + verify
  uv run python scripts/scorecard.py --update   # re-pin the claims
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, "core")
sys.path.insert(0, "scripts")

CLAIMS_FILE = Path("models/claims.json")


class Kind:
    VERIFIED = "verified"
    PINNED = "pinned"
    UNVERIFIED = "unverified"


@dataclass
class Claim:
    key: str
    label: str
    kind: str
    compute: Optional[Callable[[], Optional[float]]] = None
    tolerance: float = 0.0
    note: str = ""
    evidence: str = ""


@dataclass
class Result:
    claim: Claim
    value: Optional[float]
    pinned: Optional[float]
    status: str          # ok | DRIFT | missing | unverified
    detail: str = ""


# ------------------------------------------------------- computations
def _count_tests(name: str, marker: str = "def test_") -> float:
    """Count the hand-verified cases. Looks in tests/ and the repo
    root, because a scorecard that silently reports 'no evidence'
    when the file merely moved is a scorecard that will be ignored."""
    for p in (Path("tests") / name, Path(name)):
        if p.exists():
            return float(p.read_text().count(marker))
    return None


def _pytest_total() -> Optional[float]:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q",
                        "--collect-only"], capture_output=True,
                       text=True)
    for line in reversed(r.stdout.splitlines()):
        if "test" in line and "collected" in line:
            for tok in line.split():
                if tok.isdigit():
                    return float(tok)
    return None


def _extraction_macro(tier: str, lang: Optional[str] = None
                      ) -> Optional[float]:
    """Re-score the cached extractions. The model is not re-run; the
    SCORER is — which is what catches a scorer bug or a schema drift."""
    runs = Path(f"runs/extractions_{tier}.jsonl")
    gold_f = Path("data/corpus/gold.json")
    if not runs.exists() or not gold_f.exists():
        return None
    from benchmark_extraction import field_correct
    from extract import FIELDS
    gold = {g["doc_id"]: g for g in json.loads(gold_f.read_text())}
    preds = {json.loads(l)["doc_id"]: json.loads(l)["pred"]
             for l in runs.read_text().splitlines()}
    docs = [d for d in preds if d in gold
            and (lang is None or gold[d]["language"] == lang)]
    if not docs:
        return None
    per_field = []
    for f in FIELDS:
        ok = sum(1 for d in docs
                 if field_correct(f, preds[d].get(f), gold[d][f]))
        per_field.append(ok / len(docs))
    return round(sum(per_field) / len(per_field), 4)


def _perception_rate(reader: str, profile: str, what: str
                     ) -> Optional[float]:
    runs = Path(f"runs/perception_{reader}_{profile}.jsonl")
    gold_f = Path("data/corpus/gold.json")
    if not runs.exists() or not gold_f.exists():
        return None
    from benchmark_extraction import field_correct
    from extract import FIELDS
    gold = {g["doc_id"]: g for g in json.loads(gold_f.read_text())}
    preds = {json.loads(l)["doc_id"]: json.loads(l)["pred"]
             for l in runs.read_text().splitlines()}
    n = ok = ab = wr = 0
    for d, p in preds.items():
        if d not in gold:
            continue
        for f in FIELDS:
            n += 1
            v = p.get(f)
            if v is None:
                ab += 1
            elif field_correct(f, v, gold[d][f]):
                ok += 1
            else:
                wr += 1
    if not n:
        return None
    return round({"accuracy": ok / n, "abstain": ab / n,
                  "corrupt": wr / n}[what], 4)


def _crossreader_catch_rate() -> Optional[float]:
    """The 63/63 claim: does reader disagreement still catch every
    silent OCR corruption?"""
    gold_f = Path("data/corpus/gold.json")
    o = Path("runs/perception_ocr_fax.jsonl")
    v = Path("runs/perception_vlm_fax.jsonl")
    if not (gold_f.exists() and o.exists() and v.exists()):
        return None
    from benchmark_extraction import field_correct
    from extract import FIELDS
    gold = {g["doc_id"]: g for g in json.loads(gold_f.read_text())}
    ocr = {json.loads(l)["doc_id"]: json.loads(l)["pred"]
           for l in o.read_text().splitlines()}
    vlm = {json.loads(l)["doc_id"]: json.loads(l)["pred"]
           for l in v.read_text().splitlines()}
    corrupt = caught = 0
    for d in set(ocr) & set(vlm) & set(gold):
        for f in FIELDS:
            a, b = ocr[d].get(f), vlm[d].get(f)
            if a is None or field_correct(f, a, gold[d][f]):
                continue
            corrupt += 1
            agree = (b is not None
                     and str(a).strip().lower() == str(b).strip().lower())
            if not agree:
                caught += 1
    if not corrupt:
        return None
    return round(caught / corrupt, 4)


def _from_json(path: str, *keys, min_n: Optional[int] = None
               ) -> Optional[float]:
    """Read a measured value — and refuse it if the run behind it was
    too small to be the claim.

    This module pinned a groundedness of 0.9167 that came from a
    SIX-document run killed by a quota, while every full run measured
    0.938 on twenty-four. The file said nothing about which it was, and
    the scorecard trusted it — the precise failure it exists to
    prevent, committed by the thing preventing it. A number without its
    n is not a measurement.
    """
    p = Path(path)
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    if min_n is not None:
        n = d.get("n")
        if n is None:
            raise ValueError(
                f"{path} records no n — a number without its sample "
                f"size cannot be a claim")
        if n < min_n:
            raise ValueError(
                f"{path} was measured on n={n}, and this claim is "
                f"defined at n>={min_n}. A partial run is not a "
                f"smaller measurement, it is a different one. "
                f"Re-run the evaluation.")
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return float(d) if isinstance(d, (int, float)) else None


# ------------------------------------------------------------ claims
def claims() -> list[Claim]:
    return [
        # ---------- deterministic: recomputed, always ----------
        Claim("deadline_cases_pt", "PT deadline cases, hand-verified",
              Kind.VERIFIED,
              lambda: _count_tests("test_pt_deadlines.py"),
              evidence="tests/test_pt_deadlines.py"),
        Claim("deadline_cases_eu", "EU deadline cases, hand-verified",
              Kind.VERIFIED,
              lambda: _count_tests("test_eu_deadlines.py"),
              evidence="tests/test_eu_deadlines.py"),
        Claim("deadline_cases_es", "ES deadline cases, hand-verified",
              Kind.VERIFIED,
              lambda: _count_tests("test_es_deadlines.py"),
              evidence="tests/test_es_deadlines.py"),
        Claim("tests_total", "tests in the suite", Kind.VERIFIED,
              _pytest_total, tolerance=0,
              evidence="pytest --collect-only"),
        Claim("tier2_macro", "Rules-only extraction (template-fit)",
              Kind.VERIFIED,
              lambda: _extraction_macro("tier2"), tolerance=0.001,
              note="deterministic — no model, so a drift here is a "
                   "code change",
              evidence="runs/extractions_tier2.jsonl"),

        # ---------- pinned: the cache is re-scored, not re-run ------
        Claim("tier0_macro", "Cloud AI extraction, macro", Kind.PINNED,
              lambda: _extraction_macro("tier0"), tolerance=0.005,
              note="model output cached; the SCORER is re-run",
              evidence="runs/extractions_tier0.jsonl"),
        Claim("tier1_macro", "Local AI extraction, macro", Kind.PINNED,
              lambda: _extraction_macro("tier1"), tolerance=0.005,
              evidence="runs/extractions_tier1.jsonl"),
        Claim("tier1_macro_pt", "Local AI, pt", Kind.PINNED,
              lambda: _extraction_macro("tier1", "pt"),
              tolerance=0.005,
              note="measured per language because an aggregate hides "
                   "asymmetry",
              evidence="runs/extractions_tier1.jsonl + gold.json[pt]"),
        Claim("tier1_macro_en", "Local AI, en", Kind.PINNED,
              lambda: _extraction_macro("tier1", "en"),
              tolerance=0.005,
              evidence="runs/extractions_tier1.jsonl + gold.json[en]"),
        Claim("ocr_fax_corrupt", "OCR silently corrupts (fax)",
              Kind.PINNED,
              lambda: _perception_rate("ocr", "fax", "corrupt"),
              tolerance=0.005,
              note="the headline of Phase 10",
              evidence="runs/perception_ocr_fax.jsonl"),
        Claim("vlm_fax_corrupt", "Local VLM silently corrupts (fax)",
              Kind.PINNED,
              lambda: _perception_rate("vlm", "fax", "corrupt"),
              tolerance=0.005,
              evidence="runs/perception_vlm_fax.jsonl"),
        Claim("vlm_fax_accuracy", "Local VLM accuracy (fax)",
              Kind.PINNED,
              lambda: _perception_rate("vlm", "fax", "accuracy"),
              tolerance=0.005,
              evidence="runs/perception_vlm_fax.jsonl"),
        Claim("crossreader_catch", "disagreement catches OCR lies",
              Kind.PINNED, _crossreader_catch_rate, tolerance=0.001,
              note="the 63/63 claim",
              evidence="runs/perception_{ocr,vlm}_fax.jsonl"),
        Claim("judge_groundedness",
              "judge mean groundedness (n>=24)", Kind.PINNED,
              lambda: _from_json("models/judge_summary.json",
                                 "mean_groundedness", min_n=24),
              tolerance=0.001,
              note="fixed evidence pack; REJECTED unless n>=24 — a "
                   "quota-truncated run is a different claim",
              evidence="models/judge_summary.json"),
        Claim("judge_n", "documents behind the groundedness score",
              Kind.PINNED,
              lambda: _from_json("models/judge_summary.json", "n"),
              tolerance=0,
              note="published so the score above can never be quoted "
                   "without its sample size",
              evidence="models/judge_summary.json"),
        Claim("judge_kappa", "judge vs blind human labels (κ, n=22)",
              Kind.PINNED,
              lambda: _from_json("models/judge_agreement.json",
                                 "cohens_kappa", min_n=20),
              tolerance=0.001,
              note="MEASURED AGAINST THE PRE-FIX HARNESS — retained "
                   "as evidence of failure, not as validation of the "
                   "current judge",
              evidence="models/judge_agreement.json"),

        # ---------- honestly out of reach ----------
        Claim("appliance_sovereign", "the appliance cannot phone home",
              Kind.UNVERIFIED,
              note="needs a Docker host; `docker compose exec mandate "
                   "python scripts/verify_sovereignty.py` exits "
                   "non-zero if it can. CI cannot run it; a human can, "
                   "and must."),
        Claim("judge_kappa_postfix",
              "judge vs blind labels, AFTER the harness fix",
              Kind.UNVERIFIED,
              note="requires a fresh blind-labelling round by a human. "
                   "Until then no κ describes the current judge, and "
                   "the README says so."),
    ]


# ------------------------------------------------------------ engine
def run(update: bool = False) -> tuple[list[Result], bool]:
    pinned = (json.loads(CLAIMS_FILE.read_text())
              if CLAIMS_FILE.exists() else {})
    results, failed = [], False

    for c in claims():
        if c.kind is Kind.UNVERIFIED or c.compute is None:
            results.append(Result(c, None, None, "unverified"))
            continue
        try:
            v = c.compute()
        except Exception as e:
            results.append(Result(c, None, pinned.get(c.key),
                                  "missing", f"{type(e).__name__}: {e}"))
            continue
        if v is None:
            results.append(Result(c, None, pinned.get(c.key), "missing",
                                  f"no evidence at {c.evidence}"))
            continue
        p = pinned.get(c.key)
        if update or p is None:
            results.append(Result(c, v, v, "ok",
                                  "pinned" if update else "new"))
            pinned[c.key] = v
            continue
        drift = abs(v - p)
        if drift > c.tolerance:
            failed = True
            results.append(Result(c, v, p, "DRIFT",
                                  f"was {p}, now {v} "
                                  f"(Δ{drift:+.4f} > {c.tolerance})"))
        else:
            results.append(Result(c, v, p, "ok"))

    if update:
        CLAIMS_FILE.parent.mkdir(exist_ok=True)
        CLAIMS_FILE.write_text(json.dumps(pinned, indent=2,
                                          sort_keys=True))
    return results, failed


def render(results: list[Result]) -> str:
    icon = {"ok": "✓", "DRIFT": "✗", "missing": "·",
            "unverified": "?"}
    out = ["", "=" * 74,
           "  SCORECARD — every number in the README, recomputed",
           "=" * 74, ""]
    for kind, title in (
            (Kind.VERIFIED,
             "VERIFIED — recomputed now; a code change moves these"),
            (Kind.PINNED,
             "PINNED — cached model output, re-scored (not re-run)"),
            (Kind.UNVERIFIED,
             "UNVERIFIED — needs a key, a model, or a human")):
        rows = [r for r in results if r.claim.kind == kind]
        if not rows:
            continue
        out.append(f"  {title}")
        for r in rows:
            val = ("—" if r.value is None
                   else f"{r.value:g}")
            out.append(f"    {icon[r.status]} {r.claim.label:<44}"
                       f"{val:>10}   {r.detail or r.claim.note[:40]}")
        out.append("")
    drift = [r for r in results if r.status == "DRIFT"]
    if drift:
        out.append(f"  ✗ {len(drift)} CLAIM(S) DRIFTED. The README now "
                   f"says something untrue.")
        for r in drift:
            out.append(f"      {r.claim.key}: {r.detail}")
        out.append("")
    missing = [r for r in results if r.status == "missing"]
    if missing:
        out.append(f"  · {len(missing)} claim(s) have no evidence in "
                   f"this checkout — regenerate the runs to verify "
                   f"them.")
        out.append("")
    out.append("=" * 74)
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true",
                    help="re-pin every claim to its current value")
    args = ap.parse_args()
    results, failed = run(update=args.update)
    print(render(results))
    if args.update:
        print(f"pinned {len(json.loads(CLAIMS_FILE.read_text()))} "
              f"claims to {CLAIMS_FILE}\n")
        sys.exit(0)
    if failed:
        print("FAILING: a published number no longer matches the "
              "evidence.\n")
        sys.exit(1)
