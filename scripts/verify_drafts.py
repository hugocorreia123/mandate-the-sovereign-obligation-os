"""Mandate — verify drafts with DETERMINISTIC checks, not the judge.

The judge has kappa 0.615 against blind human labels and caught 0 of 4
clearly-broken drafts (Phase 9). Its taxonomy is a hypothesis. These
checks are validated 7/7 against real human labels, so they are
evidence.

Usage:  uv run python scripts/verify_drafts.py
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "core")

from pipeline import (_date_juxtaposition_ok,  # noqa: E402
                      _no_amount_in_words)

DRAFTS = Path("runs/drafts.jsonl")


def language_ok(draft: str, lang: str) -> bool:
    """Did the draft answer in the document's language?

    Cheap, deterministic marker counting — no model needed.
    """
    pt = len(re.findall(r"\b(prazo|nos termos|notificação|citação|"
                        r"artigo|conhecimento|contestação|renovação|"
                        r"Exmo|MINUTA|advogado)\b", draft, re.I))
    en = len(re.findall(r"\b(deadline|pursuant|notice|acknowledges|"
                        r"Regulation|hereby|Dear|Sincerely|DRAFT|"
                        r"pending legal review)\b", draft, re.I))
    return (pt > en) if lang == "pt" else (en > pt)


def stamp_ok(draft: str) -> bool:
    return bool(re.search(r"MINUTA|PENDING LEGAL REVIEW|"
                          r"CARECE DE REVIS", draft, re.I))


def main():
    if not DRAFTS.exists():
        sys.exit("no runs/drafts.jsonl — run scripts/judge_drafts.py")
    rows = [json.loads(l) for l in DRAFTS.read_text().splitlines()]
    fails = {"date_juxtaposition": [], "amount_in_words": [],
             "wrong_language": [], "missing_stamp": [],
             "due_absent": [], "letter_dated_with_deadline": []}
    for r in rows:
        ex, draft = r["extraction"], r["draft"]
        due = date.fromisoformat(r["due_date"])
        ev = date.fromisoformat(ex["event_date"])
        if not _date_juxtaposition_ok(draft, ev, due):
            fails["date_juxtaposition"].append(r["doc_id"])
        if not _no_amount_in_words(draft):
            fails["amount_in_words"].append(r["doc_id"])
        # the deadline must not be used as the letter's own date
        if re.search(rf"^\s*(Data|Date)\s*:?\s*{re.escape(r['due_date'])}",
                     draft, re.M | re.I):
            fails["letter_dated_with_deadline"].append(r["doc_id"])
        if not language_ok(draft, r["language"]):
            fails["wrong_language"].append(r["doc_id"])
        if not stamp_ok(draft):
            fails["missing_stamp"].append(r["doc_id"])
        if r["due_date"] not in draft:
            fails["due_absent"].append(r["doc_id"])

    n = len(rows)
    print(f"\n== deterministic verification of {n} drafts ==")
    print("   (these checks are validated against blind human labels;")
    print("    the LLM judge's taxonomy is not)\n")
    print(f"{'check':<24}{'fails':>7}{'rate':>9}   documents")
    for k, v in fails.items():
        print(f"{k:<24}{len(v):>7}{len(v)/n:>8.1%}   "
              f"{', '.join(v[:4]) + ('…' if len(v) > 4 else '')}")
    clean = sum(1 for r in rows
                if r["doc_id"] not in set(sum(fails.values(), [])))
    print(f"\nfully clean drafts: {clean}/{n} ({clean/n:.1%})")


if __name__ == "__main__":
    main()
