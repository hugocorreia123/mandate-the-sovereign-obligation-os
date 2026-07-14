"""Mandate — The Sovereign Obligation OS · public demo.

Deploy-ready, friendly for non-technical visitors. Runs on Streamlit
Community Cloud: Rules-only always available; Cloud AI enabled when a
GROQ_API_KEY secret is present; Local AI is shown as on-prem-only
(no Ollama on the cloud host). Degrades gracefully on rate limits.

Run locally:  uv run streamlit run app.py
"""

import json
import os
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, "core")
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from corpus import generate_corpus  # noqa: E402
from graph import ObligationGraph, ObligationStatus  # noqa: E402
from pipeline import approve, process_document  # noqa: E402

st.set_page_config(page_title="Mandate — Sovereign Obligation OS",
                   layout="wide", page_icon="⚖️",
                   initial_sidebar_state="collapsed")

# ------------------------------------------------------------------
# One-time setup: ensure a corpus of demo documents exists (the cloud
# host starts empty), and a fresh session ledger.
CORPUS = Path("data/corpus")
LOG = "data/session_log.jsonl"


@st.cache_resource
def _ensure_corpus():
    if not (CORPUS / "gold.json").exists():
        generate_corpus(str(CORPUS), n_per_type=8, seed=42)
    return True


_ensure_corpus()
Path("data").mkdir(exist_ok=True)

# friendly names for the sample documents
DOC_LABELS = {
    "pt_cit": "🇵🇹 Court summons (citação) — 10-day deadline to contest",
    "pt_cpa": "🇵🇹 Administrative notice — business-day deadline",
    "pt_ren": "🇵🇹 Contract non-renewal letter",
    "en_reg": "🇪🇺 EU regulatory notice — working-day deadline",
    "en_ren": "🇪🇺 EU contract non-renewal notice",
}


def doc_friendly(stem: str) -> str:
    key = stem.rsplit("_", 1)[0]
    n = stem.rsplit("_", 1)[1]
    return f"{DOC_LABELS.get(key, stem)}  (#{int(n)+1})"


# ------------------------------------------------------------------
# Tier availability — cloud-safe.
GROQ_ON = bool(os.environ.get("GROQ_API_KEY") or
               (hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets))
if GROQ_ON and not os.environ.get("GROQ_API_KEY") and \
        "GROQ_API_KEY" in getattr(st, "secrets", {}):
    os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]


@st.cache_data(ttl=20)
def ollama_up() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags",
                               timeout=1)
        return True
    except Exception:
        return False


LOCAL_ON = ollama_up()

TIERS = {
    "tier0": {"label": "☁️ Cloud AI", "on": GROQ_ON,
              "help": "A frontier AI model (via Groq) reads the "
                      "document. Best quality. Needs internet; in a "
                      "real deployment the document would be redacted "
                      "before leaving the building."},
    "tier1": {"label": "🔒 Local AI", "on": LOCAL_ON,
              "help": "A smaller AI model running on the SAME computer "
                      "— nothing leaves the machine. This is the "
                      "sovereign, on-premises tier. Not available on "
                      "this public cloud demo (no local model here), "
                      "but it runs on an ordinary laptop."},
    "tier2": {"label": "⚙️ Rules only", "on": True,
              "help": "No AI at all — deterministic pattern-matching. "
                      "Always works, even with the internet "
                      "unplugged. The safety net."},
}

# ------------------------------------------------------------------
# Session rate limit (protect the shared Groq key).
MAX_AI_RUNS = 8
if "ai_runs" not in st.session_state:
    st.session_state.ai_runs = 0


def graph() -> ObligationGraph:
    if "graph" not in st.session_state:
        # fresh per session: don't persist across visitors
        p = Path(LOG)
        if p.exists():
            p.unlink()
        st.session_state.graph = ObligationGraph(LOG)
    return st.session_state.graph


# ==================================================================
# HEADER
st.markdown(
    "<h1 style='margin-bottom:0'>⚖️ Mandate</h1>"
    "<p style='color:#8b949e;margin-top:2px;font-size:1.05rem'>"
    "The Sovereign Obligation OS — it reads a legal document, "
    "computes the real deadline under the law, drafts a response, "
    "and asks a human to approve.</p>", unsafe_allow_html=True)

badge = "  ".join(
    f"{TIERS[t]['label']} {'🟢' if TIERS[t]['on'] else '⚫'}"
    for t in ("tier0", "tier1", "tier2"))
st.caption(f"**Live system modes:** {badge}  ·  "
           f"🟢 = available now · ⚫ = on-premises only")

# ------------------------------------------------------------------
# WELCOME (first visit)
if "seen_welcome" not in st.session_state:
    st.session_state.seen_welcome = False

