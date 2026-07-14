<h1 align="center">⚖️ Mandate — The Sovereign Obligation OS</h1>

<p align="center">
  <b>Legal AI reads documents. IDP extracts fields.<br>
  Mandate executes what the enterprise owes — and keeps working when the cloud is gone.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-MVP_shipped-2EA44F?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/tests-50%2F50_green-2EA44F?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/deadline_engine-34_verified_cases-1F6FEB?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/license-Apache--2.0-8957E5?style=for-the-badge"/>
</p>

<p align="center">
  <code>deterministic where it counts</code> · <code>sovereign by default</code> · <code>measured, not asserted</code>
</p>

---

## The thesis

**A contract is not information. It is a machine that manufactures obligations** — *pay €185,435 by the 14th, respond within 10 business days, renew 90 days before term, notify the regulator, disclose the breach.* An enterprise signs thousands of these machines and then loses track of what they produce. The obligations are born in PDFs, scattered into inboxes, and forgotten until a deadline detonates. Missed *prazos* are the largest single category of legal malpractice; unmanaged renewals and indexation clauses bleed revenue in silence; one missed regulatory window becomes a headline fine.

The market's answer has been to build ever-smarter *readers* — tools that extract a clause or summarize a contract and stop there. That is the wrong altitude. **Reading a document is a subtask; the job is executing the obligation it creates** — computing the real deadline under the law that governs it, drafting the response, routing it for approval, and remembering that it happened, immutably.

And there is a second, harder truth the reader-tools ignore: **the enterprises that need this most cannot legally use what exists.** Banks under DORA, insurers, courts, healthcare groups, defense, public administration — the institutions drowning in obligation-bearing documents — are barred from streaming those documents to a US cloud API, and have learned to ask the follow-up question every AI vendor dodges: *what happens when the API is down, rate-limited, or deprecated mid-quarter?*

**Mandate is the answer to both at once.** It compiles obligation-bearing documents into a living **Obligation Graph** and executes the follow-through under two non-negotiable doctrines:

> **1 · The LLM proposes; the engine computes.** Anything with legal consequence — deadline arithmetic, obligation state, the audit trail — is deterministic, tested, source-cited code. Courts do not accept *"the model estimated."* Language models extract and draft; **deterministic code computes and gates; a human approves.**
>
> **2 · Sovereign by default, resilient by architecture.** The system runs inside the customer's perimeter and degrades in rungs — frontier LLM → local model → classical heuristics → **rules + playbooks + humans**. The legally dangerous parts never depended on connectivity, so an outage is a *quality dial, not a failure* — and it is logged as an auditable event.

You don't win Legal AI and IDP by building a better reader. **You absorb them** — reading becomes a pipeline stage, extraction becomes a swappable subsystem — and you ship the thing a regulated European buyer is actually allowed to deploy: a ledger of what the enterprise owes, to whom, by when, in their language, inside their walls, with its error rates printed on the label.

---

## Results — every claim, its evidence

| # | Claim | Evidence |
|---|---|---|
| 1 | **The dangerous parts never needed the cloud** | The Deadline Engine and Obligation Graph are deterministic, LLM-free code. Due dates compute, obligations track, the ledger holds — with every AI service on earth unreachable. **34 hand-verified deadline cases** across two jurisdictions, green |
| 2 | **The doctrine is enforced mechanically, not promised** | The drafting agent must embed the engine's computed date *verbatim*; a deterministic red-team rejects any draft whose date/amount diverges from the record; the LLM critic is **forbidden from recomputing** the date. On its **first live run the gate blocked a flawed draft** — catching a misleading date the drafter prompt itself had induced |
| 3 | **Cloud extraction is near-perfect; the sovereign tier trades completeness, not correctness** | Zero-shot on 40 unseen documents. **Cloud (qwen3-32b): 99.8%** — 0 abstentions, 1 error in 440 fields. **Local 7B, fully offline, ~6s/doc: 91% macro** — but it **abstains on 7.3%** (→ human queue) and **errs on only 2.0%**, with errors concentrated in one hard document type, not spread randomly |
| 4 | **Extraction quality came from reading disagreements, not guessing** | Prompt-specification iteration, measured at each step: **v1 0.83 → v2 0.94 → v3 1.00 → v4 1.00** macro. Every jump traced to a *named* specification bug found by dumping the model's mistakes and reading them |
| 5 | **The ledger is tamper-evident by construction** | Every claim, computation, draft and approval is an append-only, **SHA-256 hash-chained** event. Editing one byte anywhere breaks `verify_chain()` — proven with a forged-record test. Full event-sourced **replay** rebuilds all state from the log alone |
| 6 | **Multilingual — and honest about it per language** | pt-PT + English, measured *separately* — which is precisely how the local model's language-asymmetric weakness (English contract party-attribution) was caught. Two-axis design: **language ≠ jurisdiction** (an English contract can be governed by Portuguese law) |
| 7 | **Governance a regulator could read** | Human gates placed by *measured* error rates; per-field provenance (which tier or human produced each claim); an immutable event log that records the outages themselves — the DORA/AI-Act checklist, satisfied by architecture rather than paperwork |

