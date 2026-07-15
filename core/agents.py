"""Mandate — Phase 4: the LLM agents (drafter + red-team critic).

Both are thin, replaceable callables matching pipeline.py's injection
points. The drafter receives the ENGINE's DeadlineResult and must
embed its due date verbatim — the LLM writes prose around computed
facts, never computes them. The red-team critic is a second LLM pass
that attacks the draft against the extraction record.
"""

from __future__ import annotations

import json
import os
import re


def _groq():
    from groq import Groq
    return Groq(api_key=os.environ["GROQ_API_KEY"])


DRAFT_PROMPT = """LANGUAGE: write the ENTIRE draft in {lang_name}.
Every sentence, every heading, every date. The examples below are
SCHEMATIC — they are placeholders showing STRUCTURE, never wording or
language to copy.

You are drafting a formal response/notice for the obliged party.

Facts you MUST use exactly as given (computed deterministically — do
not recalculate, reformat or re-derive them):
- response DEADLINE (computed): {due}
- date of the event / citation / notice: {event}
- period: {amount} {unit}
- legal basis: {basis}
- debtor (the acting party): {debtor}
- creditor / addressee: {creditor}
- amount at stake: EUR {amount_eur}

RULE 1 — DATE PLACEMENT. The deadline {due} must NEVER appear beside
the event date {event}. Gluing them together states that the document
was served on the deadline: false, and materially misleading.
    WRONG:  <notice> of <EVENT DATE in prose> ({due})
    RIGHT:  <notice> of <EVENT DATE in prose>. <deadline sentence
            naming <DUE DATE in prose>> ({due}).
Put {due} in parentheses immediately after the DEADLINE's own prose
date — never after any other date.

RULE 2 — DO NOT INVENT A POSITION. State the obligation, its deadline
and its legal basis. Do NOT assert any intention, decision, agreement,
reversal or commercial position that the source document does not
contain. If the document gives notice of non-renewal, the draft
acknowledges that notice and its deadline — it does NOT announce that
the party "intends to renew", "reverses its notice", or accepts or
disputes anything. When in doubt, acknowledge and state the deadline;
silence is correct, invention is not.

Write a short formal draft (<= 200 words): acknowledge the
communication of {event}, state the applicable deadline and its legal
basis, and state only what the record supports about the required
action ({obl_type}).

End with exactly this stamp, in {lang_name}:
  Portuguese -> MINUTA — CARECE DE REVISÃO POR ADVOGADO
  English    -> DRAFT — PENDING LEGAL REVIEW

SOURCE DOCUMENT:
{text}
"""


def groq_drafter(text, ex, deadline_result,
                 model="qwen/qwen3-32b") -> str:
    lang_name = {"pt": "Portuguese (pt-PT)",
                 "en": "English"}.get(ex.language, "English")
    prompt = DRAFT_PROMPT.format(
        lang_name=lang_name,
        due=deadline_result.due_date.isoformat(),
        event=ex.event_date,
        amount=ex.deadline_amount, unit=ex.deadline_unit,
        basis=ex.legal_basis, debtor=ex.debtor, creditor=ex.creditor,
        amount_eur=ex.amount_eur,
        obl_type=ex.obligation_type, text=text[:2500])
    resp = _groq().chat.completions.create(
        model=model, temperature=0, reasoning_format="hidden",
        messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content.strip()


CRITIC_PROMPT = """You are a hostile legal reviewer. Attack this draft
against the case record. Answer ONLY JSON:
{{"pass": true/false, "issues": ["..."]}}

GROUND TRUTH: the due date {due} was computed by a deterministic
legal deadline engine and is CORRECT BY DEFINITION. Do NOT
recalculate or second-guess it. Fail the draft ONLY if the draft
STATES a different due date than {due}.

Also fail it if: the period stated differs from {amount} {unit}; the
legal basis contradicts {basis}; parties are swapped; any amount is
invented (number-format differences such as "347 213.65" vs
"347,213.65" are NOT errors); the language differs from the source
document's language.

CASE RECORD: debtor={debtor} creditor={creditor} event={event}
amount_eur={amount_eur}

DRAFT:
{draft}
"""


def groq_red_team(draft, ex, deadline_result,
                  model="qwen/qwen3-32b") -> dict:
    prompt = CRITIC_PROMPT.format(
        due=deadline_result.due_date.isoformat(),
        amount=ex.deadline_amount, unit=ex.deadline_unit,
        basis=ex.legal_basis, debtor=ex.debtor, creditor=ex.creditor,
        event=ex.event_date, amount_eur=ex.amount_eur, draft=draft)
    try:
        resp = _groq().chat.completions.create(
            model=model, temperature=0, reasoning_format="hidden",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}])
    except Exception:                       # json-mode validator can
        resp = _groq().chat.completions.create(   # 400; retry plain
            model=model, temperature=0, reasoning_format="hidden",
            messages=[{"role": "user", "content": prompt}])
    m = re.search(r"\{.*\}", resp.choices[0].message.content,
                  re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else {"pass": False,
                                                 "issues": ["no JSON"]}
    except json.JSONDecodeError:
        return {"pass": False, "issues": ["bad JSON"]}