if not st.session_state.seen_welcome:
    with st.container(border=True):
        st.markdown("""
### 👋 New here? 30-second tour

A **contract or court letter is a machine that creates obligations** —
*"respond within 10 business days," "renew 90 days before term."*
Miss one and it costs real money. **Mandate** turns those documents
into tracked, computed, drafted actions.

**What makes it different — try it and watch:**

1. **📥 Pick a sample document** on the left (a Portuguese court
   summons, an EU regulatory notice…) and press **Process**.
2. **The deadline is computed by real code, not guessed by an AI** —
   and it *shows its work*, citing the exact legal article. Open the
   *"Deadline explanation"* to see the step-by-step reasoning.
3. **An AI drafts the response**, then a **second, hostile AI attacks
   the draft** to catch mistakes. Only a clean draft reaches you.
4. **You approve.** Nothing is ever sent automatically — a human
   always decides. Every step is recorded in a tamper-proof log.

> **The big idea:** the parts that matter legally (the deadline math,
> the record) are deterministic code that works **even with the
> internet unplugged** — so it can run inside a bank or a court that
> can't send documents to the cloud.
""")
        c1, c2 = st.columns([1, 4])
        if c1.button("Got it — let's go", type="primary"):
            st.session_state.seen_welcome = True
            st.rerun()
        c2.caption("You can reopen this anytime from the **Help** tab.")
    st.stop()

# ------------------------------------------------------------------
# METRICS
g = graph()
open_obls = g.open_obligations()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Obligations tracked", len(g.obligations))
soon = [o for o in open_obls if o.deadline
        and (o.deadline.due_date - date.today()).days <= 15]
m2.metric("Due within 15 days", len(soon))
m3.metric("Ledger events",
          len(Path(LOG).read_text().splitlines())
          if Path(LOG).exists() else 0)
m4.metric("Records intact",
          "✅ Yes" if not Path(LOG).exists() or g.verify_chain()
          else "❌ Tampered")

tab_do, tab_ledger, tab_how, tab_help = st.tabs(
    ["📥 Try it", "📋 Tracked obligations", "🔬 How it works & scores",
     "❓ Help"])

