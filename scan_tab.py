"""The Scan tab — Phase 10's finding, made visceral.

Design: both readings are the MEASURED ones, committed in
runs/perception_{ocr,vlm}_{profile}.jsonl by the Phase 10 benchmark.
Nothing is computed on the host — no tesseract, no Ollama, no GPU, no
API key. The visitor sees exactly the numbers in the README, on the
exact pages that produced them, which is the point: this is evidence,
not a re-enactment.
"""

import json
import re
from pathlib import Path

import streamlit as st

SCANS = Path("app_data/scans")
RUNS = Path("runs")
GOLD = Path("data/corpus/gold.json")

PROFILE_HELP = {
    "clean": "A perfect digital render. The best case that never "
             "happens.",
    "photocopy": "A photocopy of a print — the everyday case in a law "
                 "firm.",
    "fax": "A fax of a photocopy. Still real, sadly.",
}


def _gold():
    return {g["doc_id"]: g for g in json.loads(GOLD.read_text())}


def _cached(reader: str, profile: str) -> dict:
    p = RUNS / f"perception_{reader}_{profile}.jsonl"
    if not p.exists():
        return {}
    return {json.loads(l)["doc_id"]: json.loads(l)["pred"]
            for l in p.read_text().splitlines()}


def _fmt(v):
    return "— (abstained)" if v is None else str(v)


def render():
    st.markdown("#### What a scanner does to a legal fact")
    st.caption(
        "Everything else in this demo reads clean text. Real "
        "obligations arrive as scans. Here is what that costs — and "
        "why the cheap, deterministic reader is the dangerous one.")

    gold = _gold()
    docs = sorted(p.stem for p in (SCANS / "fax").glob("*.png")) \
        if (SCANS / "fax").exists() else []
    if not docs:
        st.info("Sample scans aren't bundled in this deployment.")
        return

    c1, c2 = st.columns([1.2, 1])
    with c1:
        did = st.selectbox("Document", docs)
        profile = st.select_slider(
            "Scan quality", ["clean", "photocopy", "fax"],
            value="fax")
        st.caption(PROFILE_HELP[profile])
        img = SCANS / profile / f"{did}.png"
        if img.exists():
            st.image(str(img), caption=f"{did} — {profile}",
                     width='stretch')

    with c2:
        st.markdown("##### The two readers")
        st.markdown(
            "**⚙️ Classical OCR** — 0.3 s/page, free, offline. "
            "Never says *“I can't read this.”*\n\n"
            "**🔒 Local vision model** — 34.6 s/page, offline, "
            "sovereign. Abstains when unsure.")

        ocr = _cached("ocr", profile).get(did, {})
        vlm = _cached("vlm", profile).get(did, {})
        g = gold.get(did, {})
        if not ocr and not vlm:
            st.info("No measured readings cached for this "
                    "document/profile pair.")
            return

        rows, corrupted = [], 0
        for f in ("amount_eur", "event_date", "deadline_amount",
                  "debtor", "creditor", "regime_id"):
            truth = g.get(f)
            o, v = ocr.get(f), vlm.get(f)
            o_bad = o is not None and str(o) != str(truth)
            v_bad = v is not None and str(v) != str(truth)
            corrupted += o_bad
            rows.append({
                "field": f,
                "⚙️ OCR read": ("🔴 " if o_bad else "") + _fmt(o),
                "🔒 VLM read": ("🔴 " if v_bad else "") + _fmt(v),
                "truth": _fmt(truth),
            })
        st.dataframe(rows, hide_index=True, width='stretch')
        if corrupted:
            st.error(
                f"**{corrupted} field(s) silently wrong from OCR** — "
                f"note they are *plausible, well-formed values*. "
                f"Nothing downstream can catch them: they parse, they "
                f"validate, they become an obligation.", icon="🔴")
        else:
            st.success("No OCR corruption on this page at this "
                       "quality.", icon="✅")

    st.divider()
    st.markdown("##### Measured across all 40 documents, fax quality")
    st.dataframe([
        {"reader": "⚙️ Classical OCR", "accuracy": "0.255",
         "abstains": "60.2%", "silently CORRUPTS": "14.3%",
         "s/page": "0.3",
         "verdict": "UNUSABLE — >5% of fields silently wrong"},
        {"reader": "🔒 Local VLM", "accuracy": "0.929",
         "abstains": "6.6%", "silently CORRUPTS": "0.4%",
         "s/page": "34.6",
         "verdict": "acceptable — misses abstain to a human"},
    ], hide_index=True, width='stretch')
    st.markdown(
        "> **A 36× reduction in silent corruption, for 115× the "
        "latency.** Everywhere else in this system determinism is the "
        "safe floor. In perception it is the hazard — because OCR "
        "never abstains, it guesses, fluently, in the right format.\n>\n"
        "> **A second reader is an alarm:** cross-reader disagreement "
        "flagged **63 of 63** silent corruptions, with zero cases "
        "where both readers agreed on the same wrong value.")
