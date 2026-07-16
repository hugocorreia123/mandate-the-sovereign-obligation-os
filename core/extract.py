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
MONTHS_ES = {m: i + 1 for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
     "agosto", "septiembre", "octubre", "noviembre", "diciembre"])}
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
    """Parse a pt prose date, or ABSTAIN.

    OCR of a damaged page produces impossible dates ("31 de fevereiro",
    "de 20226"). Raising here would abort the whole document; the
    doctrine is to return None so the field routes to a human. Found
    by the Phase 10 scan benchmark, which crashed on a fax-quality
    page.
    """
    m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", s)
    if not m or m.group(2) not in MONTHS_PT:
        return None
    try:
        return date(int(m.group(3)), MONTHS_PT[m.group(2)],
                    int(m.group(1))).isoformat()
    except ValueError:
        return None


def _es_date_to_iso(s: str) -> Optional[str]:
    """Parse an es prose date, or ABSTAIN. Same shape as pt but a
    different month vocabulary — 'julio' is not 'julho'."""
    m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", s)
    if not m or m.group(2).lower() not in MONTHS_ES:
        return None
    try:
        return date(int(m.group(3)), MONTHS_ES[m.group(2).lower()],
                    int(m.group(1))).isoformat()
    except ValueError:
        return None


def _en_date_to_iso(s: str) -> Optional[str]:
    """Parse an en prose date, or ABSTAIN. See _pt_date_to_iso."""
    m = re.search(r"(\d{1,2}) (\w+) (\d{4})", s)
    if not m or m.group(2) not in MONTHS_EN:
        return None
    try:
        return date(int(m.group(3)), MONTHS_EN[m.group(2)],
                    int(m.group(1))).isoformat()
    except ValueError:
        return None


def _amounts(text: str, lang: str) -> list[float]:
    out = []
    if lang in ("pt", "es"):
        for m in re.finditer(r"€\s*([\d.]+,\d{2})", text):
            out.append(float(m.group(1).replace(".", "")
                             .replace(",", ".")))
    else:
        for m in re.finditer(r"EUR\s*([\d,]+\.\d{2})", text):
            out.append(float(m.group(1).replace(",", "")))
    return out


def extract_tier2(text: str) -> ExtractionResult:
    r = ExtractionResult()
    # Portuguese and Spanish SHARE two month names — "abril" and
    # "agosto" are identical in both. Month-based detection therefore
    # cannot separate pt from es on a document dated in April or
    # August: every Portuguese citação from those months was
    # classified Spanish. Disambiguate on the EXCLUSIVE months, and
    # fall back to distinctive vocabulary when only a shared month
    # appears.
    es_only = re.search(r"\bde (enero|febrero|marzo|mayo|junio|julio|"
                        r"septiembre|octubre|noviembre|diciembre) de\b",
                        text, re.I)
    pt_only = re.search(r"\bde (janeiro|fevereiro|março|maio|junho|"
                        r"julho|setembro|outubro|novembro|dezembro) de\b",
                        text, re.I)
    if es_only and not pt_only:
        r.language = "es"
    elif pt_only and not es_only:
        r.language = "pt"
    else:
        # only a shared month (abril/agosto), or none: use vocabulary
        es_words = len(re.findall(r"\b(plazo|d[ií]as h[áa]biles|"
                                  r"emplaza|demandada|conteste|"
                                  r"notificaci[óo]n|Juzgado|LEC|"
                                  r"alegaciones)\b", text, re.I))
        pt_words = len(re.findall(r"\b(prazo|dias [úu]teis|cita[çc][ãa]o|"
                                  r"R[ée]|contestar|notifica[çc][ãa]o|"
                                  r"Tribunal Judicial|CPC|querendo)\b",
                                  text, re.I))
        r.language = ("es" if es_words > pt_words
                      else "pt" if pt_words > 0 else "en")
    es = r.language == "es"
    pt = r.language == "pt"

    # regime + jurisdiction + legal basis
    if re.search(r"\bLEC\b|Ley de Enjuiciamiento Civil", text):
        r.jurisdiction, r.regime_id = "ES", "lec_habiles"
        r.legal_basis = "LEC arts. 130-133"
    elif re.search(r"Ley 39/2015|\bLPAC\b", text):
        r.jurisdiction, r.regime_id = "ES", "lpac_habiles"
        r.legal_basis = "Ley 39/2015, art. 30.2"
    elif re.search(r"d[ií]as naturales", text) and re.search(
            r"C[oó]digo Civil", text):
        r.jurisdiction, r.regime_id = "ES", "cc_naturales"
        r.legal_basis = "CC art. 5.1"
    elif "1182/71" in text:
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
    m = (re.search(r"plazo\s+de\s+(\d+)\s+d[ií]as", text)
         or re.search(r"prazo\s+de\s+(\d+)\s+dias", text)
         or re.search(r"antecedência\s+mínima\s+de\s+(\d+)\s+dias",
                      text)
         or re.search(r"within\s+(\d+)\s+(?:working\s+)?days", text)
         or re.search(r"fewer than\s+(\d+)\s+calendar\s+days", text))
    if m:
        r.deadline_amount, r.deadline_unit = int(m.group(1)), "days"

    # obligation type
    if re.search(r"contestar|conteste|observations|alegaciones|"
                 r"dizer o que se lhe oferecer", text):
        r.obligation_type = "respond"
    elif re.search(r"não renovação|not to\s*\n?renew", text):
        r.obligation_type = "notify"

    # event date via anchors (distractor dates are elsewhere)
    anchor = re.search(
        r"(?:efetuada em|efectuada en|rececionada em|notificada en|"
        r"deemed received on|being)\s+"
        r"(\d{1,2}(?: de \w+ de | \w+ )\d{4})", text)
    if anchor:
        r.event_date = (_es_date_to_iso(anchor.group(1)) if es
                        else _pt_date_to_iso(anchor.group(1)) if pt
                        else _en_date_to_iso(anchor.group(1)))

    # parties by document anchors
    pats = [
        (r"Se emplaza a\s+(.+?),\s*en calidad", "debtor"),
        (r"demanda formulada por\s+(.+?),\s*en reclamaci", "creditor"),
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
jurisdiction: "PT" | "EU" | "ES"
regime_id: "cpc_processual" | "cpa_uteis" | "cc_corridos" |
           "eu_1182_days" | "eu_1182_working_days" |
           "lec_habiles" | "lpac_habiles" | "cc_naturales"
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

regime_id guide:
  PT: "dias úteis"+CPA -> cpa_uteis; CPC/art.138/569 -> cpc_processual;
      Código Civil art.279 (dias corridos) -> cc_corridos.
  EU: Reg.1182/71 with "working days" -> eu_1182_working_days;
      Reg.1182/71 otherwise -> eu_1182_days.
  ES: LEC / "días hábiles" in a court context -> lec_habiles;
      Ley 39/2015 or LPAC (administrative) -> lpac_habiles;
      "días naturales" / Código Civil art. 5 -> cc_naturales.

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
