"""Mandate — Phase 9: blind human labelling + Cohen's kappa.

BLIND BY CONSTRUCTION. The judge's verdict is never displayed while
you label — if you saw it, the kappa would measure your suggestibility,
not the judge's reliability. Verdicts are revealed only after every
item is labelled.

You see exactly what the judge saw: the case record (with the engine's
computed deadline) and the draft. Then you answer one question.

Usage:
  uv run python scripts/label_drafts.py            # label + report
  uv run python scripts/label_drafts.py --report   # report only
  uv run python scripts/label_drafts.py --reset
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "core")

from agreement import agreement_report, render_confusion  # noqa: E402

DRAFTS = Path("runs/drafts.jsonl")
JUDGE = Path("runs/judgements.jsonl")
LABELS = Path("runs/human_labels.jsonl")

CHOICES = {"1": "GROUNDED", "2": "PARTIALLY_GROUNDED",
           "3": "UNGROUNDED", "s": None}

GUIDE = """
  1  GROUNDED           every claim traces to the record; no invention
  2  PARTIALLY_GROUNDED substantially right, but a detail is
                        unsupported, mis-stated or misleading
  3  UNGROUNDED         a central claim contradicts the record, or the
                        draft invents material facts
  s  skip     q  quit and report
"""


def load(p):
    if not p.exists():
        return {}
    return {json.loads(l)["doc_id"]: json.loads(l)
            for l in p.read_text().splitlines()}


def show(rec):
    ex = rec["extraction"]
    print("\n" + "=" * 72)
    print(f"DOCUMENT {rec['doc_id']}  ({rec['doc_type']} · "
          f"{rec['language']})")
    print("-" * 72)
    print("CASE RECORD")
    print(f"  debtor (acts) : {ex.get('debtor')}")
    print(f"  creditor      : {ex.get('creditor')}")
    print(f"  amount        : {ex.get('amount_eur')}")
    print(f"  event date    : {ex.get('event_date')}")
    print(f"  period        : {ex.get('deadline_amount')} "
          f"{ex.get('deadline_unit')}")
    print(f"  legal basis   : {ex.get('legal_basis')}")
    print(f"  DEADLINE      : {rec['due_date']}  "
          f"(engine-computed — correct by definition)")
    print("-" * 72)
    print("DRAFT UNDER AUDIT")
    print(rec["draft"])
    print("=" * 72)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    if args.reset and LABELS.exists():
        LABELS.unlink()
        print("labels cleared")

    drafts = load(DRAFTS)
    judged = load(JUDGE)
    if not drafts:
        sys.exit("no drafts — run scripts/judge_drafts.py first")

    labels = load(LABELS)
    todo = [d for d in drafts if d not in labels and d in judged]

    if not args.report and todo:
        print(f"\nBlind labelling: {len(todo)} drafts to go. "
              f"The judge's verdict is hidden until you finish.")
        print(GUIDE)
        with LABELS.open("a") as f:
            for did in todo:
                show(drafts[did])
                while True:
                    c = input("your verdict [1/2/3/s/q]: ").strip().lower()
                    if c == "q":
                        print("stopping — progress saved.")
                        todo = []
                        break
                    if c in CHOICES:
                        if CHOICES[c] is not None:
                            f.write(json.dumps(
                                {"doc_id": did,
                                 "verdict": CHOICES[c]}) + "\n")
                            f.flush()
                        break
                    print(GUIDE)
                if c == "q":
                    break
        labels = load(LABELS)

    # ---------------- report ----------------
    common = [d for d in drafts if d in labels and d in judged]
    if not common:
        sys.exit("\nnothing labelled yet — nothing to report.")
    human = [labels[d]["verdict"] for d in common]
    judge = [judged[d]["verdict"] for d in common]
    rep = agreement_report(human, judge,
                           labels=["UNGROUNDED", "PARTIALLY_GROUNDED",
                                   "GROUNDED"])

    print(f"\n=== judging the judge (n={rep['n']}) ===")
    print(f"Cohen's kappa   : {rep['cohens_kappa']}")
    print(f"raw agreement   : {rep['raw_agreement']}")
    print(f"\n{render_confusion(human, judge, ['UNGROUNDED', 'PARTIALLY_GROUNDED', 'GROUNDED'])}")
    s = rep["strictness"]
    print(f"\nstrictness      : {s['reading']}  "
          f"(mean shift {s['mean_shift']}; stricter on "
          f"{s.get('stricter_n', 0)}, lenient on "
          f"{s.get('lenient_n', 0)}, identical on {s.get('same_n', 0)})")

    # where do they agree/disagree? that is the finding.
    clear = [(h, j) for h, j in zip(human, judge)
             if h == "UNGROUNDED" or j == "UNGROUNDED"]
    if clear:
        agree_clear = sum(1 for h, j in clear if h == j)
        print(f"agreement on clearly-broken drafts: "
              f"{agree_clear}/{len(clear)}")
    border = [(h, j) for h, j in zip(human, judge)
              if "PARTIALLY_GROUNDED" in (h, j) and h != j]
    print(f"disagreements at the PARTIAL boundary: {len(border)}")

    Path("models").mkdir(exist_ok=True)
    Path("models/judge_agreement.json").write_text(
        json.dumps(rep, indent=2))
    print("\nwrote models/judge_agreement.json")


if __name__ == "__main__":
    main()
