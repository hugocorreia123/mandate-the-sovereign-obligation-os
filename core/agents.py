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


DRAFT_PROMPT = """You are drafting a formal response/notice for the
obliged party, in the SAME LANGUAGE as the source document.

Facts you MUST use exactly as given (they were computed
deterministically; do not recalculate or reformat):
- response DEADLINE (computed): {due}. State it in ONE clear
  deadline sentence, e.g. "... até <prose date> ({due})." NEVER
  place this ISO date next to the event/citation date.
- period: {amount} {unit}
- legal basis: {basis}
- debtor (acting party): {debtor}
- creditor / addressee: {creditor}
- amount at stake: EUR {amount_eur}

Write a short formal draft (<= 200 words): acknowledge the
notification/citation of {event}, state the applicable deadline and
its legal basis, and state the action the debtor will take
({obl_type}). End with "MINUTA — CARECE DE REVISÃO POR ADVOGADO" if
Portuguese, else "DRAFT — PENDING LEGAL REVIEW".

SOURCE DOCUMENT:
{text}
"""


def groq_drafter(text, ex, deadline_result,
                 model="qwen/qwen3-32b") -> str:
    prompt = DRAFT_PROMPT.format(
        due=deadline_result.due_date.isoformat(),
        amount=ex.deadline_amount, unit=ex.deadline_unit,
        basis=ex.legal_basis, debtor=ex.debtor, creditor=ex.creditor,
        amount_eur=ex.amount_eur, event=ex.event_date,
        obl_type=ex.obligation_type, text=text[:2500])
    resp = _groq().chat.completions.create(
        model=model, temperature=0, reasoning_format="hidden",
        messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content.strip()


CRITIC_PROMPT = """You are a hostile legal reviewer. Attack this draft
against the case record. Answer ONLY JSON:
{{"pass": true/false, "issues": ["..."]}}

Fail it if: the due date differs from {due}; the period differs from
{amount} {unit}; the legal basis contradicts {basis}; parties are
swapped; any amount is invented; the language differs from the source
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
    resp = _groq().chat.completions.create(
        model=model, temperature=0, reasoning_format="hidden",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}])
    m = re.search(r"\{.*\}", resp.choices[0].message.content,
                  re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else {"pass": False,
                                                 "issues": ["no JSON"]}
    except json.JSONDecodeError:
        return {"pass": False, "issues": ["bad JSON"]}