# ==================================================================
# TAB: TRY IT
with tab_do:
    left, right = st.columns([1, 1.15], gap="large")

    with left:
        st.markdown("#### 1 · Choose a document")
        docs = sorted(p.name for p in (CORPUS / "docs").glob("*.txt"))
        pick = st.selectbox(
            "Sample legal documents",
            docs, format_func=lambda s: doc_friendly(s.replace(
                ".txt", "")), label_visibility="collapsed")
        with st.expander("👀 Read this document"):
            st.text((CORPUS / "docs" / pick).read_text())

        st.markdown("#### 2 · Choose how it reads the document")
        avail = [t for t in ("tier0", "tier1", "tier2")
                 if TIERS[t]["on"]]
        # default to Cloud AI if available, else Rules
        default_ix = 0 if "tier0" in avail else len(avail) - 1
        tier = st.radio(
            "Reading mode", avail, index=default_ix,
            format_func=lambda t: TIERS[t]["label"],
            label_visibility="collapsed", horizontal=True)
        st.caption(TIERS[tier]["help"])
        if not TIERS["tier1"]["on"]:
            st.caption("💡 *Local AI (fully offline) isn't available on "
                       "this public demo, but it's the tier you'd run "
                       "on your own hardware.*")

        use_llm = st.toggle(
            "✍️ Let AI draft a response (with hostile review)",
            value=TIERS["tier0"]["on"] and tier == "tier0",
            help="A frontier AI writes a formal reply embedding the "
                 "computed deadline; a second AI tries to poke holes "
                 "in it. Needs Cloud AI.")

        ai_left = MAX_AI_RUNS - st.session_state.ai_runs
        if use_llm and TIERS["tier0"]["on"]:
            st.caption(f"🔋 Shared demo has {ai_left} AI drafts left "
                       f"this session.")

        go = st.button("▶️  Process document", type="primary",
                       use_container_width=True)

    with right:
        if go:
            if use_llm and st.session_state.ai_runs >= MAX_AI_RUNS:
                st.warning("This shared demo's AI-draft budget for "
                           "your session is used up. Switch off the "
                           "AI-draft toggle to keep using the "
                           "deterministic engine (which is the point "
                           "anyway!).")
            else:
                text = (CORPUS / "docs" / pick).read_text()
                drafter = red = None
                if use_llm and TIERS["tier0"]["on"]:
                    from agents import groq_drafter, groq_red_team
                    drafter, red = groq_drafter, groq_red_team
                    st.session_state.ai_runs += 1
                with st.spinner("Reading → computing deadline → "
                                "drafting → reviewing…"):
                    try:
                        res = process_document(
                            text, pick.replace(".txt", ""), g,
                            tier=tier, drafter=drafter, red_team=red)
                        st.session_state.last = res
                    except Exception as e:
                        st.session_state.last = None
                        st.error(f"Something went wrong (the shared "
                                 f"cloud AI may be rate-limited — try "
                                 f"Rules-only). Details: {e}")

        res = st.session_state.get("last")
        if not res:
            st.info("⬅️ Pick a document and press **Process** to watch "
                    "the pipeline run.")
        else:
            steps = {"perceive": "📖 Read the document",
                     "compile": "🗂️ Logged the obligation",
                     "compute": "📅 Computed the deadline (by code)",
                     "act": "✍️ Drafted a response",
                     "gate": "🛡️ Hostile AI reviewed the draft"}
            st.markdown("#### What happened")
            for line in res.trace:
                tag = line.split("]")[0].strip("[")
                st.markdown(f"✓ {steps.get(tag, line)}")

            if res.obligation_id:
                o = g.obligations[res.obligation_id]
                if o.deadline:
                    dd = o.deadline.due_date
                    days = (dd - date.today()).days
                    when = (f"in {days} days" if days >= 0
                            else f"{-days} days ago")
                    st.success(
                        f"### 📅 Deadline: "
                        f"**{dd.strftime('%A, %d %B %Y')}**\n"
                        f"{o.deadline.regime} · {when}")
                    with st.expander("🔍 See exactly how this date was "
                                     "computed (cited, step by step)"):
                        for i, s in enumerate(o.deadline.steps, 1):
                            st.markdown(f"**{i}.** {s}")
                        st.caption("Computed by deterministic code — "
                                   "not estimated by an AI.")

            if res.draft:
                st.markdown("#### ✍️ Drafted response")
                st.info("This is a **draft for a human to review** — "
                        "Mandate never sends anything itself.")
                st.code(res.draft, language=None)

            if res.red_team_verdict:
                checks = res.red_team_verdict["checks"]
                npass = sum(c["pass"] for c in checks)
                st.markdown(f"#### 🛡️ Hostile review — "
                            f"{npass}/{len(checks)} checks passed")
                names = {
                    "due_date_verbatim": "Draft uses the exact "
                    "computed deadline",
                    "deadline_amount_stated": "Draft states the "
                    "deadline period",
                    "amount_present": "Draft states the money amount",
                    "legal_basis_cited": "Draft cites the legal basis",
                    "llm_critic": "Passed the hostile AI reviewer"}
                for c in checks:
                    lbl = names.get(c["check"], c["check"])
                    (st.success if c["pass"] else st.error)(
                        lbl, icon="✅" if c["pass"] else "⚠️")
                crit = res.red_team_verdict.get("llm_critic")
                if crit and crit.get("issues"):
                    st.warning("Reviewer notes: "
                               + "; ".join(crit["issues"]))

            if res.status == "awaiting_approval":
                st.markdown("#### 3 · Your decision")
                st.caption("The draft passed every check. In a real "
                           "deployment, this is where a lawyer signs "
                           "off.")
                if st.button("✅ Approve this response",
                             type="primary"):
                    approve(g, res.obligation_id, "demo-visitor")
                    st.session_state.last = None
                    st.balloons()
                    st.rerun()
            elif res.status == "in_progress" and res.draft:
                st.warning("The hostile review found a problem, so this "
                           "draft was **blocked** before reaching a "
                           "human — exactly what should happen. "
                           "(Try Cloud AI for a cleaner draft.)")
            elif res.status == "in_progress":
                st.success("✅ Document read and **deadline computed** "
                           "above. Turn on the **AI-draft toggle** "
                           "(with Cloud AI) to also draft and review a "
                           "response — or just use this as a precise, "
                           "offline deadline calculator.")
            elif res.status == "needs_human_extraction":
                st.info("The reader wasn't confident enough about this "
                        "document, so it was routed to a human instead "
                        "of guessing — the safe choice.")

