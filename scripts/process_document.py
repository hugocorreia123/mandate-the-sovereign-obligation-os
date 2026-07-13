"""Mandate — CLI: process one document end-to-end.

Usage:
  uv run python scripts/process_document.py data/corpus/docs/pt_cit_000.txt
  uv run python scripts/process_document.py <path> --tier tier0 --llm
  uv run python scripts/process_document.py --approve <obligation_id>

--llm     use Groq drafter + red-team critic (needs GROQ_API_KEY)
--tier    tier0 | tier1 | tier2 extraction (default tier2)
Graph log: data/obligation_log.jsonl (hash-chained, append-only)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, "core")
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from graph import ObligationGraph  # noqa: E402
from pipeline import approve, process_document  # noqa: E402

LOG = "data/obligation_log.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("doc", nargs="?")
    ap.add_argument("--tier", default="tier2",
                    choices=["tier0", "tier1", "tier2"])
    ap.add_argument("--llm", action="store_true",
                    help="use Groq drafter + red-team")
    ap.add_argument("--approve", metavar="OBLIGATION_ID")
    args = ap.parse_args()

    Path("data").mkdir(exist_ok=True)
    g = ObligationGraph(LOG)

    if args.approve:
        approve(g, args.approve, "cli-user")
        print(f"approved {args.approve} -> SATISFIED")
        print(f"chain intact: {g.verify_chain()}")
        return

    if not args.doc:
        print("open obligations:")
        for o in g.open_obligations():
            dd = o.deadline.due_date.isoformat() if o.deadline else "—"
            print(f"  {o.id}  due {dd}  {o.status.value:<18} "
                  f"{o.description}")
        return

    text = Path(args.doc).read_text()
    drafter = red = None
    if args.llm:
        from agents import groq_drafter, groq_red_team
        drafter, red = groq_drafter, groq_red_team

    res = process_document(text, Path(args.doc).stem, g,
                           tier=args.tier, drafter=drafter,
                           red_team=red)
    print("\n".join(res.trace))
    if res.obligation_id:
        o = g.obligations[res.obligation_id]
        if o.deadline:
            print("\n--- deadline explanation (engine) ---")
            for i, s in enumerate(o.deadline.steps, 1):
                print(f"  {i}. {s}")
    if res.draft:
        print("\n--- draft ---")
        print(res.draft)
    if res.red_team_verdict:
        print("\n--- red team ---")
        for c in res.red_team_verdict["checks"]:
            print(f"  {'PASS' if c['pass'] else 'FAIL'}  {c['check']}")
        if "llm_critic" in res.red_team_verdict:
            print(f"  critic: {res.red_team_verdict['llm_critic']}")
    print(f"\nstatus: {res.status}")
    print(f"chain intact: {g.verify_chain()}")


if __name__ == "__main__":
    main()
