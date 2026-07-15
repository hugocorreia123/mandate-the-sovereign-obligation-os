"""Mandate — Phase 9 runner: generate drafts, then judge them.

Cross-family by design: the drafter is qwen3-32b, the judge is
gpt-oss-120b. A model grading its own family's output is a
self-assessment, not an audit.

The judge sees a fixed EVIDENCE PACK (the extraction record + the
engine's computed deadline and its cited trace) and the draft. It never
sees the gold answers. It returns a verdict plus typed issues, so we
learn HOW drafts fail, not merely that they do.

Resumable: runs/drafts.jsonl and runs/judgements.jsonl are caches.

Usage:
  uv run python scripts/judge_drafts.py --n 24 --tier tier0
  uv run python scripts/judge_drafts.py --judge-only
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, "core")
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from agents import groq_drafter  # noqa: E402
from engine import compute_deadline  # noqa: E402
from extract import TIERS  # noqa: E402
from pack_eu import EU  # noqa: E402
from pack_pt import PT  # noqa: E402

PACKS = {"PT": PT, "EU": EU}
DRAFTS = Path("runs/drafts.jsonl")
JUDGE = Path("runs/judgements.jsonl")

JUDGE_PROMPT = """You are auditing a legal draft for GROUNDEDNESS: is
every factual claim in the draft supported by THE SOURCE DOCUMENT or
the computed record below?

Two things you are NOT asked:
  * whether the deadline is legally correct — it was computed by a
    deterministic engine and is correct by definition;
  * whether a detail is absent from the extracted record — the record
    is an 11-field SUMMARY, not the evidence. A draft may legitimately
    cite anything in the SOURCE DOCUMENT: the case number, the court,
    the contract date, the reference number. Those are NOT inventions.

An invention is a claim supported by NEITHER the source document NOR
the computed record.

