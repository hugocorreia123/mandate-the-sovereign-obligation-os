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
- amount at stake: {amount_line}

RULE 1 — DATE PLACEMENT. The deadline {due} must NEVER appear beside
the event date {event}. Gluing them together states that the document
was served on the deadline: false, and materially misleading.
    WRONG:  <notice> of <EVENT DATE in prose> ({due})
    RIGHT:  <notice> of <EVENT DATE in prose>. <deadline sentence
            naming <DUE DATE in prose>> ({due}).
Put {due} in parentheses immediately after the DEADLINE's own prose
date — never after any other date.

RULE 2 — DO NOT INVENT. State the obligation, its deadline and its
legal basis. Do NOT assert anything the source document does not
contain, including:
  * an intention, decision, agreement, reversal or commercial position
    ("intends to renew", "reverses its notice", accepts, disputes);
  * a LEGAL CONSEQUENCE ("results in automatic termination", "under
    penalty of...", "the rent remains applicable until...") — if the
    document does not state the consequence, neither do you;
  * the ABSENCE of something. If no amount is given above, say nothing
    about amounts. NEVER write "no amount is due" — you do not know
    that.
When in doubt: acknowledge, state the deadline, stop. Silence is
correct; invention is not.

RULE 3 — AMOUNTS IN DIGITS ONLY. Write {amount_eur_digits} exactly as
given, in digits. NEVER spell an amount in words: a draft wrote
"duzentos e dez euros" for 2.100,68 € — off by a factor of ten, in a
legal filing. No words, no parenthetical spelling-out, no rounding.

RULE 4 — DO NOT DATE THE LETTER WITH THE DEADLINE. {due} is the
response deadline, not the date of your draft. Leave the letter's own
date as a placeholder or omit it entirely.

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
                 model="openai/gpt-oss-120b") -> str:
    lang_name = {"pt": "Portuguese (pt-PT)",
                 "en": "English"}.get(ex.language, "English")
    # never render "EUR None" — the model reads it as "nothing is due"
    amount_line = (f"EUR {ex.amount_eur}" if ex.amount_eur is not None
                   else "NOT STATED — say nothing about amounts")
    prompt = DRAFT_PROMPT.format(
        lang_name=lang_name,
        amount_line=amount_line,
        amount_eur_digits=(ex.amount_eur if ex.amount_eur is not None
                           else "(no amount)"),
        due=deadline_result.due_date.isoformat(),
        event=ex.event_date,
        amount=ex.deadline_amount, unit=ex.deadline_unit,
        basis=ex.legal_basis, debtor=ex.debtor, creditor=ex.creditor,
        obl_type=ex.obligation_type, text=text[:2500])
    # An empty draft is the worst failure mode in this system: the
    # judge scores it GROUNDED (it makes no false claims), so the
    # metric REWARDS silence. Found in Phase 9 when groundedness hit
    # its best-ever 0.938 on a batch where 4 of 24 drafts were "".
    # Cause: with a long rule-heavy prompt and hidden reasoning, the
    # model spends its budget thinking and returns no content.
    for attempt in range(3):
        resp = _groq().chat.completions.create(
            model=model, temperature=0, reasoning_format="hidden",
            max_tokens=1600,
            messages=[{"role": "user", "content": prompt}])
        out = (resp.choices[0].message.content or "").strip()
        if len(out) >= 80:
            return out
        # last resort: let the model reason in the open rather than
        # silently return nothing
        if attempt == 1:
            resp = _groq().chat.completions.create(
                model=model, temperature=0, max_tokens=2000,
                messages=[{"role": "user", "content": prompt}])
            out = (resp.choices[0].message.content or "").strip()
            out = re.sub(r"<think>.*?</think>", "", out,
                         flags=re.DOTALL).strip()
            if len(out) >= 80:
                return out
    raise RuntimeError(
        "drafter returned an empty draft after 3 attempts — refusing "
        "to emit silence (an empty draft scores as 'grounded')")


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
                  model="openai/gpt-oss-120b") -> dict:
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