<p align="center">
  <img src="docs/demo_process.png" width="900" alt="Mandate processing an EU regulatory notice end-to-end: the engine-computed deadline under Reg. 1182/71 with its cited trace, an AI-drafted response embedding that date verbatim, an all-green red-team panel, and the human approval gate"/>
  <br><i>An EU regulatory notice, processed end-to-end: engine-computed deadline → AI draft (embedding that date verbatim) → all-green red-team → the human approval gate.</i>
</p>

---

## Architecture

<p align="center">
  <img src="docs/architecture.png" width="1000" alt="Mandate architecture: a six-stage pipeline (perceive, compile, compute, act, gate, approve) with the degradation ladder on the left, the tamper-evident hash-chained ledger on the right, and the deterministic deadline engine at the core"/>
</p>

Six verbs, two rails. Down the centre: **Perceive → Compile → Compute → Act → Gate → Approve.** On the left rail, the **degradation ladder** — extraction runs on any rung, and the deadline engine is not AI at all, so due dates compute even with every model off. On the right rail, the **tamper-evident ledger** — every step, immutably recorded. The green core is the sacred, deterministic heart: the doctrine made structural.

---

## The measured degradation ladder

The pitch's signature artifact — because **nobody else in legal-AI publishes their error rates**, and showing yours is the differentiation. Quality is measured on 40 documents, per field, per language, per failure mode:

| Rung | Mode | Macro (pt / en) | Abstains | Wrong | What it means |
|---|---|:---:|:---:|:---:|---|
| **0** | ☁️ **Cloud AI** — qwen3-32b (Groq) | **1.00 / 0.99** | 0 % | 0.2 % | Best quality. Needs internet + API key; documents leave the machine (redacted in production) |
| **1** | 🔒 **Local AI** — qwen2.5-7b (Ollama, **offline**, ~6 s/doc on an M1 Pro) | **0.92 / 0.88** | 7.3 % | 2.0 % | **Abstains rather than hallucinates.** Nothing leaves the machine. Residual errors concentrated in EN contract party-attribution — not random |
| **2** | ⚙️ **Rules only** — anchored heuristics | 1.00\* | — | — | No AI at all; always available, even fully offline. \*template-fit ceiling on the synthetic corpus (honesty-noted) |
| **3** | 📋 **Playbooks** — engine + humans + procedures | — | — | — | The floor that never falls |

**The headline, quantified:** the sovereign 7B tier trades *completeness, not correctness*. Offline, it abstains on 7 % of fields (each routed to a human) and errs on 2 % — and that 2 % lives almost entirely in one hard document type (English reciprocal contracts, party attribution), not smeared randomly across the schema. A frontier cloud tier reaches 99.8 %. **You choose the trade; the delta is published** — per field, per language, per failure mode.

> **Prompt-specification as engineering.** Cloud macro climbed **v1 0.83 → v2 0.94 → v3 1.00 → v4 1.00**, and not one gain came from luck. v1's misses were *specification* bugs: `obligation_type` defined as the document's topic rather than the debtor's action (8/8 administrative notices mislabelled); `creditor` conflated with the court; `legal_basis` ambiguous between the clause that creates the obligation and the statute that governs its period. Each was found by dumping the model's disagreements, reading them, and tightening the contract. The local tier's own weaknesses were localized the same way.

---

## What was built — phase by phase