# ==================================================================
# TAB: LEDGER
with tab_ledger:
    st.markdown("#### Every obligation Mandate is tracking")
    st.caption("Sorted by urgency. Each row came from a document you "
               "processed. The record is tamper-proof.")
    if not g.obligations:
        st.info("Nothing tracked yet — process a document in the "
                "**Try it** tab.")
    else:
        rows = []
        for o in sorted(g.obligations.values(),
                        key=lambda x: (x.deadline.due_date if x.deadline
                                       else date.max)):
            dd = o.deadline.due_date if o.deadline else None
            days = (dd - date.today()).days if dd else None
            status_nice = {"awaiting_approval": "⏳ Awaiting approval",
                           "satisfied": "✅ Approved & done",
                           "in_progress": "🔧 Draft blocked (review)",
                           "pending": "• New"}.get(
                               o.status.value, o.status.value)
            rows.append({
                "What's owed": o.type.value,
                "Who owes it": o.debtor,
                "Owed to": o.creditor,
                "Deadline": dd.strftime("%d %b %Y") if dd else "—",
                "Days left": (f"{days}" if days is not None
                              and days >= 0 else
                              (f"{-days} overdue" if days is not None
                               else "—")),
                "Status": status_nice,
                "Where": o.jurisdiction})
        st.dataframe(rows, hide_index=True, use_container_width=True)
        ok = g.verify_chain()
        st.caption(f"🔐 Tamper-proof record: "
                   f"{'✅ intact' if ok else '❌ TAMPERED'} — "
                   f"every action is hash-chained, like a blockchain.")

# ==================================================================
# TAB: HOW IT WORKS
with tab_how:
    st.markdown("""
#### The one rule that makes Mandate different

> **The AI proposes; the engine computes.**

Anything with legal consequence — *the deadline math, the record of
what happened* — is done by **deterministic, tested code**, not by an
AI that might hallucinate. A court won't accept *"the model estimated
the 14th."* The AI's job is to *read* the document and *draft* a reply;
the important arithmetic is code that shows its work.
""")
    st.markdown("#### The safety net: it keeps working when the cloud "
                "is gone")
    st.markdown("""
Mandate reads documents on whichever of these is available — and the
deadline engine needs **none** of them:

| Mode | What it is | Works offline? |
|---|---|---|
| ☁️ **Cloud AI** | A top-tier AI model reads the document | Needs internet |
| 🔒 **Local AI** | A smaller AI on *your own* computer | ✅ Yes — nothing leaves |
| ⚙️ **Rules only** | Pattern-matching, no AI | ✅ Yes — always |
| 📋 **Playbooks** | The deadline engine + a human | ✅ Yes — the floor |

That's why a bank or a court that legally *can't* send documents to a
US cloud can still run Mandate — on their own hardware, fully offline.
""")

    st.markdown("#### We measured how good each mode is — and published "
                "it")
    st.caption("On 40 test documents. Most AI products hide their "
               "error rates; showing ours is the point.")
    st.markdown("""
- **☁️ Cloud AI:** reads correctly **99.8%** of the time.
- **🔒 Local AI (fully offline):** gets **91%** right — and crucially,
  when it's unsure it **says so and asks a human** (7% of the time)
  rather than guessing. It almost never makes something up.
- **⚙️ Rules only:** perfect on documents in the expected format;
  the dependable fallback.

The honest headline: **the offline tier trades completeness, not
correctness.** It would rather admit "I'm not sure" than invent an
answer — which is exactly what you want in law.
""")
    bench = Path("models/extraction_benchmark.json")
    if bench.exists():
        with st.expander("📊 Full per-field scores (for the technical "
                         "reader)"):
            st.json(json.loads(bench.read_text()))
    st.caption("Two jurisdictions encoded (Portugal · EU), 34 "
               "hand-verified deadline cases. Synthetic demo "
               "documents; simplified legal rules — **not legal "
               "advice.** Code: github.com/hugocorreia123/"
               "mandate-the-sovereign-obligation-os")

# ==================================================================
# TAB: HELP
with tab_help:
    st.markdown("""
#### What am I looking at?

**Mandate** is a demo of a system that manages **legal & regulatory
obligations** — the deadlines and actions that documents like court
summonses, regulator letters, and contracts create.

**How to use this demo**
1. Go to **📥 Try it**.
2. Pick a sample document and press **Process**.
3. Watch it compute the deadline (and *show its work*), draft a reply,
   and review that reply.
4. Approve the result. Check **📋 Tracked obligations** to see it
   logged.

**Common questions**

- **Is this real legal advice?** No — it's a portfolio demonstration
  with synthetic documents and simplified rules.
- **Why is "Local AI" greyed out?** This public demo runs on a shared
  cloud server with no private AI model installed. Local AI is the
  *on-premises* tier — it runs on an ordinary laptop, fully offline.
- **Why does the AI sometimes get blocked?** By design. A second,
  hostile AI reviews every draft; if it finds a problem, the draft is
  stopped before a human sees it.
- **Who built this?** Hugo Correia — Data Scientist / ML & AI
  Engineer, Lisbon. It's one of four portfolio projects spanning
  finance, industry, and law.
""")
    if st.button("🔄 Replay the welcome tour"):
        st.session_state.seen_welcome = False
        st.rerun()
    st.markdown("[⭐ View the code on GitHub]"
                "(https://github.com/hugocorreia123/"
                "mandate-the-sovereign-obligation-os)")
