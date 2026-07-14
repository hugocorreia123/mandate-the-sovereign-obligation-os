"""Mandate — tiered extraction (Phase 3b).

One schema, three tiers:
  tier0 — frontier LLM via Groq (JSON mode, abstain-with-null)
  tier1 — local LLM via Ollama HTTP (same prompt, same contract)
  tier2 — deterministic heuristics (regex + anchors), no network

Every tier returns an ExtractionResult; unknown fields are None
(abstention beats hallucination in legal documents). The benchmark
scores tiers per field per language against the gold set.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import date
from typing import Optional

from pydantic import BaseModel

MONTHS_PT = {m: i + 1 for i, m in enumerate(
    ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
     "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"])}
MONTHS_EN = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}


class ExtractionResult(BaseModel):
    language: Optional[str] = None
    jurisdiction: Optional[str] = None
    regime_id: Optional[str] = None
    obligation_type: Optional[str] = None
    event_date: Optional[str] = None          # ISO yyyy-mm-dd
    deadline_amount: Optional[int] = None
    deadline_unit: Optional[str] = None
    debtor: Optional[str] = None
    creditor: Optional[str] = None
    amount_eur: Optional[float] = None
    legal_basis: Optional[str] = None


FIELDS = list(ExtractionResult.model_fields)


# ================= tier 2: deterministic heuristics =================
def _pt_date_to_iso(s: str) -> Optional[str]:
    m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", s)
    if not m or m.group(2) not in MONTHS_PT:
        return None
    return date(int(m.group(3)), MONTHS_PT[m.group(2)],
                int(m.group(1))).isoformat()


def _en_date_to_iso(s: str) -> Optional[str]:
    m = re.search(r"(\d{1,2}) (\w+) (\d{4})", s)
    if not m or m.group(2) not in MONTHS_EN:
        return None
    return date(int(m.group(3)), MONTHS_EN[m.group(2)],
                int(m.group(1))).isoformat()


def _amounts(text: str, lang: str) -> list[float]:
    out = []
    if lang == "pt":
        for m in re.finditer(r"€\s*([\d.]+,\d{2})", text):
            out.append(float(m.group(1).replace(".", "")
                             .replace(",", ".")))
    else:
        for m in re.finditer(r"EUR\s*([\d,]+\.\d{2})", text):
            out.append(float(m.group(1).replace(",", "")))
    return out


def extract_tier2(text: str) -> ExtractionResult:
    r = ExtractionResult()
    pt = bool(re.search(r"\bde (janeiro|fevereiro|março|abril|maio|"
                        r"junho|julho|agosto|setembro|outubro|novembro|"
                        r"dezembro) de\b", text))
    r.language = "pt" if pt else "en"

    # regime + jurisdiction + legal basis
    if "1182/71" in text:
        r.jurisdiction = "EU"
        r.legal_basis = "Reg. 1182/71"
        r.regime_id = ("eu_1182_working_days"
                       if re.search(r"working days", text)
                       else "eu_1182_days")
    elif re.search(r"dias\s+úteis", text) or "87.º do CPA" in text:
        r.jurisdiction, r.regime_id = "PT", "cpa_uteis"
        r.legal_basis = "CPA art. 121.º + art. 87.º"
    elif "138.º" in text or "569.º" in text:
        r.jurisdiction, r.regime_id = "PT", "cpc_processual"
        r.legal_basis = "CPC art. 569.º + art. 138.º"
    elif "279.º" in text:
        r.jurisdiction, r.regime_id = "PT", "cc_corridos"
        r.legal_basis = "CC art. 279.º"

    # deadline amount/unit
    m = (re.search(r"prazo\s+de\s+(\d+)\s+dias", text)
         or re.search(r"antecedência\s+mínima\s+de\s+(\d+)\s+dias",
                      text)
         or re.search(r"within\s+(\d+)\s+(?:working\s+)?days", text)
         or re.search(r"fewer than\s+(\d+)\s+calendar\s+days", text))
    if m:
        r.deadline_amount, r.deadline_unit = int(m.group(1)), "days"

    # obligation type
    if re.search(r"contestar|observations|dizer o que se lhe oferecer",
                 text):
        r.obligation_type = "respond"
    elif re.search(r"não renovação|not to\s*\n?renew", text):
        r.obligation_type = "notify"

    # event date via anchors (distractor dates are elsewhere)
    anchor = re.search(
        r"(?:efetuada em|rececionada em|deemed received on|"
        r"being)\s+(\d{1,2}(?: de \w+ de | \w+ )\d{4})", text)
    if anchor:
        r.event_date = (_pt_date_to_iso(anchor.group(1)) if pt
                        else _en_date_to_iso(anchor.group(1)))

    # parties by document anchors
    pats = [
        (r"Fica V\. Ex\.ª,\s*(.+?),\s*na qualidade", "debtor"),
        (r"que lhe move\s+(.+?),\s*Autor", "creditor"),
        (r"fica\s+(.+?)\s+notificada", "debtor"),
        (r"vem a\s+(.+?)\s+comunicar", "debtor"),
        (r"Senhor\(a\)\s+(.+?),", "creditor"),
        (r"opened on [^,]+,\s*(.+?)\s+is\s", "debtor"),
        (r"From:\s*(.+)", "debtor"),
        (r"To:\s*(.+)", "creditor"),
    ]
    flat = " ".join(text.split())
    for pat, field in pats:
        if getattr(r, field) is None:
            m = re.search(pat, flat) or re.search(pat, text)
            if m:
                setattr(r, field, m.group(1).strip())
    # authority/court header as creditor when still unknown
    if r.creditor is None:
        first = text.splitlines()[0].strip()
        if first and "NOTICE" not in first.upper():
            r.creditor = first

    amts = _amounts(text, r.language)
    if amts:
        r.amount_eur = max(amts)  # main claim > fees/custas by design
    return r


# ================= shared LLM contract (tiers 0 & 1) =================
PROMPT = """You extract structured data from legal/administrative
documents (Portuguese or English). Return ONLY a JSON object with
exactly these keys (use null when not stated or unsure — never guess):