NOT inventions (do not flag these):
  * the mandatory review stamp ("MINUTA — CARECE DE REVISÃO POR
    ADVOGADO" / "DRAFT — PENDING LEGAL REVIEW") — it is required by
    policy and is meant to be absent from the source;
  * standard salutations, addresses, signature placeholders;
  * restating the computed deadline.

Return ONLY JSON:
{{"verdict": "GROUNDED" | "PARTIALLY_GROUNDED" | "UNGROUNDED",
  "issues": [{{"type": "...", "detail": "..."}}]}}

verdict:
  GROUNDED           - every claim traces to the record; no invention
  PARTIALLY_GROUNDED - substantially right, but at least one detail is
                       unsupported, mis-stated or misleading
  UNGROUNDED         - a central claim contradicts the record, or the
                       draft invents material facts

issue types to use: wrong_date, wrong_amount, parties_swapped,
invented_fact, wrong_legal_basis, misleading_phrasing,
wrong_language, missing_review_stamp, other

SOURCE DOCUMENT (the ground truth for every factual claim)
---------------------------------------------------------
{source}

COMPUTED RECORD (a summary — absence here is NOT evidence of invention)
-----------------------------------------------------------------------
document language : {language}
jurisdiction      : {jurisdiction}
debtor (acts)     : {debtor}
creditor (owed)   : {creditor}
amount at stake   : {amount}
event date        : {event_date}
period            : {amount_days} {unit}
legal basis       : {legal_basis}
COMPUTED DEADLINE : {due}   <- correct by definition
engine trace      : {trace}

DRAFT UNDER AUDIT
-----------------
{draft}
"""


def _groq():
    from groq import Groq
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def judge_draft(rec: dict, model: str = "openai/gpt-oss-120b") -> dict:
    ex = rec["extraction"]
    prompt = JUDGE_PROMPT.format(
        source=rec.get("source_text", "(source unavailable)")[:3000],
        language=ex.get("language"), jurisdiction=ex.get("jurisdiction"),
        debtor=ex.get("debtor"), creditor=ex.get("creditor"),
        amount=ex.get("amount_eur"), event_date=ex.get("event_date"),
        amount_days=ex.get("deadline_amount"),
        unit=ex.get("deadline_unit"), legal_basis=ex.get("legal_basis"),
        due=rec["due_date"], trace=" | ".join(rec["trace"][:4]),
        draft=rec["draft"])
    try:
        resp = _groq().chat.completions.create(
            model=model, temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}])
    except Exception:
        resp = _groq().chat.completions.create(
            model=model, temperature=0,
            messages=[{"role": "user", "content": prompt}])
    raw = resp.choices[0].message.content
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"verdict": "UNGROUNDED",
                "issues": [{"type": "other", "detail": "no JSON"}]}
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"verdict": "UNGROUNDED",
                "issues": [{"type": "other", "detail": "bad JSON"}]}
    v = str(d.get("verdict", "")).upper()
    if v not in ("GROUNDED", "PARTIALLY_GROUNDED", "UNGROUNDED"):
        v = "UNGROUNDED"
    return {"verdict": v, "issues": d.get("issues", [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--tier", default="tier0")
    ap.add_argument("--judge-only", action="store_true")
    ap.add_argument("--pace", type=float, default=3.0,
                    help="seconds between calls (free-tier TPM guard)")
    args = ap.parse_args()
    Path("runs").mkdir(exist_ok=True)

    gold = json.loads(Path("data/corpus/gold.json").read_text())
    # stratify across the five document types
    by_type: dict[str, list] = {}
    for g in gold:
        by_type.setdefault(g["doc_type"], []).append(g)
    picked, i = [], 0
    while len(picked) < args.n and i < 20:
        for t in sorted(by_type):
            if i < len(by_type[t]) and len(picked) < args.n:
                picked.append(by_type[t][i])
        i += 1

    # ---------------- drafts ----------------
    done = {}
    if DRAFTS.exists():
        for line in DRAFTS.read_text().splitlines():
            r = json.loads(line)
            done[r["doc_id"]] = r

    if not args.judge_only:
        with DRAFTS.open("a") as f:
            for g in picked:
                if g["doc_id"] in done:
                    continue
                text = Path("data/corpus/docs",
                            f"{g['doc_id']}.txt").read_text()
                draft = None
                for attempt in range(4):
                    try:
                        ex = TIERS[args.tier](text)
                        r = compute_deadline(
                            PACKS[ex.jurisdiction], ex.regime_id,
                            date.fromisoformat(ex.event_date),
                            ex.deadline_amount, ex.deadline_unit)
                        draft = groq_drafter(text, ex, r)
                        break
                    except Exception as e:
                        if "rate_limit" in str(e) and attempt < 3:
                            wait = args.pace * (2 ** attempt) + 4
                            print(f"  {g['doc_id']} rate-limited, "
                                  f"waiting {wait:.0f}s "
                                  f"(attempt {attempt + 1}/4)")
                            time.sleep(wait)
                            continue
                        print(f"  {g['doc_id']} SKIP ({e})")
                        break
                if draft is None:
                    continue
                rec = {"doc_id": g["doc_id"],
                       "doc_type": g["doc_type"],
                       "language": g["language"],
                       "source_text": text,
                       "extraction": ex.model_dump(),
                       "due_date": r.due_date.isoformat(),
                       "trace": r.steps, "draft": draft}
                f.write(json.dumps(rec, default=str) + "\n")
                f.flush()
                done[g["doc_id"]] = rec
                print(f"  drafted {g['doc_id']}")
                time.sleep(args.pace)

    # ---------------- judge ----------------
    judged = {}
    if JUDGE.exists():
        for line in JUDGE.read_text().splitlines():
            r = json.loads(line)
            judged[r["doc_id"]] = r

    with JUDGE.open("a") as f:
        for did, rec in done.items():
            if did in judged:
                continue
            for attempt in range(4):
                try:
                    v = judge_draft(rec)
                    break
                except Exception as e:
                    if "rate_limit" in str(e) and attempt < 3:
                        wait = args.pace * (2 ** attempt) + 4
                        print(f"  {did} rate-limited, waiting "
                              f"{wait:.0f}s")
                        time.sleep(wait)
                        continue
                    print(f"  {did} JUDGE SKIP ({e})")
                    v = None
                    break
            if v is None:
                continue
            out = {"doc_id": did, "verdict": v["verdict"],
                   "issues": v["issues"]}
            f.write(json.dumps(out) + "\n")
            f.flush()
            judged[did] = out
            print(f"  judged {did}: {v['verdict']}")
            time.sleep(args.pace)

    # ---------------- summary ----------------
    from collections import Counter
    verdicts = Counter(j["verdict"] for j in judged.values())
    score = {"GROUNDED": 1.0, "PARTIALLY_GROUNDED": 0.5,
             "UNGROUNDED": 0.0}
    vals = [score[j["verdict"]] for j in judged.values()]
    missing = [g["doc_id"] for g in picked if g["doc_id"] not in judged]
    if missing:
        print(f"\n!! {len(missing)} of {len(picked)} requested "
              f"documents are MISSING (rate limits): {missing}")
        print("   rerun the same command — the cache resumes.")
    print(f"\n== judge summary (n={len(judged)}) ==")
    for v, c in verdicts.most_common():
        print(f"  {v:<20}{c:>4}")
    print(f"  mean groundedness: "
          f"{sum(vals)/max(len(vals),1):.3f}")
    issues = Counter(i.get("type", "other")
                     for j in judged.values() for i in j["issues"])
    if issues:
        print("\n  issue taxonomy (HOW drafts fail):")
        for t, c in issues.most_common():
            print(f"    {t:<24}{c:>4}")
    Path("models").mkdir(exist_ok=True)
    Path("models/judge_summary.json").write_text(json.dumps(
        {"n": len(judged), "verdicts": dict(verdicts),
         "mean_groundedness": round(sum(vals)/max(len(vals), 1), 4),
         "issues": dict(issues)}, indent=2))
    print("\nwrote models/judge_summary.json")
    print("NEXT: label them blind ->  uv run python "
          "scripts/label_drafts.py")


if __name__ == "__main__":
    main()
