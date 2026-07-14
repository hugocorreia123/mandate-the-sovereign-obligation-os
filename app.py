"""Mandate — The Sovereign Obligation OS: interactive demo.

Process an obligation-bearing document end-to-end (extraction tier of
your choice), watch the engine compute the deadline with its cited
trace, read the AI draft and the red-team verdict, and approve into
the hash-chained ledger. The tier badge shows which rungs of the
degradation ladder are live on this machine.

Run:  uv run streamlit run app.py
"""

import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, "core")
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from graph import ObligationGraph, ObligationStatus  # noqa: E402
from pipeline import approve, process_document  # noqa: E402

st.set_page_config(page_title="Mandate — Sovereign Obligation OS",
                   layout="wide", page_icon="⚖️")

LOG = "data/obligation_log.jsonl"
Path("data").mkdir(exist_ok=True)


# ---------------- tier availability (the ladder, live) ----------------
@st.cache_data(ttl=30)
def tier_status():
    tiers = {"tier2": True, "tier0": bool(os.environ.get(
        "GROQ_API_KEY"))}
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags",
                               timeout=1)
        tiers["tier1"] = True
    except Exception:
        tiers["tier1"] = False
    return tiers


def graph() -> ObligationGraph:
    if "graph" not in st.session_state:
        st.session_state.graph = ObligationGraph(LOG)
    return st.session_state.graph


tiers = tier_status()
TIER_LABEL = {
    "tier0": "☁️ Cloud AI",
    "tier1": "🔒 Local AI",
    "tier2": "⚙️ Rules only",
}
TIER_HELP = {
    "tier0": "Frontier model via Groq API — best quality; needs "
             "internet + API key; documents leave this machine "
             "(redaction applies in production).",
    "tier1": "Local model via Ollama on THIS machine — nothing "
             "leaves your computer; slightly lower quality, "
             "measured honestly.",
    "tier2": "Deterministic pattern-matching — no AI at all; "
             "always available, even fully offline.",
}
badge = " · ".join(
    f"{TIER_LABEL[t]} {'🟢' if tiers[t] else '⚫'}"
    for t in ("tier0", "tier1", "tier2"))

st.title("⚖️ Mandate — The Sovereign Obligation OS")
st.caption(f"**The AI proposes; the engine computes.** Deterministic "
           f"deadline engine (PT · EU packs) + governed agent crew + "
           f"tamper-evident ledger.  |  **System modes:** {badge}")
with st.expander("ℹ️ What are the system modes (degradation ladder)?"):
    st.markdown("""
Mandate is built to keep working when the cloud isn't. Extraction can
run on any of three rungs — and the **deadline engine is not AI at
all**, so due dates compute even with everything off:

| Mode | What it is | Needs | Data leaves machine? |
|---|---|---|---|
| ☁️ **Cloud AI** *(tier 0)* | Frontier LLM (Groq) | Internet + API key | Yes (redacted in production) |
| 🔒 **Local AI** *(tier 1)* | Local LLM via Ollama | Ollama running here | **No** |
| ⚙️ **Rules only** *(tier 2)* | Deterministic pattern-matching | Nothing | **No** |
| 📋 **Playbooks** *(tier 3)* | Deadline engine + humans + procedures | Nothing | **No** |

🟢 = available on this machine right now · ⚫ = not available. Lower
rungs trade quality for independence — the quality difference is
measured, not hidden (see Method tab).
""")

g = graph()
open_obls = g.open_obligations()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Open obligations", len(open_obls))
soon = [o for o in open_obls if o.deadline
        and (o.deadline.due_date - date.today()).days <= 15]
c2.metric("Due ≤ 15 days", len(soon))
c3.metric("Ledger events",
          len(Path(LOG).read_text().splitlines())
          if Path(LOG).exists() else 0)
c4.metric("Chain intact", "✅" if not Path(LOG).exists()
          or g.verify_chain() else "❌ TAMPERED")

tab_proc, tab_ledger, tab_method = st.tabs(
    ["📥 Process document", "📋 Obligation ledger", "ℹ️ Method"])