**Phase 1 · The Deadline Engine + PT jurisdiction pack.** The deterministic heart, built first because everything hangs off it. Three Portuguese counting regimes, each with its statutory basis encoded: `cc_corridos` (Código Civil art. 279.º — event-day exclusion, Sunday/holiday end-roll, and the subtlety that **Saturdays do *not* roll under the CC**), `cpc_processual` (CPC art. 138.º — continuous counting **suspended during *férias judiciais***, computed from the Easter algorithm, with the urgent-process exception and Sat/Sun/holiday end-roll), and `cpa_uteis` (CPA art. 87.º — business days). Every computed deadline returns an **explanation trace with legal references** — the auditable evidence chain. *21 hand-verified cases.*

**Phase 1b · The EU jurisdiction pack.** Regulation 1182/71 (`eu_1182_days`, `eu_1182_working_days`, plus weeks/months) with EU-institution holidays. This proved the pack architecture: **the same engine now runs two jurisdictions with contradictory rules** — the CC doesn't roll Saturdays, Reg. 1182/71 does — selected by *data*, not code. *13 more cases; 34 total.*

**Phase 2 · The Obligation Graph.** Typed claims, each carrying a source span, a calibrated confidence, and *which tier extracted it* (the ladder lives in the data model). Obligations reference their claims — one cannot exist without evidence. An enforced state machine (`PENDING → IN_PROGRESS → AWAITING_APPROVAL → SATISFIED`; illegal transitions raise) makes the human gate structural. And an **append-only, hash-chained event log** with tamper detection and full replay — the *"a court may one day read it"* ledger, born here, not retrofitted in a security sprint.

**Phase 3a · Synthetic corpus + gold set.** A deterministic generator (seed-reproducible) producing 40 realistic obligation-bearing documents (24 pt / 16 en, 5 types) with **distractor dates and amounts by design** — a second date, a second amount — so naive "grab the first match" extractors measurably fail. pt-PT number formatting (`185.435,45`) included as a deliberate trap. Every gold deadline is verified computable through the engine: corpus and engine are provably consistent.

**Phase 3b · Tiered extraction, measured.** One Pydantic contract, three tiers behind one interface (Groq cloud / Ollama local / anchored heuristics), *abstention-when-unsure* as doctrine. The prompt-iteration story (above) is the phase's spine — three spec bugs found and fixed by reading disagreements, reaching macro 1.00 on cloud and a fully-characterized 0.91 on the offline 7B.

**Phase 4 · The agent crew.** The pipeline (perceive → compile → compute → act → gate → remember) wiring everything together. The drafting agent receives the engine's computed deadline and must embed it verbatim; a deterministic red-team checks the date, amount and citation, and a hostile LLM critic attacks the draft — **forbidden from recomputing the engine's date** (the doctrine applies to critics too). On the first live run the gate **correctly blocked a flawed draft**; the post-mortem fixed a locale bug in the amount check and a date-juxtaposition ambiguity in the drafter prompt. LLM failures degrade to a failed check — never a crash.

**Phase 5 · The demo.** A Streamlit application: process a document on any tier, watch the engine's cited trace, read the draft and the red-team verdict, approve into the hash chain. A live **system-mode badge** shows which rungs are available (auto-detecting the Groq key and a local Ollama), and the Method tab publishes the honest benchmark.

<p align="center">
  <img src="docs/demo_ledger.png" width="900" alt="The obligation ledger: obligations across PT and EU jurisdictions sorted by due date, the hash-chain integrity indicator, and the append-only event log showing per-tier extraction provenance"/>
  <br><i>The obligation ledger — PT + EU obligations sorted by deadline, the hash-chain integrity indicator, and the append-only event log with per-tier provenance (<code>agent:extractor/tier0 → compiler → engine:deadline → red_team</code>).</i>
</p>

---

## Design decisions worth defending