language: "pt" | "en"
jurisdiction: "PT" | "EU"
regime_id: "cpc_processual" | "cpa_uteis" | "cc_corridos" |
           "eu_1182_days" | "eu_1182_working_days"
obligation_type: "respond" | "pay" | "renew" | "notify" | "file"
event_date: ISO date the notice/citation was received or effected
            (NOT contract signature or proceedings-opened dates)
deadline_amount: integer number of days in the stated period
deadline_unit: "days"
debtor: party who owes the action
creditor: party owed / issuing authority or court
amount_eur: the MAIN amount at stake in EUR as a number
            (not fees/custas/taxa)
legal_basis: short statute reference as stated

regime_id guide: "dias úteis"+CPA -> cpa_uteis; CPC/art.138/569 ->
cpc_processual; Código Civil art.279 (dias corridos) -> cc_corridos;
Reg.1182/71 with "working days" -> eu_1182_working_days; Reg.1182/71
otherwise -> eu_1182_days.

DOCUMENT:
"""


def _parse_llm_json(raw: str) -> ExtractionResult:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return ExtractionResult()
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return ExtractionResult()
    clean = {k: data.get(k) for k in FIELDS}
    if isinstance(clean.get("deadline_amount"), str):
        d = re.search(r"\d+", clean["deadline_amount"])
        clean["deadline_amount"] = int(d.group(0)) if d else None
    if isinstance(clean.get("amount_eur"), str):
        s = clean["amount_eur"].replace("EUR", "").replace("€", "")
        s = s.strip().replace(".", "").replace(",", ".") \
            if s.count(",") == 1 else s.replace(",", "")
        try:
            clean["amount_eur"] = float(s)
        except ValueError:
            clean["amount_eur"] = None
    try:
        return ExtractionResult.model_validate(clean)
    except Exception:
        return ExtractionResult()


def extract_tier0(text: str,
                  model: str = "qwen/qwen3-32b") -> ExtractionResult:
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    resp = client.chat.completions.create(
        model=model, temperature=0,
        reasoning_format="hidden",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": PROMPT + text}])
    return _parse_llm_json(resp.choices[0].message.content)


def extract_tier1(text: str, model: str = "qwen2.5:7b-instruct",
                  host: str = "http://localhost:11434"
                  ) -> ExtractionResult:
    body = json.dumps({
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": PROMPT + text}],
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/chat", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as f:
        raw = json.load(f)["message"]["content"]
    return _parse_llm_json(raw)


def extract_tier0_redacted(text: str,
                           model: str = "qwen/qwen3-32b"
                           ) -> ExtractionResult:
    """Tier-0 with no PII egress: pseudonymize locally, send the
    placeholder document, restore identities from the local mapping.

    The local (offline) tier finds the names; the cloud model never
    sees them. See redaction.py and THREAT_MODEL.md.
    """
    from redaction import redact
    r = redact(text)
    out = extract_tier0(r.text, model=model)
    return ExtractionResult(**r.restore_all(out.model_dump()))


TIERS = {"tier0": extract_tier0, "tier1": extract_tier1,
         "tier2": extract_tier2,
         "tier0_redacted": extract_tier0_redacted}