# ------------------------------------------------------------------
with tab_proc:
    left, right = st.columns([1, 1], gap="large")
    with left:
        docs_dir = Path("data/corpus/docs")
        options = (sorted(p.name for p in docs_dir.glob("*.txt"))
                   if docs_dir.exists() else [])
        pick = st.selectbox("Corpus document", options) \
            if options else None
        pasted = st.text_area("… or paste a document", height=160)
        avail = [t for t in ("tier0", "tier1", "tier2") if tiers[t]]
        tier = st.radio(
            "Extraction mode", avail, horizontal=True,
            index=len(avail) - 1,
            format_func=lambda t: TIER_LABEL[t],
            help="Which rung of the ladder reads the document. "
                 + " • ".join(f"{TIER_LABEL[t]}: {TIER_HELP[t]}"
                              for t in avail))
        st.caption(TIER_HELP[tier])
        use_llm = st.toggle(
            "AI crew: draft the response + hostile review",
            value=tiers["tier0"], disabled=not tiers["tier0"],
            help="Cloud AI drafts a formal response embedding the "
                 "engine's deadline verbatim; a second, adversarial "
                 "AI attacks the draft; only an all-green draft "
                 "reaches you for approval.")
        run = st.button("Process", type="primary")

    with right:
        if run:
            text = pasted.strip() or (
                (docs_dir / pick).read_text() if pick else "")
            if not text:
                st.error("No document.")
            else:
                drafter = red = None
                if use_llm:
                    from agents import groq_drafter, groq_red_team
                    drafter, red = groq_drafter, groq_red_team
                doc_id = (pick or "pasted").replace(".txt", "")
                with st.spinner("Running the pipeline..."):
                    res = process_document(text, doc_id, g, tier=tier,
                                           drafter=drafter,
                                           red_team=red)
                st.session_state.last = res
        res = st.session_state.get("last")
        if res:
            for line in res.trace:
                st.text(line)
            if res.obligation_id:
                o = g.obligations[res.obligation_id]
                if o.deadline:
                    st.success(f"**DUE {o.deadline.due_date.isoformat()}"
                               f"** · {o.deadline.regime}")
                    with st.expander("Deadline explanation "
                                     "(engine trace, cited)"):
                        for i, s in enumerate(o.deadline.steps, 1):
                            st.text(f"{i}. {s}")
            if res.draft:
                st.markdown("**Draft**")
                st.code(res.draft, language=None)
            if res.red_team_verdict:
                st.markdown("**Red team**")
                for c in res.red_team_verdict["checks"]:
                    (st.success if c["pass"] else st.error)(
                        c["check"], icon="✅" if c["pass"] else "❌")
                critic = res.red_team_verdict.get("llm_critic")
                if critic and critic.get("issues"):
                    st.warning("Critic issues: "
                               + "; ".join(critic["issues"]))
            if res.status == "awaiting_approval":
                if st.button("✍️ Approve (human gate)"):
                    approve(g, res.obligation_id, "demo-user")
                    st.session_state.last = None
                    st.rerun()
            elif res.status == "needs_human_extraction":
                st.info("Abstained — routed to human extraction "
                        "queue.")

# ------------------------------------------------------------------
with tab_ledger:
    if not open_obls and not g.obligations:
        st.info("Ledger empty — process a document.")
    else:
        rows = []
        for o in sorted(g.obligations.values(),
                        key=lambda x: (x.deadline.due_date if
                                       x.deadline else date.max)):
            dd = o.deadline.due_date if o.deadline else None
            days = (dd - date.today()).days if dd else None
            rows.append({
                "obligation": o.id, "type": o.type.value,
                "debtor": o.debtor, "creditor": o.creditor,
                "due": dd.isoformat() if dd else "—",
                "days left": days if days is not None else "—",
                "status": o.status.value,
                "jurisdiction": o.jurisdiction,
            })
        st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption(f"Hash chain: "
                   f"{'✅ intact' if g.verify_chain() else '❌ TAMPERED'}"
                   f" · append-only event log at {LOG}")
        with st.expander("Event log (last 10)"):
            lines = Path(LOG).read_text().splitlines()[-10:]
            for ln in lines:
                ev = json.loads(ln)
                st.text(f"{ev['ts'][:19]}  {ev['type']:<20} "
                        f"{ev['actor']}")

# ------------------------------------------------------------------
with tab_method:
    bench = Path("models/extraction_benchmark.json")
    st.markdown("""
**Doctrine.** Anything with legal consequence — deadline arithmetic,
obligation state — is deterministic, tested, source-cited code. LLM
agents extract and draft; the **engine computes**; a deterministic
red-team plus a hostile LLM critic gate every draft; a **human
approves**. Every step lands in an append-only, hash-chained log.

**Degradation ladder.** ☁️ Cloud AI (Groq) → 🔒 Local AI (Ollama,
nothing leaves the machine) → ⚙️ Rules only (no AI) → 📋 Playbooks
(the deadline engine + humans + procedures). The legally dangerous
parts — deadline arithmetic, obligation state, the ledger — are
deterministic code and never needed the cloud at all.

**Jurisdiction packs.** PT (CC art. 279.º · CPC art. 138.º · CPA
art. 87.º, férias judiciais via the Easter algorithm) and EU
(Reg. 1182/71) — 34 hand-verified deadline cases.
""")
    if bench.exists():
        st.markdown("**Extraction benchmark (per-field accuracy)**")
        st.json(json.loads(bench.read_text()))
    st.caption("Synthetic corpus; simplified source-cited rules — not "
               "legal advice. Code: github.com/hugocorreia123/"
               "mandate-the-sovereign-obligation-os")