- **Why a deterministic engine instead of asking the LLM for the date?** Because a deadline is a legal fact with consequences, and *"the model estimated the 14th"* is not a defensible position in front of a court or a regulator. The engine's output is reproducible, auditable, and cites the statute for every step. The LLM's job is to read the document and propose the inputs; the arithmetic is code.
- **Why abstention over best-guess?** In a legal system a confident wrong answer is the worst output class that exists — it routes a mistake downstream silently. A `null` routes to a human. The 7B's 7.3 % abstention rate is the model *knowing what it doesn't know*, and it is a feature.
- **Why measure per language separately?** Because aggregate accuracy hides asymmetry. The 7B's residual errors are almost all in English reciprocal contracts (party attribution) — a fact invisible in a single blended number, and exactly the kind of thing an operator in offline mode needs to be warned about.
- **Why hash-chain the log from day one?** Because tamper-evidence cannot be retrofitted honestly — a log that became append-only *last Tuesday* proves nothing about Monday. Chaining is cheap to build early and impossible to fake later.
- **Why a hostile critic that can't recompute?** Because a critic that re-derives the deadline re-introduces the exact non-determinism the engine exists to eliminate — and in testing, a recomputing critic *failed a correct draft with its own wrong arithmetic.* The doctrine is total: only the engine computes.

---

## Run it

```bash
git clone https://github.com/hugocorreia123/mandate-the-sovereign-obligation-os
cd mandate-the-sovereign-obligation-os && uv sync
uv run pytest -q                              # 50 passed

# generate the corpus (deterministic, seed 42)
uv run python -c "import sys; sys.path.insert(0,'core'); \
  from corpus import generate_corpus; generate_corpus('data/corpus')"

# process one document end-to-end — RULES-ONLY tier: no API key, fully offline
uv run python scripts/process_document.py data/corpus/docs/pt_cit_000.txt

# with the AI crew (needs GROQ_API_KEY) and/or local Ollama for the sovereign tier
uv run python scripts/process_document.py data/corpus/docs/pt_cit_000.txt --tier tier0 --llm

# the demo
uv run streamlit run app.py
```

Reproduce the ladder benchmark: `uv run python scripts/benchmark_extraction.py --tiers tier2 tier0 tier1` — the local tier needs `ollama pull qwen2.5:7b-instruct`.

---

## Stack

`Python 3.11` · `uv` · **Pydantic** (typed extraction contract) · **python-dateutil + holidays** (deterministic deadline engine) · **Groq qwen3-32b** (cloud tier + drafter + hostile critic) · **Ollama qwen2.5-7b** (local sovereign tier) · **Streamlit** · **SHA-256 hash-chained event log**

---

## Scope & honest limitations

The corpus is synthetic — realistic templates, not scanned real filings (VLM parsing of scans is a documented next phase). Jurisdiction packs encode the common regimes and **document their exclusions** (municipal holidays, *dilação*, the ≥6-month CPC exception, art. 139.º grace days) — a simplified, source-cited engineering implementation, **not legal advice**. Tier-2 heuristics score 100 % because they are anchored to the corpus templates — a ceiling, honesty-noted, not a claim that regex beats LLMs on real documents. The benchmark is n = 40 (directional). Encoded legal rules should be reviewed by a qualified lawyer before any real use.

---

## Related work

Mandate applies a **detect → investigate → human-decide** pattern to a fourth domain — *legal obligations, sovereign* — completing a portfolio that spans financial, physical, and legal systems with one consistent discipline:

| Project | Domain | Signature result |
|---|---|---|
| [**Tracer**](https://github.com/hugocorreia123/tracer-aml-graph-intelligence) | Financial-crime networks | GraphSAGE +40 % PR-AUC over tabular; SAR agent, judge **κ = 0.942** · *live demo* |
| [**Turbine**](https://github.com/hugocorreia123/turbine-predictive-maintenance) | Predictive maintenance | Temporal CNN wins the hard C-MAPSS benchmark; calibrated RUL; agentic copilot · *live demo* |
| [**Sentinel**](https://github.com/hugocorreia123/sentinel-fraud-mlops) | Transaction fraud (MLOps) | Champion/challenger, p99 ~96 ms, shadow A/B, full observability · *HF Spaces* |
| [**Mandate**](https://github.com/hugocorreia123/mandate-the-sovereign-obligation-os) | **Legal obligations (sovereign)** | Deterministic engine · measured degradation ladder · tamper-evident ledger |

The same throughout: **deterministic where it counts, honest baselines, measured findings including the negative ones, and a human in the loop by measured necessity.**

---

<p align="center">
  <b>Hugo Correia</b> — Data Scientist · ML & AI Engineer, Lisbon<br>
  <a href="https://www.linkedin.com/in/hugogncorreia">LinkedIn</a> · <a href="https://github.com/hugocorreia123">GitHub</a>
</p>
